"""Tests UAT-06 honestos (sin presupuesto para max-iterations).

El bug original (commit previo al actual) observaba que con
`max-iterations=2` el run acababa COMPLETED tras 1 sola llamada a
`cmd_run`. Estos tests atacan el comportamiento real del RunController
directamente (no via CLI) con un adapter FakeAgentAdapter + fixtures
correctamente sembradas.

Si estos tests pasan, el bug NO existe en la implementacion actual:
cada llamada a `reconcile_run` ejecuta UN nodo del current_node. El
max-iterations del CLI es real, y la UAT-06 es verificable.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from skillgraph.agent import FakeAgentAdapter
from skillgraph.runcontroller import RunController
from skillgraph.storage import Storage
from skillgraph.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

TENANT = "t"
PROJECT = "p"


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )


def _plan_a_b_c() -> WorkflowPlan:
    return WorkflowPlan(
        nodes=(_node("a"), _node("b"), _node("c")),
        transitions=(
            WorkflowTransition(source="a", outcome="ok", target="b"),
            WorkflowTransition(source="b", outcome="ok", target="c"),
        ),
        initial="a",
    )


def _seed_ok_fixtures(fixtures_root: Path) -> None:
    for name in ("a", "b", "c"):
        p = fixtures_root / TENANT / PROJECT / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"outcome":"ok","result":{}}')


def _exec_count(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM node_executions WHERE run_id = ?", (run_id,)
    ).fetchone()
    return int(row[0]) if row else 0


class TestReconcileOneNodePerCall:
    """Verifica que `reconcile_run` ejecuta UN nodo por llamada."""

    def _build(self, tmp_path: Path) -> tuple[Storage, RunController, WorkflowPlan]:
        storage = Storage(tmp_path / "project.sqlite")
        fixtures_root = tmp_path / "fx"
        fixtures_root.mkdir()
        _seed_ok_fixtures(fixtures_root)
        adapter = FakeAgentAdapter(fixtures_root)
        conn = storage._conn  # type: ignore[attr-defined]
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        return storage, ctl, _plan_a_b_c()

    def test_first_reconcile_executes_only_a(self, tmp_path: Path) -> None:
        """Una sola llamada ejecuta UN nodo (a), deja run ACTIVE en b."""
        storage, ctl, plan = self._build(tmp_path)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "ACTIVE"
        assert snap.current_node == "b"
        assert list(snap.executed_nodes) == ["a"]
        conn = storage._conn  # type: ignore[attr-defined]
        assert _exec_count(conn, run_id) == 1

    def test_second_reconcile_executes_only_b(self, tmp_path: Path) -> None:
        storage, ctl, plan = self._build(tmp_path)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        snap2 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap2.state == "ACTIVE"
        assert snap2.current_node == "c"
        assert list(snap2.executed_nodes) == ["a", "b"]
        conn = storage._conn  # type: ignore[attr-defined]
        assert _exec_count(conn, run_id) == 2

    def test_three_reconciles_complete_run(self, tmp_path: Path) -> None:
        """Tres llamadas (una por nodo) completan el run."""
        storage, ctl, plan = self._build(tmp_path)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snaps = [
            ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id) for _ in range(3)
        ]
        assert snaps[0].state == "ACTIVE" and snaps[0].current_node == "b"
        assert list(snaps[0].executed_nodes) == ["a"]
        assert snaps[1].state == "ACTIVE" and snaps[1].current_node == "c"
        assert list(snaps[1].executed_nodes) == ["a", "b"]
        assert snaps[2].state == "COMPLETED"
        assert snaps[2].current_node is None
        assert list(snaps[2].executed_nodes) == ["a", "b", "c"]
        conn = storage._conn  # type: ignore[attr-defined]
        assert _exec_count(conn, run_id) == 3

    def test_max_iterations_one_leaves_run_active(self, tmp_path: Path) -> None:
        """Verifica que el caller (CLI) puede cortar el bucle.

        Aqui simulamos el comportamiento del CLI: si el caller hace
        UNA sola llamada y para, el run queda ACTIVE en b (no terminal).
        Esto es lo que UAT-06 necesita: poder interrumpir entre nodos.
        """
        storage, ctl, plan = self._build(tmp_path)
        _ = storage
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        # Caller decide parar aqui (simula crash / max-iter=1).
        assert snap.state == "ACTIVE"
        assert snap.current_node == "b"
        assert list(snap.executed_nodes) == ["a"]
        # Resume: una nueva llamada continua desde b.
        snap2 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap2.state == "ACTIVE"
        assert snap2.current_node == "c"
