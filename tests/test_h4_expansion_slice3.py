"""Tests H4 Slice 3: Policy engine + EVALUATE stage.

Cubre:
- Reglas P1..P5 del DefaultPolicyEngine (rechazo + razon legal).
- Defaults conservadores (no-regression sobre slice-1+2).
- evaluate_proposal() wrapper (accepted/reason/evaluated_at).
- Custom engine via Protocol (extensibilidad).

No cubre (deferido a otros modulos):
- CLI list/show/archive (test_h4_expansion_cli_slice3.py).
- Concurrencia real (test_h4_expansion_concurrency.py, slice-4).
- Storage SQLite (deferido a slice-4; JSON files son source-of-truth
  actual; ver specs/h4-slice-3.md ��4 limitacion 3).
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from skillgraph.graph_expansion import (
    AddNode,
    Authorization,
    EvaluationResult,
    GraphExpansionProposal,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    PolicySettings,
    propose,
)
from skillgraph.workflow import WorkflowNode, WorkflowPlan

# ---------------------------------------------------------------------------
# Fixtures (minimalistas; NO duplica las de test_h4_expansion.py)
# ---------------------------------------------------------------------------


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="DecisionNode",
        namespace="ns-test",
        api_version="skillgraph/v1",
        resource_revision=1,
        expected_result=f"out-{name}",
        capabilities=(),
        metadata={"outcomes": ["pass", "fail"]},
    )


@pytest.fixture
def base_plan() -> WorkflowPlan:
    """Plan base: 2 nodos, sin transiciones (suficiente para policy)."""
    return WorkflowPlan(
        nodes=(_node("root"), _node("child")),
        initial="root",
        transitions=(),
    )


@pytest.fixture
def registry() -> Mapping[str, str]:
    return {"compile": "brick:compile", "lint": "brick:lint"}


@pytest.fixture
def manual_authorization() -> Authorization:
    return Authorization(
        mode="manual_signed",
        granted_by="op@example.com",
        granted_at="2026-09-23T11:00:00Z",
    )


@pytest.fixture
def valid_proposal(manual_authorization: Authorization) -> GraphExpansionProposal:
    """Proposal valida slice-1: AddNode con capability registrada."""
    return propose(
        base_revision="rev-1",
        problem_observed="test slice-3 policy",
        evidence=(),
        operations=(AddNode(node=_node("extra")),),
        capabilities_needed=("lint",),
        new_dependencies=(),
        attachment_point="root",
        scope="NODE",
        authorization=manual_authorization,
        author="tester",
    )


# ---------------------------------------------------------------------------
# T0: no-regression sobre slice-1
# ---------------------------------------------------------------------------


def test_default_policy_engine_accepts_valid_slice1_proposal(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """Sin settings restrictivos, una propuesta valida slice-1 debe
    pasar EVALUATE (no-regression). Si esto falla, slice-3 rompe
    slice-1.
    """
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry)
    assert result.accepted is True
    assert result.policy_decision.violated_rules == ()
    assert result.policy_decision.reason == "OK"
    assert result.evaluated_by == "DefaultPolicyEngine"
    assert result.evaluated_at  # ISO-8601 non-empty


def evaluate_proposal_valid(
    proposal: GraphExpansionProposal,
    plan: WorkflowPlan,
    registry: Mapping[str, str],
    **kwargs: object,
) -> EvaluationResult:
    """Helper: llama a evaluate_proposal (no top-level para evitar confusion)."""
    from skillgraph.graph_expansion import evaluate_proposal

    return evaluate_proposal(proposal, plan, registry, **kwargs)


# ---------------------------------------------------------------------------
# T1: regla P1 (max_ops_per_proposal)
# ---------------------------------------------------------------------------


def test_p1_rejects_proposal_with_too_many_operations(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P1: proposal con mas operaciones que max_ops_per_proposal."""
    settings = PolicySettings(max_ops_per_proposal=0)
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is False
    assert any("P1:" in r for r in result.policy_decision.violated_rules)
    assert "max_ops_per_proposal=0" in result.policy_decision.reason


