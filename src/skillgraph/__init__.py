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

__version__ = "0.42.0"  # v0.42.0: la serie B31..B35 cerrada, con el SemVer derivado con scripts/derive_semver.py sobre v0.41.0..HEAD: b/f/x/n/d 0/6/7/33/1 -> MINOR. La version activa describe el ARBOL: en este commit coincide con la etiqueta, que es el caso 1 de `test_version_matches_git_tag`. El commit que sela el sha llega DESPUES y la devuelve a `0.42.0.dev0`, caso 2.  # R0+R1: 0 breaking, 1 feat, 1 refactor, 5 otros => MINOR, derivado con scripts/derive_semver.py sobre el tramo v0.40.0..HEAD. La version activa describe el ARBOL, no la etiqueta: entre `v0.41.0` y este commit hay uno de gobernanza, que es el caso 2 de `test_version_matches_git_tag`.

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
