"""Loader de WorkflowPlan desde Markdown + YAML (Etapa 2 / S6).

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md
  external/blueprint-v1/docs/06-controladores.md (RunController)

Formato esperado de un plan file:

    ---
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

    # Comentario libre

Este modulo NO depende del parser de bricks (registry.py): el formato
del WorkflowPlan es distinto (sin necesidad de spec/body extenso).
La validacion se hace contra `WorkflowPlan` (que ya valida con
__post_init__ los campos requeridos).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgraph.core.errors import ParseError
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

# YAML es opcional para el caso comun de no tener PyYAML... pero
# el proyecto ya incluye PyYAML como dependencia de S0. Lo usamos.


def load_plan_file(path: Path) -> WorkflowPlan:
    """Carga un WorkflowPlan desde un Markdown con front matter YAML.

    Lanza `ParseError` si la estructura es invalida o faltan campos.
    """
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ParseError(f"plan sin front matter YAML: {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ParseError(f"plan con front matter incompleto: {path}")
    fm = parts[1].strip()
    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError as exc:
        raise ParseError(f"YAML invalido en plan {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError(f"front matter del plan {path} no es un dict")
    try:
        return _plan_from_dict(data, source=str(path))
    except _KeyMissing as exc:
        raise ParseError(f"plan {path} falta campo: {exc}") from exc


def _plan_from_dict(data: dict[str, Any], *, source: str) -> WorkflowPlan:
    initial = _required(data, "initial", source)
    nodes_raw = _required(data, "nodes", source)
    if not isinstance(nodes_raw, list):
        raise ParseError(f"plan {source}: `nodes` debe ser lista")
    transitions_raw = data.get("transitions") or []
    if not isinstance(transitions_raw, list):
        raise ParseError(f"plan {source}: `transitions` debe ser lista")

    nodes = tuple(_node_from_dict(n, source) for n in nodes_raw)
    transitions = tuple(_transition_from_dict(t, source) for t in transitions_raw)
    return WorkflowPlan(nodes=nodes, transitions=transitions, initial=initial)


def _resource_revision(data: dict[str, Any], source: str) -> int:
    """Lee `resourceRevision`/`resource_revision` rechazando bool.

    WI-49: `int(True)` es 1 y el resultado pasaria el invariante
    `>= 1` de WorkflowNode en silencio: el plan queda con una
    revision que nadie declaro. Misma clase de fallo que
    metadata.max_visits (fix 21087d1) y Recipe.token_budget (fix
    dbe7f81).

    Las demas coercions se preservan (deterministas y fijadas por
    test, igual que `recipe._coerce_int`): `int('3')` acepta y
    `int(2.9)` trunca. La ausencia del campo sigue devolviendo 0.
    """
    raw = data.get("resourceRevision")
    if raw is None:
        raw = data.get("resource_revision")
    if raw is None:
        return 0
    if isinstance(raw, bool):
        raise ParseError(f"plan {source}: resourceRevision debe ser int, no bool: {raw!r}")
    return int(raw)


def _node_from_dict(data: Any, source: str) -> WorkflowNode:
    if not isinstance(data, dict):
        raise ParseError(f"plan {source}: nodo invalido {data!r}")
    return WorkflowNode(
        name=data["name"],
        kind=data["kind"],
        namespace=data["namespace"],
        api_version=data.get("apiVersion") or data.get("api_version") or "",
        resource_revision=_resource_revision(data, source),
        expected_result=data.get("expectedResult") or data.get("expected_result") or "",
        capabilities=tuple(data.get("capabilities") or ()),
        metadata=dict(data.get("metadata") or {}),
    )


def _transition_from_dict(data: Any, source: str) -> WorkflowTransition:
    if not isinstance(data, dict):
        raise ParseError(f"plan {source}: transicion invalida {data!r}")
    return WorkflowTransition(
        source=data["source"],
        outcome=data["outcome"],
        target=data["target"],
    )


class _KeyMissing(Exception):
    pass


def _required(data: dict[str, Any], key: str, source: str) -> Any:
    if key not in data:
        raise _KeyMissing(key)
    return data[key]
