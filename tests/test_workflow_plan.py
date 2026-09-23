"""Tests del WorkflowPlan (Etapa 2 / S4).

Cobertura:
- WorkflowNode valida kind, name, namespace, api_version, revision,
  expected_result.
- WorkflowTransition valida campos.
- WorkflowPlan valida initial presente y nodos referenciados.
- successors() devuelve el siguiente nodo segun outcome o None si
  no hay transicion (terminal).
"""

from __future__ import annotations

import pytest

from skillgraph.errors import ValidationError
from skillgraph.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition


def _node(**overrides: object) -> WorkflowNode:
    base: dict[str, object] = dict(
        name="a",
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )
    base.update(overrides)
    return WorkflowNode(**base)  # type: ignore[arg-type]


def _transition(**overrides: object) -> WorkflowTransition:
    base: dict[str, object] = dict(source="a", outcome="ok", target="b")
    base.update(overrides)
    return WorkflowTransition(**base)  # type: ignore[arg-type]


class TestWorkflowNodeValidation:
    def test_minimal_valid(self) -> None:
        n = _node()
        assert n.name == "a"

    @pytest.mark.parametrize(
        "kwargs, needle",
        [
            (dict(name=""), "name"),
            (dict(kind="Wrong"), "kind"),
            (dict(namespace=""), "namespace"),
            (dict(api_version=""), "api_version"),
            (dict(resource_revision=0), "revision"),
            (dict(expected_result=""), "expected_result"),
        ],
    )
    def test_invalid_field_rejected(self, kwargs: dict[str, object], needle: str) -> None:
        with pytest.raises(ValidationError, match=needle):
            _node(**kwargs)  # type: ignore[arg-type]


class TestTransitionValidation:
    def test_minimal_valid(self) -> None:
        t = _transition()
        assert t.source == "a"

    @pytest.mark.parametrize(
        "kwargs, needle",
        [
            (dict(source=""), "source"),
            (dict(outcome=""), "outcome"),
            (dict(target=""), "target"),
        ],
    )
    def test_invalid_field_rejected(self, kwargs: dict[str, object], needle: str) -> None:
        with pytest.raises(ValidationError, match=needle):
            _transition(**kwargs)  # type: ignore[arg-type]


class TestWorkflowPlan:
    def test_minimal_plan(self) -> None:
        p = WorkflowPlan(nodes=(_node(name="a"),), initial="a")
        assert p.node("a").name == "a"

    def test_initial_must_be_node(self) -> None:
        with pytest.raises(ValidationError, match="initial"):
            WorkflowPlan(nodes=(_node(name="a"),), initial="z")

    def test_empty_nodes_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sin nodos"):
            WorkflowPlan(nodes=(), initial="a")

    def test_transition_must_reference_known_nodes(self) -> None:
        with pytest.raises(ValidationError, match="no es nodo"):
            WorkflowPlan(
                nodes=(_node(name="a"), _node(name="b")),
                transitions=(_transition(source="a", outcome="ok", target="z"),),
                initial="a",
            )

    def test_successors_returns_target(self) -> None:
        p = WorkflowPlan(
            nodes=(_node(name="a"), _node(name="b")),
            transitions=(_transition(source="a", outcome="ok", target="b"),),
            initial="a",
        )
        assert p.successors("a", "ok") == "b"

    def test_successors_returns_none_when_terminal(self) -> None:
        p = WorkflowPlan(nodes=(_node(name="a"),), initial="a")
        assert p.successors("a", "ok") is None

    def test_successors_only_matches_exact_outcome(self) -> None:
        p = WorkflowPlan(
            nodes=(_node(name="a"), _node(name="b"), _node(name="c")),
            transitions=(
                _transition(source="a", outcome="yes", target="b"),
                _transition(source="a", outcome="no", target="c"),
            ),
            initial="a",
        )
        assert p.successors("a", "yes") == "b"
        assert p.successors("a", "no") == "c"
        assert p.successors("a", "maybe") is None

    def test_node_lookup_raises_for_unknown(self) -> None:
        p = WorkflowPlan(nodes=(_node(name="a"),), initial="a")
        with pytest.raises(ValidationError, match="no encontrado"):
            p.node("z")
