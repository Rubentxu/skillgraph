"""Tipos, serializacion e ids del runtime (WI-59, ADR-0019 fase 1).

Extraidos verbatim de `runcontroller.py` (estrangulamiento por fases
ADR-0019): bloque puro sin dependencias de Storage. `runcontroller`
conserva re-imports para sus 39 consumidores externos; los motores de
reconciliation/recovery/snapshot (fases 2-3) seguiran el mismo patron.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from skillgraph.core.errors import ValidationError
from skillgraph.core.runtime_types import RunState
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.engine import RuntimeEvent


@contextlib.contextmanager
def _noop_lock() -> Iterator[None]:
    """Context manager noop (compat con S6 cuando lock_mode='none').

    Devuelve un iterador vacio: el `with _noop_lock():` es equivalente
    a un pass. Asi `_locked_run` puede devolver siempre un context
    manager compatible sin ramificar el caller.
    """
    yield
    return


# Categorias de presupuesto que un Run puede violar. Categoria de
# negocio (payload del evento BudgetExceeded), NO event_kind.
BudgetViolationKind = Literal["visits", "runtime", "events"]


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """Vista inmutable del estado del run tras reconcile_run."""

    run_id: str
    state: RunState
    current_node: str | None
    executed_nodes: tuple[str, ...]
    events_emitted: int


@dataclass(frozen=True, slots=True)
class RuntimeEventLog:
    """Vista inmutable de un evento de runtime con su `sequence`.

    `RuntimeEvent` (engine.py) modela el evento persistido en
    `runtime_events`, pero NO incluye el `sequence` (PK rowid de
    SQLite). Para mostrar el timeline de un Run al operador
    necesitamos el orden monotono; este wrapper lo expone.
    """

    sequence: int
    event: RuntimeEvent


@dataclass(frozen=True, slots=True)
class RunBudget:
    """Limites opt-in que un Run respeta para auto-abortarse.

    Cualquier campo `None` significa "sin limite" para esa categoria.
    Si TODOS los campos son `None`, el budget es efectivamente
    inactivo (compat con Runs anteriores a S4 Etapa 7).

    Invariantes (validadas en `__post_init__`):
    - Los limites no negativos.
    - Si todos son `None`, se acepta (equivale a sin budget).
    - Si se da un limite, debe ser > 0 (limite 0 abortaria el Run
      en su primer nodo, sin permitir ni RunCreated efectivo).
    """

    max_visits: int | None = None
    max_runtime_seconds: int | None = None
    max_events: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("max_visits", self.max_visits),
            ("max_runtime_seconds", self.max_runtime_seconds),
            ("max_events", self.max_events),
        ):
            if value is not None and value < 0:
                raise ValidationError(f"RunBudget.{name} no puede ser negativo: {value}")
            if value is not None and value == 0:
                raise ValidationError(f"RunBudget.{name} debe ser > 0 si se especifica: {value}")

    @property
    def is_active(self) -> bool:
        """True si al menos un limite esta definido (>0)."""
        return any(
            v is not None for v in (self.max_visits, self.max_runtime_seconds, self.max_events)
        )


def plan_to_json(plan: WorkflowPlan) -> str:
    """Serializa un WorkflowPlan a JSON estable para persistencia."""
    return json.dumps(
        {
            "initial": plan.initial,
            "nodes": [
                {
                    "name": n.name,
                    "kind": n.kind,
                    "namespace": n.namespace,
                    "api_version": n.api_version,
                    "resource_revision": n.resource_revision,
                    "expected_result": n.expected_result,
                    "capabilities": list(n.capabilities),
                    "metadata": n.metadata,
                }
                for n in plan.nodes
            ],
            "transitions": [
                {"source": t.source, "outcome": t.outcome, "target": t.target}
                for t in plan.transitions
            ],
        },
        sort_keys=True,
    )


def plan_from_json(blob: str) -> WorkflowPlan:
    """Reconstruye un WorkflowPlan desde su JSON persistido."""
    data = json.loads(blob)
    nodes = tuple(
        WorkflowNode(
            name=n["name"],
            kind=n["kind"],
            namespace=n["namespace"],
            api_version=n["api_version"],
            resource_revision=n["resource_revision"],
            expected_result=n["expected_result"],
            capabilities=tuple(n.get("capabilities") or ()),
            metadata=n.get("metadata") or {},
        )
        for n in data["nodes"]
    )
    transitions = tuple(
        WorkflowTransition(source=t["source"], outcome=t["outcome"], target=t["target"])
        for t in data.get("transitions") or []
    )
    return WorkflowPlan(nodes=nodes, transitions=transitions, initial=data["initial"])


def result_to_jsonable(result: AgentResult) -> dict[str, Any]:
    """Serializa un AgentResult a un dict apto para persistencia."""
    return {
        "outcome": result.outcome,
        "result": dict(result.result),
        "evidence_ref": result.evidence_ref,
    }


def is_outcome_declared(result: AgentResult, plan: WorkflowPlan, node_name: str) -> bool:
    """True si `outcome` del Adapter figura como transicion declarada en el plan.

    Un nodo sin transiciones (terminal) acepta cualquier outcome.
    """
    declared_outcomes = {t.outcome for t in plan.transitions if t.source == node_name}
    if not declared_outcomes:
        return True
    return result.outcome in declared_outcomes


def new_run_id() -> str:
    return f"run-{uuid.uuid4()}"


def new_node_execution_id() -> str:
    return f"ne-{uuid.uuid4()}"


def has_self_loop(plan: WorkflowPlan, node_name: str) -> bool:
    """True si el plan declara una transicion source=node -> target=node.

    H4: distinguir nodos terminales post-exito de ciclos declarados.
    Centralizado aqui para no duplicar la comprobacion inline.
    """
    return any(t.source == node_name and t.target == node_name for t in plan.transitions)
