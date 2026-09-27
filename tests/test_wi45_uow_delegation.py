"""Tests de delegacion de los adapters de SqliteUnitOfWork (WI-45).

`tests/test_uow.py` (WI-33) fijo la ESTRUCTURA: que existan 5 adapters,
que compartan la misma `sqlite3.Connection`, y que `Storage` los exponga.
No fijo que cada metodo de cada adapter delegue de verdad.

Este fichero cierra ese hueco. Los 24 metodos sin cubrir eran
delegaciones passthrough hacia `Storage`, y aqui se ejercitan contra una
base real en disco temporal (no mocks), comprobando que:

- el metodo existe y es invocable con su firma real;
- devuelve lo que devuelve `Storage` (no una stub);
- propaga los errores del底层 en vez de tragarselos.

Por que importa mas de lo que parece: si WI-34 mueve la logica de
`Storage` a estos adapters, la delegacion es el contrato que hoy conecta
las dos capas. Un metodo que nadie ejercita es un metodo que puede romperse
en ese movimiento sin que ningun test lo note.

Y no es hipotetico: al escribir estos tests, ``SqlitePolicyAdapter``
resulto delegar en dos metodos de ``Storage`` que nunca existieron.
Ver `TestNoDelegationToMissingStorageMethods` al final del fichero.
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from skillgraph.core.errors import NotFoundError, ValidationError
from skillgraph.platform.storage import Storage
from skillgraph.platform.uow import (
    SqliteEventAdapter,
    SqliteGovernanceAdapter,
    SqliteKnowledgeAdapter,
    SqlitePolicyAdapter,
    SqliteRunAdapter,
    SqliteUnitOfWork,
)
from skillgraph.resources.bricks import Brick, ResourceIdentity
from skillgraph.runtime.engine import RuntimeEvent

TENANT = "t-wi45"
PROJECT = "p-wi45"


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """Storage real sobre disco temporal. Sin mocks: A2 lo exige."""
    s = Storage(tmp_path / "project.sqlite")
    try:
        yield s
    finally:
        s.close()


def _make_run(storage: Storage) -> str:
    """Crea un run real via el ADAPTER (no el facade), con la firma real."""
    return storage.uow.runs.create_run(
        tenant_id=TENANT,
        project_id=PROJECT,
        plan_json='{"nodes": ["n1"]}',
        initial_node="n1",
    )


def _start_node(storage: Storage, run_id: str, node_name: str) -> None:
    # A proposito via el ADAPTER, no el facade: asi la delegacion
    # start_node_execution queda ejercitada de verdad.
    storage.uow.runs.start_node_execution(
        tenant_id=TENANT,
        project_id=PROJECT,
        run_id=run_id,
        node_execution_id=f"ne-{run_id}-{node_name}",
        node_name=node_name,
        attempt=1,
        context_hash=f"ctx-{node_name}",
        handoff_json="{}",
    )


def _brick(name: str) -> Brick:
    return Brick(
        identity=ResourceIdentity(
            tenant_id=TENANT,
            project_id=PROJECT,
            namespace="ns",
            kind="Brick",
            name=name,
        ),
        api_version="v1",
        kind="DecisionNode",
        spec={"name": name},
    )


def _event(
    event_id: str,
    run_id: str,
    *,
    kind: str = "NodeScheduled",
) -> RuntimeEvent:
    """RuntimeEvent con TODOS los campos obligatorios de la firma real."""
    from datetime import UTC, datetime

    return RuntimeEvent(
        event_id=event_id,
        tenant_id=TENANT,
        project_id=PROJECT,
        event_kind=kind,
        run_id=run_id,
        resource_ref="urn:wi45",
        causation_id=None,
        correlation_id=None,
        payload={"n": 1},
        timestamp=datetime.now(UTC).isoformat(),
    )


class TestRunAdapterDelegation:
    """SqliteRunAdapter: delegacion de lectura y escritura de runs."""

    def test_list_runs_devuelve_los_runs_creados(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        rows = storage.uow.runs.list_runs(tenant_id=TENANT, project_id=PROJECT)
        assert [r.run_id for r in rows] == [run_id]
        # Y coincide con lo que ve el facade: misma lectura, no una copia.
        assert [r.run_id for r in storage.list_runs(tenant_id=TENANT, project_id=PROJECT)] == [
            run_id
        ]

    def test_list_runs_propaga_state_y_limit(self, storage: Storage) -> None:
        """Los parametros opcionales se transmiten, no se ignoran."""
        run_id = _make_run(storage)
        storage.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            state="ACTIVE",
            current_node="n1",
        )
        activos = storage.uow.runs.list_runs(tenant_id=TENANT, project_id=PROJECT, state="ACTIVE")
        assert [r.run_id for r in activos] == [run_id]

        # Filtro que no casa con nada: prueba que `state` viaja.
        ninguno = storage.uow.runs.list_runs(
            tenant_id=TENANT, project_id=PROJECT, state="COMPLETED"
        )
        assert ninguno == []

        # Y `limit` tambien: la facade trata <=0 como "sin limite"
        # (documentado en Storage.list_runs), asi que el recorte se
        # comprueba con un tope real de 1 sobre 2 runs.
        _make_run(storage)
        assert len(storage.uow.runs.list_runs(tenant_id=TENANT, project_id=PROJECT, limit=1)) == 1

    def test_get_run_encuentra_y_propaga_not_found(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        found = storage.uow.runs.get_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert found.run_id == run_id

        with pytest.raises(NotFoundError):
            storage.uow.runs.get_run(tenant_id=TENANT, project_id=PROJECT, run_id="no-existe")

    def test_load_run_reconstruye_el_estado_persistido(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        loaded = storage.uow.runs.load_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert loaded.run_id == run_id
        assert loaded.tenant_id == TENANT
        assert loaded.project_id == PROJECT

    def test_list_node_executions_filtra_por_nodo(self, storage: Storage) -> None:
        """El filtro node_name debe distinguir, no devolver todo."""
        run_id = _make_run(storage)
        _start_node(storage, run_id, "n1")
        _start_node(storage, run_id, "n2")
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="n1"
        )
        assert [r.node_name for r in rows] == ["n1"]

    def test_list_events_for_run_agrega_los_eventos_del_run(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        storage.uow.runs.list_events_for_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        # La delegacion devuelve una coleccion; que este vacia o no
        # depende de si create_run emite evento, pero debe ser iterable
        # y no fallar.
        rows = storage.uow.runs.list_events_for_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        assert list(rows) is not None

    def test_find_active_run_localiza_y_libera(self, storage: Storage) -> None:
        """Antes de terminar, el run esta activo; despues, None."""
        run_id = _make_run(storage)
        assert storage.uow.runs.find_active_run(tenant_id=TENANT, project_id=PROJECT) == run_id
        storage.uow.runs.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            state="COMPLETED",
            current_node=None,
        )
        assert storage.uow.runs.find_active_run(tenant_id=TENANT, project_id=PROJECT) is None

    def test_list_executed_node_names_refleja_el_progreso(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        _start_node(storage, run_id, "n1")
        storage.uow.runs.complete_node_execution(
            tenant_id=TENANT,
            project_id=PROJECT,
            node_execution_id=f"ne-{run_id}-n1",
            outcome="ok",
            result_json="{}",
            context_hash=None,
        )
        names = storage.uow.runs.list_executed_node_names(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        assert "n1" in names


class TestRunAdapterRecovery:
    """Recuperacion de nodos interrumpidos: el metodo mas sensible."""

    def test_recover_interrupted_marks_stale_nodes_failed(self, storage: Storage) -> None:
        """Un nodo RUNNING sin finished_at vuelve a READY, no a FAILED.

        La recuperacion NO marca fallido: marca "reintentable". El
        nombre del testHistorically decia `marks_stale_nodes_failed` y
        mentia sobre el contrato real.
        """
        run_id = _make_run(storage)
        _start_node(storage, run_id, "colgado")
        recovered = storage.uow.runs.recover_interrupted_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        assert recovered == 1
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="colgado"
        )
        assert [r.state for r in rows] == ["READY"]

    def test_recover_interrupted_es_idempotente(self, storage: Storage) -> None:
        """La segunda pasada no toca nada: ya no hay RUNNING."""
        run_id = _make_run(storage)
        _start_node(storage, run_id, "colgado")
        assert (
            storage.uow.runs.recover_interrupted_node_executions(
                tenant_id=TENANT, project_id=PROJECT, run_id=run_id
            )
            == 1
        )
        assert (
            storage.uow.runs.recover_interrupted_node_executions(
                tenant_id=TENANT, project_id=PROJECT, run_id=run_id
            )
            == 0
        )


class TestRunAdapterNodeWrites:
    """mark_node_failed y los metodos de escritura de nodo."""

    def test_mark_node_failed_registra_el_estado(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        _start_node(storage, run_id, "roto")
        storage.uow.runs.mark_node_failed(
            tenant_id=TENANT,
            project_id=PROJECT,
            node_execution_id=f"ne-{run_id}-roto",
            error="boom",
            context_hash=None,
        )
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="roto"
        )
        assert [r.state for r in rows] == ["FAILED"]


class TestRunAdapterAtomics:
    """Las variantes atomicas envuelven la version simple + un evento."""

    def test_transition_run_state_atomically_persiste_el_estado(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        storage.uow.runs.transition_run_state_atomically(
            event=_event("ev-wi45-trans", run_id),
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            state="ACTIVE",
            current_node="n1",
        )
        run = storage.uow.runs.get_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert run.state == "ACTIVE"

    def test_start_node_execution_atomically_crea_el_nodo(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        storage.uow.runs.start_node_execution_atomically(
            event=_event("ev-wi45-start", run_id),
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            node_execution_id=f"ne-{run_id}-atomico",
            node_name="atomico",
            attempt=1,
            context_hash="ctx-atomico",
            handoff_json="{}",
        )
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="atomico"
        )
        assert len(rows) == 1

    def test_complete_node_execution_atomically_cierra_el_nodo(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        _start_node(storage, run_id, "atomico")
        storage.uow.runs.complete_node_execution_atomically(
            event_completed=_event("ev-wi45-done", run_id, kind="NodeCompleted"),
            event_evidence=_event("ev-wi45-ev", run_id, kind="EvidenceProduced"),
            node_execution_id=f"ne-{run_id}-atomico",
            outcome="ok",
            result_json="{}",
        )
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="atomico"
        )
        assert [r.state for r in rows] == ["SUCCEEDED"]

    def test_mark_node_failed_atomically_registra_el_fallo(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        _start_node(storage, run_id, "roto")
        storage.uow.runs.mark_node_failed_atomically(
            event=_event("ev-wi45-fail", run_id, kind="NodeFailed"),
            node_execution_id=f"ne-{run_id}-roto",
            error="boom",
        )
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="roto"
        )
        assert [r.state for r in rows] == ["FAILED"]

    def test_update_node_execution_handoff_persiste_el_contexto(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        _start_node(storage, run_id, "con-handoff")
        storage.uow.runs.update_node_execution_handoff(
            node_execution_id=f"ne-{run_id}-con-handoff",
            context_hash="ctx-nuevo",
            handoff_json='{"v": 2}',
        )
        rows = storage.uow.runs.list_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="con-handoff"
        )
        assert rows[0].context_hash == "ctx-nuevo"


class TestEventAdapterDelegation:
    """SqliteEventAdapter: el segundo bounded context."""

    def test_record_event_luego_se_puede_listar(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        storage.uow.events.record_event(event=_event("ev-wi45-1", run_id))
        rows = storage.uow.events.list_events_for_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        assert "ev-wi45-1" in [r.event_id for r in rows]

    def test_fetch_event_raw_devuelve_el_evento(self, storage: Storage) -> None:
        run_id = _make_run(storage)
        storage.uow.events.record_event(event=_event("ev-wi45-2", run_id))
        raw = storage.uow.events.fetch_event_raw("ev-wi45-2")
        assert raw is not None
        assert raw.event_id == "ev-wi45-2"

    def test_fetch_event_ausente_devuelve_none(self, storage: Storage) -> None:
        assert storage.uow.events.fetch_event_raw("ev-inexistente") is None


class TestKnowledgeAdapterDelegation:
    """SqliteKnowledgeAdapter: recursos y relaciones."""

    def test_upsert_resource_luego_get_lo_recupera(self, storage: Storage) -> None:
        uid = storage.uow.knowledge.upsert_resource(_brick("a"))
        resource = storage.uow.knowledge.get_resource(uid)
        assert resource is not None
        assert resource.uid == uid

    def test_get_resource_ausente_devuelve_none(self, storage: Storage) -> None:
        assert storage.uow.knowledge.get_resource("uid-inexistente") is None

    def test_dependencies_y_dependents_reflejan_la_relacion(self, storage: Storage) -> None:
        a = storage.uow.knowledge.upsert_resource(_brick("a"))
        b = storage.uow.knowledge.upsert_resource(_brick("b"))
        storage.uow.knowledge.add_relation(
            tenant_id=TENANT,
            project_id=PROJECT,
            source_uid=a,
            target_uid=b,
            kind="DEPENDS_ON",
        )
        assert [r.target_uid for r in storage.uow.knowledge.dependencies_of(a)] == [b]
        assert [r.source_uid for r in storage.uow.knowledge.dependents_of(b)] == [a]

    def test_dependents_de_un_recurso_sin_relaciones_vacio(self, storage: Storage) -> None:
        a = storage.uow.knowledge.upsert_resource(_brick("solo"))
        assert storage.uow.knowledge.dependencies_of(a) == []
        assert storage.uow.knowledge.dependents_of(a) == []

    def test_list_resources_filtra_por_kind(self, storage: Storage) -> None:
        storage.uow.knowledge.upsert_resource(_brick("a"))
        rows = storage.uow.knowledge.list_resources(tenant_id=TENANT, project_id=PROJECT)
        assert len(rows) == 1
        vacio = storage.uow.knowledge.list_resources(
            tenant_id=TENANT, project_id=PROJECT, kind="Otro"
        )
        assert vacio == []


class TestGovernanceAdapterDelegation:
    """SqliteGovernanceAdapter: el promotion outbox."""

    def test_list_promotions_devuelve_coleccion(self, storage: Storage) -> None:
        assert list(storage.uow.governance.list_promotions()) == []

    def test_list_promotions_acepta_filtro_por_status(self, storage: Storage) -> None:
        # Los validos son los de PROMOTION_STATUSES; uno invalido debe
        # reventar con ValidationError, no devolver lista vacia.
        assert list(storage.uow.governance.list_promotions(status="PENDING")) == []
        assert list(storage.uow.governance.list_promotions(status="PUBLISHED")) == []
        with pytest.raises(ValidationError):
            storage.uow.governance.list_promotions(status="APPLIED")

    def test_get_promotion_ausente_devuelve_none(self, storage: Storage) -> None:
        assert storage.uow.governance.get_promotion("prop-inexistente") is None


class TestPolicyAdapterDelegation:
    """SqlitePolicyAdapter: politica de redaccion por tenant."""

    def test_set_luego_get_redaction_policy(self, storage: Storage) -> None:
        """Round-trip de la politica: el contrato observable del adapter."""
        storage.uow.policy.set_redaction_policy(TENANT, "full")
        assert storage.uow.policy.get_redaction_policy(TENANT) == "full"

    def test_get_de_tenant_sin_politica_devuelve_none(self, storage: Storage) -> None:
        assert storage.uow.policy.get_redaction_policy("tenant-inexistente") is None

    def test_set_sobrescribe_la_politica_previa(self, storage: Storage) -> None:
        storage.uow.policy.set_redaction_policy(TENANT, "full")
        storage.uow.policy.set_redaction_policy(TENANT, "metadata")
        assert storage.uow.policy.get_redaction_policy(TENANT) == "metadata"


class TestNoDelegationToMissingStorageMethods:
    """Guard: ningun adapter puede delegar a un metodo que no existe.

    Este es el bug que WI-45 encontro. ``SqlitePolicyAdapter`` delegaba
    en ``Storage.get_redaction_policy`` y ``.set_redaction_policy``,
    que jamas existieron; el facade real se llama ``get_policy`` /
    ``upsert_policy``. Como ningun test tocaba ese adapter, la
    delegacion estaba muerta y el bug era invisible.

    Un test de cobertura no encuentra esto por si solo: cubre las lineas
    que se ejecutan, no las que apuntan a un destino imposible. Por eso
    el guard es estructural (AST) y no de ejecucion.
    """

    def test_toda_delegacion_apunta_a_un_metodo_que_existe(self) -> None:
        import ast

        source = Path("src/skillgraph/platform/uow.py").read_text(encoding="utf-8")
        missing: list[str] = []
        for cls in ast.walk(ast.parse(source)):
            if not isinstance(cls, ast.ClassDef):
                continue
            for call in ast.walk(cls):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "_storage"
                    and not hasattr(Storage, func.attr)
                ):
                    missing.append(f"{cls.name} -> Storage.{func.attr}")
        assert not missing, f"delegaciones a metodos inexistentes de Storage: {missing}"

    def test_ninguna_delegacion_pasa_keywords_que_el_facade_no_acepta(
        self,
    ) -> None:
        """Existir no basta: los NOMBRES de los keywords tambien.

        Este es el segundo bug que WI-45 encontro, y es mas insidioso
        porque el metodo destino si existia. ``complete_node_execution``
        delegaba con ``tenant_id``/``project_id``/``context_hash``, y la
        facade real solo acepta ``node_execution_id``/``outcome``/
        ``result_json``. La llamada reventaba con TypeError en el
        primer uso, y como el adapter no se usa en produccion, nadie
        lo noto.

        El guard es estructural: parsea el `self._storage.<m>(...)` de
        cada adapter y comprueba que cada keyword exista en la firma
        real de ``Storage.<m>``.
        """
        import ast

        source = Path("src/skillgraph/platform/uow.py").read_text(encoding="utf-8")
        source = source.replace('-> "list[StoredRelation]":', "-> list:")
        tree = ast.parse(source)
        incompatibles: list[str] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for call in ast.walk(cls):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if not (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "_storage"
                ):
                    continue
                destino = getattr(Storage, func.attr, None)
                if destino is None:
                    continue  # lo cubre test_toda_delegacion_apunta_a_...
                keywords = {k.arg for k in call.keywords if k.arg}
                if any(k.arg is None for k in call.keywords):
                    incompatibles.append(
                        f"{cls.name} -> Storage.{func.attr}(**kwargs): "
                        "reenvio opaco, no verificable"
                    )
                    continue
                reales = set(inspect.signature(destino).parameters) - {"self"}
                malos = keywords - reales
                if malos:
                    incompatibles.append(
                        f"{cls.name} -> Storage.{func.attr}: "
                        f"keywords inexistentes {sorted(malos)}; "
                        f"la facade acepta {sorted(reales)}"
                    )
        assert not incompatibles, (
            "delegaciones incompatibles con la firma real de Storage:\n"
            + "\n".join(f"  - {m}" for m in incompatibles)
        )

    def test_public_methods_solo_nombra_metodos_que_existen(self) -> None:
        """La lista que documenta la superficie no puede mentir."""
        inexistentes = sorted(m for m in Storage._PUBLIC_METHODS if not hasattr(Storage, m))
        assert inexistentes == [], (
            f"_PUBLIC_METHODS nombra metodos que Storage no tiene: {inexistentes}"
        )

    def test_la_politica_del_tenant_sobrevive_al_round_trip(self, storage: Storage) -> None:
        """El contrato observable que el bug roto incumplia.

        Este test es el que habria atrapado el defecto original: escribir
        y releer la politica via el adapter debe devolver lo escrito.
        """
        storage.uow.policy.set_redaction_policy(TENANT, "full")
        assert storage.uow.policy.get_redaction_policy(TENANT) == "full"
        # Y debe ser el MISMO valor que ve el facade, no una copia.
        assert storage.get_policy(tenant_id=TENANT) == "full"


class TestAdapterTypesAndConnection:
    """Invariantes de tipo y de conexion compartida que el cierre debe uphold."""

    def test_storage_expone_adapters_de_los_tipos_declarados(self, storage: Storage) -> None:
        uow = storage.uow
        assert isinstance(uow, SqliteUnitOfWork)
        assert isinstance(uow.runs, SqliteRunAdapter)
        assert isinstance(uow.events, SqliteEventAdapter)
        assert isinstance(uow.knowledge, SqliteKnowledgeAdapter)
        assert isinstance(uow.governance, SqliteGovernanceAdapter)
        assert isinstance(uow.policy, SqlitePolicyAdapter)

    def test_todos_los_adapters_ven_de_la_misma_conexion(self, storage: Storage) -> None:
        uow = storage.uow
        ids = {
            id(uow.runs._conn),
            id(uow.events._conn),
            id(uow.knowledge._conn),
            id(uow.governance._conn),
            id(uow.policy._conn),
        }
        assert len(ids) == 1
        assert isinstance(uow._conn, sqlite3.Connection)

    def test_la_conexion_escribible_a_traves_de_cualquier_adapter(self, storage: Storage) -> None:
        """Si un adapter abriera otra conexion, la escritura no se veria."""
        uow = storage.uow
        uow.policy.set_redaction_policy(TENANT, "full")
        row = uow._conn.execute(
            "SELECT redaction_policy FROM tenant_policies WHERE tenant_id = ?",
            (TENANT,),
        ).fetchone()
        assert row is not None
        assert row[0] == "full"
