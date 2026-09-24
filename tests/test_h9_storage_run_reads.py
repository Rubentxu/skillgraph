"""Tests focales de las nuevas APIs de lectura de `Storage` añadidas
en H9-BSlice3-S1.

Sustituyen a las lecturas SQL directas del `RunController` y exponen
el contrato observable de cada método:
- `Storage.load_run(*, tenant_id, project_id, run_id) -> dict`
- `Storage.list_node_executions(*, tenant_id, project_id, run_id, node_name) -> list`
- `Storage.list_executed_node_names(*, tenant_id, project_id, run_id) -> tuple`

No ejercitan combinaciones transaccionales ni performance: eso
pertenece al refactor posterior (S3..S7) cuando esas lecturas se
acompañen con escrituras atómicas.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from skillgraph.core.errors import NotFoundError
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"


@pytest.fixture
def storage(tmp_path: Path) -> tuple[Storage, sqlite3.Connection, FakeAgentAdapter]:
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


def _seed_fixture(
    fixtures_root: Path,
    *,
    node_name: str,
    outcome: str,
) -> None:
    p = fixtures_root / TENANT / PROJECT / f"{node_name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"outcome":"' + outcome + '","result":{"x":1}}', encoding="utf-8")


# ---------- load_run ----------


class TestLoadRun:
    def test_returns_full_row_as_dict(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a"))
        row = s.load_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert isinstance(row, dict)
        assert row["run_id"] == run_id
        assert row["state"] == "CREATED"
        assert row["current_node"] == "a"
        # plan_json se expone como string JSON, no como objeto.
        assert isinstance(row["plan_json"], str)
        # Debe parsear como JSON valido.
        assert "initial" in json.loads(row["plan_json"])

    def test_raises_not_found_for_inexistent_run(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, _adapter = storage
        with pytest.raises(NotFoundError) as exc_info:
            s.load_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id="nope-run-id",
            )
        assert "nope-run-id" in str(exc_info.value)

    def test_filters_by_tenant_and_project(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Un run en (t,p) NO se devuelve al consultar (other_t, p)."""
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a"))
        with pytest.raises(NotFoundError):
            s.load_run(
                tenant_id="other-tenant",
                project_id=PROJECT,
                run_id=run_id,
            )


# ---------- list_node_executions ----------


class TestListNodeExecutions:
    def test_returns_empty_when_none(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, _adapter = storage
        result = s.list_node_executions(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="empty-run",
            node_name="none",
        )
        assert result == []

    def test_orders_by_started_at_ascending(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("ordered"))
        # Renombrar para determinismo.
        _conn.execute(
            "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
            ("run-ord", run_id),
        )
        _conn.commit()
        for ne_id, started in [
            ("ne-c", "2026-09-23 10:00:00"),
            ("ne-a", "2026-09-23 08:00:00"),
            ("ne-b", "2026-09-23 09:00:00"),
        ]:
            _conn.execute(
                "INSERT INTO node_executions (node_execution_id, run_id, "
                "tenant_id, project_id, node_name, attempt, state, "
                "started_at) VALUES (?, ?, ?, ?, ?, 1, 'SUCCEEDED', ?)",
                (ne_id, "run-ord", TENANT, PROJECT, "ordered", started),
            )
        _conn.commit()

        rows = s.list_node_executions(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-ord",
            node_name="ordered",
        )
        ids = [r["node_execution_id"] for r in rows]
        assert ids == ["ne-a", "ne-b", "ne-c"]

    def test_isolates_by_node_name(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a", "b"))
        _conn.execute(
            "INSERT INTO node_executions (node_execution_id, run_id, "
            "tenant_id, project_id, node_name, attempt, state, "
            "started_at) VALUES (?, ?, ?, ?, ?, 1, 'SUCCEEDED', "
            "datetime('now'))",
            ("ne-a-1", run_id, TENANT, PROJECT, "a"),
        )
        _conn.execute(
            "INSERT INTO node_executions (node_execution_id, run_id, "
            "tenant_id, project_id, node_name, attempt, state, "
            "started_at) VALUES (?, ?, ?, ?, ?, 1, 'SUCCEEDED', "
            "datetime('now'))",
            ("ne-b-1", run_id, TENANT, PROJECT, "b"),
        )
        _conn.commit()

        rows_a = s.list_node_executions(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            node_name="a",
        )
        rows_b = s.list_node_executions(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            node_name="b",
        )
        assert [r["node_execution_id"] for r in rows_a] == ["ne-a-1"]
        assert [r["node_execution_id"] for r in rows_b] == ["ne-b-1"]


# ---------- list_executed_node_names ----------


class TestListExecutedNodeNames:
    def test_returns_distinct_sorted_succeeded_only(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("z_node"))
        _conn.execute(
            "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
            ("run-dn", run_id),
        )
        _conn.commit()

        for ne_id, name, state in [
            ("ne-1", "z_node", "SUCCEEDED"),
            ("ne-2", "a_node", "SUCCEEDED"),
            ("ne-3", "m_node", "RUNNING"),
            ("ne-4", "z_node", "SUCCEEDED"),  # duplicado
            ("ne-5", "z_node", "FAILED"),
        ]:
            _conn.execute(
                "INSERT INTO node_executions (node_execution_id, run_id, "
                "tenant_id, project_id, node_name, attempt, state, "
                "started_at) VALUES (?, ?, ?, ?, ?, 1, ?, "
                "datetime('now'))",
                (ne_id, "run-dn", TENANT, PROJECT, name, state),
            )
        _conn.commit()

        names = s.list_executed_node_names(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-dn",
        )
        # Solo SUCCEEDED, DISTINCT, ordenado alfabetico.
        assert names == ("a_node", "z_node")

    def test_returns_empty_tuple_for_empty_run(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        s, _conn, _adapter = storage
        names = s.list_executed_node_names(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="no-such-run",
        )
        assert names == ()

    def test_returns_tuple_not_list(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        """Inmutable: el contrato es tuple, no list."""
        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("only"))
        # Con un SUCCEEDED insertado directo:
        _conn.execute(
            "INSERT INTO node_executions (node_execution_id, run_id, "
            "tenant_id, project_id, node_name, attempt, state, "
            "started_at) VALUES (?, ?, ?, ?, ?, 1, 'SUCCEEDED', "
            "datetime('now'))",
            ("ne-1", run_id, TENANT, PROJECT, "only"),
        )
        _conn.commit()

        names = s.list_executed_node_names(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
        )
        assert isinstance(names, tuple)


# ---------- invitaciones de no-regresion para H9-BSlice3-S1 ----------


class TestRunControllerNoLongerSqlReads:
    """Garantia: tras S1, las 3 lecturas del RunController NO son SQL.

    Se verifica por introspeccion: el cuerpo de los metodos privados
    ya no contiene `SELECT`. Esto blinda una regresion tipica:
    alguien 'deshace' la delegacion y vuelve a SQL directo. Si pasa,
    el RunController sigue dependiendo de `sqlite3.Connection` para
    esas lecturas.
    """

    def test_load_run_has_no_select(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._load_run)
        assert "SELECT" not in src
        assert "_conn" not in src

    def test_node_executions_for_has_no_select(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._node_executions_for)
        assert "SELECT" not in src
        assert "_conn" not in src

    def test_executed_node_names_has_no_select(
        self,
        storage: tuple[Storage, sqlite3.Connection, FakeAgentAdapter],
    ) -> None:
        import inspect

        s, _conn, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        src = inspect.getsource(ctl._executed_node_names)
        assert "SELECT" not in src
        assert "_conn" not in src
