"""Delegaciones de `RunController`: politica de budget: agotamiento y emision de budgetexceeded.

WI-67, ADR-0019 fase 2. Extraccion estranguladora de metodos de
`RunController` hacia un mixin por dominio. Cuerpos movidos
**verbatim**: sin logica, ramas ni rutas de error nuevas.

Por que mixin y no `__getattr__`: `__getattr__` rompe el tipado
estatico que AGENTS.md 4.1 exige explicito. El mixin conserva las
anotaciones reales, mantiene `RunController` como la misma clase
y obliga a cero ediciones en los callers.

Invariante: este modulo solo usa `self.*`. No captura estado, no
importa `RunController` (seria un ciclo) y no define lo que la
clase mantiene. Red: `tests/test_wi67_runcontroller_mixins.py`.
"""

from __future__ import annotations

from skillgraph.resources.workflow import WorkflowPlan
from skillgraph.runtime.engine import EventBuilder
from skillgraph.runtime.run_types import BudgetViolationKind, has_self_loop


class RunBudgetDelegations:
    """Politica de budget: agotamiento y emision de BudgetExceeded.

    2 metodos, 107 LoC movidos de `RunController` (WI-67).
    Cuerpos verbatim: ver `runcontroller.py` @ WI-67.
    """

    def _is_budget_exhausted(
        self,
        plan: WorkflowPlan,
        tenant_id: str,
        project_id: str,
        run_id: str,
        prev_current: str | None,
    ) -> bool:
        """H4 + S4 Etapa 7: budget de visitas agotado en un nodo con self-loop.

        Chequeos (en orden):
        1. `prev_current` con self-loop Y `max_visits` (del nodo) Y
           ejecuciones del nodo >= limite.
        2. Si el Run tiene un `RunBudget` activo:
           a. `max_visits` (global del Run) y ejecuciones totales del
              nodo `prev_current` >= limite.
           b. `max_events` (del Run) y total de eventos >= limite.

        Si el chequeo 1 falla pero el chequeo 2a o 2b falla, emite un
        evento `BudgetExceeded` con `kind=visits` o `kind=events`
        respectivamente antes de devolver True. Asi el timeline del
        Run (v0.11.0) muestra al operador POR QUE se aborto.

        True si ALGUNO de los chequeos indica agotamiento.
        """
        if prev_current is None:
            return False

        # Chequeo 1: H4 original (max_visits por nodo en self-loop).
        node_prev = plan.node(prev_current)
        h4_exhausted = has_self_loop(plan, prev_current) and node_prev.max_visits is not None
        existing_prev = self._node_executions_for(tenant_id, project_id, run_id, prev_current)
        if h4_exhausted and len(existing_prev) >= node_prev.max_visits:
            return True

        # Chequeo 2: budget global del Run (S4 Etapa 7).
        budget_row = self._policy.get_budget(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        if budget_row is None:
            return False

        # 2a: max_visits del Run.
        mv = budget_row["max_visits"]
        if mv is not None and len(existing_prev) >= mv:
            self._emit_budget_exceeded(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                kind="visits",
                limit=mv,
                observed=len(existing_prev),
            )
            return True

        # 2b: max_events del Run.
        me = budget_row["max_events"]
        if me is not None:
            event_count = self._count_events(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
            )
            if event_count >= me:
                self._emit_budget_exceeded(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    kind="events",
                    limit=me,
                    observed=event_count,
                )
                return True

        return False

    def _emit_budget_exceeded(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        kind: BudgetViolationKind,
        limit: int,
        observed: int,
    ) -> None:
        """Emite un evento `BudgetExceeded` (helper de enforcement).

        Persiste via `EventLog.append` directamente para mantener
        atomicidad con la siguiente transicion a FAILED (que se hace
        fuera de este helper). El caller (reconcile_run) cierra el
        Run en FAILED justo despues.
        """
        events = EventBuilder(
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=run_id,
        )
        self._events.append(
            events.budget_exceeded(
                run_id=run_id,
                kind=kind,
                limit=limit,
                observed=observed,
            )
        )
