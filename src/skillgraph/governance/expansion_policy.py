"""Subsistema de policy de la expansion (WI-62, ADR-0021).

Reglas P1..P5, engine por defecto y evaluacion de propuestas
(slice-3 H4). Extraido verbatim de `graph_expansion.py`: el modulo
original conserva re-export runtime (`__all__` intacto).

Cero dependencia runtime de `graph_expansion`: las anotaciones van
bajo TYPE_CHECKING y P5 usa el nombre del tipo (alineado con P4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from skillgraph.runtime.engine import now_iso

if TYPE_CHECKING:
    from skillgraph.governance.graph_expansion import (
        GraphExpansionProposal,
        Scope,
        WorkflowPlan,
    )


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


def _check_p1_max_ops(ctx: PolicyContext) -> tuple[str, ...]:
    """P1: max operations por propuesta."""
    n_ops = len(ctx.proposal.operations)
    max_ops = ctx.settings.max_ops_per_proposal
    if n_ops > max_ops:
        return (f"P1: {n_ops} ops > max_ops_per_proposal={max_ops}",)
    return ()


def _check_p2_concurrency(ctx: PolicyContext) -> tuple[str, ...]:
    """P2: proposals concurrentes sobre el mismo attachment_point.

    Se excluye el propio proposal_id: uno no compite consigo mismo.
    """
    mine = ctx.proposal
    return tuple(
        f"P2: concurrent proposal {other.proposal_id} on attachment_point={mine.attachment_point}"
        for other in ctx.concurrent_proposals
        if other.attachment_point == mine.attachment_point and other.proposal_id != mine.proposal_id
    )


def _check_p3_scope(ctx: PolicyContext) -> tuple[str, ...]:
    """P3: scope restrictions. Allowlist vacia = todos los scopes."""
    allowed = ctx.settings.allowed_scopes
    if allowed and ctx.proposal.scope not in allowed:
        return (f"P3: scope={ctx.proposal.scope!r} not in allowed_scopes={list(allowed)}",)
    return ()


def _check_p4_forbidden_ops(ctx: PolicyContext) -> tuple[str, ...]:
    """P4: blacklist de operations. Una violacion por operacion."""
    forbidden = ctx.settings.forbidden_ops
    if not forbidden:
        return ()
    return tuple(
        f"P4: op={type(op).__name__} in forbidden_ops={list(forbidden)}"
        for op in ctx.proposal.operations
        if type(op).__name__ in forbidden
    )


def _check_p5_budget(ctx: PolicyContext) -> tuple[str, ...]:
    """P5: budget cap de nodos proyectados tras apply.

    Solo cuentan los AddNode: un AddTransition no anade nodo al plan.
    """
    projected = len(ctx.plan.nodes) + sum(
        1 for op in ctx.proposal.operations if type(op).__name__ == "AddNode"
    )
    max_nodes = ctx.settings.max_nodes_per_project
    if projected > max_nodes:
        return (f"P5: projected_nodes={projected} > max_nodes_per_project={max_nodes}",)
    return ()


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
        for rule in (
            _check_p1_max_ops,
            _check_p2_concurrency,
            _check_p3_scope,
            _check_p4_forbidden_ops,
            _check_p5_budget,
        ):
            violations.extend(rule(ctx))
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
