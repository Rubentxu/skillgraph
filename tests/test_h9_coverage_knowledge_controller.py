"""H9-Coverage-9: cobertura `skillgraph.knowledge.knowledge_controller` (93% -> >=95%).

Ramas cubiertas (todas alcanzables):
- L74-75: make_evidence_id (funcion pura no testeada directamente)
- L342->358: record_finding con finding_id vacio -> genera via make_finding_id

Sin modificacion de produccion. Spec: specs/h9-coverage-knowledge-controller.md.
"""

from __future__ import annotations

from pathlib import Path

from skillgraph.knowledge.graph import (
    Entity,
    EntityID,
    Finding,
    FindingID,
    Source,
    SourceID,
)
from skillgraph.knowledge.knowledge_controller import (
    KnowledgeController,
    make_evidence_id,
    make_finding_id,
)
from skillgraph.platform.storage import Storage

TENANT = "t"
PROJECT = "p"


def _source_id(name: str = "src1") -> SourceID:
    return SourceID(f"src-{name}")


def _entity_id(name: str = "ent1") -> EntityID:
    return EntityID(f"ent-{name}")


def _build(tmp_path: Path) -> tuple[KnowledgeController, Storage]:
    storage = Storage(tmp_path / "store.sqlite")
    # El schema se inicializa al instanciar Storage (open -> CREATE TABLE).
    ctl = KnowledgeController(storage=storage, tenant_id=TENANT, project_id=PROJECT)
    return ctl, storage


def _seed_source_and_entity(ctl: KnowledgeController) -> tuple[SourceID, EntityID]:
    src_id = _source_id()
    ctl.register_source(
        source=Source(
            source_id=src_id,
            kind="local_file",
            content_hash="abc",
            locator={"path": "src/foo.py"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    )
    ent_id = _entity_id()
    ctl.upsert_entity(
        entity=Entity(
            entity_id=ent_id,
            kind="dataset",
            stable_key="ds1",
        )
    )
    return src_id, ent_id


# ---------------------------------------------------------------------------
# L74-75: make_evidence_id (funcion pura)
# ---------------------------------------------------------------------------


def test_make_evidence_id_is_deterministic() -> None:
    """make_evidence_id retorna el mismo ID para misma entrada (idempotencia)."""
    eid_a = make_evidence_id(source_id=_source_id("s"), content_repr="payload")
    eid_b = make_evidence_id(source_id=_source_id("s"), content_repr="payload")
    assert eid_a == eid_b
    assert eid_a.startswith("ev-")


def test_make_evidence_id_changes_with_content() -> None:
    """Distinto content_repr produce distinto ID."""
    eid_a = make_evidence_id(source_id=_source_id("s"), content_repr="a")
    eid_b = make_evidence_id(source_id=_source_id("s"), content_repr="b")
    assert eid_a != eid_b


def test_make_finding_id_is_deterministic() -> None:
    """make_finding_id determinista."""
    fid_a = make_finding_id(entity_id=_entity_id("e"), rule_ref="rule.x", rule_version="1")
    fid_b = make_finding_id(entity_id=_entity_id("e"), rule_ref="rule.x", rule_version="1")
    assert fid_a == fid_b
    assert fid_a.startswith("fnd-")


# ---------------------------------------------------------------------------
# L342->358: record_finding con finding_id vacio genera via make_finding_id
# ---------------------------------------------------------------------------


def test_record_finding_generates_id_when_empty(tmp_path: Path) -> None:
    """record_finding con finding_id="" genera uno determinista.

    Cubre L342 (rama `not finding.finding_id`) y L343-357 (make_finding_id
    + Finding copy con id generado).
    """
    ctl, _storage = _build(tmp_path)
    _src_id, ent_id = _seed_source_and_entity(ctl)

    # Finding con finding_id="" explicito (NewType permite str vacio)
    f = Finding(
        finding_id=FindingID(""),
        entity_id=ent_id,
        observation="obs",
        rule_ref="rule.x",
        rule_version="1",
        evidence_ids=(),
        result="pass",
        valid_until_revision=None,
    )
    returned_id = ctl.record_finding(finding=f)
    expected_id = make_finding_id(entity_id=ent_id, rule_ref="rule.x", rule_version="1")
    assert returned_id == expected_id
    assert returned_id.startswith("fnd-")


def test_record_finding_uses_provided_id_when_set(tmp_path: Path) -> None:
    """record_finding con finding_id provisto respeta el ID del usuario."""
    ctl, _storage = _build(tmp_path)
    _src_id, ent_id = _seed_source_and_entity(ctl)

    explicit_id = FindingID("fnd-explicit-id")
    f = Finding(
        finding_id=explicit_id,
        entity_id=ent_id,
        observation="obs",
        rule_ref="rule.x",
        rule_version="1",
        evidence_ids=(),
        result="pass",
        valid_until_revision=None,
    )
    returned_id = ctl.record_finding(finding=f)
    assert returned_id == explicit_id
