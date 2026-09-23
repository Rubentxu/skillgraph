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
