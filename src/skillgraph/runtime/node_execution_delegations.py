"""Delegaciones de `RunController`: ejecucion de un nodo: guard, compilacion de handoff, adapter y cierre.

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

import json
from dataclasses import dataclass

from skillgraph.core.errors import SkillGraphError
from skillgraph.platform.ports import StoredNodeExecution
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.engine import EventBuilder
from skillgraph.runtime.handoff import Handoff
from skillgraph.runtime.run_types import (
    has_self_loop,
    is_outcome_declared,
    new_node_execution_id,
    result_to_jsonable,
)

# Maximo de reintentos por nodo antes de marcar FAILED terminal. Se
# movio aqui con el cluster de ejecucion: el orquestador lo usa y un
# import desde `runcontroller` seria un ciclo. `runcontroller` lo
# re-importa para conservar su superficie publica.
MAX_NODE_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class _NodeGuard:
    """Veredicto previo a abrir la NodeExecution de un nodo (WI-66).

    `verdict is None` significa "sigue": no hay cortocircuito, y
    `existing` es valido para calcular el numero de intento.
    """

    verdict: bool | None
    existing: tuple[StoredNodeExecution, ...]


@dataclass(frozen=True, slots=True)
class _NodeExecution:
    """Identidad de la ejecucion en curso de un nodo (WI-66)."""

    attempt: int
    node: WorkflowNode
    node_name: str
    events: EventBuilder
    node_execution_id: str


class NodeExecutionDelegations:
    """Ejecucion de UN nodo: guard, compilacion de handoff, adapter y cierre.

    12 metodos, 405 LoC movidos de `RunController` (WI-67).
    Cuerpos verbatim: ver `runcontroller.py` @ WI-67.
    """

    def _execute_one(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
        node_name: str,
    ) -> bool:
        """Ejecuta UN nodo. Devuelve False si FAILED terminal.

        Orquestador de 9 pasos lineales, agrupados en cuatro fases
        nombradas (WI-66) cuyo nombre dice que invariante protege cada
        paso. El orden ENTRE fases no es negociable: sostiene H9/H10.
        """
        guard = self._node_guard(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            plan=plan,
            node_name=node_name,
        )
        if guard.verdict is not None:
            return guard.verdict

        attempt = len(guard.existing) + 1
        # Permitimos como maximo un reintento tras fallo.
        if attempt > MAX_NODE_ATTEMPTS:
            return False
        node = plan.node(node_name)
        events, node_execution_id = self._open_node_execution(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
        )
        running = _NodeExecution(
            attempt=attempt,
            node=node,
            node_name=node_name,
            events=events,
            node_execution_id=node_execution_id,
        )

        handoff = self._compile_node_handoff(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            plan=plan,
            running=running,
        )
        if handoff is None:
            return False

        result = self._invoke_node_adapter(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            running=running,
            handoff=handoff,
        )
        if result is None:
            return False

        return self._settle_node_outcome(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            plan=plan,
            running=running,
            result=result,
            context_hash=handoff.context_hash,
        )

    def _node_guard(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
        node_name: str,
    ) -> _NodeGuard:
        """Fase 1: budget e idempotencia, ANTES de tocar el nodo.

        S4 Etapa 7: si el budget global del Run esta agotado ANTES de
        ejecutar, devolvemos False y el caller (`reconcile_run`) cierra
        el Run en FAILED.

        Idempotencia: si ya hay SUCCEEDED Y el plan NO declara un
        self-loop en este nodo, no hacemos nada (DAG lineal).
        H4: en self-loop, debemos re-ejecutar para gastar el budget.
        """
        prev = self._load_run(tenant_id, project_id, run_id)
        if self._is_budget_exhausted(
            plan,
            tenant_id,
            project_id,
            run_id,
            prev_current=prev.current_node,
        ):
            return _NodeGuard(verdict=False, existing=())

        existing = self._node_executions_for(tenant_id, project_id, run_id, node_name)
        if existing and existing[-1].state == "SUCCEEDED" and not has_self_loop(plan, node_name):
            return _NodeGuard(verdict=True, existing=tuple(existing))
        return _NodeGuard(verdict=None, existing=tuple(existing))

    def _compile_node_handoff(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
        running: _NodeExecution,
    ) -> Handoff | None:
        """Fase 2: compila el Handoff y persiste su hash.

        Devuelve `None` si el nodo quedo FAILED. Es la traduccion de
        `return self._fail_node_with(...)`, que devuelve siempre False.

        H9-context-in-run: los errores tipados de compilacion de
        contexto (Stale, MissingObligatory, TokenBudget) marcan el nodo
        FAILED sin invocar el adapter.
        """
        try:
            handoff = self._build_handoff(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=running.node_execution_id,
                attempt=running.attempt,
                node=running.node,
                plan=plan,
            )
        except SkillGraphError as exc:
            self._fail_node_with(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=running.node_execution_id,
                node_name=running.node_name,
                exc=exc,
            )
            return None
        context_hash = handoff.context_hash

        self._events.append(
            running.events.handoff_created(
                run_id=run_id,
                node_execution_id=running.node_execution_id,
                context_hash=context_hash,
            )
        )

        # H9-BSlice3-S5 (actualizado en H10/v0.7.2): delega el INSERT del
        # NodeExecution RUNNING + el evento `NodeStarted` en una SOLA
        # transaccion via `Storage.start_node_execution_atomically`.
        # Esto cierra el gap detectado por la revision externa del
        # release v0.7.1: antes, `_storage.start_node_execution` y
        # `_events.append(NodeStarted)` eran dos operaciones
        # separadas y `with self._conn:` no rollbackea (LIMITACION-7)
        # -> podian quedar desincronizadas ante un fallo del proceso.
        # El INSERT real de la NodeExecution (RUNNING + NodeStarted)
        # ya ocurrio en `_open_node_execution`, antes de compilar el
        # handoff: aqui solo se persisten el context_hash y el
        # handoff_json definitivos.
        self._runs.update_node_execution_handoff(
            node_execution_id=running.node_execution_id,
            context_hash=context_hash,
            handoff_json=json.dumps(handoff.to_dict(), sort_keys=False),
        )
        return handoff

    def _invoke_node_adapter(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        running: _NodeExecution,
        handoff: Handoff,
    ) -> AgentResult | None:
        """Fase 3: frontera con el Adapter. `None` = nodo FAILED."""
        try:
            return self._adapter.invoke(handoff)
        except Exception as exc:
            # Frontera con el Adapter, que es un `Protocol` inyectado:
            # su `invoke` lo implementa codigo externo y puede fallar
            # con cualquier excepcion. El contrato del RunController es
            # que un fallo del adapter NO tumba el run, se convierte en
            # un nodo FAILED persistido con el motivo, de modo que el
            # run queda en un estado inspeccionable. La excepcion se
            # guarda en el nodo, asi que aqui no se pierde.
            self._fail_node_with(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=running.node_execution_id,
                node_name=running.node_name,
                exc=exc,
            )
            return None

    def _settle_node_outcome(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
        running: _NodeExecution,
        result: AgentResult,
        context_hash: str,
    ) -> bool:
        """Fase 4: valida el outcome declarado y cierra el nodo."""
        if not is_outcome_declared(result, plan, running.node_name):
            error_msg = f"outcome {result.outcome!r} no declarado en plan"
            self._mark_node_failed(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=running.node_execution_id,
                node_name=running.node_name,
                error=error_msg,
                outcome=result.outcome,
            )
            return False

        # H9-BSlice3-S6 (actualizado en H10/v0.7.2): delega el UPDATE a
        # SUCCEEDED + los dos eventos (NodeCompleted y EvidenceProduced)
        # en una SOLA transaccion via
        # `Storage.complete_node_execution_atomically`. Cierra el gap
        # detectado por la revision externa de v0.7.1.
        self._finalize_node_success(
            events=running.events,
            run_id=run_id,
            node_execution_id=running.node_execution_id,
            result=result,
            context_hash=context_hash,
        )
        return True

    def _open_node_execution(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
    ) -> tuple[EventBuilder, str]:
        """Bootstrap de un nodo: emite `NodeScheduled` y crea la NodeExecution RUNNING.

        Helper local para `_execute_one`. Devuelve la tupla
        `(EventBuilder, node_execution_id)`: el builder se reutiliza
        para los eventos posteriores (`HandoffCreated`, `NodeStarted`,
        `NodeCompleted`, etc.) y `node_execution_id` identifica la fila
        creada atómicamente.

        `NodeStarted` se emite DENTRO de la transacción
        `start_node_execution_atomically` (H9-BSlice3-S5), de modo que
        `NodeExecution RUNNING` y el evento son atómicos.
        """
        node_execution_id = new_node_execution_id()
        events = EventBuilder(
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=run_id,
        )
        self._events.append(
            events.node_scheduled(
                run_id=run_id,
                node_execution_id=node_execution_id,
                node_name=node_name,
                attempt=attempt,
            )
        )
        node_started_event = events.node_started(run_id=run_id, node_execution_id=node_execution_id)
        self._runs.start_node_execution_atomically(
            event=node_started_event,
            node_execution_id=node_execution_id,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
            context_hash="",
            handoff_json="{}",
        )
        return events, node_execution_id

    def _finalize_node_success(
        self,
        *,
        events: EventBuilder,
        run_id: str,
        node_execution_id: str,
        result: AgentResult,
        context_hash: str,
    ) -> None:
        """Cierre exitoso de un nodo: emite `NodeCompleted` + `EvidenceProduced`
        y delega el UPDATE a SUCCEEDED en una sola transaccion.

        Helper local para `_execute_one`. Reutiliza el `EventBuilder`
        abierto por `_open_node_execution` para mantener la
        trazabilidad de eventos (todos comparten el mismo `correlation_id`).
        """
        ev_completed = events.node_completed(
            run_id=run_id,
            node_execution_id=node_execution_id,
            outcome=result.outcome,
            context_hash=context_hash,
        )
        # UAT-04: deja evidencia. Emitido como evento dentro de la
        # transaccion atomica.
        ev_evidence = events.evidence_produced(
            run_id=run_id,
            node_execution_id=node_execution_id,
            outcome=result.outcome,
            context_hash=context_hash,
            evidence_ref=result.evidence_ref or context_hash,
        )
        self._runs.complete_node_execution_atomically(
            event_completed=ev_completed,
            event_evidence=ev_evidence,
            node_execution_id=node_execution_id,
            outcome=result.outcome,
            result_json=json.dumps(result_to_jsonable(result), sort_keys=True),
        )

    def _fail_node_with(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_execution_id: str,
        node_name: str,
        exc: BaseException,
    ) -> bool:
        """Marca el nodo FAILED con la causa de una excepción, sin re-lanzar.

        Helper local para `_execute_one`: centraliza el formato
        `"{type(exc).__name__}: {exc}"` y delega en `_mark_node_failed`.
        Devuelve siempre `False` para que el caller haga
        `return self._fail_node_with(...)` sin escribir el literal.
        """
        self._mark_node_failed(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_execution_id=node_execution_id,
            node_name=node_name,
            error=f"{type(exc).__name__}: {exc}",
        )
        return False

    def _mark_node_failed(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_execution_id: str,
        node_name: str,
        error: str,
        outcome: str | None = None,
    ) -> None:
        # H9-BSlice3-S7 (actualizado en H10/v0.7.2): ahora delega el
        # UPDATE a FAILED + el evento NodeFailed en una SOLA
        # transaccion via `Storage.mark_node_failed_atomically`.
        # Cierra el gap detectado por la revision externa de v0.7.1.
        events = EventBuilder(
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=run_id,
        )
        node_failed_event = events.node_failed(
            run_id=run_id,
            node_execution_id=node_execution_id,
            error=error,
            outcome=outcome,
        )
        self._runs.mark_node_failed_atomically(
            event=node_failed_event,
            node_execution_id=node_execution_id,
            error=error,
        )

    def _node_executions_for(
        self, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> list[StoredNodeExecution]:
        # Lectura pura: delega en `Storage.list_node_executions`
        # (H9-BSlice3-S1). Orden por `started_at ASC` estable.
        # WI-32.4: devuelve ``list[StoredNodeExecution]`` (DTOs frozen)
        # en vez de ``list[dict]``.
        return self._runs.list_node_executions(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
        )

    def _latest_node_execution(
        self, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> StoredNodeExecution | None:
        rows = self._node_executions_for(tenant_id, project_id, run_id, node_name)
        return rows[-1] if rows else None

    def _node_has_execution(
        self, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> bool:
        return bool(self._node_executions_for(tenant_id, project_id, run_id, node_name))
