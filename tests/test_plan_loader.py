"""Tests focalizados del loader de WorkflowPlan desde Markdown+YAML.

Cubre las 23 missing lines que pytest-cov reporta como uncovered
en `src/skillgraph/plan_loader.py`:

- load_plan_file: 4 ramas de error (sin front matter, fm incompleto,
  YAML invalido, no-dict) + happy path que no tenia tests directos.
- _plan_from_dict: 2 ramas (nodes no-list, transitions no-list).
- _node_from_dict: 1 rama (no-dict).
- _transition_from_dict: 1 rama (no-dict).
- _required: 1 rama (key missing).

NO duplica lo que ya cubren tests/test_workflow_plan.py
(constructor WorkflowPlan con __post_init__).

Ver specs/h4-slice-3.md (stewardship de cobertura).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph import ParseError
from skillgraph.resources.plan_loader import load_plan_file

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_VALID_PLAN = """---
apiVersion: skillgraph.dev/v1alpha1
kind: WorkflowPlan
name: my-flow
initial: a
nodes:
  - name: a
    kind: ActionNode
    namespace: shared
    apiVersion: skillgraph.dev/v1alpha1
    resourceRevision: 1
    expectedResult: text
  - name: b
    kind: ActionNode
    namespace: shared
    apiVersion: skillgraph.dev/v1alpha1
    resourceRevision: 1
    expectedResult: text
transitions:
  - source: a
    outcome: ok
    target: b
---

# Optional body markdown
"""


def _write_plan(tmp_path: Path, body: str, name: str = "plan.md") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# T1: load_plan_file happy path
# ---------------------------------------------------------------------------


def test_load_plan_file_happy_path(tmp_path: Path) -> None:
    """Carga un plan valido: nodos + transitions + initial correctos."""
    path = _write_plan(tmp_path, _VALID_PLAN)
    plan = load_plan_file(path)
    assert plan.initial == "a"
    assert len(plan.nodes) == 2
    assert plan.nodes[0].name == "a"
    assert plan.nodes[1].name == "b"
    assert len(plan.transitions) == 1
    assert plan.transitions[0].source == "a"
    assert plan.transitions[0].outcome == "ok"
    assert plan.transitions[0].target == "b"


def test_load_plan_file_supports_camelcase_and_snake_case(tmp_path: Path) -> None:
    """_node_from_dict acepta tanto apiVersion/expectedResult (camelCase)
    como api_version/expected_result (snake_case)."""
    snake_yaml = """---
initial: root
nodes:
  - name: root
    kind: ActionNode
    namespace: shared
    api_version: skillgraph.dev/v1alpha1
    resource_revision: 1
    expected_result: text
transitions: []
---
"""
    path = _write_plan(tmp_path, snake_yaml, name="snake.md")
    plan = load_plan_file(path)
    assert plan.nodes[0].api_version == "skillgraph.dev/v1alpha1"
    assert plan.nodes[0].expected_result == "text"


def test_load_plan_file_empty_transitions(tmp_path: Path) -> None:
    """`transitions: []` (o ausente) es valido."""
    minimal = """---
initial: solo
nodes:
  - name: solo
    kind: ActionNode
    namespace: shared
    apiVersion: skillgraph.dev/v1alpha1
    resourceRevision: 1
    expectedResult: text
transitions: []
---
"""
    path = _write_plan(tmp_path, minimal)
    plan = load_plan_file(path)
    assert plan.transitions == ()


# ---------------------------------------------------------------------------
# T2: load_plan_file error branches
# ---------------------------------------------------------------------------


def test_load_plan_file_raises_when_no_front_matter(tmp_path: Path) -> None:
    """Sin delimitador '---' inicial -> ParseError."""
    path = _write_plan(tmp_path, "# solo markdown sin fm\n")
    with pytest.raises(ParseError, match="sin front matter"):
        load_plan_file(path)


def test_load_plan_file_raises_when_front_matter_incomplete(tmp_path: Path) -> None:
    """Solo el delimitador inicial '---' pero falta el de cierre -> ParseError."""
    incomplete = "---\nkey: value\n"
    path = _write_plan(tmp_path, incomplete)
    with pytest.raises(ParseError, match="front matter incompleto"):
        load_plan_file(path)


def test_load_plan_file_raises_on_yaml_invalid_syntax(tmp_path: Path) -> None:
    """YAML malformado dentro del front matter -> ParseError."""
    bad_yaml = """---
