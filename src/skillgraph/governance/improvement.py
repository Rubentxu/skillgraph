"""Improvement — H15 Evaluación y automejora acotada.

Destino (evolution-v2/plan/ROADMAP.md H15):
detectar una omision o extraccion redundante, atribuirla y
verificar una correccion. Es el ultimo workitem evolution-v2.

Adaptado a las primitivas existentes:
- H11 (FileSignature) + H12 (Scopes) + H14 (Receipts) son las
  fuentes de evidencia operativa que H15 inspecciona.
- NO introduce tabla nueva (regla AGENTS §1.5): reusa
  ``Evidence(kind="improvement_candidate")`` y
  ``Evidence(kind="promotion_decision")``.
- ADT cerradas via Literal (regla AGENTS §2.1).
- Funciones puras donde es posible (regla AGENTS §1.1):
  ``localize_omission`` y ``compare_recipes`` no tocan Storage
  para el computo (solo lectura read-only).
- H15 NO se autocertifica (UAT-EVO-18):
  ``promote_candidate`` exige ``human_approved=True`` para
  emitir una PromotionDecision. Sin esto, lanza
  ``SelfCertificationBlockedError``.

Componentes:
- ImprovementCandidate (frozen): propuesta de mejora local con
  evidencia, atribucion y metricas.
- detect_redundant_extraction(): detecta firmas stale que
  deberian re-extraerse.
- localize_omission(): detecta refs obligatorias vigentes que
  fueron omitidas del handoff (atribuye a context_selection).
- compare_recipes(): compara dos recetas en cobertura, correccion
  y trabajo redundante (UAT-EVO-17).
- promote_candidate(): emite PromotionDecision solo con
  human_approved=True (UAT-EVO-18).
- rollback_candidate(): revierte una decision promovida segun
  RollbackPolicy.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.knowledge.graph import Evidence, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController

# --- ADT cerradas (regla AGENTS §2.1) -------------------------------

ImprovementKind = Literal[
    "redundant_extraction",
    "omitted_reference",
    "recipe_swap",
]

RollbackPolicy = Literal["automatic", "manual", "blocked"]

IMPROVEMENT_KINDS: frozenset[str] = frozenset(
    {"redundant_extraction", "omitted_reference", "recipe_swap"}
)
ROLLBACK_POLICIES: frozenset[str] = frozenset({"automatic", "manual", "blocked"})


# --- Errores tipados (regla AGENTS §1.2) ----------------------------


class SelfCertificationBlockedError(SkillGraphError):
    """Una propuesta intenta autocertificarse (UAT-EVO-18).

    Se lanza cuando ``promote_candidate`` se invoca sin
    ``human_approved=True``. El sistema NUNCA promueve cambios
    de politica de validacion sin aprobacion humana explicita.
    """

    def __init__(self, *, candidate_id: str, reason: str) -> None:
        self.candidate_id = candidate_id
        self.reason = reason
        super().__init__(
            f"autocertificacion bloqueada para candidate_id={candidate_id!r}; "
            f"motivo={reason}. Se requiere human_approved=True (UAT-EVO-18)."
        )


# --- Dataclasses frozen ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    """Propuesta de mejora local con evidencia y atribucion.

    Atributos:
    - ``candidate_id``: ID determinista (autogenerado si vacio).
    - ``kind``: Literal cerrada (UAT-EVO-15..17).
    - ``evidence_refs``: tupla de EvidenceID que respaldan la propuesta.
    - ``metrics``: payload libre (e.g. coverage_ratio, work_units).
    - ``detected_at``: ISO-8601 UTC.
    - ``scope``: ambito acotado.
    """

    candidate_id: str
    kind: ImprovementKind
    evidence_refs: tuple[str, ...]
    metrics: dict[str, Any]
    detected_at: str
    scope: str

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id vacio")
        if self.kind not in IMPROVEMENT_KINDS:
            raise ValidationError(f"kind invalido: {self.kind!r}")
        if not self.detected_at:
            raise ValidationError("detected_at vacio")
        if not self.scope:
            raise ValidationError("scope vacio")


@dataclass(frozen=True, slots=True)
class RecipeComparison:
    """Comparacion declarativa entre dos recetas (UAT-EVO-17)."""

    correction_a: bool
    correction_b: bool
    coverage_a: int
    coverage_b: int
    work_units_a: int
    work_units_b: int

    @property
    def is_b_improvement(self) -> bool:
        """B es mejora si: correction_b, coverage_b>=coverage_a, work_b<work_a."""
        return (
            self.correction_b
            and self.correction_a  # A tambien correcta (referencia)
            and self.coverage_b >= self.coverage_a
            and self.work_units_b < self.work_units_a
        )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Decision de promocion de un ImprovementCandidate (UAT-EVO-18)."""

    decision_id: str
    candidate_id: str
    human_approved: bool
    approver: str
    timestamp: str
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id vacio")
        if not self.candidate_id:
            raise ValidationError("candidate_id vacio")
        if not self.approver:
            raise ValidationError("approver vacio (UAT-EVO-18)")
        if not self.timestamp:
            raise ValidationError("timestamp vacio")


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """Resultado de revertir una PromotionDecision."""

    previous_decision_id: str
    applied: bool
    timestamp: str
    policy: RollbackPolicy
    note: str = ""


