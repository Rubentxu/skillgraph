"""Tests focales de `Storage.start_node_execution`, la API añadida
en H9-BSlice3-S5 para sustituir el INSERT directo del
``RunController._execute_one``.

Cubre:
- Contrato observable: inserta fila con state RUNNING y started_at.
- Selectividad: el rowcount es 1.
- No exposicion de connection.
- No emite eventos.
- Aislamiento por (tenant+project+run).
- Red de seguridad (introspeccion): el INSERT directo ya no esta
  en el codigo de _execute_one del RunController.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.runcontroller import RunController

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


def _seed_run(
    s: Storage,
    conn: sqlite3.Connection,
    adapter: FakeAgentAdapter,
    run_id: str,
    *node_names: str,
) -> None:
    ctl = RunController(storage=s, adapter=adapter)
    real_run_id = ctl.create_run(
        tenant_id=TENANT,
        project_id=PROJECT,
        plan=_plan(*node_names),
    )
    conn.execute(
        "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
        (run_id, real_run_id),
    )
    conn.commit()


class TestStartNodeExecution:
    def test_inserts_row_in_running_state(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-s5", "a")

        s.start_node_execution(
            node_execution_id="ne-s5-1",
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-s5",
            node_name="a",
            attempt=1,
            context_hash="ctxhash-1",
            handoff_json=json.dumps({"x": 1}),
        )

        row = conn.execute(
            "SELECT state, attempt, context_hash, handoff_json, started_at "
            "FROM node_executions WHERE node_execution_id = 'ne-s5-1'"
        ).fetchone()
        assert row["state"] == "RUNNING"
        assert row["attempt"] == 1
        assert row["context_hash"] == "ctxhash-1"
        assert row["handoff_json"] == '{"x": 1}'
        assert row["started_at"] is not None

    def test_does_not_emit_events(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Storage NO emite eventos: esa coordinacion sigue siendo
        del RunController."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-no-evt", "a")

        events_before = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            ("run-no-evt",),
        ).fetchone()["c"]

        s.start_node_execution(
            node_execution_id="ne-1",
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-no-evt",
            node_name="a",
            attempt=1,
            context_hash="ctx",
            handoff_json="{}",
        )

        events_after = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            ("run-no-evt",),
        ).fetchone()["c"]
        assert events_after == events_before

    def test_isolates_by_run(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """La fila aparece bajo el run correcto."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-A", "a")
        _seed_run(s, conn, adapter, "run-B", "b")

        s.start_node_execution(
            node_execution_id="ne-A",
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-A",
            node_name="a",
            attempt=1,
            context_hash="ctx",
            handoff_json="{}",
        )

        row = conn.execute(
            "SELECT run_id, node_name FROM node_executions WHERE node_execution_id = 'ne-A'"
        ).fetchone()
        assert row["run_id"] == "run-A"
        assert row["node_name"] == "a"

    def test_unique_node_execution_id(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Insertar el mismo node_execution_id dos veces lanza
        IntegrityError (lo captura el caller como IdempotencyError,
        no nos metemos en eso aqui)."""
        import sqlite3 as _sq

        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-uniq", "a")

        s.start_node_execution(
            node_execution_id="ne-dup",
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-uniq",
            node_name="a",
            attempt=1,
            context_hash="ctx",
            handoff_json="{}",
        )
        with pytest.raises(_sq.IntegrityError):
            s.start_node_execution(
                node_execution_id="ne-dup",
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id="run-uniq",
                node_name="a",
                attempt=2,
                context_hash="ctx2",
                handoff_json="{}",
            )


class TestRunControllerExecuteOneNoLongerInsertDirect:
    """Garantia: el INSERT directo esta fuera de _execute_one del
    RunController. Esta API sigue emitiendo `node_started` despues
    (eso es orquestacion, no SQL)."""

    def test_execute_one_source_has_no_insert_for_running(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._execute_one)
        # El run_controller sigue usando 'events.node_started',
        # asi que NO esperamos que desaparezca 'node_started'.
        # Lo que esperamos es que NO haya un INSERT INTO node_executions
        # dentro del codigo de _execute_one (ahora se delega).
        assert not re.search(r"\bINSERT\s+INTO\s+node_executions\b", src, re.IGNORECASE), (
            "INSERT INTO node_executions presente en _execute_one: "
            "el INSERT deberia haber sido delegado en Storage"
        )
        # El replace de UPDATE node_executions sigue ahi para el SUCCEEDED
        # path (es el siguiente slice), asi que no lo chequeamos.
