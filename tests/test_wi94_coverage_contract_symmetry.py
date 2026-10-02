"""WI-94: el contrato de cobertura de AGENTS §6.3 solo se cumplia donde yo mire.

Por que este fichero existe
--------------------------
WI-93 hizo exigible el contrato de cobertura de `AGENTS.md §6.3` y lo
implemento con `scripts/check_coverage_floors.py`. La implementacion fue
correcta para lo queeltas, y **incorrecta en el resto**, por dos motivos que
este bloque midio:

  1. `SUELOS` era una **lista de modulos escrita a mano**, y la regla de
     «todo modulo de un paquete cubierto tiene suelo» solo se aplicaba a
     `runtime/`. Los otros siete paquetes (`core/`, `resources/`,
     `platform/`, `knowledge/`, `governance/`, `domain/`, `cli/`) no tenian
     ninguna: un modulo nuevo al 40 % en `governance/` no lo veria nadie.
     Es **el mismo fallo que WI-93 cerro para `runtime/`**, sin cerrar.

  2. `cli/` tenia suelo **agregado** (70 % sobre el paquete, que hoy mide
     86,91 %). La propia evidencia de WI-93 escribia, en su conocimiento
     negativo, que «la cobertura agregada puede tapar un modulo debil». Ese
     texto se aplico a `runtime/` y se paso por alto en `cli/`: 16,91 puntos
     de holgura, y un modulo de `cli/` podria caer al 0 % sin romper el
     contrato.

Que fijan estos tests
--------------------
No comprueban que el codigo de hoy mida X: comprueban la **propiedad** que
el contrato dice tener, sobre informes **sinteticos** con los que se puede
hacer fallar al checker. Un test que solo lee el informe real no distingue
«el contrato se cumple» de «el contrato no mira aqui».
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_coverage_floors as cc  # noqa: E402

# --- Construction de informes sinteticos -----------------------------------
# Se construye la MISMA forma que emite `coverage json`, para que el checker
# no pueda pasar por un atajo: si la aritmetica cambia, el fixture falla.


def _entry(
    stmts: int, covered: int, branches: int = 0, covered_branches: int = 0
) -> dict[str, Any]:
    return {
        "executed_lines": [],
        "excluded_lines": [],
        "missing_lines": list(range(covered + 1, stmts + 1)),
        "missing_branches": list(range(covered_branches + 1, branches + 1)),
        "executed_branches": [],
        "classes": {},
        "functions": {},
        "summary": {
            "covered_lines": covered,
            "num_statements": stmts,
            "percent_covered": 100.0 * covered / stmts if stmts else 100.0,
            "percent_covered_display": "",
            "missing_lines": stmts - covered,
            "excluded_lines": 0,
            "percent_statements_covered": 100.0 * covered / stmts if stmts else 100.0,
            "percent_statements_covered_display": "",
            "num_branches": branches,
            "num_partial_branches": 0,
            "covered_branches": covered_branches,
            "missing_branches": branches - covered_branches,
            "percent_branches_covered": 100.0 * covered_branches / branches if branches else 100.0,
            "percent_branches_covered_display": "",
        },
    }


def _modulo(ruta: str, pct: float) -> tuple[str, dict[str, Any]]:
    """Un modulo al `pct` de cobertura, con 100 statements."""
    covered = round(pct)
    return ruta, _entry(100, covered)


def _mod(ruta: str, pct: float) -> dict[str, dict[str, Any]]:
    """Como `_modulo`, pero ya como mapping, para poder hacer `**`."""
    return dict([_modulo(ruta, pct)])


def _informe(*pares: tuple[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return dict(pares)


def _base() -> dict[str, dict[str, Any]]:
    """Informe minimo pero REALISTA: un modulo sano por paquete declarado.

    Sin esto, un informe sintetico de un solo modulo haria que TODOS los
    demas paquetes declarados apareciesen como «sin ningun modulo», que es un
    fallo legitimo del contrato y no lo que el test quiere observar. Un
    fixture que dispara ruido propio esconde el fallo que apunta.
    """
    return {f"{prefijo}ok.py": _entry(100, 100) for prefijo in cc.SUELOS_POR_PAQUETE}


def _fallos(files: dict[str, dict[str, Any]]) -> list[str]:
    _, fallos = cc.evaluar(files)
    return fallos


def _fallos_de(files: dict[str, dict[str, Any]], ruta: str) -> list[str]:
    """Solo los fallos que HABLAN de `ruta`.

    Un `assert fallos` a secas pasa en cuanto el contrato se queja de
    cualquier otra cosa, que es como un guard decorativo se camufla de
    test.
    """
    return [f for f in _fallos(files) if ruta in f]


# --- La simetria que WI-93 no tenia ---------------------------------------


class TestTodoPaqueteCubiertoTieneSuelo:
    """La regla de `runtime/` era la correcta; el fallo era que era la unica."""

    def test_governance_hereda_suelo_y_no_depende_de_una_lista_manal(self) -> None:
        """Un modulo flojo en `governance/` se detecta sin estar en ninguna lista.

        Esta es la asercion central del bloque. Antes de WI-94, este informe
        pasaba: `governance` no estaba en la regla de «todo modulo tiene
        suelo», asi que un modulo al 10 % no era nadie asunto de nadie.
        """
        ruta = "src/skillgraph/governance/receipts.py"
        files = {**_base(), **_mod(ruta, 10.0)}
        fallos = _fallos_de(files, ruta)
        assert fallos, (
            "un modulo de governance/ al 10 % no lo detecta nadie: la regla de "
            f"simetria sigue siendo solo de runtime/. Fallos: {_fallos(files)}"
        )

    def test_knowledge_platform_y_domain_tambien(self) -> None:
        """El paquete no es el unico: la regla se aplica a todos los cubiertos."""
        for ruta in (
            "src/skillgraph/knowledge/graph.py",
            "src/skillgraph/platform/event_store.py",
            "src/skillgraph/domain/dsl.py",
            "src/skillgraph/resources/bricks.py",
            "src/skillgraph/core/errors.py",
        ):
            files = {**_base(), **_mod(ruta, 10.0)}
            fallos = _fallos_de(files, ruta)
            assert fallos, f"{ruta} al 10 % no produce ningun fallo que la nombre"

    def test_el_suelo_lo_hace_heredarlo_el_paquete_no_la_lista(self) -> None:
        """`suelo_de` resuelve por prefijo, sin mirar una lista de modulos."""
        assert cc.suelo_de("src/skillgraph/governance/backups.py") == 90.0
        assert cc.suelo_de("src/skillgraph/runtime/locks.py") == 90.0
        assert cc.suelo_de("src/skillgraph/cli/parser.py") == 70.0


class TestCliSeCompruebaPorModulo:
    """La asimetria que el propio WI-93 se contradijo al escribir."""

    def test_un_modulo_cli_al_20_se_detecta_aunque_el_agregado_este_al_95(self) -> None:
        """El agregado verde no absuelve a un modulo roto.

        Este es el caso exacto que la evidencia de WI-93 describia y que el
        checker no cubria: 11 modulos de `cli/` donde uno esta al 20 %.
        """
        ruta = "src/skillgraph/cli/commands/pack.py"
        sanos = {f"src/skillgraph/cli/cmd{i}.py": _entry(100, 100) for i in range(9)}
        files = {**_base(), **sanos, **_mod(ruta, 20.0)}
        fallos = _fallos_de(files, ruta)
        assert fallos, (
            "el agregado de cli/ puede seguir verde con un modulo al 20 %, y "
            f"eso es exactamente lo que §6.3 no dice. Fallos: {_fallos(files)}"
        )

    def test_el_agregado_de_cli_sigue_comprobandose(self) -> None:
        """Quitar el agregado no es el arreglo: se comprueba de las dos formas."""
        assert "src/skillgraph/cli/" in cc.SUELOS_AGGREGADOS


class TestExcepcionDePaths:
    """`paths.py` tiene su propio suelo en §6.3, y una excepcion se declara."""

    def test_paths_py_conserva_su_suelo_propio(self) -> None:
        assert cc.suelo_de("src/skillgraph/platform/paths.py") == 60.0

    def test_paths_py_al_80_pasa_porque_el_63_le_da_60(self) -> None:
        """`paths.py` al 80 % NO es un incumplimiento: su suelo es 60 %, no 90 %.

        Sin la excepcion, `platform/` a 90 % haria fallar al unico modulo que
        §6.3 exime explicitamente, y el contrato estaria mintiendo sobre si
        mismo.
        """
        files = {**_base(), **_mod("src/skillgraph/platform/paths.py", 80.0)}
        assert not _fallos(files), "paths.py tiene suelo propio del 60 % en §6.3"

    def test_paths_py_por_debajo_de_60_si_falla(self) -> None:
        ruta = "src/skillgraph/platform/paths.py"
        files = {**_base(), **_mod(ruta, 50.0)}
        assert _fallos_de(files, ruta)

    def test_la_excepcion_no_se_extiende_al_resto_de_platform(self) -> None:
        assert cc.suelo_de("src/skillgraph/platform/storage.py") == 90.0


# --- Los limites que el contrato tiene que tener --------------------------


class TestLimitesDelContrato:
    def test_modulo_fuera_de_todo_paquete_gobiernado_se_ignora(self) -> None:
        """`__init__.py` de la raiz no lo gobierna §6.3 y no debe exigirle nada."""
        ruta = "src/skillgraph/__init__.py"
        files = {**_base(), **_mod(ruta, 50.0)}
        assert not _fallos_de(files, ruta), "un modulo que §6.3 no nombra no puede incumplirlo"

    def test_modulo_vacio_se_excluye(self) -> None:
        """0 sentencias y 0 ramas: medirlo es division por cero."""
        ruta = "src/skillgraph/governance/__init__.py"
        files = {**_base(), ruta: _entry(0, 0)}
        assert not _fallos_de(files, ruta), "un fichero vacio no puede incumplir un suelo"

    def test_paquete_cubierto_sin_modulos_en_el_informe_es_fallo(self) -> None:
        """Un paquete declarado que desaparece del informe no se ignora en silencio.

        Con suelos por lista a mano, un modulo fantasma era detectable porque
        la lista lo nombraba. Con suelos por prefijo desaparece esa via, y
        esta asercion es la que la sustituye: si `governance/` no aporta ni
        un modulo, o se borro o se renombro, y hay que enterarse.
        """
        files = {f: e for f, e in _base().items() if not f.startswith("src/skillgraph/governance/")}
        fallos = _fallos(files)
        assert any("governance/" in f for f in fallos), (
            f"un paquete declarado sin ningun modulo pasa desapercibido. Fallos: {fallos}"
        )

    def test_el_suelo_global_se_sigue_comprobando(self) -> None:
        assert cc.SUELO_GLOBAL == 80.0
        files = _informe(_modulo("src/skillgraph/runtime/locks.py", 10.0))
        assert any("global" in f for f in _fallos(files))


# --- Los floors declarados existen de verdad -------------------------------


class TestSuelosDeclaradosSonReales:
    """Un suelo sobre un paquete que no existe es una regla sobre la nada."""

    @pytest.mark.parametrize("prefijo", sorted(cc.SUELOS_POR_PAQUETE))
    def test_cada_paquete_declarado_tiene_modulos_de_verdad(self, prefijo: str) -> None:
        """El prefijo existe en el ARBOL, no en el informe de cobertura.

        Lee el sistema de ficheros y no `coverage json` a proposito, y no por
        comodidad. La primera version de este test leia el informe, y
        fallo en la CI con 9 rojos: durante la ejecucion de pytest los datos
        de cobertura estan todavia en `.coverage.parallel.*` sin combinar, y
        `coverage json` responde «No data to report». Es decir, el test
        dependia de un artefacto que pytest produce DESPUES de correr, y se
        daba por bueno en local unicamente porque aqui ya habia un
        `scripts/coverage.sh` anterior que habia combinado los datos.

        Que un paquete tenga modulos es una propiedad del codigo fuente, no
        de la medicion. Preguntarselo al informe era medir en el sitio
        equivocado, que es como nacen los numeros que confirman cualquier
        premisa.
        """
        ruta = ROOT / prefijo
        assert ruta.is_dir(), f"{prefijo} tiene suelo declarado pero no es un directorio"
        assert any(ruta.rglob("*.py")), f"{prefijo} tiene suelo declarado pero ningun modulo .py"

    def test_no_ay_manos_dos_listas_que_se_puedan_desincronizar(self) -> None:
        """La lista de modulos desaparecio; el contrato vive en una sola fuente."""
        assert not hasattr(cc, "SUELOS"), (
            "vuelve la lista de modulos escrita a mano: es la fuente que se "
            "desincroniza del codigo y la que dejo siete paquetes sin vigilar"
        )


# --- Lo que este fichero NO comprueba, y por que ---------------------------
#
# Una version anterior de este modulo terminaba con
# `test_el_informe_real_no_tiene_infracciones`, que ejecutaba el contrato
# contra el informe de cobertura real. Se ha eliminado a proposito, y el
# borrado es la decision, no una falta:
#
#   * Es CIRCULAR. `scripts/coverage.sh` corre pytest y DESPUES hace
#     `coverage combine`. Un test que necesita el informe combinado para
#     pasar no puede vivir dentro del pytest que lo produce.
#   * Es REDUNDANTE. La garantia «el arbol real cumple el contrato» ya la
#     da `scripts/check_coverage_floors.py`, que corre en el stage
#     `coverage-floors` de `.pipeline.kts`, en su propia pasada y con el
#     informe ya combinado. Ese stage es el sitio correcto para comprobar
#     una propiedad de la medicion: despues de la medicion.
#
# Lo que si queda aqui es la PROPIEDAD del contrato, comprobable con informes
# sinteticos en cualquier orden y sin depender de que nadie haya medido antes.
