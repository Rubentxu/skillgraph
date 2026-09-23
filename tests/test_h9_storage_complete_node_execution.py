"""Tests focales de `Storage.complete_node_execution`, la API añadida
en H9-BSlice3-S6 para sustituir el UPDATE directo del
``RunController._execute_one`` (parte SUCCEEDED).

Cubre:
- Contrato observable: state=SUCCEEDED, outcome, result_json,
  finished_at materializado.
- Aislamiento por node_execution_id.
- No emite eventos.
- Red de seguridad (introspeccion): el UPDATE directo de
  SUCCEEDED esta fuera de _execute_one del RunController.
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


class TestCompleteNodeExecution:
    def test_transitions_running_to_succeeded(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-s6", "ne-1")

        s.complete_node_execution(
            node_execution_id="ne-1",
            outcome="ok",
            result_json='{"x":1}',
        )

        row = conn.execute(
            "SELECT state, outcome, result_json, finished_at FROM "
            "node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        assert row["state"] == "SUCCEEDED"
        assert row["outcome"] == "ok"
        assert row["result_json"] == '{"x":1}'
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

        s.complete_node_execution(
            node_execution_id="ne-1",
            outcome="ok",
            result_json="{}",
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
        """UPDATE no-op: si el ne_id no existe, la fila queda intacta."""
        s, _conn, _adapter = storage
        # No raise.
        s.complete_node_execution(
            node_execution_id="ghost-ne",
            outcome="ok",
            result_json="{}",
        )

    def test_isolates_by_node_execution_id(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Solo el ne indicado cambia; otros quedan intactos."""
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-A", "ne-1")
        _seed_run_and_running_node(s, conn, adapter, "run-B", "ne-2")

        s.complete_node_execution(
            node_execution_id="ne-1",
            outcome="ok",
            result_json='{"a":1}',
        )

        row1 = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        row2 = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-2'"
        ).fetchone()
        assert row1["state"] == "SUCCEEDED"
        assert row2["state"] == "RUNNING"

    def test_result_json_passed_through_as_string(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Storage NO serializa: el caller pasa la string ya hecha.

        Esto blinda contra una regresion donde Storage intente
        serializar (perdiendo el sort_keys=True del caller).
        """
        s, conn, adapter = storage
        _seed_run_and_running_node(s, conn, adapter, "run-rj", "ne-1")

        # Una string arbitraria (no JSON valido a proposito).
        s.complete_node_execution(
            node_execution_id="ne-1",
            outcome="ok",
            result_json="not-actually-json",
        )

        row = conn.execute(
            "SELECT result_json FROM node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        assert row["result_json"] == "not-actually-json"


class TestRunControllerExecuteOneNoLongerUpdateDirect:
    """Garantia: el UPDATE directo de SUCCEEDED esta fuera de _execute_one."""

    def test_execute_one_source_has_no_update_for_running_or_succeeded(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._execute_one)
        # Ni INSERT INTO node_executions (S5), ni
        # UPDATE node_executions SET state='SUCCEEDED' (S6).
        assert not re.search(r"\bINSERT\s+INTO\s+node_executions\b", src, re.IGNORECASE)
        # El S7 (_mark_node_failed) sigue en su sitio, asi que NO
        # bloqueamos UPDATE node_executions sin mas: lo que S6
        # reemplazaba es la linea con state='SUCCEEDED'. Esa
        # expresion es especifica: la linea borrada era
        # 'SET state = \'SUCCEEDED\''.
        assert "SET state = 'SUCCEEDED'" not in src, (
            "SET state = 'SUCCEEDED' presente en _execute_one: "
            "el UPDATE SUCCEEDED deberia estar delegado"
        )
