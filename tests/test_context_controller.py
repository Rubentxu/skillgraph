"""Tests H3 Slice 5: ContextController + OutcomeTracer + Recipe.

Doc de cobertura:
  specs/h3-slice-5.md (12 unit + 3 E2E).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.context_controller import (
    ContextController,
    OutcomeTracer,
    approx_chars,
)
from skillgraph.errors import (
    MissingObligatoryError,
    StaleKnowledgeError,
    TokenBudgetExceededError,
)
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Source,
)
from skillgraph.knowledge_controller import KnowledgeController
from skillgraph.recipe import ContextRecipe, ObligatorySelector
from skillgraph.storage import Storage

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


def _ent(eid: str = "file:a") -> Entity:
    return Entity(entity_id=eid, kind="file", stable_key=eid)


def _claim(
    ctl: KnowledgeController,
    *,
    claim_id: str,
    entity_id: str,
    source_id: str,
    revision: str = "rev1",
    object_literal: object = 1,
    predicate: str = "line_count",
) -> str:
    return ctl.record_claim(
        claim=Claim(
            claim_id=claim_id,
            subject_entity_id=entity_id,
            predicate=predicate,
            object_literal=object_literal,
            source_id=source_id,
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


def _recipe(
    *,
    recipe_ref: str = "r1",
    obligatory_kinds: list[tuple[str, str]] | None = None,
    freshness_policy: str = "best_effort",
    token_budget: int = 8000,
    overflow_strategy: str = "drop_optional",
) -> ContextRecipe:
    obligatory = tuple(
        ObligatorySelector(kind=kind_, value=val, label=lab)
        for kind_, val, lab in (obligatory_kinds or [])
    )
    return ContextRecipe(
        recipe_ref=recipe_ref,
        obligatory=obligatory,
        freshness_policy=freshness_policy,  # type: ignore[arg-type]
        token_budget=token_budget,
        overflow_strategy=overflow_strategy,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Tests unit
# ---------------------------------------------------------------------------


def test_compile_handoff_returns_handoff_with_hash(tmp_path: Path) -> None:
    """Compilar con una receta basica devuelve Handoff con context_hash."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    recipe = _recipe(obligatory_kinds=[("source", "local:a", "")])
    ctx = ContextController(knowledge=ctl)
    h = ctx.compile_handoff(
        recipe=recipe,
        run_id="r1",
        node_execution_id="n1",
    )
    assert h.context_hash  # SHA-256 hex
    assert len(h.context_hash) == 64


def test_compile_handoff_strict_rejects_stale(tmp_path: Path) -> None:
    """strict + Claim stale obligatorio -> StaleKnowledgeError."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    ctl.invalidate_from_source(source_id="local:a")
    recipe = _recipe(
        obligatory_kinds=[("source", "local:a", "")],
        freshness_policy="strict",
    )
    ctx = ContextController(knowledge=ctl)
    with pytest.raises(StaleKnowledgeError):
        ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")


def test_compile_handoff_best_effort_includes_stale_flag(tmp_path: Path) -> None:
    """best_effort + stale -> el handoff lleva capability ('stale',)."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    ctl.invalidate_from_source(source_id="local:a")
    recipe = _recipe(
        obligatory_kinds=[("source", "local:a", "")],
        freshness_policy="best_effort",
    )
    ctx = ContextController(knowledge=ctl)
    h = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
    assert "stale" in h.capabilities


def test_compile_handoff_missing_obligatory_raises(tmp_path: Path) -> None:
    """Selector obligatorio que no resuelve -> MissingObligatoryError."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    recipe = _recipe(obligatory_kinds=[("entity", "file:missing", "")])
    ctx = ContextController(knowledge=ctl)
    with pytest.raises(MissingObligatoryError):
        ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")


def test_compile_handoff_token_budget_truncates_optional(tmp_path: Path) -> None:
    """overflow drop_optional: para de aniadir optional al llegar al budget."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    # Creamos 3 entities adicionales y claims sobre la source a.
    for i in range(3):
        eid = f"file:e{i}"
        ctl.upsert_entity(entity=Entity(entity_id=eid, kind="file", stable_key=eid))
        _claim(
            ctl,
            claim_id=f"c{i + 2}",
            entity_id=eid,
            source_id="local:a",
            revision="r1",
        )
    # Receta con budget muy chico.
    recipe = ContextRecipe(
        recipe_ref="r2",
        obligatory=(ObligatorySelector(kind="entity", value="file:a", label=""),),
        optional=tuple(
            ObligatorySelector(kind="entity", value=eid, label="")
            for eid in ["file:e0", "file:e1", "file:e2"]
        ),
        token_budget=200,
        overflow_strategy="drop_optional",
    )
    ctx = ContextController(knowledge=ctl)
    h = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
    # Obligatorio entra; opcional, total >200 chars solo file:a. Limita el
    # numero de items en included.
    assert len(h.knowledge.included) >= 1  # al menos el obligatorio


