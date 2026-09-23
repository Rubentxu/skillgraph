"""SkillGraph: plataforma local-first para workflows declarativos de agentes.

API pública estable. La version se mantiene aquí y la consume hatchling
para construir el wheel (ver pyproject.toml [tool.hatch.version]).

Tras el refactor por bounded contexts (v0.7.0), las APIs publicas viven
en subpaquetes:

- skillgraph.core: errores, tipos runtime, recipes.
- skillgraph.resources: parser, bricks, registry, catalog, plan_loader,
  workflow.
- skillgraph.domain: skill_importer, pack_loader, dsl.
- skillgraph.knowledge: knowledge, knowledge_controller,
  knowledge_invalidator, context_controller, git_source.
- skillgraph.runtime: engine, agent, handoff, runcontroller.
- skillgraph.governance: graph_expansion, promotion.
- skillgraph.platform: paths, storage.
- skillgraph.cli: runner (entry point CLI).

Los shims en la raiz ``skillgraph.X`` siguen disponibles para backward
compat con tests/external code, pero iran desapareciendo en futuras
versiones.
"""

__version__ = "0.7.0.dev0"

from skillgraph.core.errors import (
    IdentityConflictError,
    ParseError,
    SkillGraphError,
    UnknownKindError,
    ValidationError,
)
from skillgraph.core.recipe import ContextRecipe, ObligatorySelector
from skillgraph.core.runtime_types import (
    NodeKind,
    NodeName,
    NodeState,
    OutcomeLabel,
    RevisionNumber,
    RunState,
)
from skillgraph.resources.bricks import Brick, ResourceIdentity
from skillgraph.resources.parser import parse_file, parse_markdown
from skillgraph.resources.registry import BrickRegistry, BrickType, load_defaults
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

__all__ = [
    # Runtime types (case-sensitive ordering per ruff)
    "Brick",
    "BrickRegistry",
    "BrickType",
    "ContextRecipe",
    "IdentityConflictError",
    "NodeKind",
    "NodeName",
    "NodeState",
    "ObligatorySelector",
    "OutcomeLabel",
    "ParseError",
    "ResourceIdentity",
    "RevisionNumber",
    "RunState",
    "SkillGraphError",
    "UnknownKindError",
    "ValidationError",
    "WorkflowNode",
    "WorkflowPlan",
    "WorkflowTransition",
    "load_defaults",
    "parse_file",
    "parse_markdown",
]
