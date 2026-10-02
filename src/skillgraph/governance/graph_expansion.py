"""H4 Slice 1+3: Expansion controlada (DISCOVER -> APPLY -> EVALUATE).

Doc externo:
  specs/h4-slice-1.md (sub-spec firmado en este turno).
  specs/h4-slice-3.md (slice-3: policy engine + EVALUATE stage).
  external/blueprint-v1/plan/UAT.md UAT-08 (autorizada) + UAT-09 (rechazada).
  external/blueprint-v1/05-workflows-y-ciclo-de-vida.md §5 §6
  (pipeline + invariantes literales).

Pipeline legal (blueprint §5 §5):
  DISCOVER -> PROPOSE -> VALIDATE -> AUTHORIZE -> APPLY -> EXECUTE -> EVALUATE

Este modulo cubre: PROPOSE -> VALIDATE -> AUTHORIZE -> APPLY.
EVALUATE (slice-3) reordena: VALIDATE -> POLICY EVALUATE -> AUTHORIZE.

Invariantes blueprint §6 (codigos de violacion I1..I6):
  I1: No reescribir resultados historicos.
  I2: No alterar una instancia activa silenciosamente.
  I3: No adquirir capacidades no autorizadas.
  I4: No introducir referencias inexistentes.
  I5: No crear dependencias circulares sin salida (max_visits).
  I6: No incorporar cambios sobre una revision obsoleta.

Slice-3 anade policy engine (P1..P5) que se ejecuta entre VALIDATE
y AUTHORIZE. Defaults conservadores: no rechaza propuestas slice-1
validas (ver test `test_policy_engine_default_settings_allow_existing_proposals`).
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NewType

from skillgraph.core.errors import (
    InvalidExpansionError,
    UnauthorizedExpansionError,
)
from skillgraph.governance.expansion_policy import (
    DefaultPolicyEngine,
    EvaluationResult,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    PolicySettings,
    ProposalStage,
    ProposalStageName,
    evaluate_proposal,
)
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition
from skillgraph.runtime.engine import now_iso

ProposalID = NewType("ProposalID", str)
AuthorizationMode = Literal["manual_signed", "policy_approved", "auto_low_risk"]
Scope = Literal["NODE", "TRANSITION", "SUBGRAPH"]


# ---------------------------------------------------------------------------
# ADT: errores
# ---------------------------------------------------------------------------


class ExpansionOnObsoleteRevisionError(InvalidExpansionError):
    """I6: la base_revision declarada ya no es la actual del plan."""


@dataclass(frozen=True, slots=True)
class InvalidProposal:
    """Resultado de validacion fallida."""

    reason: str
    violated_invariants: tuple[str, ...]
    proposal_id: ProposalID

    def to_dict(self) -> dict[str, str | tuple[str, ...]]:
        return {
            "reason": self.reason,
            "violated_invariants": self.violated_invariants,
            "proposal_id": self.proposal_id,
        }


# Either-ish; resultado explicito sin Result type externo (sin mas deps).


@dataclass(frozen=True, slots=True)
class _Ok:
    value: WorkflowPlan


@dataclass(frozen=True, slots=True)
class _Err:
    error: InvalidProposal


@dataclass(frozen=True, slots=True)
class ExpansionResult:
    """Either-like de ``apply_expansion``."""

    _inner: _Ok | _Err

    def is_ok(self) -> bool:
        return isinstance(self._inner, _Ok)

    def is_err(self) -> bool:
        return isinstance(self._inner, _Err)

    def unwrap(self) -> WorkflowPlan:
        if isinstance(self._inner, _Ok):
            return self._inner.value
        raise RuntimeError(f"ExpansionResult.unwrap en Err: {self._inner.error.reason}")

    def unwrap_err(self) -> InvalidProposal:
        if isinstance(self._inner, _Err):
            return self._inner.error
        raise RuntimeError("ExpansionResult.unwrap_err en Ok")


# ---------------------------------------------------------------------------
# ADT: operaciones (PatchOp)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AddNode:
    """AddNode: agrega un nodo al plan (WorkflowPlan)."""

    node: WorkflowNode


@dataclass(frozen=True, slots=True)
class AddTransition:
    """AddTransition: agrega una WorkflowTransition al plan."""

    transition: WorkflowTransition


@dataclass(frozen=True, slots=True)
class RemoveTransition:
    """RemoveTransition: elimina transiciones (source, outcome)."""

    from_node: str
    outcome: str


# PatchOp es ADT cerrado: NO incluimos RemoveNode (preserva invariante I1).


# ---------------------------------------------------------------------------
# ADT: autorizacion
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Authorization:
    """Forma en que se aprobo esta propuesta.

    - ``manual_signed``: requiere firmante + timestamp humano.
    - ``policy_approved``: requiere timestamp (aprobado por policy engine).
    - ``auto_low_risk``: auto-aprobado por ser ops de bajo riesgo (add node
      aislado, sin tocar completados).
    """

    mode: AuthorizationMode
    granted_by: str | None = None
    granted_at: str | None = None

    def is_valid(self) -> bool:
        if self.mode == "manual_signed":
            return bool(self.granted_by) and bool(self.granted_at)
        if self.mode == "policy_approved":
            return bool(self.granted_at)
        return self.mode == "auto_low_risk"


# ---------------------------------------------------------------------------
# ADT: propuesta
# ---------------------------------------------------------------------------


def _make_proposal_id(
    *,
    base_revision: str,
    operations: tuple[object, ...],
    capabilities_needed: tuple[str, ...],
    attachment_point: str,
    author: str,
) -> ProposalID:
    """UUIDv5 estable sobre el contenido canonico de la propuesta.

    El mismo (base_revision, ops, capabilities, attachment_point, author)
    produce el mismo proposal_id. Si cambia cualquiera, cambia el id.
    """
    payload = json.dumps(
        {
            "rev": base_revision,
            "ops": [type(op).__name__ for op in operations],
            "caps": list(capabilities_needed),
            "at": attachment_point,
            "by": author,
        },
        sort_keys=True,
    )
    return ProposalID(f"prop-{uuid.uuid5(uuid.NAMESPACE_OID, payload).hex[:12]}")


@dataclass(frozen=True, slots=True)
class GraphExpansionProposal:
    """Una propuesta de cambio del plan bajo el pipeline blueprint §5 §5.

    La propuesta cumple los 9 campos obligatorios:
      1. problema_observado (problem_observed)
      2. evidencia (evidence)
      3. revision_base (base_revision)
      4. operaciones_minimas (operations)
      5. nuevas_dependencias (new_dependencies)
      6. capacidades_necesarias (capabilities_needed)
      7. alcance (scope)
      8. punto_incorporacion (attachment_point)
      9. condiciones_reversion (rollback_plan)

    + campos propios: id estable, created_at, author, authorization.
    """

    proposal_id: ProposalID
    base_revision: str
    problem_observed: str
    evidence: tuple[str, ...]
    operations: tuple[object, ...]  # PatchOp: AddNode | AddTransition | RemoveTransition
    new_dependencies: tuple[str, ...]
    capabilities_needed: tuple[str, ...]
    scope: Scope
    attachment_point: str
    rollback_plan: tuple[object, ...]
    authorization: Authorization
    created_at: str
    author: str


# ---------------------------------------------------------------------------
# ADT: resultado de validacion
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Resultado del validador (I1..I6)."""

    accepted: bool
    reason: str = ""
    violated_invariants: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Public API: propose / validate / apply_expansion / record_rejection
