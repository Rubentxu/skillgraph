"""Red de contrato WI-53 corte 2: estrangulamiento del cluster `runs`.

Segundo corte de ADR-0018: los 5 handlers `cmd_runs_*` salen a
`cli.commands.runs`; `_open_project_storage` (compartida por >=2
clusters) vive en `cli.support` y `runner` conserva alias para su
dispatch y sus 4 usos internos.
"""

from __future__ import annotations

import skillgraph.cli.commands.runs as runs
from skillgraph.cli import runner
from skillgraph.cli.support import _open_project_storage


class TestRunsStranglerIdentity:
    """runner.cmd_runs_* DEBE ser el componente real, no una copia."""

    def test_list_identity(self) -> None:
        assert runner.cmd_runs_list is runs.cmd_runs_list

    def test_show_identity(self) -> None:
        assert runner.cmd_runs_show is runs.cmd_runs_show

    def test_logs_identity(self) -> None:
        assert runner.cmd_runs_logs is runs.cmd_runs_logs

    def test_cancel_identity(self) -> None:
        assert runner.cmd_runs_cancel is runs.cmd_runs_cancel

    def test_budget_identity(self) -> None:
        assert runner.cmd_runs_budget is runs.cmd_runs_budget


class TestSharedHelperPlacement:
    """_open_project_storage es compartida: vive en support, no en runner."""

    def test_open_project_storage_lives_in_support(self) -> None:
        assert runner._open_project_storage is _open_project_storage

    def test_runner_keeps_no_private_copy(self) -> None:
        import inspect

        assert "def _open_project_storage" not in inspect.getsource(runner)
