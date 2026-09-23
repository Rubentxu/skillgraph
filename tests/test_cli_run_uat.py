"""Tests subprocess del CLI `run` (Etapa 2).

Estos tests cierran H2 por la via UAT real: invocan `python -m skillgraph`
como lo haria una persona y comprueban el recorrido desde la shell.

Cubre:
- UAT-04 (ejecucion determinista): un workflow lineal termina COMPLETED
  con eventos emitidos por el EventLog.
- UAT-06 (recuperacion): un Run interrumpido se reanuda sin repetir
  acciones confirmadas y devuelve los NodeExecutions colgados a READY.
- UAT-07 (idempotencia): emitir el mismo `event_id` dos veces NO duplica
  la accion.

El Adapter es siempre FakeAgentAdapter (modo determinista local).

Reglas (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Tests subprocess sobre la CLI instalada por `uv`.
- Aislamiento total por test (data root en tmp_path).
- Negative-space testing: tamizar el EventLog para verificar ausencia
  de eventos duplicados o re-emisiones tras recover.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoca `python -m skillgraph.cli` con aislamiento total.

    `cwd` y `data_root` son directorios temporales; el test no debe
    depender de ningun estado del repo del usuario.
    """
    env = os.environ.copy()
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph.cli", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _init_project(tmp_path: Path, project: str = "demo") -> Path:
    """Crea data_root + proyecto. Devuelve el data_root."""
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    r = _run_cli(
        "project", "create", project, cwd=tmp_path, data_root=data_root
    )
    assert r.returncode == 0, r.stderr
    return data_root


def _write_plan(path: Path, *, initial: str, names: list[str]) -> None:
    """Escribe un WorkflowPlan.md lineal (cada nodo -> siguiente)."""
    nodes_yaml = "\n".join(
        f"""    - name: {n}
      kind: ActionNode
      namespace: shared
      apiVersion: skillgraph.dev/v1alpha1
      resourceRevision: 1
      expectedResult: file"""
        for n in names
    )
    transitions_yaml = "\n".join(
        f"""  - source: {a}
    outcome: ok
    target: {b}"""
        for a, b in zip(names, names[1:])
    )
    body = f"""---
apiVersion: skillgraph.dev/v1alpha1
kind: WorkflowPlan
name: linear
initial: {initial}
nodes:
{nodes_yaml}
transitions:
{transitions_yaml}
---

# plan
"""
    path.write_text(body, encoding="utf-8")


def _write_fixture(fixtures_root: Path, *, name: str, outcome: str = "ok") -> None:
    """Escribe una fixture del FakeAgentAdapter para el nodo `name`.

    Por defecto el Adapter busca:
      <fixtures_root>/<tenant>/<project>/<name>.json
    """
    fixtures_root.mkdir(parents=True, exist_ok=True)
    p = fixtures_root / "default" / "demo" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {"outcome": outcome, "result": {"step": name}, "evidence_ref": f"ev-{name}"}
        ),
        encoding="utf-8",
    )


def _project_db_path(data_root: Path, project: str = "demo") -> Path:
    """Devuelve la ruta del project.sqlite (para inspeccion directa)."""
    return data_root / "tenants" / "default" / "projects" / project / "project.sqlite"


