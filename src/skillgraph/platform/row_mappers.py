"""Mappers fila-SQLite -> DTO del facade `Storage` (WI-65, fase 2).

Funciones **puras**: reciben una fila y devuelven un DTO. Sin `self`,
sin conexion, sin reloj, sin SQL. Mismo criterio y mismo motivo de
cambio que `knowledge_mappers.py` (ADR-0020, WI-60) aplico a
`knowledge_repository`: un modulo para el contrato fila->DTO.

`storage.py` los re-exporta porque los componentes de WI-56 (ADR-0016
corte 5) los importan desde ahi. NO renombrar ni mover sin migrar
`event_store`, `policy_store` y `knowledge_repository`.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from skillgraph.resources.bricks import Brick

# Estos cinco se CONSTRUYEN en el cuerpo de los mappers, no solo se
# anotan: con `from __future__ import annotations` una anotacion es una
# cadena perezosa, pero `StoredRun(...)` es una busqueda de nombre real.
# Bajo TYPE_CHECKING rompen con NameError en cuanto se ejecuta el mapper.
from skillgraph.platform.ports import (
    StoredBudget,
    StoredEvent,
    StoredNodeExecution,
    StoredPromotion,
    StoredRun,
)

MAPPER_NAMES: Final[tuple[str, ...]] = (
    "_row_to_stored_event",
    "_row_to_stored_promotion",
    "_row_to_stored_budget",
    "_row_to_source",
    "_row_to_evidence",
    "_row_to_stored_evidence",
    "_row_to_claim",
    "_row_to_stored_claim",
    "_row_to_run",
    "_row_to_node_execution",
    "_row_to_resource",
    "_row_to_relation",
)
"""Los 12 mappers extraidos de `storage.py` (guarda de recuento)."""

__all__ = [
    "MAPPER_NAMES",
    "_row_to_claim",
    "_row_to_evidence",
    "_row_to_node_execution",
    "_row_to_relation",
    "_row_to_resource",
    "_row_to_run",
    "_row_to_source",
    "_row_to_stored_budget",
    "_row_to_stored_claim",
    "_row_to_stored_event",
    "_row_to_stored_evidence",
    "_row_to_stored_promotion",
    "_uid",
]


def _uid(brick: Brick) -> str:
    """UID determinista por (tenant, project, apiVersion, kind, namespace, name).

    El blueprint (doc 03 §3) deja la elección al núcleo. Aquí usamos un
    UID estable pero NO un hash criptográfico: las revisiones usan un
    contador (resource_version) y la identidad de los `Brick` ya viene
    garantizada por la UNIQUE constraint de la tabla.
    """
    i = brick.identity
    return f"{i.tenant_id}/{i.project_id}/{brick.api_version}/{brick.kind}/{i.namespace}/{i.name}"


def _row_to_stored_event(row: sqlite3.Row) -> StoredEvent:
    """Mapea ``sqlite3.Row`` de ``runtime_events`` al DTO ``StoredEvent``.

    WI-32.2 (R1 strict, audit 2026-09-27): este helper es la frontera
    entre ``platform/`` y el resto del runtime. El consumidor (EventLog,
    RunController) solo ve ``StoredEvent``; nunca importa ``sqlite3``.

    El campo ``payload`` se deserializa desde ``payload_json`` aqui;
    ``runtime/engine.py`` ya no maneja ``json.loads`` sobre filas.
    """
    import json  # local import por consistencia con resto del modulo

    return StoredEvent(
        sequence=row["sequence"],
        event_id=row["event_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        event_kind=row["event_kind"],
        run_id=row["run_id"],
        resource_ref=row["resource_ref"],
        causation_id=row["causation_id"],
        correlation_id=row["correlation_id"],
        payload=json.loads(row["payload_json"]),
        timestamp=row["timestamp"],
        schema_version=row["schema_version"],
    )


def _row_to_stored_promotion(row: sqlite3.Row) -> StoredPromotion:
    """Mapea ``sqlite3.Row`` de ``promotion_outbox`` al DTO ``StoredPromotion``.

    WI-38 (R1 strict): cierra la fuga de ``dict[str, Any]`` en los
    3 metodos de promotion (``get_promotion``, ``list_pending_promotions``,
    ``list_promotions``). El campo ``payload`` se deserializa aqui.
    """
    import json  # local import por consistencia con resto del modulo

    return StoredPromotion(
        proposal_id=row["proposal_id"],
        idempotency_key=row["idempotency_key"],
        tenant_id=row["tenant_id"],
        source_project=row["source_project"],
        target_catalog=row["target_catalog"],
        knowledge_ref=row["knowledge_ref"],
        payload=json.loads(row["payload_json"]),
        status=row["status"],
        attempts=row["attempts"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
    )


def _row_to_stored_budget(row: sqlite3.Row) -> StoredBudget:
    """Mapea ``sqlite3.Row`` de ``run_budgets`` al DTO ``StoredBudget``.

    WI-38 (R1 strict): sustituye ``dict(row)`` en ``get_budget``.
    """
    return StoredBudget(
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        run_id=row["run_id"],
        max_visits=row["max_visits"],
        max_runtime_seconds=row["max_runtime_seconds"],
        max_events=row["max_events"],
    )


def _row_to_source(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_source``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_source

    return row_to_source(row, json)


def _row_to_evidence(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_evidence``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_evidence

    return row_to_evidence(row, json)


def _row_to_stored_evidence(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_stored_evidence``. El corte 5
    reubicara los callers."""
    from skillgraph.platform.knowledge_repository import row_to_stored_evidence

    return row_to_stored_evidence(row, json)


def _row_to_claim(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_claim``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_claim

    return row_to_claim(row, [], json)


def _row_to_stored_claim(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_stored_claim``. El corte 5
    reubicara los callers."""
    from skillgraph.platform.knowledge_repository import row_to_stored_claim

    return row_to_stored_claim(row, json)


def _row_to_run(row: sqlite3.Row) -> StoredRun:
    """Convierte una fila de ``workflow_runs`` al DTO ``StoredRun``.

    WI-32.4: sustituye ``dict(row)`` por una traduccion tipada.
    El adapter expone ``StoredRun`` (frozen + slots) en vez de dict
    mutable, evitando que ``sqlite3.Row`` escape del modulo
    ``platform/``.
    """
    return StoredRun(
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        state=row["state"],
        plan_json=row["plan_json"],
        current_node=row["current_node"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_node_execution(row: sqlite3.Row) -> StoredNodeExecution:
    """Convierte una fila de ``node_executions`` al DTO ``StoredNodeExecution``.

    WI-32.4: sustituye ``dict(row)`` por una traduccion tipada.
    ``StoredNodeExecution`` es frozen + slots y refleja 1:1 la tabla.
    """
    return StoredNodeExecution(
        node_execution_id=row["node_execution_id"],
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        node_name=row["node_name"],
        attempt=row["attempt"],
        state=row["state"],
        outcome=row["outcome"],
        context_hash=row["context_hash"],
        handoff_json=row["handoff_json"],
        result_json=row["result_json"],
        error=row["error"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _row_to_resource(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_resource``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_resource

    return row_to_resource(row)


def _row_to_relation(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_relation``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_relation

    return row_to_relation(row)
