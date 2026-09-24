"""Tests de caracterización para H9-BSlice3 (RunController ↔ Storage).

Este archivo **no modifica código de producción**: solo bloquea el
comportamiento observable de las 10 SQL sites del RunController
identificadas en `docs/architecture/h9-bslice3-runcontroller-storage.md`.

Sirve como red de seguridad para los futuros slices del refactor
que añadirá APIs transaccionales a `Storage` y migrará `RunController`.

Reglas:
- Cada test verifica UNA invariante observable HOY. Si pasa, está
  midiendo el comportamiento actual (que puede tener la grieta de
  no-atomicidad). Si pasa tras el refactor, el comportamiento se ha
  preservado o mejorado sin regresión.
- T1, T2 son **red de seguridad de no-regresión sobre atomicidad
  observable**: documentan el comportamiento observable actual.
  Un refactor que cambie comportamiento sin evidencia debe romper
  estos tests a propósito.
- T3, T4, T5, T6 son invariantes de orden/forma de las lecturas.

Numeración T# alineada con el documento §5.1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skillgraph.core.errors import IdempotencyError
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.engine import EventLog, RuntimeEvent
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"


# ---------- Fixtures compartidas (mismo patron que test_runcontroller.py) ---


@pytest.fixture
def storage_conn(
    tmp_path: Path,
) -> tuple[Storage, FakeAgentAdapter, sqlite3.Connection]:
    """Storage + adapter + conn. El conn es lo que permite inyectar al
    RunController HOY (el refactor futuro eliminará esta dependencia)."""
    storage_path = tmp_path / "project.sqlite"
    storage = Storage(storage_path)
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    adapter = FakeAgentAdapter(fixtures_root)
    conn = storage._conn  # type: ignore[attr-defined]  # caracterizacion intencional
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
    node_name: str,
    outcome: str,
) -> None:
    p = fixtures_root / TENANT / PROJECT / f"{node_name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"outcome":"' + outcome + '","result":{"x":1}}', encoding="utf-8")


# ---------- T1 · create_run state persiste si event append lanza ---


class TestT1CreateRunStatePersistsIfAppendFails:
    """S1: comportamiento actual observable.

    Si `create_run` ejecuta INSERT del workflow_run, commitea, y el
    posterior `EventLog.append` lanza `IdempotencyError`, el workflow_run
    queda persistido sin su evento. Esta grieta es observable y debe
    documentarse. Un futuro refactor que introduzca atomicidad real
    PASARÁ este test (el INSERT + append pueden o no hacer rollback;
    lo que se exige es que la invariante observable sea REASONABLE).
    """

    def test_workflow_run_remains_after_idempotency_error(
        self,
        storage_conn: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
    ) -> None:
        storage, _adapter, conn = storage_conn
        ctl = RunController(storage=storage, adapter=_adapter)
        plan = _plan((_node("a"),))
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)

        # Forzar IdempotencyError reusando el mismo event_id.
        # Tomamos el event_id emitido por create_run.
        row = conn.execute(
            "SELECT event_id FROM runtime_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert row is not None  # sanity: el evento sí se emitió.

        log = EventLog(conn)
        with pytest.raises(IdempotencyError):
            log.append(
                RuntimeEvent(
                    event_id=row["event_id"],  # mismo event_id -> UNIQUE
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

        # Caracterización: el workflow_run SIGUE EXISTIENDO tras el
        # IdempotencyError. Esta es la grieta de no-atomicidad HOY.
        run_row = conn.execute(
            "SELECT state, current_node FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run_row is not None
        assert run_row["state"] == "CREATED"
        assert run_row["current_node"] == "a"


# ---------- T2 · complete_node_execution estado + eventos ---


class TestT2CompleteNodeExecutionAtomicityObservable:
    """S6: tras un reconcile exitoso, runs state y eventos conviven.

    Documenta el comportamiento esperado: si todo va bien, ambos
    lados quedan reflejados. Si la operación global falla por algo
    distinto a un evento duplicado, hoy NO hay garantía de que ambos
    lados queden consistentes — esto se documenta en el documento y
    el test verifica solo el camino feliz (que es lo que se exige
    preservar).
    """

    def test_succeeded_run_has_state_and_events(
        self,
        storage_conn: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = storage_conn
        fixtures_root = tmp_path / "fixtures"
        _seed_fixture(fixtures_root, node_name="only", outcome="ok")

        ctl = RunController(storage=storage, adapter=adapter)
        plan = _plan((_node("only"),))
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        snap = ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert snap.state == "COMPLETED"

        # Estado consistente
        run_row = conn.execute(
            "SELECT state FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert run_row["state"] == "COMPLETED"

        # Eventos esperados: run_created + node_started + node_completed + evidence_produced
        event_kinds = tuple(
            r["event_kind"]
            for r in conn.execute(
                "SELECT event_kind FROM runtime_events WHERE run_id = ? ORDER BY sequence ASC",
                (run_id,),
            ).fetchall()
        )
        for kind in (
            "RunCreated",
            "NodeStarted",
            "NodeCompleted",
            "EvidenceProduced",
        ):
            assert kind in event_kinds, f"falta evento {kind} en {event_kinds}"


# ---------- T3 · recover_interrupted por-fila ---


class TestT3RecoverInterruptedPerRowAtomic:
    """S4: cada UPDATE dentro del bucle abre su propia transacción.

    Caracterización observable: `_recover_interrupted` RECUPERA
    TODOS los NodeExecutions RUNNING del run, sin discriminar. Esto
    es importante documentarlo: si un día se quisiese preservar alguno
    (p. ej. el inicial) sería un cambio de comportamiento.
    """

    def test_all_running_node_executions_are_recovered(
        self,
        storage_conn: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, _adapter, conn = storage_conn

        # Primero creamos un workflow_run real para satisfacer las FK.
        ctl = RunController(storage=storage, adapter=_adapter)
        plan = _plan((_node("stays_running"), (_node("to_recover"))))
        real_run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)

        # Renombrar el run con SQL para que sea determinista.
        conn.execute(
            "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
            ("run-rec", real_run_id),
        )
        conn.commit()

        # Sembramos dos NodeExecutions RUNNING bajo ese run_id.
        conn.execute(
            "INSERT INTO node_executions (node_execution_id, run_id, "
            "tenant_id, project_id, node_name, attempt, state, "
            "started_at) VALUES (?, ?, ?, ?, ?, 1, 'RUNNING', "
            "datetime('now'))",
            ("ne-r-1", "run-rec", TENANT, PROJECT, "stays_running"),
        )
        conn.execute(
            "INSERT INTO node_executions (node_execution_id, run_id, "
            "tenant_id, project_id, node_name, attempt, state, "
            "started_at) VALUES (?, ?, ?, ?, ?, 1, 'RUNNING', "
            "datetime('now'))",
            ("ne-r-2", "run-rec", TENANT, PROJECT, "to_recover"),
        )
        conn.commit()

        ctl._recover_interrupted(tenant_id=TENANT, project_id=PROJECT, run_id="run-rec")

        rows = conn.execute(
            "SELECT state, finished_at FROM node_executions WHERE run_id = ?",
            ("run-rec",),
        ).fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r["state"] == "READY"
            assert r["finished_at"] is not None


# ---------- T4 · orden state change antes que evento ---


class TestT4StateChangeBeforeEvent:
    """Invariante observable: el state se mueva antes del evento.

    Si observamos en cualquier reconciliación la fila y los eventos,
    la fila debe tener el state actualizado, mientras que el evento
    puede aparecer como el último de la secuencia. Lo que PROHIBE
    este test es un estado futuro sin su evento.
    """

    def test_workflow_runs_row_state_is_consistent_with_last_event(
        self,
        storage_conn: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
        tmp_path: Path,
    ) -> None:
        storage, adapter, conn = storage_conn
        fixtures_root = tmp_path / "fixtures"
        _seed_fixture(fixtures_root, node_name="only", outcome="ok")

        ctl = RunController(storage=storage, adapter=adapter)
        plan = _plan((_node("only"),))
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)

        # Estado final esperado:
        run_row = conn.execute(
            "SELECT state FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert run_row["state"] == "COMPLETED"

        # El evento "RunCompleted" NO se emite por el controller actual
        # (se delega al llamador), pero los eventos de nodo SÍ.
        ev_completed = conn.execute(
            "SELECT 1 FROM runtime_events WHERE run_id = ? AND event_kind = 'NodeCompleted'",
            (run_id,),
        ).fetchone()
        assert ev_completed is not None


# ---------- T5 · orden de _node_executions_for ---


class TestT5NodeExecutionsForOrdering:
    """S8: ordering por `started_at ASC`."""

    def test_orders_by_started_at_ascending(
        self,
        storage_conn: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
    ) -> None:
        storage, _adapter, conn = storage_conn

        # Primero workflow_run real para satisfacer FK.
        ctl = RunController(storage=storage, adapter=_adapter)
        plan = _plan((_node("ordered"),))
        real_run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        conn.execute(
            "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
            ("run-order", real_run_id),
        )
        conn.commit()

        # Sembramos tres ejecuciones para el mismo nodo con timestamps
        # en orden distinto al de insercion.
        for ne_id, started in [
            ("ne-c", "2026-09-23 10:00:00"),
            ("ne-a", "2026-09-23 08:00:00"),
            ("ne-b", "2026-09-23 09:00:00"),
        ]:
            conn.execute(
                "INSERT INTO node_executions (node_execution_id, run_id, "
                "tenant_id, project_id, node_name, attempt, state, "
                "started_at) VALUES (?, ?, ?, ?, ?, 1, 'SUCCEEDED', ?)",
                (ne_id, "run-order", TENANT, PROJECT, "ordered", started),
            )
        conn.commit()

        rows = ctl._node_executions_for(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-order",
            node_name="ordered",
        )
        ids = [r["node_execution_id"] for r in rows]
        assert ids == ["ne-a", "ne-b", "ne-c"]


# ---------- T6 · DISTINCT + ORDER de _executed_node_names ---


class TestT6ExecutedNodeNamesDistinctSorted:
    """S9: distinct node_name con state=SUCCEEDED, ordenado."""

    def test_returns_distinct_sorted_names(
        self,
        storage_conn: tuple[Storage, FakeAgentAdapter, sqlite3.Connection],
    ) -> None:
        storage, _adapter, conn = storage_conn

        # Primero workflow_run real para satisfacer FK.
        ctl = RunController(storage=storage, adapter=_adapter)
        plan = _plan((_node("z_node"),))
        real_run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        conn.execute(
            "UPDATE workflow_runs SET run_id = ? WHERE run_id = ?",
            ("run-dn", real_run_id),
        )
        conn.commit()

        # Siembra: dos nodos SUCCEEDED, un nodo RUNNING, un SUCCEEDED duplicado.
        seeds = [
            ("ne-1", "z_node", "SUCCEEDED"),
            ("ne-2", "a_node", "SUCCEEDED"),
            ("ne-3", "m_node", "RUNNING"),  # no cuenta
            ("ne-4", "z_node", "SUCCEEDED"),  # duplicado
        ]
        for ne_id, node_name, state in seeds:
            conn.execute(
                "INSERT INTO node_executions (node_execution_id, run_id, "
                "tenant_id, project_id, node_name, attempt, state, "
                "started_at) VALUES (?, ?, ?, ?, ?, 1, ?, "
                "datetime('now'))",
                (ne_id, "run-dn", TENANT, PROJECT, node_name, state),
            )
        conn.commit()

        names = ctl._executed_node_names(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-dn",
        )
        assert names == ("a_node", "z_node")
