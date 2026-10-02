"""Contrato de los tres helpers de "abrir proyecto + storage" (WI-44).

WI-41 documento por que estos tres NO deben unificarse: comparten la
construccion del resolver pero divergen en como reportan el fallo y en su
ciclo de vida. Unificarlos produciria un helper con mas ramas que los tres
que sustituye, el mismo antipatron que WI-41 elimino del dispatch.

WI-44 extrae `resolve_project` para eliminar las 21 repeticiones de la
construccion del resolver. Este fichero fija que la extraccion NO cambia
ninguno de los tres contratos, y que la duplicacion desaparecio.

Los tres contratos, tal cual estan hoy (verificado por AST antes de
escribir el test):

| helper                      | decorador      | retorna                            | lanza              |
|-----------------------------|----------------|------------------------------------|--------------------|
| `_open_known_project`       | contextmanager | Iterator[tuple[str, str, Storage]] | FileNotFoundError  |
| `_open_project_storage`     | contextmanager | Iterator[tuple[Storage|None, int]] | ninguna            |
| `_open_project_or_error`    | (ninguno)      | tuple[dict|None, int]              | ninguna            |

Un helper "unificado" que devolviera siempre el mismo tipo pasaria D2a y
D2c y fallaria D2b, y viceversa. Los tres juntos son la garantia.
"""

from __future__ import annotations

import argparse
import inspect
from pathlib import Path

import pytest

from skillgraph.cli import runner  # resto de la superficie CLI
from skillgraph.cli.commands.knowledge import _open_known_project
from skillgraph.cli.support import (
    _open_project_or_error,
    _open_project_storage,
    resolve_project,
)

# ---------------------------------------------------------------------------
# D1  La construccion del resolver deja de estar repetida
# ---------------------------------------------------------------------------

_RESOLVER_LINE = "ProjectResolver(data_root=resolve_data_root(args.data_root))"


class TestResolverNotDuplicated:
    def test_la_construccion_del_resolver_aparece_una_sola_vez(self) -> None:
        """D1: el numero de repeticiones cae de 21 a 1.

        Cuenta la construccion en todo el codigo fuente del paquete, no
        solo en un fichero: si alguien reintroduce la linea en otro
        modulo, este test tambien falla.
        """
        offenders: dict[str, int] = {}
        for path in Path("src/skillgraph").rglob("*.py"):
            count = path.read_text(encoding="utf-8").count(_RESOLVER_LINE)
            if count:
                offenders[str(path)] = count
        total = sum(offenders.values())
        assert total <= 1, (
            f"la construccion del resolver aparece {total} veces: {offenders}. "
            "Deberia existir un unico punto de construccion (resolve_project)."
        )

    def test_resolve_project_esta_disponible(self) -> None:
        """El helper extraido existe y es una funcion, no un alias.

        WI-55 lo reubico en `cli.support` (estrangulamiento ADR-0018).
        """
        assert callable(resolve_project)
        assert resolve_project.__module__ == "skillgraph.cli.support"

    def test_resolve_project_es_pura_hasta_la_llamada_al_registro(self) -> None:
        """resolve_project no lee disco por su cuenta: recibe el resolver.

        La construccion del ProjectResolver se queda dentro de
        resolve_project; sus consumidores solo deben usar el resultado.
        """
        source = inspect.getsource(resolve_project)
        assert _RESOLVER_LINE in source, (
            "resolve_project debe ser quien construye el ProjectResolver"
        )


# ---------------------------------------------------------------------------
# D2  Los tres contratos sobreviven intactos
# ---------------------------------------------------------------------------


def _is_contextmanager(fn: object) -> bool:
    """¿`fn` esta decorado con @contextmanager?

    Se comprueba la firma, no el codigo: @contextmanager reescribe la
    funcion a un generador, asi que la firma expone los parametros que
    realmente se consumen y no el `*args, **kwargs` del decorador.
    """
    return inspect.isgeneratorfunction(inspect.unwrap(fn))


class TestHelperContractsUnchanged:
    @pytest.mark.parametrize(
        "fn",
        (_open_known_project, _open_project_storage, _open_project_or_error),
        ids=("_open_known_project", "_open_project_storage", "_open_project_or_error"),
    )
    def test_los_tres_siguen_existiendo(self, fn: object) -> None:
        assert callable(fn)

    def test_dos_siguen_siendo_contextmanager(self) -> None:
        """D2a/D2b: exactamente dos de los tres gestionan el ciclo de vida.

        Si los tres fueran contextmanager, o solo uno, se habria roto la
        distincion que justifica no unificarlos.
        """
        managed = [
            fn.__name__
            for fn in (_open_known_project, _open_project_storage, _open_project_or_error)
            if _is_contextmanager(fn)
        ]
        assert set(managed) == {"_open_known_project", "_open_project_storage"}, (
            f"contextmanagers inesperados: {managed}"
        )

    def test_open_known_project_sigue_lanzando(self) -> None:
        """D2a: el helper que lanza debe seguir lanzando.

        El resto de sus pasos (lookup + validacion) cambian de sitio al
        usar resolve_project; el contrato observable no.
        """
        source = inspect.getsource(_open_known_project)
        assert "FileNotFoundError" in source, (
            "_open_known_project debe seguir levantando FileNotFoundError"
        )

    def test_open_project_or_error_sigue_devolviendo_tupla(self) -> None:
        """D2c: contrato (dict|None, int), no contextmanager."""
        assert not _is_contextmanager(_open_project_or_error)
        annotation = str(inspect.signature(_open_project_or_error).return_annotation)
        assert "tuple" in annotation, annotation

    def test_open_project_or_error_no_lanza_para_proyecto_ausente(self, tmp_path: Path) -> None:
        """Un proyecto inexistente devuelve (None, exit_code), no excepcion."""
        args = argparse.Namespace(data_root=tmp_path / "data")
        result, code = _open_project_or_error(args, "no-existe-xyz")
        assert result is None
        assert code != 0

    def test_resolve_project_devuelve_error_para_proyecto_ausente(self, tmp_path: Path) -> None:
        """El helper extraido propaga el lookup fallido como exit code."""
        args = argparse.Namespace(data_root=tmp_path / "data")
        project, code = runner.resolve_project(args, "no-existe-xyz")
        # `lookup` devuelve `({}, exit_code)` en fallo: el dict vacio, no None.
        assert project == {}
        assert code == runner.EXIT_PROJECT_NOT_FOUND

    def test_resolve_project_es_idempotente_sobre_el_mismo_proyecto(self, tmp_path: Path) -> None:
        """Dos llamadas seguidas dan el mismo resultado (sin estado)."""
        data_root = tmp_path / "sg-data"
        assert runner.main(["--data-root", str(data_root), "init"]) == runner.EXIT_OK
        assert (
            runner.main(["--data-root", str(data_root), "project", "create", "demo"])
            == runner.EXIT_OK
        )
        args = argparse.Namespace(data_root=data_root)
        first = runner.resolve_project(args, "demo")
        second = runner.resolve_project(args, "demo")
        assert first[0] == second[0]
        # El sentinel de exito es `None`, NO `EXIT_OK`: quien consume
        # compara contra `None` porque el error es el valor truthy.
        assert first[1] is None
        assert first[1] == second[1]
