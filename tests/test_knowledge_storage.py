"""Tests H3 Slice 1: Knowledge ADT + Storage delta.

Doc de cobertura:
  specs/h3-slice-1.md (17 tests propuestos).

Reglas (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Fixtures sin red ni proveedor externo.
- Aislamiento: cada test abre su propio Storage en tmp_path.
- Tests focalizados en la responsabilidad del slice (no duplica cobertura
  de tests/test_s1_sqlite.py).
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from skillgraph.errors import (
    InvalidEntityIDError,
    InvalidSourceError,
    InvalidSourceIDError,
    UnknownClaimPredicateError,
)
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
    entity_id,
    source_id,
)
from skillgraph.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage(tmp_path: Path) -> Storage:
    """Crea un Storage fresco en `tmp_path`."""
    return Storage(tmp_path / "knowledge.sqlite")


def _src(
    source_id_str: str = "local:src/foo.py",
    *,
    kind: str = "local_file",
    git_sha: str | None = None,
) -> Source:
    """Helper: crea un Source valido. git_sha solo obligatorio si kind empieza por 'git_'."""
    return Source(
        source_id=source_id_str,
        kind=kind,  # type: ignore[arg-type]
        content_hash="abc123",
        locator={"path": "src/foo.py"},
        git_commit_sha=git_sha,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-01-01T00:00:00Z",
        freshness="fresh",
    )


def _ent(entity_id_str: str = "file:src/foo.py") -> Entity:
    return Entity(entity_id=entity_id_str, kind="file", stable_key="src/foo.py")


# ---------------------------------------------------------------------------
# Schema (4 tests)
# ---------------------------------------------------------------------------


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    """Llamar `_migrate()` 5 veces seguidas no rompe nada, no duplica indices."""
    s = _make_storage(tmp_path)
    for _ in range(5):
        s._migrate()
    # Las 7 tablas existen.
    tables = {
        row[0] for row in s._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "sources",
        "entities",
        "evidences",
        "claims",
        "claim_evidence",
        "findings",
        "outcome_traces",
        "outcome_trace_links",
    }.issubset(tables)


def test_migrate_creates_all_seven_tables(tmp_path: Path) -> None:
    """Las 7 (en realidad 8 con claim_evidence) tablas del subsistema existen."""
    s = _make_storage(tmp_path)
    tables = {
        row[0] for row in s._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    expected = {
        "sources",
        "entities",
        "evidences",
        "claims",
        "claim_evidence",
        "findings",
        "outcome_traces",
        "outcome_trace_links",
    }
    assert expected.issubset(tables), f"Faltan tablas: {expected - tables}"


def test_migrate_does_not_touch_existing_tables(tmp_path: Path) -> None:
    """Las tablas existentes (resources, relations, workflow_runs, etc.)
    siguen con su schema original despues de la migration."""
    s = _make_storage(tmp_path)
    cols = {row[1] for row in s._conn.execute("PRAGMA table_info(resources)")}
    assert "uid" in cols
    assert "spec_json" in cols
    cols = {row[1] for row in s._conn.execute("PRAGMA table_info(workflow_runs)")}
    assert "run_id" in cols
    assert "plan_json" in cols


def test_indexes_exist_for_stale_and_subject(tmp_path: Path) -> None:
    """Los indices idx_claims_subject y idx_claims_stale existen."""
    s = _make_storage(tmp_path)
    indexes = {
        row[0] for row in s._conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert "idx_claims_subject" in indexes
    assert "idx_claims_stale" in indexes


# ---------------------------------------------------------------------------
# Sources (3 tests)
# ---------------------------------------------------------------------------


def test_register_and_get_source_roundtrip(tmp_path: Path) -> None:
    """Roundtrip Source -> row -> Source preserva todos los campos."""
    s = _make_storage(tmp_path)
    src = _src()
    s.register_source(tenant_id="t", project_id="p", source=src)
    got = s.get_source(tenant_id="t", project_id="p", source_id="local:src/foo.py")
    assert got is not None
    assert got.source_id == "local:src/foo.py"
    assert got.kind == "local_file"
    assert got.content_hash == "abc123"
    assert got.locator == {"path": "src/foo.py"}
    assert got.checked_at == "2026-01-01T00:00:00Z"
    assert got.freshness == "fresh"


def test_register_source_rejects_empty_content_hash() -> None:
    """Source con content_hash vacio lanza InvalidSourceError (regla del ADT)."""
    with pytest.raises(InvalidSourceError):
        Source(
            source_id="local:src/foo.py",
            kind="local_file",
            content_hash="",
            locator={"path": "src/foo.py"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )


def test_register_git_source_requires_commit_sha() -> None:
    """Source(kind='git_commit') sin git_commit_sha lanza InvalidSourceError."""
    with pytest.raises(InvalidSourceError) as exc_info:
        Source(
            source_id="git:abc:src/foo.py",
            kind="git_commit",
            content_hash="deadbeef",
            locator={"commit": "abc"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    assert "git_commit_sha" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Entities (2 tests)
# ---------------------------------------------------------------------------


def test_upsert_entity_is_idempotent(tmp_path: Path) -> None:
    """Misma clave (kind, stable_key) -> upsert idempotente (mismo entity_id)."""
    s = _make_storage(tmp_path)
    e1 = Entity(entity_id="file:src/foo.py", kind="file", stable_key="src/foo.py")
    e2 = Entity(entity_id="file:src/foo.py", kind="file", stable_key="src/foo.py")
    s.upsert_entity(tenant_id="t", project_id="p", entity=e1)
    s.upsert_entity(tenant_id="t", project_id="p", entity=e2)
    got = s.get_entity(tenant_id="t", project_id="p", entity_id="file:src/foo.py")
    assert got is not None
    assert got.entity_id == "file:src/foo.py"


def test_upsert_entity_different_kind_same_key(tmp_path: Path) -> None:
    """`file:foo.py` y `module:foo.py` son entities distintas."""
    s = _make_storage(tmp_path)
    s.upsert_entity(
        tenant_id="t",
        project_id="p",
        entity=Entity(entity_id="file:foo.py", kind="file", stable_key="foo.py"),
    )
    s.upsert_entity(
        tenant_id="t",
        project_id="p",
        entity=Entity(entity_id="module:foo.py", kind="module", stable_key="foo.py"),
    )
    assert s.get_entity(tenant_id="t", project_id="p", entity_id="file:foo.py") is not None
    assert s.get_entity(tenant_id="t", project_id="p", entity_id="module:foo.py") is not None


# ---------------------------------------------------------------------------
# Claims (4 tests)
# ---------------------------------------------------------------------------


def test_record_claim_returns_claim_id(tmp_path: Path) -> None:
    """record_claim devuelve el claim_id del ADT."""
    s = _make_storage(tmp_path)
    s.register_source(tenant_id="t", project_id="p", source=_src())
    s.upsert_entity(tenant_id="t", project_id="p", entity=_ent())
    claim = Claim(
        claim_id="clm-1",
        subject_entity_id="file:src/foo.py",
        predicate="line_count",
        object_literal=42,
        source_id="local:src/foo.py",
        checked_at_revision="rev1",
    )
    out = s.record_claim(tenant_id="t", project_id="p", claim=claim)
    assert out == "clm-1"


def test_record_claim_idempotent_on_revision(tmp_path: Path) -> None:
    """Misma (subject, predicate, source, checked_at_revision) -> UNIQUE OK."""
    s = _make_storage(tmp_path)
    s.register_source(tenant_id="t", project_id="p", source=_src())
    s.upsert_entity(tenant_id="t", project_id="p", entity=_ent())
    base = dict(
        subject_entity_id="file:src/foo.py",
        predicate="line_count",
        source_id="local:src/foo.py",
        checked_at_revision="rev1",
    )
    s.record_claim(
        tenant_id="t",
        project_id="p",
        claim=Claim(claim_id="c1", object_literal=42, **base),  # type: ignore[arg-type]
    )
    # Re-registrar con mismo claim_id -> no-op, no incrementa contador.
    s.record_claim(
        tenant_id="t",
        project_id="p",
        claim=Claim(claim_id="c1", object_literal=42, **base),  # type: ignore[arg-type]
    )
    n = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert n == 1


def test_record_claim_with_different_revision_creates_new(tmp_path: Path) -> None:
    """Nueva revision -> nueva Claim; la vieja queda como historico."""
    s = _make_storage(tmp_path)
    s.register_source(tenant_id="t", project_id="p", source=_src())
    s.upsert_entity(tenant_id="t", project_id="p", entity=_ent())
    s.record_claim(
        tenant_id="t",
        project_id="p",
        claim=Claim(
            claim_id="c1",
            subject_entity_id="file:src/foo.py",
            predicate="line_count",
            object_literal=42,
            source_id="local:src/foo.py",
            checked_at_revision="rev1",
        ),
    )
    s.record_claim(
        tenant_id="t",
        project_id="p",
        claim=Claim(
            claim_id="c2",
            subject_entity_id="file:src/foo.py",
            predicate="line_count",
            object_literal=100,
            source_id="local:src/foo.py",
            checked_at_revision="rev2",
        ),
    )
    n = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert n == 2
    # Y se pueden listar ambas.
    rows = s._conn.execute(
        "SELECT claim_id, checked_at_revision FROM claims ORDER BY checked_at_revision"
    ).fetchall()
    assert [r["claim_id"] for r in rows] == ["c1", "c2"]


def test_attach_evidence_to_claim_roundtrip(tmp_path: Path) -> None:
    """N:M Claim <-> Evidence funciona via claim_evidence."""
    s = _make_storage(tmp_path)
    s.register_source(tenant_id="t", project_id="p", source=_src())
    s.upsert_entity(tenant_id="t", project_id="p", entity=_ent())
    s.record_evidence(
        tenant_id="t",
        project_id="p",
        evidence=Evidence(
            evidence_id="ev1",
            kind="metric",
            content={"loc": 42},
            source_id="local:src/foo.py",
            observed_at="2026-01-01",
        ),
    )
    s.record_claim(
        tenant_id="t",
        project_id="p",
        claim=Claim(
            claim_id="c1",
            subject_entity_id="file:src/foo.py",
            predicate="line_count",
            object_literal=42,
            source_id="local:src/foo.py",
            checked_at_revision="rev1",
        ),
    )
    s.attach_evidence_to_claim(
        tenant_id="t",
        project_id="p",
        claim_id="c1",
        evidence_id="ev1",
    )
    evs = s.get_evidences_for_claim(
        tenant_id="t",
        project_id="p",
        claim_id="c1",
    )
    assert len(evs) == 1
    assert evs[0].evidence_id == "ev1"


# ---------------------------------------------------------------------------
# Evidence + Finding (2 tests)
# ---------------------------------------------------------------------------


def test_record_evidence_with_invalid_source_raises(tmp_path: Path) -> None:
    """FK falla: Evidence sin Source registrada -> IntegrityError."""
    s = _make_storage(tmp_path)
    # NO registramos source.
    with pytest.raises(sqlite3.IntegrityError):
        s.record_evidence(
            tenant_id="t",
            project_id="p",
            evidence=Evidence(
                evidence_id="ev1",
                kind="metric",
                content={"x": 1},
                source_id="missing:source",
                observed_at="2026-01-01",
            ),
        )


def test_record_finding_stores_evidence_ids_as_json(tmp_path: Path) -> None:
    """La lista de evidence_ids serializada se recupera igual."""
    s = _make_storage(tmp_path)
    s.register_source(tenant_id="t", project_id="p", source=_src())
    s.upsert_entity(tenant_id="t", project_id="p", entity=_ent())
    s.record_finding(
        tenant_id="t",
        project_id="p",
        finding=Finding(
            finding_id="f1",
            entity_id="file:src/foo.py",
            observation="function too long",
            rule_ref="max_lines_per_function",
            rule_version="skillgraph-rules/0.1.0",
            evidence_ids=("ev1", "ev2"),
            result="fail",
            valid_until_revision=None,
        ),
    )
    row = s._conn.execute(
        "SELECT evidence_ids_json FROM findings WHERE finding_id = ?", ("f1",)
    ).fetchone()
    assert row is not None
    import json

    assert json.loads(row["evidence_ids_json"]) == ["ev1", "ev2"]


# ---------------------------------------------------------------------------
# Trace (1 test)
# ---------------------------------------------------------------------------


def test_record_trace_with_links_preserves_order(tmp_path: Path) -> None:
    """`position` mantiene el orden del OutcomeTrace."""
    s = _make_storage(tmp_path)
    s.register_source(tenant_id="t", project_id="p", source=_src())
    s.record_trace(
        tenant_id="t",
        project_id="p",
        trace=OutcomeTrace(
            trace_id="tr1",
            kind="SoftwareExecutionSlice",
            name="my-trace",
            project_id="p",
            created_at="2026-01-01",
            claim_refs=("c3", "c1", "c2"),
            evidence_refs=("ev2", "ev1"),
        ),
    )
    rows = s._conn.execute(
        "SELECT link_kind, link_id, position FROM outcome_trace_links "
        "WHERE trace_id = ? ORDER BY link_kind, position",
        ("tr1",),
    ).fetchall()
    claim_order = [r["link_id"] for r in rows if r["link_kind"] == "claim"]
    evidence_order = [r["link_id"] for r in rows if r["link_kind"] == "evidence"]
    assert claim_order == ["c3", "c1", "c2"]
    assert evidence_order == ["ev2", "ev1"]


# ---------------------------------------------------------------------------
# Inmutabilidad ADT (1 test)
# ---------------------------------------------------------------------------


def test_dataclass_frozen_slots_raises_on_mutation() -> None:
    """Claim.foo = 1 lanza FrozenInstanceError. __slots__ rechaza atributos nuevos."""
    c = Claim(
        claim_id="c1",
        subject_entity_id="file:x",
        predicate="line_count",
        object_literal=10,
        source_id="local:x",
        checked_at_revision="r1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.claim_id = "otro"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.foo = 1  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests extra (no estaban en el spec pero verifican invariantes del spec)
# ---------------------------------------------------------------------------


def test_smart_constructor_source_id_rejects_empty() -> None:
    """source_id('') lanza InvalidSourceIDError."""
    with pytest.raises(InvalidSourceIDError):
        source_id("")


def test_smart_constructor_entity_id_requires_colon() -> None:
    """entity_id('foo.py') lanza InvalidEntityIDError (sin ':')."""
    with pytest.raises(InvalidEntityIDError):
        entity_id("foo.py")


def test_claim_unknown_predicate_raises() -> None:
    """Claim con predicate no registrado lanza UnknownClaimPredicateError."""
    with pytest.raises(UnknownClaimPredicateError):
        Claim(
            claim_id="c1",
            subject_entity_id="file:x",
            predicate="not_a_real_predicate",  # type: ignore[arg-type]
            object_literal=1,
            source_id="local:x",
            checked_at_revision="r1",
        )
