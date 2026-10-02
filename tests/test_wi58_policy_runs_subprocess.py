"""Red end-to-end WI-58: `sg policy` y `sg runs` via subprocess.

La investigacion WI-57 (evidence/investigation-2026-10-02.md) mostro
que estos handlers eran los UNICOS consumidores runtime de
`_open_project_storage` sin red end-to-end: el decorador
`@contextmanager` perdido en el corte 2 los rompio (TypeError en cada
invocacion) y ningun test lo vio durante 6 commits. Esta red ejercita
el binario real (`python -m skillgraph ...`) para que cualquier rotura
de ese contrato vuelva a ser visible en el primer gate.

Alcance deliberadamente minimo: camino feliz + error de dominio. La
logica de negocio ya esta cubierta por las suites de storage y
runcontroller; aqui se protege la FRONTERA argv -> handler -> salida.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from skillgraph.cli.support import EXIT_USAGE


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def _init_project(tmp_path: Path, project: str = "demo") -> Path:
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    assert _run_cli("project", "create", project, cwd=tmp_path, data_root=data_root).returncode == 0
    return data_root


class TestPolicySubprocess:
    def test_policy_get_default_subprocess(self, tmp_path: Path) -> None:
        """`policy get` exit=0 sobre el contexto roto en WI-53/57."""
        data_root = _init_project(tmp_path)
        result = _run_cli("policy", "get", "demo", cwd=tmp_path, data_root=data_root)
        assert result.returncode == 0, result.stderr
        assert "policy=none" in result.stdout

    def test_policy_set_then_get_subprocess(self, tmp_path: Path) -> None:
        """`policy set --redact-policy` persiste y `get` lo devuelve."""
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "policy",
            "set",
            "demo",
            "--redact-policy",
            "metadata",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, result.stderr
        assert "policy=metadata" in result.stdout
        result = _run_cli("policy", "get", "demo", cwd=tmp_path, data_root=data_root)
        assert result.returncode == 0, result.stderr
        assert "policy=metadata" in result.stdout

    def test_policy_set_rejects_invalid_choice(self, tmp_path: Path) -> None:
        """Caso contrafactual: choice invalido -> argparse lo rechaza.

        WI-88 (ADR-0016): antes rechazaba con 2, el codigo de argparse, que
        en esta CLI colisiona con `EXIT_BAD_NAME`. Ahora rechaza con
        `EXIT_USAGE`, que es lo que el contrato declaraba.
        """
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "policy",
            "set",
            "demo",
            "--redact-policy",
            "bogus",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == EXIT_USAGE, result.stderr
        assert "invalid choice" in result.stderr


class TestRunsSubprocess:
    def test_runs_list_empty_subprocess(self, tmp_path: Path) -> None:
        """`runs list` sobre proyecto sin runs -> exit=0 y '(sin runs)'."""
        data_root = _init_project(tmp_path)
        result = _run_cli("runs", "list", "demo", cwd=tmp_path, data_root=data_root)
        assert result.returncode == 0, result.stderr
        assert "(sin runs)" in result.stdout

    def test_runs_budget_missing_run_is_domain_error(self, tmp_path: Path) -> None:
        """Caso contrafactual: run inexistente -> EXIT_DOMAIN (10) con
        mensaje legible, no traceback."""
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "runs",
            "budget",
            "demo",
            "nope",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 10
        # Este handler captura NotFoundError LOCALMENTE y imprime con
        # prefijo plano: contrato as-built distinto del de `cancel`.
        assert "ERROR: run no encontrado: nope" in result.stderr
        assert "Traceback" not in result.stderr

    def test_runs_cancel_missing_run_is_domain_error(self, tmp_path: Path) -> None:
        """Caso contrafactual: cancelar run inexistente -> EXIT_DOMAIN con
        el codigo tipado en el mensaje."""
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "runs",
            "cancel",
            "demo",
            "nope",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 10
        assert "sg_not_found" in result.stderr
        assert "run no encontrado" in result.stderr
        assert "Traceback" not in result.stderr
