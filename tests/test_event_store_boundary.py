"""Tests de frontera de plataforma (WI-32.2 R1 strict).

WI-32.2 (Persistence Boundary Closure, audit 2026-09-27):
estos tests verifican que el contrato del EventStore Protocol
realmente cumple el objetivo 2 de WI-32:

    "ningun ``sqlite3.Row`` fuera de ``platform/``"

Tests:
  - list_events_for_run devuelve StoredEvent (atributos tipados)
  - fetch_event_raw devuelve StoredEvent | None
  - payload ya viene deserializado (no raw json string)
  - atributos no son dict/Row (verificacion con isinstance)
  - DTO es frozen (intento de asignar falla)
  - to_dict() preserva equivalencia con API legacy
"""

from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError

import pytest


class TestEventStoreProtocolContract:
    """Contrato del EventStore: retorna DTOs, no filas crudas."""

    def test_list_events_for_run_returns_storedevent_list(self, tmp_path) -> None:
        from skillgraph.platform.ports import StoredEvent
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "events.db")
        try:
            storage.record_event(
                tenant_id="t",
                project_id="p",
                event_id="evt-1",
                event_kind="RunCreated",
                resource_ref="r",
                payload={"k": "v"},
                run_id="run-1",
            )
            out = storage.list_events_for_run(tenant_id="t", project_id="p", run_id="run-1")
            assert isinstance(out, list)
            assert all(isinstance(e, StoredEvent) for e in out)
            # ninguno es sqlite3.Row ni dict (la frontera)
            for e in out:
                assert not isinstance(e, sqlite3.Row)
                assert not isinstance(e, dict)
        finally:
            storage.close()

    def test_fetch_event_raw_returns_storedevent_or_none(self, tmp_path) -> None:
        from skillgraph.platform.ports import StoredEvent
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "events.db")
        try:
            storage.record_event(
                tenant_id="t",
                project_id="p",
                event_id="evt-found",
                event_kind="RunCreated",
                resource_ref="r",
                payload={"k": "v"},
                run_id="run-1",
            )
            # hit
            found = storage.fetch_event_raw(event_id="evt-found")
            assert isinstance(found, StoredEvent)
            assert found.event_id == "evt-found"
            assert not isinstance(found, sqlite3.Row)
            # miss
            miss = storage.fetch_event_raw(event_id="evt-no-existe")
            assert miss is None
        finally:
            storage.close()

    def test_payload_already_deserialized(self, tmp_path) -> None:
        """WI-32.2: payload no es un string JSON raw; ya viene deserializado.

        Esto cumple el objetivo 3 de WI-32:
            "ningun ``*_json`` raw fuera del adapter SQLite"
        """
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "events.db")
        try:
            original_payload = {"k": 1, "nested": {"x": [1, 2, 3]}}
            storage.record_event(
                tenant_id="t",
                project_id="p",
                event_id="evt-payload",
                event_kind="RunCreated",
                resource_ref="r",
                payload=original_payload,
                run_id="run-1",
            )
            ev = storage.fetch_event_raw(event_id="evt-payload")
            assert ev is not None
            # payload es dict, NO string
            assert isinstance(ev.payload, dict)
            assert ev.payload == original_payload
            # no hay atributo payload_json (eliminado del DTO)
            assert not hasattr(ev, "payload_json")
        finally:
            storage.close()

    def test_dto_is_frozen(self, tmp_path) -> None:
        """StoredEvent no admite asignacion post-construccion.

        Cumplimiento de AGENTS.md 1.1: inmutabilidad por defecto.
        """
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "events.db")
        try:
            storage.record_event(
                tenant_id="t",
                project_id="p",
                event_id="evt-frozen",
                event_kind="RunCreated",
                resource_ref="r",
                payload={},
                run_id="run-1",
            )
            ev = storage.fetch_event_raw(event_id="evt-frozen")
            assert ev is not None
            with pytest.raises(FrozenInstanceError):
                ev.event_id = "mutated"  # type: ignore[misc]
        finally:
            storage.close()

    def test_to_dict_round_trip_preserves_legacy_shape(self, tmp_path) -> None:
        """StoredEvent.to_dict() preserva la forma legacy dict.

        Compat: consumers que esperan dict (no podemos migrar todos en
        WI-32.2 sin expandir el scope) pueden llamar ``to_dict()`` y
        obtener la misma estructura que tenian antes.
        """
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "events.db")
        try:
            payload = {"state": "ACTIVE", "n": 42}
            storage.record_event(
                tenant_id="t",
                project_id="p",
                event_id="evt-legacy",
                event_kind="RunCreated",
                resource_ref="r",
                payload=payload,
                run_id="run-1",
                causation_id="cause-x",
                correlation_id="corr-y",
            )
            ev = storage.fetch_event_raw(event_id="evt-legacy")
            assert ev is not None
            as_dict = ev.to_dict()
            # 12 campos, mismos nombres que antes
            expected_keys = {
                "sequence",
                "event_id",
                "tenant_id",
                "project_id",
                "event_kind",
                "run_id",
                "resource_ref",
                "causation_id",
                "correlation_id",
                "payload",
                "timestamp",
                "schema_version",
            }
            assert set(as_dict.keys()) == expected_keys
            assert as_dict["event_id"] == "evt-legacy"
            assert as_dict["causation_id"] == "cause-x"
            assert as_dict["correlation_id"] == "corr-y"
            assert as_dict["payload"] == payload
        finally:
            storage.close()

    def test_no_sqlite3_row_leaks_to_consumer(self, tmp_path) -> None:
        """Ningun consumer recibe sqlite3.Row.

        Verifica la promesa arquitectonica de WI-32.2 a nivel de
        ``Storage`` (la fachada publica de plataforma).
        """
        from skillgraph.platform.storage import Storage

        storage = Storage(tmp_path / "events.db")
        try:
            storage.record_event(
                tenant_id="t",
                project_id="p",
                event_id="evt-no-leak",
                event_kind="RunCreated",
                resource_ref="r",
                payload={},
                run_id="run-1",
            )
            # Cualquier consumer que use la API publica del EventStore
            # (via Storage como fachada) NO recibe sqlite3.Row.
            rows_via_storage = storage.list_events_for_run(
                tenant_id="t", project_id="p", run_id="run-1"
            )
            for r in rows_via_storage:
                assert not isinstance(r, sqlite3.Row), (
                    "Storage.list_events_for_run devolvio sqlite3.Row; "
                    "es una fuga del boundary platform/."
                )
        finally:
            storage.close()