def test_p1_accepts_proposal_within_limit(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P1: proposal con 1 op y max_ops=1 debe pasar."""
    settings = PolicySettings(max_ops_per_proposal=1)
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is True


# ---------------------------------------------------------------------------
# T2: regla P2 (no concurrent proposals on same attachment_point)
# ---------------------------------------------------------------------------


def test_p2_rejects_concurrent_proposal_same_attachment(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
    manual_authorization: Authorization,
) -> None:
    """P2: proposal concurrente con mismo attachment_point debe rechazarse."""
    concurrent = propose(
        base_revision="rev-1",
        problem_observed="otro",
        evidence=(),
        operations=(AddNode(node=_node("otro")),),
        capabilities_needed=("lint",),
        new_dependencies=(),
        attachment_point="root",  # MISMO attachment_point
        scope="NODE",
        authorization=manual_authorization,
        author="tester2",
    )
    result = evaluate_proposal_valid(
        valid_proposal,
        base_plan,
        registry,
        concurrent_proposals=(concurrent,),
    )
    assert result.accepted is False
    assert any("P2:" in r for r in result.policy_decision.violated_rules)
    assert "concurrent proposal" in result.policy_decision.reason
    assert concurrent.proposal_id in result.policy_decision.reason


def test_p2_accepts_concurrent_proposal_different_attachment(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
    manual_authorization: Authorization,
) -> None:
    """P2: proposal concurrente con attachment_point distinto debe pasar."""
    concurrent = propose(
        base_revision="rev-1",
        problem_observed="otro",
        evidence=(),
        operations=(AddNode(node=_node("otro")),),
        capabilities_needed=("lint",),
        new_dependencies=(),
        attachment_point="otro",  # DIFERENTE
        scope="NODE",
        authorization=manual_authorization,
        author="tester2",
    )
    result = evaluate_proposal_valid(
        valid_proposal,
        base_plan,
        registry,
        concurrent_proposals=(concurrent,),
    )
    assert result.accepted is True


# ---------------------------------------------------------------------------
# T3: regla P3 (scope restrictions)
# ---------------------------------------------------------------------------


def test_p3_rejects_scope_not_in_allowed(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P3: scope NODE no permitido si allowed_scopes=('TRANSITION',)."""
    settings = PolicySettings(allowed_scopes=("TRANSITION",))
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is False
    assert any("P3:" in r for r in result.policy_decision.violated_rules)


def test_p3_accepts_when_allowed_scopes_empty(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P3: vacio = todos los scopes permitidos (default conservador)."""
    settings = PolicySettings(allowed_scopes=())
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is True


# ---------------------------------------------------------------------------
# T4: regla P4 (forbidden_ops, defensa en profundidad)
# ---------------------------------------------------------------------------


def test_p4_rejects_forbidden_op(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P4: AddNode bloqueado si forbidden_ops=('AddNode',)."""
    settings = PolicySettings(forbidden_ops=("AddNode",))
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is False
    assert any("P4:" in r for r in result.policy_decision.violated_rules)
    assert "AddNode" in result.policy_decision.reason


def test_p4_default_empty_forbidden_accepts(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P4: defaults (forbidden_ops vacio) acepta cualquier op valida."""
    settings = PolicySettings(forbidden_ops=())
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is True


# ---------------------------------------------------------------------------
# T5: regla P5 (budget cap, projected nodes)
# ---------------------------------------------------------------------------


def test_p5_rejects_when_projected_exceeds_budget(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P5: 2 nodos actuales + 1 AddNode proyectado = 3 > max_nodes=2."""
    settings = PolicySettings(max_nodes_per_project=2)
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is False
    assert any("P5:" in r for r in result.policy_decision.violated_rules)
    assert "projected_nodes=3" in result.policy_decision.reason


def test_p5_accepts_when_within_budget(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """P5: 3 proyectados <= max_nodes=3."""
    settings = PolicySettings(max_nodes_per_project=3)
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is True


# ---------------------------------------------------------------------------
# T6: combinacion de reglas
# ---------------------------------------------------------------------------


def test_multiple_violations_combined_in_reason(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """Multiples violaciones aparecen en reason y violated_rules."""
    settings = PolicySettings(
        max_ops_per_proposal=0,
        forbidden_ops=("AddNode",),
    )
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, settings=settings)
    assert result.accepted is False
    assert len(result.policy_decision.violated_rules) == 2
    assert "P1:" in result.policy_decision.reason
    assert "P4:" in result.policy_decision.reason


# ---------------------------------------------------------------------------
# T7: extensibilidad (custom engine via Protocol)
# ---------------------------------------------------------------------------


class _AlwaysRejectEngine:
    """Custom engine: rechaza TODO (testing protocol extensibility)."""

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        return PolicyDecision(
            accepted=False,
            reason="custom: always reject",
            violated_rules=("CUSTOM",),
        )


def test_custom_engine_protocol_compatibility(
    valid_proposal: GraphExpansionProposal,
    base_plan: WorkflowPlan,
    registry: Mapping[str, str],
) -> None:
    """Un engine custom que cumple el Protocol debe poder sustituir
    al default via parametro `engine=`.
    """
    engine: PolicyEngine = _AlwaysRejectEngine()
    result = evaluate_proposal_valid(valid_proposal, base_plan, registry, engine=engine)
    assert result.accepted is False
    assert result.evaluated_by == "_AlwaysRejectEngine"
    assert "always reject" in result.policy_decision.reason


# ---------------------------------------------------------------------------
# T8: defaults PolicySettings son frozen y conservadores
# ---------------------------------------------------------------------------


def test_default_policy_settings_are_conservative() -> None:
    """Defaults deben ser tales que propuestas slice-1 validas pasen."""
    s = PolicySettings()
    assert s.max_ops_per_proposal >= 1  # 1 op por propuesta es normal
    assert s.max_nodes_per_project > 0
    assert s.allowed_scopes == ()  # vacio = todos
    assert s.forbidden_ops == ()  # vacio = ninguno


def test_policy_settings_is_immutable() -> None:
    """PolicySettings es frozen: no se puede mutar."""
    s = PolicySettings()
    with pytest.raises((AttributeError, Exception)):
        s.max_ops_per_proposal = 999  # type: ignore[misc]
