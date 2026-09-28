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

from skillgraph.core.errors import ValidationError
from skillgraph.core.runtime_types import NODE_KINDS, NodeKind

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
    """Lee el limite de visitas declarado, o None si no se declaro.

    `bool` se excluye a proposito: en Python `isinstance(True, int)` es
    True, asi que un chequeo ingenuo acepta un booleano como limite.
    Y como `True == 1`, el efecto no es un error visible sino un nodo
    que se queda con una sola visita sin que nadie lo haya pedido.
    Mismo motivo por el que `_matches` separa `bool` de `integer`.
    """
    raw = metadata.get(MAX_VISITS_KEY)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
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
        _validate_scalar_fields(self)
        _validate_metadata(self)
        _reconcile_from_metadata(self)


def _validate_scalar_fields(node: WorkflowNode) -> None:
    """Valida los campos escalares en orden fijo.

    El orden es parte del contrato observable: cuando varios campos son
    invalidos a la vez, el error que gana es el del primero de esta
    lista. Fijarlo en una tabla lo hace explicito en vez de accidental.
    """
    checks: tuple[tuple[str, bool, str], ...] = (
        ("name", bool(node.name), "WorkflowNode.name vacio"),
        ("kind", node.kind in NODE_KINDS, f"WorkflowNode.kind invalido: {node.kind!r}"),
        ("namespace", bool(node.namespace), "WorkflowNode.namespace vacio"),
        ("api_version", bool(node.api_version), "WorkflowNode.api_version vacio"),
        (
            "resource_revision",
            node.resource_revision >= 1,
            "WorkflowNode.resource_revision debe ser >= 1",
        ),
        (
            "expected_result",
            bool(node.expected_result),
            "WorkflowNode.expected_result vacio",
        ),
    )
    for _field, ok, message in checks:
        if not ok:
            raise ValidationError(message)


def _validate_metadata(node: WorkflowNode) -> None:
    if not isinstance(node.metadata, dict):
        raise ValidationError("WorkflowNode.metadata debe ser dict")


def _reconcile_from_metadata(node: WorkflowNode) -> None:
    """Proyecta `metadata` sobre los campos derivados de la instancia.

    `metadata` es la verdad: lo declarado ahi gana sobre el valor por
    defecto del dataclass. Un DecisionNode sin outcomes declarados es
    invalido; un ActionNode que los declara se respeta (degraded mode).
    """
    declared = _declared_outcomes(node.metadata)
    match node.kind:
        case "DecisionNode":
            if not declared:
                raise ValidationError("DecisionNode requiere metadata.outcomes (lista no vacia)")
            object.__setattr__(node, "outcomes", declared)
        case _:
            if declared:
                object.__setattr__(node, "outcomes", declared)
    mv = _declared_max_visits(node.metadata)
    if mv is not None:
        object.__setattr__(node, "max_visits", mv)


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
