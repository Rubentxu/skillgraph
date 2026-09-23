"""Contrato de eventos del runtime (Etapa 2 / S0).

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md §4 (eventos).
  external/blueprint-v1/docs/06-controladores.md §7 (bucle de
  reconciliacion).

Un evento es un hecho append-only que afecta al estado del run o del
nodo. La identidad del evento (`event_id`) es la UNICA defensa contra
duplicacion: el EventLog NO usa el orden temporal como autoridad.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from skillgraph.errors import IdempotencyError, ValidationError

SCHEMA_VERSION = 1

EVENT_KINDS = frozenset(
    {
        "RunCreated",
        "NodeScheduled",
        "HandoffCreated",
        "NodeStarted",
        "NodeCompleted",
        "NodeFailed",
        "EvidenceProduced",
        "KnowledgeInvalidated",
        "ProblemDiscovered",
        "GraphExpansionProposed",
        "GraphExpansionAccepted",
        "GraphExpansionRejected",
        "RunCompleted",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Hecho inmutable del runtime.

    Coincide con el contrato del blueprint §4 (eventos), incluyendo
    los campos obligatorios.
    """

    event_id: str
    tenant_id: str
    project_id: str
    event_kind: str
    run_id: str | None
    resource_ref: str
    causation_id: str | None
    correlation_id: str | None
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.event_kind not in EVENT_KINDS:
            raise ValidationError(f"event_kind desconocido: {self.event_kind!r}")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runtime_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    run_id TEXT,
    resource_ref TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_run
    ON runtime_events(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS events_by_resource
    ON runtime_events(tenant_id, project_id, resource_ref);
"""


class EventLog:
    """Registro append-only de eventos del runtime."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._migrate()

    def _migrate(self) -> None:
        with self._tx() as cur:
            cur.executescript(_SCHEMA_SQL)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        with self._conn:
            yield self._conn.cursor()

    def append(self, event: RuntimeEvent) -> int:
        """Inserta un evento. Devuelve el sequence asignado.

        Si el `event_id` ya existe (duplicado), lanza `IdempotencyError`
        — la idempotencia vive en el UNIQUE de la tabla, no en código.
        Esto cumple UAT-07: evento entregado dos veces NO duplica.
        """
        import json as _json

        try:
            with self._tx() as cur:
                cur.execute(
                    """
                    INSERT INTO runtime_events
                        (event_id, tenant_id, project_id, event_kind, run_id,
                         resource_ref, causation_id, correlation_id,
                         payload_json, timestamp, schema_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.tenant_id,
                        event.project_id,
                        event.event_kind,
                        event.run_id,
                        event.resource_ref,
                        event.causation_id,
                        event.correlation_id,
                        _json.dumps(event.payload, sort_keys=True),
                        event.timestamp,
                        event.schema_version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            # UNIQUE(event_id) -> el evento ya estaba. UAT-07.
            raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc
        row = self._conn.execute(
            "SELECT sequence FROM runtime_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()
        if row is None:  # pragma: no cover
            raise ValidationError("Fallo inesperado al obtener sequence del evento")
        return int(row["sequence"])

    def events_for_run(
        self, *, tenant_id: str, project_id: str, run_id: str
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM runtime_events
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
            ORDER BY sequence ASC
            """,
            (tenant_id, project_id, run_id),
        ).fetchall()
        return [_row_to_event_dict(r) for r in rows]

    def has_event(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM runtime_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return row is not None


def _row_to_event_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sequence": row["sequence"],
        "event_id": row["event_id"],
        "tenant_id": row["tenant_id"],
        "project_id": row["project_id"],
        "event_kind": row["event_kind"],
        "run_id": row["run_id"],
        "resource_ref": row["resource_ref"],
        "causation_id": row["causation_id"],
        "correlation_id": row["correlation_id"],
        "payload": json.loads(row["payload_json"]),
        "timestamp": row["timestamp"],
        "schema_version": row["schema_version"],
    }


def new_event_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    """ISO 8601 UTC sin microsegundos. Centralizado para evitar drift.

    Unico punto de definicion: antes existian 3 copias (_now_iso en
    git_source/context_controller/knowledge_invalidator). Cualquier
    serializacion temporal del runtime debe usar este helper.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# --- Builder funcional para eventos ----------------------------------------


class EventBuilder:
    """Constructor inmutable de `RuntimeEvent` con smart constructors.

    Cada metodo (`run_created`, `node_scheduled`, ...) devuelve un NUEVO
    `RuntimeEvent` ya validado. Elimina el boilerplate de repetir los
    7 argumentos comunes en cada sitio del RunController.

    Reglas (AGENTS.md §2 y §11.9):
    - Inmutable: cada llamada devuelve un nuevo `RuntimeEvent`,
      no muta estado.
    - Errores tipados: la validacion vive en `RuntimeEvent.__post_init__`.
    """

    __slots__ = ("_correlation_id", "_project_id", "_tenant_id")

    def __init__(
        self,
        *,
        tenant_id: str,
        project_id: str,
        correlation_id: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._project_id = project_id
        self._correlation_id = correlation_id

    def _emit(
        self,
        *,
        kind: str,
        run_id: str | None,
        resource_ref: str,
        payload: dict[str, Any],
        causation_id: str | None = None,
    ) -> RuntimeEvent:
        return RuntimeEvent(
            event_id=new_event_id(),
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            event_kind=kind,
            run_id=run_id,
            resource_ref=resource_ref,
            causation_id=causation_id,
            correlation_id=self._correlation_id,
            payload=payload,
        )

    def run_created(self, *, run_id: str, initial_node: str) -> RuntimeEvent:
        return self._emit(
            kind="RunCreated",
            run_id=run_id,
            resource_ref=f"run/{run_id}",
            payload={"initial_node": initial_node},
        )

    def node_scheduled(
        self, *, run_id: str, node_execution_id: str, node_name: str, attempt: int
    ) -> RuntimeEvent:
        return self._emit(
            kind="NodeScheduled",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload={
                "node_name": node_name,
                "node_execution_id": node_execution_id,
                "attempt": attempt,
            },
        )

    def handoff_created(
        self, *, run_id: str, node_execution_id: str, context_hash: str
    ) -> RuntimeEvent:
        return self._emit(
            kind="HandoffCreated",
            run_id=run_id,
            resource_ref=f"handoff/{node_execution_id}",
            payload={
                "node_execution_id": node_execution_id,
                "context_hash": context_hash,
            },
        )

    def node_started(self, *, run_id: str, node_execution_id: str) -> RuntimeEvent:
        return self._emit(
            kind="NodeStarted",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload={"node_execution_id": node_execution_id},
        )

    def node_completed(
        self,
        *,
        run_id: str,
        node_execution_id: str,
        outcome: str,
        context_hash: str,
    ) -> RuntimeEvent:
        return self._emit(
            kind="NodeCompleted",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload={
                "node_execution_id": node_execution_id,
                "outcome": outcome,
                "context_hash": context_hash,
            },
        )

    def node_failed(
        self,
        *,
        run_id: str,
        node_execution_id: str,
        error: str,
        outcome: str | None = None,
    ) -> RuntimeEvent:
        payload: dict[str, Any] = {
            "node_execution_id": node_execution_id,
            "error": error,
        }
        if outcome is not None:
            payload["outcome"] = outcome
        return self._emit(
            kind="NodeFailed",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload=payload,
        )

    def evidence_produced(
        self,
        *,
        run_id: str,
        node_execution_id: str,
        outcome: str,
        context_hash: str,
        evidence_ref: str,
    ) -> RuntimeEvent:
        return self._emit(
            kind="EvidenceProduced",
            run_id=run_id,
            resource_ref=f"evidence/{node_execution_id}",
            payload={
                "node_execution_id": node_execution_id,
                "outcome": outcome,
                "context_hash": context_hash,
                "evidence_ref": evidence_ref,
            },
        )

    def run_completed(self, *, run_id: str, state: str, at: str | None = None) -> RuntimeEvent:
        payload: dict[str, Any] = {"state": state}
        if at is not None:
            payload["at"] = at
        return self._emit(
            kind="RunCompleted",
            run_id=run_id,
            resource_ref=f"run/{run_id}",
            payload=payload,
        )
