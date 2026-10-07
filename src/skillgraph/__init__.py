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
  knowledge_invalidator, context_controller, git_source,
  file_signature (H11), file_scope (H12), file_handoff (H13).
- skillgraph.runtime: engine, agent, handoff, runcontroller.
- skillgraph.governance: graph_expansion, promotion,
  receipts (H14), improvement (H15).
- skillgraph.platform: paths, storage.
- skillgraph.cli: runner (entry point CLI).

Los shims en la raiz ``skillgraph.X`` siguen disponibles para backward
compat con tests/external code, pero iran desapareciendo en futuras
versiones.
"""

__version__ = "0.42.2.dev0"  # v0.42.2 esta etiquetada y este commit es el que SELLA SU SHA, luego HEAD queda despues de la etiqueta: caso 2 de test_version_matches_git_tag. El sha se escribe ahora y no antes porque test_every_listed_sha_matches_its_tag lo contrasta contra `git rev-list -n1 v0.42.2`, y escrito antes guardaria el commit ANTERIOR. # PATCH derivado con scripts/derive_semver.py sobre v0.42.1..HEAD: b/f/x/n/d 0/0/1/4/0. Cero `feat` es lo que hace correcto el PATCH: B37 no anade superficie, cambia lo que el hook DICE.  # v0.42.1 esta etiquetada y este commit es el que SELLA SU SHA, luego HEAD queda despues de la etiqueta: caso 2 de test_version_matches_git_tag. El sha se escribe ahora y no antes porque test_every_listed_sha_matches_its_tag lo contrasta contra `git rev-list -n1 v0.42.1`, y escrito antes guardaria el commit ANTERIOR.

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
