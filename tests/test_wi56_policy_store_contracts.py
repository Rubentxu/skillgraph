"""Red de contrato WI-56 corte 2: SqlitePolicyStore real.

Fija el contrato del estrangulamiento definido en ADR-0016 para el
cluster policy/budget (4 metodos: get_policy, upsert_policy,
upsert_budget, get_budget):

1. ``Storage.policy_store()`` devuelve UNA instancia de componente
   real (no ``self``), cacheada: identidad estable entre llamadas.
2. Los 4 metodos producen el mismo efecto observable por el camino
   delegado y por el componente (dos bases identicas, dump semantico
   de tenant_policies y run_budgets sin columnas de reloj).
3. El componente satisface el Protocol ``PolicyStore`` (los 4
   metodos del protocolo) y comparte la conexion de Storage.
4. El schema no cambia: una nueva instancia de ``Storage`` sobre el
   mismo fichero ve lo escrito por el componente.
5. El adapter ``uow.policy`` (get/set_redaction_policy) sigue
   funcionando sobre el facade (los delegados no desaparecen).

Tests contra Storage real (SQLite en tmp_path), sin mocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from skillgraph.platform.ports import PolicyStore
from skillgraph.platform.storage import Storage

TENANT = "t"
PROJECT = "p"
RUN = "run-seed"


def _seed_base(storage: Storage) -> None:
    """Estado inicial identico en ambos ficheros: un budget previo."""
    conn = storage._conn
    conn.execute(
        "INSERT INTO run_budgets (run_id, tenant_id, project_id, "
        "max_visits, max_runtime_seconds, max_events) "
        "VALUES (?, ?, ?, 10, 60, 100)",
        (RUN, TENANT, PROJECT),
    )
    conn.commit()


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Storage, Storage]:
    live = Storage(tmp_path / "live.sqlite")
    delegated = Storage(tmp_path / "delegated.sqlite")
    _seed_base(live)
    _seed_base(delegated)
    return live, delegated


def _cases() -> dict[str, dict[str, Any]]:
    return {
        "get_policy": {"tenant_id": TENANT},
        "upsert_policy": {"tenant_id": TENANT, "policy": "full"},
        "upsert_budget": {
            "tenant_id": TENANT,
            "project_id": PROJECT,
            "run_id": RUN,
            "max_visits": 20,
            "max_runtime_seconds": 120,
            "max_events": 200,
        },
        "get_budget": {"tenant_id": TENANT, "project_id": PROJECT, "run_id": RUN},
    }


def _snapshot(storage: Storage) -> list[tuple[str, tuple[Any, ...]]]:
    conn = storage._conn
    out: list[tuple[str, tuple[Any, ...]]] = []
    for table, cols in (
        ("tenant_policies", "tenant_id, redaction_policy"),
        (
            "run_budgets",
            "run_id, tenant_id, project_id, max_visits, max_runtime_seconds, max_events",
        ),
    ):
        rows = conn.execute(f"SELECT {cols} FROM {table} ORDER BY 1").fetchall()
        out.extend((table, tuple(r)) for r in rows)
    return out


def _invoke(target: Any, method: str, kwargs: dict[str, Any]) -> Any:
    return getattr(target, method)(**dict(kwargs))


class TestFacadeIdentity:
    def test_policy_store_is_cached_component_not_self(self, pair) -> None:
        storage, _other = pair
        store = storage.policy_store()
        assert store is not storage
        assert storage.policy_store() is store

    def test_component_shares_storage_connection(self, pair) -> None:
        storage, _other = pair
        assert storage.policy_store()._conn is storage._conn

    def test_component_satisfies_policy_store_protocol(self, pair) -> None:
        storage, _other = pair
        store = storage.policy_store()
        # PolicyStore no es runtime_checkable (ver nota en ports):
        # comprobacion estructural por nombres de los 4 metodos.
        for name in (
            "get_policy",
            "upsert_policy",
            "upsert_budget",
            "get_budget",
        ):
            assert callable(getattr(store, name, None)), f"{name} missing"
        proto_methods = {n for n in dir(PolicyStore) if not n.startswith("_")}
        for name in proto_methods:
            assert callable(getattr(store, name, None)), f"{name} missing vs Protocol"


class TestClusterEquivalence:
    @pytest.mark.parametrize(
        "method",
        ["get_policy", "upsert_policy", "upsert_budget", "get_budget"],
    )
    def test_component_path_matches_delegated_path(self, pair, method: str) -> None:
        live, delegated = pair
        kwargs = dict(_cases()[method])

        live_ret = _invoke(live.policy_store(), method, kwargs)
        delegated_ret = _invoke(delegated, method, kwargs)

        assert live_ret == delegated_ret
        assert _snapshot(live) == _snapshot(delegated)

        if method == "upsert_policy":
            # Round-trip: la politica escrita por el componente se lee igual.
            assert live.policy_store().get_policy(tenant_id=TENANT) == "full"
        if method == "upsert_budget":
            b = live.policy_store().get_budget(tenant_id=TENANT, project_id=PROJECT, run_id=RUN)
            assert b is not None and b.max_visits == 20
        if method == "get_budget":
            assert live_ret is not None and live_ret.max_visits == 10
        if method == "get_policy":
            assert live_ret is None  # sin semilla de politica

    def test_budget_replace_semantics_match(self, pair) -> None:
        """Segunda escritura REPLACE sobre la misma PK: mismo resultado."""
        live, delegated = pair
        for store in (live.policy_store(), delegated):
            store.upsert_budget(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id=RUN,
                max_visits=1,
                max_runtime_seconds=None,
                max_events=None,
            )
            store.upsert_budget(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id=RUN,
                max_visits=2,
                max_runtime_seconds=5,
                max_events=5,
            )
        assert _snapshot(live) == _snapshot(delegated)
        b = live.policy_store().get_budget(tenant_id=TENANT, project_id=PROJECT, run_id=RUN)
        assert b is not None and b.max_visits == 2

    def test_missing_budget_returns_none_both_paths(self, pair) -> None:
        live, delegated = pair
        assert live.policy_store().get_budget(tenant_id="x", project_id="y", run_id="z") is None
        assert delegated.get_budget(tenant_id="x", project_id="y", run_id="z") is None


class TestSchemaUntouched:
    def test_new_storage_instance_sees_component_writes(self, tmp_path) -> None:
        storage = Storage(tmp_path / "single.sqlite")
        _seed_base(storage)
        storage.policy_store().upsert_policy(tenant_id=TENANT, policy="metadata")
        reopened = Storage(tmp_path / "single.sqlite")
        assert reopened.get_policy(tenant_id=TENANT) == "metadata"
        reopened.close()


class TestAdapterCompatibility:
    def test_uow_policy_adapter_still_round_trips(self, pair) -> None:
        """El adapter uow.policy (get/set_redaction_policy) sigue
        funcionando: sus delegados apuntan al facade, que delega al
        componente."""
        live, _other = pair
        live.uow.policy.set_redaction_policy(TENANT, "full")
        assert live.uow.policy.get_redaction_policy(TENANT) == "full"
        assert live.uow.policy.get_redaction_policy("no-existe") is None
