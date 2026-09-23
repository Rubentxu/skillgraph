"""H9-BSlice2: API publica Storage.find_active_run(tenant_id, project_id).

Cierra la limitacion 'storage._conn en runner' para el helper _find_active_run_id.
Antes era SQL directo; ahora delega en un metodo Storage.

Convenciones: patron del slice 1 (test_h9_storage_promo_list.py) y slice 2
(test_h9_cli_*). Sin mocks, storage real en :memory: o tmp_path.
"""

from __future__ import annotations

import pytest

from skillgraph.platform.storage import NON_TERMINAL_RUN_STATES, Storage


@pytest.fixture
def storage(tmp_path):
    db = Storage(tmp_path / "test.db")
    yield db
    db.close()


def _insert_run(
    storage: Storage,
    *,
    run_id: str,
    state: str,
    tenant_id: str = "t1",
    project_id: str = "p1",
) -> None:
    """Inserta un workflow_run con el estado pedido.

    Implementacion minima via API publica (Storage no expone aun
    'create_run' como API de alto nivel; usamos _conn directo solo aqui
    en TEST code, no en codigo de produccion).
    """
    storage._conn.execute(  # type: ignore[attr-defined]
        "INSERT INTO workflow_runs "
        "(run_id, tenant_id, project_id, state, plan_json) "
        "VALUES (?, ?, ?, ?, '{}')",
        (run_id, tenant_id, project_id, state),
    )
    storage._conn.commit()  # type: ignore[attr-defined]


class TestFindActiveRunEmpty:
    def test_empty_runs_returns_none(self, storage: Storage) -> None:
        """Sin runs en el proyecto -> None."""
        assert storage.find_active_run(tenant_id="t1", project_id="p1") is None


class TestFindActiveRunSingleState:
    @pytest.mark.parametrize("state", ["CREATED", "ACTIVE", "WAITING"])
    def test_each_non_terminal_state_is_picked_up(self, storage: Storage, state: str) -> None:
        """Cualquier estado en NON_TERMINAL_RUN_STATES es candidato."""
        assert state in NON_TERMINAL_RUN_STATES
        _insert_run(storage, run_id=f"r-{state}", state=state)
        assert storage.find_active_run(tenant_id="t1", project_id="p1") == f"r-{state}"

    @pytest.mark.parametrize("state", ["COMPLETED", "FAILED", "CANCELLED"])
    def test_terminal_states_are_ignored(self, storage: Storage, state: str) -> None:
        """Estados terminales NO se consideran 'active'."""
        assert state not in NON_TERMINAL_RUN_STATES
        _insert_run(storage, run_id=f"r-term-{state}", state=state)
        assert storage.find_active_run(tenant_id="t1", project_id="p1") is None


class TestFindActiveRunOrdering:
    def test_returns_most_recent_first(self, storage: Storage) -> None:
        """Cuando hay multiples runs no terminales, devuelve el mas reciente."""
        _insert_run(storage, run_id="r-old", state="CREATED")
        # Forzar diferencia de created_at (1s de granularity en SQLite default).
        import time

        time.sleep(1.05)
        _insert_run(storage, run_id="r-new", state="ACTIVE")
        assert storage.find_active_run(tenant_id="t1", project_id="p1") == "r-new"


class TestFindActiveRunIsolation:
    def test_different_project_returns_none(self, storage: Storage) -> None:
        """Filtrado por (tenant, project): el run activo esta en OTRO proyecto."""
        _insert_run(storage, run_id="r-other", state="ACTIVE", project_id="p2")
        assert storage.find_active_run(tenant_id="t1", project_id="p1") is None
        # Y para el proyecto correcto, lo encuentra.
        assert storage.find_active_run(tenant_id="t1", project_id="p2") == "r-other"

    def test_different_tenant_returns_none(self, storage: Storage) -> None:
        """Filtrado por tenant: el run activo esta en OTRO tenant."""
        _insert_run(storage, run_id="r-other", state="ACTIVE", tenant_id="t2")
        assert storage.find_active_run(tenant_id="t1", project_id="p1") is None
        assert storage.find_active_run(tenant_id="t2", project_id="p1") == "r-other"


class TestRunnerNoStoragePrivateAccess:
    """Invariante H9: el runner NO accede a atributos privados del Storage.

    Tras H9-BSlice2, los helpers _find_active_run_id, _source_to_payload y
    _entity_to_payload delegan en metodos publicos de Storage. Este test
    protege esa arquitectura de regresiones silenciosas.
    """

    @pytest.mark.parametrize(
        "helper_name",
        ["_find_active_run_id", "_source_to_payload", "_entity_to_payload"],
    )
    def test_helper_no_longer_touches_storage_private(self, helper_name: str) -> None:
        import inspect

        from skillgraph.cli import runner

        fn = getattr(runner, helper_name)
        src = inspect.getsource(fn)
        assert "storage._conn" not in src, (
            f"{helper_name} no debe acceder a storage._conn; "
            "delega en un metodo publico de Storage."
        )