initial: x
nodes: [a, b
---
"""
    path = _write_plan(tmp_path, bad_yaml)
    with pytest.raises(ParseError, match="YAML inv"):
        load_plan_file(path)


def test_load_plan_file_raises_when_yaml_top_level_not_dict(tmp_path: Path) -> None:
    """YAML cuyo top-level es lista -> ParseError."""
    list_yaml = """---
- item
---
"""
    path = _write_plan(tmp_path, list_yaml)
    with pytest.raises(ParseError, match="no es un dict"):
        load_plan_file(path)


# ---------------------------------------------------------------------------
# T3: _plan_from_dict error branches
# ---------------------------------------------------------------------------


def test_load_plan_file_raises_when_nodes_not_list(tmp_path: Path) -> None:
    """`nodes` presente pero no es lista -> ParseError via _plan_from_dict."""
    bad = """---
initial: a
nodes: "not-a-list"
---
"""
    path = _write_plan(tmp_path, bad)
    with pytest.raises(ParseError, match="`nodes` debe ser lista"):
        load_plan_file(path)


def test_load_plan_file_raises_when_transitions_not_list(tmp_path: Path) -> None:
    """`transitions` presente pero no es lista -> ParseError via _plan_from_dict."""
    bad = """---
initial: a
nodes:
  - name: a
    kind: ActionNode
    namespace: shared
    apiVersion: skillgraph.dev/v1alpha1
    resourceRevision: 1
    expectedResult: text
transitions: "not-a-list"
---
"""
    path = _write_plan(tmp_path, bad)
    with pytest.raises(ParseError, match="`transitions` debe ser lista"):
        load_plan_file(path)


def test_load_plan_file_raises_when_node_entry_not_dict(tmp_path: Path) -> None:
    """Nodo dentro de la lista `nodes` que no es dict -> ParseError."""
    bad = """---
initial: a
nodes:
  - "not-a-dict"
---
"""
    path = _write_plan(tmp_path, bad)
    with pytest.raises(ParseError, match="nodo invalido"):
        load_plan_file(path)


def test_load_plan_file_raises_when_transition_entry_not_dict(tmp_path: Path) -> None:
    """Transition dentro de la lista `transitions` que no es dict -> ParseError."""
    bad = """---
initial: a
nodes:
  - name: a
    kind: ActionNode
    namespace: shared
    apiVersion: skillgraph.dev/v1alpha1
    resourceRevision: 1
    expectedResult: text
transitions:
  - "not-a-dict"
---
"""
    path = _write_plan(tmp_path, bad)
    with pytest.raises(ParseError, match="transicion invalida"):
        load_plan_file(path)


# ---------------------------------------------------------------------------
# T4: _required branch (campo obligatorio faltante)
# ---------------------------------------------------------------------------


def test_load_plan_file_raises_when_initial_missing(tmp_path: Path) -> None:
    """Campo obligatorio `initial` ausente -> ParseError via _required."""
    bad = """---
nodes:
  - name: a
    kind: ActionNode
    namespace: shared
    apiVersion: skillgraph.dev/v1alpha1
    resourceRevision: 1
    expectedResult: text
---
"""
    path = _write_plan(tmp_path, bad)
    with pytest.raises(ParseError, match="falta campo: initial"):
        load_plan_file(path)


def test_load_plan_file_raises_when_nodes_missing(tmp_path: Path) -> None:
    """Campo obligatorio `nodes` ausente -> ParseError via _required."""
    bad = """---
initial: a
---
"""
    path = _write_plan(tmp_path, bad)
    with pytest.raises(ParseError, match="falta campo: nodes"):
        load_plan_file(path)
