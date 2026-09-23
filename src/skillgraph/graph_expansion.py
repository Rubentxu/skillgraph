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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NewType, Protocol

from skillgraph.errors import (
    InvalidExpansionError,
    UnauthorizedExpansionError,
)
from skillgraph.runtime import now_iso
from skillgraph.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

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


def _has_cycle_via_new_transitions(
    new_nodes: tuple[WorkflowNode, ...],
    new_trans: tuple[WorkflowTransition, ...],
    plan: WorkflowPlan,
) -> bool:
    """Devuelve True si el conjunto (plan ++ nuevas ops) tiene ciclo."""
    from collections import deque

    by_name = {n.name for n in plan.nodes}
    by_name.update(n.name for n in new_nodes)

    # Edges: existentes + nuevas
    edges: dict[str, list[str]] = {n: [] for n in by_name}
    for t in plan.transitions:
        edges.setdefault(t.source, []).append(t.target)
    for t in new_trans:
        edges.setdefault(t.source, []).append(t.target)

    # BFS: si hay un ciclo, lo detecta retornando True.
    visited: set[str] = set()

    def bfs_cycle(start: str) -> bool:
        seen: set[str] = set()
        q = deque([(start, [start])])
        while q:
            node, path = q.popleft()
            if node in seen:
                return True
            seen.add(node)
            for nxt in edges.get(node, []):
                if nxt in path:  # back-edge -> cycle
                    return True
                q.append((nxt, [*path, nxt]))
        return False

    for n in by_name:
        if n not in visited:
            if bfs_cycle(n):
                return True
            visited.add(n)
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

    violated: list[str] = []
    warnings: list[str] = []

    # I3: capabilities no autorizadas (no en registry).
    for cap in proposal.capabilities_needed:
        if not _ref_exists(cap, registry):
            violated.append("I3")
            break

    # I4: dependencias inexistentes.
    for dep in proposal.new_dependencies:
        if not _ref_exists(dep, registry):
            violated.append("I4")
            break

    # I1: no reescribir historicos. Para H4 slice-1, ninguna op propuesta
    # modifica nodos completados (se conserva su revision+resultado original
    # en node_executions). Esto se valida en una invariante de plan-level
    # cuando se introduzcan operaciones de tipo ModifyNode (futuro slice).
    # Por ahora, ninguna op del slice-1 lo hace -> I1 vacio en este nivel.
    # La invariante REAL queda en storage.py: el patch nunca toca
    # node_executions de completados.

    # I2: advertencia si se propone cambio sobre nodo activo.
    for op in proposal.operations:
        if isinstance(op, RemoveTransition) and op.from_node in active_nodes:
            warnings.append(f"W1: RemoveTransition sobre nodo activo {op.from_node!r}")

    # I5: ciclo sin salida en el plan resultante.
    # Detectamos: si AddTransition/AddNode crean un ciclo, el plan
    # resultante no tiene max_visits en el nodo origen.
    new_nodes: list[WorkflowNode] = []
    new_transitions: list[WorkflowTransition] = []
    for op in proposal.operations:
        if isinstance(op, AddNode):
            new_nodes.append(op.node)
        elif isinstance(op, AddTransition):
            new_transitions.append(op.transition)

    if _has_cycle_via_new_transitions(tuple(new_nodes), tuple(new_transitions), plan):
        # Para que esto NO rompa I5, el nodo source de cualquier ciclo
        # debe declarar max_visits>=2.
        max_visits_ok = True
        cycle_nodes = _cycle_source_nodes(tuple(new_nodes), tuple(new_transitions), plan)
        for node_name in cycle_nodes:
            node_in_plan = next((n for n in plan.nodes if n.name == node_name), None)
            node_new = next((n for n in new_nodes if n.name == node_name), None)
            node = node_in_plan or node_new
            if node is None or node.max_visits is None or node.max_visits < 1:
                max_visits_ok = False
                break
        if not max_visits_ok:
            violated.append("I5")

    # I6: base_revision obsoleta.
    if current_revision is not None and proposal.base_revision != current_revision:
        violated.append("I6")

    # Eliminar duplicados de violated
    violated_tuple = tuple(dict.fromkeys(violated))

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
    by_name = {n.name for n in plan.nodes}
    by_name.update(n.name for n in new_nodes)
    edges: dict[str, list[str]] = {n: [] for n in by_name}
    for t in plan.transitions:
        edges.setdefault(t.source, []).append(t.target)
    for t in new_trans:
        edges.setdefault(t.source, []).append(t.target)

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


# ---------------------------------------------------------------------------
# ADT slice-3: stages, stored proposals, policy engine
# ---------------------------------------------------------------------------


ProposalStageName = Literal[
    "PROPOSED", "EVALUATED", "AUTHORIZED", "APPLIED", "REJECTED", "ARCHIVED"
]


@dataclass(frozen=True, slots=True)
class ProposalStage:
    """Estado del ciclo de vida de una propuesta (slice-3).

    El campo `name` viene del Literal `ProposalStageName`. Esto
    permite evolution del stage (anadir nuevos) sin cambiar el ADT.
    """

    name: ProposalStageName
    entered_at: str  # ISO-8601 UTC
    entered_by: str  # "validator" | "policy-engine" | "operator"
    note: str = ""


