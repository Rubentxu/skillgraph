"""Red de contrato WI-55 corte 6: el cluster `run` sale de runner.

Ultimo corte del estrangulamiento H-02 (ADR-0018): `cmd_run` y sus 5
helpers de orquestacion salen a `cli.commands.run`; runner queda en
main + dispatch + subcomandos planos pequeños (<800 LoC => fuera de
god files segun audits/architecture-debt).
"""

from __future__ import annotations

import skillgraph.cli.commands.run as run_mod
from skillgraph.cli import runner


class TestRunStranglerIdentity:
    """runner.cmd_run y sus helpers DEBEN ser el componente real."""

    def test_cmd_run_identity(self) -> None:
        assert runner.cmd_run is run_mod.cmd_run

    def test_helpers_live_only_in_the_component(self) -> None:
        """Los helpers son internos del cluster: ni copias ni alias.

        El dispatch solo necesita `cmd_run`; si runner re-exporta o
        redefinie los helpers, el estrangulamiento esta a medio hacer.
        """
        assert hasattr(run_mod, "_resolve_run_inputs")
        assert hasattr(run_mod, "_reconcile_until_terminal")
        assert hasattr(run_mod, "_build_adapter")
        assert hasattr(run_mod, "_find_active_run_id")
        assert not hasattr(runner, "_resolve_run_inputs")
        assert not hasattr(runner, "_reconcile_until_terminal")
        assert not hasattr(runner, "_build_adapter")
        assert not hasattr(runner, "_find_active_run_id")


class TestGodModuleThreshold:
    """H-02 resuelto: runner por debajo del umbral de god file (800 LoC)."""

    def test_runner_under_800_loc(self) -> None:
        import inspect

        loc = len(inspect.getsource(runner).splitlines())
        assert loc < 800, f"runner volvio a ser god file: {loc} LoC"
