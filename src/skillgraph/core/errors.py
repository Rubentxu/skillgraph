"""Excepciones de dominio de SkillGraph.

La estrategia de tests exige mensajes accionables: cada error lleva un
código estable, el path del recurso y la regla violada.
"""

from __future__ import annotations


class SkillGraphError(Exception):
    """Raíz del árbol de excepciones del núcleo."""

    code: str = "sg_error"


class ValidationError(SkillGraphError):
    """Un recurso no cumple el contrato declarativo."""

    code = "sg_validation"


class ParseError(SkillGraphError):
    """Un recurso no pudo parsearse (front matter o YAML inválido)."""

    code = "sg_parse"


class UnknownKindError(ValidationError):
    """El `kind` del recurso no está registrado en el catálogo de tipos."""

    code = "sg_unknown_kind"


class IdentityConflictError(ValidationError):
    """Mismo (tenant, project, namespace, kind, name) ya registrado."""

    code = "sg_identity_conflict"


class IdempotencyError(SkillGraphError):
    """La operacion ya habia sido aplicada (UNIQUE sobre event_id)."""

    code = "sg_idempotency"


class NotFoundError(SkillGraphError):
    """Un recurso o fixture solicitada no existe."""

    code = "sg_not_found"


class OutcomeInvalidError(ValidationError):
    """El outcome del agente no esta declarado en el WorkflowPlan."""

    code = "sg_outcome_invalid"


class StateTransitionError(ValidationError):
    """Una transicion de estado no es legal."""

    code = "sg_state_transition"


class MaxIterationsExceeded(SkillGraphError):
    """El bucle de reconciliacion agoto el presupuesto de iteraciones."""

    code = "sg_max_iterations"


# --- H4 Slice 1: errores de expansion controlada -----------------------


class InvalidExpansionError(SkillGraphError):
    """Una propuesta de expansion controlada viola una invariante.

    Ver blueprint §5 §6 (literal). Las invariantes se codifican como
    ``I1..I6`` en el resultado de ``validate`` y en ``InvalidProposal``.
    """

    code = "sg_invalid_expansion"


class UnauthorizedExpansionError(SkillGraphError):
    """La propuesta no tiene una autorizacion explicita valida.

    El modo ``manual_signed`` requiere firmante + timestamp;
    ``policy_approved`` requiere timestamp; ``auto_low_risk`` se
    auto-aprueba por la naturaleza de las operaciones.
    """

    code = "sg_unauthorized_expansion"


# --- H3 Slice 1: errores del modelo de conocimiento -----------------------


class InvalidSourceIDError(ValidationError):
    """Un SourceID no cumple el formato esperado (vacio o no normalizado)."""

    code = "sg_invalid_source_id"


class InvalidEntityIDError(ValidationError):
    """Un EntityID no cumple el formato `kind:key`."""

    code = "sg_invalid_entity_id"


class InvalidSourceError(ValidationError):
    """Una instancia de Source no cumple sus invariantes (e.g. git_* sin SHA)."""

    code = "sg_invalid_source"


class UnknownClaimPredicateError(ValidationError):
    """El predicado de un Claim no esta registrado en CLAIM_PREDICATES."""

    code = "sg_unknown_predicate"


class SkillGraphWarning(UserWarning):
    """Raíz de los warnings no fatales de SkillGraph.

    NO rompe el flujo: el caller decide que hacer (log, abortar, continuar).
    Vive como `UserWarning` para que `warnings.warn()` la trate como warning
    estandar de Python (visible con `-W error::UserWarning` si se quiere
    estricto).
    """

    code: str = "sg_warning"


class UnknownSourceError(SkillGraphError):
    """Una Source solicitada por ID no existe."""

    code = "sg_unknown_source"


class UnknownEntityError(SkillGraphError):
    """Una Entity solicitada por ID no existe."""

    code = "sg_unknown_entity"


class UnknownClaimError(SkillGraphError):
    """Un Claim solicitado por ID no existe."""

    code = "sg_unknown_claim"


