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
