"""Tests focales de `Storage.mark_node_failed`, la API añadida en
H9-BSlice3-S7 para sustituir el UPDATE directo del
``RunController._mark_node_failed``.

Cubre:
- Contrato observable: state=FAILED, error, finished_at.
- No emite eventos.
- Aislamiento por node_execution_id.
- Noop para ne_id inexistente.
- Red de seguridad: el UPDATE directo de FAILED esta fuera de
  _mark_node_failed del RunController.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from skillgraph.agent import FakeAgentAdapter
from skillgraph.runcontroller import RunController
from skillgraph.storage import Storage
from skillgraph.workflow import WorkflowNode, WorkflowPlan

TENANT = "t"
PROJECT = "p"


@pytest.fixture
def storage(
    tmp_path: Path,
) -> tuple[Storage, sqlite3.Connection, FakeAgentAdapter]:
    storage_path = tmp_path / "project.sqlite"
    storage = Storage(storage_path)
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    adapter = FakeAgentAdapter(fixtures_root)
    return storage, storage._conn, adapter  # type: ignore[attr-defined]


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )


def _plan(*names: str) -> WorkflowPlan:
    nodes = tuple(_node(n) for n in names)
    return WorkflowPlan(nodes=nodes, transitions=(), initial=nodes[0].name)


def _seed_run_and_running_node(
    s: Storage,
    conn: sqlite3.Connection,
    adapter: FakeAgentAdapter,
    run_id: str,
    node_execution_id: str,
    node_name: str = "a",
) -> None:
    ctl = RunController(storage=s, adapter=adapter)
    real_run_id = ctl.create_run(
        tenant_id=TENANT,
        project_id=PROJECT,
        plan=_plan(node_name),
    )
    conn.execute(
        "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
        (run_id, real_run_id),
    )
    conn.execute(
        "INSERT INTO node_executions (node_execution_id, run_id, "
        "tenant_id, project_id, node_name, attempt, state, "
        "context_hash, handoff_json, started_at) VALUES (?, ?, ?, "
        "?, ?, 1, 'RUNNING', 'ctx', '{}', datetime('now'))",
        (node_execution_id, run_id, TENANT, PROJECT, node_name),
    )
    conn.commit()


class TestMarkNodeFailed:
    def test_transitions_running_to_failed(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-s7", "ne-1")

        s.mark_node_failed(
            node_execution_id="ne-1",
            error="boom",
        )

        row = conn.execute(
            "SELECT state, error, finished_at FROM node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        assert row["state"] == "FAILED"
        assert row["error"] == "boom"
        assert row["finished_at"] is not None

    def test_does_not_emit_events(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Storage NO emite eventos: el RunController orquesta."""
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-no-evt", "ne-1")

        events_before = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            ("run-no-evt",),
        ).fetchone()["c"]

        s.mark_node_failed(
            node_execution_id="ne-1",
            error="x",
        )

        events_after = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            ("run-no-evt",),
        ).fetchone()["c"]
        assert events_after == events_before

    def test_noop_for_unknown_node_execution(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """UPDATE no-op: si el ne_id no existe, no raise."""
        s, _conn, _adapter = storage
        # No raise.
        s.mark_node_failed(
            node_execution_id="ghost-ne",
            error="x",
        )

    def test_isolates_by_node_execution_id(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-A", "ne-1")
        _seed_run_and_running_node(s, conn, adapter, "run-B", "ne-2")

        s.mark_node_failed(
            node_execution_id="ne-1",
            error="only-1",
        )

        row1 = conn.execute(
            "SELECT state, error FROM node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        row2 = conn.execute(
            "SELECT state, error FROM node_executions WHERE node_execution_id = 'ne-2'"
        ).fetchone()
        assert row1["state"] == "FAILED" and row1["error"] == "only-1"
        assert row2["state"] == "RUNNING" and row2["error"] is None

    def test_error_passed_through_verbatim(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Storage NO transforma el error: el caller ya lo formatea.

        Esto blinda contra una regresion donde Storage intente
        serializar, truncar o sustituir el error.
        """
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-rj", "ne-1")

        s.mark_node_failed(
            node_execution_id="ne-1",
            error="something with newline\nand unicode: \u2603",
        )

        row = conn.execute(
            "SELECT error FROM node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        assert row["error"] == "something with newline\nand unicode: \u2603"


class TestRunControllerMarkNodeFailedNoLongerUpdateDirect:
    """Garantia: el UPDATE directo de FAILED esta fuera de
    ``RunController._mark_node_failed``.
    """

    def test_mark_node_failed_source_has_no_update_node_executions(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._mark_node_failed)
        # El UPDATE directo tiene la firma completa: 'UPDATE
        # node_executions'. Filtramos por ese patron exacto.
        assert not re.search(r"\bUPDATE\s+node_executions\b", src, re.IGNORECASE), (
            "UPDATE node_executions presente en _mark_node_failed: "
            "deberia delegarse en Storage.mark_node_failed"
        )
