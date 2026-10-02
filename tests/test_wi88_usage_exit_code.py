"""WI-88: los errores de uso devuelven EXIT_USAGE y el 2 queda libre (ADR-0016).

Antes de este cambio, `argparse` abortaba los errores de invocacion con su
codigo 2, y 2 ya era `EXIT_BAD_NAME`, que `runner.py:131` devuelve vivo.
Tres fallos sin relacion devolvian el mismo numero:

    skillgraph project create "NOMBRE INVALIDO"  -> 2  (EXIT_BAD_NAME)
    skillgraph no-existe-comando                 -> 2  (error de uso)
    skillgraph runs budget                       -> 2  (error de uso)

Un script que comprobara `rc == 2` para detectar un nombre invalido recibia
un falso positivo ante cualquier error de uso, y `EXIT_USAGE` (1) no se
producia nunca.

Los tests de este archivo se centran en tres cosas:

- no comprueban codigos sueltos, sino la **separabilidad** de las dos
  categorias: que un error de uso y un nombre invalido NO compartan numero;
- fijan `--help` y `--version` en 0, porque no son errores de uso y un
  arreglo de este estilo es el sitio tipico donde se rompen;
- cubren los tres niveles del parser (raiz, sub, sub-sub), que es donde
  una correccion parcial pasaria inadvertida.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli.parser import build_parser
from skillgraph.cli.support import EXIT_BAD_NAME, EXIT_OK, EXIT_USAGE

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


class TestUsageErrorsReturnUsageCode:
    """Cada error de invocacion aborta con EXIT_USAGE, no con 2."""

    @pytest.mark.parametrize(
        ("argv", "motivo"),
        [
            (["no-existe-comando"], "comando raiz inexistente"),
            (["no-existe-comando", "sub"], "subcomando inexistente"),
            (["runs", "budget"], "faltan argumentos requeridos (nivel sub)"),
            (["backup"], "subcomando requerido ausente (nivel sub)"),
            (["--opcion-inexistente"], "opcion global inexistente"),
        ],
    )
    def test_usage_error_exits_with_usage_code(self, argv: list[str], motivo: str) -> None:
        with pytest.raises(SystemExit) as exc:
            _parse(*argv)
        assert exc.value.code == EXIT_USAGE, f"{motivo}: {argv}"

    def test_usage_error_is_not_the_bad_name_code(self) -> None:
        """La colision concreta: el 2 queda libre para EXIT_BAD_NAME."""
        with pytest.raises(SystemExit) as exc:
            _parse("no-existe-comando")
        assert exc.value.code != EXIT_BAD_NAME

    def test_error_message_still_goes_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Convertir el codigo no puede tragarse el diagnostico."""
        with pytest.raises(SystemExit):
            _parse("no-existe-comando")
        err = capsys.readouterr().err
        assert "invalid choice" in err
        assert "usage" in err.lower()


class TestNonUsageOutcomesAreUnaffected:
    """Lo que no es error de uso no se toca."""

    def test_help_exits_ok(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            _parse("--help")
        assert exc.value.code == EXIT_OK

    def test_subcommand_help_exits_ok(self) -> None:
        with pytest.raises(SystemExit) as exc:
            _parse("runs", "--help")
        assert exc.value.code == EXIT_OK

    def test_version_flag_is_not_a_usage_error(self, tmp_path: Path) -> None:
        """`--version` es un flag propio, no la action `version` de argparse.

        Medido: `parser.py:37-39` lo declara con `action="store_true"`, luego
        NO aborta; lo atiende el runner y devuelve 0. Una prueba que
        esperase un `SystemExit` estaria afirmando algo falso sobre el
        programa, y solo pasaria si alguien cambiara la declaracion.
        """
        args = _parse("--version")
        assert args.version is True

        from skillgraph.cli.runner import main

        rc = main(["--data-root", str(tmp_path / "sg-data"), "--version"])
        assert rc == EXIT_OK

    def test_valid_invocation_parses(self) -> None:
        """Un arreglo en error() no puede romper el camino feliz."""
        args = _parse("runs", "budget", "demo", "r1")
        assert args.command == "runs"


class TestBadNameKeepsItsOwnCode:
    """EXIT_BAD_NAME sigue siendo 2, y ya no significa tambien 'uso'."""

    def test_bad_name_returns_two(self, tmp_path: Path) -> None:
        from skillgraph.cli.runner import main

        rc = main(
            [
                "--data-root",
                str(tmp_path / "sg-data"),
                "project",
                "create",
                "Nombre Con Espacios",
            ]
        )
        assert rc == EXIT_BAD_NAME == 2

    def test_the_two_categories_are_disjoint(self, tmp_path: Path) -> None:
        """La propiedad que se compro: 1 y 2 significan cosas distintas."""
        from skillgraph.cli.runner import main

        bad_name = main(["--data-root", str(tmp_path / "a"), "project", "create", "Con Espacios"])
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["no-existe-comando"])
        usage = exc.value.code

        assert bad_name != usage, (
            f"EXIT_BAD_NAME y el error de uso comparten el codigo {bad_name}: "
            "un script no puede distinguirlos"
        )


class TestEveryLevelOfTheParserIsCovered:
    """Un solo sitio corregido debe cubrir los tres niveles del parser.

    Se comprueba por comportamiento y no mirando la clase: `argparse`
    propaga `type(self)` a los subparsers, y una correccion aplicada solo
    a la raiz dejaria los niveles internos devolviendo 2 sin que nada lo
    note. Estos tres casos son raiz, sub y sub-sub.
    """

    def test_root_level(self) -> None:
        with pytest.raises(SystemExit) as exc:
            _parse("no-existe-comando")
        assert exc.value.code == EXIT_USAGE

    def test_subparser_level(self) -> None:
        # `runs` existe, pero le faltan los posicionales requeridos.
        with pytest.raises(SystemExit) as exc:
            _parse("runs", "budget")
        assert exc.value.code == EXIT_USAGE

    def test_sub_subparser_level(self) -> None:
        # `promotion` existe y exige a su vez un subcomando.
        with pytest.raises(SystemExit) as exc:
            _parse("promotion")
        assert exc.value.code == EXIT_USAGE


class TestRealProcessContract:
    """El contrato externo, medido en un subproceso real."""

    def _run(self, *argv: str, data_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from skillgraph.cli import main; raise SystemExit(main())",
                *argv,
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={"PATH": "/usr/bin:/bin", "SKILLGRAPH_DATA_ROOT": str(data_root)},
        )

    def test_unknown_command_in_a_real_process(self, tmp_path: Path) -> None:
        proc = self._run("no-existe-comando", data_root=tmp_path / "d")
        assert proc.returncode == EXIT_USAGE, proc.stderr

    def test_bad_name_in_a_real_process(self, tmp_path: Path) -> None:
        proc = self._run("project", "create", "Con Espacios", data_root=tmp_path / "d")
        assert proc.returncode == EXIT_BAD_NAME, proc.stderr
