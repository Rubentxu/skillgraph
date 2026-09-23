"""Tests focales de la limpieza de S8+S9 en H9-BSlice3: el
``RunController.__init__`` ya no recibe ``conn`` y
``Storage.conn`` es API publica para que ``EventLog`` (que el
RunController construye internamente) obtenga la conexion.

Cubre:
- Storage.conn existe y devuelve la conexion subyacente.
- Storage.conn es la misma identidad que Storage._conn (no un
  wrapper que rompa el sharing entre mutaciones de Storage y
  lectura/escritura de EventLog).
- RunController.__init__ ya no acepta parametro ``conn``
  (TypeError al pasarlo).
- El RunController construido sin conn funciona end-to-end
  (create_run + reconcile_run emiten eventos en runtime_events).
- Red de seguridad (introspeccion): RunController.__init__ no
  contiene "self._conn" como atributo.
"""

from __future__ import annotations

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
) -> tuple[Storage, FakeAgentAdapter]:
    storage_path = tmp_path / "project.sqlite"
    storage = Storage(storage_path)
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    adapter = FakeAgentAdapter(fixtures_root)
    return storage, adapter


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


class TestStorageConnPublic:
    def test_storage_conn_returns_a_sqlite_connection(
        self,
        storage: tuple[Storage, FakeAgentAdapter],
    ) -> None:
        s, _ = storage
        assert isinstance(s.conn, sqlite3.Connection)

    def test_storage_conn_is_same_as_underlying(
        self,
        storage: tuple[Storage, FakeAgentAdapter],
    ) -> None:
        """Storage.conn no es un wrapper: es la misma identidad.

        Importante: si fuera un wrapper, las mutaciones que Storage
        hace sobre ``self._conn`` podrian no verse desde EventLog
        (que toma ``storage.conn`` en el RunController). Aqui
        verificamos que la identidad coincide.
        """
        s, _ = storage
        assert s.conn is s._conn  # type: ignore[attr-defined]


class TestRunControllerNoLongerAcceptsConn:
    def test_init_rejects_conn_keyword(
        self,
        storage: tuple[Storage, FakeAgentAdapter],
    ) -> None:
        """Pasar ``conn=...`` ahora es TypeError."""
        s, adapter = storage
        with pytest.raises(TypeError):
            RunController(storage=s, adapter=adapter, conn=s.conn)  # type: ignore[call-arg]

    def test_init_signature_has_only_storage_and_adapter(self) -> None:
        """Red de seguridad: la firma no incluye ``conn``."""
        import inspect

        sig = inspect.signature(RunController.__init__)
        params = list(sig.parameters.keys())
        assert "conn" not in params, f"RunController.__init__ aun acepta 'conn' (params={params})"
        # Solo storage, adapter (y self).
        assert params[:3] == ["self", "storage", "adapter"]


class TestRunControllerWorksWithoutConn:
    def test_create_run_and_reconcile_via_storage_conn(
        self,
        storage: tuple[Storage, FakeAgentAdapter],
    ) -> None:
        """Camino real: ctl sin conn usa storage.conn para EventLog."""
        s, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)

        run_id = ctl.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan=_plan("a"),
        )

        # El evento RunCreated SI se emite en runtime_events
        # (eso prueba que EventLog tiene la conexion correcta).
        row = s.conn.execute(
            "SELECT COUNT(*) c FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row["c"] == 1

        # Y el run existe en workflow_runs.
        row = s.conn.execute(
            "SELECT state FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row["state"] == "CREATED"


class TestRunControllerNoLongerKeepsConnAttribute:
    """Garantia: RunController ya no tiene ``self._conn``."""

    def test_init_source_does_not_assign_self_conn(self) -> None:
        import inspect

        src = inspect.getsource(RunController.__init__)
        # No debe asignar self._conn = ... ni import sqlite3.
        assert "self._conn" not in src
        assert "import sqlite3" not in src
