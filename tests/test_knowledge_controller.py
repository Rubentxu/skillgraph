"""Tests H3 Slice 2: KnowledgeController (sin invalidacion transitiva).

Doc de cobertura:
  specs/h3-slice-2.md (14 tests propuestos).

Reglas:
- Storage real con tmp_path (no se mockea SQLite para evitar tests
  ceremoniales; la fidelidad del modelo gana).
- Para tests de inyeccion se usa una FakeStorage (un Storage envuelto
  que captura llamadas) sin tocar SQLite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.errors import (
    InvalidSourceError,
    StaleKnowledgeWarning,
    UnknownClaimError,
    UnknownEntityError,
    UnknownSourceError,
)
from skillgraph.knowledge import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)
from skillgraph.knowledge_controller import (
    KnowledgeController,
    make_claim_id,
)
from skillgraph.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "k.sqlite")


def _src(
    sid: str = "local:src/foo.py",
    *,
    freshness: str = "fresh",
    kind: str = "local_file",
    git_sha: str | None = None,
) -> Source:
    return Source(
        source_id=sid,
        kind=kind,  # type: ignore[arg-type]
        content_hash="abc",
        locator={"path": "src/foo.py"},
        git_commit_sha=git_sha,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-01-01T00:00:00Z",
        freshness=freshness,  # type: ignore[arg-type]
    )


def _ent(eid: str = "file:src/foo.py") -> Entity:
    return Entity(entity_id=eid, kind="file", stable_key="src/foo.py")


# ---------------------------------------------------------------------------
# Happy path (5 tests)
# ---------------------------------------------------------------------------


def test_register_and_get_source_roundtrip(tmp_path: Path) -> None:
    """Source->register->get OK."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src())
    got = ctl.get_source(source_id="local:src/foo.py")
    assert got.source_id == "local:src/foo.py"
    assert got.freshness == "fresh"


def test_upsert_entity_returns_existing_id(tmp_path: Path) -> None:
    """upsert_entity idempotente: devuelve el mismo entity_id."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    e = _ent()
    id1 = ctl.upsert_entity(entity=e)
    id2 = ctl.upsert_entity(entity=e)
    assert id1 == id2 == "file:src/foo.py"
    got = ctl.get_entity(entity_id=id1)
    assert got.entity_id == "file:src/foo.py"


def test_record_claim_returns_generated_id(tmp_path: Path) -> None:
    """Claim con claim_id='' genera un ClaimID formato `claim-{uuid5}`."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src())
    ctl.upsert_entity(entity=_ent())
    cid = ctl.record_claim(
        claim=Claim(
            claim_id="",  # forzar generacion
            subject_entity_id="file:src/foo.py",
            predicate="line_count",
            object_literal=42,
            source_id="local:src/foo.py",
            checked_at_revision="rev1",
        ),
    )
    assert cid.startswith("claim-")
    # El id generado debe ser determinista.
    expected = make_claim_id(
        subject_entity_id="file:src/foo.py",
        predicate="line_count",
        source_id="local:src/foo.py",
        checked_at_revision="rev1",
    )
    assert cid == expected


def test_find_entity_by_kind_and_key(tmp_path: Path) -> None:
    """find_entity busca sin saber el entity_id."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.upsert_entity(entity=_ent("file:src/foo.py"))
    got = ctl.find_entity(kind="file", stable_key="src/foo.py")
    assert got is not None
    assert got.entity_id == "file:src/foo.py"
    assert ctl.find_entity(kind="file", stable_key="nonexistent") is None


def test_record_trace_with_links_preserves_order(tmp_path: Path) -> None:
    """record_trace y link_trace preservan orden via position."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src())
    tid = ctl.record_trace(
        trace=OutcomeTrace(
            trace_id="tr1",
            kind="SoftwareExecutionSlice",
            name="my-trace",
            project_id="p",
            created_at="2026-01-01",
            claim_refs=("c1", "c2"),
        ),
    )
    assert tid == "tr1"
    # Aniadir enlaces preservando orden.
    ctl.link_trace(trace_id="tr1", link_kind="claim", link_id="c3", position=2)
    rows = ctl.storage._conn.execute(
        "SELECT link_id, position FROM outcome_trace_links "
        "WHERE trace_id = ? AND link_kind = 'claim' ORDER BY position",
        ("tr1",),
    ).fetchall()
    assert [r["link_id"] for r in rows] == ["c1", "c2", "c3"]


# ---------------------------------------------------------------------------
# Errores tipados (5 tests)
# ---------------------------------------------------------------------------


def test_register_invalid_source_raises_invalid_source_error() -> None:
    """Source con content_hash='' falla en __post_init__ del ADT."""
    with pytest.raises(InvalidSourceError):
        Source(
            source_id="x",
            kind="local_file",
            content_hash="",
            locator={},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01",
            freshness="fresh",
        )


def test_get_unknown_source_raises(tmp_path: Path) -> None:
    """get_source lanza UnknownSourceError si no existe."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    with pytest.raises(UnknownSourceError):
        ctl.get_source(source_id="missing")


def test_record_claim_for_unknown_entity_raises(tmp_path: Path) -> None:
    """FK violation subject_entity_id -> UnknownEntityError."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src())
    # NO creamos entity.
    with pytest.raises(UnknownEntityError):
        ctl.record_claim(
            claim=Claim(
                claim_id="c1",
                subject_entity_id="file:nope",
                predicate="line_count",
                object_literal=1,
                source_id="local:src/foo.py",
                checked_at_revision="r1",
            ),
        )