# ---------------------------------------------------------------------------


def _require_authorization(auth: Authorization) -> None:
    if not auth.is_valid():
        raise UnauthorizedExpansionError(
            f"Authorization invalida: mode={auth.mode!r} "
            f"granted_by={auth.granted_by!r} granted_at={auth.granted_at!r}"
        )


def _require_problem(problem: str) -> None:
    if not problem or not problem.strip():
        raise InvalidExpansionError("proposal.problem_observed vacio")


def _require_attachment(point: str, plan: WorkflowPlan) -> None:
    if point not in {n.name for n in plan.nodes}:
        raise InvalidExpansionError(f"attachment_point={point!r} no es un nodo del plan")


def propose(
    *,
    base_revision: str,
    problem_observed: str,
    evidence: tuple[str, ...],
    operations: tuple[object, ...],
    new_dependencies: tuple[str, ...] = (),
    capabilities_needed: tuple[str, ...] = (),
    scope: Scope = "NODE",
    attachment_point: str,
    rollback_plan: tuple[object, ...] = (),
    authorization: Authorization,
    author: str,
) -> GraphExpansionProposal:
    """Crea una propuesta validando requisitos minimos (autorizacion + 9 campos)."""
    _require_authorization(authorization)
    _require_problem(problem_observed)
    if not operations:
        raise InvalidExpansionError("proposal.operations vacio")
    if not author:
        raise InvalidExpansionError("proposal.author vacio")

    proposal_id = _make_proposal_id(
        base_revision=base_revision,
        operations=operations,
        capabilities_needed=capabilities_needed,
        attachment_point=attachment_point,
        author=author,
    )
    return GraphExpansionProposal(
        proposal_id=proposal_id,
        base_revision=base_revision,
        problem_observed=problem_observed,
        evidence=evidence,
        operations=operations,
        new_dependencies=new_dependencies,
        capabilities_needed=capabilities_needed,
        scope=scope,
        attachment_point=attachment_point,
        rollback_plan=rollback_plan,
        authorization=authorization,
        created_at=now_iso(),
        author=author,
    )


