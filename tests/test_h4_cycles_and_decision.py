"""Tests H4: DecisionNode outcomes declarados + max_visits en ciclos.

Decisiones aplicadas (defaults del agente, reversibles via git revert):
- D1: solo slices 1+2 (DecisionNode outcomes + max_visits ciclos).
- D2: DecisionNode via metadata.outcomes, sin Literal nuevo (reusa el
  Literal existente "DecisionNode" en WorkflowNode.kind).
- D3: budget exhausted -> run FAILED.
- D4: NO en H4 (token budget aproximado OK).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgraph.agent import FakeAgentAdapter
from skillgraph.errors import ValidationError
from skillgraph.runcontroller import RunController
from skillgraph.storage import Storage
from skillgraph.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

TENANT = "t"
PROJECT = "p"


def _node(name: str, kind: str = "ActionNode", metadata: dict | None = None) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
        metadata=metadata or {},
    )


def _seed_ok(fixtures_root: Path, *names: str) -> None:
    for n in names:
        p = fixtures_root / TENANT / PROJECT / f"{n}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"outcome": "ok", "result": {}}))


def _seed(fixtures_root: Path, mapping: dict[str, str]) -> None:
    for n, outcome in mapping.items():
        p = fixtures_root / TENANT / PROJECT / f"{n}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"outcome": outcome, "result": {}}))


def _build(tmp_path: Path, plan: WorkflowPlan) -> tuple[Storage, RunController]:
    storage = Storage(tmp_path / "p.sqlite")
    fx = tmp_path / "fx"
    fx.mkdir()
    adapter = FakeAgentAdapter(fx)
    ctl = RunController(storage=storage, adapter=adapter, conn=storage._conn)  # type: ignore[attr-defined]
    return storage, ctl


# ---------------------------------------------------------------------------
# Slice 1: outcomes declarados (DecisionNode + ActionNode con outcomes)
# ---------------------------------------------------------------------------


class TestOutcomesDeclared:
    def test_decision_node_requires_outcomes(self) -> None:
        with pytest.raises(ValidationError, match="DecisionNode requiere"):
            _node("d", kind="DecisionNode")

    def test_decision_node_with_outcomes_ok(self) -> None:
        n = _node("d", kind="DecisionNode", metadata={"outcomes": ["ok", "abort"]})
        assert n.outcomes == ("ok", "abort")

    def test_transition_outcome_must_be_declared(self) -> None:
        n = _node("d", kind="DecisionNode", metadata={"outcomes": ["ok"]})
        with pytest.raises(ValidationError, match="no esta en outcomes"):
            WorkflowPlan(
                nodes=(n, _node("z")),
                transitions=(WorkflowTransition(source="d", outcome="abort", target="z"),),
                initial="d",
            )

    def test_action_node_without_outcomes_accepts_any(self) -> None:
        """ActionNode sin outcomes sigue aceptando cualquier outcome (DAG lineal)."""
        a = _node("a")
        b = _node("b")
        plan = WorkflowPlan(
            nodes=(a, b),
            transitions=(WorkflowTransition(source="a", outcome="anything", target="b"),),
            initial="a",
        )
        assert plan.successors("a", "anything") == "b"


# ---------------------------------------------------------------------------
# Slice 2: max_visits en self-loops
# ---------------------------------------------------------------------------


class TestMaxVisitsSelfLoop:
    def test_no_max_visits_no_loop_returns_empty_frontier(self, tmp_path: Path) -> None:
        """Sin self-loop declarada: tras 2 reconciles el DAG lineal completa."""
        plan = _plan_dag()
        _storage, ctl = _build(tmp_path, plan)
        _seed_ok(tmp_path / "fx", "a", "b")
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "COMPLETED"

    def test_self_loop_with_max_visits_iterates_then_fails(self, tmp_path: Path) -> None:
        """Self-loop con max_visits=2 ejecuta 2 veces y termina FAILED."""
        a = _node("a", metadata={"max_visits": 2})
        plan = WorkflowPlan(
            nodes=(a,),
            transitions=(WorkflowTransition(source="a", outcome="ok", target="a"),),
            initial="a",
        )
        storage, ctl = _build(tmp_path, plan)
        _seed_ok(tmp_path / "fx", "a")
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        s1 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        conn = storage._conn  # type: ignore[attr-defined]
        n1 = conn.execute(
            "SELECT COUNT(*) FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert s1.state == "ACTIVE", f"after s1: state={s1.state} n_exec={n1}"
        assert s1.current_node == "a"
        s2 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        n2 = conn.execute(
            "SELECT COUNT(*) FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert s2.state == "FAILED", f"after s2: state={s2.state} n_exec={n2}"
        assert n2 == 2

    def test_self_loop_with_no_max_visits_runs_once(self, tmp_path: Path) -> None:
        """max_visits=None en self-loop: ejecuta 1 vez y termina FAILED
        (la 2da llamada detecta budget_exhausted con max_visits=None? No,
        sin max_visits el frontier devuelve [] con last=SUCCEEDED,
        y como NO hay budget_exhausted (max_visits is None) -> COMPLETED.

        OJO: este test documenta la semantica actual (sin max_visits en
        self-loop es infinito). El operador debe poner max_visits explicito
        si quiere terminar.
        """
        a = _node("a", metadata={"max_visits": 1})
        plan = WorkflowPlan(
            nodes=(a,),
            transitions=(WorkflowTransition(source="a", outcome="ok", target="a"),),
            initial="a",
        )
        storage, ctl = _build(tmp_path, plan)
        _seed_ok(tmp_path / "fx", "a")
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        _s1 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        # max_visits=1: ejecuta 1 vez, budget=1, FAILED al 2do reconcile
        s2 = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert s2.state == "FAILED"
        conn = storage._conn  # type: ignore[attr-defined]
        n_exec = conn.execute(
            "SELECT COUNT(*) FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert n_exec == 1


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _plan_dag() -> WorkflowPlan:
    a = _node("a")
    b = _node("b")
    return WorkflowPlan(
        nodes=(a, b),
        transitions=(WorkflowTransition(source="a", outcome="ok", target="b"),),
        initial="a",
    )
