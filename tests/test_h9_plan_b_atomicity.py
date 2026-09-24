"""Tests TDD del H9-Plan-B (atomicidad workflow_runs ↔ runtime_events).

Estos tests son **TDD-RED**: definen el comportamiento atómico esperado
del fix. HOY fallan porque `Storage` no expone operaciones atómicas
que combinen mutación de `node_executions` con inserción de `runtime_events`.

Cuando el Plan B implemente `Storage.start_node_execution_atomically`
y similares, estos tests pasan a GREEN. Constituyen el criterio de
aceptación verificable del Plan B.

NO modifica código de producción. NO modifica los tests existentes
(`test_h9_runcontroller_characterization.py`).

Numeración T7..T10 alineada con
`docs/architecture/h9-plan-b-atomicity-characterization.md` §8.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.engine import RuntimeEvent

TENANT = "t"
PROJECT = "p"


@pytest.fixture
def storage_conn(tmp_path: Path):
    storage_path = tmp_path / "project.sqlite"
    storage = Storage(storage_path)
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    adapter = FakeAgentAdapter(fixtures_root)
    conn = storage._conn  # caracterización; necesaria para setup directo FK
    return storage, adapter, conn


@pytest.fixture
def seeded_run(storage_conn):
    """Inserta un workflow_run + node_execution RUNNING para escenarios
    que parten de estado no-vacío. FK-safe (workflow_run existe)."""
    storage, adapter, conn = storage_conn
    run_id = "run-seed"
    conn.execute(
        "INSERT INTO workflow_runs (run_id, tenant_id, project_id, "
        "plan_json, state, current_node) "
        "VALUES (?, ?, ?, '{}', 'ACTIVE', 'n')",
        (run_id, TENANT, PROJECT),
    )
    conn.execute(
        "INSERT INTO node_executions (node_execution_id, run_id, "
        "tenant_id, project_id, node_name, attempt, state, context_hash, "
        "handoff_json, started_at) "
        "VALUES ('ne-seed', ?, ?, ?, 'n', 1, 'RUNNING', 'h', '{}', "
        "datetime('now'))",
        (run_id, TENANT, PROJECT),
    )
    conn.commit()
    return storage, adapter, conn, run_id


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )


# ---------- T7 · API atómica start_node_execution_atomically ----------


class TestT7StartNodeExecutionAtomic:
    """La nueva API `Storage.start_node_execution_atomically(event, **kwargs)`
    debe confirmar INSERT node_executions RUNNING + INSERT runtime_events
    en una transacción, o ninguno.
    """

    def test_api_exists(self, seeded_run) -> None:
        storage, _a, _c, _r = seeded_run
        assert hasattr(storage, "start_node_execution_atomically")

    def test_commits_state_and_event_atomically(self, seeded_run) -> None:
        storage, _a, conn, run_id = seeded_run
        event = RuntimeEvent(
            event_id="evt-t7-ok",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeStarted",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={"ok": True},
        )
        # Llamada real. Debe confirmar ambos.
        storage.start_node_execution_atomically(
            event=event,
            node_execution_id="ne-t7",
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id=run_id,
            node_name="n2",
            attempt=2,
            context_hash="h2",
            handoff_json="{}",
        )
        # Estado
        rows = list(
            conn.execute(
                "SELECT state FROM node_executions WHERE node_execution_id = ?",
                ("ne-t7",),
            )
        )
        assert rows and rows[0]["state"] == "RUNNING"
        # Evento
        ev = list(
            conn.execute(
                "SELECT event_kind FROM runtime_events WHERE event_id = ?",
                ("evt-t7-ok",),
            )
        )
        assert ev and ev[0]["event_kind"] == "NodeStarted"

    def test_rolls_back_on_event_insert_failure(self, seeded_run, monkeypatch) -> None:
        """Si el INSERT del evento falla, ambos rollbackean."""
        storage, _a, conn, run_id = seeded_run
        # Forzar error en la segunda escritura (INSERT runtime_events).
        # Parcheamos _insert_event_in_tx para no depender de que
        # sqlite3.Connection acepte setattr en su `.execute` (read-only).
        def faulty_insert(cur, event):
            raise RuntimeError("fault injection: events table fail")

        monkeypatch.setattr(storage, "_insert_event_in_tx", faulty_insert)

        event = RuntimeEvent(
            event_id="evt-t7-rb",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeStarted",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={},
        )
        with pytest.raises(RuntimeError, match="fault injection"):
            storage.start_node_execution_atomically(
                event=event,
                node_execution_id="ne-t7-rb",
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id=run_id,
                node_name="n3",
                attempt=1,
                context_hash="h3",
                handoff_json="{}",
            )

        # Estado: rollback completo. La fila ne-t7-rb NO existe.
        rows = list(
            conn.execute(
                "SELECT node_execution_id FROM node_executions "
                "WHERE node_execution_id = ?",
                ("ne-t7-rb",),
            )
        )
        assert rows == []
        # Evento: rollback completo.
        ev = list(
            conn.execute(
                "SELECT event_id FROM runtime_events WHERE event_id = ?",
                ("evt-t7-rb",),
            )
        )
        assert ev == []


# ---------- T8 · API atómica complete_node_execution_atomically ----------


class TestT8CompleteNodeExecutionAtomic:
    """Triple atómico: UPDATE SUCCEEDED + node_completed + evidence_produced."""

    def test_api_exists(self, storage_conn) -> None:
        storage, _, _ = storage_conn
        assert hasattr(storage, "complete_node_execution_atomically")

    def test_commits_state_and_both_events(self, seeded_run) -> None:
        storage, _a, conn, run_id = seeded_run
        event_completed = RuntimeEvent(
            event_id="evt-completed",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeCompleted",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={"outcome": "ok"},
        )
        event_evidence = RuntimeEvent(
            event_id="evt-evidence",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="EvidenceProduced",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id="evt-completed",
            correlation_id=run_id,
            payload={"evidence_ref": "h"},
        )
        storage.complete_node_execution_atomically(
            event_completed=event_completed,
            event_evidence=event_evidence,
            node_execution_id="ne-seed",
            outcome="ok",
            result_json='{"outcome":"ok"}',
        )
        # Estado
        st = list(
            conn.execute(
                "SELECT state, outcome, result_json FROM node_executions "
                "WHERE node_execution_id = ?",
                ("ne-seed",),
            )
        )
        assert st and st[0]["state"] == "SUCCEEDED"
        # Ambos eventos persistidos
        ev_ids = {
            row["event_id"]
            for row in conn.execute(
                "SELECT event_id FROM runtime_events WHERE run_id = ? AND "
                "event_id IN ('evt-completed', 'evt-evidence')",
                (run_id,),
            )
        }
        assert ev_ids == {"evt-completed", "evt-evidence"}

    def test_rolls_back_on_evidence_event_failure(
        self, seeded_run, monkeypatch
    ) -> None:
        """Si falla la inserción de EvidenceProduced (segundo evento),
        el UPDATE SUCCEEDED y el NodeCompleted rollbackean."""
        storage, _a, conn, run_id = seeded_run
        # Permitimos el primer _insert_event_in_tx, rompemos el segundo.
        real_insert = storage._insert_event_in_tx

        def faulty_insert(cur, event):
            # Evento 1: NodeCompleted pasa. Evento 2: EvidenceProduced rompe.
            if event.event_kind == "EvidenceProduced":
                raise RuntimeError("fault injection: second event")
            return real_insert(cur, event)

        monkeypatch.setattr(storage, "_insert_event_in_tx", faulty_insert)

        ev_completed = RuntimeEvent(
            event_id="evt-c-rb",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeCompleted",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={},
        )
        ev_evidence = RuntimeEvent(
            event_id="evt-e-rb",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="EvidenceProduced",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id="evt-c-rb",
            correlation_id=run_id,
            payload={},
        )
        with pytest.raises(RuntimeError, match="second event"):
            storage.complete_node_execution_atomically(
                event_completed=ev_completed,
                event_evidence=ev_evidence,
                node_execution_id="ne-seed",
                outcome="ok",
                result_json='{"outcome":"ok"}',
            )
        # Estado sigue RUNNING (no se promovió a SUCCEEDED).
        st = list(
            conn.execute(
                "SELECT state FROM node_executions WHERE node_execution_id = ?",
                ("ne-seed",),
            )
        )
        assert st[0]["state"] == "RUNNING"
        # Ningún evento persistido.
        evs = list(
            conn.execute(
                "SELECT event_id FROM runtime_events WHERE "
                "event_id IN ('evt-c-rb', 'evt-e-rb')"
            )
        )
        assert evs == []


# ---------- T9 · API atómica mark_node_failed_atomically ----------


class TestT9MarkNodeFailedAtomic:
    """Atómico: UPDATE FAILED + node_failed."""

    def test_api_exists(self, storage_conn) -> None:
        storage, _, _ = storage_conn
        assert hasattr(storage, "mark_node_failed_atomically")

    def test_commits_state_and_event(self, seeded_run) -> None:
        storage, _a, conn, run_id = seeded_run
        event = RuntimeEvent(
            event_id="evt-failed",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeFailed",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={"error": "boom"},
        )
        storage.mark_node_failed_atomically(
            event=event,
            node_execution_id="ne-seed",
            error="boom",
        )
        st = list(
            conn.execute(
                "SELECT state, error FROM node_executions WHERE node_execution_id = ?",
                ("ne-seed",),
            )
        )
        assert st[0]["state"] == "FAILED"
        assert st[0]["error"] == "boom"
        ev = list(
            conn.execute(
                "SELECT event_kind FROM runtime_events WHERE event_id = ?",
                ("evt-failed",),
            )
        )
        assert ev[0]["event_kind"] == "NodeFailed"

    def test_rolls_back_on_event_failure(self, seeded_run, monkeypatch) -> None:
        storage, _a, conn, run_id = seeded_run

        def faulty_insert(cur, event):
            raise RuntimeError("fault injection: event fail")

        monkeypatch.setattr(storage, "_insert_event_in_tx", faulty_insert)

        event = RuntimeEvent(
            event_id="evt-f-rb",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeFailed",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={},
        )
        with pytest.raises(RuntimeError, match="event fail"):
            storage.mark_node_failed_atomically(
                event=event,
                node_execution_id="ne-seed",
                error="boom",
            )
        st = list(
            conn.execute(
                "SELECT state FROM node_executions WHERE node_execution_id = ?",
                ("ne-seed",),
            )
        )
        assert st[0]["state"] == "RUNNING"
        ev = list(
            conn.execute(
                "SELECT event_id FROM runtime_events WHERE event_id = ?",
                ("evt-f-rb",),
            )
        )
        assert ev == []


# ---------- T10 · Idempotencia: reaplicar no duplica ----------


class TestT10IdempotentReplay:
    """Si la transacción combinada se ejecuta dos veces con el mismo
    `event_id`:
    - la 2ª ejecución debe lanzar `IdempotencyError` (UNIQUE constraint).
    - el estado NO se duplica ni se corrompe (replay del primer commit).
    """

    def test_replay_same_event_id_raises_idempotency(
        self, seeded_run
    ) -> None:
        from skillgraph.core.errors import IdempotencyError

        storage, _a, conn, run_id = seeded_run
        event = RuntimeEvent(
            event_id="evt-idem-1",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeFailed",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={},
        )
        storage.mark_node_failed_atomically(
            event=event,
            node_execution_id="ne-seed",
            error="boom",
        )
        # Replay: mismo event_id, mismo error
        event_replay = RuntimeEvent(
            event_id="evt-idem-1",
            tenant_id=TENANT,
            project_id=PROJECT,
            event_kind="NodeFailed",
            run_id=run_id,
            resource_ref="ne-test",
            causation_id=None,
            correlation_id=run_id,
            payload={},
        )
        with pytest.raises(IdempotencyError):
            storage.mark_node_failed_atomically(
                event=event_replay,
                node_execution_id="ne-seed",
                error="boom",
            )
        # Estado consistente (sólo 1 fila, 1 evento).
        st = list(
            conn.execute(
                "SELECT node_execution_id, state FROM node_executions "
                "WHERE node_execution_id = ?",
                ("ne-seed",),
            )
        )
        assert len(st) == 1
        ev = list(
            conn.execute(
                "SELECT event_id FROM runtime_events WHERE event_id = ?",
                ("evt-idem-1",),
            )
        )
        assert len(ev) == 1


# ---------- T11 · La operación atómica NO usa la EventLog externa ----------


class TestT11UsesInternalTransactionNotEventLog:
    """El nuevo código NO debe llamar a `EventLog.append` desde dentro
    de la transacción (doble-commit evitado). Es una garantía mecánica
    por introspección: la nueva API no importa EventLog.
    """

    def test_storage_methods_have_no_eventlog_dependency(self, storage_conn) -> None:
        storage, _a, _c = storage_conn
        import inspect

        src = inspect.getsource(storage.start_node_execution_atomically)
        assert "EventLog" not in src
        src2 = inspect.getsource(storage.complete_node_execution_atomically)
        assert "EventLog" not in src2
        src3 = inspect.getsource(storage.mark_node_failed_atomically)
        assert "EventLog" not in src3
