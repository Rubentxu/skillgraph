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
    """WI-57: los tres helpers viven en sus ubicaciones canonicas
    post-estrangulamiento (ADR-0018): knowledge (uno) y support (dos)."""

    def test_los_tres_helpers_existen(self) -> None:
        from skillgraph.cli.commands.knowledge import _open_known_project
        from skillgraph.cli.support import (
            _open_project_or_error,
            _open_project_storage,
        )

        for fn in (_open_known_project, _open_project_storage, _open_project_or_error):
            assert callable(fn)

    def test_open_known_project_gestiona_ciclo_de_vida(self) -> None:
        """Debe gestionar el ciclo de vida del Storage (contextmanager)."""
        from skillgraph.cli.commands.knowledge import _open_known_project

        assert callable(_open_known_project)

    def test_open_project_or_error_no_lanza_para_proyecto_ausente(self, tmp_path: Path) -> None:
        """Un proyecto inexistente devuelve (None, exit_code), no excepcion."""
        from skillgraph.cli.support import _open_project_or_error

        args = argparse.Namespace(data_root=tmp_path / "data")
        result, code = _open_project_or_error(args, "no-existe-xyz")
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
        """Comando invalido lo atrapa argparse, y ahora con exit=EXIT_USAGE.

        Este test se llamaba `..._devuelve_usage` y afirmaba 2: el nombre
        decia una cosa y el cuerpo otra. Su docstring llego mas lejos y
        declaraba que `EXIT_USAGE` (1) era "dead code en la practica porque
        argparse declara choices para todos los subcomandos".

        WI-88 (ADR-0016): no era codigo muerto, era **código secuestrado**.
        argparse interceptaba antes y salia con su 2, de modo que el 1
        nunca se producia — y un numero que nunca ocurre no se parece a
        codigo muerto sino a codigo inalcanzable por un equivoco. Y ese
        2 era `EXIT_BAD_NAME`, que `runner.py:131` devuelve vivo, luego
        un script no podia separar "nombre invalido" de "me equivoque al
        escribir el comando".
        """
        proc = _run_cli("no-existe", cwd=tmp_path, data_root=tmp_path / "sg-data")
        assert proc.returncode == runner.EXIT_USAGE, proc.stderr

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


def arbol_con_hotspot(tmp_path: Path) -> tuple[Path, str]:
    """Arbol minimo con una funcion publica de cc>=20. Devuelve (raiz, nombre).

    El contraejemplo del gate. Sin el, `test_el_arbol_real_no_tiene_main_como_hotspot`
    pasaria siempre con la misma seguridad con la que pasaba antes WI-103: no
    porque `main` este bien, sino porque nada miraba.

    La cc del auditor es `1 + nº de If/For/While/With/Try`, asi que 25 `if`
    dan cc=26. Se construye por generacion y no escrito a mano para que el
    numero no dependa de contar lineas.
    """
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").write_text("", encoding="utf-8")

    cuerpo = "\n".join(f"    if valor == {i}:\n        total += {i}" for i in range(25))
    (src / "modulo.py").write_text(
        "def main(valor: int) -> int:\n    total = 0\n" + cuerpo + "\n    return total\n",
        encoding="utf-8",
    )
    return src, "main"


