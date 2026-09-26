"""Protocols de persistencia (WI-02a).

Estos Protocols definen el **contrato observable** que el core
(RunController, EventLog, KnowledgeController) consume. Las
implementaciones concretas viven en
``src/skillgraph/platform/sqlite_adapters.py`` (adapters SQLite)
y ``src/skillgraph/platform/storage.py`` mantiene una fachada
compatible con el código legacy.

Cada Protocol cubre una capability disjunta:

- :class:`RunRepository` — runs y node_executions.
- :class:`EventStore` — log append-only de ``runtime_events``.
- :class:`KnowledgeRepository` — sources, entities, claims,
  evidence, traces, recursos, relaciones.
- :class:`PromotionRepository` — outbox de promoción H7.
- :class:`PolicyStore` — políticas de redacción y budgets.

Reglas arquitectónicas (AGENTS.md §4.3):

- ``sqlite3.Connection`` **no sale** de
  ``src/skillgraph/platform/``. Los adapters SQLite son los
  únicos que reciben conexión; el resto del código consume
  estos Protocols.
- Atomicidad transaccional: el adapter SQLite expone
  operaciones compuestas (``*_atomically``) cuando la
  invariante es real (estado + evento en una transacción).
  No se modela UnitOfWork algebraico.

Este módulo NO contiene imports de runtime: las clases que
recibe (``RuntimeEvent``, ``Source``, ``Entity``, ``Claim``,
``Evidence``, ``Finding``, ``OutcomeTrace``, ``Brick``) se
importan en los adapters, no aquí. Los Protocols usan tipos
genéricos ``Any`` solo donde el adapter los acepta; el código
de aplicación puede refinarlos.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Note: ``@runtime_checkable`` se aplica selectivamente. Solo
# ``RunRepository`` y ``EventStore`` lo llevan en WI-02a porque son
# los que RunController consume. El resto de Protocols son
# estructurales (duck typing) sin check en runtime; basta con
# que el adapter implemente los métodos con la firma correcta.
# ---------------------------------------------------------------------------


@runtime_checkable
class RunRepository(Protocol):
    """Operaciones sobre runs y node_executions.

    Consumido por :class:`skillgraph.runtime.runcontroller.RunController`.
    Las operaciones ``*_atomically`` preservan invariantes transaccionales
    (estado + evento en una sola transacción SQLite) y son obligatorias
    para que el RunController mantenga la regla "workflow state y event
    atomically" del blueprint.
    """

    # --- lecturas de runs ------------------------------------------------
    def find_active_run(self, *, tenant_id: str, project_id: str) -> str | None: ...

    def list_runs(
        self, *, tenant_id: str, project_id: str, state: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]: ...

    def get_run(self, *, tenant_id: str, project_id: str, run_id: str) -> dict[str, Any] | None: ...

    def list_events_for_run(self, *, tenant_id: str, project_id: str, run_id: str) -> list[Any]: ...

    def load_run(self, *, tenant_id: str, project_id: str, run_id: str) -> dict[str, Any]: ...

    def list_node_executions(
        self, *, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> list[dict[str, Any]]: ...

    def list_executed_node_names(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> tuple[str, ...]: ...

    # --- mutaciones simples ----------------------------------------------
    def recover_interrupted_node_executions(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> int: ...

    def transition_run_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None: ...

    def start_node_execution(
        self,
        *,
        node_execution_id: str,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
        context_hash: str,
        handoff_json: str,
    ) -> None: ...

    def complete_node_execution(
        self, *, node_execution_id: str, outcome: str, result_json: str
    ) -> None: ...

    def mark_node_failed(self, *, node_execution_id: str, error: str) -> None: ...

    def update_node_execution_handoff(
        self, *, node_execution_id: str, context_hash: str, handoff_json: str
    ) -> None: ...

    # --- mutaciones atómicas (compuestas) -------------------------------
    def start_node_execution_atomically(
        self,
        *,
        event: Any,
        node_execution_id: str,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
        context_hash: str,
        handoff_json: str,
    ) -> None: ...

    def complete_node_execution_atomically(
        self,
        *,
        event_completed: Any,
        event_evidence: Any,
        node_execution_id: str,
        outcome: str,
        result_json: str,
    ) -> None: ...

    def mark_node_failed_atomically(
        self, *, event: Any, node_execution_id: str, error: str
    ) -> None: ...

    def create_run(
        self, *, tenant_id: str, project_id: str, plan_json: str, initial_node: str
    ) -> str: ...

    def create_run_atomically(
        self,
        *,
        event: Any,
        tenant_id: str,
        project_id: str,
        plan_json: str,
        initial_node: str,
        run_id: str | None = None,
    ) -> str: ...

    def transition_run_state_atomically(
        self,
        *,
        event: Any,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None: ...


@runtime_checkable
class EventStore(Protocol):
    """Append-only log de ``runtime_events``.

    Consumido por :class:`skillgraph.runtime.engine.EventLog`
    (no migrado en WI-02a; queda como dependencia a
    ``PolicyStore`` y a este Protocol en WI-02b).
    """

    def record_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_id: str,
        event_kind: str,
        resource_ref: str,
        payload: Any,
        run_id: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        timestamp: str | None = None,
    ) -> int: ...

    def list_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
        resource_ref: str | None = None,
        event_kind: str | None = None,
    ) -> list[Any]: ...

    def list_events_for_run(self, *, tenant_id: str, project_id: str, run_id: str) -> list[Any]: ...

    def fetch_event_raw(self, *, event_id: str) -> Any | None:
        """Devuelve la fila raw por ``event_id`` o None.

        WI-02b: anadido para soportar ``EventLog.has_event`` sin
        importar a ``runtime_events`` ni exponer ``sql conn`` al caller.
        Implementacion SQLite hace ``SELECT * WHERE event_id = ?``.
        """

    def ensure_schema(self) -> None:
        """Idempotente: aplica la migracion del schema de ``runtime_events``.

        Llamado por :class:`EventLog` en su ``__init__``. Si el schema
        ya existe (caso comun tras primera invocacion), no hace nada.
        """

    # append() con un objeto RuntimeEvent se expone en WI-02b.


class KnowledgeRepository(Protocol):
    """Operaciones sobre sources, entities, claims, evidence, traces.

    Consumido por :class:`skillgraph.knowledge.knowledge_controller.KnowledgeController`.
    No migrado en WI-02a; queda como contrato declarado.
    """

    def register_source(self, *, tenant_id: str, project_id: str, source: Any) -> None: ...
    def get_source(self, *, tenant_id: str, project_id: str, source_id: str) -> Any | None: ...
    def list_sources(self, *, tenant_id: str, project_id: str) -> tuple[Any, ...]:
        """Sources del tenant/project (read-only).

        WI-03: cierra el escape hatch ``storage._conn.execute('SELECT
        source_id FROM sources ...')`` que ``receipts.list_applicable_receipts``
        usaba.
        """
        ...

    def update_source_freshness(
        self, *, tenant_id: str, project_id: str, source_id: str, freshness: str
    ) -> None: ...
    def upsert_entity(self, *, tenant_id: str, project_id: str, entity: Any) -> None: ...
    def get_entity(self, *, tenant_id: str, project_id: str, entity_id: str) -> Any | None: ...
    def find_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str,
        stable_key: str,
    ) -> Any | None:
        """Busca una Entity por (kind, stable_key). None si no existe.

        Reemplaza el acceso directo a ``storage._conn`` que hacia
        ``KnowledgeController.find_entity`` antes de WI-02b.
        """

    def source_exists_anywhere(self, *, source_id: str) -> bool:
        """True si el ``source_id`` existe en cualquier tenant/project.

        Usado por ``KnowledgeController`` para distinguir
        ``UnknownSourceError`` por typo vs por pertenencia a otro
        proyecto (regla de leakage cross-tenant ADR-0015).
        """

    def list_claims_for_subject(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
    ) -> list[Any]:
        """Lista Claims de un sujeto, con evidence_ids pre-cargados.

        Reemplaza el patron N+1 de ``KnowledgeController.
        list_claims_for_subject`` que iteraba row por row haciendo
        una query adicional a ``claim_evidence``.
        """

    def record_evidence(self, *, tenant_id: str, project_id: str, evidence: Any) -> None: ...
    def get_evidences_for_claim(
        self, *, tenant_id: str, project_id: str, claim_id: str
    ) -> tuple[Any, ...]: ...
    def record_claim(self, *, tenant_id: str, project_id: str, claim: Any) -> str: ...
    def get_claim(self, *, tenant_id: str, project_id: str, claim_id: str) -> Any | None: ...
    def list_claims_for_source(
        self, *, tenant_id: str, project_id: str, source_id: str
    ) -> list[Any]: ...
    def list_claims_by_predicate(
        self, *, tenant_id: str, project_id: str, predicate: str
    ) -> tuple[Any, ...]: ...
    def list_evidences_for_source(self, *, source_id: str) -> tuple[Any, ...]: ...
    def list_resource_refs_for_run(
        self, *, tenant_id: str, project_id: str, run_id: str, kind: str
    ) -> tuple[str, ...]: ...
    def attach_evidence_to_claim(
        self, *, tenant_id: str, project_id: str, claim_id: str, evidence_id: str
    ) -> None: ...
    def record_finding(self, *, tenant_id: str, project_id: str, finding: Any) -> None: ...
    def record_trace(self, *, tenant_id: str, project_id: str, trace: Any) -> None: ...
    def link_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace_id: str,
        link_kind: str,
        link_id: str,
        position: int,
    ) -> None: ...
    # Recursos / relaciones (cubren la capability 'resources').
    def upsert_resource(self, brick: Any) -> str: ...
    def get_resource(self, uid: str) -> dict[str, Any] | None: ...
    def list_resources(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str | None = None,
    ) -> list[dict[str, Any]]: ...
    def add_relation(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_uid: str,
        target_uid: str,
        kind: str,
        properties: dict[str, Any] | None = None,
    ) -> str: ...
    def dependencies_of(self, uid: str) -> list[dict[str, Any]]: ...
    def dependents_of(self, uid: str) -> list[dict[str, Any]]: ...

    # --- WI-02b: puertos de mantenimiento (invalidation, refresh) ---

    def list_claims_using_evidence(self, *, evidence_id: str) -> tuple[Any, ...]:
        """Yield ClaimID de las claims que referencian una evidence.

        Sustituye ``controller.storage._conn.execute('SELECT claim_id
        FROM claim_evidence WHERE evidence_id = ?')`` que hacia
        ``KnowledgeInvalidator._claims_using_evidence``.
        """

    def mark_claims_stale(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_ids: tuple[str, ...],
    ) -> None:
        """Marca stale=1 las claims indicadas (atomicidad: 1 transaccion).

        Sustituye el bucle con ``UPDATE claims SET stale = 1 WHERE
        claim_id = ?`` que hacia ``invalidate_from_source``.
        """

    def reactivate_claims_with_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        new_revision: str,
    ) -> tuple[str, ...]:
        """Marca stale=0 las Claims que referencian ``new_revision``.

        Devuelve los claim_ids reactivados en una sola query
        (``UPDATE ... RETURNING claim_id``).
        """

    def list_stale_claims(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[Any, ...]:
        """Lista todas las Claims stale (con evidence_ids pre-cargados).

        Sin N+1: una sola query con LEFT JOIN a ``claim_evidence``.
        """

    def record_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_id: str,
        event_kind: str,
        resource_ref: str,
        payload: Any,
        run_id: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Escribir un evento. WI-02b: KC/KI emiten eventos de mantenimiento.

        Delegado al EventStore real. Storage cumple ambos Protocols
        por duck typing."""


class PromotionRepository(Protocol):
    """Outbox de promoción entre proyectos (H7)."""

    def register_promotion(
        self,
        *,
        proposal_id: str,
        idempotency_key: str,
        tenant_id: str,
        source_project: str,
        target_catalog: str,
        knowledge_ref: str,
        payload: dict[str, Any],
    ) -> None: ...
    def get_promotion(self, proposal_id: str) -> dict[str, Any] | None: ...
    def list_pending_promotions(self) -> list[dict[str, Any]]: ...


class PolicyStore(Protocol):
    """Políticas de redacción por tenant y budgets por run.

    Consumido por :class:`skillgraph.runtime.engine.EventLog`
    (para resolver la política de redacción) y por
    :class:`skillgraph.runtime.runcontroller.RunController`
    (para consultar el budget activo).
    """

    def get_policy(self, *, tenant_id: str) -> str | None: ...
    def upsert_policy(self, *, tenant_id: str, policy: str) -> None: ...
    def upsert_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        max_visits: int | None,
        max_runtime_seconds: int | None,
        max_events: int | None,
    ) -> None: ...
    def get_budget(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> dict[str, Any] | None: ...


__all__ = [
    "EventStore",
    "KnowledgeRepository",
    "PolicyStore",
    "PromotionRepository",
    "RunRepository",
]
