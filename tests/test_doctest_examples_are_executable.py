"""El ejemplo del docstring del builder "se puede ejecutar", y NADIE
lo ejecuta.

`AGENTS.md §3.2` punto 7 dice: «Docstring con ejemplo: el `__init__` del
builder debe incluir un ejemplo en formato doctest **que se pueda
ejecutar**».

**POR QUE ESTE FICHERO NO LLEVA NUMERO DE WORKITEM.** Se escribio como
WI-116, que fue el workitem siguiente a WI-115 y el ultimo de la serie
abierta «qué declara el repo que nada comprueba». B0 cerro esa serie: los
workitems ya no se numeran, se responden con el nombre de la propiedad.
Un guard cuyo nombre es un numero caduca con el contador, y este mide una
declaracion permanente de `AGENTS.md` —esta, si, permanente.

El ejemplo existe (`src/skillgraph/domain/dsl.py`) y HOY es cierto. Eso no
es la propiedad: la propiedad es que si dejara de serlo, algo se pusiera
rojo. MEDIDO que no lo hacia (`.pipelinek/wi116_measure.py`, restauracion
byte a byte):

    docstrings con `>>>` en src/    : 1  (PlanBuilder)
    ficheros que mencionan doctest : 0

    M1  docstring con un >>> que MIENTE         : rc=0  VERDE (NO LO VE)
        el doctest de verdad, invocado a mano   : rc=1  ROJO
    M2  el ejemplo invoca un metodo inexistente : rc=0  VERDE (NO LO VE)

La segunda linea de M1 es el nucleo: **la comprobacion correcta ya existe
en el repo** —`doctest` la detecta— y lo que falta es conectarla a algo.

**EL CONJUNTO VIENE DEL ARBOL, NO DE UNA LISTA.** Una enumeracion de «los
modulos con ejemplo» seria una fuente de verdad mas que hay que mantener a
mano, y se quedaria vieja en silencio el dia que alguien anadiera un
ejemplo en un modulo que nadie escribio en la lista. Aqui se recorre
`src/` entero por AST, y todo ejemplo que aparezca queda cubierto sin
tocar este fichero.

**LOS DOS LADOS TIENEN QUE COINCIDIR.** Un guard que solo ejecutara lo
que `doctest` encuentra no veria un ejemplo que el parser hubiera
descartado en silencio: compararia contra su propia copia y pasaria en
verde (el error de WI-106). Por eso se mide tambien que los `>>>` que ve
el AST sean los mismos que los ejemplos que encuentra `doctest`.
"""

from __future__ import annotations

import ast
import doctest
import importlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

# El punto de contrato que `AGENTS.md §3.2` nombra de forma explicita al
# hablar de este DSL («Ver `skillgraph.dsl.PlanBuilder` como referencia»).
# Nombrar un contrato NO es enumerar el conjunto: el conjunto de ejemplos
# que se ejecutan sigue saliendo del arbol, aqui. Lo que este par
# comprueba es que el builder siga TENIENDO ejemplo, porque un guard
# generico («al menos un ejemplo en el arbol») pasaria en verde si
# borraran el de `PlanBuilder` y anadieran otro en cualquier otro sitio.
DSL = "skillgraph.domain.dsl"
BUILDER = "PlanBuilder"