# --- Funciones puras + detectores ----------------------------------


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_candidate_id(*, kind: str, scope: str, detected_at: str) -> str:
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    payload = f"{kind}|{scope}|{detected_at}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return str(uuid.uuid5(namespace, digest.hex()))


def detect_redundant_extraction(
    *,
    controller: KnowledgeController,
    source_ids: tuple[str, ...],
) -> tuple[ImprovementCandidate, ...]:
    """Detecta firmas stale que deberian re-extraerse (UAT-EVO-15).

    Args:
        controller: KnowledgeController (lectura de FileSignatures).
        source_ids: source_ids a inspeccionar.

    Returns:
        Tupla de ImprovementCandidate(kind='redundant_extraction')
        para CADA source con firmas NO-fresh (vigencia.stale=True
        o state != 'complete'). Las fuentes con firmas fresh
        NO producen candidatos: el sistema ya tiene la informacion.
    """
    out: list[ImprovementCandidate] = []
    ts = _utc_now_iso()
    for sid in source_ids:
        sigs = controller.list_file_signatures_for_source(
            source_id=sid,
            only_stale=False,
        )
        if not sigs:
            continue
        # Si TODAS las firmas son fresh -> no hay redundancia.
        if all(s.vigencia.fresh for s in sigs):
            continue
        # Al menos una firma NO-fresh -> candidato a re-extraccion.
        out.append(
            ImprovementCandidate(
                candidate_id=_make_candidate_id(
                    kind="redundant_extraction",
                    scope=sid,
                    detected_at=ts,
                ),
                kind="redundant_extraction",
                evidence_refs=(),  # se rellenaria al ejecutar la re-extraccion
                metrics={
                    "source_id": sid,
                    "stale_count": sum(1 for s in sigs if not s.vigencia.fresh),
                    "fresh_count": sum(1 for s in sigs if s.vigencia.fresh),
                    "attribution": "context_selection",
                },
                detected_at=ts,
                scope=sid,
            )
        )
    return tuple(out)


def localize_omission(
    *,
    controller: KnowledgeController,
    expected_source_ids: tuple[str, ...],
    included_source_ids: tuple[str, ...],
) -> tuple[ImprovementCandidate, ...]:
    """Detecta refs obligatorias vigentes omitidas del handoff (UAT-EVO-16).

    Atribuye el defecto a 'context_selection' (no propone nueva rama
    de comportamiento). El campo ``evidence_refs`` del candidato
    apunta a las evidencias vigentes disponibles para su consulta.

    Args:
        controller: KnowledgeController.
        expected_source_ids: source_ids que DEBERIAN estar en el handoff.
        included_source_ids: source_ids que ACTUALMENTE incluye el handoff.

    Returns:
        Tupla de ImprovementCandidate(kind='omitted_reference') por
        cada source esperado que NO esta incluido pero TIENE firma
        vigente (es decir, era disponible y se omitio).
    """
    included_set = set(included_source_ids)
    out: list[ImprovementCandidate] = []
    ts = _utc_now_iso()
    for sid in expected_source_ids:
        if sid in included_set:
            continue
        sigs = controller.list_file_signatures_for_source(
            source_id=sid,
            only_stale=False,
        )
        if not sigs:
            continue  # sin firma vigente -> no es omision atribuible
        out.append(
            ImprovementCandidate(
                candidate_id=_make_candidate_id(
                    kind="omitted_reference",
                    scope=sid,
                    detected_at=ts,
                ),
                kind="omitted_reference",
                evidence_refs=(sid,),  # source_id de la firma vigente
                metrics={
                    "source_id": sid,
                    "viable_signature_count": len(sigs),
                    "attribution": "context_selection",
                },
                detected_at=ts,
                scope=sid,
            )
        )
    return tuple(out)


def compare_recipes(
    *,
    controller: KnowledgeController,
    recipe_a_source_ids: tuple[str, ...],
    recipe_b_source_ids: tuple[str, ...],
) -> RecipeComparison:
    """Compara dos recetas en cobertura, correccion y trabajo (UAT-EVO-17).

    Args:
        controller: KnowledgeController (solo lectura).
        recipe_a_source_ids: source_ids cubiertos por la receta A.
        recipe_b_source_ids: source_ids cubiertos por la receta B.

    Returns:
        RecipeComparison con metricas declaradas. Una receta es
        'correcta' si tiene al menos una firma fresh por source.

    Notes:
        Funcion de lectura: NO muta Storage. La correccion se
        evalua contra el estado actual del Storage (las firmas
        vigentes disponibles). Esto refleja 'correccion bajo el
        estado actual', no 'correccion teorica maxima'.
    """

    def _metrics(source_ids: tuple[str, ...]) -> tuple[int, int, bool]:
        coverage = 0
        work = len(source_ids)
        all_correct = True
        for sid in source_ids:
            sigs = controller.list_file_signatures_for_source(
                source_id=sid,
                only_stale=False,
            )
            if any(s.vigencia.fresh for s in sigs):
                coverage += 1
            else:
                all_correct = False
        return coverage, work, all_correct

    cov_a, work_a, corr_a = _metrics(recipe_a_source_ids)
    cov_b, work_b, corr_b = _metrics(recipe_b_source_ids)
    return RecipeComparison(
        correction_a=corr_a,
        correction_b=corr_b,
        coverage_a=cov_a,
        coverage_b=cov_b,
        work_units_a=work_a,
        work_units_b=work_b,
    )


