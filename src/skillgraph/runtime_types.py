"""Tipos canonicos del runtime de SkillGraph.

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md §1-2
  (estados de run y de instancia de nodo).

Estos tipos son **ADT cerradas**: anadir un valor nuevo es un cambio
de contrato del blueprint, no un detalle local. Si necesitas un valor
nuevo, abre una ADR primero.

Por que existe este modulo aparte:
- `runtime.py` ya tiene EVENT_KINDS como frozenset, pero NO como
  Literal (porque al ser un frozen dataclass necesita el valor como
  tipo de campo). Aqui declaramos las versiones Literal que pueden
  usar las firmas publicas, y los frozenset que necesitan las
  validaciones runtime.
- Centralizar las constantes evita divergencia entre el snapshot,
  el controller y la CLI.
"""

from __future__ import annotations

from typing import Final, Literal, NewType

# --- Tipos suma (ADT cerradas) -------------------------------------------

NodeKind = Literal["DecisionNode", "ActionNode"]
"""Suma cerrada: un nodo del runtime es DecisionNode o ActionNode."""

RunState = Literal["CREATED", "ACTIVE", "WAITING", "COMPLETED", "FAILED", "CANCELLED"]
"""Ciclo de vida de un Run (blueprint §1)."""

NodeState = Literal["READY", "RUNNING", "WAITING", "SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"]
"""Ciclo de vida de una instancia de nodo (blueprint §2)."""

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


def is_terminal_run_state(state: str) -> bool:
    """True si el estado del Run es terminal (no admite mas reconciliacion)."""
    return state in TERMINAL_RUN_STATES


def is_terminal_node_state(state: str) -> bool:
    """True si el estado de la NodeExecution es terminal."""
    return state in TERMINAL_NODE_STATES
