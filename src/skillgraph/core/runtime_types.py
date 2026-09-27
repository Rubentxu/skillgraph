"""Tipos canonicos del runtime de SkillGraph.

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md §1-2
  (estados de run y de instancia de nodo).

Estos tipos son **ADT cerradas**: anadir un valor nuevo es un cambio
de contrato del blueprint, no un detalle local. Si necesitas un valor
nuevo, abre una ADR primero.

QW-D (WI-31, 2026-09-27): ``EventType`` Literal y ``EVENT_KINDS``
frozenset eran DOS conjuntos con interseccion de 3 valores. Ahora
hay una sola fuente: ``EventType`` Literal. ``EVENT_KINDS`` se deriva
de el via ``typing.get_args()``. El antiguo modulo ``runtime.engine``
define ``EVENT_KINDS`` por compat historica pero importa ``EventType``
de aqui; cualquier valor nuevo debe declararse en ``EventType``.
"""

from __future__ import annotations

from typing import Final, Literal, NewType, get_args

# --- Tipos suma (ADT cerradas) -------------------------------------------

NodeKind = Literal["DecisionNode", "ActionNode"]
"""Suma cerrada: un nodo del runtime es DecisionNode o ActionNode."""

RunState = Literal["CREATED", "ACTIVE", "WAITING", "COMPLETED", "FAILED", "CANCELLED"]
"""Ciclo de vida de un Run (blueprint §1)."""

NodeState = Literal["READY", "RUNNING", "WAITING", "SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"]
"""Ciclo de vida de una instancia de nodo (blueprint §2)."""

# --- H3 Slice 1: tipos de conocimiento -------------------------------------

SourceKind = Literal[
    "git_commit",
    "git_tree",
    "local_file",
    "external_doc",
    "skill_pack",
]
"""Tipo de fuente de la que se extrae evidencia.

- `git_commit`: snapshot inmutable de un commit.
- `git_tree`: snapshot de un tree (directorio) en un commit.
- `local_file`: archivo del workspace NO bajo git (provisional).
- `external_doc`: documento externo (URL, PDF, etc.).
- `skill_pack`: paquete de skill externa asimilada (H5). Conserva
  el material original como referencia (path + content_hash) sin
  ejecutar el codigo del paquete. Ver `skill_importer.py`.
"""

FreshnessState = Literal["fresh", "stale", "archived"]
"""Estado de actualidad de una Source.

`fresh` = el contenido coincide con el esperado.
`stale` = el contenido cambio (su hash difiere del registrado).
`archived` = retirada del catalogo activo.
"""

ClaimPredicate = Literal[
    "line_count",
    "function_count",
    "imports_module",
    "defines_symbol",
    "test_passes",
    "file_exists",
    "spec_revision",
]
"""Predicados extraibles en H3 (extensibles en H5 con Domain Packs)."""

FindingResult = Literal["pass", "fail", "inconclusive"]
"""Resultado de aplicar una regla a una entidad."""

TraceKind = Literal["SoftwareExecutionSlice"]
"""Tipo de OutcomeTrace. H3 cubre solo `SoftwareExecutionSlice`."""

RuleRef = Literal["max_lines_per_function", "max_complexity", "naming_convention"]
"""Reglas de software disponibles en H3."""

EventType = Literal[
    "RunCreated",
    "RunStarted",
    "RunCompleted",
    "RunFinished",
    "RunFailed",
    "NodeScheduled",
    "HandoffCreated",
    "NodeStarted",
    "NodeFinished",
    "NodeCompleted",
    "NodeFailed",
    "EvidenceProduced",
    "KnowledgeInvalidated",
    "KnowledgeRefreshed",
    "ProblemDiscovered",
    "GraphExpansionProposed",
    "GraphExpansionAccepted",
    "GraphExpansionRejected",
    "BudgetExceeded",
]
"""Tipos de evento que pueden aparecer en `runtime_events`.

QW-D: union canonica de los antiguos ``EventType`` (8 valores) y
``runtime.engine.EVENT_KINDS`` (14 valores). Las dos colecciones
estaban desincronizadas (solo 3 comunes: RunCreated, NodeStarted,
KnowledgeInvalidated). Ahora hay una sola fuente. ``EVENT_KINDS`` se
deriva de este Literal via ``get_args()``.

Si anades un evento nuevo, declaralo aqui y un ADR con la justificacion.
"""