def _find_capable(plan: WorkflowPlan, capability: str) -> bool:
    """Una capability es 'autorizada' si algun nodo del plan la declara."""
    return any(capability in n.capabilities for n in plan.nodes)


def _ref_exists(ref: str, registry: Mapping[str, str]) -> bool:
    return ref in registry


def _check_capabilities(
    proposal: GraphExpansionProposal,
    registry: Mapping[str, str],
) -> tuple[str, ...]:
    """I3+I4: caps/deps no en registry. Una entrada por invariant violada."""
    violated: list[str] = []
    if any(not _ref_exists(cap, registry) for cap in proposal.capabilities_needed):
        violated.append("I3")
    if any(not _ref_exists(dep, registry) for dep in proposal.new_dependencies):
        violated.append("I4")
    return tuple(violated)


def _active_remove_warnings(
    proposal: GraphExpansionProposal,
    active_nodes: frozenset[str],
) -> tuple[str, ...]:
    """W1: RemoveTransition sobre nodo activo."""
    if not active_nodes:
        return ()
    msgs: list[str] = []
    for op in proposal.operations:
        if isinstance(op, RemoveTransition) and op.from_node in active_nodes:
            msgs.append(f"W1: RemoveTransition sobre nodo activo {op.from_node!r}")
    return tuple(msgs)


def _check_cycle_bound(
    proposal: GraphExpansionProposal,
    plan: WorkflowPlan,
) -> tuple[str, ...]:
    """I5: AddNode/AddTransition crean ciclo sin salida (max_visits<1).

    Devuelve ("I5",) si se rompe la invariante; () si no hay ciclo o
    el plan declara max_visits adecuado en los nodos origen del ciclo.
    """
    new_nodes, new_trans = _split_new_ops(proposal)
    if not _has_cycle_via_new_transitions(new_nodes, new_trans, plan):
        return ()
    cycle_nodes = _cycle_source_nodes(new_nodes, new_trans, plan)
    if any(_node_without_bound(plan.nodes, new_nodes, name) for name in cycle_nodes):
        return ("I5",)
    return ()


def _split_new_ops(
    proposal: GraphExpansionProposal,
) -> tuple[tuple[WorkflowNode, ...], tuple[WorkflowTransition, ...]]:
    """Separa las operaciones de la propuesta en nodos y transiciones."""
    nodes: list[WorkflowNode] = []
    trans: list[WorkflowTransition] = []
    for op in proposal.operations:
        if isinstance(op, AddNode):
            nodes.append(op.node)
        elif isinstance(op, AddTransition):
            trans.append(op.transition)
    return tuple(nodes), tuple(trans)


def _node_without_bound(
    plan_nodes: tuple[WorkflowNode, ...],
    new_nodes: tuple[WorkflowNode, ...],
    name: str,
) -> bool:
    """True si el nodo `name` no declara max_visits utilizable.

    Un nodo del plan manda sobre uno nuevo con el mismo nombre: la
    propuesta no puede debilitar una declaracion ya existente.
    Declarar max_visits en solo uno de los dos extremos del ciclo no
    basta, por eso esto se consulta por nodo y no por ciclo.
    """
    node = next((n for n in plan_nodes if n.name == name), None)
    node = node or next((n for n in new_nodes if n.name == name), None)
    return node is None or node.max_visits is None or node.max_visits < 1


