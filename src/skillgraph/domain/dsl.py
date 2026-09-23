"""DSL declarativo para construir WorkflowPlan (Etapa 2 / S7).

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md

Por que existe este modulo aparte de `plan_loader.py`:
- `plan_loader.py` parsea texto (Markdown + YAML).
- `dsl.py` ofrece un constructor tipado en Python para tests y
  para quien prefiera declarar el plan sin tocar Markdown.

Reglas de diseno (siguiendo las reglas de AGENTS.md):
- **Inmutabilidad**: todas las estructuras son `frozen=True`.
- **ADT sum-type**: NodeKind y Outcome son `Literal`/`NewType`
  reexportados desde `runtime_types` (no strings sueltos circulando
  por el codigo).
- **Funcional**: las operaciones de composicion devuelven NUEVOS
  PlanBuilders; nunca mutan el receptor.
- **Errores tipados**: las validaciones lanzan `ValidationError` /
  `ParseError` (no `ValueError` generico).
- **Sin I/O**: este modulo no toca disco ni red.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast, overload

from skillgraph.core.errors import ParseError, ValidationError
from skillgraph.core.runtime_types import (
    NODE_KINDS,
    NodeKind,
    NodeName,
    OutcomeLabel,
    RevisionNumber,
)
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

API_VERSION = "skillgraph.dev/v1alpha1"
"""Version del contrato de recursos en este vertical slice."""

__all__ = [
    "API_VERSION",
    "NODE_KINDS",
    "NodeKind",
    "NodeName",
    "OutcomeLabel",
    "PlanBuilder",
    "RevisionNumber",
    "node_name",
    "outcome",
    "revision",
]

# --- Constructores con ADT y validacion ------------------------------------


def node_name(s: str) -> NodeName:
    """Smart constructor: valida y devuelve `NodeName` tipado.

    Reglas: no vacio, comienza con letra, solo [a-zA-Z0-9-_].
    """
    import re

    if not s or not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", s):
        raise ValidationError(f"NodeName invalido: {s!r}")
    return NodeName(s)


def outcome(s: str) -> OutcomeLabel:
    """Smart constructor: valida y devuelve `OutcomeLabel` tipado."""
    if not s:
        raise ValidationError("OutcomeLabel vacio")
    return OutcomeLabel(s)


def _make_revision(n: int) -> RevisionNumber:
    if n < 1:
        raise ValidationError(f"RevisionNumber debe ser >= 1: {n}")
    return RevisionNumber(n)


# Alias publico (smart constructor).
revision = _make_revision
"""Smart constructor: valida y devuelve `RevisionNumber` tipado."""


# --- Builder funcional (inmutable) ----------------------------------------


class PlanBuilder:
    """Constructor incremental de un `WorkflowPlan`.

    Cada metodo (`add_node`, `link`, `starts_at`) devuelve un NUEVO
    `PlanBuilder` con el estado extendido. El receptor nunca muta.

    >>> p = (
    ...     PlanBuilder()
    ...     .add_node(node_name("a"), kind="ActionNode", expected="text")
    ...     .add_node(node_name("b"), kind="ActionNode", expected="text")
    ...     .link(node_name("a"), outcome("ok"), node_name("b"))
    ...     .starts_at(node_name("a"))
    ...     .build()
    ... )
    >>> p.initial == "a"
    True
    """

    __slots__ = ("_initial", "_nodes", "_transitions")

    def __init__(
        self,
        nodes: tuple[WorkflowNode, ...] = (),
        transitions: tuple[WorkflowTransition, ...] = (),
        initial: NodeName | None = None,
    ) -> None:
        self._nodes: tuple[WorkflowNode, ...] = nodes
        self._transitions: tuple[WorkflowTransition, ...] = transitions
        self._initial: NodeName | None = initial

    # ----- nodos -----

    @overload
    def add_node(
        self,
        name: NodeName,
        *,
        kind: NodeKind = "ActionNode",
        namespace: str = "shared",
        api_version: str = API_VERSION,
        revision: int = 1,
        expected: str,
        capabilities: Iterable[str] = (),
        metadata: dict[str, object] | None = None,
    ) -> PlanBuilder: ...
    def add_node(
        self,
        name: NodeName,
        *,
        kind: NodeKind = "ActionNode",
        namespace: str = "shared",
        api_version: str = API_VERSION,
        revision: int = 1,
        expected: str,
        capabilities: Iterable[str] = (),
        metadata: dict[str, object] | None = None,
    ) -> PlanBuilder:
        """Devuelve un NUEVO builder con el nodo aniadido.

        No muta el receptor. Si el `name` ya existe, lanza
        `ParseError` (duplicado en el plan).
        """
        if any(n.name == name for n in self._nodes):
            raise ParseError(f"nodo duplicado en plan: {name!r}")
        # Las anotaciones `NodeKind` ya restringen `kind` en tiempo de
        # type-check; aqui validamos en runtime para usuarios que
        # usen `cast` o `type: ignore`.
        if kind not in NODE_KINDS:
            raise ValidationError(f"NodeKind invalido: {kind!r}")
        rev = _make_revision(revision)
        node = WorkflowNode(
            name=name,
            kind=cast(NodeKind, kind),
            namespace=namespace,
            api_version=api_version,
            resource_revision=rev,
            expected_result=expected,
            capabilities=tuple(capabilities),
            metadata=dict(metadata) if metadata else {},
        )
        return PlanBuilder(
            nodes=(*self._nodes, node),
            transitions=self._transitions,
            initial=self._initial,
        )

    # ----- transiciones -----

    def link(
        self,
        source: NodeName,
        outcome_label: OutcomeLabel,
        target: NodeName,
    ) -> PlanBuilder:
        """Devuelve un NUEVO builder con la transicion aniadida."""
        # Las referencias a nodos se validan en `build()` cuando ya
        # no se pueden aniadir mas nodos; aqui solo acumulamos.
        t = WorkflowTransition(source=source, outcome=outcome_label, target=target)
        return PlanBuilder(
            nodes=self._nodes,
            transitions=(*self._transitions, t),
            initial=self._initial,
        )

    # ----- inicial -----

    def starts_at(self, name: NodeName) -> PlanBuilder:
        """Devuelve un NUEVO builder con `initial` fijado.

        Si ya estaba fijado, lanza `ParseError` para evitar
        ambiguedad silenciosa en la declaracion.
        """
        if self._initial is not None and self._initial != name:
            raise ParseError(
                f"PlanBuilder ya tiene initial={self._initial!r}; se intento fijar a {name!r}"
            )
        return PlanBuilder(
            nodes=self._nodes,
            transitions=self._transitions,
            initial=name,
        )

    # ----- finalizacion -----

    def build(self) -> WorkflowPlan:
        """Materializa un `WorkflowPlan` validado.

        La validacion la hace `WorkflowPlan.__post_init__`, que ya
        es estricta (initial presente, transiciones referencian
        nodos existentes, etc.).
        """
        if self._initial is None:
            raise ParseError(
                "PlanBuilder.build() sin starts_at(): todo plan debe declarar su nodo inicial"
            )
        return WorkflowPlan(
            nodes=self._nodes,
            transitions=self._transitions,
            initial=self._initial,
        )
