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

from skillgraph.core.errors import IdempotencyError
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition
from skillgraph.runtime.agent import FakeAgentAdapter, RecordingAdapter
from skillgraph.runtime.runcontroller import RunController

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
        ctl = RunController(storage=storage, adapter=adapter)
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
        ctl = RunController(storage=storage, adapter=adapter)
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
        storage, adapter, _conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan((_node("a"),))
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        ctl = RunController(storage=storage, adapter=adapter)
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
        ctl = RunController(storage=storage, adapter=adapter)
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
        storage, adapter, _conn = fixture_setup
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir(exist_ok=True)
        plan = _plan(
            nodes=(_node("a"), _node("b")),
            transitions=(WorkflowTransition("a", "ok", "b"),),
        )
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="a", outcome="ok")
        _seed_fixture(fixtures_root, tenant=TENANT, project=PROJECT, node_name="b", outcome="done")
        ctl = RunController(storage=storage, adapter=adapter)
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
        ctl = RunController(storage=storage, adapter=adapter)
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
        ctl = RunController(storage=storage, adapter=adapter)
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
        ctl = RunController(storage=storage, adapter=adapter)
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
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        # Tomamos el event_id del primer RunCreated y lo reusamos.
        row = conn.execute(
            "SELECT event_id FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        from skillgraph.runtime.engine import EventLog, RuntimeEvent

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
        storage, _, _conn = fixture_setup
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
        ctl = RunController(storage=storage, adapter=rec)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert len(rec) == 2
        names = sorted(c.behavior.definition_name for c in rec.calls)
        assert names == ["a", "b"]


def _seed_adapter_fixture(tmp_path):
    fixtures_root = tmp_path / "fixtures_helper"
    fixtures_root.mkdir()
    return FakeAgentAdapter(fixtures_root)


def _seed_adapter_fixture(tmp_path):
    """Construye un FakeAgentAdapter con su propio fixtures_root."""
    fixtures_root = tmp_path / "fixtures_helper"
    fixtures_root.mkdir()
    return FakeAgentAdapter(fixtures_root)


class TestFailNodeWithHelper:
    """El helper `_fail_node_with(exc=...)` centraliza el formato de
    error de `_mark_node_failed`. Estos tests verifican el contrato:
    acepta cualquier excepción, no re-lanza, y delega correctamente.
    """

    def test_helper_accepts_arbitrary_exception(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """El helper debe aceptar Exception genérica sin re-lanzar."""
        storage, _adapter, _conn = fixture_setup
        ctl = RunController(storage=storage, adapter=_seed_adapter_fixture(tmp_path))
        ctl.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan=_plan((_node("a"),)),
        )
        # No debe lanzar: UPDATE de una NodeExecution inexistente es no-op.
        ctl._fail_node_with(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="r-test-1",
            node_execution_id="ne-no-existe",
            node_name="a",
            exc=ValueError("boom"),
        )

    def test_helper_accepts_skill_graph_error(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """El helper debe aceptar subclases de SkillGraphError, que es
        el caso real que la rama de compilación de contexto emite."""
        from skillgraph.core.errors import SkillGraphError

        storage, _adapter, _conn = fixture_setup
        ctl = RunController(storage=storage, adapter=_seed_adapter_fixture(tmp_path))
        ctl.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan=_plan((_node("a"),)),
        )
        ctl._fail_node_with(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="r-test-2",
            node_execution_id="ne-no-existe",
            node_name="a",
            exc=SkillGraphError("stale claim o cualquier subtype"),
        )

    def test_helper_persists_error_for_existing_node_execution(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """Si la NodeExecution existe, el helper debe persistir el
        error con formato '<Type>: <message>' en node_executions.error.
        """
        storage, _adapter, conn = fixture_setup
        ctl = RunController(storage=storage, adapter=_seed_adapter_fixture(tmp_path))
        # create_run inserta la NodeExecution en RUNNING via start.
        run_id = ctl.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan=_plan((_node("a"),)),
        )
        # Sembrar manualmente una NodeExecution mínima para que el
        # helper tenga fila que actualizar.
        node_execution_id = "ne-x"
        from skillgraph.runtime.engine import EventBuilder
        event = EventBuilder(
            tenant_id=TENANT,
            project_id=PROJECT,
            correlation_id=run_id,
        ).node_started(
            run_id=run_id,
            node_execution_id=node_execution_id,
        )
        ctl._storage.start_node_execution_atomically(
            event=event,
            node_execution_id=node_execution_id,
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            node_name="a",
            attempt=1,
            context_hash="",
            handoff_json="{}",
        )
        ctl._fail_node_with(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            node_execution_id=node_execution_id,
            node_name="a",
            exc=ValueError("boom-test"),
        )
        row = conn.execute(
            "SELECT state, error FROM node_executions WHERE node_execution_id = ?",
            (node_execution_id,),
        ).fetchone()
        assert row["state"] == "FAILED"
        assert row["error"] == "ValueError: boom-test"


class TestCancelRun:
    """Contrato de `RunController.cancel_run`.

    Cubre el slice S1 del roadmap Etapa 7 (presupuestos y cancelacion):
    el operador puede detener un run que esta ACTIVE sin esperar a
    que el reconcile completo termine. Emite `RunCompleted` con
    `state=CANCELLED` de forma atomica con la transicion de estado.
    """

    def test_cancel_active_run_marks_state_cancelled(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        plan = _plan((_node("a"),))
        # `fixture_setup` construye el adapter con su propio root
        # `tmp_path/"fixtures"`; sembramos ahi.
        _seed_fixture(
            tmp_path / "fixtures",
            tenant=TENANT,
            project=PROJECT,
            node_name="a",
            outcome="ok",
        )
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        snap = ctl.cancel_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
        )
        assert snap.state == "CANCELLED"
        # DB consistente
        row = conn.execute(
            "SELECT state FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert row["state"] == "CANCELLED"

    def test_cancel_emits_run_completed_event(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        plan = _plan((_node("a"),))
        _seed_fixture(
            tmp_path / "fixtures",
            tenant=TENANT,
            project=PROJECT,
            node_name="a",
            outcome="ok",
        )
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        ctl.cancel_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
        )
        evs = conn.execute(
            "SELECT event_kind, payload_json FROM runtime_events "
            "WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        # El ultimo evento del run debe ser RunCompleted con state=CANCELLED.
        last = evs[-1]
        assert last["event_kind"] == "RunCompleted"
        payload = json.loads(last["payload_json"])
        assert payload["state"] == "CANCELLED"

    def test_cancel_terminal_run_raises_run_already_terminal(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """Cancelar un run que ya es terminal (COMPLETED/FAILED/CANCELLED)
        es un error operacional: el caller no debe poder 're-cancelar'."""
        from skillgraph.core.errors import ValidationError

        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        _seed_fixture(
            tmp_path / "fixtures",
            tenant=TENANT,
            project=PROJECT,
            node_name="a",
            outcome="ok",
        )
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        # Reconciliar hasta COMPLETED
        ctl.reconcile_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        ctl.reconcile_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        snap = ctl._snapshot(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "COMPLETED"
        with pytest.raises(ValidationError):
            ctl.cancel_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id=run_id,
            )

    def test_cancel_unknown_run_raises_not_found(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        from skillgraph.core.errors import NotFoundError

        storage, adapter, _conn = fixture_setup
        ctl = RunController(storage=storage, adapter=adapter)
        with pytest.raises(NotFoundError):
            ctl.cancel_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id="run-que-no-existe",
            )

    def test_reconcile_after_cancel_is_noop(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = fixture_setup
        plan = _plan((_node("a"),))
        _seed_fixture(
            tmp_path / "fixtures",
            tenant=TENANT,
            project=PROJECT,
            node_name="a",
            outcome="ok",
        )
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        ctl.cancel_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
        )
        # Snapshot estable: reconcile_run no debe re-ejecutar el nodo
        # ni emitir nuevos eventos.
        events_before = conn.execute(
            "SELECT COUNT(*) AS n FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()["n"]
        snap = ctl.reconcile_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        assert snap.state == "CANCELLED"
        events_after = conn.execute(
            "SELECT COUNT(*) AS n FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()["n"]
        assert events_after == events_before


class TestListAndShowRun:
    """Contrato de `RunController.list_runs` y `RunController.show_run`.

    Inspeccion read-only de Runs sin volver a reconciliar. Complementa
    `cancel_run`: el operador primero lista, decide cual cancelar.
    """

    def test_list_runs_empty_returns_empty_tuple(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, _conn = fixture_setup
        ctl = RunController(storage=storage, adapter=adapter)
        result = ctl.list_runs(tenant_id=TENANT, project_id=PROJECT)
        assert result == ()

    def test_list_runs_returns_recent_first(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """El mas reciente aparece primero (orden por rowid DESC)."""
        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter)
        rid1 = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        rid2 = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        rid3 = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        rows = ctl.list_runs(tenant_id=TENANT, project_id=PROJECT)
        ids = tuple(r.run_id for r in rows)
        assert ids == (rid3, rid2, rid1)

    def test_list_runs_respects_limit(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter)
        for _ in range(5):
            ctl.create_run(
                tenant_id=TENANT, project_id=PROJECT, plan=plan
            )
        rows = ctl.list_runs(
            tenant_id=TENANT, project_id=PROJECT, limit=2
        )
        assert len(rows) == 2

    def test_list_runs_filters_by_state(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """`state` opcional filtra runs por estado."""
        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter)
        rid = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        # El run recien creado esta en CREATED.
        rows_created = ctl.list_runs(
            tenant_id=TENANT, project_id=PROJECT, state="CREATED"
        )
        assert rid in tuple(r.run_id for r in rows_created)
        # Filtrar por COMPLETED no debe devolver nada.
        rows_completed = ctl.list_runs(
            tenant_id=TENANT, project_id=PROJECT, state="COMPLETED"
        )
        assert rows_completed == ()

    def test_show_run_returns_snapshot(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter)
        rid = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        snap = ctl.show_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=rid
        )
        assert snap.run_id == rid
        assert snap.state == "CREATED"

    def test_show_run_unknown_raises_not_found(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        from skillgraph.core.errors import NotFoundError

        storage, adapter, _conn = fixture_setup
        ctl = RunController(storage=storage, adapter=adapter)
        with pytest.raises(NotFoundError):
            ctl.show_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id="run-que-no-existe",
            )


class TestLogsRun:
    """Contrato de `RunController.logs_run`.

    Inspeccion read-only del timeline de eventos de un Run.
    Complementa `list_runs`/`show_run`: tras localizar un Run y
    ver su snapshot, el operador ve el detalle de que eventos
    se emitieron (nodo a nodo, en orden).
    """

    def test_logs_run_unknown_raises_not_found(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        from skillgraph.core.errors import NotFoundError

        storage, adapter, _conn = fixture_setup
        ctl = RunController(storage=storage, adapter=adapter)
        with pytest.raises(NotFoundError):
            ctl.logs_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id="run-que-no-existe",
            )

    def test_logs_run_returns_run_created_for_empty_run(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """Run recien creado -> al menos el evento `RunCreated`."""
        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        events = ctl.logs_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        kinds = tuple(e.event.event_kind for e in events)
        # Como minimo: RunCreated.
        assert "RunCreated" in kinds
        # Orden monotono por sequence.
        seqs = tuple(e.sequence for e in events)
        assert seqs == tuple(sorted(seqs))

    def test_logs_run_returns_event_details(
        self,
        fixture_setup: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        """Cada `RuntimeEventLog` expone sequence + RuntimeEvent.

        El RuntimeEvent subyacente tiene event_kind, timestamp,
        payload, correlation_id.
        """
        from skillgraph.runtime.engine import RuntimeEvent
        from skillgraph.runtime.runcontroller import RuntimeEventLog

        storage, adapter, _conn = fixture_setup
        plan = _plan((_node("a"),))
        ctl = RunController(storage=storage, adapter=adapter)
        run_id = ctl.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )
        events = ctl.logs_run(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
        assert len(events) > 0
        ev = events[0]
        assert isinstance(ev, RuntimeEventLog)
        assert isinstance(ev.event, RuntimeEvent)
        assert isinstance(ev.sequence, int)
        assert isinstance(ev.event.event_kind, str)
        assert ev.event.event_kind in {
            "RunCreated",
            "NodeScheduled",
            "NodeStarted",
            "HandoffCreated",
            "NodeCompleted",
            "NodeFailed",
            "EvidenceProduced",
            "RunCompleted",
        }