def _edge_map(
    new_nodes: tuple[WorkflowNode, ...],
    new_trans: tuple[WorkflowTransition, ...],
    plan: WorkflowPlan,
) -> dict[str, list[str]]:
    """Mapa de adyacencia del grafo resultante: `plan` ++ `new_*`.

    Vive en un solo sitio a proposito. Las dos funciones que analizan
    ciclos necesitan exactamente el mismo grafo, y con el armado
    duplicado en ambas cualquier cambio en la forma de las aristas
    podia dejar a la otra mirando un grafo distinto sin que ningun
    test lo notara.
    """
    by_name = {n.name for n in plan.nodes}
    by_name.update(n.name for n in new_nodes)
    edges: dict[str, list[str]] = {n: [] for n in by_name}
    for t in (*plan.transitions, *new_trans):
        edges.setdefault(t.source, []).append(t.target)
    return edges


def _has_cycle_via_new_transitions(
    new_nodes: tuple[WorkflowNode, ...],
    new_trans: tuple[WorkflowTransition, ...],
    plan: WorkflowPlan,
) -> bool:
    """Devuelve True si el conjunto (plan ++ nuevas ops) tiene ciclo."""
    edges = _edge_map(new_nodes, new_trans, plan)
    return any(_bfs_from(start, edges) for start in edges)


def _bfs_from(start: str, edges: Mapping[str, list[str]]) -> bool:
    """Recorre en anchura desde `start`; True si vuelve a un nodo ya visto.

    El back-edge se detecta de dos formas, ambas necesarias: `seen`
    captura el reencuentro por un camino distinto y `path` captura el
    back-edge directo del ciclo actual.
    """
    seen: set[str] = set()
    queue = deque([(start, (start,))])
    while queue:
        node, path = queue.popleft()
        if node in seen:
            return True
        seen.add(node)
        for nxt in edges.get(node, ()):
            if nxt in path:
                return True
            queue.append((nxt, (*path, nxt)))
    return False


def validate(
    proposal: GraphExpansionProposal,
    *,
    plan: WorkflowPlan,
    registry: Mapping[str, str],
    completed_nodes: frozenset[str] = frozenset(),
    active_nodes: frozenset[str] = frozenset(),
    current_revision: str | None = None,
) -> ValidationResult:
    """Valida la propuesta contra las 6 invariantes de blueprint §6."""
    _require_attachment(proposal.attachment_point, plan)

    # Componer violations y warnings delegando en helpers puros.
    # I3+I4: capabilities / dependencias no autorizadas.
    violations: list[str] = list(_check_capabilities(proposal, registry))

    # I2: warnings por RemoveTransition sobre nodo activo.
    warnings: list[str] = list(_active_remove_warnings(proposal, active_nodes))

    # I5: ciclo sin salida en el plan resultante.
    violations.extend(_check_cycle_bound(proposal, plan))

    # I6: base_revision obsoleta.
    if current_revision is not None and proposal.base_revision != current_revision:
        violations.append("I6")

    # I1 vacio en este nivel (delegado a storage.py: patch no toca
    # node_executions de completados; ver comment de slice-1/blueprint).

    # Eliminar duplicados preservando orden
    violated_tuple = tuple(dict.fromkeys(violations))

    if violated_tuple:
        reason = "; ".join(f"{code} violated" for code in violated_tuple)
        return ValidationResult(
            accepted=False,
            reason=reason,
            violated_invariants=violated_tuple,
            warnings=tuple(warnings),
        )

    return ValidationResult(
        accepted=True,
        warnings=tuple(warnings),
    )


def _cycle_source_nodes(
    new_nodes: tuple[WorkflowNode, ...],
    new_trans: tuple[WorkflowTransition, ...],
    plan: WorkflowPlan,
) -> tuple[str, ...]:
    """Devuelve los nombres de nodos origen de cualquier ciclo nuevo."""
    edges = _edge_map(new_nodes, new_trans, plan)

    # Encuentra los nodos que son fuente o objetivo de un back-edge.
    in_cycle: set[str] = set()
    for src, targets in edges.items():
        for tgt in targets:
            if tgt in edges and src in edges[tgt]:
                in_cycle.add(src)
                in_cycle.add(tgt)
    return tuple(in_cycle)


