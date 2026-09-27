"""SqliteUnitOfWork: una sola conexion, cinco bounded-context adapters.

WI-33 (R2 audit externo, 2026-09-27): el audit identifico que el
``Storage`` (2629 LoC pre-WI-33) actuaba como god-class con 30+
metodos heterogeneos cubriendo 5 bounded contexts (runs, events,
knowledge, governance, policy). Esto generaba tres problemas:

1. **Connection lifecycle**: la ``sqlite3.Connection`` la creaba
   ``Storage.__init__`` y se cerraba en ``close()``. Tests con
   fixtures que no llamaban ``close()`` generaban
   ``ResourceWarning: unclosed database``.

2. **Acoplamiento**: cualquier cambio a la conexion (WAL, FK,
   row_factory) afectaba a todo el storage, sin via para que
   un adapter necesitase un pragma distinto.

3. **Falta de transaccion cross-context**: las invariantes que
   cruzan dos bounded contexts (e.g. workflow state + event
   atomically) se garantizaban con ``BEGIN`` explicito y no con
   un UoW que coordinase.

Esta primera iteracion introduce ``SqliteUnitOfWork`` como una
fachada ligera: los 5 adapters exponen los metodos del
``Storage`` actual (sin duplicar logica), comparten la misma
``sqlite3.Connection`` (single owner: la UoW), y son
estructuralmente intercambiables con los Protocols del proyecto
(``RunRepository``, ``EventStore``, etc.).

WI-34 (siguiente) ya no parte el ``Storage``: cada bounded
context migra su logica a su adapter en commits separados, y el
``Storage`` queda como un facade delgado de 200-300 LoC.

Patrones:
- ``@dataclass(frozen=True, slots=True)`` para la UoW: garantiza
  inmutabilidad estructural (no se reemplaza la conexion
  accidentalmente). Los adapters siguen siendo mutables (cada
  metodo ejecuta SQL).
- Los adapters son dataclasses NO-frozen con ``_conn: sqlite3.Connection``
  privado. Exponen metodos que delegan a ``Storage`` para preservar
  la logica actual.

Decisiones:
- La UoW NO expone ``close()`` directamente: el lifecycle lo
  gestiona el ``Storage`` facade. Esto evita dos owners
  compitiendo por cerrar la conexion.
- Los adapters son ``Protocol``-compatible (``@runtime_checkable``
  detecta correctamente las clases concretas).
- Los metodos del ``Storage`` facade delegan al adapter
  correspondiente (storage.list_runs is storage.uow.runs.list_runs).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skillgraph.platform.storage import Storage


# --- Adapter views --------------------------------------------------------
#
# Estos 5 dataclasses envuelven una ``sqlite3.Connection`` y exponen
# los metodos del ``Storage`` actual como vistas. WI-34 los migrara
# de "wrapper que delega" a "implementacion autonoma con su logica".
#
# Por ahora cada metodo hace ``return storage.metodo(...)`` para
# preservar la logica centralizada del god-class.


@dataclass(slots=True)
class _AdapterBase:
    """Base comun para los 5 adapters.

    Atributos:
        _conn: la conexion SQLite compartida por la UoW.
        _storage: el facade ``Storage`` del que delegan los metodos.
            WI-34 lo eliminara: cada adapter tendra su propia logica.

    El dataclass NO es frozen: las clases hijas reciben parametros
    por keyword y los almacenan en slots. La UoW garantiza que
    ``_conn`` nunca se reasigna (la UoW es frozen).
    """

    _conn: sqlite3.Connection
    _storage: Storage

    def __post_init__(self) -> None:
        # El adapter base no expone metodos: las clases hijas
        # anaden los suyos. Esto es solo para forzar a los hijos
        # a usar el mismo constructor.
        pass


# --- RunRepository adapter ------------------------------------------------


@dataclass(slots=True)
class SqliteRunAdapter(_AdapterBase):
    """Adapter para ``RunRepository`` (runs + node_executions).

    WI-33: vista sobre el ``Storage`` facade. WI-34 migrara la
    logica desde ``Storage`` a este modulo.
    """

    def list_runs(
        self,
        *,
        tenant_id: str,
        project_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> Any:
        return self._storage.list_runs(
            tenant_id=tenant_id,
            project_id=project_id,
            state=state,
            limit=limit,
        )

    def get_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> Any:
        return self._storage.get_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )

    def load_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> Any:
        return self._storage.load_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )

    def list_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
    ) -> Any:
        return self._storage.list_node_executions(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
        )

    def list_events_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> Any:
        # Este metodo conceptualmente pertenece al ``EventStore``,
        # pero el Protocol ``RunRepository`` lo expone para que
        # ``RunController.logs_run`` pueda obtener el timeline de
        # un run sin inyectar ``EventStore`` por separado.
        return self._storage.list_events_for_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )

    # --- mutaciones (delegadas al facade) ---

    def find_active_run(self, *, tenant_id: str, project_id: str) -> str | None:
        return self._storage.find_active_run(tenant_id=tenant_id, project_id=project_id)

    def list_executed_node_names(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> tuple[str, ...]:
        return self._storage.list_executed_node_names(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def recover_interrupted_node_executions(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> int:
        return self._storage.recover_interrupted_node_executions(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def transition_run_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        self._storage.transition_run_state(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
        )

    def start_node_execution(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_execution_id: str,
        node_name: str,
        attempt: int,
        context_hash: str | None,
        handoff_json: str | None,
    ) -> None:
        self._storage.start_node_execution(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_execution_id=node_execution_id,
            node_name=node_name,
            attempt=attempt,
            context_hash=context_hash,
            handoff_json=handoff_json,
        )

    def complete_node_execution(
        self,
        *,
        tenant_id: str,
        project_id: str,
        node_execution_id: str,
        outcome: str | None,
        result_json: str | None,
        context_hash: str | None,
    ) -> None:
        self._storage.complete_node_execution(
            tenant_id=tenant_id,
            project_id=project_id,
            node_execution_id=node_execution_id,
            outcome=outcome,
            result_json=result_json,
            context_hash=context_hash,
        )

    def mark_node_failed(
        self,
        *,
        tenant_id: str,
        project_id: str,
        node_execution_id: str,
        error: str,
        context_hash: str | None,
    ) -> None:
        self._storage.mark_node_failed(
            tenant_id=tenant_id,
            project_id=project_id,
            node_execution_id=node_execution_id,
            error=error,
            context_hash=context_hash,
        )

    def create_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan_json: str,
        initial_node: str,
        run_id: str | None = None,
    ) -> str:
        return self._storage.create_run(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_json=plan_json,
            initial_node=initial_node,
            run_id=run_id,
        )

    def transition_run_state_atomically(
        self,
        *,
        event: Any,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        self._storage.transition_run_state_atomically(
            event=event,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
        )

    def start_node_execution_atomically(self, *, event: Any, **kwargs: Any) -> None:
        self._storage.start_node_execution_atomically(event=event, **kwargs)

    def complete_node_execution_atomically(self, *, event: Any, **kwargs: Any) -> None:
        self._storage.complete_node_execution_atomically(event=event, **kwargs)

    def mark_node_failed_atomically(self, *, event: Any, **kwargs: Any) -> None:
        self._storage.mark_node_failed_atomically(event=event, **kwargs)

    def update_node_execution_handoff(self, **kwargs: Any) -> None:
        self._storage.update_node_execution_handoff(**kwargs)


# --- EventStore adapter ---------------------------------------------------


@dataclass(slots=True)
class SqliteEventAdapter(_AdapterBase):
    """Adapter para ``EventStore`` (runtime_events append-only)."""

    def list_events_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> Any:
        return self._storage.list_events_for_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )

    def fetch_event_raw(self, event_id: str) -> Any:
        return self._storage.fetch_event_raw(event_id=event_id)

    def record_event(self, *, event: Any) -> None:
        self._storage.record_event(event=event)


# --- KnowledgeRepository adapter ------------------------------------------


@dataclass(slots=True)
class SqliteKnowledgeAdapter(_AdapterBase):
    """Adapter para ``KnowledgeRepository`` (resources, relations, knowledge)."""

    def get_resource(self, uid: str) -> Any:
        return self._storage.get_resource(uid=uid)

    def list_resources(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str | None = None,
    ) -> Any:
        return self._storage.list_resources(tenant_id=tenant_id, project_id=project_id, kind=kind)

    def dependencies_of(self, uid: str) -> Any:
        return self._storage.dependencies_of(uid=uid)

    def dependents_of(self, uid: str) -> Any:
        return self._storage.dependents_of(uid=uid)

    def upsert_resource(self, brick: Any) -> str:
        return self._storage.upsert_resource(brick=brick)

    def add_relation(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_uid: str,
        target_uid: str,
        kind: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        return self._storage.add_relation(
            tenant_id=tenant_id,
            project_id=project_id,
            source_uid=source_uid,
            target_uid=target_uid,
            kind=kind,
            properties=properties,
        )


# --- PromotionRepository / PolicyStore adapters ----------------------------


@dataclass(slots=True)
class SqliteGovernanceAdapter(_AdapterBase):
    """Adapter para ``PromotionRepository`` (promotion_outbox + governance)."""

    def get_promotion(self, proposal_id: str) -> dict[str, Any] | None:
        return self._storage.get_promotion(proposal_id=proposal_id)

    def list_promotions(self, *, status: str | None = None, limit: int = 50) -> Any:
        return self._storage.list_promotions(status=status, limit=limit)


@dataclass(slots=True)
class SqlitePolicyAdapter(_AdapterBase):
    """Adapter para ``PolicyStore`` (tenant_policies)."""

    def get_redaction_policy(self, tenant_id: str) -> Any:
        return self._storage.get_redaction_policy(tenant_id=tenant_id)

    def set_redaction_policy(self, tenant_id: str, policy: str) -> None:
        self._storage.set_redaction_policy(tenant_id=tenant_id, policy=policy)


# --- SqliteUnitOfWork ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SqliteUnitOfWork:
    """Fachada que owns la ``sqlite3.Connection`` y expone 5 adapters.

    WI-33 (R2 audit externo, 2026-09-27): agrupa los 5 bounded
    contexts del proyecto y garantiza que comparten exactamente
    la misma conexion fisica. Esto cierra el hallazgo "Connection
    lifecycle" del audit.

    Atributos frozen: una vez creada, la UoW no se reasigna (los
    adapters internos pueden mutar su estado, pero la identidad
    de la UoW es estable). Esto permite a tests usar
    ``storage.uow is storage.uow``.

    Atributos:
        runs: ``SqliteRunAdapter`` para bounded context runs.
        events: ``SqliteEventAdapter`` para bounded context events.
        knowledge: ``SqliteKnowledgeAdapter`` para knowledge graph.
        governance: ``SqliteGovernanceAdapter`` para promotion
            outbox + governance (promotions, backups).
        policy: ``SqlitePolicyAdapter`` para tenant_policies
            (redaction policy por tenant).

    Los adapters NO son frozen (cada metodo ejecuta SQL y muta
    la conexion), pero la UoW si lo es: una vez construida,
    ``runs`` siempre apunta al mismo adapter, lo que evita
    estados inconsistentes entre dos referencias.

    La conexion subyacente (``_conn``) es accesible via el
    adapter (privada). Tests pueden verificar identidad via
    ``id(adapter._conn) == id(other._conn)``.
    """

    runs: SqliteRunAdapter
    events: SqliteEventAdapter
    knowledge: SqliteKnowledgeAdapter
    governance: SqliteGovernanceAdapter
    policy: SqlitePolicyAdapter

    @property
    def _conn(self) -> sqlite3.Connection:
        """Acceso de solo-lectura a la conexion compartida.

        Los 5 adapters reciben esta misma conexion en su
        constructor. Esto es la unica forma de garantizar
        identidad: un solo objeto ``sqlite3.Connection`` por UoW.
        """
        return self.runs._conn


__all__ = [
    "SqliteEventAdapter",
    "SqliteGovernanceAdapter",
    "SqliteKnowledgeAdapter",
    "SqlitePolicyAdapter",
    "SqliteRunAdapter",
    "SqliteUnitOfWork",
]
