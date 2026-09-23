"""Tests del runtime append-only (Etapa 2 / S0).

Cobertura:
- Apende eventos validos.
- Rechaza event_kind no registrado (ValidationError).
- Idempotencia: el segundo append con el mismo event_id lanza
  ValidationError (UAT-07 del blueprint).
- Reconstruccion por run: events_for_run devuelve eventos en orden
  de sequence.
"""

from __future__ import annotations

import sqlite3

import pytest

from skillgraph.errors import IdempotencyError, ValidationError
from skillgraph.runtime.engine import (
    EVENT_KINDS,
    EventLog,
    RuntimeEvent,
    new_event_id,
)

pytestmark = pytest.mark.etapa1


def _make_event(*, event_kind: str = "RunCreated", event_id: str | None = None) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=event_id or new_event_id(),
        tenant_id="t",
        project_id="p",
        event_kind=event_kind,
        run_id="r-1",
        resource_ref="run/r-1",
        causation_id=None,
        correlation_id=None,
        payload={"k": "v"},
    )


@pytest.fixture
def event_log() -> EventLog:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return EventLog(conn)


class TestEventAppend:
    def test_append_valid_event_returns_sequence(self, event_log: EventLog) -> None:
        ev = _make_event()
        seq = event_log.append(ev)
        assert seq == 1
        assert event_log.has_event(ev.event_id)

    def test_append_unknown_event_kind_rejected(self) -> None:
        with pytest.raises(ValidationError, match="event_kind"):
            _make_event(event_kind="InventedEvent")

    @pytest.mark.parametrize("kind", sorted(EVENT_KINDS))
    def test_all_blueprint_event_kinds_accepted(self, event_log: EventLog, kind: str) -> None:
        ev = _make_event(event_kind=kind)
        # No debe lanzar.
        event_log.append(ev)

    def test_duplicate_event_id_is_rejected(self, event_log: EventLog) -> None:
        """UAT-07: evento entregado dos veces NO duplica la acción."""
        ev = _make_event(event_id="dup-id")
        event_log.append(ev)
        with pytest.raises(IdempotencyError):
            event_log.append(ev)


class TestEventReconstruction:
    def test_events_for_run_returns_in_sequence_order(self, event_log: EventLog) -> None:
        ev1 = _make_event(event_kind="RunCreated", event_id="e1")
        ev2 = _make_event(event_kind="NodeScheduled", event_id="e2")
        ev3 = _make_event(event_kind="RunCompleted", event_id="e3")
        event_log.append(ev1)
        event_log.append(ev2)
        event_log.append(ev3)
        out = event_log.events_for_run(tenant_id="t", project_id="p", run_id="r-1")
        assert [e["event_id"] for e in out] == ["e1", "e2", "e3"]

    def test_events_for_run_filters_by_project_and_run(self, event_log: EventLog) -> None:
        a = RuntimeEvent(
            event_id="a",
            tenant_id="t",
            project_id="pA",
            event_kind="RunCreated",
            run_id="r-A",
            resource_ref="run/r-A",
            causation_id=None,
            correlation_id=None,
            payload={},
        )
        b = RuntimeEvent(
            event_id="b",
            tenant_id="t",
            project_id="pA",
            event_kind="RunCreated",
            run_id="r-B",
            resource_ref="run/r-B",
            causation_id=None,
            correlation_id=None,
            payload={},
        )
        event_log.append(a)
        event_log.append(b)
        out_a = event_log.events_for_run(tenant_id="t", project_id="pA", run_id="r-A")
        out_b = event_log.events_for_run(tenant_id="t", project_id="pA", run_id="r-B")
        assert [e["event_id"] for e in out_a] == ["a"]
        assert [e["event_id"] for e in out_b] == ["b"]

    def test_event_payload_round_trip_preserves_data(self, event_log: EventLog) -> None:
        payload = {"k": 1, "nested": {"x": [1, 2, 3]}}
        ev = RuntimeEvent(
            event_id="p",
            tenant_id="t",
            project_id="p",
            event_kind="RunCreated",
            run_id="r-1",
            resource_ref="r",
            causation_id=None,
            correlation_id=None,
            payload=payload,
        )
        event_log.append(ev)
        out = event_log.events_for_run(tenant_id="t", project_id="p", run_id="r-1")[0]
        assert out["payload"] == payload