def test_record_evidence_for_unknown_source_raises(tmp_path: Path) -> None:
    """FK violation source_id -> UnknownSourceError."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    with pytest.raises(UnknownSourceError):
        ctl.record_evidence(
            evidence=Evidence(
                evidence_id="ev1",
                kind="metric",
                content={"x": 1},
                source_id="missing",
                observed_at="2026-01-01",
            ),
        )


def test_get_unknown_claim_raises(tmp_path: Path) -> None:
    """get_claim lanza UnknownClaimError si no existe."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    with pytest.raises(UnknownClaimError):
        ctl.get_claim(claim_id="missing")


# ---------------------------------------------------------------------------
# Idempotencia (2 tests)
# ---------------------------------------------------------------------------


def test_register_source_idempotent(tmp_path: Path) -> None:
    """Registrar misma source dos veces no duplica."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src())
    ctl.register_source(source=_src())
    n = ctl.storage._conn.execute(
        "SELECT COUNT(*) FROM sources"
    ).fetchone()[0]
    assert n == 1


def test_record_claim_idempotent_on_full_tuple(tmp_path: Path) -> None:
    """Mismo (subject, predicate, source, revision) -> mismo ClaimID."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src())
    ctl.upsert_entity(entity=_ent())
    base = dict(
        subject_entity_id="file:src/foo.py",
        predicate="line_count",
        source_id="local:src/foo.py",
        checked_at_revision="rev1",
    )
    id1 = ctl.record_claim(
        claim=Claim(claim_id="", object_literal=42, **base),  # type: ignore[arg-type]
    )
    id2 = ctl.record_claim(
        claim=Claim(claim_id="", object_literal=99, **base),  # type: ignore[arg-type]
    )
    # Misma tupla natural -> mismo ClaimID determinista.
    assert id1 == id2
    n = ctl.storage._conn.execute(
        "SELECT COUNT(*) FROM claims"
    ).fetchone()[0]
    assert n == 1  # solo 1 row (INSERT OR IGNORE)


# ---------------------------------------------------------------------------
# Inyeccion (2 tests)
# ---------------------------------------------------------------------------


def test_controller_uses_injected_storage(tmp_path: Path) -> None:
    """Storage real inyectado: el controller lo usa via interfaz."""
    storage = _storage(tmp_path)
    ctl = KnowledgeController(storage=storage, tenant_id="t1", project_id="p1")
    # Cambiar el storage en runtime NO es posible (frozen dataclass).
    # Pero verificamos que el controller escribe en el storage dado.
    ctl.register_source(source=_src(sid="git:abc:src/x.py"))
    # Verificar que la fila existe en el storage original.
    row = storage._conn.execute(
        "SELECT source_id FROM sources WHERE source_id = ?",
        ("git:abc:src/x.py",),
    ).fetchone()
    assert row is not None
    assert row["source_id"] == "git:abc:src/x.py"


def test_controller_isolates_tenants(tmp_path: Path) -> None:
    """Dos KnowledgeController con distinto tenant_id no se ven entre si."""
    storage = _storage(tmp_path)
    ctl_a = KnowledgeController(storage=storage, tenant_id="tenant_a", project_id="p")
    ctl_b = KnowledgeController(storage=storage, tenant_id="tenant_b", project_id="p")
    ctl_a.register_source(source=_src(sid="local:a.py"))
    # tenant_b NO ve la source de tenant_a.
    with pytest.raises(UnknownSourceError):
        ctl_b.get_source(source_id="local:a.py")
    # tenant_a si la ve.
    assert ctl_a.get_source(source_id="local:a.py").source_id == "local:a.py"


# ---------------------------------------------------------------------------
# Tests extra del slice 2
# ---------------------------------------------------------------------------


def test_register_stale_source_emits_warning(tmp_path: Path) -> None:
    """Re-registrar source con freshness != 'fresh' emite StaleKnowledgeWarning."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src(freshness="stale"))
    with pytest.warns(StaleKnowledgeWarning):
        ctl.register_source(source=_src(freshness="stale"))


def test_mark_source_stale_then_fresh(tmp_path: Path) -> None:
    """mark_source_stale + mark_source_fresh funcionan."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.register_source(source=_src(freshness="fresh"))
    ctl.mark_source_stale(source_id="local:src/foo.py")
    assert ctl.get_source(source_id="local:src/foo.py").freshness == "stale"
    ctl.mark_source_fresh(source_id="local:src/foo.py")
    assert ctl.get_source(source_id="local:src/foo.py").freshness == "fresh"


def test_record_finding_generates_id_when_empty(tmp_path: Path) -> None:
    """record_finding genera ID via UUIDv5 si finding_id=''."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="t", project_id="p")
    ctl.upsert_entity(entity=_ent())
    fid = ctl.record_finding(
        finding=Finding(
            finding_id="",
            entity_id="file:src/foo.py",
            observation="too long",
            rule_ref="max_lines_per_function",
            rule_version="skillgraph-rules/0.1.0",
            evidence_ids=(),
            result="fail",
            valid_until_revision=None,
        ),
    )
    assert fid.startswith("fnd-")