class StaleKnowledgeWarning(SkillGraphWarning):
    """Una operacion se completo pero el conocimiento involucrado esta stale.

    NO aborta: el controller ya registro los datos. El caller decide
    si abortar (`-W error::StaleKnowledgeWarning`) o continuar.
    """

    code = "sg_stale_knowledge"


class DulwichNotAvailableError(SkillGraphError):
    """Operacion Git solicitada pero `dulwich` no esta instalado.

    Se lanza desde `git_source.py` cuando el caller pide funcionalidad
    que requiere la dependencia opcional `skillgraph[git]` y el modulo
    no se puede importar.
    """

    code = "sg_dulwich_not_installed"


class CyclicDependencyError(SkillGraphError):
    """El traversal de dependencias encontro un ciclo.

    NO aborta la operacion global; aborta SOLO el traversal. El caller
    puede recibir este error si configura ciclos como no permisibles.
    """

    code = "sg_cyclic_dependency"


#: Subclase de Warning para reportar ciclos durante traversal.
#: Hereda de SkillGraphWarning para que el caller pueda usar
#: `warnings.filterwarnings("error::CyclicDependencyWarning", ...)`
#: si quiere tratar ciclos como fatales.
class CyclicDependencyWarning(SkillGraphWarning):
    """El traversal detecto un ciclo. Continua, NO aborta."""

    code = "sg_cyclic_dependency_warn"


class RefreshFailedError(SkillGraphError):
    """`refresh_source` no pudo reactivar ninguna Claim.

    Indica que la `new_revision` no aporta evidences compatibles con
    las Claims stale. NO aborta el flujo, pero el caller deberia
    registrar el incidente.
    """

    code = "sg_refresh_failed"


class HopLimitExceededWarning(SkillGraphWarning):
    """El traversal de dependencias alcanzo `max_hops` antes de agotar.

    NO fatal. El caller decide si continuar o re-intentar con mas hops
    (`-W error::HopLimitExceededWarning` lo convertiria en error).
    """

    code = "sg_hop_limit_exceeded"


class StaleKnowledgeError(SkillGraphError):
    """`compile_handoff` fallo porque habia Claims stale y policy=strict.

    NO aborta llamadas menos estrictas: el caller elige strict/best_effort
    en la receta.
    """

    code = "sg_stale_knowledge_error"


class MissingObligatoryError(SkillGraphError):
    """`compile_handoff` fallo porque un selector obligario no resolvio.

    El error message incluye el selector que fallo.
    """

    code = "sg_missing_obligatory"


class TokenBudgetExceededError(SkillGraphError):
    """`compile_handoff` fallo porque el conocimiento obligatorio no cabe
    en `token_budget` (con `overflow_strategy=fail`).
    """

    code = "sg_token_budget_exceeded"


class RecipeNotFoundError(SkillGraphError):
    """`recipe_ref` no corresponde a una receta registrada o cargable."""

    code = "sg_recipe_not_found"


# Public API surface for `from skillgraph.core.errors import *`.
# Mantener sincronizado con las clases definidas en este modulo.
__all__ = [
    "CyclicDependencyError",
    "CyclicDependencyWarning",
    "DulwichNotAvailableError",
    "HopLimitExceededWarning",
    "IdempotencyError",
    "IdentityConflictError",
    "InvalidEntityIDError",
    "InvalidExpansionError",
    "InvalidSourceError",
    "InvalidSourceIDError",
    "MaxIterationsExceeded",
    "MissingObligatoryError",
    "NotFoundError",
    "OutcomeInvalidError",
    "ParseError",
    "RecipeNotFoundError",
    "RefreshFailedError",
    "SkillGraphError",
    "SkillGraphWarning",
    "StaleKnowledgeError",
    "StaleKnowledgeWarning",
    "StateTransitionError",
    "TokenBudgetExceededError",
    "UnauthorizedExpansionError",
    "UnknownClaimError",
    "UnknownClaimPredicateError",
    "UnknownEntityError",
    "UnknownKindError",
    "UnknownSourceError",
    "ValidationError",
]
