"""RunController: orquestador del ciclo de reconciliacion (Etapa 2 / S5).

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md §3
  (algoritmo principal) + §4 (eventos) + §7 (presupuestos).
  external/blueprint-v1/docs/06-controladores.md §2 (RunController).

Responsabilidades:
- Mantener la instancia del Run (estado + plan + current_node).
- Calcular la ready frontier desde el plan y los NodeExecutions.
- Compilar el Handoff de cada NodeExecution nuevo.
- Invocar el AgentAdapter.
- Persistir el resultado y emitir eventos.
- Recuperarse tras interrupcion (UAT-06): si un NodeExecution queda
  en RUNNING sin finished_at, se devuelve a READY.
- Idempotente en evento (UAT-07): la UNIQUE sobre event_id hace el
  trabajo; el controller NO reintenta nodos ya completados.

No responsabilidades:
- No compila la receta de contexto (Etapa 3 lo hara): por ahora
  `HandoffKnowledge.included` esta vacio y `recipe_ref` es un stub.
- No aplica efectos externos: el Adapter hace su trabajo aislado
  y devuelve un AgentResult estructurado.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from skillgraph.core.runtime_types import RunState, is_terminal_run_state
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition
from skillgraph.runtime.agent import AgentAdapter, AgentResult
from skillgraph.runtime.engine import EventBuilder, EventLog
from skillgraph.runtime.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)

# Maximo de reintentos por nodo antes de marcar FAILED terminal.
MAX_NODE_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """Vista inmutable del estado del run tras reconcile_run."""

    run_id: str
    state: RunState
    current_node: str | None
    executed_nodes: tuple[str, ...]
    events_emitted: int


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


class RunController:
    """Orquestador del bucle de reconciliacion para un proyecto."""

    def __init__(
        self,
        *,
        storage: Storage,
        adapter: AgentAdapter,
        conn: sqlite3.Connection,
    ) -> None:
        self._storage = storage
        self._adapter = adapter
        self._conn = conn
        self._events = EventLog(conn)
        # Stubs para Etapa 3: el ContextController (receta) y
        # KnowledgeController se aniadiran cuando hagan falta.
        self._recipe_ref = "default-empty-recipe/v1"
        self._workspace_ref = "ws:."

    # ---------- ciclo de vida del Run ----------

    def create_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan: WorkflowPlan,
    ) -> str:
        """Crea un Run con el plan dado. NO lo ejecuta.

        Devuelve el `run_id`. Emite un evento `RunCreated`.
        """
        run_id = new_run_id()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO workflow_runs
                    (run_id, tenant_id, project_id, state, plan_json,
                     current_node)
                VALUES (?, ?, ?, 'CREATED', ?, ?)
                """,
                (
                    run_id,
                    tenant_id,
                    project_id,
                    plan_to_json(plan),
                    plan.initial,
                ),
            )
        self._events.append(
            EventBuilder(
                tenant_id=tenant_id,
                project_id=project_id,
                correlation_id=run_id,
            ).run_created(run_id=run_id, initial_node=plan.initial)
        )
        return run_id

    def reconcile_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> RunSnapshot:
        """Ejecuta UNA pasada del bucle de reconciliacion.

        Devuelve el snapshot del estado. Si el Run ya estaba terminal,
        devuelve el snapshot sin emitir eventos.
        """
        run = self._load_run(tenant_id, project_id, run_id)
        plan = plan_from_json(run["plan_json"])
        state = run["state"]

        # UAT-06: si un NodeExecution quedo RUNNING sin finished_at,
        # lo devolvemos a READY (interrupcion).
        self._recover_interrupted(tenant_id, project_id, run_id)

        if is_terminal_run_state(state):
            return self._snapshot(tenant_id, project_id, run_id)

        # Activar el run si estaba CREATED.
        if state == "CREATED":
            self._set_run_state(tenant_id, project_id, run_id, "ACTIVE", plan.initial)

        # Calcular frontier.
        frontier = self._calculate_frontier(tenant_id, project_id, run_id, plan)

        # Ejecutar cada nodo de la frontier.
        for node_name in frontier:
            ok = self._execute_one(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                plan=plan,
                node_name=node_name,
            )
            if ok is False:
                # FAILED terminal: paramos.
                self._set_run_state(tenant_id, project_id, run_id, "FAILED", node_name)
                self._events.append(
                    EventBuilder(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        correlation_id=run_id,
                    ).run_completed(run_id=run_id, state="FAILED", at=node_name)
                )
                return self._snapshot(tenant_id, project_id, run_id)

            # Si el nodo completado no tiene sucesor, el run termina.
            last = self._latest_node_execution(tenant_id, project_id, run_id, node_name)
            if last is None or last["state"] != "SUCCEEDED":
                continue
            next_name = plan.successors(node_name, last["outcome"] or "")
            if next_name is None:
                break
            # Avanzar el puntero current_node al siguiente.
            self._set_run_state(tenant_id, project_id, run_id, "ACTIVE", next_name)
            # Por diseno: una pasada ejecuta UN nodo. El caller
            # (CLI o scheduler externo) llama a reconcile_run de
            # nuevo para avanzar el siguiente. Esto cumple la
            # propiedad del blueprint: cada pasada del bucle es
            # determinista y reversible.

        # Si frontier vacia -> terminamos.
        # Caso H4 budget exhausted: current con self-loop y max_visits
        # agotado -> FAILED. Caso DAG normal -> COMPLETED.
        run_row = self._load_run(tenant_id, project_id, run_id)
        prev_current = run_row["current_node"]
        budget_exhausted = False
        if prev_current is not None:
            node_prev = plan.node(prev_current)
            if has_self_loop(plan, prev_current) and node_prev.max_visits is not None:
                existing_prev = self._node_executions_for(
                    tenant_id, project_id, run_id, prev_current
                )
                if len(existing_prev) >= node_prev.max_visits:
                    budget_exhausted = True
        new_frontier = self._calculate_frontier(tenant_id, project_id, run_id, plan)
        if not new_frontier:
            if budget_exhausted:
                self._set_run_state(tenant_id, project_id, run_id, "FAILED", prev_current)
                self._events.append(
                    EventBuilder(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        correlation_id=run_id,
                    ).run_completed(run_id=run_id, state="FAILED", at=prev_current)
                )
            else:
                self._set_run_state(tenant_id, project_id, run_id, "COMPLETED", None)
                self._events.append(
                    EventBuilder(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        correlation_id=run_id,
                    ).run_completed(run_id=run_id, state="COMPLETED")
                )

        return self._snapshot(tenant_id, project_id, run_id)

    # ---------- internals ----------

    def _load_run(self, tenant_id: str, project_id: str, run_id: str) -> dict[str, Any]:
        # Lectura pura: delega en `Storage.load_run` (H9-BSlice3-S1).
        return self._storage.load_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id)

    def _set_run_state(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: RunState,
        current_node: str | None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE workflow_runs
                SET state = ?, current_node = ?,
                    updated_at = datetime('now')
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                """,
                (state, current_node, tenant_id, project_id, run_id),
            )

    def _recover_interrupted(self, tenant_id: str, project_id: str, run_id: str) -> None:
        """UAT-06: cualquier NodeExecution RUNNING sin finished_at se
        devuelve a READY para ser reintentada.

        Ahora delega en ``Storage.recover_interrupted_node_executions``
        (H9-BSlice3-S4). Escritura sin evento; la atomicidad interna la
        gestiona Storage (una sola transaccion para todas las filas,
        a diferencia del bucle anterior que abria una tx por fila).
        """
        self._storage.recover_interrupted_node_executions(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def _calculate_frontier(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
    ) -> list[str]:
        """Lista de nombres de nodo listos para ejecutar.

        Reglas:
        - Un nodo aparece en la frontier si:
          * Nunca se ha ejecutado (no hay NodeExecution para el run+name).
          * Su unico NodeExecution esta en READY (interrumpido y
            recuperado) o FAILED (a reintentar, aunque por ahora no
            incrementamos attempt automaticamente).
        - El plan es un DAG simple: un nodo solo se ejecuta si su
          current_node = su nombre, O si es el initial y el run esta
          recien creado.
        """
        run_row = self._load_run(tenant_id, project_id, run_id)
        current = run_row["current_node"]
        if current is None:
            return []

        # Miramos si el current ya esta completado.
        existing = self._node_executions_for(tenant_id, project_id, run_id, current)
        last = existing[-1] if existing else None
        if last is None:
            return [current]
        # H4: si last es SUCCEEDED, es ciclo solo si el plan declara una
        # auto-transicion desde current hacia si mismo. Sin self-loop
        # declarada, es nodo terminal post-exito: devolver [].
        if last["state"] == "SUCCEEDED":
            node = plan.node(current)
            if not has_self_loop(plan, current):
                return []
            if node.max_visits is not None and len(existing) >= node.max_visits:
                return []
            return [current]
        if last["state"] in {"SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"}:
            return []
        return [current]

    def _execute_one(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
        node_name: str,
    ) -> bool:
        """Ejecuta UN nodo. Devuelve False si FAILED terminal."""
        # Idempotencia: si ya hay SUCCEEDED Y el plan NO declara un
        # self-loop en este nodo, no hacemos nada (DAG lineal).
        # H4: en self-loop, debemos re-ejecutar para gastar el budget.
        existing = self._node_executions_for(tenant_id, project_id, run_id, node_name)
        if existing and existing[-1]["state"] == "SUCCEEDED" and not has_self_loop(plan, node_name):
            return True

        attempt = len(existing) + 1
        # Permitimos como maximo un reintento tras fallo.
        if attempt > MAX_NODE_ATTEMPTS:
            return False
        node = plan.node(node_name)
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

        # Compilar Handoff
        handoff = self._build_handoff(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_execution_id=node_execution_id,
            attempt=attempt,
            node=node,
            plan=plan,
        )
        context_hash = handoff.context_hash

        self._events.append(
            events.handoff_created(
                run_id=run_id,
                node_execution_id=node_execution_id,
                context_hash=context_hash,
            )
        )

        # Insertar NodeExecution en RUNNING
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO node_executions
                    (node_execution_id, run_id, tenant_id, project_id,
                     node_name, attempt, state, context_hash, handoff_json,
                     started_at)
                VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, datetime('now'))
                """,
                (
                    node_execution_id,
                    run_id,
                    tenant_id,
                    project_id,
                    node_name,
                    attempt,
                    context_hash,
                    json.dumps(handoff.to_dict(), sort_keys=False),
                ),
            )

        self._events.append(events.node_started(run_id=run_id, node_execution_id=node_execution_id))

        # Invocar Adapter
        try:
            result = self._adapter.invoke(handoff)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self._mark_node_failed(
                tenant_id=tenant_id,
                project_id=project_id,
                node_execution_id=node_execution_id,
                error=error_msg,
            )
            self._events.append(
                events.node_failed(
                    run_id=run_id,
                    node_execution_id=node_execution_id,
                    error=error_msg,
                )
            )
            return False

        # Validar resultado (outcome declarado?)
        if not is_outcome_declared(result, plan, node_name):
            error_msg = f"outcome {result.outcome!r} no declarado en plan"
            self._mark_node_failed(
                tenant_id=tenant_id,
                project_id=project_id,
                node_execution_id=node_execution_id,
                error=error_msg,
            )
            self._events.append(
                events.node_failed(
                    run_id=run_id,
                    node_execution_id=node_execution_id,
                    error="outcome no declarado",
                    outcome=result.outcome,
                )
            )
            return False

        # Marcar SUCCEEDED
        with self._conn:
            self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'SUCCEEDED', outcome = ?, result_json = ?,
                    finished_at = datetime('now')
                WHERE node_execution_id = ?
                """,
                (
                    result.outcome,
                    json.dumps(result_to_jsonable(result), sort_keys=True),
                    node_execution_id,
                ),
            )

        self._events.append(
            events.node_completed(
                run_id=run_id,
                node_execution_id=node_execution_id,
                outcome=result.outcome,
                context_hash=context_hash,
            )
        )

        # UAT-04: deja evidencia.
        self._events.append(
            events.evidence_produced(
                run_id=run_id,
                node_execution_id=node_execution_id,
                outcome=result.outcome,
                context_hash=context_hash,
                evidence_ref=result.evidence_ref or context_hash,
            )
        )
        return True

    def _build_handoff(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_execution_id: str,
        attempt: int,
        node: WorkflowNode,
        plan: WorkflowPlan,
    ) -> Handoff:
        """Compila el Handoff para un nodo listo para ejecutar.

        Funcion pura (sin I/O): produce un Handoff inmutable. La logica
        es identica entre intentos; solo cambian `attempt` y el id.
        """
        identity = HandoffIdentity(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_execution_id=node_execution_id,
            attempt=attempt,
        )
        behavior = HandoffBehavior(
            definition_kind=node.kind,
            definition_name=node.name,
            definition_namespace=node.namespace,
            definition_revision=node.resource_revision,
            api_version=node.api_version,
        )
        knowledge = HandoffKnowledge(
            recipe_ref=self._recipe_ref,
            included=(),
        )
        execution = HandoffExecution(
            workspace_ref=self._workspace_ref,
            source_revision=plan.initial,
            budget={"max_nodes": len(plan.nodes)},
        )
        return Handoff(
            identity=identity,
            behavior=behavior,
            knowledge=knowledge,
            execution=execution,
            expected_result=node.expected_result,
            capabilities=node.capabilities,
        )

    def _mark_node_failed(
        self,
        *,
        tenant_id: str,
        project_id: str,
        node_execution_id: str,
        error: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'FAILED', error = ?, finished_at = datetime('now')
                WHERE node_execution_id = ?
                """,
                (error, node_execution_id),
            )

    def _node_executions_for(
        self, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> list[dict[str, Any]]:
        # Lectura pura: delega en `Storage.list_node_executions`
        # (H9-BSlice3-S1). Orden por `started_at ASC` estable.
        return self._storage.list_node_executions(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
        )

    def _latest_node_execution(
        self, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> dict[str, Any] | None:
        rows = self._node_executions_for(tenant_id, project_id, run_id, node_name)
        return rows[-1] if rows else None

    def _node_has_execution(
        self, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> bool:
        return bool(self._node_executions_for(tenant_id, project_id, run_id, node_name))

    def _count_executed(self, tenant_id: str, project_id: str, run_id: str) -> int:
        return len(self._executed_node_names(tenant_id, project_id, run_id))

    def _executed_node_names(self, tenant_id: str, project_id: str, run_id: str) -> tuple[str, ...]:
        # Lectura pura: delega en `Storage.list_executed_node_names`
        # (H9-BSlice3-S1). DISTINCT + ORDER BY node_name ASC determinista.
        return self._storage.list_executed_node_names(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )

    def _snapshot(self, tenant_id: str, project_id: str, run_id: str) -> RunSnapshot:
        run = self._load_run(tenant_id, project_id, run_id)
        return RunSnapshot(
            run_id=run_id,
            state=run["state"],
            current_node=run["current_node"],
            executed_nodes=self._executed_node_names(tenant_id, project_id, run_id),
            events_emitted=len(
                self._events.events_for_run(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                )
            ),
        )


__all__ = [
    "MAX_NODE_ATTEMPTS",
    "RunController",
    "RunSnapshot",
    "has_self_loop",
    "is_outcome_declared",
    "new_node_execution_id",
    "new_run_id",
    "plan_from_json",
    "plan_to_json",
    "result_to_jsonable",
]
