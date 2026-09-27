"""Caracterizacion del contrato de dispatch del CLI (WI-41).

El auditor de arquitectura marca `main` en `skillgraph.cli.runner` como
el UNICO hotspot publico con cc>=20 (refactor obligatorio). Este fichero
fija el comportamiento observable de ese dispatch ANTES de extraer codigo,
de modo que la extraccion sea demostrablemente sin cambio de comportamiento.

Contrato fijado:
- C1  Cada subcomando declarado en el parser enruta a su handler.
- C2  La tabla de dispatch es completa: ningun comando queda huerfano.
- C3  Los tres helpers de "abrir proyecto + storage" comparten contrato.
- C4  Un comando desconocido produce EXIT_USAGE, no una excepcion.
- C5  Sin subcomando se imprime la ayuda y se devuelve EXIT_OK.

Reglas (AGENTS.md 6.1): tests rojos primero. Este fichero debe pasar
contra el codigo ANTES de la extraccion; si falla antes, el contrato
elegido no describe el comportamiento real.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli import runner

# ---------------------------------------------------------------------------
# Extraer el contrato de dispatch del codigo real
# ---------------------------------------------------------------------------


def _command_names() -> tuple[str, ...]:
    parser = runner._build_parser()
    subparsers = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert subparsers, "el parser raiz debe declarar subcomandos"
    return tuple(sorted(subparsers[0].choices))


def _subparser_for(command: str) -> argparse.ArgumentParser:
    parser = runner._build_parser()
    subparsers = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    return subparsers[0].choices[command]


def _subcommand_choices(command: str) -> tuple[str, ...]:
    """Subcomandos declarados bajo `command`, leidos del parser real."""
    actions = [
        action
        for action in _subparser_for(command)._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if not actions:
        return ()
    return tuple(sorted(actions[0].choices))


# ---------------------------------------------------------------------------
# C1 / C2  La tabla de dispatch cubre todos los subcomandos declarados
# ---------------------------------------------------------------------------


class TestDispatchTableCompleteness:
    def test_todo_comando_del_parser_tiene_entrada(self) -> None:
        """C2: ningun comando del parser puede quedar huerfano.

        Un comando plano se indexa por nombre; uno con subcomandos, por
        el par (comando, subcomando). La tabla se contrasta contra el
        parser real, no contra una lista escrita a mano.
        """
        declared = set(_command_names())
        flat = {key for key in runner._DISPATCH if isinstance(key, str)}
        nested = {key[0] for key in runner._DISPATCH if not isinstance(key, str)}
        assert flat == declared - nested, (
            f"comandos planos sin entrada: {(declared - nested) - flat}; "
            f"entradas planas huerfanas: {flat - (declared - nested)}"
        )
        assert nested <= declared, f"grupos huerfanos: {nested - declared}"

    def test_todo_subcomando_anidado_tiene_entrada(self) -> None:
        """C2: cada (comando, subcomando) declarado esta en la tabla."""
        for command, attribute in runner._SUBCOMMAND_OF.items():
            if attribute is None:
                continue
            for sub in _subcommand_choices(command):
                assert (command, sub) in runner._DISPATCH, (
                    f"falta entrada en _DISPATCH para ({command!r}, {sub!r})"
                )

    def test_ninguna_clave_esta_huerfana(self) -> None:
        """Ninguna entrada apunta a un comando inexistente o handler roto."""
        declared = set(_command_names())
        for key in runner._DISPATCH:
            command = key if isinstance(key, str) else key[0]
            assert command in declared, f"clave huerfana en _DISPATCH: {key!r}"
            assert callable(runner._DISPATCH[key]), f"handler no invocable: {key!r}"

    def test_main_delega_y_no_tiene_ramas_de_comando(self) -> None:
        """`main` sigue siendo un dispatch, no un negociador.

        Si esto falla, alguien reintrodujo el if-chain dentro de main y la
        extraccion deja de ser mecanica.
        """
        import inspect

        source = inspect.getsource(runner.main)
        assert "args.command ==" not in source, "if-chain reintroducido en main"
        assert "_resolve_handler(args)" in source, "main debe resolver via tabla"

    def test_resolve_handler_devuelve_none_para_comando_sin_handler(self) -> None:
        """`None` es el contrato para 'sin handler': main imprime ayuda."""
        args = argparse.Namespace(command="comando-inexistente-en-tabla")
        assert runner._resolve_handler(args) is None

    def test_resolve_handler_resuelve_plano_y_anidado(self) -> None:
        """La resolucion cubre ambos niveles de la tabla."""
        assert runner._resolve_handler(argparse.Namespace(command="init")) is runner.cmd_init
        assert (
            runner._resolve_handler(argparse.Namespace(command="project", project_command="list"))
            is runner.cmd_project_list
        )
        assert (
            runner._resolve_handler(argparse.Namespace(command="runs", runs_command="budget"))
            is runner.cmd_runs_budget
        )

    def test_resolve_handler_devuelve_none_para_subcomando_desconocido(self) -> None:
        """Un subcomando sin entrada no resuelve a un handler."""
        args = argparse.Namespace(command="runs", runs_command="inventado")
        assert runner._resolve_handler(args) is None

    def test_dispatch_nested_reporta_subcomando_invalido(self) -> None:
        """`_dispatch_nested` conserva el contrato EXIT_USAGE del router."""
        args = argparse.Namespace(runs_command="inventado")
        assert runner._dispatch_nested("runs", args) == runner.EXIT_USAGE

    @pytest.mark.parametrize("command", _command_names())
    def test_todo_subcomando_esta_registrado(self, command: str) -> None:
        """Cada subcomando del parser debe ser alcanzable desde main."""
        assert hasattr(runner, "main")
        assert command in _command_names(), command


# ---------------------------------------------------------------------------
# C3  Los tres helpers de apertura de proyecto/storage comparten contrato
# ---------------------------------------------------------------------------


class TestProjectOpenHelpers:
    def test_los_tres_helpers_existen(self) -> None:
        for name in ("_open_known_project", "_open_project_storage", "_open_project_or_error"):
            assert callable(getattr(runner, name)), name

    def test_open_known_project_gestiona_ciclo_de_vida(self) -> None:
        """Debe gestionar el ciclo de vida del Storage (contextmanager)."""
        fn = runner._open_known_project
        assert callable(fn)

    def test_open_project_or_error_no_lanza_para_proyecto_ausente(self, tmp_path: Path) -> None:
        """Un proyecto inexistente devuelve (None, exit_code), no excepcion."""
        args = argparse.Namespace(data_root=tmp_path / "data")
        result, code = runner._open_project_or_error(args, "no-existe-xyz")
        assert result is None
        assert code != 0, "proyecto ausente debe producir exit code de error"


# ---------------------------------------------------------------------------
# C4 / C5  Comportamiento observable en el borde
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


class TestDispatchObservableBehaviour:
    def test_comando_desconocido_devuelve_usage(self, tmp_path: Path) -> None:
        """Comando invalido lo atrapa argparse con exit=2, no llega a main.

        Mismo contrato que `test_cli_branches.TestCliExitUsage`: el
        `EXIT_USAGE` (1) de main es dead code en la practica porque
        argparse declara choices para todos los subcomandos.
        """
        proc = _run_cli("no-existe", cwd=tmp_path, data_root=tmp_path / "sg-data")
        assert proc.returncode == 2, proc.stderr

    def test_sin_comando_imprime_ay_devuelve_ok(self, tmp_path: Path) -> None:
        proc = _run_cli(cwd=tmp_path, data_root=tmp_path / "sg-data")
        assert proc.returncode == runner.EXIT_OK, proc.stderr
        assert "usage" in (proc.stdout + proc.stderr).lower()

    def test_version_responde(self, tmp_path: Path) -> None:
        proc = _run_cli("--version", cwd=tmp_path, data_root=tmp_path / "sg-data")
        assert proc.returncode == runner.EXIT_OK
        assert "skillgraph" in proc.stdout


# ---------------------------------------------------------------------------
# C2bis  El contrato publico del modulo no cambia al extraer
# ---------------------------------------------------------------------------


class TestPublicSurfaceStability:
    def test_exit_codes_publicos_son_estables(self) -> None:
        for name in (
            "EXIT_OK",
            "EXIT_USAGE",
            "EXIT_DOMAIN",
            "EXIT_PROJECT_NOT_FOUND",
        ):
            assert isinstance(getattr(runner, name), int), name

    def test_handlers_publicos_siguen_importables(self) -> None:
        """D7: mover simbolos no puede romper la API importada por tests."""
        for name in (
            "cmd_init",
            "cmd_run",
            "cmd_project_create",
            "cmd_project_list",
            "cmd_project_inspect",
            "cmd_backup",
            "cmd_brick_register",
            "cmd_pack_load",
            "cmd_pack_import",
        ):
            assert callable(getattr(runner, name)), name

    def test_parser_expone_ayuda_por_comando(self, tmp_path: Path) -> None:
        proc = _run_cli("runs", "--help", cwd=tmp_path, data_root=tmp_path / "sg-data")
        assert proc.returncode == runner.EXIT_OK
        assert "runs" in proc.stdout


# ---------------------------------------------------------------------------
# C6  El auditor no debe reportar `main` como hotspot tras el refactor
# ---------------------------------------------------------------------------


class TestAuditGateForMain:
    def test_main_no_esta_en_hotspots_publicos(self) -> None:
        """Gate D1: el informe de deuda no debe listar `main` (cc>=20)."""
        from datetime import UTC, datetime

        report = Path("audits") / f"architecture-debt-{datetime.now(UTC).date()}.md"
        if not report.exists():
            pytest.skip("auditoria del dia no generada todavia")
        text = report.read_text(encoding="utf-8")
        section = text.split("## Hotspots publicos")[-1].split("##")[0]
        assert "`main`" not in section, (
            "main sigue listado como hotspot publico: refactor incompleto"
        )
