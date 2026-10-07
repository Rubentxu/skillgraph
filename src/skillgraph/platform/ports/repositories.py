"""Protocols de persistencia: el contrato que consume el core.

WI-69. Desdoblamiento de `ports/__init__.py` (927 LoC) en `dto`
(tipos almacenados) y `repositories` (Protocols), con `__init__`
como indice de re-export.

Por que: el audit marca >800 LoC por fichero y este lo supera por
ANCHURA (14 tipos), no por profundidad: la clase mayor es
`KnowledgeRepository` con 179 LoC. La razon de cambio que si
justificaba el corte es la separacion entre lo que se persiste y
los contratos que lo consumen, con dependencia unidireccional
(los Protocols importan los DTO, nunca al reves).

`from skillgraph.platform.ports import <cualquiera>` sigue
funcionando: `__init__` reexporta los catorce y los declara en
`__all__`. Red: `tests/test_wi69_ports_split.py`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from skillgraph.platform.ports.dto import (
    StoredClaim,
    StoredEvent,
    StoredEvidence,
    StoredNodeExecution,
    StoredRelation,
    StoredResource,
    StoredRun,
)


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
    ) -> list[StoredRun]: ...

    def get_run(self, *, tenant_id: str, project_id: str, run_id: str) -> StoredRun: ...

    def list_events_for_run(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> list[StoredEvent]: ...

    def load_run(self, *, tenant_id: str, project_id: str, run_id: str) -> StoredRun: ...

    def list_node_executions(
        self, *, tenant_id: str, project_id: str, run_id: str, node_name: str
    ) -> list[StoredNodeExecution]: ...

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

    def list_events_for_run(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> list[StoredEvent]: ...

    def fetch_event_raw(self, *, event_id: str) -> StoredEvent | None:
        """Devuelve el evento por ``event_id`` o None.

        WI-02b: anadido para soportar ``EventLog.has_event`` sin
        importar a ``runtime_events`` ni exponer ``sql conn`` al caller.
        Implementacion SQLite hace ``SELECT * WHERE event_id = ?`` y mapea
        ``Row -> StoredEvent`` (WI-32.2 R1 strict, audit 2026-09-27).

        WI-32.2: el retorno cambia de ``sqlite3.Row`` a ``StoredEvent``.
        Consumidores que necesiten filas raw pueden consultar
        ``Storage`` directamente (legacy); el Protocol ya no las expone.
        """

    def ensure_schema(self) -> None:
        """Idempotente: aplica la migracion del schema de ``runtime_events``.

        Llamado por :class:`EventLog` en su ``__init__``. Si el schema
        ya existe (caso comun tras primera invocacion), no hace nada.
        """


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
    def record_claim(self, *, tenant_id: str, project_id: str, claim: Any) -> Any:
        """Registra un claim.

        **B27: EL RETORNO DEJO DE SER UN `str`.** Antes devolvia el `claim_id`
        dado, y con `INSERT OR IGNORE` eso miente: el `UNIQUE` de la tupla
        natural puede rechazar el INSERT y devolvia igual, como si hubiera
        escrito. Ahora devuelve un valor con `.claim_id` y `.conflicto`, y el
        conflicto dice **que se solapa y con que valor**.

        Se declara `Any` y no el ADT concreto porque este modulo es un puerto:
        no debe conocer el ADT de `knowledge.graph`, que es del lado de arriba.
        """
        ...

    def conflicts_for(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
        revision: str | None = None,
    ) -> tuple[Any, ...]:
        """B27: los conflictos de un sujeto, consultables y ESTABLES.

        **B29: `revision` es parte del contrato, y no un extra.** Sin el, el
        unico conflicto que se puede ver es el de HEAD, y el de HEAD no es el
        unico que hay: MEDIDO, dos afirmaciones de la MISMA fuente en revisiones
        consecutivas daban un conflicto, y el sistema contestaba «gana NADIE» a
        algo que si tiene respuesta en cada instante. La ventana es lo que
        separa «cambio» de «contradiccion», y la ventana se pregunta por
        revision.

        En el puerto, para que un consumidor pueda preguntar por los conflictos
        sin abrir el componente de SQLite. Un dato que se guarda y no se puede
        preguntar es peor que no tenerlo.
        """
        ...

    def claims_at_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
        revision: str | None,
    ) -> tuple[Any, ...]:
        """B29: ¿qué afirmaciones eran CIERTAS en `revision`? `None` = HEAD.

        En el puerto por el mismo motivo que `conflicts_for`: es la mitad
        «consultable» de una fila de roadmap que decia que no se podia
        preguntar. Una revision que el store nunca ha visto devuelve vacio, y
        vacio no es error: es que no hay nada que dijera de ella.
        """
        ...

    def get_claim(self, *, tenant_id: str, project_id: str, claim_id: str) -> Any | None: ...
    def list_claims_for_source(
        self, *, tenant_id: str, project_id: str, source_id: str
    ) -> list[Any]: ...
    def list_claims_by_predicate(
        self, *, tenant_id: str, project_id: str, predicate: str
    ) -> tuple[StoredClaim, ...]: ...
    def list_evidences_for_source(self, *, source_id: str) -> tuple[StoredEvidence, ...]: ...
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
    def get_resource(self, uid: str) -> StoredResource | None: ...
    def list_resources(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str | None = None,
    ) -> list[StoredResource]: ...
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
    def dependencies_of(self, uid: str) -> list[StoredRelation]: ...
    def dependents_of(self, uid: str) -> list[StoredRelation]: ...

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

    def claims_desde_commit(
        self,
        *,
        tenant_id: str,
        project_id: str,
        commit_sha: str,
    ) -> tuple[Any, ...]:
        """B32: ¿qué afirmaciones se hicieron DESDE este commit?

        En el puerto por el mismo motivo que `claims_at_revision`: es la
        mitad «consultable» de una fila de roadmap que decia que no se
        podia preguntar. MEDIDO antes de escribirla: no existia ninguna
        consulta en `src/` que cruzara `claims.source_id` con
        `sources.git_commit_sha`, luego no era que faltara el indice —no
        habia ni la pregunta—.

        El SHA es la identidad porque es el contenido: no se puede reasignar
        ni mover debajo de otro commit. Y el alcance lleva `tenant_id` y
        `project_id` porque una ascendencia que cruza de proyecto responderia
        «qué dijo otro proyecto sobre este commit», que no es una pregunta
        que este sistema pueda contestar honestamente.

        Un commit del que este proyecto no tiene ninguna fuente devuelve
        vacio, y no es un error: una afirmacion es algo que ESTE proyecto
        afirmo.
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
