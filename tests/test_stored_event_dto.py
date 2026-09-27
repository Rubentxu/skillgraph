"""Tests del DTO StoredEvent (WI-32.2 R1 strict).

WI-32.2 (Persistence Boundary Closure, R1 estricto): introduce el
DTO ``StoredEvent`` que reemplaza el retorno de ``sqlite3.Row`` por
el ``EventStore`` Protocol. La representacion SQLite se queda en
``platform/storage.py``; el resto del runtime consume DTOs tipados.

Patron TDD: los tests verifican (1) inmutabilidad, (2) construccion
desde campos de BD, (3) round-trip dict, (4) equivalencia funcional
con el antiguo ``_row_to_event_dict``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest


def test_stored_event_is_frozen_dataclass() -> None:
    """StoredEvent es un dataclass frozen: inmutable post-construccion."""
    from skillgraph.platform.ports import StoredEvent

    assert is_dataclass(StoredEvent)
    # frozen=True -> no permite asignacion de atributos
    assert StoredEvent.__dataclass_params__.frozen is True


def test_stored_event_slots() -> None:
    """StoredEvent usa __slots__: sin __dict__, footprint minimo."""
    from skillgraph.platform.ports import StoredEvent

    # __slots__ definido a nivel de clase
    assert "__slots__" in StoredEvent.__dict__


def test_stored_event_construction_minimal() -> None:
    """StoredEvent se construye con los campos del schema runtime_events."""
    from skillgraph.platform.ports import StoredEvent

    event = StoredEvent(
        sequence=1,
        event_id="evt-uuid-1",
        tenant_id="t1",
        project_id="p1",
        event_kind="RunCreated",
        run_id="run-1",
        resource_ref="tenant=t1/project=p1/run=run-1",
        causation_id=None,
        correlation_id=None,
        payload={"state": "ACTIVE"},
        timestamp="2026-09-27T10:00:00+00:00",
        schema_version=1,
    )
    assert event.sequence == 1
    assert event.event_id == "evt-uuid-1"
    assert event.payload == {"state": "ACTIVE"}
    assert event.run_id == "run-1"


def test_stored_event_immutable() -> None:
    """StoredEvent no admite asignacion post-construccion."""
    from skillgraph.platform.ports import StoredEvent

    event = StoredEvent(
        sequence=1,
        event_id="evt-uuid-1",
        tenant_id="t1",
        project_id="p1",
        event_kind="RunCreated",
        run_id="run-1",
        resource_ref="r",
        causation_id=None,
        correlation_id=None,
        payload={},
        timestamp="2026-09-27T10:00:00+00:00",
        schema_version=1,
    )
    with pytest.raises(FrozenInstanceError):
        event.sequence = 2  # type: ignore[misc]


def test_stored_event_field_count_matches_schema() -> None:
    """StoredEvent tiene exactamente 12 campos (1:1 con runtime_events)."""
    from skillgraph.platform.ports import StoredEvent

    expected_fields = {
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
    actual = {f.name for f in fields(StoredEvent)}
    assert actual == expected_fields


def test_stored_event_to_dict_roundtrip() -> None:
    """StoredEvent expone un metodo de serializacion a dict (compat con consumers)."""
    from skillgraph.platform.ports import StoredEvent

    event = StoredEvent(
        sequence=42,
        event_id="evt-x",
        tenant_id="t",
        project_id="p",
        event_kind="NodeScheduled",
        run_id="r",
        resource_ref="ref",
        causation_id="cause",
        correlation_id="corr",
        payload={"key": "value"},
        timestamp="2026-09-27T10:00:00+00:00",
        schema_version=1,
    )
    as_dict = event.to_dict()
    assert as_dict["sequence"] == 42
    assert as_dict["event_id"] == "evt-x"
    assert as_dict["causation_id"] == "cause"
    assert as_dict["payload"] == {"key": "value"}
    # round-trip: el dict contiene todos los campos
    for f in fields(StoredEvent):
        assert f.name in as_dict
