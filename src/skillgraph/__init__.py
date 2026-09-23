"""SkillGraph: plataforma local-first para workflows declarativos de agentes.

API pública estable. La version se mantiene aquí y la consume hatchling
para construir el wheel (ver pyproject.toml [tool.hatch.version]).
"""

__version__ = "0.1.0.dev0"

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
