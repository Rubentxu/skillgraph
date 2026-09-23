"""Tests focales de `Storage.recover_interrupted_node_executions`,
la API añadida en H9-BSlice3-S4 para sustituir el bucle de
``RunController._recover_interrupted``.

Cubre:
- Contrato observable: cuenta devuelta, transicion de estado,
  selectividad por (tenant+project+run+state=RUNNING+finished_at IS NULL).
- No afecta a filas que no cumplen los criterios.
- Atomicidad interna: una sola ``UPDATE`` (no bucle).
- Red de seguridad (introspeccion): el metodo privado del
  RunController ya no contiene SQL directo.
"""

from __future__ import annotations

import inspect
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


def _seed_run(
    s: Storage,
    conn: sqlite3.Connection,
    adapter: FakeAgentAdapter,
    run_id: str,
    *node_names: str,
) -> str:
    """Helper: crea un run con plan de N nodos y devuelve run_id real."""
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
    return run_id


def _insert_node_execution(
    conn: sqlite3.Connection,
    *,
    node_execution_id: str,
    run_id: str,
    node_name: str,
    state: str = "RUNNING",
    finished_at: str | None = None,
    finished_at_expr: str | None = None,
) -> None:
    """Inserta un NodeExecution con valores arbitrarios para los tests."""
    if finished_at_expr is not None:
        # e.g. "datetime('now')"
        conn.execute(
            "INSERT INTO node_executions (node_execution_id, run_id, "
            "tenant_id, project_id, node_name, attempt, state, "
            "started_at, finished_at) VALUES (?, ?, ?, ?, ?, 1, ?, "
            "datetime('now'), " + finished_at_expr + ")",
            (node_execution_id, run_id, TENANT, PROJECT, node_name, state),
        )
    else:
        if finished_at is None:
            conn.execute(
                "INSERT INTO node_executions (node_execution_id, run_id, "
                "tenant_id, project_id, node_name, attempt, state, "
                "started_at) VALUES (?, ?, ?, ?, ?, 1, ?, "
                "datetime('now'))",
                (node_execution_id, run_id, TENANT, PROJECT, node_name, state),
            )
        else:
            conn.execute(
                "INSERT INTO node_executions (node_execution_id, run_id, "
                "tenant_id, project_id, node_name, attempt, state, "
                "started_at, finished_at) VALUES (?, ?, ?, ?, ?, 1, ?, "
                "datetime('now'), ?)",
                (
                    node_execution_id,
                    run_id,
                    TENANT,
                    PROJECT,
                    node_name,
                    state,
                    finished_at,
                ),
            )
    conn.commit()


# ---------- Contrato observable ----------


