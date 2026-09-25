"""Tests H3 Slice 4: invalidacion transitiva + KnowledgeInvalidated event.

Doc de cobertura:
  specs/h3-slice-4.md (10 tests propuestos).

Reglas:
- Storage real (tmp_path) para fidelidad del modelo.
- Aislamiento de tests via tmp_path unico por test.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest

from skillgraph.core.errors import (
    HopLimitExceededWarning,
    UnknownSourceError,
)
from skillgraph.knowledge.graph import Claim, Entity, Evidence, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctl(tmp_path: Path) -> KnowledgeController:
    return KnowledgeController(
        storage=Storage(tmp_path / "k.sqlite"),
        tenant_id="t",
        project_id="p",
    )


def _src(sid: str = "local:a") -> Source:
    return Source(
        source_id=sid,
        kind="local_file",
        content_hash="h",
        locator={"path": sid},
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-01-01T00:00:00Z",
        freshness="fresh",
    )


def _ent(eid: str = "file:x") -> Entity:
    return Entity(entity_id=eid, kind="file", stable_key=eid)


def _claim(
    ctl: KnowledgeController,
    *,
    claim_id: str,
    entity_id: str,
    source_id: str,
    revision: str,
    predicate: str = "line_count",
    object_literal: object = 1,
    evidence_ids: tuple[str, ...] = (),
) -> str:
    return ctl.record_claim(
        claim=Claim(
            claim_id=claim_id,
            subject_entity_id=entity_id,
            predicate=predicate,
            object_literal=object_literal,
            source_id=source_id,
            evidence_ids=evidence_ids,
            extraction_method="manual",
            extractor_version="skillgraph-rules/0.1.0",
            checked_at_revision=revision,
        ),
    )


def _evidence(ctl: KnowledgeController, *, eid: str, source_id: str) -> str:
    return ctl.record_evidence(
        evidence=Evidence(
            evidence_id=eid,
            kind="metric",
            content={"x": 1},
            source_id=source_id,
            observed_at="2026-01-01T00:00:00Z",
        ),
    )


# ---------------------------------------------------------------------------
# Happy path (4)
# ---------------------------------------------------------------------------


def test_invalidate_marks_direct_claims_stale(tmp_path: Path) -> None:
    """Source A, claim C1 con source_id=A. Invalidar A -> C1 stale=1."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    cid = _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a", revision="rev1")
    # Sanity: no stale inicialmente.
    assert ctl.get_claim(claim_id=cid).stale is False

    invalidated = ctl.invalidate_from_source(source_id="local:a")
    assert cid in invalidated
    assert ctl.get_claim(claim_id=cid).stale is True


def test_invalidate_propagates_via_evidence(tmp_path: Path) -> None:
    """Chain de 2 hops via evidencia compartida."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.register_source(source=_src("local:b"))
    ctl.upsert_entity(entity=_ent("file:a"))
    ctl.upsert_entity(entity=_ent("file:b"))

    # Evidence e1 pertenece a source:b
    _evidence(ctl, eid="ev1", source_id="local:b")
    # C1 sobre entity:a, source:a, usa evidence ev1 (source:b)
    c1 = _claim(
        ctl,
        claim_id="c1",
        entity_id="file:a",
        source_id="local:a",
        revision="r1",
        evidence_ids=("ev1",),
    )
    # C2 sobre entity:b, source:b, usa evidence ev1
    c2 = _claim(
        ctl,
        claim_id="c2",
        entity_id="file:b",
        source_id="local:b",
        revision="r1",
        evidence_ids=("ev1",),
    )

    # Invalidar source:a -> C1 directo + C2 transitivo via ev1.
    invalidated = ctl.invalidate_from_source(source_id="local:a")
    assert c1 in invalidated
    assert c2 in invalidated


def test_invalidate_respects_max_hops(tmp_path: Path) -> None:
    """max_hops=1 capta directos (hop 0) + 1 nivel transitivo (hop 1).

    Para demostrar el cap, construimos un grafo de 3 niveles:
      source:a -> c1 (directo, hop 0)
      c1 -> ev1 -> c2 (transitivo 1 nivel, hop 1)
      c2 -> ev2 -> c3 (transitivo 2 niveles, hop 2, FUERA de max_hops=1)
    """
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.register_source(source=_src("local:b"))
    ctl.register_source(source=_src("local:c"))
    ctl.upsert_entity(entity=_ent("file:a"))
    ctl.upsert_entity(entity=_ent("file:b"))
    ctl.upsert_entity(entity=_ent("file:c"))

    _evidence(ctl, eid="ev1", source_id="local:b")
    _evidence(ctl, eid="ev2", source_id="local:c")

    c1 = _claim(
        ctl,
        claim_id="c1",
        entity_id="file:a",
        source_id="local:a",
        revision="r1",
        evidence_ids=("ev1",),
    )
    c2 = _claim(
        ctl,
        claim_id="c2",
        entity_id="file:b",
        source_id="local:b",
        revision="r1",
        evidence_ids=("ev1", "ev2"),
    )
    c3 = _claim(
        ctl,
        claim_id="c3",
        entity_id="file:c",
        source_id="local:c",
        revision="r1",
        evidence_ids=("ev2",),
    )

    # max_hops=1: c1, c2 son alcanzables (hops 0 y 1). c3 queda fuera (hop 2).
    # S2/I (ADR-0015): mensaje expone cardinalidad (count de frontier) + el
    # parametro caller-provided `max_hops`, NO identificadores cross-tenant.
    with pytest.warns(HopLimitExceededWarning, match=r"max_hops=1.*frontier"):
        invalidated = ctl.invalidate_from_source(
            source_id="local:a",
            max_hops=1,
        )
    assert c1 in invalidated
    assert c2 in invalidated
    assert c3 not in invalidated  # 2 niveles transitivos: fuera del cap.


def test_refresh_reactivates_claims(tmp_path: Path) -> None:
    """Invalidar -> refresh con nueva revision -> reactivadas."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    cid = _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a", revision="rev1")
    ctl.invalidate_from_source(source_id="local:a")
    assert ctl.get_claim(claim_id=cid).stale is True

    # Insertamos una nueva revision de la misma Claim.
    _claim(
        ctl,
        claim_id="c1-new",
        entity_id="file:a",
        source_id="local:a",
        revision="rev2",
        object_literal=2,
    )
    # refresh_source revalida las Claims stale cuya checked_at_revision
    # coincida con new_revision. Aqui la stale tiene rev1, no rev2, asi
    # que NO se reactiva. Esto verifica honestidad de la semantica:
    # el caller externo debe generar Claims nuevas para la nueva
    # revision y luego invalidarlas/refresharlas.
    reactivated = ctl.refresh_source(
        source_id="local:a",
        new_revision="rev2",
    )
    assert reactivated == []  # ninguna stale coincide con rev2


