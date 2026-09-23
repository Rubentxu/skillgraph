"""Workflow declarativo (Etapa 2 / S4).

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md

El `WorkflowPlan` es la declaracion de un subgrafo ejecutable:
- Cada nodo es un brick del catalogo (DecisionNode o ActionNode).
- Las relaciones de control de flujo se declaran como pares
  `(source_name, outcome_label) -> target_name`.

NO es un grafo general: es un DAG de control de flujo. La expansion
dinamica (DISCOVER -> PROPOSE -> ...) llega en Etapa 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from skillgraph.errors import ValidationError
from skillgraph.runtime_types import NODE_KINDS, NodeKind

OUTCOME_KEY = "outcomes"
MAX_VISITS_KEY = "max_visits"


def _declared_outcomes(metadata: dict[str, Any]) -> tuple[str, ...]:
    raw = metadata.get(OUTCOME_KEY)
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(o, str) and o for o in raw):
        raise ValidationError(
            f"WorkflowNode.metadata[{OUTCOME_KEY!r}] debe ser lista de strings no vacios"
        )
    return tuple(raw)


def _declared_max_visits(metadata: dict[str, Any]) -> int | None:
    raw = metadata.get(MAX_VISITS_KEY)
    if raw is None:
        return None
    if not isinstance(raw, int) or raw < 1:
        raise ValidationError(
            f"WorkflowNode.metadata[{MAX_VISITS_KEY!r}] debe ser int >= 1 o ausente"
        )
    return raw


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """Un nodo del plan: que brick ejecutar."""

    name: str
    """Identificador local dentro del plan (unico)."""

    kind: NodeKind
    """DecisionNode o ActionNode."""

    namespace: str
    api_version: str
    resource_revision: int
    expected_result: str
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    outcomes: tuple[str, ...] = ()
    max_visits: int | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("WorkflowNode.name vacio")
        if self.kind not in NODE_KINDS:
            raise ValidationError(f"WorkflowNode.kind invalido: {self.kind!r}")
        if not self.namespace:
            raise ValidationError("WorkflowNode.namespace vacio")
        if not self.api_version:
            raise ValidationError("WorkflowNode.api_version vacio")
        if self.resource_revision < 1:
            raise ValidationError("WorkflowNode.resource_revision debe ser >= 1")
        if not self.expected_result:
            raise ValidationError("WorkflowNode.expected_result vacio")
        if not isinstance(self.metadata, dict):
            raise ValidationError("WorkflowNode.metadata debe ser dict")
        # H4: DecisionNode requiere outcomes declarados; max_visits es optativo.
        declared = _declared_outcomes(self.metadata)
        if self.kind == "DecisionNode":
            if not declared:
                raise ValidationError("DecisionNode requiere metadata.outcomes (lista no vacia)")
            object.__setattr__(self, "outcomes", declared)
        elif declared:
            # Si ActionNode declara outcomes por metadata, lo respetamos
            # (degraded mode: metadata es la verdad).
            object.__setattr__(self, "outcomes", declared)
        mv = _declared_max_visits(self.metadata)
        if mv is not None:
            object.__setattr__(self, "max_visits", mv)


@dataclass(frozen=True, slots=True)
class WorkflowTransition:
    """Salida de un nodo: 'cuando el outcome = X, ve al nodo Y'."""

    source: str
    outcome: str
    target: str

    def __post_init__(self) -> None:
        if not self.source:
            raise ValidationError("WorkflowTransition.source vacio")
        if not self.outcome:
            raise ValidationError("WorkflowTransition.outcome vacio")
        if not self.target:
            raise ValidationError("WorkflowTransition.target vacio")


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    """Grafo de control de flujo ejecutable."""

    nodes: tuple[WorkflowNode, ...]
    initial: str
    transitions: tuple[WorkflowTransition, ...] = ()

    def __post_init__(self) -> None:
        names = {n.name for n in self.nodes}
        if not names:
            raise ValidationError("WorkflowPlan sin nodos")
        if not self.initial:
            raise ValidationError("WorkflowPlan.initial vacio")
        if self.initial not in names:
            raise ValidationError(f"WorkflowPlan.initial {self.initial!r} no es un nodo del plan")
        for t in self.transitions:
            if t.source not in names:
                raise ValidationError(f"WorkflowTransition.source {t.source!r} no es nodo")
            if t.target not in names:
                raise ValidationError(f"WorkflowTransition.target {t.target!r} no es nodo")
        # H4: validar que las transiciones usen outcomes declarados si el
        # nodo los declaro (DecisionNode o ActionNode con outcomes explicitos).
        by_name = {n.name: n for n in self.nodes}
        for t in self.transitions:
            src = by_name[t.source]
            if src.outcomes and t.outcome not in src.outcomes:
                raise ValidationError(
                    f"WorkflowTransition: outcome {t.outcome!r} no esta en "
                    f"outcomes declarados del nodo {src.name!r}={list(src.outcomes)!r}"
                )

    def successors(self, node_name: str, outcome: str) -> str | None:
        """Devuelve el siguiente nodo segun el outcome, o None si terminal."""
        for t in self.transitions:
            if t.source == node_name and t.outcome == outcome:
                return t.target
        return None

    def node(self, node_name: str) -> WorkflowNode:
        for n in self.nodes:
            if n.name == node_name:
                return n
        raise ValidationError(f"nodo no encontrado en plan: {node_name!r}")
