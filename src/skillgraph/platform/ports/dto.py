"""DTOs de la capa de persistencia.

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

import json
from dataclasses import dataclass
from typing import Any


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