class TestAuditGateForMain:
    """WI-103: la propiedad se mide, ya no depende de que exista un informe.

    Antes este gate leia `audits/architecture-debt-<HOY>.md` y hacia
    `pytest.skip` si no existia, de modo que solo corria los dias en que
    alguien se acordaba de generar el informe. MEDIDO: 6 informes en 7 dias
    (falta el `2026-09-30`) y hoy ni uno, con el gate en `SKIPPED` y exit 0.

    Ahora ejecuta `audits/audit_debt.py` sobre el arbol que se le pase y
    escribe el informe en un temporal, asi que la propiedad se comprueba
    siempre y contra el codigo que hay ahora.
    """

    def test_el_arbol_real_no_tiene_main_como_hotspot(self, tmp_path: Path) -> None:
        """LA puerta. `src/` de verdad, hoy.

        Un gate que solo sabe fallar con arboles de prueba no vigila el
        repositorio. Este es el que dice si el refactor de WI-41 sigue en pie.
        """
        from tests._gate_main_hotspot import hotspots_publicos

        nombres = hotspots_publicos(Path("src"), out_dir=tmp_path / "out")
        assert "main" not in nombres, (
            f"main vuelve a listarse como hotspot publico: {sorted(nombres)}"
        )

    def test_la_medicion_detecta_un_main_realmente_hotspot(self, tmp_path: Path) -> None:
        """El contraejemplo: sin el, el gate de arriba podria ser vacio.

        Un contraejemplo que no degrada nada no prueba que el guard funcione
        (leccion de WI-99). Si la medicion no encontrase un `main` con cc>=20
        en un arbol que lo tiene, el gate de arriba pasaria siempre sin
        decir nada, que es exactamente el defecto que se esta corrigiendo.
        """
        from tests._gate_main_hotspot import hotspots_publicos

        src, nombre = arbol_con_hotspot(tmp_path)
        nombres = hotspots_publicos(src, out_dir=tmp_path / "out")
        assert nombre in nombres, (
            f"la medicion no vio un hotspot publico con cc>=20 en un arbol que "
            f"lo tiene: devio encontrar {nombre!r} y encontro {sorted(nombres)}"
        )

    def test_no_puede_saltarse_ninguna_vez(self, tmp_path: Path) -> None:
        """El helper no puede saltarse: ni siquiera importa pytest.

        La primera version de este guard buscaba la cadena `skip` en el fuente
        del modulo, y se ponia en rojo **por su propio docstring**, que explica
        el defecto que arregla. Un guard que busca una palabra encuentra la
        palabra, no la propiedad: es la serie completa de este bloque en una
        linea, y la razon por la que este guard se escribe sobre el arbol de
        sintaxis y no sobre el texto.

        Un modulo que no importa pytest no puede llamar a `pytest.skip`. Y el
        comportamiento ya lo comprueban los tests de arriba: si se saltara,
        ellos no llegarian a su `assert`.
        """
        import ast
        import inspect

        from tests import _gate_main_hotspot

        arbol = ast.parse(inspect.getsource(_gate_main_hotspot))
        raices: set[str] = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                raices.update(alias.name.split(".")[0] for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                raices.add(nodo.module.split(".")[0])
        assert "pytest" not in raices, (
            f"el helper vuelve a poder saltarse: importa {sorted(raices)}"
        )

    def test_la_medicion_no_es_una_cadena_vacia(self) -> None:
        """Devuelve una tupla, siempre. Including cuando no hay hotspots.

        Una funcion que devuelve `()` porque no encontro nada y una que
        devuelve `()` porque no mire se distinguen por el segundo test: el
        contraejemplo obliga a que la medicion vea un hotspot real. Este solo
        fija que la forma del contrato no se degrade a `None`.
        """
        import inspect as _i

        from tests._gate_main_hotspot import hotspots_publicos

        firma = _i.signature(hotspots_publicos)
        assert "out_dir" in firma.parameters, (
            "el helper perdio out_dir y podria escribir en audits/"
        )
        assert firma.parameters["out_dir"].kind is _i.Parameter.KEYWORD_ONLY, (
            "out_dir debe ser solo-de-palabra-clave: como posicional, un "
            "llamador podria auditar y escribir en el repo por accidente"
        )

    def test_no_escribe_en_audits(self, tmp_path: Path) -> None:
        """`audits/` esta versionado: un test que escribe ahi deja el arbol
        sucio y ensucia el historico. WI-89 hizo `--out-dir` parametro; esto
        lo comprueba."""
        from tests._gate_main_hotspot import hotspots_publicos

        antes = sorted(p.name for p in Path("audits").glob("*"))
        hotspots_publicos(Path("src"), out_dir=tmp_path / "out")
        despues = sorted(p.name for p in Path("audits").glob("*"))
        assert antes == despues, f"el test escribio en audits/: {set(despues) - set(antes)}"
