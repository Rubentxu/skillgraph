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

__version__ = "0.39.0.dev0"  # B29: 0 breaking, 2 feat, 1 fix, 5 otros => MINOR, derivado con scripts/derive_semver.py sobre el tramo v0.38.0..HEAD. **POR QUE `.dev0` Y NO EL SEMVER PUERO:** el commit de gobernanza del release esta UN COMMIT POR ENCIMA de la etiqueta `v0.39.0`, porque se hizo DESPUES de crearla. Es el caso 2 de `test_version_matches_git_tag`. **ES LA SEXTA VEZ QUE ESTO SE DESCUADRA EN LA SERIE**, y las seis son la misma clase de error: un numero que describe un instante y se lee en otro. En B24 fue la ventana del ROADMAP, en B25 `tests.package_version`, y en B26, B27, B28 y B29 el caso entre «HEAD esta en la etiqueta» y «HEAD esta por encima». La version activa describe el ARBOL, no la etiqueta: el release queda, el arbol sigue.

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
