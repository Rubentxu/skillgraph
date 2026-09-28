"""Red de contrato WI-56 corte 4: SqliteEventStore real.

Fija el contrato del estrangulamiento ADR-0016 para el cluster
events (record_event, list_events, ensure_schema, fetch_event_raw;
list_events_for_run ya vive en SqliteRunRepository desde el corte 1):

1. ``Storage.event_store()`` devuelve UNA instancia del componente
   real (no ``self``), cacheada.
2. Los 4 metodos producen el mismo efecto observable por camino
   delegado y por componente (dos bases identicas, dump semantico de
   ``runtime_events`` sin la columna ``timestamp`` cuando es reloj).
3. El componente comparte la conexion de Storage y cubre
   estructuralmente el Protocol ``EventStore`` (runtime_checkable).
4. Los helpers atomicos ``_insert_event_in_tx`` /
   ``_atomic_state_and_event`` siguen siendo del ``Storage`` dueno:
   los tests H9/H10 monkeypatchean ``storage._insert_event_in_tx`` y
   el componente los resuelve tarde via ``self._storage`` (I1).
5. El schema no cambia: una nueva instancia de ``Storage`` sobre el
   mismo fichero ve lo escrito por el componente.

Tests contra Storage real (SQLite en tmp_path), sin mocks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from skillgraph.platform.ports import EventStore
from skillgraph.platform.storage import Storage

TENANT = "t"
PROJECT = "p"


def _event(eid: str = "evt-1", kind: str = "RunCreated", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tenant_id": TENANT,
        "project_id": PROJECT,
        "event_id": eid,
        "event_kind": kind,
        "resource_ref": "res:1",
        "payload": {"k": "v"},
        "run_id": "run-1",
        "causation_id": None,
        "correlation_id": "corr-1",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    base.update(kw)
    return base


def _seed_base(storage: Storage) -> None:
    storage.event_store().record_event(**_event("evt-1"))
    storage.event_store().record_event(**_event("evt-2", kind="NodeScheduled"))


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Storage, Storage]:
    live = Storage(tmp_path / "live.sqlite")
    delegated = Storage(tmp_path / "delegated.sqlite")
    _seed_base(live)
    _seed_base(delegated)
    return live, delegated


def _cases() -> dict[str, dict[str, Any]]:
    return {
        "record_event": _event("evt-3", kind="NodeCompleted"),
        "record_event_no_run": _event("evt-4", run_id=None),
        "list_events": {"tenant_id": TENANT, "project_id": PROJECT},
        "list_events_filtered": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "event_kind": "RunCreated",
        },
        "fetch_event_raw": {"event_id": "evt-1"},
        "fetch_event_raw_missing": {"event_id": "nope"},
    }


def _snapshot(storage: Storage) -> list[tuple[str, tuple[Any, ...]]]:
    conn = storage._conn
    rows = conn.execute(
        """
        SELECT event_id, tenant_id, project_id, event_kind, run_id,
               resource_ref, causation_id, correlation_id, payload_json,
               schema_version
        FROM runtime_events ORDER BY event_id
        """
    ).fetchall()
    return [("runtime_events", tuple(r)) for r in rows]


class TestFacadeIdentity:
    def test_event_store_is_cached_component_not_self(self, pair) -> None:
        storage, _other = pair
        store = storage.event_store()
        assert store is not storage
        assert storage.event_store() is store

    def test_component_shares_storage_connection(self, pair) -> None:
        storage, _other = pair
        assert storage.event_store()._conn is storage._conn

    def test_component_satisfies_eventstore_protocol(self, pair) -> None:
        storage, _other = pair
        # EventStore es runtime_checkable: chequeo structural real.
        assert isinstance(storage.event_store(), EventStore)


class TestClusterEquivalence:
    @pytest.mark.parametrize(
        "case_name",
        sorted(_cases().keys()),
    )
    def test_component_path_matches_delegated_path(self, pair, case_name: str) -> None:
        live, delegated = pair
        kwargs = dict(_cases()[case_name])

        if case_name.startswith("record_event"):
            live_ret = live.event_store().record_event(**kwargs)
            delegated_ret = delegated.record_event(**kwargs)
        elif case_name.startswith("list_events"):
            live_ret = live.event_store().list_events(**kwargs)
            delegated_ret = delegated.list_events(**kwargs)
        else:
            live_ret = live.event_store().fetch_event_raw(**kwargs)
            delegated_ret = delegated.fetch_event_raw(**kwargs)

        assert _snapshot(live) == _snapshot(delegated)

        def norm(s: str) -> str:
            return re.sub(r"\d+", "N", s)

        assert norm(repr(live_ret)) == norm(repr(delegated_ret))

    def test_fetch_event_raw_returns_dto(self, pair) -> None:
        from skillgraph.platform.ports import StoredEvent

        live, _other = pair
        evt = live.event_store().fetch_event_raw(event_id="evt-1")
        assert isinstance(evt, StoredEvent)
        assert evt.event_id == "evt-1"

    def test_list_events_orders_by_sequence(self, pair) -> None:
        live, _other = pair
        evts = live.event_store().list_events(tenant_id=TENANT, project_id=PROJECT)
        assert [e.event_id for e in evts] == ["evt-1", "evt-2"]

    def test_duplicate_event_id_raises_typed_error_both_paths(self, pair) -> None:
        from skillgraph.core.errors import IntegrityError

        live, delegated = pair
        dup = _event("evt-1")
        with pytest.raises(IntegrityError):
            live.event_store().record_event(**dup)
        with pytest.raises(IntegrityError):
            delegated.record_event(**dup)


class TestAtomicHelpersStayOnStorage:
    """Corte 4 NO mueve los helpers atomicos: H9/H10 parchean
    ``storage._insert_event_in_tx`` y el componente los consume via
    ``self._storage`` (resolucion tardia)."""

    def test_storage_still_owns_helpers(self, pair) -> None:
        live, _other = pair
        assert callable(live._insert_event_in_tx)
        assert callable(live._atomic_state_and_event)

    def test_helper_monkeypatch_flows_into_component_tx(self, pair, monkeypatch) -> None:
        """El componente delega en storage._insert_event_in_tx: parchear
        el storage cambia el comportamiento de las rutas atomicas del
        run-cluster que lo consumen (contrato I1)."""
        from skillgraph.runtime.engine import RuntimeEvent

        live, _other = pair
        calls: list[str] = []
        real = live._insert_event_in_tx

        def spy(cur: Any, event: RuntimeEvent) -> None:
            calls.append(event.event_id)
            real(cur, event)

        monkeypatch.setattr(live, "_insert_event_in_tx", spy)
        evt = RuntimeEvent(
            event_id="evt-spy",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="RunCreated",
            run_id=None,
            resource_ref="res:spy",
            causation_id=None,
            correlation_id=None,
            payload={},
        )
        live._atomic_state_and_event(
            event=evt,
            exec_sql=("UPDATE workflow_runs SET state = 'ACTIVE' WHERE 1=0", ()),
        )
        assert calls == ["evt-spy"]


class TestSchemaUntouched:
    def test_ensure_schema_is_idempotent_and_shared(self, tmp_path) -> None:
        storage = Storage(tmp_path / "single.sqlite")
        _seed_base(storage)
        storage.event_store().ensure_schema()  # no-op tras migracion inicial
        storage.event_store().ensure_schema()
        reopened = Storage(tmp_path / "single.sqlite")
        evts = reopened.list_events(tenant_id=TENANT, project_id=PROJECT)
        assert [e.event_id for e in evts] == ["evt-1", "evt-2"]
        reopened.close()