def _open_project_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _latest_run_id(db: sqlite3.Connection) -> str:
    row = db.execute(
        "SELECT run_id FROM workflow_runs ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row is not None, "no hay runs registrados"
    return row["run_id"]


# ---------------------------------------------------------------------------
# UAT-04: ejecucion determinista via CLI
# ---------------------------------------------------------------------------


class TestUAT04ExecutionDeterministicViaCli:
    def test_linear_workflow_completes_via_cli(
        self, tmp_path: Path
    ) -> None:
        """Tres nodos lineales -> run COMPLETED, 17 eventos (UAT-04)."""
        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        for n in ("collect", "transform", "deliver"):
            _write_fixture(fixtures_root, name=n)
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="collect", names=["collect", "transform", "deliver"])

        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, result.stderr
        assert "Estado: COMPLETED" in result.stdout
        assert "collect" in result.stdout
        assert "deliver" in result.stdout

        # Inspeccion directa del EventLog: 1 RunCreated + 5 eventos/nodo
        # (NodeScheduled, HandoffCreated, NodeStarted, NodeCompleted,
        # EvidenceProduced) = 16 + 1 RunCompleted = 17.
        db = _open_project_db(_project_db_path(data_root))
        try:
            run_id = _latest_run_id(db)
            n_events = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            assert n_events == 17, f"esperaba 17 eventos, obtuvo {n_events}"
            # Tres nodos SUCCEEDED, ninguno FAILED.
            succeeded = db.execute(
                "SELECT COUNT(*) AS c FROM node_executions WHERE run_id = ? AND state = 'SUCCEEDED'",
                (run_id,),
            ).fetchone()["c"]
            assert succeeded == 3
            # El run esta COMPLETED.
            state = db.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()["state"]
            assert state == "COMPLETED"
        finally:
            db.close()

    def test_outcome_not_declared_marks_run_failed(
        self, tmp_path: Path
    ) -> None:
        """Fixture devuelve outcome no declarado -> Run FAILED, exit=20.

        El plan declara la transicion `collect -ok-> transform`. La
        fixture devuelve outcome 'surprise' (no 'ok'), asi que el
        Adapter no produce un outcome declarado y el nodo FAILED.
        """
        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        # La fixture devuelve outcome "surprise" que no esta en el plan.
        _write_fixture(fixtures_root, name="collect", outcome="surprise")
        # transform tambien tiene fixture por si la primera ejecucion
        # pasara (no deberia, pero asi no falla por error tangencial).
        _write_fixture(fixtures_root, name="transform", outcome="ok")
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="collect", names=["collect", "transform"])

        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 20, (
            f"esperaba exit 20 (FAILED), obtuvo {result.returncode}; "
            f"stderr={result.stderr!r} stdout={result.stdout!r}"
        )
        assert "Estado: FAILED" in result.stdout

    def test_missing_fixture_marks_run_failed(self, tmp_path: Path) -> None:
        """Sin fixture -> FakeAgentAdapter NotFoundError -> Run FAILED."""
        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        # NO escribimos fixture.
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="collect", names=["collect"])

        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 20
        assert "Estado: FAILED" in result.stdout

    def test_unknown_project_returns_exit_4(self, tmp_path: Path) -> None:
        """Proyecto inexistente -> exit 4 (ProjectResolver)."""
        data_root = _init_project(tmp_path)
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="a", names=["a"])
        fixtures_root = tmp_path / "fixtures"

        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "ghost",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 4
        assert "no existe" in result.stderr

    def test_invalid_plan_returns_exit_11(self, tmp_path: Path) -> None:
        """Plan con front matter invalido -> exit 11 (ParseError)."""
        data_root = _init_project(tmp_path)
        plan = tmp_path / "plan.md"
        plan.write_text("---\nesto no es yaml valido: [\n", encoding="utf-8")
        fixtures_root = tmp_path / "fixtures"

        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 11
        assert "sg_parse" in result.stderr


# ---------------------------------------------------------------------------
# UAT-06: recuperacion desde CLI tras crash simulado
# ---------------------------------------------------------------------------


