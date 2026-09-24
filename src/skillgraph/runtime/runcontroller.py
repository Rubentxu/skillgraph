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

import contextlib
import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.core.runtime_types import RunState, is_terminal_run_state
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition
from skillgraph.runtime.agent import AgentAdapter, AgentResult
from skillgraph.runtime.engine import EventBuilder, EventLog, RuntimeEvent
from skillgraph.runtime.locks import (
    LockMode,
    RunLock,
    RunLockKey,
)

if TYPE_CHECKING:
    from skillgraph.core.recipe import ContextRecipe

from skillgraph.knowledge.context_controller import ContextController
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.runtime.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)

# Maximo de reintentos por nodo antes de marcar FAILED terminal.
MAX_NODE_ATTEMPTS = 2


@contextlib.contextmanager
def _noop_lock() -> Iterator[None]:
    """Context manager noop (compat con S6 cuando lock_mode='none').

    Devuelve un iterador vacio: el `with _noop_lock():` es equivalente
    a un pass. Asi `_locked_run` puede devolver siempre un context
    manager compatible sin ramificar el caller.
    """
    yield
    return


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


# Categorias de presupuesto que un Run puede violar. Categoria de
# negocio (payload del evento BudgetExceeded), NO event_kind.
BudgetViolationKind = Literal["visits", "runtime", "events"]


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
                raise ValidationError(
                    f"RunBudget.{name} no puede ser negativo: {value}"
                )
            if value is not None and value == 0:
                raise ValidationError(
                    f"RunBudget.{name} debe ser > 0 si se especifica: {value}"
                )

    @property
    def is_active(self) -> bool:
        """True si al menos un limite esta definido (>0)."""
        return any(
            v is not None
            for v in (self.max_visits, self.max_runtime_seconds, self.max_events)
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


class RunController:
    """Orquestador del bucle de reconciliacion para un proyecto."""

    def __init__(
        self,
        *,
        storage: Storage,
        adapter: AgentAdapter,
        recipe_resolver: Callable[[str], ContextRecipe | None] | None = None,
        lock_dir: Path | None = None,
        lock_mode: LockMode = "none",
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        # H9-BSlice3-S8/S9: el constructor deja de recibir
        # ``conn``. La conexion se obtiene de ``storage.conn``
        # (API publica a partir de esta misma entrega). Tras
        # S1..S7 ya no hay SQL directo en el RunController, asi
        # que el atributo ``<conn_privado>`` se elimina tambien:
        # solo ``EventLog`` lo necesita, y EventLog lo toma via
        # ``storage.conn``.
        self._storage = storage
        self._adapter = adapter
        # S6 Etapa 7: configuracion de locks por run_id.
        # `lock_dir=None` + `lock_mode='none'` = no locks (compat
        # pre-S6; tests existentes no se enteran). Cualquier otra
        # combinacion activa la proteccion.
        self._lock_dir = Path(lock_dir) if lock_dir is not None else None
        self._lock_mode: LockMode = lock_mode
        self._lock_timeout_seconds = lock_timeout_seconds
        # S5 Etapa 7: inyectamos un policy_resolver en el EventLog
        # para que aplique redaccion al payload antes de persistir.
        # El resolver delega en Storage.get_policy (regla "Storage
        # encapsula SQL"). Si no hay politica configurada para el
        # tenant, el resolver devuelve None y EventLog usa el
        # default seguro "metadata".
        self._events = EventLog(
            storage.conn,
            policy_resolver=lambda tenant_id: storage.get_policy(
                tenant_id=tenant_id
            ),
        )
        # H9-context-in-run: resolver opt-in de recetas de contexto.
        # None (default) preserva el stub `default-empty-recipe/v1`.
        # El resolver recibe la ctx_recipe_ref del nodo y devuelve la
        # ContextRecipe a compilar, o None para degradar al stub.
        self._recipe_resolver = recipe_resolver
        self._recipe_ref = "default-empty-recipe/v1"
        self._workspace_ref = "ws:."

    # ---------- ciclo de vida del Run ----------

    def _locked_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> Iterator[None]:
        """Context manager: lock por run_id si S6 esta activo.

        Devuelve un iterator vacio si el modo es 'none' o si
        `lock_dir` es None (compat pre-S6). En caso contrario,
        delega en `RunLock.take(...)`.

        Raises:
            LockUnavailable: si el lock esta tomado y expira el
                timeout (modo advisory) o si ya estaba tomado
                (modo fail-fast).
        """
        if self._lock_dir is None or self._lock_mode == "none":
            return _noop_lock()
        lock = RunLock(
            lock_dir=self._lock_dir,
            key=RunLockKey(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
            ),
        )
        return lock.take(
            mode=self._lock_mode,
            timeout_seconds=self._lock_timeout_seconds,
        )

    def create_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan: WorkflowPlan,
        budget: RunBudget | None = None,
    ) -> str:
        """Crea un Run con el plan dado. NO lo ejecuta.

        Devuelve el `run_id`. Emite un evento `RunCreated`.

        Si `budget` se pasa Y `budget.is_active`, lo persiste en
        `run_budgets` (idempotente: INSERT OR REPLACE). Si se pasa
        un budget inactivo (todos None), se ignora para mantener la
        semantica de ausencia de fila = sin limites.

        H9-run-lifecycle: la creacion del run y la emision del evento
        `RunCreated` viven en una sola transaccion via
        `Storage.create_run_atomically`. Antes iban en commits
        separados (`Storage.create_run` + `EventLog.append`), con
        riesgo de que el run quedara confirmado sin su evento si la
        segunda escritura fallaba.
        """
        run_id = new_run_id()
        with self._locked_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        ):
            result = self._storage.create_run_atomically(
                event=EventBuilder(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    correlation_id=run_id,
                ).run_created(run_id=run_id, initial_node=plan.initial),
                run_id=run_id,
                tenant_id=tenant_id,
                project_id=project_id,
                plan_json=plan_to_json(plan),
                initial_node=plan.initial,
            )
            if budget is not None and budget.is_active:
                self._storage.upsert_budget(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    max_visits=budget.max_visits,
                    max_runtime_seconds=budget.max_runtime_seconds,
                    max_events=budget.max_events,
                )
            return result

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

        S6: toma el lock por run_id al inicio (si esta configurado)
        para serializar reconciliaciones concurrentes del mismo Run.
        """
        with self._locked_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        ):
            return self._reconcile_run_locked(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
            )

    def _reconcile_run_locked(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> RunSnapshot:
        """Cuerpo de reconcile_run ejecutado dentro del lock."""
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
                # H9-run-lifecycle: la transicion a FAILED y la emision
                # del evento `RunCompleted(state=FAILED)` viven en una
                # sola transaccion via `Storage.transition_run_state_atomically`.
                # Antes iban en commits separados (`transition_run_state`
                # + `EventLog.append`).
                self._transition_run_state_with_event(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    state="FAILED",
                    current_node=node_name,
                    at=node_name,
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
        prev_current = self._load_run(tenant_id, project_id, run_id)["current_node"]
        new_frontier = self._calculate_frontier(tenant_id, project_id, run_id, plan)
        if not new_frontier:
            if self._is_budget_exhausted(plan, tenant_id, project_id, run_id, prev_current):
                # H9-run-lifecycle: FAILED por budget agotado. Transicion
                # + evento atomicos.
                self._transition_run_state_with_event(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    state="FAILED",
                    current_node=prev_current,
                    at=prev_current,
                )
            else:
                # H9-run-lifecycle: COMPLETED. Transicion + evento atomicos.
                self._transition_run_state_with_event(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    state="COMPLETED",
                    current_node=None,
                )

        return self._snapshot(tenant_id, project_id, run_id)

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
        h4_exhausted = (
            has_self_loop(plan, prev_current)
            and node_prev.max_visits is not None
        )
        existing_prev = self._node_executions_for(
            tenant_id, project_id, run_id, prev_current
        )
        if h4_exhausted and len(existing_prev) >= node_prev.max_visits:
            return True

        # Chequeo 2: budget global del Run (S4 Etapa 7).
        budget_row = self._storage.get_budget(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        if budget_row is None:
            return False

        # 2a: max_visits del Run.
        mv = budget_row.get("max_visits")
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
        me = budget_row.get("max_events")
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

    def list_runs(
        self,
        *,
        tenant_id: str,
        project_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> tuple[RunSnapshot, ...]:
        """Lista Runs de un (tenant, project) ordenados por mas reciente.

        Inspeccion read-only: NO emite eventos NI modifica estado.
        Complementa `cancel_run`: el operador primero lista, decide
        cual cancelar.

        Args:
            state: filtro opcional por estado exacto.
            limit: tope de runs devueltos (default 50).

        Returns:
            Tupla inmutable de `RunSnapshot` ordenada por created_at
            DESC. El snapshot expone run_id, state, current_node y
            la lista de nodos ejecutados (via `_executed_node_names`).
        """
        rows = self._storage.list_runs(
            tenant_id=tenant_id,
            project_id=project_id,
            state=state,
            limit=limit,
        )
        snapshots: list[RunSnapshot] = []
        for row in rows:
            executed = self._executed_node_names(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=row["run_id"],
            )
            snapshots.append(
                RunSnapshot(
                    run_id=row["run_id"],
                    state=row["state"],  # type: ignore[arg-type]
                    current_node=row["current_node"],
                    executed_nodes=executed,
                    events_emitted=self._count_events(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        run_id=row["run_id"],
                    ),
                )
            )
        return tuple(snapshots)

    def show_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> RunSnapshot:
        """Devuelve el snapshot de un Run por id.

        Inspeccion read-only: NO emite eventos. Levanta `NotFoundError`
        si el run no existe (delegado en `Storage.get_run`).
        """
        row = self._storage.get_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        executed = self._executed_node_names(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        return RunSnapshot(
            run_id=row["run_id"],
            state=row["state"],  # type: ignore[arg-type]
            current_node=row["current_node"],
            executed_nodes=executed,
            events_emitted=self._count_events(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
            ),
        )

    def _count_events(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> int:
        """Cuenta eventos asociados a un Run (read-only).

        Delega en `Storage.list_events_for_run` (regla "Storage
        encapsula SQL"); no toca `_conn` directamente.
        """
        rows = self._storage.list_events_for_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )
        return len(rows)

    def logs_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> tuple[RuntimeEventLog, ...]:
        """Devuelve el timeline de eventos de un Run en orden monotono.

        Inspeccion read-only: NO emite eventos. Levanta `NotFoundError`
        si el run no existe (delegado en `Storage.get_run`; lo
        validamos ANTES de leer eventos para fallar rapido si el
        run no existe vs. devolver una tupla vacia).
        """
        from skillgraph.runtime.engine import _row_to_event_dict

        # Validacion temprana: si el run no existe, error tipado
        # en lugar de una tupla vacia confusa.
        self._storage.get_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        rows = self._storage.list_events_for_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        out: list[RuntimeEventLog] = []
        for row in rows:
            d = _row_to_event_dict(row)
            out.append(
                RuntimeEventLog(
                    sequence=int(d["sequence"]),
                    event=RuntimeEvent(
                        event_id=d["event_id"],
                        tenant_id=d["tenant_id"],
                        project_id=d["project_id"],
                        event_kind=d["event_kind"],
                        run_id=d["run_id"],
                        resource_ref=d["resource_ref"],
                        causation_id=d["causation_id"],
                        correlation_id=d["correlation_id"],
                        payload=d["payload"],
                        timestamp=d["timestamp"],
                        schema_version=d["schema_version"],
                    ),
                )
            )
        return tuple(out)

    def cancel_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> RunSnapshot:
        """Cancela un run en curso.

        S1 del roadmap Etapa 7 (presupuestos y cancelacion): el operador
        puede detener un run ACTIVE/WAITING sin esperar al reconcile
        completo. Emite `RunCompleted(state=CANCELLED)` de forma
        atomica con la transicion de estado a `CANCELLED` y deja
        `current_node=None`.

        - Si el run no existe -> `NotFoundError`.
        - Si el run ya es terminal (COMPLETED/FAILED/CANCELLED) ->
          `ValidationError` (operacion no idempotente: el caller
          debe distinguir 'no cancelable').
        - Si el run tiene NodeExecutions RUNNING, estas se quedan
          en RUNNING: la cancelacion es a nivel de Run, no de
          nodo. El siguiente reconcile_run no las re-ejecuta
          porque detecta el estado terminal del Run al inicio.
        """
        from skillgraph.core.errors import ValidationError

        # `Storage.load_run` lanza NotFoundError si el run no existe.
        run = self._storage.load_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        state = run["state"]
        if is_terminal_run_state(state):
            raise ValidationError(
                f"Run {run_id!r} ya es terminal ({state}); no se puede cancelar"
            )
        # H9-run-lifecycle: la transicion a CANCELLED y la emision del
        # evento `RunCompleted(state=CANCELLED)` viven en una sola TX.
        self._transition_run_state_with_event(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state="CANCELLED",
            current_node=None,
        )
        return self._snapshot(tenant_id, project_id, run_id)

    def _transition_run_state_with_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
        at: str | None = None,
    ) -> None:
        """Transiciona el estado del run emitiendo `RunCompleted` en una sola TX.

        Helper de `reconcile_run` que centraliza las 3 ramas de terminación
        del run (FAILED por nodo fallido, FAILED por budget exhausted,
        COMPLETED normal). El parámetro `at` indica el nodo en que el run
        termina (solo FAILED; COMPLETED pasa None).
        """
        event = EventBuilder(
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=run_id,
        ).run_completed(
            run_id=run_id,
            state=state,
            at=at,
        )
        self._storage.transition_run_state_atomically(
            event=event,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
        )

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
        # H9-BSlice3-S3: delega la mutacion de la fila de workflow_runs
        # en `Storage.transition_run_state`. La transicion del state en
        # el SQL no coordina con EventLog.append: el llamador sigue
        # siendo responsable de emitir el evento que toque (ver decision
        # arquitectonica del 2026-09-23 18:24). Mantener esta separacion
        # evita acoplar Storage al emisor de eventos.
        self._storage.transition_run_state(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
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
        # S4 Etapa 7: si el budget global del Run esta agotado ANTES
        # de ejecutar, emitimos BudgetExceeded y devolvemos False.
        # Asi el caller (reconcile_run) cierra el Run en FAILED.
        prev = self._load_run(tenant_id, project_id, run_id)
        if self._is_budget_exhausted(
            plan,
            tenant_id,
            project_id,
            run_id,
            prev_current=prev["current_node"],
        ):
            return False

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
        events, node_execution_id = self._open_node_execution(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
        )

        # Compilar Handoff. Los errores tipados de compilación de
        # contexto (Stale, MissingObligatory, TokenBudget) marcan el
        # nodo FAILED sin invocar el adapter (H9-context-in-run).
        # El NodeExecution RUNNING se inserta ANTES de compilar para
        # que `_mark_node_failed` tenga una fila que actualizar:
        # el UPDATE de `mark_node_failed_atomically` es afecta-0-filas
        # silencioso si la NodeExecution no existe.
        try:
            handoff = self._build_handoff(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=node_execution_id,
                attempt=attempt,
                node=node,
                plan=plan,
            )
        except SkillGraphError as exc:
            return self._fail_node_with(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=node_execution_id,
                node_name=node_name,
                exc=exc,
            )
        context_hash = handoff.context_hash

        self._events.append(
            events.handoff_created(
                run_id=run_id,
                node_execution_id=node_execution_id,
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
        # ya ocurrio arriba, antes de compilar el handoff: aqui solo
        # se persisten el context_hash y el handoff_json definitivos.
        self._storage.update_node_execution_handoff(
            node_execution_id=node_execution_id,
            context_hash=context_hash,
            handoff_json=json.dumps(handoff.to_dict(), sort_keys=False),
        )

        # Invocar Adapter
        try:
            result = self._adapter.invoke(handoff)
        except Exception as exc:
            return self._fail_node_with(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=node_execution_id,
                node_name=node_name,
                exc=exc,
            )

        # Validar resultado (outcome declarado?)
        if not is_outcome_declared(result, plan, node_name):
            error_msg = f"outcome {result.outcome!r} no declarado en plan"
            self._mark_node_failed(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                node_execution_id=node_execution_id,
                node_name=node_name,
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
            events=events,
            run_id=run_id,
            node_execution_id=node_execution_id,
            result=result,
            context_hash=context_hash,
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
        knowledge = self._compile_knowledge(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_execution_id=node_execution_id,
            node=node,
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

    def _compile_knowledge(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_execution_id: str,
        node: WorkflowNode,
    ) -> HandoffKnowledge:
        """Resuelve la receta de contexto del nodo (H9-context-in-run).

        Si hay `recipe_resolver` y devuelve una ContextRecipe, compila
        via ContextController (claims/evidencias reales en `included`).
        Errores tipados del compilador (Stale, MissingObligatory,
        TokenBudget) se propagan: el nodo falla en vez de ejecutar el
        adapter con contexto incompleto.

        Sin resolver, o si el resolver devuelve None, degrada al stub
        `default-empty-recipe/v1` con `included=()`.
        """
        recipe_ref = node.metadata.get("ctx_recipe_ref") or self._recipe_ref
        if self._recipe_resolver is None:
            return HandoffKnowledge(recipe_ref=recipe_ref, included=())
        recipe = self._recipe_resolver(recipe_ref)
        if recipe is None:
            return HandoffKnowledge(recipe_ref=recipe_ref, included=())
        kctl = KnowledgeController(
            storage=self._storage,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        ctx = ContextController(knowledge=kctl)
        compiled = ctx.compile_handoff(
            recipe=recipe,
            run_id=run_id,
            node_execution_id=node_execution_id,
            definition_kind=node.kind,
            definition_name=node.name,
            definition_namespace=node.namespace,
            definition_revision=node.resource_revision,
            api_version=node.api_version,
            expected_result=node.expected_result,
        )
        return compiled.knowledge

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
        node_started_event = events.node_started(
            run_id=run_id, node_execution_id=node_execution_id
        )
        self._storage.start_node_execution_atomically(
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
        self._storage.complete_node_execution_atomically(
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
        self._storage.mark_node_failed_atomically(
            event=node_failed_event,
            node_execution_id=node_execution_id,
            error=error,
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