#: Conjunto canonico derivado del Literal EventType.
#: Cualquier ``event_kind`` fuera de este set falla validacion
#: (``RuntimeEvent.__post_init__``).
EVENT_KINDS: Final[frozenset[str]] = frozenset(get_args(EventType))
"""Conjunto derivado: ``frozenset(get_args(EventType))``. Importado por
``runtime.engine`` para la validacion runtime. No redefinir en otros
modulos: una sola fuente de verdad (QW-D)."""

# --- NewType: evita confusion entre strings ------------------------------
# Un NodeName NO es un Outcome, aunque ambos sean str. Los NewType
# desaparecen en runtime (no afectan performance) pero hacen que el
# type-checker rechace mezclas accidentales.

NodeName = NewType("NodeName", str)
"""Identificador local de un nodo dentro de un WorkflowPlan."""

OutcomeLabel = NewType("OutcomeLabel", str)
"""Etiqueta declarativa que un Adapter devuelve o un WorkflowTransition declara."""

RevisionNumber = NewType("RevisionNumber", int)
"""Version monotona de un recurso (>= 1)."""

# --- Constantes runtime (validacion + branching) ------------------------

#: Conjunto canonico de kinds de nodo ejecutables.
NODE_KINDS: Final[frozenset[str]] = frozenset({"DecisionNode", "ActionNode"})

#: Estados terminales de un Run (no avanzan mas).
TERMINAL_RUN_STATES: Final[frozenset[str]] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

#: Estados terminales de una NodeExecution.
TERMINAL_NODE_STATES: Final[frozenset[str]] = frozenset(
    {"SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"}
)

#: Conjunto canonico de kinds de fuente.
SOURCE_KINDS: Final[frozenset[str]] = frozenset(get_args(SourceKind))
"""Conjunto derivado: ``frozenset(get_args(SourceKind))`` (QW-E).

Antes era un frozenset declarado a mano con 4 valores; el Literal
``SourceKind`` tenia 5 (``skill_pack`` incluido). Validacion runtime
rechazaba ``skill_pack`` por la divergencia.

Cualquier ``source_kind`` fuera de este set falla validacion.
"""

#: Conjunto canonico de predicados de Claim (H3).
CLAIM_PREDICATES: Final[frozenset[str]] = frozenset(
    {
        "line_count",
        "function_count",
        "imports_module",
        "defines_symbol",
        "test_passes",
        "file_exists",
        "spec_revision",
    }
)

#: Conjunto canonico de resultados de Finding.
FINDING_RESULTS: Final[frozenset[str]] = frozenset({"pass", "fail", "inconclusive"})


def is_terminal_run_state(state: str) -> bool:
    """True si el estado del Run es terminal (no admite mas reconciliacion)."""
    return state in TERMINAL_RUN_STATES


def is_terminal_node_state(state: str) -> bool:
    """True si el estado de la NodeExecution es terminal."""
    return state in TERMINAL_NODE_STATES


# Public API surface for `from skillgraph.core.runtime_types import *`.
__all__ = [
    "CLAIM_PREDICATES",
    "FINDING_RESULTS",
    "NODE_KINDS",
    "SOURCE_KINDS",
    "TERMINAL_NODE_STATES",
    "TERMINAL_RUN_STATES",
    "ClaimPredicate",
    "EventType",
    "FindingResult",
    "FreshnessState",
    "NodeKind",
    "NodeName",
    "NodeState",
    "OutcomeLabel",
    "RevisionNumber",
    "RuleRef",
    "RunState",
    "SourceKind",
    "TraceKind",
    "is_terminal_node_state",
    "is_terminal_run_state",
]
