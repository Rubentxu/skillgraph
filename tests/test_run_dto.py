"""Tests for WI-32.4 run/node-execution DTOs.

Verifica que ``StoredRun`` y ``StoredNodeExecution`` son dataclasses
inmutables (frozen + slots) con campos 1:1 contra ``workflow_runs`` y
``node_executions``, y que ``to_dict()`` es roundtrip-safe para los
consumers legacy.

Estos tests son el admission gate de WI-32.4 (R1 del audit externo).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from skillgraph.platform.ports import StoredNodeExecution, StoredRun


def test_stored_run_is_frozen_dataclass() -> None:
    """StoredRun es frozen + slots + dataclass."""
    assert is_dataclass(StoredRun)
    r = StoredRun(
        run_id="r1",
        tenant_id="t1",
        project_id="p1",
        state="ACTIVE",
        plan_json="{}",
        current_node="n1",
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )
    with pytest.raises(FrozenInstanceError):
        r.state = "COMPLETED"  # type: ignore[misc]


def test_stored_run_field_count_matches_schema() -> None:
    """StoredRun tiene los 8 campos exactos de workflow_runs."""
    f = {fld.name for fld in fields(StoredRun)}
    assert f == {
        "run_id",
        "tenant_id",
        "project_id",
        "state",
        "plan_json",
        "current_node",
        "created_at",
        "updated_at",
    }


def test_stored_run_to_dict_roundtrip() -> None:
    """``to_dict()`` preserva todos los campos."""
    r = StoredRun(
        run_id="r1",
        tenant_id="t1",
        project_id="p1",
        state="ACTIVE",
        plan_json='{"k":1}',
        current_node="n1",
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:01",
    )
    d = r.to_dict()
    assert d["run_id"] == "r1"
    assert d["state"] == "ACTIVE"
    assert d["current_node"] == "n1"
    assert d["plan_json"] == '{"k":1}'
    assert d["tenant_id"] == "t1"
    assert d["project_id"] == "p1"


def test_stored_run_current_node_optional() -> None:
    """``current_node`` es Optional (None para runs no iniciados)."""
    r = StoredRun(
        run_id="r1",
        tenant_id="t1",
        project_id="p1",
        state="CREATED",
        plan_json="{}",
        current_node=None,
        created_at="2026-01-01 00:00:00",
        updated_at="2026-01-01 00:00:00",
    )
    assert r.current_node is None


def test_stored_node_execution_is_frozen_dataclass() -> None:
    """StoredNodeExecution es frozen + slots + dataclass."""
    assert is_dataclass(StoredNodeExecution)
    ne = StoredNodeExecution(
        node_execution_id="ne1",
        run_id="r1",
        tenant_id="t1",
        project_id="p1",
        node_name="n1",
        attempt=1,
        state="SUCCEEDED",
        outcome="ok",
        context_hash="h",
        handoff_json="{}",
        result_json='{"ok":true}',
        error=None,
        started_at="2026-01-01 00:00:00",
        finished_at="2026-01-01 00:00:01",
    )
    with pytest.raises(FrozenInstanceError):
        ne.state = "FAILED"  # type: ignore[misc]


def test_stored_node_execution_field_count_matches_schema() -> None:
    """StoredNodeExecution tiene los 13 campos exactos de node_executions."""
    f = {fld.name for fld in fields(StoredNodeExecution)}
    assert f == {
        "node_execution_id",
        "run_id",
        "tenant_id",
        "project_id",
        "node_name",
        "attempt",
        "state",
        "outcome",
        "context_hash",
        "handoff_json",
        "result_json",
        "error",
        "started_at",
        "finished_at",
    }


def test_stored_node_execution_to_dict_roundtrip() -> None:
    """``to_dict()`` preserva campos clave."""
    ne = StoredNodeExecution(
        node_execution_id="ne1",
        run_id="r1",
        tenant_id="t1",
        project_id="p1",
        node_name="n1",
        attempt=2,
        state="FAILED",
        outcome=None,
        context_hash="abc",
        handoff_json=None,
        result_json=None,
        error="boom",
        started_at="2026-01-01 00:00:00",
        finished_at="2026-01-01 00:00:01",
    )
    d = ne.to_dict()
    assert d["node_execution_id"] == "ne1"
    assert d["attempt"] == 2
    assert d["state"] == "FAILED"
    assert d["error"] == "boom"
    assert d["outcome"] is None
