"""API pública del paquete (Etapa 0/1).

Mantener este módulo delgado: es el contrato estable entre
Etapa 0, 2, 3 y 5. Si crece, auditar duplicación.
"""

from skillgraph.bricks import Brick, ResourceIdentity
from skillgraph.errors import (
    IdentityConflictError,
    ParseError,
    SkillGraphError,
    UnknownKindError,
    ValidationError,
)
from skillgraph.parser import parse_file, parse_markdown
from skillgraph.registry import BrickRegistry, BrickType, load_defaults

__all__ = [
    "Brick",
    "BrickRegistry",
    "BrickType",
    "IdentityConflictError",
    "ParseError",
    "ResourceIdentity",
    "SkillGraphError",
    "UnknownKindError",
    "ValidationError",
    "load_defaults",
    "parse_file",
    "parse_markdown",
]
