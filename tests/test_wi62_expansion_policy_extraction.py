"""Red de contrato WI-62: subsistema de policy extraido a expansion_policy.

Cuarto estrangulamiento (ADR-0021): el bloque policy (196 LoC) sale de
`graph_expansion.py` a `governance/expansion_policy.py` con
TYPE_CHECKING para anotaciones (cero ciclo) y re-export runtime en
graph_expansion (`__all__` intacto; el test H4-slice3 no se edita).
"""

from __future__ import annotations

import skillgraph.governance.expansion_policy as policy
from skillgraph.governance import graph_expansion


class TestPolicyIdentity:
    """`graph_expansion.X` DEBE ser el simbolo real de expansion_policy."""

    def test_policy_engine_identity(self) -> None:
        assert graph_expansion.PolicyEngine is policy.PolicyEngine

    def test_default_policy_engine_identity(self) -> None:
        assert graph_expansion.DefaultPolicyEngine is policy.DefaultPolicyEngine

    def test_evaluate_proposal_identity(self) -> None:
        assert graph_expansion.evaluate_proposal is policy.evaluate_proposal

    def test_policy_types_identity(self) -> None:
        assert graph_expansion.PolicySettings is policy.PolicySettings
        assert graph_expansion.PolicyContext is policy.PolicyContext
        assert graph_expansion.PolicyDecision is policy.PolicyDecision
        assert graph_expansion.EvaluationResult is policy.EvaluationResult
        assert graph_expansion.ProposalStage is policy.ProposalStage

    def test_proposal_stage_name_identity(self) -> None:
        assert graph_expansion.ProposalStageName is policy.ProposalStageName


class TestGraphExpansionBelowThreshold:
    """ADR-0021: graph_expansion por debajo del umbral de god file."""

    def test_graph_expansion_under_800_loc(self) -> None:
        import inspect

        loc = len(inspect.getsource(graph_expansion).splitlines())
        assert loc < 800, f"graph_expansion volvio a ser god file: {loc} LoC"

    def test_graph_expansion_has_no_policy_definitions_left(self) -> None:
        import inspect

        source = inspect.getsource(graph_expansion)
        assert "class DefaultPolicyEngine" not in source
        assert "def evaluate_proposal" not in source


class TestBehavioralSmoke:
    """La policy extraida decide igual (contrato P1..P5, humo minimo).

    Contexto via SimpleNamespace: el subsistema no hace isinstance del
    proposal (solo de los ops por nombre en P5, y aqui van vacios).
    """

    def _ctx(self) -> policy.PolicyContext:
        from types import SimpleNamespace

        proposal = SimpleNamespace(
            proposal_id="p1",
            attachment_point="a",
            scope="NODE",
            operations=(),
        )
        plan = SimpleNamespace(nodes=())
        return policy.PolicyContext(
            proposal=proposal,
            plan=plan,
            registry={},
            concurrent_proposals=(),
            settings=policy.PolicySettings(),
        )

    def test_default_engine_accepts_context_within_limits(self) -> None:
        decision = policy.DefaultPolicyEngine().evaluate(self._ctx())
        assert decision.accepted
        assert decision.violated_rules == ()

    def test_p1_max_ops_violation(self) -> None:
        from types import SimpleNamespace

        proposal = SimpleNamespace(
            proposal_id="p1",
            attachment_point="a",
            scope="NODE",
            operations=(object(), object()),
        )
        ctx = policy.PolicyContext(
            proposal=proposal,
            plan=SimpleNamespace(nodes=()),
            registry={},
            concurrent_proposals=(),
            settings=policy.PolicySettings(max_ops_per_proposal=1),
        )
        decision = policy.DefaultPolicyEngine().evaluate(ctx)
        assert not decision.accepted
        assert any(v.startswith("P1:") for v in decision.violated_rules)
