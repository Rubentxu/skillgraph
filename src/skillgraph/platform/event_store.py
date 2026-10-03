"""SqliteEventStore: componente WI-56 corte 4.

Implementacion real del cluster events del ``Storage`` god-module
(ADR-0016, strangler): append-only log de ``runtime_events``
(Protocol ``EventStore``). Extraido verbatim de
``platform/storage.py``: el SQL y el orden de columnas no cambian.

Los contextos transaccionales ``_tx`` se resuelven via el
``Storage`` dueno (``self._storage``) y los helpers atomicos
``_insert_event_in_tx`` / ``_atomic_state_and_event`` permanecen en
``Storage``: los tests H9/H10 monkeypatchean
``storage._insert_event_in_tx`` y esta resolucion tardia preserva
ese contrato (I1). El corte 5 decidira su hogar definitivo.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from skillgraph.platform.ports import StoredEvent
from skillgraph.platform.row_mappers import _row_to_stored_event
from skillgraph.platform.storage import _SCHEMA_SQL, Storage
from skillgraph.runtime.engine import now_iso


class SqliteEventStore:
    """Implementacion real de ``EventStore`` sobre la conexion de
    ``Storage``. No duena el schema ni la migracion; solo habla SQL
    del cluster events con la misma forma que ``Storage`` tenia."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        """Conexion compartida con el ``Storage`` dueno del schema."""
        return self._storage._conn  # composicion interna acordada en ADR-0016

    def list_events_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> list[StoredEvent]:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository``
        (corte 1); aqui solo se puentea para que ``SqliteEventStore``
        satisfaga el Protocol completo ``EventStore``."""
        return self._storage.run_repository().list_events_for_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def record_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_id: str,
        event_kind: str,
        resource_ref: str,
        payload: Mapping[str, Any],
        run_id: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Registra un evento en `runtime_events`. Devuelve su sequence.

        `payload` se serializa como JSON. `timestamp` por defecto = now UTC.
        """
        import json as _json

        # WI-112: el reloj se lee solo en `runtime.engine.now_iso`.
        ts = timestamp or now_iso()
        try:
            with self._storage._tx() as cur:
                cur.execute(
                    """
                    INSERT INTO runtime_events
                        (event_id, tenant_id, project_id, event_kind, run_id,
                         resource_ref, causation_id, correlation_id,
                         payload_json, timestamp, schema_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        _json.dumps(dict(payload), ensure_ascii=False),
                        ts,
                        1,
                    ),
                )
                return cur.lastrowid or 0
        except sqlite3.IntegrityError as exc:
            # WI-02b: traducimos a IntegrityError del core para que
            # EventLog (y futuros consumidores) no necesiten
            # importar sqlite3.
            from skillgraph.core.errors import IntegrityError as _IntegrityError

            raise _IntegrityError(f"constraint UNIQUE(event_id) violada: {event_id!r}") from exc

    def list_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
        resource_ref: str | None = None,
        event_kind: str | None = None,
    ) -> list[StoredEvent]:
        """Lista eventos filtrados por (tenant, project) + resource_ref/kind.

        WI-38 (R1 strict): devuelve ``list[StoredEvent]`` (frozen + slots)
        en vez de ``list[sqlite3.Row]``. Mapea via ``_row_to_stored_event``
        para cerrar la fuga de Row fuera de ``platform/``.
        """
        q = "SELECT * FROM runtime_events WHERE tenant_id = ? AND project_id = ?"
        params: list[Any] = [tenant_id, project_id]
        if resource_ref is not None:
            q += " AND resource_ref = ?"
            params.append(resource_ref)
        if event_kind is not None:
            q += " AND event_kind = ?"
            params.append(event_kind)
        q += " ORDER BY sequence ASC"
        rows = self._conn.execute(q, params).fetchall()
        return [_row_to_stored_event(r) for r in rows]

    def ensure_schema(self) -> None:
        """Idempotente: aplica el schema de ``runtime_events``.

        WI-02b: ``EventLog`` ya no toca la conexion directamente; delega
        en este metodo del ``EventStore`` Protocol. La migracion ocurre
        en el ``__init__`` de ``Storage`` (``migrate()`` ya invoca
        ``_SCHEMA_SSQL`` sobre ``runtime_events``), por lo que aqui
        simplemente ejecutamos ``executescript`` reentrante (los
        ``CREATE TABLE IF NOT EXISTS`` son idempotentes).
        """
        with self._storage._tx() as cur:
            cur.executescript(_SCHEMA_SQL)

    def fetch_event_raw(self, *, event_id: str) -> StoredEvent | None:
        """WI-02b: lookup directo por ``event_id``.

        WI-32.2: devuelve ``StoredEvent`` (DTO inmutable). El adapter
        SQLite mapea ``Row -> StoredEvent`` aqui; el resto del runtime
        nunca ve ``sqlite3.Row``. Ver ``platform/ports.py`` para el DTO.
        """
        row = self._conn.execute(
            "SELECT * FROM runtime_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_stored_event(row)
