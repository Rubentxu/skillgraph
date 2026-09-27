"""Regression tests for the StoredClaim/StoredEvidence boundary."""

from __future__ import annotations

from pathlib import Path

from skillgraph.knowledge.graph import Claim, Entity, Evidence, Source
from skillgraph.platform.ports import StoredClaim, StoredEvidence
from skillgraph.platform.storage import Storage


def _source(source_id: str) -> Source:
    return Source(
        source_id=source_id,
        kind="local_file",  # type: ignore[arg-type]
        content_hash=f"hash-{source_id}",
        locator={"path": source_id},
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-01-01T00:00:00Z",
        freshness="fresh",  # type: ignore[arg-type]
    )


def test_list_claims_by_predicate_returns_stored_claim_dto(tmp_path: Path) -> None:
    with Storage(tmp_path / "claims.sqlite") as storage:
        storage.register_source(tenant_id="t1", project_id="p1", source=_source("src-1"))
        storage.upsert_entity(
            tenant_id="t1",
            project_id="p1",
            entity=Entity(entity_id="ent-1", kind="function", stable_key="ent-1"),
        )
        storage.record_claim(
            tenant_id="t1",
            project_id="p1",
            claim=Claim(
                claim_id="claim-1",
                subject_entity_id="ent-1",
                predicate="line_count",  # type: ignore[arg-type]
                object_literal={"value": 3},
                source_id="src-1",
                evidence_ids=(),
                extraction_method="manual",
                extractor_version="test",
                checked_at_revision="rev-1",
                stale=False,
            ),
        )

        result = storage.list_claims_by_predicate(
            tenant_id="t1",
            project_id="p1",
            predicate="line_count",
        )

    assert isinstance(result, tuple)
    assert len(result) == 1
    claim = result[0]
    assert isinstance(claim, StoredClaim)
    assert claim.claim_id == "claim-1"
    assert claim.object_literal == {"value": 3}
    assert claim.stale is False


def test_list_evidences_for_source_returns_stored_evidence_dto(tmp_path: Path) -> None:
    with Storage(tmp_path / "evidence.sqlite") as storage:
        storage.register_source(tenant_id="t1", project_id="p1", source=_source("src-1"))
        storage.record_evidence(
            tenant_id="t1",
            project_id="p1",
            evidence=Evidence(
                evidence_id="evidence-1",
                kind="test_evidence",
                content={"observation": "ok"},
                source_id="src-1",
                observed_at="2026-01-01T00:00:00Z",
            ),
        )

        result = storage.list_evidences_for_source(source_id="src-1")

    assert isinstance(result, tuple)
    assert len(result) == 1
    evidence = result[0]
    assert isinstance(evidence, StoredEvidence)
    assert evidence.evidence_id == "evidence-1"
    assert evidence.content == {"observation": "ok"}
    assert evidence.kind == "test_evidence"


def test_dtos_are_immutable_and_slotted() -> None:
    assert StoredClaim.__dataclass_params__.frozen is True
    assert StoredEvidence.__dataclass_params__.frozen is True
    assert hasattr(StoredClaim, "__slots__")
    assert hasattr(StoredEvidence, "__slots__")