_MARCA = re.compile(r"^[ \t]*>>>", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Ejemplo:
    """Un `>>>` declarado en un docstring, y donde vive."""

    modulo: str
    ruta: str
    linea: int
    calificada: str
    cuenta: int

    def donde(self) -> str:
        """Como se le diria a alguien a quien le toca arreglarlo."""
        return f"{self.ruta}:{self.linea}  ({self.calificada})"


def _modulo_de(ruta: Path) -> str:
    """`src/skillgraph/domain/dsl.py` -> `skillgraph.domain.dsl`."""
    partes = list(ruta.relative_to(RAIZ / "src").with_suffix("").parts)
    if partes[-1] == "__init__":
        partes.pop()
    return ".".join(partes)


def _docstrings(nodo: ast.AST, calificada: str) -> Iterator[tuple[str, ast.AST, str]]:
    """Recorre el cuerpo, no el texto.

    Se busca en el AST porque la propiedad es «este codigo DECLARA un
    ejemplo». Un docstring que mencione `>>>` en prosa no declara nada, y
    un ejemplo puede estar escrito de formas que un grep encontrarian a la
    primera y a la segunda no.
    """
    for hijo in getattr(nodo, "body", []):
        if isinstance(hijo, ast.ClassDef):
            doc = ast.get_docstring(hijo, clean=False)
            nombre = f"{calificada}.{hijo.name}"
            if doc:
                yield nombre, hijo, doc
            yield from _docstrings(hijo, nombre)
        elif isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(hijo, clean=False)
            if doc:
                yield f"{calificada}.{hijo.name}", hijo, doc


def _inventario() -> tuple[Ejemplo, ...]:
    """Todos los docstrings de `src/` que declaran un ejemplo.

    Se deriva del ARBOL en cada llamada. Son unos 90 ficheros y el parseo
    es de microsegundos: cachearlo anadiria estado por una ganancia que no
    existe, y el estado es justo lo que este bloque vigila.
    """
    salida: list[Ejemplo] = []
    for ruta in sorted(SRC.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        modulo = _modulo_de(ruta)
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        doc_modulo = ast.get_docstring(arbol, clean=False)
        if doc_modulo and _MARCA.search(doc_modulo):
            salida.append(
                Ejemplo(
                    modulo,
                    str(ruta.relative_to(RAIZ)),
                    1,
                    modulo,
                    len(_MARCA.findall(doc_modulo)),
                )
            )
        for calificada, nodo, doc in _docstrings(arbol, modulo):
            marcas = _MARCA.findall(doc)
            if marcas:
                salida.append(
                    Ejemplo(
                        modulo,
                        str(ruta.relative_to(RAIZ)),
                        nodo.body[0].lineno,
                        calificada,
                        len(marcas),
                    )
                )
    return tuple(salida)


def _describir(ejemplo: Ejemplo, fuente: str, obtenido: str, esperado: str) -> str:
    """EL mensaje de fallo. Un solo sitio, y el codigo de produccion lo usa.

    Si el formateador estuviera duplicado (una copia para el guard y otra
    para su propio test), el test verificaria la copia y no el camino que
    se ejecuta: es el error de WI-106 aplicado a un mensaje de error.
    """
    return (
        f"{ejemplo.donde()}: el ejemplo `{fuente}` devolvió {obtenido!r} "
        f"y el docstring dice {esperado!r}"
    )


def _pruebas_de(modulo: str) -> list[doctest.DocTest]:
    mod = importlib.import_module(modulo)
    return [t for t in doctest.DocTestFinder().find(mod, modulo) if t.examples]


class _Grabador(doctest.DocTestRunner):
    """Runner que SE APAGA y anota los fallos.

    Dos cosas que se glean de medir, no de suponer:

    - `DocTestRunner.failures` es un CONTADOR, no una lista. La lista de
      fallos no existe en ningun sitio: no hay de donde leerla.
    - `__init__` no acepta `report=` en 3.13. El punto de extension
      documentado es `report_failure`, que ademas recibe exactamente lo
      que hace falta para nombrar el sitio: el test, el ejemplo y lo que
      salio.

    Sin heredar de aqui, el runner imprimiria su informe en `stdout` y el
    mensaje de este guard seria el segundo, no el primero.
    """

    def __init__(self) -> None:
        super().__init__(verbose=False)
        self.vistos: list[tuple[doctest.DocTest, doctest.Example, str]] = []

    def report_failure(
        self, out: object, test: doctest.DocTest, example: doctest.Example, got: str
    ) -> None:
        self.vistos.append((test, example, got))


def _silencio(texto: str) -> None:
    """Enrollable: el informe del runner no va a `stdout`."""


def _ejecutar(inventario: tuple[Ejemplo, ...]) -> list[str]:
    """Ejecuta los ejemplos declarados y devuelve los fallos, con sitio."""
    por_calificada = {e.calificada: e for e in inventario}
    runner = _Grabador()
    fallos: list[str] = []
    for modulo in dict.fromkeys(e.modulo for e in inventario):
        for prueba in _pruebas_de(modulo):
            runner.vistos.clear()
            runner.run(prueba, out=_silencio)
            for prueba_fallada, ejemplo, obtenido in runner.vistos:
                declarado = por_calificada.get(prueba_fallada.name)
                if declarado is None:  # pragma: no cover - no deberia ocurrir
                    pytest.fail(
                        f"doctest ha ejecutado un ejemplo en {prueba_fallada.name} "
                        f"que el AST no declaro. Sin su ficha no se puede decir "
                        f"donde esta: el guard no puede fallar a medias."
                    )
                # `test.lineno` es la linea del docstring y `example.lineno`
                # va desde 1 dentro de el: las dos cuentan esa misma linea.
                linea = declarado.linea + ejemplo.lineno - 1
                fallo = Ejemplo(declarado.modulo, declarado.ruta, linea, declarado.calificada, 0)
                fallos.append(
                    _describir(
                        fallo, ejemplo.source.strip(), obtenido.strip(), ejemplo.want.strip()
                    )
                )
    return fallos


class TestElEjemploDelDocstringEsUnContrato:
    def test_todo_ejemplo_del_arbol_se_ejecuta_y_pasa(self) -> None:
        """La propiedad, tal y como la declara `AGENTS.md §3.2.7`.

        Cubre el arbol entero, no solo el ejemplo que hay hoy: un ejemplo
        nuevo en cualquier modulo queda vigilado sin editar este test.
        """
        fallos = _ejecutar(_inventario())
        assert not fallos, (
            f"hay {len(fallos)} ejemplo(s) de docstring que ya no son ciertos:\n"
            + "\n".join(f"  - {f}" for f in fallos)
            + "\n\nUn ejemplo que miente es prosa, no documentacion. O se "
            "arregla el ejemplo, o se arregla el codigo que documenta."
        )

    def test_el_fallo_dice_el_fichero_la_linea_y_el_esperado(self) -> None:
        """Sin esto, el fallo anterior no dice ni donde ni que.

        Se comprueba sobre un fallo FABRICADO: un mensaje de error que
        solo se verifica cuando el repo ya se rompio no vigila nada.
        """
        declarado = Ejemplo("m", "src/skillgraph/domain/dsl.py", 100, "m.PlanBuilder", 2)
        texto = _describir(declarado, "p.initial == 'a'", "False", "True")
        assert "src/skillgraph/domain/dsl.py:100" in texto
        assert "PlanBuilder" in texto
        assert "'False'" in texto and "'True'" in texto

    def test_el_arbol_declara_al_menos_un_ejemplo_ejecutable(self) -> None:
        """El otro lado de §3.2.7: que el ejemplo EXISTA.

        Sin este contrasalto, borrar el ejemplo entero dejaria los otros
        tests en verde —no habria nada que ejecutar y nada que fallar— y
        la viñeta pasaria sin cumplir. Es el error de WI-109 repetido: un
        guard que solo sabe pasar no esta probado.
        """
        inventario = _inventario()
        assert inventario, (
            "AGENTS.md §3.2.7 exige que el builder del DSL documente su API "
            "con un ejemplo ejecutable, y el arbol no declara ninguno. Si el "
            "ejemplo se borro, esta es la linea que lo dice."
        )
        assert sum(e.cuenta for e in inventario) > 0

    def test_lo_que_encuentra_doctest_es_lo_que_ve_el_arbol(self) -> None:
        """El contrasalto del cero silencioso.

        `doctest` podria descartar un ejemplo mal formado y devolver cero
        sin decirlo. Si aqui solo se ejecutara lo que `doctest` encuentra,
        ese cero pasaria por «todo correcto». Por eso los dos lados tienen
        que coincidir: si dejan, el guard compara contra su propia copia.
        """
        inventario = _inventario()
        declarados = sum(e.cuenta for e in inventario)
        encontrados = sum(
            len(t.examples)
            for m in dict.fromkeys(e.modulo for e in inventario)
            for t in _pruebas_de(m)
        )
        assert declarados == encontrados, (
            f"el AST declara {declarados} lineas `>>>` y `doctest` encuentra "
            f"{encontrados} ejemplos. Si no coinciden, `doctest` esta "
            "descartando un ejemplo en silencio y el guard de arriba no lo "
            "estaria mirando. Arregla el docstring, no este test."
        )


class TestElBuilderDelDslEstaDocumentado:
    """El contrato con nombre, para el agujero que el guard generico deja.

    Los tests de arriba derivan el conjunto del arbol, y por eso pasan en
    verde si BORRAN el ejemplo de `PlanBuilder` y anaden uno en cualquier
    otro modulo. Este test ata el contrato al builder que `AGENTS.md §3.2`
    nombra, que es lo que §3.2.7 protege.
    """

    def test_el_modulo_del_dsl_se_importa(self) -> None:
        """Si el modulo se renombro, el contrato se rompio de verdad.

        Sin esta separacion, un renombrado daria un `ModuleNotFoundError`
        que parece un fallo del guard en vez de un contrato incumplido.
        """
        try:
            importlib.import_module(DSL)
        except ModuleNotFoundError as exc:  # pragma: no cover
            pytest.fail(
                f"`AGENTS.md §3.2` declara que este DSL vive en "
                f"`{DSL}` y ya no se puede importar ({exc}). O el modulo se "
                "renombro y el contrato hay que moverlo, o se borro."
            )

    def test_el_builder_del_dsl_tiene_un_ejemplo_ejecutable(self) -> None:
        objetivo = f"{DSL}.{BUILDER}"
        con_ejemplo = [e for e in _inventario() if e.calificada == objetivo]
        assert con_ejemplo, (
            f"`AGENTS.md §3.2.7` exige que el builder del DSL documente su API "
            f"con un ejemplo en formato doctest, y `{objetivo}` no tiene "
            "ninguno. Los demas tests seguirian en verde si anadirieras un "
            "ejemplo en otro modulo: por eso este existe."
        )
        fallos = _ejecutar(tuple(con_ejemplo))
        assert not fallos, "\n".join(fallos)