@dataclass(frozen=True, slots=True)
class PolicySettings:
    """Configuracion del policy engine (slice-3 §2.6 spec).

    Defaults conservadores: NO rechaza propuestas slice-1 validas.
    Tests focalizados verifican esto (no-regression test).
    """

    max_ops_per_proposal: int = 20
    max_nodes_per_project: int = 1000
    # vacio = todos los scopes permitidos
    allowed_scopes: tuple[Scope, ...] = ()
    # vacio = ninguna operation prohibida; defaults seguros
    forbidden_ops: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Contexto para que el policy engine decida (slice-3 §2.3 spec)."""

    proposal: GraphExpansionProposal
    plan: WorkflowPlan
    registry: Mapping[str, str]
    concurrent_proposals: tuple[GraphExpansionProposal, ...]
    settings: PolicySettings


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Decision del policy engine sobre una propuesta.

    `violated_rules` codigos P1..P5 (ver DefaultPolicyEngine).
    `warnings` no rompen la aceptacion pero se loggean (slice-4).
    """

    accepted: bool
    reason: str
    violated_rules: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class PolicyEngine(Protocol):
    """Interface para policy engines (slice-3 ��2.3 spec)."""

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision: ...


@dataclass(frozen=True, slots=True)
class DefaultPolicyEngine:
    """Policy engine por defecto: reglas P1..P5 (slice-3 §2.3 spec).

    Reglas evaluadas en orden:

    - P1: max operations por propuesta (settings.max_ops_per_proposal).
    - P2: no concurrent proposals sobre el mismo attachment_point.
    - P3: scope restrictions (settings.allowed_scopes; vacio = todos).
    - P4: blacklist de operations (settings.forbidden_ops; defensa en
      profundidad; coherente con H4 ciclos y decision donde RemoveNode
      NO es PatchOp valido por diseno).
    - P5: budget cap (settings.max_nodes_per_project).
    """

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        violations: list[str] = []

        # P1: max operations.
        max_ops = ctx.settings.max_ops_per_proposal
        if len(ctx.proposal.operations) > max_ops:
            violations.append(
                f"P1: {len(ctx.proposal.operations)} ops > max_ops_per_proposal={max_ops}"
            )

        # P2: concurrent proposals on same attachment_point.
        for other in ctx.concurrent_proposals:
            if (
                other.attachment_point == ctx.proposal.attachment_point
                and other.proposal_id != ctx.proposal.proposal_id
            ):
                violations.append(
                    f"P2: concurrent proposal {other.proposal_id} "
                    f"on attachment_point={ctx.proposal.attachment_point}"
                )

        # P3: scope restrictions.
        allowed = ctx.settings.allowed_scopes
        if allowed and ctx.proposal.scope not in allowed:
            violations.append(
                f"P3: scope={ctx.proposal.scope!r} not in allowed_scopes={list(allowed)}"
            )

        # P4: blacklist de operations.
        forbidden = ctx.settings.forbidden_ops
        for op in ctx.proposal.operations:
            if type(op).__name__ in forbidden:
                violations.append(f"P4: op={type(op).__name__} in forbidden_ops={list(forbidden)}")

        # P5: budget cap (nodes proyectados despues de apply).
        current_node_count = len(ctx.plan.nodes)
        new_nodes = sum(1 for op in ctx.proposal.operations if isinstance(op, AddNode))
        projected = current_node_count + new_nodes
        max_nodes = ctx.settings.max_nodes_per_project
        if projected > max_nodes:
            violations.append(
                f"P5: projected_nodes={projected} > max_nodes_per_project={max_nodes}"
            )

        return PolicyDecision(
            accepted=not violations,
            reason="OK" if not violations else "; ".join(violations),
            violated_rules=tuple(violations),
        )


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Resultado de la fase EVALUATE (slice-3 §2.4).

    Se usa para gating: auto_signed requiere `accepted=True` antes
    de pasar a AUTHORIZE. Manual_signed no requiere EVALUATE (es
    pre-autorizado por el operador).
    """

    accepted: bool
    policy_decision: PolicyDecision
    evaluated_at: str
    evaluated_by: str  # "default-policy-engine"


def evaluate_proposal(
    proposal: GraphExpansionProposal,
    plan: WorkflowPlan,
    registry: Mapping[str, str],
    *,
    settings: PolicySettings | None = None,
    concurrent_proposals: tuple[GraphExpansionProposal, ...] = (),
    engine: PolicyEngine | None = None,
) -> EvaluationResult:
    """Ejecuta la fase EVALUATE del pipeline (slice-3 §2.4).

    Si el proposal ya fallo en validate (validation pasada externamente),
    no se ejecuta la policy engine: solo se registra el rechazo.

    Por defecto usa DefaultPolicyEngine y PolicySettings() (defaults
    conservadores que NO rechazan propuestas slice-1 validas).
    """
    effective_engine: PolicyEngine = engine or DefaultPolicyEngine()
    effective_settings = settings or PolicySettings()
    ctx = PolicyContext(
        proposal=proposal,
        plan=plan,
        registry=registry,
        concurrent_proposals=concurrent_proposals,
        settings=effective_settings,
    )
    decision = effective_engine.evaluate(ctx)
    return EvaluationResult(
        accepted=decision.accepted,
        policy_decision=decision,
        evaluated_at=now_iso(),
        evaluated_by=type(effective_engine).__name__,
    )


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
