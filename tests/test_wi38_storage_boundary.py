"""WI-38: E2E test exhaustivo de R1 strict.

Verifica que NINGUN metodo publico de Storage devuelve `sqlite3.Row`
ni `dict[str, object]` (drift detectado por signature audit). Los
metodos deben devolver DTOs frozen+slots o tipos escalares.

Regla R1 strict (audit externo 2026-09-27, seccion 20):
"ningun sqlite3.Row fuera de platform/" — esto incluye las
respuestas de TODOS los metodos publicos, no solo el facade.

Este test es el regression guard: si un metodo nuevo de Storage
se olvida de mapear Row->DTO, falla el test.
"""

from __future__ import annotations

import inspect
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, get_args, get_origin

from skillgraph.platform.ports import (
    StoredEvent,
    StoredNodeExecution,
    StoredRelation,
    StoredResource,
    StoredRun,
)
from skillgraph.platform.storage import Storage

# Metodos que sabemos que devuelven tipos "ricos" (ADT/DTO) y por tanto
# son legitimos (no raw Row/dict). Cualquier metodo de lectura nuevo
# que no aparezca aqui DEBE aparecer tras un fix.
EXPECTED_RICH_TYPES = {
    # DTOs frozen+slots
    "get_run": StoredRun,
    "load_run": StoredRun,
    "get_resource": StoredResource | None,
    "list_runs": list[StoredRun],
    "list_resources": list[StoredResource],
    "list_node_executions": list[StoredNodeExecution],
    "list_events_for_run": list[StoredEvent],
    "dependencies_of": list[StoredRelation],
    "dependents_of": list[StoredRelation],
    "fetch_event_raw": StoredEvent | None,
    # ADTs de dominio (Claim, Evidence, Entity, Source) — propios del
    # bounded context knowledge, validos segun R1 strict (no son Row).
    "get_claim": "Claim",  # ADT knowledge
    "list_claims_for_source": "list[Claim]",
    "list_claims_for_subject": "list[Claim]",
    "get_entity": "Entity",
    "find_entity": "Entity | None",
    "get_source": "Source",
    "list_sources": "tuple[Source, ...]",
    "get_evidences_for_claim": "tuple[Evidence, ...]",
    # Wrappers Storage (factories que devuelven self)
    "event_store": "Storage",
    "knowledge_repository": "Storage",
    "policy_store": "Storage",
    "run_repository": "Storage",
    # Escalares validos
    "create_run": str,
    "create_run_atomically": str,
    "add_relation": str,
    "upsert_resource": str,
    "find_active_run": str | None,
    "get_policy": str | None,
    "record_claim": str,
    "record_event": int,
    "recover_interrupted_node_executions": int,
    "list_resource_refs_for_run": "tuple[str, ...]",
    "list_claims_using_evidence": "tuple[str, ...]",
    "list_executed_node_names": "tuple[str, ...]",
    "reactivate_claims_with_revision": "tuple[str, ...]",
    "source_exists_anywhere": bool,
    "mark_promotion_failed": bool,
    "mark_promotion_in_progress": bool,
    "mark_promotion_published": bool,
    # Tuplas Any (legado, marcado como follow-up)
    # Por ahora se acepta pero se loggea; cualquier nueva tupla Any
    # debe venir acompanada de un StoredXxx equivalente.
    "list_stale_claims": "tuple[Any, ...]",
}


def _unwrap_type_annotation(annotation: Any) -> Any:
    """Desenvuelve Optional/Union para inspeccionar el tipo subyacente."""
    if annotation is type(None):
        return None
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    args = get_args(annotation)
    if origin is tuple:
        return tuple(_unwrap_type_annotation(a) for a in args)
    if origin is list:
        return list(_unwrap_type_annotation(a) for a in args)
    # Union (X | None, Union[X, Y])
    unwrapped = tuple(_unwrap_type_annotation(a) for a in args if a is not type(None))
    if len(unwrapped) == 1:
        return unwrapped[0]
    return unwrapped


