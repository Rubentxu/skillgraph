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

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# DTO de persistencia (WI-32.2 R1 strict, audit 2026-09-27):
#
# ``StoredEvent`` es el DTO inmutable que reemplaza el retorno de
# ``sqlite3.Row`` por el ``EventStore`` Protocol. La representacion
# SQLite se queda en ``platform/storage.py``; el resto del runtime
# consume estos DTOs. Esto cumple el objetivo 2 de WI-32:
#
#   "ningun ``sqlite3.Row`` fuera de ``platform/``"
#
# ``StoredEvent``:
#   - frozen=True, slots=True: inmutable, sin __dict__, footprint minimo.
#   - 12 campos 1:1 con la tabla ``runtime_events`` (sequence autogenerado).
#   - ``to_dict()`` para compatibilidad con consumers que esperan dict
#     (RunController.logs_run, EventLog.events_for_run legacy API).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """DTO inmutable de un evento persistido en ``runtime_events``.

    WI-32.2: sustituye ``sqlite3.Row`` en el contrato de
    :class:`EventStore`. El adapter SQLite (``Storage``) realiza la
    traduccion ``Row -> StoredEvent`` y la inversa en mutaciones.
    El resto del runtime (EventLog, RunController) opera exclusivamente
    sobre estos DTOs, sin importar ``sqlite3``.
    """

    sequence: int
    event_id: str
    tenant_id: str
    project_id: str
    event_kind: str
    run_id: str | None
    resource_ref: str
    causation_id: str | None
    correlation_id: str | None
    payload: dict[str, Any]
    timestamp: str
    schema_version: int

    def __getitem__(self, key: str) -> Any:
        """Compat legacy: ``event["payload_json"]`` -> ``event.payload``.

        WI-38 (R1 strict): los tests historicos subscriptan ``row["payload_json"]``
        y luego aplican ``json.loads()``. Mantenemos frozen=True delegando
        en ``getattr``; los campos son 1:1 con la tabla.

        ``payload_json`` (clave historica de la columna SQLite) devuelve
        el JSON serializado de ``payload`` (dict) para que los tests
        legacy que esperan string raw continen funcionando sin cambios.
        Lanza KeyError si la clave no es un campo del DTO.
        """
        if key == "payload_json":
            return json.dumps(self.payload, sort_keys=True)
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict para consumers que esperan API dict-legacy.

        Compatibilidad: ``RunController.logs_run`` y ``EventLog.events_for_run``
        exponen ``list[dict]`` en su API publica historica. Este metodo
        evita que esos consumidores tengan que conocer el DTO.
        """
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "event_kind": self.event_kind,
            "run_id": self.run_id,
            "resource_ref": self.resource_ref,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class StoredRun:
    """DTO inmutable de un Run persistido en ``workflow_runs``.

    WI-32.4: sustituye ``dict[str, Any]`` y ``sqlite3.Row`` en el
    contrato de :class:`RunRepository`. Los 8 campos reflejan 1:1
    la tabla ``workflow_runs`` (``sequence`` autogenerado, no
    almacenado: ``run_id`` es PK textual).

    ``current_node`` es opcional: ``None`` para runs en estado
    ``CREATED`` que aún no han avanzado.

    ``to_dict()`` preserva la API legacy (``RunController.show_run``
    y ``list_runs`` exponen ``list[dict]`` historicamente).
    """

    run_id: str
    tenant_id: str
    project_id: str
    state: str
    plan_json: str
    current_node: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict preservando todas las columnas.

        Compatibilidad con consumers (``RunController.show_run``,
        tests historicos) que esperan API dict-based.
        """
        return {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "state": self.state,
            "plan_json": self.plan_json,
            "current_node": self.current_node,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class StoredNodeExecution:
    """DTO inmutable de una NodeExecution persistida en ``node_executions``.

    WI-32.4: sustituye ``dict[str, Any]`` en el contrato de
    :class:`RunRepository`. Los 13 campos son 1:1 con la tabla
    ``node_executions``.

    ``outcome``, ``context_hash``, ``handoff_json``, ``result_json``,
    ``error``, ``started_at``, ``finished_at`` son opcionales: una fila
    recien creada via ``start_node_execution`` solo tiene ``state='RUNNING'``
    y los timestamps inicializados.
    """

    node_execution_id: str
    run_id: str
    tenant_id: str
    project_id: str
    node_name: str
    attempt: int
    state: str
    outcome: str | None
    context_hash: str | None
    handoff_json: str | None
    result_json: str | None
    error: str | None
    started_at: str | None
    finished_at: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict preservando todas las columnas."""
        return {
            "node_execution_id": self.node_execution_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "node_name": self.node_name,
            "attempt": self.attempt,
            "state": self.state,
            "outcome": self.outcome,
            "context_hash": self.context_hash,
            "handoff_json": self.handoff_json,
            "result_json": self.result_json,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass(frozen=True, slots=True)
class StoredResource:
    """DTO inmutable de un Resource persistido en ``resources``.

    WI-32.5: sustituye ``dict[str, Any]`` y ``sqlite3.Row`` en el
    contrato de :class:`KnowledgeRepository` para ``get_resource``
    y ``list_resources``. Los 12 campos son 1:1 con la tabla.

    ``spec_json`` y ``status_json`` mantienen la convencion JSON-as-text
    del resto del proyecto: el adapter (``Storage``) deserializa a
    ``dict`` solo en la capa de uso (registry); el DTO expone el
    texto crudo preservando la frontera de persistencia.
    """

    uid: str
    tenant_id: str
    project_id: str
    api_version: str
    kind: str
    namespace: str
    name: str
    resource_version: int
    generation: int
    spec_json: str
    status_json: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict preservando todas las columnas."""
        return {
            "uid": self.uid,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "api_version": self.api_version,
            "kind": self.kind,
            "namespace": self.namespace,
            "name": self.name,
            "resource_version": self.resource_version,
            "generation": self.generation,
            "spec_json": self.spec_json,
            "status_json": self.status_json,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class StoredRelation:
    """DTO inmutable de una Relation (arista) entre resources.

    WI-32.5: sustituye ``dict[str, Any]`` en ``dependencies_of`` y
    ``dependents_of``. Los 7 campos son 1:1 con la tabla ``relations``.

    ``properties_json`` es opcional (``None`` permitido por defecto
    via ``DEFAULT '{}'``): ``to_dict()`` lo serializa tal cual.
    """

    uid: str
    tenant_id: str
    project_id: str
    source_uid: str
    target_uid: str
    kind: str
    properties_json: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict preservando todas las columnas."""
        return {
            "uid": self.uid,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "source_uid": self.source_uid,
            "target_uid": self.target_uid,
            "kind": self.kind,
            "properties_json": self.properties_json,
        }


@dataclass(frozen=True, slots=True)
class StoredClaim:
    """DTO inmutable de un Claim persistido.

    WI-39 sustituye filas y diccionarios raw en las lecturas de claims.
    ``object_literal`` y ``evidence_ids`` ya vienen deserializados por
    el adapter SQLite.
    """

    claim_id: str
    tenant_id: str
    project_id: str
    subject_entity_id: str
    predicate: str
    object_literal: Any
    source_id: str
    evidence_ids: tuple[str, ...]
    extraction_method: str
    extractor_version: str
    checked_at_revision: str
    stale: bool

    def __getitem__(self, key: str) -> Any:
        """Compatibilidad explícita con consumidores históricos basados en filas."""
        if key == "object_literal_json":
            return json.dumps(self.object_literal, sort_keys=True)
        if key == "stale":
            return int(self.stale)
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Compatibilidad explícita con ``dict.get`` durante la migración."""
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Serializa preservando los nombres históricos de columnas."""
        return {
            "claim_id": self.claim_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "subject_entity_id": self.subject_entity_id,
            "predicate": self.predicate,
            "object_literal_json": json.dumps(self.object_literal, sort_keys=True),
            "source_id": self.source_id,
            "extraction_method": self.extraction_method,
            "extractor_version": self.extractor_version,
            "checked_at_revision": self.checked_at_revision,
            "stale": int(self.stale),
            "evidence_ids": self.evidence_ids,
        }


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    """DTO inmutable de una Evidence persistida.

    WI-39 sustituye filas y diccionarios raw en las lecturas de evidences.
    ``content`` ya viene deserializado por el adapter SQLite.
    """

    evidence_id: str
    tenant_id: str
    project_id: str
    kind: str
    content: Any
    source_id: str
    observed_at: str

    def __getitem__(self, key: str) -> Any:
        """Compatibilidad explícita con consumidores históricos basados en filas."""
        if key == "content_json":
            return json.dumps(self.content, sort_keys=True)
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Compatibilidad explícita con ``dict.get`` durante la migración."""
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Serializa preservando los nombres históricos de columnas."""
        return {
            "evidence_id": self.evidence_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "content_json": json.dumps(self.content, sort_keys=True),
            "source_id": self.source_id,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True)
class StoredPromotion:
    """DTO inmutable de una propuesta de promocion (promotion_outbox).

    WI-38 (R1 strict): sustituye ``dict[str, Any]`` en ``get_promotion``,
    ``list_pending_promotions`` y ``list_promotions``. Los 11 campos
    son 1:1 con la tabla ``promotion_outbox`` + ``payload`` (parseado
    desde ``payload_json``).

    ``to_dict()`` preserva el dict historico con ``payload_json`` (no
    parseado) para compatibilidad con consumers que esperan string raw.
    ``__getitem__`` permite subscript legacy (``p["status"]``) mientras
    se migran los tests que dependen de la API dict-based.
    """

    proposal_id: str
    idempotency_key: str
    tenant_id: str
    source_project: str
    target_catalog: str
    knowledge_ref: str
    payload: dict[str, Any]
    status: str
    attempts: int
    created_at: str
    updated_at: str
    published_at: str | None

    def __getitem__(self, key: str) -> Any:
        """Compat legacy: ``proposal["status"]`` -> ``proposal.status``.

        Mantiene frozen=True. NO permite assignment (KV implicito seria
        un workaround del dataclass frozen). Lanza KeyError si la
        clave no es un campo del DTO.
        """
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict preservando todas las columnas (payload_json raw)."""
        return {
            "proposal_id": self.proposal_id,
            "idempotency_key": self.idempotency_key,
            "tenant_id": self.tenant_id,
            "source_project": self.source_project,
            "target_catalog": self.target_catalog,
            "knowledge_ref": self.knowledge_ref,
            "payload_json": json.dumps(self.payload, sort_keys=True),
            "status": self.status,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
        }


@dataclass(frozen=True, slots=True)
class StoredBudget:
    """DTO inmutable de un RunBudget (run_budgets).

    WI-38 (R1 strict): sustituye ``dict[str, Any]`` en ``get_budget``.
    Los 3 campos son 1:1 con la tabla ``run_budgets``.

    ``to_dict()`` preserva el dict historico.
    ``__getitem__`` permite subscript legacy durante la migracion.
    """

    tenant_id: str
    project_id: str
    run_id: str
    max_visits: int | None
    max_runtime_seconds: int | None
    max_events: int | None

    def __getitem__(self, key: str) -> Any:
        """Compat legacy: ``budget["max_visits"]`` -> ``budget.max_visits``."""
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict preservando todas las columnas."""
        return {
            "max_visits": self.max_visits,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_events": self.max_events,
        }


__all__ = [
    "StoredBudget",
    "StoredClaim",
    "StoredEvent",
    "StoredEvidence",
    "StoredNodeExecution",
    "StoredPromotion",
    "StoredRelation",
    "StoredResource",
    "StoredRun",
]

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
