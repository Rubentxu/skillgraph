"""Red de contrato WI-56 corte 1: SqliteRunRepository real.

Fija el contrato del estrangulamiento definido en ADR-0016
(docs/blueprint/adr/ADR-0016-storage-decomposition.md):

1. ``Storage.run_repository()`` devuelve UNA instancia de componente
   (no ``self``), cacheada: identidad estable entre llamadas.
2. Los 19 metodos del cluster runs producen el mismo efecto observable
   por el camino delegado (``storage.<metodo>``) y por el componente
   (``storage.run_repository().<metodo>``): la equivalencia se mide
   sobre DOS bases identicas (una por camino) comparando el dump
   semantico de workflow_runs / node_executions / runtime_events,
   excluyendo columnas de reloj. Comparar dos llamadas sobre la MISMA
   base seria un falso negativo para mutaciones (PK conflicts,
   contadores de segunda pasada).
3. La transaccion es compartida: inyectar un fallo en
   ``storage._insert_event_in_tx`` (superficie que parchean los tests
   H9/H10 existentes) rompe TAMBIEN las llamadas por el componente,
   y la idempotencia por ``UNIQUE(event_id)`` se respeta en ambos.
4. El schema no cambia: una nueva instancia de ``Storage`` sobre el
   mismo fichero ve las escrituras hechas por el componente.

Tests contra Storage real (SQLite en tmp_path), sin mocks del object
store, igual que la suite de plataforma existente.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from skillgraph.core.errors import IdempotencyError
from skillgraph.platform.ports import RunRepository
from skillgraph.platform.storage import Storage
from skillgraph.runtime.engine import RuntimeEvent

TENANT = "t"
PROJECT = "p"
RUN = "run-seed"

_SEED_RUN_SQL = (
    "INSERT INTO workflow_runs (run_id, tenant_id, project_id, "
    "plan_json, state, current_node) VALUES (?, ?, ?, '{}', 'ACTIVE', 'n')"
)
_SEED_NODE_SQL = (
    "INSERT INTO node_executions (node_execution_id, run_id, tenant_id, "
    "project_id, node_name, attempt, state, context_hash, handoff_json, "
    "started_at) VALUES (?, ?, ?, ?, ?, 1, ?, 'h', '{}', datetime('now'))"
)


def _seed_base(storage: Storage) -> None:
    """Puebla la base con estado FK-safe identico en ambos ficheros."""
    conn = storage._conn
    conn.execute(_SEED_RUN_SQL, (RUN, TENANT, PROJECT))
    conn.execute(_SEED_NODE_SQL, (f"{RUN}-ok", RUN, TENANT, PROJECT, "n", "SUCCEEDED"))
    conn.execute(_SEED_NODE_SQL, (f"{RUN}-run", RUN, TENANT, PROJECT, "n", "RUNNING"))
    conn.execute(_SEED_NODE_SQL, (f"{RUN}-hand", RUN, TENANT, PROJECT, "n", "RUNNING"))
    conn.execute(_SEED_NODE_SQL, (f"{RUN}-done", RUN, TENANT, PROJECT, "n", "RUNNING"))
    conn.execute(_SEED_NODE_SQL, (f"{RUN}-fail", RUN, TENANT, PROJECT, "n", "RUNNING"))
    conn.execute(_SEED_NODE_SQL, (f"{RUN}-atb", RUN, TENANT, PROJECT, "na", "RUNNING"))
    conn.commit()


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Storage, Storage]:
    """Dos Storage reales sobre ficheros distintos con la MISMA semilla.

    El camino 'live' corre sobre el primero (via componente) y el
    'delegated' sobre el segundo (via delegados de Storage).
    """
    live = Storage(tmp_path / "live.sqlite")
    delegated = Storage(tmp_path / "delegated.sqlite")
    _seed_base(live)
    _seed_base(delegated)
    return live, delegated


def _event(event_id: str, kind: str, run_id: str = RUN) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=event_id,
        tenant_id=TENANT,
        project_id=PROJECT,
        event_kind=kind,
        run_id=run_id,
        resource_ref=f"ne-{event_id}",
        causation_id=None,
        correlation_id=run_id,
        payload={"k": event_id},
    )


def _snapshot(storage: Storage) -> list[tuple[str, tuple[Any, ...]]]:
    """Dump semantico determinista (sin columnas de reloj).

    Los run_id generados (UUID) se normalizan: run-<hex> -> run-ID.
    """
    conn = storage._conn
    out: list[tuple[str, tuple[Any, ...]]] = []
    for table, cols in (
        ("workflow_runs", "run_id, tenant_id, project_id, state, current_node, plan_json"),
        (
            "node_executions",
            "node_execution_id, run_id, tenant_id, project_id, node_name, "
            "attempt, state, outcome, error, result_json, context_hash, handoff_json",
        ),
        (
            "runtime_events",
            "event_id, tenant_id, project_id, event_kind, run_id, resource_ref, "
            "causation_id, correlation_id, payload_json, schema_version",
        ),
    ):
        rows = conn.execute(f"SELECT {cols} FROM {table} ORDER BY 1").fetchall()
        for r in rows:
            vals = tuple(
                "run-ID" if isinstance(v, str) and re.fullmatch(r"run-[0-9a-f-]{36}", v) else v
                for v in tuple(r)
            )
            out.append((table, vals))
    return out


def _cases() -> dict[str, dict[str, Any]]:
    """Argumentos por metodo (ids fijos, reproducibles en ambas bases)."""
    return {
        "find_active_run": {},
        "list_runs": {},
        "get_run": {},
        "list_events_for_run": {},
        "load_run": {},
        "list_node_executions": {"node_name": "n"},
        "list_executed_node_names": {},
        "recover_interrupted_node_executions": {},
        "transition_run_state": {"state": "ACTIVE", "current_node": "n2"},
        "start_node_execution": {
            "node_execution_id": f"{RUN}-new",
            "node_name": "nx",
            "attempt": 2,
            "context_hash": "h2",
            "handoff_json": '{"x": 1}',
        },
        "complete_node_execution": {
            "node_execution_id": f"{RUN}-run",
            "outcome": "ok",
            "result_json": '{"r": 1}',
        },
        "mark_node_failed": {"node_execution_id": f"{RUN}-fail", "error": "boom"},
        "update_node_execution_handoff": {
            "node_execution_id": f"{RUN}-hand",
            "context_hash": "h9",
            "handoff_json": '{"h": 9}',
        },
        "start_node_execution_atomically": {
            "event": _event("evt-ata", "NodeStarted"),
            "node_execution_id": f"{RUN}-ata",
            "node_name": "na",
            "attempt": 1,
            "context_hash": "h",
            "handoff_json": "{}",
        },
        "complete_node_execution_atomically": {
            "event_completed": _event("evt-atb1", "NodeCompleted"),
            "event_evidence": _event("evt-atb2", "EvidenceProduced"),
            "node_execution_id": f"{RUN}-atb",
            "outcome": "ok",
            "result_json": "{}",
        },
        "mark_node_failed_atomically": {
            "event": _event("evt-atc", "NodeFailed"),
            "node_execution_id": f"{RUN}-atb",
            "error": "boom",
        },
        "create_run": {"plan_json": "{}", "initial_node": "z"},
        "create_run_atomically": {
            "event": _event("evt-cr", "RunCreated", run_id="run-cr"),
            "run_id": "run-cr",
            "plan_json": "{}",
            "initial_node": "z",
        },
        "transition_run_state_atomically": {
            "event": _event("evt-tr", "RunCompleted"),
            "state": "COMPLETED",
            "current_node": None,
        },
    }


def _invoke(target: Any, method: str, kwargs: dict[str, Any]) -> Any:
    call = dict(kwargs)
    node_scoped = method in {
        "complete_node_execution",
        "mark_node_failed",
        "update_node_execution_handoff",
        "complete_node_execution_atomically",
        "mark_node_failed_atomically",
    }
    call.setdefault("tenant_id", TENANT)
    call.setdefault("project_id", PROJECT)
    if node_scoped:
        call.pop("tenant_id", None)
        call.pop("project_id", None)
    elif method not in {
        "find_active_run",
        "list_runs",
        "create_run",
        "create_run_atomically",
    }:
        call.setdefault("run_id", RUN)
    return getattr(target, method)(**call)


def _normalized_return(method: str, value: Any) -> Any:
    if method == "create_run":
        return "RUN_ID" if isinstance(value, str) and value else repr(value)
    return value


class TestFacadeIdentity:
    def test_run_repository_is_cached_component_not_self(self, pair) -> None:
        storage, _other = pair
        repo = storage.run_repository()
        assert repo is not storage
        assert storage.run_repository() is repo

    def test_component_shares_storage_connection(self, pair) -> None:
        storage, _other = pair
        assert storage.run_repository()._conn is storage._conn

    def test_component_satisfies_run_repository_protocol(self, pair) -> None:
        storage, _other = pair
        assert isinstance(storage.run_repository(), RunRepository)


class TestClusterEquivalence:
    """Un camino por base identica; el efecto observable debe coincidir."""

    @pytest.mark.parametrize(
        "method",
        [
            "find_active_run",
            "list_runs",
            "get_run",
            "list_events_for_run",
            "load_run",
            "list_node_executions",
            "list_executed_node_names",
            "recover_interrupted_node_executions",
            "transition_run_state",
            "start_node_execution",
            "complete_node_execution",
            "mark_node_failed",
            "update_node_execution_handoff",
            "start_node_execution_atomically",
            "complete_node_execution_atomically",
            "mark_node_failed_atomically",
            "create_run",
            "create_run_atomically",
            "transition_run_state_atomically",
        ],
    )
    def test_component_path_matches_delegated_path(self, pair, method: str) -> None:
        live, delegated = pair
        kwargs = dict(_cases()[method])

        live_ret = _invoke(live.run_repository(), method, dict(kwargs))
        delegated_ret = _invoke(delegated, method, dict(kwargs))

        assert _normalized_return(method, live_ret) == _normalized_return(method, delegated_ret)
        assert _snapshot(live) == _snapshot(delegated)

        # Postcondiciones minimas por metodo (que el dump no enmascare
        # un no-op doble, p.ej. un UPDATE que no matchea nada).
        if method == "get_run":
            assert live_ret.run_id == RUN
        if method == "load_run":
            assert live_ret.run_id == RUN
        if method == "find_active_run":
            assert live_ret == RUN
        if method == "list_runs":
            assert [r.run_id for r in live_ret] == [RUN]
        if method == "list_node_executions":
            assert len(live_ret) == 5  # los 5 sembrados con node_name='n'
        if method == "list_executed_node_names":
            assert live_ret == ("n",)
        if method == "recover_interrupted_node_executions":
            assert live_ret == 5  # RUNNING: run, hand, done, fail y 'atb'
        if method == "create_run":
            assert isinstance(live_ret, str) and live_ret
        if method == "create_run_atomically":
            assert live_ret == "run-cr"
        if method == "start_node_execution":
            row = live._conn.execute(
                "SELECT state FROM node_executions WHERE node_execution_id = ?",
                (f"{RUN}-new",),
            ).fetchone()
            assert row is not None and row["state"] == "RUNNING"
        if method == "transition_run_state_atomically":
            row = live._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?", (RUN,)
            ).fetchone()
            assert row["state"] == "COMPLETED"


class TestSharedTransactionPlumbing:
    def test_facade_fault_injection_breaks_component_path_too(self, pair, monkeypatch) -> None:
        """Los tests H9/H10 parchean ``storage._insert_event_in_tx``;
        ese parche debe surtir efecto cuando el SQL corre dentro del
        componente (transaccion compartida, helper no duplicado)."""
        live, _other = pair
        real_insert = live._insert_event_in_tx

        def faulty_insert(cur: sqlite3.Cursor, event: RuntimeEvent) -> None:
            if event.event_kind == "NodeStarted":
                raise RuntimeError("fault injection: NodeStarted insert fail")
            real_insert(cur, event)

        monkeypatch.setattr(live, "_insert_event_in_tx", faulty_insert)
        with pytest.raises(RuntimeError, match="fault injection"):
            _invoke(
                live.run_repository(),
                "start_node_execution_atomically",
                dict(_cases()["start_node_execution_atomically"]),
            )
        row = live._conn.execute(
            "SELECT COUNT(*) AS n FROM node_executions WHERE node_execution_id = ?",
            (f"{RUN}-ata",),
        ).fetchone()
        assert row["n"] == 0  # rollback completo
        row = live._conn.execute(
            "SELECT COUNT(*) AS n FROM runtime_events WHERE event_id = 'evt-ata'"
        ).fetchone()
        assert row["n"] == 0

    def test_duplicate_event_id_raises_idempotency_via_both_paths(self, pair) -> None:
        """El evento con id repetido revienta en cualquier camino, no
        solo via delegado: la constraint UNIQUE vive en la base."""
        live, delegated = pair
        kwargs = dict(_cases()["transition_run_state_atomically"])

        # Primera pasada en cada camino: ok (bases distintas).
        _invoke(live.run_repository(), "transition_run_state_atomically", dict(kwargs))
        _invoke(delegated, "transition_run_state_atomically", dict(kwargs))
        # Segunda pasada sobre la misma base: IdempotencyError.
        with pytest.raises(IdempotencyError):
            _invoke(live.run_repository(), "transition_run_state_atomically", dict(kwargs))
        with pytest.raises(IdempotencyError):
            _invoke(delegated, "transition_run_state_atomically", dict(kwargs))


class TestSchemaUntouched:
    def test_new_storage_instance_sees_component_writes(self, tmp_path) -> None:
        storage = Storage(tmp_path / "single.sqlite")
        _seed_base(storage)
        storage.run_repository().transition_run_state(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=RUN,
            state="ACTIVE",
            current_node="n2",
        )
        reopened = Storage(tmp_path / "single.sqlite")
        assert (
            reopened.load_run(tenant_id=TENANT, project_id=PROJECT, run_id=RUN).current_node == "n2"
        )
        reopened.close()
