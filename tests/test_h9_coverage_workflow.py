"""H9-Coverage-7: cobertura de las ramas no ejercitadas de
`skillgraph.resources.workflow` (93% -> >=95%).

Las ramas cubiertas aqui son:
- _declared_outcomes: raw no-lista o no-strings -> ValidationError
- _declared_max_visits: raw no-int o < 1 -> ValidationError
- WorkflowNode: metadata no-dict -> ValidationError
- WorkflowNode: ActionNode con outcomes via metadata (degraded mode)
- WorkflowPlan: initial vacio -> ValidationError
- WorkflowPlan: transition.source no es nodo -> ValidationError

Sin modificacion de produccion. Spec: specs/h9-coverage-workflow.md.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.resources.workflow import (
    MAX_VISITS_KEY,
    OUTCOME_KEY,
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_node(
    *,
    name: str = "a1",
    metadata: dict | None = None,
    **overrides: object,
) -> WorkflowNode:
    """Crea un WorkflowNode valido ActionNode."""
    defaults: dict[str, object] = {
        "name": name,
        "kind": "ActionNode",
        "namespace": "shared",
        "api_version": "skillgraph.dev/v1alpha1",
        "resource_revision": 1,
        "expected_result": "ok",
    }
    defaults.update(overrides)
    if metadata is not None:
        defaults["metadata"] = metadata
    return WorkflowNode(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _declared_outcomes: raw no-lista o no-strings
# ---------------------------------------------------------------------------


def test_metadata_outcomes_not_a_list_raises() -> None:
    """`metadata.outcomes = "ok"` (string, no list) -> ValidationError.

    Cubre linea 32 (rama `not isinstance(raw, list)`).
    """
    with pytest.raises(ValidationError, match=r"debe ser lista de strings"):
        _action_node(metadata={OUTCOME_KEY: "ok"})  # type: ignore[arg-type]


def test_metadata_outcomes_with_non_string_item_raises() -> None:
    """`metadata.outcomes = ["ok", 123]` -> ValidationError (123 no string).

    Cubre linea 32 (rama `not all(isinstance(o, str) ...)`).
    """
    with pytest.raises(ValidationError, match=r"debe ser lista de strings"):
        _action_node(metadata={OUTCOME_KEY: ["ok", 123]})  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# _declared_max_visits: raw no-int o < 1
# ---------------------------------------------------------------------------


def test_metadata_max_visits_negative_raises() -> None:
    """`metadata.max_visits = -1` -> ValidationError.

    Cubre linea 43 (rama `raw < 1`).
    """
    with pytest.raises(ValidationError, match=r"debe ser int >= 1"):
        _action_node(metadata={MAX_VISITS_KEY: -1})


def test_metadata_max_visits_string_raises() -> None:
    """`metadata.max_visits = "5"` (string) -> ValidationError.

    Cubre linea 43 (rama `not isinstance(raw, int)`).
    """
    with pytest.raises(ValidationError, match=r"debe ser int >= 1"):
        _action_node(metadata={MAX_VISITS_KEY: "5"})  # type: ignore[dict-item]


# ---------------------------------------------------------------------------
# WorkflowNode.__post_init__: metadata no-dict
# ---------------------------------------------------------------------------


def test_workflow_node_metadata_not_dict_raises() -> None:
    """WorkflowNode con `metadata="x"` (no dict) -> ValidationError.

    Cubre linea 82.
    """
    with pytest.raises(ValidationError, match=r"WorkflowNode\.metadata debe ser dict"):
        _action_node(metadata="not-a-dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WorkflowNode: ActionNode con outcomes via metadata (degraded mode)
# ---------------------------------------------------------------------------


def test_action_node_with_metadata_outcomes_respects_declared() -> None:
    """ActionNode con `metadata.outcomes = ["ok", "next"]` -> outcomes
    se respetan via metadata (degraded mode: metadata es la verdad).

    Cubre linea 92 (rama `elif declared`).
    """
    node = _action_node(metadata={OUTCOME_KEY: ["ok", "next"]})
    assert node.outcomes == ("ok", "next")


# ---------------------------------------------------------------------------
# WorkflowPlan: initial vacio
# ---------------------------------------------------------------------------


def test_workflow_plan_initial_empty_raises() -> None:
    """WorkflowPlan con initial="" -> ValidationError.

    Cubre linea 128.
    """
    node = _action_node(name="a1")
    with pytest.raises(ValidationError, match=r"WorkflowPlan\.initial vacio"):
        WorkflowPlan(nodes=(node,), initial="")


# ---------------------------------------------------------------------------
# WorkflowPlan: transition.source no es nodo del plan
# ---------------------------------------------------------------------------


def test_workflow_plan_transition_source_not_in_nodes_raises() -> None:
    """Transicion con source fantasma (no en nodes) -> ValidationError.

    Cubre linea 133.
    """
    a1 = _action_node(name="a1")
    t = WorkflowTransition(source="ghost", outcome="ok", target="a1")
    with pytest.raises(ValidationError, match=r"WorkflowTransition\.source 'ghost' no es nodo"):
        WorkflowPlan(nodes=(a1,), initial="a1", transitions=(t,))