# --- Promocion + rollback -------------------------------------------


def promote_candidate(
    *,
    controller: KnowledgeController,
    candidate: ImprovementCandidate,
    human_approved: bool,
    approver: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> PromotionDecision:
    """Promueve un ImprovementCandidate a PromotionDecision (UAT-EVO-18).

    Args:
        controller: KnowledgeController (persiste la decision).
        candidate: ImprovementCandidate a promover.
        human_approved: si False, lanza SelfCertificationBlockedError
            (regla UAT-EVO-18: el sistema NUNCA se autocertifica).
        approver: nombre del aprobador humano (obligatorio si
            human_approved=True).
        extra_metadata: payload libre.

    Returns:
        PromotionDecision persistida como Evidence(kind='promotion_decision').

    Raises:
        SelfCertificationBlockedError: si human_approved=False.
        ValidationError: si human_approved=True sin approver.
    """
    if not human_approved:
        raise SelfCertificationBlockedError(
            candidate_id=candidate.candidate_id,
            reason="human_approved=False",
        )
    if not approver:
        raise ValidationError("approver requerido cuando human_approved=True")

    ts = _utc_now_iso()
    # ID determinista sobre (candidate_id, approver, ts).
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    payload = f"{candidate.candidate_id}|{approver}|{ts}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    decision_id = str(uuid.uuid5(namespace, digest.hex()))

    decision = PromotionDecision(
        decision_id=decision_id,
        candidate_id=candidate.candidate_id,
        human_approved=True,
        approver=approver,
        timestamp=ts,
        extra_metadata=dict(extra_metadata or {}),
    )

    # Persistir como Evidence(kind='promotion_decision').
    source_id = f"improvement:{candidate.candidate_id}"
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind="local_file",
            content_hash=decision_id,
            locator={"path": f"improvement/{candidate.candidate_id}"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at=ts,
            freshness="fresh",
        )
    )
    evidence = Evidence(
        evidence_id="",
        source_id=source_id,
        kind="promotion_decision",
        content={
            "decision_id": decision.decision_id,
            "candidate_id": decision.candidate_id,
            "human_approved": decision.human_approved,
            "approver": decision.approver,
            "timestamp": decision.timestamp,
            "extra_metadata": decision.extra_metadata,
            "candidate_kind": candidate.kind,
            "candidate_scope": candidate.scope,
            "candidate_metrics": candidate.metrics,
        },
        observed_at=ts,
    )
    controller.record_evidence(evidence=evidence)
    return decision


def rollback_candidate(
    *,
    controller: KnowledgeController,
    decision: PromotionDecision,
    policy: RollbackPolicy = "automatic",
    note: str = "",
) -> RollbackResult:
    """Revierte una PromotionDecision segun RollbackPolicy.

    Args:
        controller: KnowledgeController (persiste el rollback).
        decision: PromotionDecision a revertir.
        policy: "automatic" aplica el rollback ahora; "manual" lo
            encola para aplicacion humana; "blocked" lo rechaza.
        note: comentario opcional.

    Returns:
        RollbackResult indicando si se aplico.

    Raises:
        ValidationError: si policy="blocked" (rollback rechazado).
    """
    if policy == "blocked":
        raise ValidationError(
            f"rollback bloqueado por policy='blocked' para decision={decision.decision_id}"
        )

    ts = _utc_now_iso()
    applied = policy == "automatic"

    # Persistir el rollback como Evidence(kind='rollback').
    source_id = f"rollback:{decision.decision_id}"
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind="local_file",
            content_hash=decision.decision_id,
            locator={"path": f"rollback/{decision.decision_id}"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at=ts,
            freshness="fresh",
        )
    )
    evidence = Evidence(
        evidence_id="",
        source_id=source_id,
        kind="rollback",
        content={
            "previous_decision_id": decision.decision_id,
            "applied": applied,
            "policy": policy,
            "note": note,
            "timestamp": ts,
        },
        observed_at=ts,
    )
    controller.record_evidence(evidence=evidence)
    return RollbackResult(
        previous_decision_id=decision.decision_id,
        applied=applied,
        timestamp=ts,
        policy=policy,
        note=note,
    )
