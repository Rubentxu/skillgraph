"""Tests del RunController (Etapa 2 / S5).

Cubre UAT-04 (ejecucion determinista) y UAT-06 (recuperacion).

Casos:
- create_run emite RunCreated.
- reconcile_run ejecuta un solo nodo terminal y marca Run COMPLETED.
- reconcile_run ejecuta multiples nodos conectados y avanza el current.
- run terminal no emite eventos en reconcile subsiguientes.
- adapter falla -> NodeFailed, run FAILED.
- outcome no declarado -> NodeFailed.
- UAT-06: reanimacion de NodeExecution RUNNING sin finished_at.
- UAT-07: idempotencia via UNIQUE sobre event_id al re-ejecutar.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from skillgraph.agent import FakeAgentAdapter, RecordingAdapter
from skillgraph.errors import IdempotencyError
from skillgraph.runcontroller import RunController
from skillgraph.storage import Storage
from skillgraph.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

TENANT = "t"
PROJECT = "p"


@pytest.fixture
def fixture_setup(tmp_path: Path) -> tuple[Storage, FakeAgentAdapter, sqlite3.Connection]:
    storage_path = tmp_path / "project.sqlite"
    storage = Storage(storage_path)
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    adapter = FakeAgentAdapter(fixtures_root)
    # Acceso al sqlite3.Connection interno del Storage.
    conn = storage._conn  # type: ignore[attr-defined]
    return storage, adapter, conn


def _node(name: str, **overrides: object) -> WorkflowNode:
    base: dict[str, object] = dict(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )
    base.update(overrides)
    return WorkflowNode(**base)  # type: ignore[arg-type]


def _plan(
    nodes: tuple[WorkflowNode, ...],
    transitions: tuple[WorkflowTransition, ...] = (),
) -> WorkflowPlan:
    return WorkflowPlan(nodes=nodes, transitions=transitions, initial=nodes[0].name)


def _seed_fixture(
    fixtures_root: Path,
    *,
    tenant: str,
    project: str,
    node_name: str,
    outcome: str,
    payload: dict[str, object] | None = None,
) -> None:
    p = fixtures_root / tenant / project / f"{node_name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"outcome": outcome, "result": payload or {}, "evidence_ref": f"ev-{node_name}"})
    )


def _seed_fixtures_for_plan(
    fixtures_root: Path,
    plan: WorkflowPlan,
    *,
    outcome_for: dict[str, str],
) -> None:
    """Para cada nodo del plan, escribe una fixture con outcome dado."""
    for n in plan.nodes:
        _seed_fixture(
            fixtures_root,
            tenant=TENANT,
            project=PROJECT,
            node_name=n.name,
            outcome=outcome_for.get(n.name, "ok"),
        )


class TestCreateRun:
    def test_create_run_inserts_workflow_runs_row(
        self, fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection]
    ) -> None:
        storage, adapter, conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        row = conn.execute(
            "SELECT state, current_node FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row["state"] == "CREATED"
        assert row["current_node"] == "a"

    def test_create_run_emits_run_created_event(
        self, fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection]
    ) -> None:
        storage, adapter, conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        rows = conn.execute(
            "SELECT event_kind FROM runtime_events WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        ).fetchall()
        assert [r["event_kind"] for r in rows] == ["RunCreated"]


class TestReconcileTerminal:
    def test_single_node_completes_run(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan((_node("a"),))
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "COMPLETED"
        assert snap.executed_nodes == ("a",)
        assert snap.current_node is None

    def test_completed_run_does_not_emit_on_reconcile(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan((_node("a"),))
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        events_before = conn.execute(
            "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
        snap2 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        events_after = conn.execute(
            "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
        assert snap2.state == "COMPLETED"
        assert events_before == events_after


class TestReconcileSequential:
    def test_two_nodes_advance_via_two_reconciles(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan(
            nodes=(_node("a"), _node("b")),
            transitions=(WorkflowTransition("a", "ok", "b"),),
        )
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="b", outcome="done")
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap1 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap1.state == "ACTIVE"
        assert snap1.executed_nodes == ("a",)
        assert snap1.current_node == "b"
        snap2 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap2.state == "COMPLETED"
        assert snap2.executed_nodes == ("a", "b")
        assert snap2.current_node is None


class TestReconcileFailure:
    def test_missing_fixture_fails_node(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan((_node("a"),))
        # NO sembramos fixture.
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "FAILED"
        node_state = conn.execute(
            "SELECT state, error FROM node_executions WHERE node_name = 'a' AND run_id = ?",
            (run_id,),
        ).fetchone()
        assert node_state["state"] == "FAILED"
        assert "fixture" in node_state["error"].lower()

    def test_outcome_not_declared_in_plan_fails(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        # Plan solo declara outcome "ok".
        plan = _plan(
            nodes=(_node("a"), _node("b")),
            transitions=(WorkflowTransition("a", "ok", "b"),),
        )
        _seed_fixture(
            fixtures_root,
            tenant=TENANT,
            project=PROJECT,
            node_name="a",
            outcome="surprise",  # NO declarado
        )
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "FAILED"
        node_state = conn.execute(
            "SELECT state, error FROM node_executions WHERE node_name = 'a' AND run_id = ?",
            (run_id,),
        ).fetchone()
        assert node_state["state"] == "FAILED"
        assert "declarado" in node_state["error"]


class TestRecovery:
    def test_running_node_without_finished_at_is_recovered(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """UAT-06: tras un crash, el siguiente reconcile reanuda desde
        un punto seguro (no re-ejecuta eventos confirmados, vuelve a
        READY los RUNNING colgados)."""
        storage, adapter, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan((_node("a"),))
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        # Simulamos crash: insertamos manualmente un NodeExecution RUNNING
        # sin finished_at para el nodo a.
        conn.execute(
            """
            INSERT INTO node_executions
                (node_execution_id, run_id, tenant_id, project_id,
                 node_name, attempt, state, context_hash, started_at)
            VALUES (?, ?, ?, ?, ?, 1, 'RUNNING', 'fakehash', datetime('now'))
            """,
            ("ne-crashed", run_id, TENANT, PROJECT, "a"),
        )
        conn.commit()
        # Primer reconcile: detecta la interrupcion y lo devuelve a READY,
        # luego ejecuta normalmente.
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "COMPLETED"
        # Debe haber dos NodeExecutions para 'a': la colgada (READY) y la
        # nueva (SUCCEEDED).
        rows = conn.execute(
            "SELECT state FROM node_executions WHERE node_name = 'a' AND run_id = ? ORDER BY started_at",
            (run_id,),
        ).fetchall()
        states = [r["state"] for r in rows]
        assert "READY" in states
        assert "SUCCEEDED" in states


class TestIdempotency:
    def test_replaying_run_created_event_id_raises(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
    ) -> None:
        """UAT-07: el UNIQUE sobre event_id garantiza que un evento
        duplicado no duplica la accion."""
        storage, adapter, conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        # Tomamos el event_id del primer RunCreated y lo reusamos.
        row = conn.execute(
            "SELECT event_id FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        from skillgraph.runtime import EventLog, RuntimeEvent

        log = EventLog(conn)
        with pytest.raises(IdempotencyError):
            log.append(
                RuntimeEvent(
                    event_id=row["event_id"],
                    tenant_id=TENANT,
                    project_id=PROJECT,
                    event_kind="RunCreated",
                    run_id=run_id,
                    resource_ref=f"run/{run_id}",
                    causation_id=None,
                    correlation_id=run_id,
                    payload={"replayed": True},
                )
            )


class TestRecordingAdapter:
    def test_adapter_called_once_per_node(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, _, conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan(
            nodes=(_node("a"), _node("b")),
            transitions=(WorkflowTransition("a", "ok", "b"),),
        )
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="b", outcome="done")
        fake = FakeAgentAdapter(fixtures_root)
        rec = RecordingAdapter(fake)
        ctl = RunController(storage=storage, adapter=rec, conn=conn)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert len(rec) == 2
        names = sorted(c.behavior.definition_name for c in rec.calls)
        assert names == ["a", "b"]
