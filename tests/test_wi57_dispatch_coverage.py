"""Red de contrato WI-57: la tabla de dispatch cubre TODO lo que declara el parser.

Hallazgo de la investigacion retrospectiva del ciclo WI-52..WI-55:
`main` degrada a `print_help()` + `EXIT_USAGE` (fallback silencioso)
cuando `_resolve_handler` devuelve None, y NINGUN test fijaba que la
tabla `_DISPATCH`/`_SUBCOMMAND_OF` cubre todos los comandos que
`build_parser` declara. Un typo al mover un handler habria roto un
subcomando entero sin fallar ni un solo gate.

Esta red camina el arbol REAL del parser (acciones `_SubParsersAction`,
incluido el `dest` de cada subparsers anidado) y afirma la
correspondencia exacta en ambos sentidos, con los dos estilos legitimos
de despacho (WI-41):

- TABLE-NESTED: clave `(command, sub)` en `_DISPATCH` y
  `_SUBCOMMAND_OF[command] == dest` del subparsers anidado.
- FLAT-ROUTER: `_SUBCOMMAND_OF[command] is None` y handler plano
  `command` en `_DISPATCH` que enruta sus subs internamente.

Excepcion documentada (as-built, no cambiar sin ADR): `backup`
declara subparsers con dest='backup_command' pero se despacha
FLAT-ROUTER via `cmd_backup`, que lee `args.backup_command`. La red
lo acepta y caza cualquier OTRO comando que mezcle estilos.
"""

from __future__ import annotations

import argparse

import pytest

from skillgraph.cli import runner
from skillgraph.cli.parser import build_parser

# Unico FLAT-ROUTER con subparsers anidados declarados (as-built).
_FLAT_ROUTER_WITH_NESTED_PARSER = frozenset({"backup"})


def _subparsers_of(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            return a
    return None


def _declared_routes() -> dict[str, tuple[str | None, dict[str, None]]]:
    """command -> (dest del subparsers anidado o None, {subs declarados})."""
    top = _subparsers_of(build_parser())
    assert top is not None, "build_parser no declara subcomandos"
    declared: dict[str, tuple[str | None, dict[str, None]]] = {}
    for command, sub in top.choices.items():
        nested = _subparsers_of(sub)
        declared[command] = (
            nested.dest if nested else None,
            dict.fromkeys(nested.choices) if nested else {},
        )
    return declared


def _is_table_nested(command: str) -> bool:
    return any(isinstance(key, tuple) and key[0] == command for key in runner._DISPATCH)


class TestDispatchCoversParser:
    def test_every_declared_route_has_legal_dispatch(self) -> None:
        missing: list[str] = []
        for command, (dest, subs) in _declared_routes().items():
            if not subs:
                assert command in runner._DISPATCH, f"sin handler para {command!r}"
                continue
            if dest is None:
                # FLAT-ROUTER puro: handler plano sin subparsers anidados.
                assert command in runner._DISPATCH, f"router {command!r} ausente"
                continue
            if command in _FLAT_ROUTER_WITH_NESTED_PARSER:
                assert command in runner._DISPATCH, f"router {command!r} ausente de _DISPATCH"
                continue
            assert runner._SUBCOMMAND_OF.get(command) == dest, (
                f"{command!r}: dest del parser={dest!r} != _SUBCOMMAND_OF="
                f"{runner._SUBCOMMAND_OF.get(command)!r}"
            )
            for sub in subs:
                if (command, sub) not in runner._DISPATCH:
                    missing.append(f"{command} {sub}")
        assert not missing, f"rutas declaradas sin handler: {missing}"

    def test_dispatch_has_no_phantom_routes(self) -> None:
        declared = _declared_routes()
        phantom: list[str] = []
        for key in runner._DISPATCH:
            command, sub = key if isinstance(key, tuple) else (key, None)
            dest, subs = declared.get(command, (None, {}))
            if command not in declared:
                phantom.append(f"{command!r} no declarado")
            elif sub is not None and sub not in subs:
                phantom.append(f"{command} {sub!r} no declarado (dest={dest!r})")
        assert not phantom, f"rutas fantasma en _DISPATCH: {phantom}"

    def test_every_handler_is_callable(self) -> None:
        for key, handler in runner._DISPATCH.items():
            assert callable(handler), f"handler de {key!r} no es invocable"

    def test_routing_style_matches_parser_shape(self) -> None:
        """TABLE-NESTED exige dest en `_SUBCOMMAND_OF`; FLAT-ROUTER, None."""
        for command, (dest, subs) in _declared_routes().items():
            if not subs:
                continue
            attribute = runner._SUBCOMMAND_OF.get(command)
            if dest is None or command in _FLAT_ROUTER_WITH_NESTED_PARSER:
                assert attribute in (None, dest), (
                    f"{command!r}: atributo {attribute!r} inconsistente con dest={dest!r}"
                )
            else:
                assert attribute == dest, (
                    f"{command!r}: _SUBCOMMAND_OF={attribute!r} != dest={dest!r}"
                )


def test_unknown_subcommand_of_table_nested_is_argparse_usage() -> None:
    """Caso contrafactual: SUB desconocido de un comando TABLE-NESTED.

    argparse valida los choices y aborta ANTES de llegar a
    `_resolve_handler`. WI-88 (ADR-0016): antes abortaba con SystemExit(2),
    y el nombre de este test ya decia "usage" mientras el cuerpo afirmaba
    2 — el mismo patron que se corrigio en test_wi41_cli_dispatch.py.

    Antes el docstring sostenia que el fallback de EXIT_USAGE "aplica a
    comandos flat sin handler, nunca a subs desconocidos". Tras ADR-0016
    los dos caminos devuelven EXIT_USAGE, luego ya no se distinguen, y esa
    era justo la prueba de que el 1 no se producia nunca.
    """
    with pytest.raises(SystemExit) as excinfo:
        runner.main(["runs", "bogus-sub"])
    assert excinfo.value.code == runner.EXIT_USAGE
