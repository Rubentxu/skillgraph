"""Tests del DSL declarativo (Etapa 2 / S7).

Cobertura:
- Smart constructors validan y producen tipos nominales.
- PlanBuilder es INMUTABLE: add_node/link/starts_at devuelven un
  NUEVO builder; el receptor no cambia.
- PlanBuilder rechaza duplicados y `initial` doble.
- PlanBuilder.build() delega la validacion de WorkflowPlan (atomicidad).
- El DSL produce el mismo WorkflowPlan que el plan_loader desde
  el mismo diccionario.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ParseError, ValidationError
from skillgraph.domain.dsl import (
    NODE_KINDS,
    NodeName,
    OutcomeLabel,
    PlanBuilder,
    node_name,
    outcome,
    revision,
)
from skillgraph.resources.plan_loader import _plan_from_dict
from skillgraph.resources.workflow import WorkflowPlan


class TestSmartConstructors:
    def test_node_name_accepts_alnum_dash_underscore(self) -> None:
        assert node_name("a") == "a"
        assert node_name("node_1") == "node_1"
        assert node_name("step-two") == "step-two"

    @pytest.mark.parametrize("bad", ["", "1abc", "with space", "with.dot"])
    def test_node_name_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            node_name(bad)

    def test_outcome_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="vacio"):
            outcome("")

    def test_revision_rejects_zero(self) -> None:
        with pytest.raises(ValidationError, match=">= 1"):
            revision(0)

    def test_revision_passes_positive(self) -> None:
        assert revision(3) == 3


class TestPlanBuilderImmutability:
    def test_add_node_returns_new_builder(self) -> None:
        b1 = PlanBuilder()
        b2 = b1.add_node(node_name("a"), expected="text")
        # El receptor NO cambio.
        assert b1._nodes == ()
        # El nuevo builder tiene el nodo.
        assert [n.name for n in b2._nodes] == ["a"]

    def test_link_returns_new_builder(self) -> None:
        b1 = (
            PlanBuilder()
            .add_node(node_name("a"), expected="text")
            .add_node(node_name("b"), expected="text")
        )
        b2 = b1.link(node_name("a"), outcome("ok"), node_name("b"))
        assert b1._transitions == ()
        assert len(b2._transitions) == 1

    def test_starts_at_returns_new_builder(self) -> None:
        b1 = PlanBuilder().add_node(node_name("a"), expected="text")
        b2 = b1.starts_at(node_name("a"))
        assert b1._initial is None
        assert b2._initial == "a"

    def test_double_starts_at_rejects_mismatch(self) -> None:
        b = (
            PlanBuilder()
            .add_node(node_name("a"), expected="text")
            .add_node(node_name("b"), expected="text")
            .starts_at(node_name("a"))
        )
        with pytest.raises(ParseError, match="ya tiene initial"):
            b.starts_at(node_name("b"))

    def test_add_node_rejects_duplicate(self) -> None:
        b = PlanBuilder().add_node(node_name("a"), expected="text")
        with pytest.raises(ParseError, match="duplicado"):
            b.add_node(node_name("a"), expected="text")

    def test_build_without_initial_rejected(self) -> None:
        b = PlanBuilder().add_node(node_name("a"), expected="text")
        with pytest.raises(ParseError, match="starts_at"):
            b.build()


class TestPlanBuilderBuildsValidPlan:
    def test_full_chain_builds(self) -> None:
        plan: WorkflowPlan = (
            PlanBuilder()
            .add_node(node_name("a"), expected="text")
            .add_node(node_name("b"), expected="text")
            .link(node_name("a"), outcome("ok"), node_name("b"))
            .starts_at(node_name("a"))
            .build()
        )
        assert plan.initial == "a"
        assert {n.name for n in plan.nodes} == {"a", "b"}
        assert plan.successors("a", "ok") == "b"
        assert plan.successors("a", "other") is None

    def test_node_kinds_is_closed(self) -> None:
        # ADT cerrada: estos son los unicos.
        assert frozenset({"DecisionNode", "ActionNode"}) == NODE_KINDS

    def test_decision_node_kind_accepted(self) -> None:
        plan = (
            PlanBuilder()
            .add_node(
                node_name("decide"),
                kind="DecisionNode",  # type: ignore[arg-type]
                expected="text",
                metadata={"outcomes": ["ok", "abort"]},
            )
            .starts_at(node_name("decide"))
            .build()
        )
        assert plan.node("decide").kind == "DecisionNode"
        assert plan.node("decide").outcomes == ("ok", "abort")


class TestDslMatchesLoader:
    def test_dsl_and_loader_produce_equivalent_plans(self) -> None:
        # Mismo plan por DSL...
        dsl_plan = (
            PlanBuilder()
            .add_node(node_name("a"), expected="text")
            .add_node(node_name("b"), expected="text")
            .link(node_name("a"), outcome("ok"), node_name("b"))
            .starts_at(node_name("a"))
            .build()
        )
        # ...y por loader (mismo dict de partida).
        loader_plan = _plan_from_dict(
            {
                "initial": "a",
                "nodes": [
                    {
                        "name": "a",
                        "kind": "ActionNode",
                        "namespace": "shared",
                        "apiVersion": "skillgraph.dev/v1alpha1",
                        "resourceRevision": 1,
                        "expectedResult": "text",
                    },
                    {
                        "name": "b",
                        "kind": "ActionNode",
                        "namespace": "shared",
                        "apiVersion": "skillgraph.dev/v1alpha1",
                        "resourceRevision": 1,
                        "expectedResult": "text",
                    },
                ],
                "transitions": [{"source": "a", "outcome": "ok", "target": "b"}],
            },
            source="<test>",
        )
        assert dsl_plan.initial == loader_plan.initial
        assert len(dsl_plan.nodes) == len(loader_plan.nodes)
        assert len(dsl_plan.transitions) == len(loader_plan.transitions)
        # Misma representacion canonica del `WorkflowPlan` -> mismas keys.
        assert {n.name for n in dsl_plan.nodes} == {n.name for n in loader_plan.nodes}
        # Tipos nominales: NewType es str en runtime pero el type-checker
        # debe distinguirlos.
        nm: NodeName = node_name("a")
        out: OutcomeLabel = outcome("ok")
        assert isinstance(nm, str)
        assert isinstance(out, str)
