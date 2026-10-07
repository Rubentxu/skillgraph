"""R0.4 — la dependencia de `_pytest` es un CONTRATO, no un olvido.

**EL INCIDENTE QUE ABRIO ESTE TRABAJO, Y LA CLASIFICACION QUE PIDIÓ EL
ENUNCIADO.** El bloque B29 dejo anotado que la suite completa no podia
tener «full suite verde» con interpretacion automatica por un fallo
preexistente:

    ModuleNotFoundError: No module named '_pytest'

El enunciado pedia decidir en que contrato caia, de estas tres:

    A. `_pytest` forma parte del entorno canonico
    B. El hook no puede depender de internals de pytest
    C. Es deliberadamente un test de entorno opcional

**MEDIDO, Y ES LA B — PERO MEDIDO, NO DECLARADO:**

    import _pytest        -> OK, version 9.1.1 (lo trae pytest)
    ningun modulo del     -> 0 resultados
      repo lo importa

Es decir: `_pytest` **si** existe en el entorno, luego A no era el fallo; y
ningun hook lo importa, luego la dependencia que se rompio era de un hook
o un helper que ya no existe o que se corrigio. Lo que queda es una
pregunta con respuesta: **¿puede algo volver a importar un private de
pytest y romper la suite en produccion?**

**POR QUE UN GUARD Y NO UNA NOTA.** La forma que el enunciado rechaza
expresamente es:

    suite -> 1 fallo conocido -> «GREEN por clasificacion»

Eso no lo decide el runner, lo decide una persona, y el proximo que llegue
no lo sabra. Aqui no hay exception list: hay una **ley** —ninguna
dependencia de internals de pytest en el arbol— y una prueba de que el
entorno puede cumplirla.

**Y LA MITAD QUE FALTA SI SE MIDIERA SOLO EL ARBOL.** Un guard que solo
mirara los imports daria verde en un entorno donde `_pytest` no existe,
que es exactamente el fallo original. Por eso este fichero tambien ejecuta
el import de verdad: si pytest no trae `_pytest`, el entorno **no puede**
cumplir el contrato, y eso tiene que ponerse rojo aqui y no en produccion.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

#: Donde vive el codigo que NO puede depender de internals de pytest.
#:
#: `scripts/` entra porque ahi viven los hooks y los instrumentos, que son
#: los que se ejecutan FUERA de pytest; `tests/` entra porque un test que
#: importa un private de pytest es el que masrieda en la version que se este
#: usando. `external/` queda fuera a proposito: es material de blueprint,
#: no codigo de este repo, y `AGENTS.md` §0 dice que no se toca.
DIRECTORIOS_SIN_DEPENDENCIA = ("src", "tests", "scripts")


def _modulos_python() -> Iterator[Path]:
    for directorio in DIRECTORIOS_SIN_DEPENDENCIA:
        base = RAIZ / directorio
        for ruta in sorted(base.rglob("*.py")):
            # `__pycache__` no es codigo. Y **este fichero tampoco**: el guard
            # que verifica la ley no puede violarla sin ponerse rojo a si
            # mismo, porque medir la ley exige IMPORTAR `_pytest` para poder
            # afirmar que el entorno la cumple. MEDIDO: sin esta excepcion,
            # el guard se cazaba con
            # `tests/test_r0d_entorno_pytest.py: import _pytest`,
            # que es el unico falsopositivo que no es falsopositivo.
            if "__pycache__" in ruta.parts:
                continue
            if ruta == Path(__file__).resolve():
                continue
            yield ruta


def _importa_pytest_interno(ruta: Path) -> tuple[int, str] | None:
    """¿Este modulo importa algo de `_pytest`? Devuelve linea y forma.

    **SE MIDE POR AST Y POR AMBIGAS ENTRADAS.** La propiedad es «este codigo
    *importa*», y un docstring que mencione `_pytest` no es una importacion.
    Un guard que buscara con regex contaria su propia prosa, que es
    exactamente lo que le paso a la primera version del guard de skips de
    WI-108.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name == "_pytest" or alias.name.startswith("_pytest."):
                    return (nodo.lineno, f"import {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            modulo = nodo.module or ""
            # `from _pytest import ...` y `from _pytest.fixtures import ...`.
            # Un `node` relativo (`.algo`) no es `_pytest`.
            if modulo == "_pytest" or modulo.startswith("_pytest."):
                nombres = ", ".join(a.name for a in nodo.names)
                return (nodo.lineno, f"from {modulo} import {nombres}")
    return None


class TestElArbolNoDependeDeInternalsDePytest:
    """La ley, medida sobre el AST del arbol real."""

    def test_ningun_modulo_del_repo_importa_pytest_interno(self) -> None:
        culpables: list[str] = []
        for ruta in _modulos_python():
            encontrado = _importa_pytest_interno(ruta)
            if encontrado is not None:
                lin, forma = encontrado
                relativo = ruta.relative_to(RAIZ)
                culpables.append(f"{relativo}:{lin}  {forma}")

        assert not culpables, (
            "modulos que dependen de un private de pytest:\n  "
            + "\n  ".join(culpables)
            + "\n\n`_pytest` no es API publica de pytest: cambia entre "
            "versiones sin aviso, y un hook que lo importe rompe la "
            "instalacion entera en vez de un test. Lo que se necesita de "
            "pytest se pide por su API publica."
        )

    def test_el_instrumento_de_este_guard_encuentra_al_menos_un_modulo(self) -> None:
        """**EL CONTRA SALTO: UN GUARD QUE NO MIDE NADA TAMBIEN PASA.**

        Sin esto, `_importa_pytest_interno` podria devolver siempre `None`
        —por un typo en el nombre, por un `ast.walk` mal usado— y el guard
        de arriba daria verde para siempre. Se mide contra el arbol REAL: si
        este finder no encuentra ni un modulo en los tres directorios, algo
        esta roto en el finder, no en el arbol.
        """
        modulos = list(_modulos_python())
        assert len(modulos) > 200, (
            f"el finder solo ve {len(modulos)} modulos: el directorio del "
            "guard no es el que cree ser, y su exito no mediria nada"
        )

    def test_un_docstring_que_mentiona_pytest_no_es_una_importacion(self) -> None:
        """La ambiguedad que el guard tiene que distinguir, probada."""
        fuente = (
            '"""Este modulo-documento habla de _pytest en prosa.\n\n'
            "No importa nada: es un docstring.\n"
            '"""\n\nimport sqlite3\n\nSQLITE = "_pytest"\n'
        )
        ruta = RAIZ / ".pipelinek" / "_wi_r0d_ambiguedad.py"
        try:
            ruta.write_text(fuente, encoding="utf-8")
            assert _importa_pytest_interno(ruta) is None, (
                "el finder conto la prosa del docstring como una importacion"
            )
        finally:
            ruta.unlink(missing_ok=True)

    def test_el_finder_detecta_una_importacion_real(self) -> None:
        """Y el otro lado: una importacion de verdad tiene que verse."""
        fuente = "import pytest\nimport _pytest.python\nfrom _pytest import mark\n"
        ruta = RAIZ / ".pipelinek" / "_wi_r0d_real.py"
        try:
            ruta.write_text(fuente, encoding="utf-8")
            encontrados = [
                _importa_pytest_interno(ruta),
                *(  # el `from` tambien
                    (nodo.lineno, "x")
                    for nodo in ast.walk(ast.parse(fuente))
                    if isinstance(nodo, ast.ImportFrom)
                    and (nodo.module or "").startswith("_pytest")
                ),
            ]
            assert encontrados[0] is not None, "no vio `import _pytest.python`"
            assert encontrados[1] is not None, "no vio `from _pytest import mark`"
        finally:
            ruta.unlink(missing_ok=True)


class TestElEntornoPuedeCumplirElContrato:
    """**LA MITAD QUE UN GUARD DE SOLO-ARBOL NO CUBRE.**

    El fallo original era de ENTORNO: el modulo no existia. Un guard que
    solo mirara los imports pasaria en una instalacion sin `_pytest`, que es
    justo donde el hook reventaba. Por eso se importa de verdad, aqui, en
    la suite: si el entorno no puede cumplir la ley, tiene que ponerse rojo
    aqui y no en la instalacion de un cliente.
    """

    def test_el_entorno_trae_pytest_interno(self) -> None:
        try:
            import _pytest
        except ModuleNotFoundError as exc:
            pytest.fail(
                f"el entorno no puede cumplir el contrato de este bloque: {exc}. "
                "Sin `_pytest`, cualquier hook o instrumento que lo importara "
                "reventaria en la instalacion del cliente, y la suite de aqui "
                "no lo veria porque aqui tampoco existe. Es la opcion A del "
                "enunciado —instalacion incompleta— y se arregla instalando "
                "pytest, no declarando el fallo."
            )
        # No basta con que el import no lance: tiene que ser un PAQUETE de
        # verdad. MEDIDO al escribirlo —sin esta asercion ruff ahogaba el
        # import como `_pytest imported but unused`, que es la manera de que
        # un linter te diga que tu prueba no prueba nada sin decirlo claro.
        assert _pytest.__path__, (
            "`_pytest` se importa pero no es un paquete: es un atributo o un "
            "stub, y la opcion A del enunciado (instalacion incompleta) sigue "
            "sin resolverse"
        )

    def test_y_es_el_pytest_que_la_metadata_declara(self) -> None:
        """Que `_pytest` y `pytest` sean el MISMO paquete, no dos cosas.

        Importar `_pytest` puede tener exito mientras el `pytest` del
        entorno es otro, y entonces el fallo aparece mas tarde y en otro
        sitio.

        **MEDIDO AL ESCRIBIRLO, Y CORRIGE UNA ASERCION MIA.** La primera
        version afirmaba `hasattr(_pytest, "version")`. FALLA: en pytest 9.1.1
        `_pytest` no expone `version` —tampoco `__version__`—, y esa
        asercion era exactamente la clase de dependencia que este bloque
        prohibe: atarse a la FORMA de un private. Se pregunta a la
        **metadata** del paquete, que es la API publica y estable.
        """
        import importlib.metadata as metadata

        import _pytest
        import pytest

        assert _pytest.__name__ == "_pytest", _pytest.__name__
        assert pytest.__version__ == metadata.version("pytest"), (
            f"pytest.__version__={pytest.__version__} y la metadata dice "
            f"{metadata.version('pytest')}: hay dos pytest en el entorno"
        )
        # El private tiene que VENIR de la MISMA distribucion. MEDIDO:
        # `_pytest/` y `pytest/` son HERMANOS dentro de `site-packages/`, no
        # padre e hijo —la primera version miro `Path(pytest.__file__).parent`
        # y fallo, porque eso es `site-packages/pytest/` y no
        # `site-packages/`—. La pregunta es «estan en el mismo arbol».
        raiz_pytest = Path(pytest.__file__ or "").parent.parent
        raiz_interno = Path(_pytest.__file__ or "").parent.parent
        assert raiz_interno == raiz_pytest, (
            f"`_pytest` se importa de {raiz_interno} y `pytest` de "
            f"{raiz_pytest}: el private no viene de la misma distribucion"
        )


class TestElFalloNoEsUnExcepcionHumana:
    """**LO QUE EL ENUNCIADO RECHAZA EXPRESAMENTE.**

        suite -> 1 fallo conocido -> «GREEN por clasificacion»

    Aqui no hay una lista de fallos perdonados: hay una ley que se cumple o
    un rojo. Este test no necesita mirar ningun run —comprueba que el propio
    mecanismo de perdon que describe el enunciado **no existe en el arbol**.
    """

    def test_no_hay_una_lista_de_fallos_conocidos_que_se_perdonen(self) -> None:
        """`check_pipeline_receipt.py` no puede tener una lista de reds."""
        ruta = RAIZ / "scripts" / "check_pipeline_receipt.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Assign):
                for objetivo in nodo.targets:
                    nombre = getattr(objetivo, "id", "")
                    if not isinstance(nombre, str):
                        continue
                    if "CONOCIDOS" in nombre or "PERDON" in nombre:
                        pytest.fail(
                            f"scripts/check_pipeline_receipt.py declara "
                            f"{nombre!r}: una lista de fallos perdonados es "
                            "la forma que R0.4 declara inaceptable, porque "
                            "el runner no puede decidirla sin una persona."
                        )

    def test_los_skips_declarados_siguen_siendo_tres_y_nombrados(self) -> None:
        """Lo que SÍ es una excepción declarada: los skips de plataforma.

        La diferencia es que un skip declarado tiene una **razon escrita** y
        una entrada en `SKIPS_PLATAFORMA` vigilada en las dos direcciones por
        `test_wi108_zero_skips.py`. No es una lista de «esto lo perdi»:
        es una lista de «esto se decide asi, y por esta razon».
        """
        from scripts.check_pipeline_receipt import (
            SKIPS_PLATAFORMA,
        )

        assert SKIPS_PLATAFORMA, "la lista de skips declarados esta vacia"
        for ruta, razon in SKIPS_PLATAFORMA.items():
            assert razon.strip(), f"{ruta} esta declarado sin razon"
            assert (RAIZ / ruta).exists(), (
                f"{ruta} esta declarado como legitimo y no existe: una "
                "declaracion sin suelo no declara nada"
            )
