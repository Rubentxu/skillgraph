"""Tests subprocess CLI para `sg policy` (S5 Etapa 7)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

# Reusamos los helpers del archivo tests/test_cli_runs_inspect.py para
# crear el proyecto base. Como pytest los descubre por nombre, los
# importamos directamente.
from tests.test_cli_runs_inspect import _init_project, _project_db_path


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    """Helper: invoca el CLI `sg` con argumentos."""
    cmd = [
        sys.executable,
        "-m",
        "skillgraph.cli.runner",
        "--data-root",
        str(data_root),
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


class TestPolicyCli:
    """`sg policy get` y `sg policy set` (S5 Etapa 7)."""

    def test_get_policy_no_policy_prints_default(self, tmp_path: Path) -> None:
        """`sg policy get` sin policy configurada -> policy=none."""
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "policy",
            "get",
            "demo",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode == 0, result.stderr
        assert "policy=none" in result.stdout
        assert "tenant_id=default" in result.stdout

    def test_set_policy_persists_then_get_returns_it(self, tmp_path: Path) -> None:
        """`sg policy set ... --redact-policy payload` persiste."""
        data_root = _init_project(tmp_path)
        # Set.
        result_set = _run_cli(
            "policy",
            "set",
            "demo",
            "--redact-policy",
            "payload",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result_set.returncode == 0, result_set.stderr
        # Get.
        result_get = _run_cli(
            "policy",
            "get",
            "demo",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result_get.returncode == 0, result_get.stderr
        assert "policy=payload" in result_get.stdout

    def test_set_policy_rejects_invalid_choice(self, tmp_path: Path) -> None:
        """`sg policy set --redact-policy invalid` -> exit != 0."""
        data_root = _init_project(tmp_path)
        result = _run_cli(
            "policy",
            "set",
            "demo",
            "--redact-policy",
            "mask",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert result.returncode != 0, result.stdout
        assert "invalid choice" in result.stderr.lower()

    def test_set_policy_persists_to_storage(self, tmp_path: Path) -> None:
        """El set persiste en la tabla tenant_policies (verificable SQL)."""
        data_root = _init_project(tmp_path)
        _run_cli(
            "policy",
            "set",
            "demo",
            "--redact-policy",
            "full",
            cwd=tmp_path,
            data_root=data_root,
        )
        db_path = _project_db_path(data_root)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT redaction_policy FROM tenant_policies WHERE tenant_id = ?",
                ("default",),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["redaction_policy"] == "full"