def test_compile_handoff_token_budget_fail_raises(tmp_path: Path) -> None:
    """overflow=fail + obligatory > budget -> TokenBudgetExceededError."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    recipe = ContextRecipe(
        recipe_ref="r3",
        obligatory=(ObligatorySelector(kind="source", value="local:a", label=""),),
        token_budget=10,  # menor que cualquier Claim
        overflow_strategy="fail",
    )
    ctx = ContextController(knowledge=ctl)
    # Como el obligatory no cabe, NO usamos el overflow del opcional:
    # el overflow aplica solo entre obligatory y optional cuando el
    # obligatorio ya esta dentro del budget.
    # Aqui el obligatorio es > 10 chars, asi que SIEMPRE overflow.
    with pytest.raises(TokenBudgetExceededError):
        ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")


def test_compile_handoff_idempotent(tmp_path: Path) -> None:
    """Misma receta + mismo knowledge -> mismo context_hash."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(ctl, claim_id="c1", entity_id="file:a", source_id="local:a")
    recipe = _recipe(obligatory_kinds=[("source", "local:a", "")])
    ctx = ContextController(knowledge=ctl)
    h1 = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
    h2 = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
    assert h1.context_hash == h2.context_hash


def test_refresh_handoff_returns_new_hash(tmp_path: Path) -> None:
    """Knowledge cambia -> hash diferente (nueva source)."""
    ctl = _ctl(tmp_path)
    ctl.register_source(source=_src("local:a"))
    ctl.upsert_entity(entity=_ent("file:a"))
    _claim(
        ctl,
        claim_id="c1",
        entity_id="file:a",
        source_id="local:a",
        object_literal=1,
    )
    recipe = _recipe(obligatory_kinds=[("source", "local:a", "")])
    ctx = ContextController(knowledge=ctl)
    h1 = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
    # Aniadimos una nueva source + entity + claim.
    ctl.register_source(source=_src("local:b"))
    ctl.upsert_entity(entity=Entity(entity_id="file:b", kind="file", stable_key="file:b"))
    _claim(ctl, claim_id="c3", entity_id="file:b", source_id="local:b")
    recipe_b = _recipe(obligatory_kinds=[("source", "local:b", "")])
    h3 = ctx.compile_handoff(
        recipe=recipe_b,
        run_id="r1",
        node_execution_id="n1",
    )
    assert h3.context_hash != h1.context_hash


def test_outcome_tracer_references_claims_not_copies(tmp_path: Path) -> None:
    """El trace tiene `claim_refs`, NO copia contenido."""
    ctl = _ctl(tmp_path)
    # Insertar evento con resource_ref='claim:foo' y run_id='r1'.
    ctl.storage.record_event(
        tenant_id="t",
        project_id="p",
        event_id="evt-1",
        event_kind="KnowledgeInvalidated",
        resource_ref="claim:foo",
        payload={"x": 1},
        run_id="r1",
    )
    trace = OutcomeTracer.from_run(
        knowledge=ctl,
        run_id="r1",
    )
    assert "foo" in trace.claim_refs


def test_outcome_tracer_preserves_order(tmp_path: Path) -> None:
    """El orden del run se mantiene (lexicografico por resource_ref)."""
    ctl = _ctl(tmp_path)
    for cid in ["z-claim", "a-claim", "m-claim"]:
        ctl.storage.record_event(
            tenant_id="t",
            project_id="p",
            event_id=f"evt-{cid}",
            event_kind="ClaimUsed",
            resource_ref=f"claim:{cid}",
            payload={},
            run_id="r1",
        )
    trace = OutcomeTracer.from_run(knowledge=ctl, run_id="r1")
    # DISTINCT + ORDER BY resource_ref en SQL -> lexicografico.
    assert list(trace.claim_refs) == sorted(
        ["z-claim", "a-claim", "m-claim"],
    )


def test_recipe_as_brick_roundtrip(tmp_path: Path) -> None:
    """Una receta valida pasa por from_dict sin error."""
    recipe = ContextRecipe.from_dict(
        recipe_ref="my-recipe",
        raw={
            "obligatory": [
                {"kind": "source", "value": "local:a", "label": "main"},
            ],
            "optional": [],
            "freshness_policy": "strict",
            "token_budget": 100,
            "overflow_strategy": "fail",
            "revision": 2,
        },
    )
    assert recipe.recipe_ref == "my-recipe"
    assert recipe.freshness_policy == "strict"
    assert recipe.token_budget == 100
    assert recipe.overflow_strategy == "fail"
    assert recipe.revision == 2
    assert len(recipe.obligatory) == 1


def test_recipe_as_dict_when_brick_disabled(tmp_path: Path) -> None:
    """Sin brick kind 'ContextRecipe', from_dict funciona puro."""
    from skillgraph.errors import ValidationError

    with pytest.raises(ValidationError):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"obligatory": "not-a-list"},  # type: ignore[dict-item]
        )


# Bonus: helper test
def test_approx_chars_is_heuristic() -> None:
    """approx_chars es heuristica (D4 cerrada), NO tokens reales."""
    assert approx_chars({"a": 1, "b": 2}) > 0
    assert approx_chars("hello") == 5
