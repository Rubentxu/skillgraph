"""Red in-proceso WI-63: handlers CLI con cobertura ciega hasta hoy.

La investigacion WI-57/63 mostro que `runs`, `expansion` y `pack` solo
tenian red via SUBPROCESS, cuya cobertura la instrumentacion pisotea
(no determinista). Esta red llama a los handlers DIRECTAMENTE
(in-proceso, patron inproc del H9), de modo que `--cov` los mide
siempre. El SETUP (crear proyecto) sigue via subprocess: lo que se
mide es la llamada al handler.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli.commands.expansion import (
    cmd_expansion_propose,
    cmd_expansion_rejections,
)
from skillgraph.cli.commands.pack import cmd_pack_load
from skillgraph.cli.commands.runs import (
    cmd_runs_budget,
    cmd_runs_cancel,
    cmd_runs_list,
)
from skillgraph.cli.runner import EXIT_DOMAIN, EXIT_OK

_RUNNER = [sys.executable, "-m", "skillgraph"]


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = {"SKILLGRAPH_DATA_ROOT": str(data_root), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _seed_project(tmp_path: Path, project: str = "demo") -> Path:
    """Setup por subprocess (NO medido): catalogo + proyecto."""
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    assert _run_cli("project", "create", project, cwd=tmp_path, data_root=data_root).returncode == 0
    return data_root


def _ns(data_root: Path, **kw: object) -> argparse.Namespace:
    return argparse.Namespace(data_root=Path(data_root), **kw)  # type: ignore[arg-type]


class TestRunsHandlersInProc:
    def test_runs_list_empty(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        data_root = _seed_project(tmp_path)
        rc = cmd_runs_list(_ns(data_root, project="demo", state=None, limit=20))
        assert rc == EXIT_OK
        assert "(sin runs)" in capsys.readouterr().out

    def test_runs_budget_missing_run(self, tmp_path: Path) -> None:
        data_root = _seed_project(tmp_path)
        rc = cmd_runs_budget(_ns(data_root, project="demo", run_id="nope"))
        assert rc == EXIT_DOMAIN

    def test_runs_cancel_missing_run_propagates_not_found(self, tmp_path: Path) -> None:
        """El handler PROPAGA NotFoundError: es `main` quien la traduce a
        EXIT_DOMAIN (contrato as-built; ver test subprocess WI-58)."""
        from skillgraph.core.errors import NotFoundError

        data_root = _seed_project(tmp_path)
        with pytest.raises(NotFoundError, match="run no encontrado"):
            cmd_runs_cancel(_ns(data_root, project="demo", run_id="nope"))


class TestPackHandlerInProc:
    def test_pack_load_fixture(self, tmp_path: Path) -> None:
        data_root = _seed_project(tmp_path)
        pack_path = Path(__file__).parent / "fixtures" / "packs" / "narrative-core.md"
        rc = cmd_pack_load(_ns(data_root, project="demo", path=pack_path))
        assert rc == EXIT_OK


class TestExpansionHandlersInProc:
    def _proposal_file(self, tmp_path: Path) -> Path:
        proposal = {
            "base_revision": "0",
            "problem_observed": "problema de prueba",
            "evidence": [],
            "operations": [
                {
                    "op": "add_node",
                    "node": {
                        "name": "nuevo",
                        "kind": "ActionNode",
                        "namespace": "shared",
                        "api_version": "skillgraph.dev/v1alpha1",
                        "resource_revision": 1,
                        "expected_result": "x",
                        "capabilities": [],
                        "metadata": {},
                    },
                }
            ],
            "new_dependencies": [],
            "capabilities_needed": [],
            "scope": "NODE",
            "attachment_point": "nodo-a",
            "rollback_plan": [],
            "authorization": {
                "mode": "manual_signed",
                "granted_by": "wi63",
                "granted_at": "2026-10-02T00:00:00+00:00",
            },
            "author": "wi63",
        }
        path = tmp_path / "proposal.json"
        path.write_text(json.dumps(proposal), encoding="utf-8")
        return path

    def test_expansion_propose_inproc(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        data_root = _seed_project(tmp_path)
        proposal_json = self._proposal_file(tmp_path)
        rc = cmd_expansion_propose(_ns(data_root, project="demo", proposal_json=proposal_json))
        assert rc == EXIT_OK
        assert "Propuesta" in capsys.readouterr().out

    def test_expansion_rejections_empty_inproc(self, tmp_path: Path) -> None:
        data_root = _seed_project(tmp_path)
        rc = cmd_expansion_rejections(_ns(data_root, project="demo"))
        assert rc == EXIT_OK
