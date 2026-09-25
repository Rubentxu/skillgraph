"""Cobertura subprocess de las ramas del CLI no cubiertas por
test_cli_uat ni test_cli_run_uat.

Cubre exit codes:
- EXIT_DB_MISSING (5): inspect sobre proyecto con DB borrada.
- EXIT_PLAN_NOT_FOUND (6): run con plan inexistente.
- EXIT_DOMAIN (10): main() captura un SkillGraphError que escapa.
- EXIT_VALIDATION (12): brick con kind valido pero validacion falla.
- EXIT_RUN_INCOMPLETE (21): workflow que no termina en max_iterations
  (loop con ciclo). Aqui se modela un workflow con DecisionNode que
  siempre devuelve el mismo outcome sin transicion que agota el run.
- EXIT_USAGE (1): comando desconocido.
- max_iterations warning: workflow circular que agota el budget.

Reglas (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Subprocess sobre la CLI instalada por uv (mismo patron que test_cli_uat).
- Aislamiento total por test (data_root en tmp_path).
- Estos tests son defensa en profundidad: cada uno verifica una rama
  del CLI que, de fallar, haria pasar bugs silenciosos al usuario.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from skillgraph.cli import runner

# ---------------------------------------------------------------------------
# Helpers (duplicados a proposito: cero acoplamiento entre test files)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
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
    assert _run_cli("project", "create", project, cwd=tmp_path, data_root=data_root).returncode == 0
    return data_root


def _project_db_path(data_root: Path, project: str = "demo") -> Path:
    return data_root / "tenants" / "default" / "projects" / project / "project.sqlite"


def _write_plan_linear(path: Path, *, names: list[str]) -> None:
    """Escribe un WorkflowPlan lineal (sin ciclos, terminal en el ultimo nodo).

    Se usa en tests que NO quieren probar comportamiento del controller;
    el ciclo de INCOMPLETE se fuerza con monkeypatch.
    """
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
        for a, b in pairwise(names[:-1])
    )
    body = f"""---
apiVersion: skillgraph.dev/v1alpha1
kind: WorkflowPlan
name: linear
initial: {names[0]}
nodes:
{nodes_yaml}
transitions:
{transitions_yaml}
---

# plan lineal
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


# ---------------------------------------------------------------------------
# EXIT_DB_MISSING (5): inspect con DB borrada
# ---------------------------------------------------------------------------


class TestCliExitDbMissing:
    def test_inspect_after_db_file_deleted(self, tmp_path: Path) -> None:
        """Si el .sqlite del proyecto se borra, inspect devuelve exit=5."""
        data_root = _init_project(tmp_path)
        db_path = _project_db_path(data_root)
        assert db_path.exists()
        db_path.unlink()
        result = _run_cli("project", "inspect", "demo", cwd=tmp_path, data_root=data_root)
        assert result.returncode == 5
        assert "ausente" in result.stderr


# ---------------------------------------------------------------------------
# EXIT_PLAN_NOT_FOUND (6): run con plan que no existe
# ---------------------------------------------------------------------------


