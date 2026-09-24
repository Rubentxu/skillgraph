"""Tests focales de `Storage.create_run`, la API añadida en
H9-BSlice3-S1 para sustituir el INSERT directo del
``RunController.create_run``.

Cubre:
- Contrato observable: run_id unico, state=CREATED, plan_json
  serializado, current_node=initial.
- run_id generado por Storage (no por el caller).
- No emite eventos.
- plan_json se persiste tal cual (no se re-serializa ni se
  reordena).
- Red de seguridad: el INSERT directo de workflow_runs esta
  fuera de create_run del RunController.
"""

from __future__ import annotations

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


class TestCreateRun:
    def test_persists_created_state_with_plan(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, conn, _adapter = storage

        run_id = s.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan_json='{"plan":1}',
            initial_node="a",
        )

        row = conn.execute(
            "SELECT run_id, tenant_id, project_id, state, plan_json, "
            "current_node FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row["state"] == "CREATED"
        assert row["tenant_id"] == TENANT
        assert row["project_id"] == PROJECT
        assert row["plan_json"] == '{"plan":1}'
        assert row["current_node"] == "a"

    def test_returns_unique_run_ids(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, _adapter = storage

        ids = {
            s.create_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                plan_json="{}",
                initial_node="a",
            )
            for _ in range(10)
        }
        assert len(ids) == 10

    def test_run_id_format(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, _adapter = storage
        run_id = s.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan_json="{}",
            initial_node="a",
        )
        # El formato exacto vive en runtime.runcontroller.new_run_id.
        # Aqui solo verificamos que el prefijo es estable.
        assert run_id.startswith("run-")

    def test_does_not_emit_events(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Storage NO emite eventos: el RunController orquesta."""
        s, conn, _adapter = storage

        before = conn.execute("SELECT COUNT(*) c FROM runtime_events").fetchone()["c"]

        run_id = s.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan_json="{}",
            initial_node="a",
        )

        after = conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
        assert after == 0
        assert before == conn.execute("SELECT COUNT(*) c FROM runtime_events").fetchone()["c"]

    def test_plan_json_passed_through_verbatim(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Storage NO serializa: el caller pasa la string ya hecha.

        Esto blinda contra una regresion donde Storage intente
        re-serializar (perdiendo el sort_keys=True del caller).
        """
        s, conn, _adapter = storage

        # String arbitraria: no JSON valido a proposito.
        weird = "not-actually-json-but-the-caller-said-so"

        run_id = s.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan_json=weird,
            initial_node="a",
        )

        row = conn.execute(
            "SELECT plan_json FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row["plan_json"] == weird

    def test_works_through_runcontroller(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Camino real: RunController.create_run -> Storage.create_run."""
        s, conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)

        run_id = ctl.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan=_plan("a", "b"),
        )

        row = conn.execute(
            "SELECT state, current_node FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row["state"] == "CREATED"
        assert row["current_node"] == "a"
        # Y el evento RunCreated SI se emite (es del RunController).
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            == 1
        )


class TestRunControllerCreateRunNoLongerUpdateDirect:
    """Garantia: el INSERT directo de workflow_runs esta fuera de
    ``RunController.create_run``.
    """

    def test_create_run_source_has_no_insert_workflow_runs(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl.create_run)
        assert not re.search(r"\bINSERT\s+INTO\s+workflow_runs\b", src, re.IGNORECASE), (
            "INSERT INTO workflow_runs presente en create_run: "
            "deberia delegarse en Storage.create_run"
        )
