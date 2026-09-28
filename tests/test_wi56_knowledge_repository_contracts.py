"""Red de contrato WI-56 corte 3: SqliteKnowledgeRepository real.

Fija el contrato del estrangulamiento definido en ADR-0016 para el
cluster knowledge (31 metodos: recursos/relations, sources, entities,
claims, evidences, findings, traces):

1. ``Storage.knowledge_repository()`` devuelve UNA instancia de
   componente real (no ``self``), cacheada.
2. Los 31 metodos producen el mismo efecto observable por camino
   delegado y por componente (dos bases identicas, dump semantico de
   las tablas knowledge sin columnas de reloj).
3. El componente comparte la conexion de Storage y cubre
   estructuralmente la superficie del Protocol
   ``KnowledgeRepository``.
4. El schema no cambia: una nueva instancia de ``Storage`` sobre el
   mismo fichero ve lo escrito por el componente.

Tests contra Storage real (SQLite en tmp_path), sin mocks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)
from skillgraph.platform.ports import KnowledgeRepository
from skillgraph.platform.storage import Storage
from skillgraph.resources.bricks import Brick, ResourceIdentity

TENANT = "t"
PROJECT = "p"


def _brick(name: str, spec: dict[str, Any]) -> Brick:
    return Brick(
        identity=ResourceIdentity(
            tenant_id=TENANT,
            project_id=PROJECT,
            namespace="ns",
            kind="prompts",
            name=name,
        ),
        api_version="v1",
        kind="prompts",
        spec=spec,
    )


def _source(sid: str = "s1") -> Source:
    return Source(
        source_id=sid,
        kind="local_file",
        content_hash="abc",
        locator={"path": "src/foo.py"},
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-01-01T00:00:00Z",
        freshness="fresh",
    )


def _entity(eid: str = "file:src/foo.py", key: str = "src/foo.py") -> Entity:
    return Entity(entity_id=eid, kind="file", stable_key=key)


def _evidence(eid: str = "e1") -> Evidence:
    return Evidence(
        evidence_id=eid,
        kind="quote",
        content="texto",
        source_id="s1",
        observed_at="2026-01-01T00:00:00Z",
    )


def _claim(cid: str = "c1", obj: Any = 42, pred: str = "line_count") -> Claim:
    return Claim(
        claim_id=cid,
        subject_entity_id="file:src/foo.py",
        predicate=pred,
        object_literal=obj,
        source_id="s1",
        evidence_ids=("e1",),
        checked_at_revision="rev1",
    )


def _seed_base(storage: Storage) -> None:
    """Estado inicial identico: 2 resources, relation, source, entity,
    evidence y claim con enlace N:M."""
    storage.upsert_resource(_brick("a", {"x": 1}))
    storage.upsert_resource(_brick("b", {"y": 2}))
    uid_a = storage.upsert_resource(_brick("a", {"x": 1}))  # idempotente
    uid_b = storage.upsert_resource(_brick("b", {"y": 2}))
    storage.add_relation(
        tenant_id=TENANT,
        project_id=PROJECT,
        source_uid=uid_a,
        target_uid=uid_b,
        kind="uses",
        properties={},
    )
    storage.register_source(tenant_id=TENANT, project_id=PROJECT, source=_source())
    storage.upsert_entity(tenant_id=TENANT, project_id=PROJECT, entity=_entity())
    storage.record_evidence(tenant_id=TENANT, project_id=PROJECT, evidence=_evidence())
    storage.record_claim(tenant_id=TENANT, project_id=PROJECT, claim=_claim())


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Storage, Storage]:
    live = Storage(tmp_path / "live.sqlite")
    delegated = Storage(tmp_path / "delegated.sqlite")
    _seed_base(live)
    _seed_base(delegated)
    return live, delegated


def _cases() -> dict[str, dict[str, Any]]:
    return {
        "upsert_resource": {"brick": _brick("c", {"z": 3})},
        "get_resource": {"uid": None},  # resuelto en el test via uid_a
        "list_resources": {"tenant_id": TENANT, "project_id": PROJECT},
        "add_relation": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "source_uid": "RA",
            "target_uid": "RB",
            "kind": "duplicates",
            "properties": {"note": "dup"},
        },
        "dependencies_of": {"uid": "RA"},
        "dependents_of": {"uid": "RB"},
        "register_source": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "source": _source("s2"),
        },
        "get_source": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "source_id": "s1",
        },
        "list_sources": {"tenant_id": TENANT, "project_id": PROJECT},
        "update_source_freshness": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "source_id": "s1",
            "freshness": "stale",
        },
        "source_exists_anywhere": {"source_id": "s1"},
        "upsert_entity": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "entity": _entity("file:src/bar.py", "src/bar.py"),
        },
        "get_entity": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "entity_id": "file:src/foo.py",
        },
        "find_entity": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "kind": "file",
            "stable_key": "src/foo.py",
        },
        "record_evidence": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "evidence": _evidence("e2"),
        },
        "get_evidences_for_claim": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "claim_id": "c1",
        },
        "record_claim": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "claim": _claim("c2", obj=7, pred="function_count"),
        },
        "get_claim": {"tenant_id": TENANT, "project_id": PROJECT, "claim_id": "c1"},
        "list_claims_for_subject": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "subject_entity_id": "file:src/foo.py",
        },
        "list_claims_for_source": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "source_id": "s1",
        },
        "list_claims_using_evidence": {"evidence_id": "e1"},
        "mark_claims_stale": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "claim_ids": ("c1",),
        },
        "reactivate_claims_with_revision": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "source_id": "s1",
            "new_revision": "rev1",
        },
        "list_stale_claims": {"tenant_id": TENANT, "project_id": PROJECT},
        "list_claims_by_predicate": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "predicate": "line_count",
        },
        "list_evidences_for_source": {"source_id": "s1"},
        "list_resource_refs_for_run": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "run_id": "run-x",
            "kind": "claim",
        },
        "attach_evidence_to_claim": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "claim_id": "c1",
            "evidence_id": "e1",
        },
        "record_finding": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "finding": Finding(
                finding_id="f1",
                entity_id="file:src/foo.py",
                observation="observacion",
                rule_ref="max_lines_per_function",
                rule_version="skillgraph-rules/0.1.0",
                evidence_ids=("e1",),
                result="pass",
                valid_until_revision=None,
            ),
        },
        "record_trace": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "trace": OutcomeTrace(
                trace_id="tr1",
                kind="SoftwareExecutionSlice",
                name="my-trace",
                project_id=PROJECT,
                created_at="2026-01-01",
                claim_refs=("c1",),
            ),
        },
        "link_trace": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "trace_id": "tr1",
            "link_kind": "claim",
            "link_id": "c1",
            "position": 5,
        },
    }


_KNOWLEDGE_TABLES = (
    "resources",
    "relations",
    "sources",
    "entities",
    "evidences",
    "claims",
    "claim_evidence",
    "findings",
    "outcome_traces",
    "outcome_trace_links",
)


def _snapshot(storage: Storage) -> list[tuple[str, tuple[Any, ...]]]:
    conn = storage._conn
    out: list[tuple[str, tuple[Any, ...]]] = []
    for table in _KNOWLEDGE_TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        keep = [
            c
            for c in cols
            if not any(
                w in c
                for w in (
                    "created_at",
                    "updated_at",
                    "recorded_at",
                    "observed_at",
                    "checked_at",
                    "valid_until",
                )
            )
        ]
        rows = conn.execute(f"SELECT {', '.join(keep)} FROM {table} ORDER BY 1").fetchall()
        for r in rows:
            # Normalizar UUIDs generados (relation_id) para comparar bases
            # semanticas iguales (mismo patron que el corte 1 con run_id).
            vals = tuple(
                re.sub(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    "UUID",
                    str(v),
                )
                for v in tuple(r)
            )
            out.append((table, vals))
    return sorted(out, key=lambda x: (x[0], x[1]))


class TestFacadeIdentity:
    def test_knowledge_repository_is_cached_component_not_self(self, pair) -> None:
        storage, _other = pair
        repo = storage.knowledge_repository()
        assert repo is not storage
        assert storage.knowledge_repository() is repo

    def test_component_shares_storage_connection(self, pair) -> None:
        storage, _other = pair
        assert storage.knowledge_repository()._conn is storage._conn

    def test_component_covers_protocol_surface(self, pair) -> None:
        storage, _other = pair
        repo = storage.knowledge_repository()
        proto_methods = {
            n for n in dir(KnowledgeRepository) if not n.startswith("_") and n != "record_event"
        }
        missing = [n for n in proto_methods if not callable(getattr(repo, n, None))]
        assert missing == []


class TestClusterEquivalence:
    @pytest.mark.parametrize("method", sorted(_cases().keys()))
    def test_component_path_matches_delegated_path(self, pair, method: str) -> None:
        live, delegated = pair
        # Casos que referencian un trace: sembrar el trace primero en
        # ambas bases (el link exige el trace, FK outcome_trace_links).
        if method == "link_trace":
            from skillgraph.knowledge.graph import OutcomeTrace

            for store in (live, delegated):
                store.knowledge_repository().record_trace(
                    tenant_id=TENANT,
                    project_id=PROJECT,
                    trace=OutcomeTrace(
                        trace_id="tr1",
                        kind="SoftwareExecutionSlice",
                        name="seed-trace",
                        project_id=PROJECT,
                        created_at="2026-01-01",
                        claim_refs=(),
                    ),
                )
        # reactivate opera sobre claims stale con la nueva revision:
        # sembrar c1 stale y luego reactivar con rev2 no toca nada;
        # el semantico correcto es stale(c1) -> reactivate(rev1).
        if method == "reactivate_claims_with_revision":
            for store in (live, delegated):
                store.knowledge_repository().mark_claims_stale(
                    tenant_id=TENANT, project_id=PROJECT, claim_ids=("c1",)
                )
        kwargs = dict(_cases()[method])
        # Resolver uids reales (dependen del formato de uid de Brick).
        conn = live._conn
        uids = [r["uid"] for r in conn.execute("SELECT uid FROM resources ORDER BY uid")]
        ra, rb = uids[0], uids[1]
        for k, v in list(kwargs.items()):
            if v == "RA":
                kwargs[k] = ra
            elif v == "RB":
                kwargs[k] = rb
        if method == "get_resource":
            kwargs["uid"] = ra

        live_ret = getattr(live.knowledge_repository(), method)(**kwargs)
        delegated_ret = getattr(delegated, method)(**kwargs)

        assert _snapshot(live) == _snapshot(delegated)

        def norm(s: str) -> str:
            return re.sub(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                "UUID",
                s,
            )

        assert norm(repr(live_ret)) == norm(repr(delegated_ret))

        if method == "get_resource":
            assert live_ret is not None and live_ret.uid == ra
        if method == "get_claim":
            assert live_ret is not None and live_ret.claim_id == "c1"
        if method == "get_source":
            assert live_ret is not None and live_ret.source_id == "s1"
        if method == "find_entity":
            assert live_ret is not None and live_ret.entity_id == "file:src/foo.py"
        if method == "source_exists_anywhere":
            assert live_ret is True
        if method == "list_claims_using_evidence":
            assert live_ret == ("c1",)
        if method == "reactivate_claims_with_revision":
            assert live_ret == ("c1",)

    def test_upsert_resource_conflict_raises_both_paths(self, pair) -> None:
        """Mismo uid con spec distinto: IdentityConflictError en ambos."""
        from skillgraph.core.errors import IdentityConflictError

        live, delegated = pair
        conn = live._conn
        ra = next(iter([r["uid"] for r in conn.execute("SELECT uid FROM resources ORDER BY uid")]))

        # Reconstruir el brick con el uid existente cambiando solo spec.
        def conflicting(store: Any) -> None:
            b = _brick("a", {"distinto": True})
            conflicting_brick = Brick(
                identity=ResourceIdentity(
                    tenant_id=TENANT,
                    project_id=PROJECT,
                    namespace="ns",
                    kind="prompts",
                    name=b.identity.name,
                ),
                api_version=b.api_version,
                kind=b.kind,
                spec={"distinto": True},
            )
            assert conflicting_brick  # usa el uid real del resource a
            store.upsert_resource(conflicting_brick)

        with pytest.raises(IdentityConflictError):
            conflicting(live.knowledge_repository())
        with pytest.raises(IdentityConflictError):
            conflicting(delegated)
        assert ra  # uid resuelto usado implicitamente arriba


class TestSchemaUntouched:
    def test_new_storage_instance_sees_component_writes(self, tmp_path) -> None:
        storage = Storage(tmp_path / "single.sqlite")
        _seed_base(storage)
        storage.knowledge_repository().register_source(
            tenant_id=TENANT, project_id=PROJECT, source=_source("s2")
        )
        reopened = Storage(tmp_path / "single.sqlite")
        src = reopened.get_source(tenant_id=TENANT, project_id=PROJECT, source_id="s2")
        assert src is not None and src.source_id == "s2"
        reopened.close()