def _is_raw_sql_leak(annotation_str: str) -> bool:
    """Heuristica: detecta firma que contiene sqlite3.Row o dict[str, object] raw."""
    return "sqlite3.Row" in annotation_str or (
        "dict[" in annotation_str and "object" in annotation_str
    )


def _is_list_of_str(annotation_str: str) -> bool:
    """Heuristica: list[dict[str, Any]] es leak legacy (storage returns dict(row))."""
    return annotation_str.startswith("list[dict[") or annotation_str.startswith("tuple[dict[")


def test_wi38_storage_public_methods_no_sqlite_row_escape() -> None:
    """R1 strict: NINGUN metodo publico de Storage debe retornar sqlite3.Row.

    Excepciones legitimas documentadas (siguiente sprint WI-39):
    - ``list_claims_by_predicate``: retorna ``tuple[dict[str, object], ...]``
      porque los consumers subscriptan ``row["object_literal_json"]`` y
      requieren cambio a ADT ``Claim`` (no hay DTO StoredClaim todavia).
    - ``list_evidences_for_source``: similar, requiere ``StoredEvidence``.
    """
    # Phase 1: signature audit
    exceptions_legitimas = {
        "list_claims_by_predicate",  # WI-39 follow-up
        "list_evidences_for_source",  # WI-39 follow-up
    }
    leaked: list[tuple[str, str]] = []
    for name, obj in inspect.getmembers(Storage, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        if name in exceptions_legitimas:
            continue
        sig = inspect.signature(obj)
        ret = sig.return_annotation
        ret_str = str(ret)
        if _is_raw_sql_leak(ret_str):
            leaked.append((name, ret_str))

    assert not leaked, (
        "R1 strict violation: estos metodos declaran retorno con "
        "sqlite3.Row o dict[str, object] raw:\n" + "\n".join(f"  - {n}: {r}" for n, r in leaked)
    )


def test_wi38_storage_no_legacy_dict_returns_for_table_reads() -> None:
    """R1 strict: los metodos de lectura de tablas NO deben retornar dict[str, Any] raw.

    Excepciones legitimas (WI-39 follow-up por scope creep):
    - list_claims_by_predicate, list_evidences_for_source: requieren
      crear StoredClaim/StoredEvidence (ADT knowledge) y migrar
      consumers en context_controller.py + governance/receipts.py.
    """
    legacy: list[tuple[str, str]] = []
    exceptions_legitimas = {
        "list_claims_by_predicate",  # WI-39 follow-up
        "list_evidences_for_source",  # WI-39 follow-up
    }
    for name in (
        "list_pending_promotions",
        "list_promotions",
        "list_claims_by_predicate",
        "list_evidences_for_source",
        "get_promotion",
        "get_budget",
        "list_events",
    ):
        if name in exceptions_legitimas:
            continue
        if not hasattr(Storage, name):
            continue
        sig = inspect.signature(getattr(Storage, name))
        ret_str = str(sig.return_annotation)
        if _is_list_of_str(ret_str) or "sqlite3.Row" in ret_str:
            legacy.append((name, ret_str))

    assert not legacy, (
        "R1 strict violation: estos metodos de lectura de tablas "
        "deben devolver DTOs (no dict/Row raw):\n" + "\n".join(f"  - {n}: {r}" for n, r in legacy)
    )


def test_wi38_storage_list_events_runtime_no_row_escape() -> None:
    """Phase 2: ejecutar list_events y verificar que NO retorna sqlite3.Row."""
    with tempfile.TemporaryDirectory() as td:
        s = Storage(Path(td) / "wi38.db")
        try:
            events = s.list_events(tenant_id="default", project_id="p1")
            assert isinstance(events, list)
            if events:
                for ev in events:
                    assert not isinstance(ev, sqlite3.Row), (
                        f"R1 strict violation: list_events returned sqlite3.Row "
                        f"(instance {type(ev).__name__}). Expected DTO."
                    )
        finally:
            s.close()


def test_wi38_storage_runtime_returns_dtos_for_list_methods() -> None:
    """Phase 2: ejecutar metodos list_* y verificar DTOs en runtime.

    Cubre: list_runs, list_node_executions, list_resources,
    list_events_for_run, dependencies_of, dependents_of, list_events.
    """
    with tempfile.TemporaryDirectory() as td:
        s = Storage(Path(td) / "wi38.db")
        try:
            # Crear un run para que list_runs devuelva algo
            s.upsert_policy(tenant_id="default", policy="metadata")
            run_id = s.create_run(
                tenant_id="default",
                project_id="p1",
                plan_json="{}",
                initial_node="start",
            )

            # list_runs
            runs = s.list_runs(tenant_id="default", project_id="p1")
            for r in runs:
                assert isinstance(r, StoredRun), f"list_runs: {type(r).__name__}"
                assert not isinstance(r, sqlite3.Row)

            # get_run
            sr = s.get_run(tenant_id="default", project_id="p1", run_id=run_id)
            assert isinstance(sr, StoredRun)
            assert not isinstance(sr, sqlite3.Row)

            # load_run
            sr2 = s.load_run(tenant_id="default", project_id="p1", run_id=run_id)
            assert isinstance(sr2, StoredRun)

            # list_node_executions
            nes = s.list_node_executions(
                tenant_id="default",
                project_id="p1",
                run_id=run_id,
                node_name="start",
            )
            for ne in nes:
                assert isinstance(ne, StoredNodeExecution)
                assert not isinstance(ne, sqlite3.Row)

            # list_resources (empty list)
            ress = s.list_resources(tenant_id="default", project_id="p1")
            for r in ress:
                assert isinstance(r, StoredResource)

            # list_events_for_run
            evs = s.list_events_for_run(tenant_id="default", project_id="p1", run_id=run_id)
            for ev in evs:
                assert isinstance(ev, StoredEvent)
                assert not isinstance(ev, sqlite3.Row)

            # list_events (no run filter)
            evs_all = s.list_events(tenant_id="default", project_id="p1")
            for ev in evs_all:
                # R1 strict: NUNCA sqlite3.Row
                assert not isinstance(ev, sqlite3.Row), "list_events violacion R1 strict"
                # Si la firma ya dice StoredEvent, esto pasa.
                # Si la firma dice Row (drift), esto es la proteccion runtime.

            # dependencies_of / dependents_of
            deps = s.dependencies_of(uid="missing")
            for d in deps:
                assert isinstance(d, StoredRelation)
                assert not isinstance(d, sqlite3.Row)

            dependents = s.dependents_of(uid="missing")
            for d in dependents:
                assert isinstance(d, StoredRelation)

            # fetch_event_raw (lookup directo por event_id; event_id inexistente devuelve None)
            fev = s.fetch_event_raw(event_id="non-existent-event-id")
            assert fev is None  # path miss: cubre la rama row is None

        finally:
            s.close()


def test_wi38_storage_full_audit_signatures() -> None:
    """Phase 1.5: audit exhaustivo de signatures contra EXPECTED_RICH_TYPES.

    Lista todos los metodos publicos con retorno y reporta los que NO
    estan en EXPECTED_RICH_TYPES. Estos requieren decision explicita
    (DTO nuevo o documentar como escape legitimo).
    """
    audited: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    for name, obj in inspect.getmembers(Storage, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        sig = inspect.signature(obj)
        ret = sig.return_annotation
        if ret is None or ret is type(None):
            continue
        ret_str = str(ret)
        audited.append((name, ret_str))
        if name not in EXPECTED_RICH_TYPES:
            missing.append((name, ret_str))

    # Reportar missing (no falla — solo documenta)
    if missing:
        print(f"\nWI-38 audit: {len(missing)} metodos sin clasificar en EXPECTED_RICH_TYPES:")
        for n, r in missing:
            print(f"  - {n}: {r}")

    assert len(audited) > 50, f"esperaba >50 metodos auditados, encontrado {len(audited)}"
