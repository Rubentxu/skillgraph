"""H10 / v0.7.2 — Tests de integracion del RunController con APIs atomicas.

Cierra el hallazgo de revision externa del release v0.7.1:
RunController debe INVOCAR las APIs *atomically de Storage en su
recorrido real, no solo en tests focales.

Estrategia: tests de integracion con fault injection. Se induce un
fallo en el INSERT de runtime_events y se verifica que el estado de
node_executions tambien rollbackee (transaccion compartida via la
API *atomically de Storage).

Estos tests RED -> GREEN documentan la propiedad bajo el camino
publico del runtime, complementando T7-T11 (que solo cubren Storage
aislado).

Refs:
- audits/review-finding-v0.7.1-integration-gap.md
- audits/h9-plan-b-atomicity-closure-b38c105.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"


# ---------- Helpers de fixture + plan ----------


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
        capabilities=(),
        metadata={},
    )


def _plan_single(node_name: str) -> WorkflowPlan:
    return WorkflowPlan(nodes=(_node(node_name),), transitions=(), initial=node_name)


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
        json.dumps(
            {
                "outcome": outcome,
                "result": payload or {"answer": "ok"},
                "evidence_ref": f"ev-{node_name}",
            }
        )
    )


# ---------- Helpers para inspeccionar BD ----------


def _node_exec_rows(storage: Storage, run_id: str, name: str) -> list[sqlite3.Row]:
    return list(
        storage._conn.execute(
            "SELECT node_execution_id, state, outcome FROM node_executions "
            "WHERE run_id = ? AND node_name = ?",
            (run_id, name),
        )
    )


def _event_count(storage: Storage, run_id: str, kind: str) -> int:
    row = storage._conn.execute(
        "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ? AND event_kind = ?",
        (run_id, kind),
    ).fetchone()
    return row["c"]


# ---------- Fixtures ----------


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "project.sqlite")


@pytest.fixture
def fixtures_root(tmp_path: Path) -> Path:
    p = tmp_path / "fixtures"
    p.mkdir()
    return p


@pytest.fixture
def adapter(fixtures_root: Path) -> FakeAgentAdapter:
    return FakeAgentAdapter(fixtures_root)


# ---------- Tests T12: integracion start atomic ----------


class TestT12RunControllerUsesStartAtomic:
    """El par `start_node_execution + NodeStarted` de RunController se
    ejecuta en una sola transaccion: si falla el evento, el INSERT del
    estado tambien rollbackea.
    """

    def test_runtime_start_is_atomic_when_event_fails(
        self,
        storage: Storage,
        adapter: FakeAgentAdapter,
        fixtures_root: Path,
        monkeypatch,
    ) -> None:
        # Plan y Run simples
        controller = RunController(storage=storage, adapter=adapter)
        plan = _plan_single("n")
        run_id = controller.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        # Fixture del adapter con outcome "ok"
        _seed_fixture(
            fixtures_root,
            tenant=TENANT,
            project=PROJECT,
            node_name="n",
            outcome="ok",
        )

        # Forzar fallo en el INSERT de NodeStarted dentro de la API
        # atomica start_node_execution_atomically.
        original_helper = storage._insert_event_in_tx

        def faulty_insert(cur, event):
            if event.event_kind == "NodeStarted":
                raise RuntimeError("fault injection: NodeStarted insert fail")
            return original_helper(cur, event)

        monkeypatch.setattr(storage, "_insert_event_in_tx", faulty_insert)

        # La excepcion del INSERT se propaga (correcto: la transaccion
        # falla -> el caller debe enterarse).
        with pytest.raises(RuntimeError, match="fault injection"):
            controller.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)

        # POST: NO debe haber node_execution persistido (rollback).
        rows = _node_exec_rows(storage, run_id, "n")
        assert rows == [], f"expected rollback, got {rows}"

        # POST: NodeStarted NO debe estar persistido.
        assert _event_count(storage, run_id, "NodeStarted") == 0


# ---------- Tests T13: integracion complete atomic ----------


class TestT13RunControllerUsesCompleteAtomic:
    """El triple `complete_node_execution + NodeCompleted + EvidenceProduced`
    de RunController se ejecuta en una sola transaccion. Si el INSERT
    del evento falla, el UPDATE a SUCCEEDED rollbackea.
    """

    def test_runtime_complete_is_atomic_when_evidence_fails(
        self,
        storage: Storage,
        adapter: FakeAgentAdapter,
        fixtures_root: Path,
        monkeypatch,
    ) -> None:
        controller = RunController(storage=storage, adapter=adapter)
        plan = _plan_single("c")
        run_id = controller.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        _seed_fixture(
            fixtures_root,
            tenant=TENANT,
            project=PROJECT,
            node_name="c",
            outcome="ok",
        )

        # Forzar fallo en el EvidenceProduced (segundo evento de complete)
        original_helper = storage._insert_event_in_tx

        def faulty_insert(cur, event):
            if event.event_kind == "EvidenceProduced":
                raise RuntimeError("fault injection: EvidenceProduced fail")
            return original_helper(cur, event)

        monkeypatch.setattr(storage, "_insert_event_in_tx", faulty_insert)

        with pytest.raises(RuntimeError, match="fault injection"):
            controller.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)

        # POST: el node_execution debe seguir RUNNING (rollback del UPDATE).
        rows = _node_exec_rows(storage, run_id, "c")
        assert len(rows) == 1, rows
        assert rows[0]["state"] == "RUNNING", (
            f"complete_node_execution_atomically debe rollbackear; "
            f"esperaba RUNNING, obtuve {rows[0]['state']!r}"
        )
        # NodeCompleted NO debe estar persistido.
        assert _event_count(storage, run_id, "NodeCompleted") == 0


# ---------- Tests T14: integracion fail atomic ----------


class TestT14RunControllerUsesFailAtomic:
    """El par `mark_node_failed + NodeFailed` se ejecuta en una sola
    transaccion via mark_node_failed_atomically.
    """

    def test_runtime_fail_is_atomic_when_event_fails(
        self,
        storage: Storage,
        adapter: FakeAgentAdapter,
        fixtures_root: Path,
        monkeypatch,
    ) -> None:
        # Adapter que SIEMPRE lanza excepcion (fuerza la rama de fail).
        class FailingAdapter:
            def invoke(self, handoff):
                raise ValueError("boom")

        controller = RunController(
            storage=storage,
            adapter=FailingAdapter(),  # type: ignore[arg-type]
        )
        plan = _plan_single("f")
        run_id = controller.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)

        # Forzar fallo en el INSERT del NodeFailed dentro de la API
        # atomica mark_node_failed_atomically.
        original_helper = storage._insert_event_in_tx

        def faulty_insert(cur, event):
            if event.event_kind == "NodeFailed":
                raise RuntimeError("fault injection: NodeFailed insert fail")
            return original_helper(cur, event)

        monkeypatch.setattr(storage, "_insert_event_in_tx", faulty_insert)

        # La excepcion del INSERT se propaga.
        with pytest.raises(RuntimeError, match="fault injection"):
            controller.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)

        # POST: el node_execution debe seguir RUNNING (rollback del UPDATE FAILED).
        rows = _node_exec_rows(storage, run_id, "f")
        assert len(rows) == 1, rows
        assert rows[0]["state"] == "RUNNING", (
            f"mark_node_failed_atomically debe rollbackear; "
            f"esperaba RUNNING, obtuve {rows[0]['state']!r}"
        )
        # NodeFailed NO debe estar persistido.
        assert _event_count(storage, run_id, "NodeFailed") == 0
