"""Red de contrato WI-52 corte 1: estrangulamiento del cluster `expansion`.

Patron ADR-0016 trasladado al CLI (ADR-0018): los handlers
`cmd_expansion_*` salen a un componente real (`cli.commands.expansion`)
y `runner` conserva SOLO alias de import, de modo que la tabla de
dispatch (WI-41) y los call-sites no se editan. Los helpers compartidos
(EXIT_*, resolucion de proyecto, I/O de plan) viven en `cli.support`.

La identidad es la red: si manana alguien reimplanta un handler en
runner en vez de delegar, el `is` falla.
"""

from __future__ import annotations

import skillgraph.cli.commands.expansion as expansion
from skillgraph.cli import runner
from skillgraph.cli.support import EXIT_VALIDATION


class TestExpansionStranglerIdentity:
    """runner.cmd_expansion_* DEBE ser el componente real, no una copia."""

    def test_propose_identity(self) -> None:
        assert runner.cmd_expansion_propose is expansion.cmd_expansion_propose

    def test_apply_identity(self) -> None:
        assert runner.cmd_expansion_apply is expansion.cmd_expansion_apply

    def test_validate_identity(self) -> None:
        assert runner.cmd_expansion_validate is expansion.cmd_expansion_validate

    def test_rejections_identity(self) -> None:
        assert runner.cmd_expansion_rejections is expansion.cmd_expansion_rejections

    def test_list_identity(self) -> None:
        assert runner.cmd_expansion_list is expansion.cmd_expansion_list

    def test_show_identity(self) -> None:
        assert runner.cmd_expansion_show is expansion.cmd_expansion_show

    def test_archive_identity(self) -> None:
        assert runner.cmd_expansion_archive is expansion.cmd_expansion_archive


class TestSupportExtraction:
    """Los helpers compartidos viven en support y runner los re-exporta."""

    def test_exit_codes_are_the_support_ones(self) -> None:
        assert runner.EXIT_VALIDATION is EXIT_VALIDATION

    def test_runner_does_not_redefine_moved_helpers(self) -> None:
        """Los helpers movidos viven SOLO en support: ni copias ni sombras.

        `_load_plan_from_storage` ya solo lo usa el componente expansion
        (via support); si runner vuelve a definirlo, es una copia del
        estrangulamiento a medio hacer y este test lo caza.
        """
        assert not hasattr(runner, "_load_plan_from_storage")
        assert not hasattr(runner, "_load_registry")
        assert not hasattr(runner, "_ops_from_dict")

    def test_support_does_not_import_runner(self) -> None:
        """El strangler no puede crear un ciclo de imports runner<->commands."""
        import sys

        support = sys.modules["skillgraph.cli.support"]
        assert not hasattr(support, "runner")
        source_names = getattr(support, "__dict__", {})
        assert "cmd_expansion_propose" not in source_names