class TestCliExitPlanNotFound:
    def test_run_with_missing_plan_file(self, tmp_path: Path) -> None:
        data_root = _init_project(tmp_path)
        ghost = tmp_path / "ghost-plan.md"
        fixtures_root = tmp_path / "fixtures"
        result = _run_cli(
            "run",
            "--fixtures-root",
            str(fixtures_root),
            "demo",
            str(ghost),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 6
        assert "no encontrado" in result.stderr


# ---------------------------------------------------------------------------
# EXIT_DOMAIN (10): main() captura un SkillGraphError escapado
# ---------------------------------------------------------------------------


class TestCliExitDomain:
    def test_main_catches_skillgraph_error(self, tmp_path: Path, monkeypatch) -> None:
        """main() envuelve cualquier SkillGraphError que escape en EXIT_DOMAIN.

        Forzamos un error monkeypatching storage para que lance
        IdempotencyError (que es SkillGraphError) en medio del flujo.
        """
        from skillgraph.cli import runner
        from skillgraph.core.errors import IdempotencyError

        # Forzamos que cmd_project_list lance una excepcion de dominio
        # interceptando catalog para que get_project lance IdempotencyError
        # en una llamada que normalmente no lo haria.
        # NOTA: parcheamos runner (no cli) porque cmd_project_list resuelve
        # open_catalog en los globals del modulo runner.
        def boom(*args, **kwargs):
            raise IdempotencyError("simulado")

        monkeypatch.setattr(runner, "open_catalog", boom)
        result = runner.main(["--data-root", str(tmp_path / "data"), "project", "list"])
        assert result == 10


# ---------------------------------------------------------------------------
# EXIT_VALIDATION (12): brick con kind valido pero validacion falla
# ---------------------------------------------------------------------------


class TestCliExitValidation:
    def test_brick_with_invalid_semantics_returns_exit_12(self, tmp_path: Path) -> None:
        """Un Domain Pack valido en YAML pero con semantica invalida
        -> registry.validate() lanza ValidationError -> exit=12.

        _validate_domain_pack exige spec.version como string. Pasamos
        un int (1) para disparar la validacion de tipo y obtener
        exit=12 en lugar de exit=0.
        """
        data_root = _init_project(tmp_path, project="proj")
        bad = tmp_path / "bad.md"
        bad.write_text(
            "---\n"
            "apiVersion: skillgraph.dev/v1alpha1\n"
            "kind: DomainPack\n"
            "metadata:\n"
            "  name: bad-pack\n"
            "  namespace: software\n"
            "spec:\n"
            "  version: 1\n"
            "  capabilities:\n"
            "    - name: review\n"
            "---\n"
            "# bad pack\n",
            encoding="utf-8",
        )
        result = _run_cli(
            "brick",
            "proj",
            str(bad),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 12, (
            f"esperaba exit 12, obtuvo {result.returncode}; stderr={result.stderr!r}"
        )
        assert "version" in result.stderr


# ---------------------------------------------------------------------------
# EXIT_RUN_INCOMPLETE (21): workflow que agota max-iterations
# ---------------------------------------------------------------------------


class TestCliExitRunIncomplete:
    def test_max_iterations_hits_active_state(self, tmp_path: Path, monkeypatch) -> None:
        """Si reconcil_run siempre devuelve un RunSnapshot ACTIVE, el bucle
        while del CLI agota --max-iterations y devuelve EXIT_RUN_INCOMPLETE.

        Esto modela el caso real (futuro H4+) en el que un nodo del
        workflow deja el run en ACTIVE sin transicionar, p.ej. un
        DecisionNode que pide input humano o un agente que retorna
        outcome='pending'. En H2 NO existe tal DecisionNode todavia
        (SkillGraph H2 = DAG lineal), asi que invocamos main() in-process
        con monkeypatch sobre RunController.reconcile_run para forzar el
        path de INCOMPLETE sin inventar funcionalidad.

        In-process y no subprocess porque no podemos monkeypatchear
        codigo que se ejecuta en otro proceso Python.
        """
        import skillgraph.runtime.runcontroller as rc_module
        from skillgraph.runtime.runcontroller import RunSnapshot

        # Monkeypatch ANTES de main() porque el CLI hace import local
        # cada vez. In-process.
        def reconcile_stub(self, **kwargs):
            return RunSnapshot(
                run_id=kwargs["run_id"],
                state="ACTIVE",
                current_node="a",
                executed_nodes=(),
                events_emitted=0,
            )

        monkeypatch.setattr(rc_module.RunController, "reconcile_run", reconcile_stub)

        data_root = _init_project(tmp_path)
        fixtures_root = tmp_path / "fixtures"
        _write_fixture(fixtures_root, name="a")
        plan = tmp_path / "plan.md"
        _write_plan_linear(plan, names=["a"])

        # In-process via cli.main()
        from skillgraph import cli as cli_module

        rc = cli_module.main(
            [
                "--data-root",
                str(data_root),
                "run",
                "--fixtures-root",
                str(fixtures_root),
                "--max-iterations",
                "2",
                "demo",
                str(plan),
            ]
        )
        assert rc == 21, f"esperaba exit 21 (incomplete), obtuvo {rc}"
        # Output fue a stdout real; no podemos capturar pero el
        # exit code es la evidencia.


# ---------------------------------------------------------------------------
# EXIT_USAGE (1): subcomando desconocido
# ---------------------------------------------------------------------------


class TestCliExitUsage:
    def test_unknown_command_returns_exit_2(self, tmp_path: Path) -> None:
        """argparse ya devuelve exit=2 para choice invalid.

        El EXIT_USAGE (1) del CLI es un dead code en la practica
        porque argparse anidado tiene choices para todos los
        sub-subcomandos y atrapa los invalidos antes de llegar al
        dispatch de cmd_main. Mantenemos la constante por si en el
        futuro queremos reportar errores de uso propios; este test
        documenta la frontera actual con argparse.
        """
        data_root = _init_project(tmp_path)
        result = _run_cli("totally-unknown-command", cwd=tmp_path, data_root=data_root)
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# version flag y help
# ---------------------------------------------------------------------------


class TestCliHelpAndVersion:
    def test_version_flag_prints_version(self, tmp_path: Path) -> None:
        result = _run_cli("--version", cwd=tmp_path, data_root=tmp_path / "x")
        assert result.returncode == 0
        assert result.stdout.startswith("skillgraph ")

    def test_no_args_prints_help(self, tmp_path: Path) -> None:
        result = _run_cli(cwd=tmp_path, data_root=tmp_path / "x")
        assert result.returncode == 0
        assert "SkillGraph" in result.stdout
        # Todos los subcomandos aparecen en el help.
        for cmd in ("init", "project", "brick", "run"):
            assert cmd in result.stdout


class TestCliArgparseErrors:
    """Ramas de error del parser argparse (entrada InProcess de `main`).

    Estos errores se manifiestan como `SystemExit(2)` desde argparse;
    subprocess tests los ven como rc=2, pero pytest-cov solo registra
    la cobertura de codigo ejecutado InProcess. Por eso los cubrimos
    explicitamente aqui con `pytest.raises(SystemExit)` en lugar de
    via subprocess: para sumar ~3-5% de cobertura del entry point
    `main()` sin duplicar los tests de acceptance.
    """

    def test_main_unknown_flag_exits_with_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`main(["--bogus-flag"])` -> argparse eleva SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            runner.main(
                [
                    "--data-root",
                    str(tmp_path / "data"),
                    "--no-such-flag",
                    "init",
                ]
            )
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "unrecognized arguments" in err
        assert "--no-such-flag" in err

    def test_main_project_invalid_subcommand_exits_with_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`main(["project", "bogus"])` -> argparse 'invalid choice'."""
        with pytest.raises(SystemExit) as exc_info:
            runner.main(
                [
                    "--data-root",
                    str(tmp_path / "data"),
                    "project",
                    "bogus-sub",
                ]
            )
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "invalid choice" in err

    def test_main_project_list_extra_positional_exits_with_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`main(["project", "list", "extra"])` -> argparse 'unrecognized'."""
        with pytest.raises(SystemExit) as exc_info:
            runner.main(
                [
                    "--data-root",
                    str(tmp_path / "data"),
                    "project",
                    "list",
                    "extra-positional",
                ]
            )
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "unrecognized arguments" in err

    def test_main_help_full_prints_and_returns_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`main(["--help"])` -> SystemExit(0) con help completo."""
        with pytest.raises(SystemExit) as exc_info:
            runner.main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "SkillGraph" in out
        assert "--data-root" in out
        assert "--version" in out


# ---------------------------------------------------------------------------
# Knowledge CLI (H3 Slice 5)
# ---------------------------------------------------------------------------


def _seed_knowledge(data_root: Path, *, source_id: str = "local:src/foo.py") -> None:
    """Carga un Source + Entity + Claim en el knowledge del proyecto demo.

    Lo hace invocando un python -c que usa el controller real; asi los
    tests E2E pueden partir de un estado conocido.
    """
    code = (
        "from pathlib import Path;"
        "from skillgraph.platform.paths import resolve_data_root, project_db_path, DEFAULT_TENANT;"
        "from skillgraph.platform.storage import Storage;"
        "from skillgraph.knowledge.knowledge_controller import KnowledgeController;"
        "from skillgraph.knowledge.graph import Claim, Entity, Source;"
        f"data_root = resolve_data_root(Path({str(data_root)!r}));"
        "db = project_db_path(data_root, 'demo', DEFAULT_TENANT);"
        "s = Storage(db);"
        "ctl = KnowledgeController(storage=s, tenant_id=DEFAULT_TENANT, project_id='demo');"
        f"ctl.register_source(source=Source(source_id={source_id!r}, kind='local_file', content_hash='h', locator={{'path': 'src/foo.py'}}, git_commit_sha=None, git_tree_sha=None, working_tree_status=None, checked_at='2026-01-01T00:00:00Z', freshness='fresh'));"
        "ctl.upsert_entity(entity=Entity(entity_id='file:src/foo.py', kind='file', stable_key='src/foo.py'));"
        "ctl.record_claim(claim=Claim(claim_id='c1', subject_entity_id='file:src/foo.py', predicate='line_count', object_literal=42, source_id='local:src/foo.py', extraction_method='manual', extractor_version='skillgraph-rules/0.1.0', checked_at_revision='rev1'));"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"seed fallo: stderr={result.stderr!r} stdout={result.stdout!r}")


class TestCliKnowledgeExitOk:
    def test_knowledge_stale_subprocess(self, tmp_path: Path) -> None:
        """`knowledge stale demo` -> exit=0 (sin stale)."""
        data_root = _init_project(tmp_path)
        _seed_knowledge(data_root)
        result = _run_cli(
            "knowledge",
            "stale",
            "demo",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, result.stderr
        assert "stale claims" in result.stdout

    def test_knowledge_invalidate_subprocess(self, tmp_path: Path) -> None:
        """`knowledge invalidate` -> exit=0 y reporta 1 claim invalidado."""
        data_root = _init_project(tmp_path)
        _seed_knowledge(data_root)
        result = _run_cli(
            "knowledge",
            "invalidate",
            "demo",
            "--source",
            "local:src/foo.py",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, result.stderr
        assert "invalidated 1" in result.stdout

    def test_knowledge_compile_subprocess_succeeds(self, tmp_path: Path) -> None:
        """`knowledge compile --strict` exit=0 cuando hay knowledge y no stale."""
        data_root = _init_project(tmp_path)
        _seed_knowledge(data_root)
        result = _run_cli(
            "knowledge",
            "compile",
            "demo",
            "local:src/foo.py",
            "--strict",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        assert "context_hash" in result.stdout

    def test_knowledge_compile_strict_rejects_subprocess(self, tmp_path: Path) -> None:
        """strict + source invalidated -> exit=10 (DOMAIN error)."""
        data_root = _init_project(tmp_path)
        _seed_knowledge(data_root)
        # invalidamos primero para tener stale.
        _run_cli(
            "knowledge",
            "invalidate",
            "demo",
            "--source",
            "local:src/foo.py",
            cwd=tmp_path,
            data_root=data_root,
        )
        result = _run_cli(
            "knowledge",
            "compile",
            "demo",
            "local:src/foo.py",
            "--strict",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 10, result.stdout
        assert "stale" in result.stderr.lower()

    def test_knowledge_trace_subprocess(self, tmp_path: Path) -> None:
        """`knowledge trace` exit=0 y devuelve JSON con trace_id."""
        data_root = _init_project(tmp_path)
        _seed_knowledge(data_root)
        result = _run_cli(
            "knowledge",
            "trace",
            "demo",
            "--run",
            "run-cli-trace",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, result.stderr
        # El output es JSON con trace_id.
        out = result.stdout
        import json as _json

        parsed = _json.loads(out)
        assert "trace_id" in parsed
        assert parsed["kind"] == "SoftwareExecutionSlice"