def apply_expansion(
    proposal: GraphExpansionProposal,
    plan: WorkflowPlan,
    *,
    registry: Mapping[str, str],
    completed_nodes: frozenset[str] = frozenset(),
    active_nodes: frozenset[str] = frozenset(),
    current_revision: str | None = None,
) -> ExpansionResult:
    """Aplica una propuesta y devuelve un plan NUEVO.

    NO muta ``plan``. Si la validacion falla, devuelve ``ExpansionResult``
    con error tipado en ``unwrap_err()``.
    """
    result = validate(
        proposal,
        plan=plan,
        registry=registry,
        completed_nodes=completed_nodes,
        active_nodes=active_nodes,
        current_revision=current_revision,
    )
    if not result.accepted:
        err = InvalidProposal(
            reason=result.reason,
            violated_invariants=result.violated_invariants,
            proposal_id=proposal.proposal_id,
        )
        return ExpansionResult(_Err(error=err))

    # Construir el nuevo plan (inmutablemente).
    new_nodes: list[WorkflowNode] = list(plan.nodes)
    new_transitions: list[WorkflowTransition] = list(plan.transitions)

    for op in proposal.operations:
        if isinstance(op, AddNode):
            new_nodes.append(op.node)
        elif isinstance(op, AddTransition):
            new_transitions.append(op.transition)
        elif isinstance(op, RemoveTransition):
            new_transitions = [
                t
                for t in new_transitions
                if not (t.source == op.from_node and t.outcome == op.outcome)
            ]

    # Construir plan nuevo; WorkflowPlan.__post_init__ valida integridad.
    try:
        new_plan = WorkflowPlan(
            nodes=tuple(new_nodes),
            initial=plan.initial,
            transitions=tuple(new_transitions),
        )
    except Exception as e:
        # Conversion inmediata a error de dominio tipado: lo que salga
        # de construir el WorkflowPlan (TypeError por una arista
        # mal formada, ValidationError de una invariante) se reporta
        # como InvalidProposal, que es el contrato de esta funcion.
        # El mensaje original se conserva en `reason` para no perder
        # el detalle. La exception no escapa nunca.
        err = InvalidProposal(
            reason=f"WorkflowPlan integrity check failed: {e}",
            violated_invariants=("I0",),
            proposal_id=proposal.proposal_id,
        )
        return ExpansionResult(_Err(error=err))

    return ExpansionResult(_Ok(value=new_plan))


def record_rejection(
    proposal: GraphExpansionProposal,
    *,
    reason: str,
    rejected_by: str,
    project_dir: Path,
    violated_invariants: tuple[str, ...] = (),
) -> Path:
    """Persiste evidencia de rechazo (UAT-09).

    Crea un archivo ``expansion_rejections/<proposal_id>.json`` dentro
    del directorio del proyecto. Devuelve la ruta del archivo.

    ``violated_invariants`` es opcional: si la rechazo viene del
    validador (I1..I6), se persiste para audit. Los rechazos por
    autorizacion (I0) o por error de carga no llevan invariantes.
    """
    target_dir = project_dir / "expansion_rejections"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{proposal.proposal_id}.json"
    payload = {
        "proposal_id": proposal.proposal_id,
        "author": proposal.author,
        "created_at": proposal.created_at,
        "problem_observed": proposal.problem_observed,
        "operations_count": len(proposal.operations),
        "capabilities_needed": list(proposal.capabilities_needed),
        "new_dependencies": list(proposal.new_dependencies),
        "attachment_point": proposal.attachment_point,
        "authorization_mode": proposal.authorization.mode,
        "rejected_by": rejected_by,
        "rejected_at": now_iso(),
        "reason": reason,
        "violated_invariants": list(violated_invariants),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return target


__all__ = [
    "AddNode",
    "AddTransition",
    "Authorization",
    "AuthorizationMode",
    "DefaultPolicyEngine",
    "EvaluationResult",
    "ExpansionResult",
    "GraphExpansionProposal",
    "InvalidProposal",
    "PolicyContext",
    "PolicyDecision",
    "PolicyEngine",
    "PolicySettings",
    "ProposalID",
    "ProposalStage",
    "ProposalStageName",
    "RemoveTransition",
    "Scope",
    "ValidationResult",
    "apply_expansion",
    "evaluate_proposal",
    "propose",
    "record_rejection",
    "validate",
]
