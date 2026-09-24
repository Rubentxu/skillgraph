"""Tests subprocess del CLI `runs cancel` (Etapa 7 / S1).

Cubre el contrato externo del comando `sg runs cancel <project> <run-id>`:
- Exit code 0 cuando el run se cancela OK.
- Estado persistido = CANCELLED en `workflow_runs`.
- Evento `RunCompleted(state=CANCELLED)` emitido.
- Exit code != 0 cuando el run no existe (NotFoundError -> EXIT_DOMAIN).

Reglas (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Tests subprocess sobre la CLI instalada por `uv`.
- Aislamiento total por test (data root en tmp_path).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from itertools import pairwise
from pathlib import Path


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoca `python -m skillgraph.cli` con aislamiento total."""
    env = os.environ.copy()
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _init_project(tmp_path: Path, project: str = "demo") -> Path:
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    r = _run_cli("project", "create", project, cwd=tmp_path, data_root=data_root)
    assert r.returncode == 0, r.stderr
    return data_root


def _write_plan(path: Path, *, initial: str, names: list[str]) -> None:
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
        for a, b in pairwise(names)
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
    fixtures_root.mkdir(parents=True, exist_ok=True)
    p = fixtures_root / "default" / "demo" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"outcome": outcome, "result": {"step": name}, "evidence_ref": f"ev-{name}"}),
        encoding="utf-8",
    )


def _project_db_path(data_root: Path, project: str = "demo") -> Path:
    return data_root / "tenants" / "default" / "projects" / project / "project.sqlite"


def _open_project_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _latest_run_id(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT run_id FROM workflow_runs ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row is not None, "no hay runs registrados"
    return row["run_id"]


class TestRunsCancelCli:
    def test_cancel_active_run_via_cli_marks_cancelled(
        self, tmp_path: Path
    ) -> None:
        """`sg runs cancel <project> <run_id>` cancela un run ACTIVE.

        Setup: plan lineal de 3 nodos; sembramos fixture para el primero
        (collect) pero NO para los siguientes. Asi el run queda ACTIVE
        tras el primer reconcile (transform nunca encuentra fixture ->
        FAILED). Pero queremos probar cancel sobre ACTIVE, asi que
        usamos un plan de UN solo nodo y cancelamos ANTES del reconcile.
        En realidad `sg run` reconcilia en el mismo comando, asi que
        necesitamos un mecanismo para 'dejar' un run activo. Usamos
        un plan con un nodo que falle y luego reseteamos manualmente
        el state a ACTIVE via SQL... NO: eso acopla el test al schema.

        Estrategia alternativa: crear el run directamente via SQLite
        (sin ejecutar `sg run`), y luego cancelarlo por CLI.
        """
        data_root = _init_project(tmp_path)
        db_path = _project_db_path(data_root)
        assert db_path.exists()

        # Insertar manualmente un Run en estado ACTIVE para que
        # `sg runs cancel` lo pueda cancelar.
        db = _open_project_db(db_path)
        try:
            db.execute(
                """
                INSERT INTO workflow_runs
                    (run_id, tenant_id, project_id, plan_json, state, current_node,
                     created_at, updated_at)
                VALUES (?, 'default', 'demo', '{}', 'ACTIVE', 'a',
                        datetime('now'), datetime('now'))
                """,
                ("run-cli-test",),
            )
            db.commit()
        finally:
            db.close()

        result = _run_cli(
            "runs", "cancel", "demo", "run-cli-test",
            cwd=tmp_path, data_root=data_root,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
        assert "state=CANCELLED" in result.stdout

        db = _open_project_db(db_path)
        try:
            state = db.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                ("run-cli-test",),
            ).fetchone()["state"]
            assert state == "CANCELLED"
            # Evento RunCompleted emitido con state=CANCELLED.
            ev = db.execute(
                "SELECT event_kind, payload_json FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCompleted'",
                ("run-cli-test",),
            ).fetchone()
            assert ev is not None
            payload = json.loads(ev["payload_json"])
            assert payload["state"] == "CANCELLED"
        finally:
            db.close()

    def test_cancel_unknown_run_via_cli_returns_error(
        self, tmp_path: Path
    ) -> None:
        """Cancelar un run inexistente -> EXIT_DOMAIN (error tipado)."""
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "runs", "cancel", "demo", "run-que-no-existe",
            cwd=tmp_path, data_root=data_root,
        )
        # NotFoundError es subclase de SkillGraphError -> el dispatcher
        # principal traduce a EXIT_DOMAIN (10).
        assert result.returncode != 0, (
            f"esperaba rc != 0; stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
