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

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from skillgraph.core.errors import ValidationError
from skillgraph.core.runtime_types import RunState, is_terminal_run_state
from skillgraph.platform.ports import (
    EventStore,
    KnowledgeRepository,
    PolicyStore,
    RunRepository,
    StoredRun,
)

# B3-cierre: por la RUTA COMPLETA, y no desde `platform.ports`. B3
# decidio explicitamente que `capabilities` NO se reexporta desde el
# indice de WI-69 —catorce tipos, contrato cerrado con su propio test— y
# anadirlo seria cambiar ese contrato desde otro bloque. La ruta
# completa deja ademas el origen a la vista cuando alguien busca de
# donde sale una capability.
from skillgraph.platform.ports.capabilities import CapabilityNotFound, CapabilityRegistry
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.agent import AgentAdapter
from skillgraph.runtime.capability_controller import CapabilityController
from skillgraph.runtime.engine import EventBuilder, EventLog
from skillgraph.runtime.locks import (
    LockMode,
    RunLock,
    RunLockKey,
)
from skillgraph.runtime.run_types import (
    BudgetViolationKind,
    RunBudget,
    RunSnapshot,
    RuntimeEventLog,
    _noop_lock,
    has_self_loop,
    is_outcome_declared,
    new_node_execution_id,
    new_run_id,
    plan_from_json,
    plan_to_json,
    result_to_jsonable,
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
from skillgraph.runtime.node_execution_delegations import (
    MAX_NODE_ATTEMPTS,
    NodeExecutionDelegations,
    _NodeExecution,
    _NodeGuard,
)
from skillgraph.runtime.run_budget_delegations import RunBudgetDelegations
from skillgraph.runtime.run_observability_delegations import (
    RunObservabilityDelegations,
)


class RunController(
    NodeExecutionDelegations,
    RunObservabilityDelegations,
    RunBudgetDelegations,
):
    """Orquestador del bucle de reconciliacion para un proyecto."""

    def __init__(
        self,
        *,
        runs: RunRepository,
        events: EventStore,
        policy: PolicyStore,
        adapter: AgentAdapter,
        recipe_resolver: Callable[[str], ContextRecipe | None] | None = None,
        knowledge: KnowledgeRepository | None = None,
        capabilities: CapabilityRegistry | None = None,
        lock_dir: Path | None = None,
        lock_mode: LockMode = "none",
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        # WI-02a: ``RunController`` depende de los Protocols
        # ``RunRepository``, ``EventStore`` y ``PolicyStore``. La
        # conexión SQLite queda contenida en
        # ``src/skillgraph/platform/``; el controlador no ve ni
        # ``Storage`` ni ``sqlite3.Connection``. La fachada
        # ``Storage`` implementa los 5 Protocols por duck typing
        # y expone factorías (``storage.run_repository()`` etc.)
        # para inyección granular. Tests legacy que construyen
        # ``RunController(storage=Storage(...), ...)`` siguen
        # funcionando durante el WI-02a; en WI-02b se elimina
        # el kwarg ``storage=``.
        self._runs = runs
        self._policy = policy
        self._adapter = adapter
        # WI-31: ``knowledge`` (opcional) es el ``KnowledgeRepository``
        # que ``_compile_knowledge`` usara cuando el recipe_resolver
        # devuelva una receta. Si es None (default), el camino
        # ``recipe_resolver is not None`` se sigue cortocircuitando
        # al stub ``default-empty-recipe/v1`` (incluido=()) y el
        # atributo no se usa. Esto elimina el antiguo ``cast(Storage,
        # self._runs)`` que era un workaround del type checker
        # para tratar ``RunRepository`` como ``KnowledgeRepository``
        # (Storage los implementa ambos por structural subtyping).
        # ``Storage`` satisface los dos Protocols; al separarse en
        # WI-02b (cuando ``RunRepository`` deja de cumplir duck
        # typing de knowledge), el caller debera pasar
        # explícitamente ``knowledge=storage.knowledge_repository()``.
        self._knowledge: KnowledgeRepository | None = knowledge
        # B3-cierre: la costura que hace ALCANZABLE el puerto de
        # capabilities desde produccion. Sin esto, el gate de B3 se
        # cumplia en vacio: se podia anadir una capability sin tocar el
        # core porque el core no la veia nunca. Medido antes de escribir
        # nada (criterio declarado por delante): 16 construcciones de
        # `CapabilityRegistry` en el arbol, las 16 en tests, cero
        # importadores del puerto bajo `src/`.
        #
        # LA POLITICA, Y POR QUE EL DEFAULT ES `None`. La exigencia la
        # PIDE quien despliega, y solo si la pide:
        #
        # - `None` (default): comportamiento EXACTAMENTE el de antes. Un
        #   plan que declara `'stale'` —que no es una capability sino un
        #   `FreshnessState`, y que `build_capabilities` produce— sigue
        #   ejecutandose igual. Cero ruptura, y por eso esto se puede
        #   aterrizar sin migrar nada.
        # - con registro: lo que el plan declara tiene que existir. Si no,
        #   el nodo queda FAILED con `CapabilityNotFound`, que es un
        #   `SkillGraphError` con `code`, traducible a exit code.
        #
        # Exigir siempre habria roto los 9 sitios que construyen
        # `node.capabilities` y los 30 que lo leen. Exigir nunca habria
        # dejado el puerto sin consumidor, que es el estado medido.
        #
        # LO QUE NO SE AFIRMA: que las capabilities se invoquen durante la
        # ejecucion. No se invocan. `Handoff.capabilities` sigue siendo un
        # `tuple[str, ...]` porque cambiar su forma esta MEDIDO como
        # ruptura de datos (`runtime/handoff.py:195` lo mete en el hash
        # firmado), y es materia de B8. Lo que se hace es que la
        # declaracion tenga un consumidor que la verifique, en vez de
        # viajar a un prompt sin que nadie la mire.
        self._capabilities: CapabilityRegistry | None = capabilities
        # S6 Etapa 7: configuracion de locks por run_id.
        # `lock_dir=None` + `lock_mode='none'` = no locks (compat
        # pre-S6; tests existentes no se enteran). Cualquier otra
        # combinacion activa la proteccion.
        self._lock_dir = Path(lock_dir) if lock_dir is not None else None
        self._lock_mode: LockMode = lock_mode
        self._lock_timeout_seconds = lock_timeout_seconds
        # S5 Etapa 7: el EventLog aplica redaccion al payload
        # antes de persistir. ``policy`` es el ``PolicyStore``
        # desde el que se resuelve la politica por tenant_id.
        # Sin politica configurada, el resolver devuelve ``None``
        # y EventLog usa el default seguro "metadata".
        #
        # WI-02b AC-3: ``EventLog`` acepta directamente el Protocol
        # ``EventStore`` (que ``events`` ya cumple por duck typing).
        # Antes usabamos ``events.conn`` (escape hatch WI-02a,
        # eliminado en T-16 / AC-4).
        self._events = EventLog(
            events,
            policy_resolver=lambda tenant_id: policy.get_policy(tenant_id=tenant_id),
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
        with self._locked_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id):
            result = self._runs.create_run_atomically(
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
                self._policy.upsert_budget(
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
        with self._locked_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id):
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
        plan = plan_from_json(run.plan_json)

        # UAT-06: si un NodeExecution quedo RUNNING sin finished_at,
        # lo devolvemos a READY (interrupcion).
        self._recover_interrupted(tenant_id, project_id, run_id)

        if is_terminal_run_state(run.state):
            return self._snapshot(tenant_id, project_id, run_id)

        # Activar el run si estaba CREATED.
        if run.state == "CREATED":
            self._set_run_state(tenant_id, project_id, run_id, "ACTIVE", plan.initial)

        match self._execute_frontier(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            plan=plan,
        ):
            case "node_failed":
                # FAILED terminal: paramos. La transicion y su evento
                # ya ocurrieron dentro de _execute_frontier.
                return self._snapshot(tenant_id, project_id, run_id)
            case "frontier_consumed":
                pass

        self._finalize_settled_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            plan=plan,
        )
        return self._snapshot(tenant_id, project_id, run_id)

    def _execute_frontier(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
    ) -> Literal["node_failed", "frontier_consumed"]:
        """Ejecuta los nodos de la frontier actual, uno como maximo por
        diseno (ver comentario al final del bucle).

        Devuelve "node_failed" si un nodo fallo (el run ya esta en
        FAILED, con su evento emitido atomicamente) o
        "frontier_consumed" si la pasada termino sin fallo, agote la
        frontier de golpe o el puntero se quedo sin sucesor.
        """
        for node_name in self._calculate_frontier(tenant_id, project_id, run_id, plan):
            ok = self._execute_one(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                plan=plan,
                node_name=node_name,
            )
            if ok is False:
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
                return "node_failed"

            # Si el nodo completado no tiene sucesor, el run termina.
            last = self._latest_node_execution(tenant_id, project_id, run_id, node_name)
            if last is None or last.state != "SUCCEEDED":
                continue
            next_name = plan.successors(node_name, last.outcome or "")
            if next_name is None:
                break
            # Avanzar el puntero current_node al siguiente.
            self._set_run_state(tenant_id, project_id, run_id, "ACTIVE", next_name)
            # Por diseno: una pasada ejecuta UN nodo. El caller
            # (CLI o scheduler externo) llama a reconcile_run de
            # nuevo para avanzar el siguiente. Esto cumple la
            # propiedad del blueprint: cada pasada del bucle es
            # determinista y reversible.

        return "frontier_consumed"

    def _finalize_settled_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
    ) -> None:
        """Cierra el run si su frontier quedo vacia.

        Si queda frontier, el run sigue ACTIVE y no se emite nada: el
        caller decide si lanza otra pasada.
        """
        # Si frontier vacia -> terminamos.
        # Caso H4 budget exhausted: current con self-loop y max_visits
        # agotado -> FAILED. Caso DAG normal -> COMPLETED.
        prev_current = self._load_run(tenant_id, project_id, run_id).current_node
        new_frontier = self._calculate_frontier(tenant_id, project_id, run_id, plan)
        if new_frontier:
            return
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
        # `Storage.load_run` lanza NotFoundError si el run no existe.
        run = self._runs.load_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        state = run.state
        if is_terminal_run_state(state):
            raise ValidationError(f"Run {run_id!r} ya es terminal ({state}); no se puede cancelar")
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
        self._runs.transition_run_state_atomically(
            event=event,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
        )

    # ---------- internals ----------

    def _load_run(self, tenant_id: str, project_id: str, run_id: str) -> StoredRun:
        # Lectura pura: delega en `Storage.load_run` (H9-BSlice3-S1).
        # WI-32.4: devuelve ``StoredRun`` (DTO inmutable) en vez de
        # ``dict``. Los consumidores internos del RunController usan
        # atributos (no ``["key"]``), eliminando el ``dict[str, Any]``
        # que el audit externo senalo como fuga de persistencia.
        return self._runs.load_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id)

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
        self._runs.transition_run_state(
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
        self._runs.recover_interrupted_node_executions(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def _verificar_capabilities(self, *, node: WorkflowNode) -> None:
        """Comprueba que el despliegue sepa lo que el nodo declara.

        **POR QUE LA LLAMADA ESTA EN `_compile_node_handoff`.** Dentro del
        `try` de ahi, y por dos razones que dependen la una de la otra: ese
        `except SkillGraphError` ya sabe persistir el fallo con su mensaje,
        y esa fase corre ANTES de `_invoke_node_adapter`. De las dos sale la
        propiedad que no se ve en la fila del nodo: un plan mal declarado no
        llega a **gastar una llamada al adapter**. Un plan que paga una
        llamada de red y luego falla PARECE funcional, y esa fila en la base
        es la unica que delata que no lo fue.

        **NO HACE NADA si no hay registro inyectado.** Esa es la politica,
        y esta escrita en `__init__`: la exigencia la pide quien despliega.
        Sin registro, un plan que declara `'stale'` —que no es una
        capability— sigue ejecutandose como antes, y por eso esto se puede
        aterrizar sin migrar nada.

        Delega en `CapabilityController.missing`, que ya existe, en vez de
        repetir el calculo: el criterio de «falta» vive en un sitio, y
        dos copias de un criterio divergen sin que nada lo note.

        Lanza `CapabilityNotFound` —un `SkillGraphError` con `code`, que la
        CLI traduce a exit code (WI-109)— y el `except` del llamante lo
        convierte en nodo FAILED. No devuelve una lista: la ausencia de
        una capability que el plan promete es un fallo del despliegue, y
        devolverla convertiria un error en un dato que alguien interpretara
        como «no hay nada que hacer».
        """
        if self._capabilities is None:
            return
        kernel = CapabilityController(registry=self._capabilities)
        faltan = kernel.missing(node.capabilities)
        if faltan:
            raise CapabilityNotFound(
                f"el nodo {node.name!r} declara {list(faltan)} y este "
                f"despliegue no las resuelve. Resuelve: "
                f"{list(kernel.types) or '(ninguna)'}"
            )

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
        # WI-31: el ``KnowledgeRepository`` se inyecta por constructor
        # (``knowledge=...``). Sin el, el code path se cortocircuita al
        # stub ``default-empty-recipe/v1`` (incluido=()). Esto elimina
        # el antiguo ``cast(Storage, self._runs)`` que era un workaround
        # del type checker.
        if self._knowledge is None:
            return HandoffKnowledge(recipe_ref=recipe_ref, included=())
        kctl = KnowledgeController(
            knowledge=self._knowledge,
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


# Re-exports de WI-67. Varios modulos y tests importan estos nombres
# DESDE `runcontroller` aunque su definicion este ahora en los mixin
# por dominio. Declararlos aqui los marca como usados: sin esto ruff
# los borra por F401 en cuanto `RunController` deja de referenciarlos,
# y la rotura aparece como ImportError en otro modulo, no aqui.
# NO eliminar sin migrar esos imports.
__all__ = [
    "MAX_NODE_ATTEMPTS",
    "BudgetViolationKind",
    "NodeExecutionDelegations",
    "RunBudget",
    "RunBudgetDelegations",
    "RunController",
    "RunObservabilityDelegations",
    "RunSnapshot",
    "RuntimeEventLog",
    "_NodeExecution",
    "_NodeGuard",
    "has_self_loop",
    "is_outcome_declared",
    "new_node_execution_id",
    "new_run_id",
    "plan_from_json",
    "plan_to_json",
    "result_to_jsonable",
]