class TestRecoverInterruptedNodeExecutions:
    def test_returns_zero_when_none_running(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-empty", "a")
        count = s.recover_interrupted_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id="run-empty"
        )
        assert count == 0

    def test_transitions_running_without_finished_at(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-rec", "a", "b", "c")
        _insert_node_execution(conn, node_execution_id="ne-1", run_id="run-rec", node_name="a")
        _insert_node_execution(conn, node_execution_id="ne-2", run_id="run-rec", node_name="b")

        count = s.recover_interrupted_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id="run-rec"
        )
        assert count == 2

        row1 = conn.execute(
            "SELECT state, finished_at FROM node_executions WHERE node_execution_id = 'ne-1'"
        ).fetchone()
        row2 = conn.execute(
            "SELECT state, finished_at FROM node_executions WHERE node_execution_id = 'ne-2'"
        ).fetchone()
        assert row1["state"] == "READY"
        assert row1["finished_at"] is not None
        assert row2["state"] == "READY"
        assert row2["finished_at"] is not None

    def test_does_not_touch_succeeded(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-mix", "a", "b")
        # Un RUNNING (debe transicionar)
        _insert_node_execution(conn, node_execution_id="ne-r", run_id="run-mix", node_name="a")
        # Un SUCCEEDED (NO debe transicionar)
        _insert_node_execution(
            conn, node_execution_id="ne-s", run_id="run-mix", node_name="b", state="SUCCEEDED"
        )

        count = s.recover_interrupted_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id="run-mix"
        )
        assert count == 1

        # RUNNING -> READY
        row_r = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-r'"
        ).fetchone()
        # SUCCEEDED intacto
        row_s = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-s'"
        ).fetchone()
        assert row_r["state"] == "READY"
        assert row_s["state"] == "SUCCEEDED"

    def test_does_not_touch_running_with_finished_at(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Nodo RUNNING pero con `finished_at` no es inconsistente: ya termino."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-fty", "a", "b")
        # RUNNING sin finished_at: SI
        _insert_node_execution(conn, node_execution_id="ne-1", run_id="run-fty", node_name="a")
        # RUNNING con finished_at (estado inconsistente): NO cuenta
        _insert_node_execution(
            conn,
            node_execution_id="ne-2",
            run_id="run-fty",
            node_name="b",
            finished_at="2026-09-23 12:00:00",
        )

        count = s.recover_interrupted_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id="run-fty"
        )
        assert count == 1
        # ne-2 sigue RUNNING con su finished_at intacto.
        row2 = conn.execute(
            "SELECT state, finished_at FROM node_executions WHERE node_execution_id = 'ne-2'"
        ).fetchone()
        assert row2["state"] == "RUNNING"
        assert row2["finished_at"] == "2026-09-23 12:00:00"

    def test_isolates_by_run(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Solo afecta al run indicado; otros runs del mismo tenant intactos."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-A", "a")
        _seed_run(s, conn, adapter, "run-B", "b")
        _insert_node_execution(conn, node_execution_id="ne-A", run_id="run-A", node_name="a")
        _insert_node_execution(conn, node_execution_id="ne-B", run_id="run-B", node_name="b")

        count = s.recover_interrupted_node_executions(
            tenant_id=TENANT, project_id=PROJECT, run_id="run-A"
        )
        assert count == 1

        # ne-A pasa a READY
        row_a = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-A'"
        ).fetchone()
        # ne-B intacto
        row_b = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-B'"
        ).fetchone()
        assert row_a["state"] == "READY"
        assert row_b["state"] == "RUNNING"

    def test_isolates_by_tenant_and_project(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Si el tenant o project no coincide, el UPDATE no toca la fila."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-iso", "a")
        _insert_node_execution(conn, node_execution_id="ne-iso", run_id="run-iso", node_name="a")

        # El run esta en (t, p). Si consultamos (other_t, p), cuenta 0
        # y la fila no se toca.
        count = s.recover_interrupted_node_executions(
            tenant_id="other-tenant",
            project_id=PROJECT,
            run_id="run-iso",
        )
        assert count == 0

        row = conn.execute(
            "SELECT state FROM node_executions WHERE node_execution_id = 'ne-iso'"
        ).fetchone()
        assert row["state"] == "RUNNING"


# ---------- Atomicidad interna: una sola UPDATE ----------


class TestSingleUpdateAtomicity:
    def test_issues_single_update_for_multiple_rows(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Compara contra el bucle original: hoy (S4) debe haber UNA
        sola `UPDATE` ejecutada, no N updates por fila."""
        from unittest.mock import MagicMock

        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-atomic", "a", "b", "c", "d")
        for i, ne_id in enumerate(("ne-a", "ne-b", "ne-c", "ne-d")):
            _insert_node_execution(
                conn,
                node_execution_id=ne_id,
                run_id="run-atomic",
                node_name=("a", "b", "c", "d")[i],
            )

        # Wrapeamos `Storage._conn` con un MagicMock que delega al conn
        # real y cuenta los UPDATE sobre `node_executions`. `conn.execute`
        # es read-only, pero `_conn` (atributo Storage) sí es reasignable.
        real_conn = s._conn  # type: ignore[attr-defined]
        updates_count = {"n": 0}

        def counting_execute(sql: str, *args: object, **kw: object):
            if "UPDATE node_executions" in sql:
                updates_count["n"] += 1
            return real_conn.execute(sql, *args, **kw)

        wrapped = MagicMock(wraps=real_conn)
        wrapped.execute.side_effect = counting_execute
        wrapped.__enter__.return_value = wrapped  # soporta `with`
        wrapped.__exit__.return_value = False

        try:
            s._conn = wrapped  # type: ignore[assignment]
            count = s.recover_interrupted_node_executions(
                tenant_id=TENANT, project_id=PROJECT, run_id="run-atomic"
            )
        finally:
            s._conn = real_conn  # type: ignore[assignment]

        assert count == 4
        assert updates_count["n"] == 1, (
            f"se esperaba 1 UPDATE; se ejecutaron {updates_count['n']}. "
            f"El refactor ha vuelto a un bucle."
        )


# ---------- Red de seguridad: introspeccion del RunController ----------


class TestRunControllerNoLongerSqlInRecoverInterrupted:
    """Garantia: el metodo privado del RunController ya no contiene SQL."""

    def test_recover_interrupted_has_no_sql(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._recover_interrupted)
        # Buscamos SQL como palabras completas (regex word boundary).
        for stmt in ("SELECT", "UPDATE", "INSERT", "DELETE"):
            pattern = r"\b" + stmt + r"\b"
            assert re.search(pattern, src) is None, (
                f"{stmt} como SQL presente en _recover_interrupted"
            )
        assert "_conn.execute" not in src, "_conn.execute presente: la operacion no se ha delegado"