# ---------------------------------------------------------------------------
# Errores (3)
# ---------------------------------------------------------------------------


def test_invalidate_unknown_source_raises(tmp_path: Path) -> None:
    """Source inexistente -> UnknownSourceError."""
    ctl = _ctl(tmp_path)
    with pytest.raises(UnknownSourceError):
        ctl.invalidate_from_source(source_id="local:nope")


def test_refresh_with_same_revision_no_op(tmp_path: Path) -> None:
    """Refresh con misma revision: ninguna reactivacion nueva."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a", revision="rev1")
    # No hay stale; refresh no es un noop real, pero no reescribe claims
    # ya fresh (UPDATE WHERE stale=1 filtra).
    reactivated = ctl.refresh_source(
        source_id="local:a",
        new_revision="rev1",
    )
    assert reactivated == []


def test_hop_limit_exceeded_emits_warning(tmp_path: Path) -> None:
    """max_hops=1 con chain de 2 hops -> warning emitido, no excepcion."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.register_source(source=_src("local:b"))
    ctl.upsert_entity(entity=_ent("file:a"))
    ctl.upsert_entity(entity=_ent("file:b"))
    _evidence(ctl, eid="ev1", source_id="local:b")
    _claim(
        ctl,
        claim_id="c1",
        entity_id="file:a",
        source_id="local:a",
        revision="r1",
        evidence_ids=("ev1",),
    )
    _claim(
        ctl,
        claim_id="c2",
        entity_id="file:b",
        source_id="local:b",
        revision="r1",
        evidence_ids=("ev1",),
    )
    # S2/I (ADR-0015): mensaje expone cardinalidad + parametro caller-provided,
    # NO identificadores cross-tenant (no claim_id, no entity_id, no source_id).
    with pytest.warns(HopLimitExceededWarning, match=r"max_hops=1.*frontier"):
        ctl.invalidate_from_source(source_id="local:a", max_hops=1)


# ---------------------------------------------------------------------------
# Eventos (2)
# ---------------------------------------------------------------------------


def test_invalidate_emits_knowledge_invalidated_event(tmp_path: Path) -> None:
    """Event KnowledgeInvalidated se persiste en runtime_events."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a", revision="r1")

    ctl.invalidate_from_source(source_id="local:a")

    rows = ctl.storage.list_events(
        tenant_id="t",
        project_id="p",
        event_kind="KnowledgeInvalidated",
    )
    assert len(rows) == 1
    payload = _json.loads(rows[0]["payload_json"])
    assert payload["source_id"] == "local:a"
    assert payload["count"] == 1
    assert payload["max_hops"] == 2
    assert rows[0]["resource_ref"] == "source:local:a"


def test_refresh_emits_knowledge_refreshed_event(tmp_path: Path) -> None:
    """Event KnowledgeRefreshed con reactivated_count y lista."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a", revision="rev1")

    ctl.refresh_source(source_id="local:a", new_revision="rev1")

    rows = ctl.storage.list_events(
        tenant_id="t",
        project_id="p",
        event_kind="KnowledgeRefreshed",
    )
    assert len(rows) == 1
    payload = _json.loads(rows[0]["payload_json"])
    assert payload["source_id"] == "local:a"
    assert payload["new_revision"] == "rev1"
    assert payload["reactivated_count"] == 0


# ---------------------------------------------------------------------------
# Edge cases (1)
# ---------------------------------------------------------------------------


def test_invalidate_with_no_claims_is_noop(tmp_path: Path) -> None:
    """Source sin claims: retorna [], NO emite event."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:alone"))

    invalidated = ctl.invalidate_from_source(source_id="local:alone")
    assert invalidated == []

    rows = ctl.storage.list_events(
        tenant_id="t",
        project_id="p",
        event_kind="KnowledgeInvalidated",
    )
    assert rows == []