def _seed_active_run(
    tmp_path: Path,
    data_root: Path,
    *,
    plan_path: Path,
    node_crashed: str,
    fixtures_root: Path,
) -> str:
    """Crea un run en estado ACTIVE con un NodeExecution RUNNING colgado.

    Simula un crash del CLI en medio de la ejecucion: hay un run
    ACTIVE, current_node=node_crashed, y un NodeExecution RUNNING
    sin finished_at para ese mismo nodo. El siguiente `run` debe
    detectar el colgado, devolverlo a READY, y re-ejecutarlo hasta
    que el workflow termine COMPLETED.
    """
    import yaml as _yaml

    from skillgraph.agent import FakeAgentAdapter
    from skillgraph.runcontroller import RunController
    from skillgraph.storage import Storage

    with open(plan_path, encoding="utf-8") as f:
        text = f.read()
    fm = text.split("---", 2)[1]
    data = _yaml.safe_load(fm)

    storage = Storage(_project_db_path(data_root))
    try:
        from skillgraph.plan_loader import _plan_from_dict  # interno OK en tests

        plan = _plan_from_dict(data, source=str(plan_path))
        adapter = FakeAgentAdapter(fixtures_root)
        ctl = RunController(storage=storage, adapter=adapter, conn=storage._conn)  # type: ignore[attr-defined]
        run_id = ctl.create_run(tenant_id="default", project_id="demo", plan=plan)
        # Forzar el run a ACTIVE en current_node=node_crashed.
        ctl._set_run_state(  # type: ignore[attr-defined]
            tenant_id="default",
            project_id="demo",
            run_id=run_id,
            state="ACTIVE",
            current_node=node_crashed,
        )
        # Insertar NodeExecution RUNNING colgado.
        storage._conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO node_executions
                (node_execution_id, run_id, tenant_id, project_id,
                 node_name, attempt, state, context_hash, started_at)
            VALUES (?, ?, 'default', 'demo', ?, 1, 'RUNNING', 'fakehash',
                    datetime('now'))
            """,
            (f"ne-crashed-{uuid.uuid4()}", run_id, node_crashed),
        )
        storage._conn.commit()  # type: ignore[attr-defined]
        return run_id
    finally:
        storage.close()


class TestUAT06RecoveryViaCli:
    def test_recovery_resumes_active_run_after_crash(
        self, tmp_path: Path
    ) -> None:
        """UAT-06: tras un crash, el siguiente `run` del CLI continua
        desde el nodo colgado sin duplicar eventos ya confirmados.

        Setup: un run ACTIVE con un NodeExecution RUNNING colgado para
        'collect'. El siguiente `run` debe (a) detectar el colgado,
        (b) devolverlo a READY, (c) ejecutarlo y (d) completar hasta
        COMPLETED.
        """
        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        for n in ("collect", "transform"):
            _write_fixture(fixtures_root, name=n)
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="collect", names=["collect", "transform"])

        run_id = _seed_active_run(
            tmp_path,
            data_root,
            plan_path=plan,
            node_crashed="collect",
            fixtures_root=fixtures_root,
        )

        db = _open_project_db(_project_db_path(data_root))
        try:
            n_before = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            crashed_states = [
                r["state"]
                for r in db.execute(
                    "SELECT state FROM node_executions WHERE run_id = ? AND node_name = 'collect'",
                    (run_id,),
                ).fetchall()
            ]
            assert "RUNNING" in crashed_states, (
                f"setup incorrecto: no hay RUNNING colgado en {crashed_states}"
            )
        finally:
            db.close()

        # El siguiente `run` debe reanudar y completar.
        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, f"stderr={result.stderr!r} stdout={result.stdout!r}"
        assert "Estado: COMPLETED" in result.stdout

        db = _open_project_db(_project_db_path(data_root))
        try:
            n_after = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            # Se emiten eventos de recovery + ejecucion de collect + transform.
            assert n_after > n_before, (
                f"recovery no emitio eventos: antes={n_before} despues={n_after}"
            )
            states = [
                r["state"]
                for r in db.execute(
                    "SELECT state FROM node_executions WHERE run_id = ? "
                    "ORDER BY started_at",
                    (run_id,),
                ).fetchall()
            ]
            assert "READY" in states, (
                f"recovery no promovio el RUNNING colgado a READY: {states}"
            )
            assert states.count("SUCCEEDED") == 2, (
                f"recovery no completo ambos nodos: {states}"
            )
        finally:
            db.close()

    def test_repeated_run_on_completed_does_not_duplicate(
        self, tmp_path: Path
    ) -> None:
        """Idempotencia estricta: ejecutar `run` sobre un run ya
        COMPLETED NO re-emite eventos ni re-ejecuta nodos.
        """
        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        for n in ("collect", "transform"):
            _write_fixture(fixtures_root, name=n)
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="collect", names=["collect", "transform"])

        r1 = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r1.returncode == 0
        assert "Estado: COMPLETED" in r1.stdout

        db = _open_project_db(_project_db_path(data_root))
        try:
            run_id = _latest_run_id(db)
            n1 = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            succ1 = db.execute(
                "SELECT COUNT(*) AS c FROM node_executions WHERE run_id = ? AND state = 'SUCCEEDED'",
                (run_id,),
            ).fetchone()["c"]
        finally:
            db.close()

        r2 = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r2.returncode == 0
        assert "Estado: COMPLETED" in r2.stdout

        db = _open_project_db(_project_db_path(data_root))
        try:
            n2 = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            succ2 = db.execute(
                "SELECT COUNT(*) AS c FROM node_executions WHERE run_id = ? AND state = 'SUCCEEDED'",
                (run_id,),
            ).fetchone()["c"]
            assert n2 == n1, (
                f"segundo run duplico eventos: antes={n1} despues={n2}"
            )
            assert succ2 == succ1, (
                f"segundo run re-ejecuto nodos: antes={succ1} despues={succ2}"
            )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# UAT-07: idempotencia via CLI (sin re-emitir eventos)
# ---------------------------------------------------------------------------


class TestUAT07IdempotencyViaCli:
    def test_repeated_run_does_not_duplicate_events(
        self, tmp_path: Path
    ) -> None:
        """UAT-07 via CLI: ejecutar `run` dos veces NO duplica eventos.

        El primer run completa el workflow; el segundo run encuentra el
        Run COMPLETED y termina sin emitir eventos.
        """
        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        for n in ("a", "b"):
            _write_fixture(fixtures_root, name=n)
        plan = tmp_path / "plan.md"
        _write_plan(plan, initial="a", names=["a", "b"])

        r1 = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r1.returncode == 0
        assert "Estado: COMPLETED" in r1.stdout

        db = _open_project_db(_project_db_path(data_root))
        try:
            run_id = _latest_run_id(db)
            n1 = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
        finally:
            db.close()

        # Segundo run: debe ser COMPLETED sin nuevos eventos.
        r2 = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(plan),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r2.returncode == 0
        assert "Estado: COMPLETED" in r2.stdout

        db = _open_project_db(_project_db_path(data_root))
        try:
            n2 = db.execute(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["c"]
            assert n2 == n1, (
                f"segundo run duplico eventos: antes={n1} despues={n2}"
            )
        finally:
            db.close()
