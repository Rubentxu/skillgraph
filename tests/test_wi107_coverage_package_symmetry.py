"""WI-107: el suelo lo hereda el PAQUETE, pero el paquete seguia escrito a mano.

Por que existe este fichero
---------------------------
WI-94 cambio el contrato de cobertura de `AGENTS.md §6.3` de una lista de 21
modulos a un suelo **por paquete**, y el docstring del checker afirmaba con
razon:

    «Una sola fuente, sin lista que mantener, y por eso no se puede olvidar
     uno.»

Eso es falso, y este bloque mide exactamente en que punto se rompe. El
suelo paso a declararse por prefijo de paquete, pero el **conjunto de
prefijos** seguia siendo un diccionario escrito a mano
(`SUELOS_POR_PAQUETE`, ocho entradas). Un paquete nuevo que no estuviera en
esa lista no heredaba nada: `suelo_de()` devolvia `None` y `evaluar()` hacia
`continue` sin mirar el modulo.

Es el mismo fallo que WI-93 cerro para `runtime/` y WI-94 extends a los
ocho paquetes, un nivel mas arriba y sin cerrar: cambiar el eje de la
lista (modulos -> paquetes) no cambia su naturaleza.

Lo que se midio antes de tocar nada
-----------------------------------
Con `src/skillgraph/telepatia/` — un paquete nuevo con codigo que nadie
importa, anadido al indice de git para que ningun otro guard tenga nada
que decir — el **instrumento de produccion**:

    pytest                         2709 passed in 234.75s
    check_coverage_floors.py       exit 0, «todos los suelos se cumplen»
    coverage de oracular.py        0 %  (18 sentencias, 10 ramas, 0 cubiertas)
    suelo global                   94.85 % (fail_under = 80)

Que se declara en el camino, porque el camino descartado tambien es
evidencia: con el paquete **sin** versionar, `sg_build_sdist_no_versionado`
(WI-97) lo detectaba y la suite daba 1 failed. Ese guard lo ve, pero por
otra propiedad —el artefacto no puede llevar lo que git no versiona— y con
otro mensaje. Un paquete nuevo se versiona, asi que ese aviso no es el
contrato de §6.3: es otra puerta que se abre por casualidad. Este bloque
mide el caso real, con el paquete ya en el indice.

Que fijan estos tests
--------------------
La PROPIEDAD, sobre informes sinteticos con los que se puede hacer fallar
al checker. Un test que solo lee el informe real no distingue «el contrato
se cumple» de «el contrato no mira aqui».

El conjunto de paquetes sale del ARBOL (`iterdir()`), no de una lista: una
lista de obligatorios dentro de un guard es la misma lista, un nivel mas
abajo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_coverage_floors as cc  # noqa: E402

# Paquete que el arbol no tiene. La medicion de arriba lo creo, lo midio y
# lo borro; el guard tiene que seguir funcionando con un nombre que no
# existe, porque un paquete nuevo tampoco existe cuando se escribe el
# test que lo vigila.
FANTASMA = "src/skillgraph/telepatia/"

# Prefijo para un suelo declarado a mano que no tiene paquete detras. No
# puede existir en el arbol, que es justo lo que un contraejemplo necesita:
# uno que puede aparecer por si solo no prueba nada.
INEXISTENTE = "src/skillgraph/paquete_que_no_existe/"


# --- Informes sinteticos ---------------------------------------------------
# Misma forma que emite `coverage json`. La deconstruccion vive en
# test_wi94_coverage_contract_symmetry.py; aqui se repite a proposito en
# vez de importarse, para que este fichero siga siendo legible si WI-94
# se mueve.


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
            "percent_branches_covered": (
                100.0 * covered_branches / branches if branches else 100.0
            ),
            "percent_branches_covered_display": "",
        },
    }


def _mod(ruta: str, pct: float) -> dict[str, dict[str, Any]]:
    return {ruta: _entry(100, round(pct))}


def _base() -> dict[str, dict[str, Any]]:
    """Un arbol sano: un modulo por paquete, y los de las desviaciones.

    Sin esto, los paquetes que si se gobiernan aparecerian como «sin ningun
    modulo» —que es un fallo legitimo— y el ruido esconderia el fallo que
    este bloque quiere observar. Un fixture que dispara su propio ruido
    esconde el suyo. Los modulos de `EXCEPCIONES` van aparte porque se
    declaran por ruta, no por paquete, y un arbol que los tiene es lo
    unico contra lo que «lo declarado a mano existe» no se queja.
    """
    base = {f"{p}ok.py": _entry(100, 100) for p in _paquetes_del_arbol()}
    return {**base, **{ruta: _entry(100, 100) for ruta in cc.EXCEPCIONES}}


def _paquetes_del_arbol() -> tuple[str, ...]:
    """Prefijos `src/skillgraph/<paquete>/` que existen de verdad.

    Del ARBOL y no de `cc`: si se leyera del propio diccionario que se
    quiere vigilar, el test no distinguiria «todo paquete tiene suelo» de
    «todo paquete declarado tiene suelo», que es exactamente el fallo.
    """
    base = ROOT / "src" / "skillgraph"
    return tuple(
        sorted(
            f"src/skillgraph/{p.name}/"
            for p in base.iterdir()
            if p.is_dir() and p.name != "__pycache__" and any(p.rglob("*.py"))
        )
    )


def _fallos(files: dict[str, dict[str, Any]]) -> list[str]:
    _, fallos = cc.evaluar(files)
    return fallos


def _fallos_de(files: dict[str, dict[str, Any]], ruta: str) -> list[str]:
    """Solo los fallos que HABLAN de `ruta`.

    Un `assert fallos` a secas pasa en cuanto el contrato se queja de otra
    cosa, que es como un guard decorativo se camufla de test.
    """
    return [f for f in _fallos(files) if ruta in f]


# --- Predicados puros sobre §6.3 -----------------------------------------
#
# Se extraen del test a proposito, por la misma razon que WI-106 extrajo
# `_bump_valido`: un predicado que solo se llama con el valor de hoy no
# comprueba un dominio, comprueba una coincidencia. Un extractor de texto
# que solo se ha visto con la forma de §6.3 tampoco: hay que poder
# darle una entrada que NO sea la de §6.3 y ver que responde.


def _modulos_enumerados(seccion: str) -> tuple[str, ...]:
    """Nombres de modulo que la seccion enumera entre parentesis.

    Que se detecta una enumeracion de al menos TRES elementos separados por
    comas dentro de parentesis. El umbral no es arbitrario: con dos, un
    parentesis corriente («el CLI (`paths.py` y quien mas)») se contaria
    como enumeracion y el test seria inservible.

    El nombre se devuelve SIN extension porque §6.3 escribe los modulos sin
    ella, y la comprobacion de que exista como fichero la hace el llamador
    con `_existe_como_fichero`: son dos preguntas y por eso son dos
    predicados.
    """
    import re

    nombres: list[str] = []
    for grupo in re.findall(r"\(([^()]*)\)", seccion):
        partes = [p.strip() for p in grupo.replace("\n", " ").split(",")]
        if len(partes) < 3:
            continue
        # Una enumeracion de modulos son identificadores, no frases: si
        # alguno trae palabras sueltas, es prosa con parentesis.
        for parte in partes:
            if not re.fullmatch(r"`?[A-Za-z_][A-Za-z0-9_]*(?:\.py)?`?", parte):
                break
        else:
            nombres.extend(p.strip("`") for p in partes)
    return tuple(dict.fromkeys(nombres))


def _existe_como_fichero(nombre: str) -> bool:
    """¿`nombre` es un modulo `.py` real bajo `src/skillgraph/`?

    Un paquete NO cuenta: `runtime` es un directorio con doce modulos, y
    sigue sin que exista `runtime.py`. Es la distincion que hace §6.3
    cuando escribe «runtime» al lado de «handoff» como si fueran la misma
    clase de cosa.
    """
    base = ROOT / "src" / "skillgraph"
    return any(p.stem == nombre for p in base.rglob("*.py"))


# --- La asercion central ---------------------------------------------------


class TestTodoPaqueteTieneSuelo:
    def test_un_paquete_que_no_esta_en_ninguna_lista_hereda_suelo(self) -> None:
        """La asercion que manda. Antes de WI-107 esto devolvia `None`.

        `SUELOS_POR_PAQUETE` era un diccionario escrito a mano, asi que un
        paquete que no estuviera en el no heredaba nada. Este paquete no
        esta en ninguna parte: ni en el arbol, ni en ninguna lista. Y aun
        asi tiene que tener suelo, porque el suelo es la NORMA y las
        listas son las desviaciones.
        """
        ruta = f"{FANTASMA}oracular.py"
        assert cc.suelo_de(ruta) == 90.0, (
            "un paquete que no figura en ninguna lista no hereda suelo: "
            "vuelve la lista de paquetes escrita a mano, la que dejo sin "
            "vigilar a un paquete nuevo"
        )

    def test_un_modulo_al_cero_en_un_paquete_sin_declarar_falla(self) -> None:
        """La propiedad entera, no solo la resolucion del suelo.

        `suelo_de` podria acertar y `evaluar` seguir haciendo `continue`,
        que es como un contrato tiene la respuesta y no la usa.
        """
        ruta = f"{FANTASMA}oracular.py"
        files = {**_base(), **_mod(ruta, 0.0)}
        fallos = _fallos_de(files, ruta)
        assert fallos, (
            "el modulo nuevo al 0 % no produce ningun fallo que lo nombre. "
            f"El contrato no mira los paquetes que no declara. Fallos: {_fallos(files)}"
        )

    @pytest.mark.parametrize("prefijo", _paquetes_del_arbol())
    def test_todo_paquete_del_arbol_tiene_suelo(self, prefijo: str) -> None:
        """Ningun paquete que exista puede quedarse fuera, hoy ni mañana.

        El conjunto sale de `iterdir()` sobre el arbol, no de una lista: una
        lista de obligatorios aqui seria `SUELOS_POR_PAQUETE` con otro
        nombre y un piso mas abajo.
        """
        assert cc.suelo_de(f"{prefijo}cualquier.py") is not None, (
            f"{prefijo} es un paquete real del arbol y no hereda ningun suelo"
        )


# --- Los limites, que tambien hay que fijar --------------------------------


class TestLoQueElSueloPorDefectoNoGobierna:
    def test_la_raiz_del_paquete_no_cuelga_de_un_subdirectorio(self) -> None:
        """`src/skillgraph/__init__.py` no lo gobierna §6.3 y no debe exigirle nada.

        Con un suelo por defecto que alcance «todo lo que este bajo
        `src/skillgraph/`», el fichero de la raiz caeria dentro por
        accidente. Esta es la distincion que hace falta declarar: lo que
        cuelga de un SUBDIRECTORIO es un modulo de un paquete; la raiz es
        la raiz. Ademas esta en `omit` de coverage, asi que nunca aparece
        en el informe.
        """
        assert cc.suelo_de("src/skillgraph/__init__.py") is None

    def test_fuera_del_paquete_no_se_gobierna(self) -> None:
        assert cc.suelo_de("scripts/check_coverage_floors.py") is None
        assert cc.suelo_de("tests/test_wi107_coverage_package_symmetry.py") is None

    def test_un_modulo_vacio_se_excluye_sea_del_paquete_que_sea(self) -> None:
        """0 sentencias y 0 ramas: medirlo es division por cero."""
        files = {**_base(), f"{FANTASMA}__init__.py": _entry(0, 0)}
        assert not _fallos_de(files, f"{FANTASMA}__init__.py")


# --- Las desviaciones se siguen declarando una a una ----------------------


class TestLasDesviacionesSiguenDeclaradas:
    """El suelo por defecto no borra los datos: los mueve al sitio correcto."""

    def test_el_cli_conserva_su_70_por_ciento(self) -> None:
        """§6.3 exime al CLI, y el CLI es mas grande que el resto: aplicarle
        el 90 % por defecto lo haria incumplir el contrato a proposito."""
        assert cc.suelo_de("src/skillgraph/cli/runner.py") == 70.0

    def test_paths_py_conserva_su_suelo_propio(self) -> None:
        assert cc.suelo_de("src/skillgraph/platform/paths.py") == 60.0

    def test_la_excepcion_no_se_extiende_al_resto_de_su_paquete(self) -> None:
        assert cc.suelo_de("src/skillgraph/platform/storage.py") == 90.0

    def test_lo_declarado_a_mano_aporta_su_modulo(self) -> None:
        """La asercion que sustituye a la de WI-94, y con mas alcance.

        Antes vigilaba que los ocho paquetes declarados existieran. Ahora
        lo declarado a mano son DOS entradas (el CLI al 70 % y `paths.py`
        al 60 %), y son justo las que pueden quedarse obsoletas al borrar
        o renombrar lo que nombran. Con suelo por defecto, vigilar que
        existan los ocho era tautologico: se derivan del arbol.
        """
        fallos = _fallos(_base())
        assert not fallos, f"un suelo declarado a mano sin su modulo es un fallo: {fallos}"

    def test_un_prefijo_declarado_sin_modulo_es_fallo(self) -> None:
        """El contraejemplo: se declara un paquete que no existe.

        El nombre NO es `FANTASMA`. La primera version lo usaba, y el
        fallo lo destapo la medicion post-arreglo, no un test: con el
        paquete de la medicion presente en el arbol, `_base()` lo recogia
        como un modulo mas, el prefijoDeclared aportaba algo, y el test
        se ponia rojo. Es decir, afirmaba una propiedad que dependia del
        arbol sin decirlo —y un guard que depende del arbol sin decirlo no
        es un guard, es una coinidencia. Un contraejemplo tiene que ser
        incapable de aparecer por si solo.
        """
        cc.SUELOS_ESPECIALES[INEXISTENTE] = 50.0
        try:
            fallos = _fallos(_base())
        finally:
            del cc.SUELOS_ESPECIALES[INEXISTENTE]
        assert any(INEXISTENTE in f for f in fallos), (
            f"un suelo declarado a mano para un paquete que no aporta ningun "
            f"modulo pasa desapercibido. Fallos: {fallos}"
        )


# --- La segunda mitad: §6.3 enumeraba modulos que ya no estan ------------


class TestElDocNoEnumeraModulosQueNoExisten:
    """La lista de modulos de §6.3 era la misma lista escrita a mano, dos veces.

    §6.3 decia «modulos del core (errors, bricks, parser, registry, storage,
    runtime, handoff, agent, workflow, runcontroller)». Medido: **nueve de
    los diez** viven fuera de `core/`, y `runtime.py` **no existe** como
    fichero —hoy `runtime` es un paquete. Y nada lo comprobaba: un doc que
    nombra un fichero inexistente se lee igual que uno que no.
    """

    def _seccion_63(self) -> str:
        texto = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        inicio = texto.index("### 6.3")
        fin = texto.index("### 6.4", inicio)
        return texto[inicio:fin]

    def test_la_enumeracion_se_detecta_y_su_predicado_sabe_leerla(self) -> None:
        """PRIMERO el predicado, y con una entrada que se parezca a §6.3.

        Sin esto, los dos tests de abajo se alimentan de un extractor que
        nunca encuentra nada y pasan los dos: es el contraejemplo que pasa
        por la rama equivocada, y en WI-104 tres tests de ese tipo costaron
        una segunda vuelta de mutaciones. Aqui el texto de prueba esta
        escrito en la FORMA REAL de §6.3 —parentesis, comas, y los nombres
        SIN punto antes de la extension, que es como los escribe el doc—
        porque un extractor probado contra una forma que nadie escribe no
        prueba el extractor.
        """
        texto_real = (
            "- Módulos del core (errors, bricks, parser, registry, storage,\n"
            "  runtime, handoff, agent, workflow, runcontroller): ≥ 90%.\n"
        )
        assert _modulos_enumerados(texto_real) == (
            "errors",
            "bricks",
            "parser",
            "registry",
            "storage",
            "runtime",
            "handoff",
            "agent",
            "workflow",
            "runcontroller",
        ), "el extractor no lee la forma que §6.3 tiene de verdad"

    def test_el_predicado_de_fichero_distingue_paquete_de_modulo(self) -> None:
        """Y el segundo predicado, por la misma razon, sobre `runtime`.

        Es el caso medido: `runtime` sale de la enumeracion y `runtime.py`
        no existe, porque `runtime` es un paquete. Un extractor que
        devuelve el nombre no dice nada de si el nombre es un fichero.
        """
        assert not _existe_como_fichero("runtime"), (
            "runtime.py no deberia existir para que este test mida algo: si "
            "alguien lo crea, la enumeracion de §6.3 deja de ser falsa y el "
            "test pasa a medir otra cosa"
        )
        assert _existe_como_fichero("handoff"), (
            "handoff.py si existe: el predicado no puede decir que todo falta"
        )

    def test_la_seccion_63_no_enumera_modulos(self) -> None:
        """La propiedad, aplicada al doc real.

        Se admite `paths.py`, que es una excepcion real y un fichero real.
        """
        enumerados = _modulos_enumerados(self._seccion_63())
        assert not enumerados, (
            f"§6.3 sigue enumerando modulos: {list(enumerados)}. Con el suelo "
            "heredado del paquete esa enumeracion es una lista escrita a mano "
            "que puede quedarse vieja sin que nadie lo note, y ya esta vieja: "
            "«runtime» no es un modulo, es un paquete."
        )

    def test_la_seccion_63_declara_el_suelo_por_paquete(self) -> None:
        """La regla tiene que seguir declarando los tres numeros del contrato.

        Este test no mira el codigo: mira que el contrato normativo siga
        diciendo lo que dice. Un `§6.3` vacio cumple el test anterior y
        no dice nada, que es peor que mentir.
        """
        seccion = self._seccion_63()
        for numero in ("90", "70", "60"):
            assert numero in seccion, f"§6.3 ya no declara el suelo del {numero} %"
