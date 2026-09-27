"""Adapter minimo de EventStore sobre sqlite3.Connection (test helper, WI-02b).

Permite que los tests con conexion ``:memory:`` o ``tmp_path``
usen :class:`EventLog` sin necesidad de montar un ``Storage``
entero. El adapter aplica el schema via ``ensure_schema()`` y
delega a ``record_event`` / ``list_events_for_run``.

No es parte de la API publica: existe solo para que la suite
migre limpia de ``EventLog(conn)`` a ``EventLog(store)``.

WI-32.2 (R1 strict, audit 2026-09-27): ahora devuelve DTOs
``StoredEvent`` (no ``sqlite3.Row``) para mantener paridad con el
contrato del ``EventStore`` Protocol que cambio en WI-32.2.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from skillgraph.platform.ports import StoredEvent


def _row_to_stored_event(row: sqlite3.Row) -> StoredEvent:
    """Adaptador Row -> StoredEvent (test helper, paralelo a
    ``platform/storage._row_to_stored_event``)."""
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


class SqliteEventStoreForTest:
    """Implementacion minima de :class:`EventStore` sobre una conexion.

    Solo para tests. La implementacion real vive en
    ``platform/storage.Storage`` (la fachada), que cumple el
    Protocol por duck typing.
    """

    _SCHEMA = """
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
            schema_version INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS events_by_run
            ON runtime_events(tenant_id, project_id, run_id);
        CREATE INDEX IF NOT EXISTS events_by_resource
            ON runtime_events(tenant_id, project_id, resource_ref);
        """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(self._SCHEMA)

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
        ts = timestamp or datetime.now().replace(microsecond=0).isoformat()
        try:
            with self._conn:
                cur = self._conn.execute(
                    """
                    INSERT INTO runtime_events
                        (event_id, tenant_id, project_id, event_kind, run_id,
                         resource_ref, causation_id, correlation_id,
                         payload_json, timestamp, schema_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        event_id,
                        tenant_id,
                        project_id,
                        event_kind,
                        run_id,
                        resource_ref,
                        causation_id,
                        correlation_id,
                        json.dumps(dict(payload), ensure_ascii=False),
                        ts,
                    ),
                )
            return int(cur.lastrowid or 0)
        except sqlite3.IntegrityError as exc:
            from skillgraph.core.errors import IntegrityError as _IntegrityError

            raise _IntegrityError(f"constraint UNIQUE(event_id) violada: {event_id!r}") from exc

    def list_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
        resource_ref: str | None = None,
        event_kind: str | None = None,
    ) -> list[Any]:
        q = "SELECT * FROM runtime_events WHERE tenant_id = ? AND project_id = ?"
        params: list[Any] = [tenant_id, project_id]
        if resource_ref is not None:
            q += " AND resource_ref = ?"
            params.append(resource_ref)
        if event_kind is not None:
            q += " AND event_kind = ?"
            params.append(event_kind)
        q += " ORDER BY sequence ASC"
        return list(self._conn.execute(q, params).fetchall())

    def list_events_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> list[StoredEvent]:
        rows = self._conn.execute(
            "SELECT * FROM runtime_events "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ? "
            "ORDER BY sequence ASC",
            (tenant_id, project_id, run_id),
        ).fetchall()
        return [_row_to_stored_event(r) for r in rows]

    def fetch_event_raw(self, *, event_id: str) -> StoredEvent | None:
        row = self._conn.execute(
            "SELECT * FROM runtime_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_stored_event(row)
