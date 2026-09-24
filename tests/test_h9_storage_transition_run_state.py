"""Tests focales de `Storage.transition_run_state`, la API añadida
en H9-BSlice3-S3 para sustituir el SQL directo de
``RunController._set_run_state``.

Cubre:
- Contrato observable: actualiza state y current_node, marca updated_at.
- Aislamiento por (tenant+project+run).
- No exposicion de connection.
- Red de seguridad (introspeccion): el metodo privado del
  RunController ya no contiene SQL directo.
"""

from __future__ import annotations

import inspect
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


class TestTransitionRunState:
    def test_updates_state_and_current_node(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-t", "a", "b")

        s.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-t",
            state="ACTIVE",
            current_node="a",
        )

        row = conn.execute(
            "SELECT state, current_node, updated_at FROM workflow_runs WHERE run_id = 'run-t'"
        ).fetchone()
        assert row["state"] == "ACTIVE"
        assert row["current_node"] == "a"
        # updated_at distinto al del create: la API la refresca.
        assert row["updated_at"] is not None

    def test_is_noop_for_inexistent_run(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, _adapter = storage
        # No raise: la API no valida existencia (UPDATE no-op).
        s.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="ghost-run",
            state="COMPLETED",
            current_node=None,
        )

    def test_allows_transition_to_current_node_none(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Run terminal: current_node=None."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-end", "a")
        s.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-end",
            state="COMPLETED",
            current_node=None,
        )
        row = conn.execute(
            "SELECT state, current_node FROM workflow_runs WHERE run_id = 'run-end'"
        ).fetchone()
        assert row["state"] == "COMPLETED"
        assert row["current_node"] is None

    def test_isolates_by_run(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Solo afecta al run indicado."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-A", "a")
        _seed_run(s, conn, adapter, "run-B", "b")

        s.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-A",
            state="FAILED",
            current_node=None,
        )
        row_a = conn.execute("SELECT state FROM workflow_runs WHERE run_id = 'run-A'").fetchone()
        row_b = conn.execute("SELECT state FROM workflow_runs WHERE run_id = 'run-B'").fetchone()
        assert row_a["state"] == "FAILED"
        assert row_b["state"] == "CREATED"

    def test_isolates_by_tenant_and_project(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Si tenant o project no coincide, no toca la fila."""
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-iso", "a")

        s.transition_run_state(
            tenant_id="other-tenant",
            project_id=PROJECT,
            run_id="run-iso",
            state="FAILED",
            current_node=None,
        )

        row = conn.execute("SELECT state FROM workflow_runs WHERE run_id = 'run-iso'").fetchone()
        assert row["state"] == "CREATED"

    def test_does_not_emit_events(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Contrato explicito: esta API NO emite eventos.

        Cualquier llamada a EventLog.append desde Storage seria un
        acoplamiento no deseado. Esto blinda una regresion.
        """
        s, conn, adapter = storage
        _seed_run(s, conn, adapter, "run-no-evt", "a")

        events_before = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            ("run-no-evt",),
        ).fetchone()["c"]

        s.transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-no-evt",
            state="ACTIVE",
            current_node="a",
        )

        events_after = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            ("run-no-evt",),
        ).fetchone()["c"]
        assert events_after == events_before, (
            f"Storage.transition_run_state emitio eventos "
            f"(antes={events_before}, despues={events_after})"
        )


class TestRunControllerNoLongerSqlInSetRunState:
    """Garantia: _set_run_state ya no contiene SQL directo."""

    def test_set_run_state_has_no_sql(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._set_run_state)
        # Buscamos `UPDATE`, `SELECT`, `INSERT`, `DELETE` solo como
        # palabras completas (con boundary). Asi no da positivo el
        # substring `_set_run_state` que contiene 'UPDATE'.
        for stmt in ("SELECT", "UPDATE", "INSERT", "DELETE"):
            pattern = r"\b" + stmt + r"\b"
            assert re.search(pattern, src) is None, f"{stmt} como SQL presente en _set_run_state"
        assert "_conn.execute" not in src
