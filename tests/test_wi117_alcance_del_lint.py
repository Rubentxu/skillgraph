"""El alcance del lint, y el gate de formato que la receta no tenia.

**EL DEFECTO, MEDIDO.** `.pipeline.kts` y `scripts/hooks/pre-commit` decian
los dos `ruff check src tests`, sin `scripts`. Ahi viven los instrumentos de
medicion del repo —los guards que certifican todo lo demas—, luego el hueco
era justo sobre lo que vigila.

Consecuencia medida, no temida: `scripts/project_truth.py` se quedo sin
formatear en `d2c47e3` y ningun gate lo vio. Un guard que puede romperse en
silencio es un guard que no vigila, y el que se rompio era el que decide si
`project_truth` da rojo.

Y la segunda mitad, que es la mas grave porque es una AUSENCIA: la etapa
`lint` de la receta no comprobaba FORMATO. Solo lo comprobaba el hook, y el
hook es un aviso que se salta con `--no-verify`. La via por la que entra el
CI no miraba el formato.

**LO QUE SE COMPRUEBA, Y POR QUE NO BASTA CON QUE EL CODIGO ESTE BIEN.**
Que hoy `ruff check src tests scripts` pase es una afirmacion sobre HOY, y se
puede volver a romper sin que nadie se entere. Lo que se mide son las tres
COSAS que tienen que seguir siendo verdad:

  1. el alcance del lint incluye `scripts`, en la receta y en el hook, y los
     dos DICEN LO MISMO (si divergen, uno de los dos miente sobre lo que
     comprueba);
  2. la receta tiene un gate de formato, no solo el hook;
  3. `scripts/` tiene ficheros `.py` de verdad —sin esta comprobacion, un
     guard que devuelve la lista vacia pasaria todo lo demas en verde, que es
     el M2 que este repo lleva cerrando desde WI-110.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE = ROOT / ".pipeline.kts"
HOOK = ROOT / "scripts" / "hooks" / "pre-commit"

#: Los tres directorios que el lint debe mirar, EN ESE ORDEN.
#:
#: **POR QUE LA LISTA ESTA AQUI Y NO SE DERIVA DEL CODIGO.** Al principio
#: este comentario decia que escribirla aqui era «compararse consigo mismo»,
#: y es al reves: si el alcance se derivara del codigo, bastaria con quitar
#: `scripts` de la receta para que el guard derivara `src tests`,一样 pasara
#: en verde, y el hueco volveria sin que nadie lo notara. Una lista escrita
#: puede quedarse vieja —y ese es el riesgo real—; una lista derivada no
#: puede, pero para eso no vigila nada.
#:
#: El riesgo de la lista escrita lo cubre
#: `test_la_receta_Y_el_hook_dicen_LO_MISMO`, que compara lo que el codigo dice
#: con lo que este fichero declara. Entre los dos, quitar un directorio del
#: lint pone la suite en rojo. MEDIDO con sondas: quitar `scripts` de la receta
#: pone en rojo dos tests, y quitar el gate de formato pone en rojo el
#: tercero.
ALCANCE = ("src", "tests", "scripts")


def _texto_de_la_receta() -> str:
    return RECIPE.read_text(encoding="utf-8")


def _texto_del_hook() -> str:
    return HOOK.read_text(encoding="utf-8")


class TestElAlcanceNoPierdeDirectorios:
    """El alcance del lint, en los DOS sitios, y los dos diciendo lo mismo.

    Se mide en los dos porque estan separados y ninguno deriva del otro: el
    hook se copia a `.git/hooks/` por `install-hooks.sh` y la receta la lee el
    motor. Divergen en silencio.
    """

    def test_la_receta_lint_ea_los_tres(self) -> None:
        """La etapa `lint` de `.pipeline.kts` mira los tres.

        Se busca la etapa y no el fichero entero a proposito: `scripts`
        aparece por mil motivos en la receta, y medir «el fichero contiene la
        palabra» seria medir que hay una palabra.
        """
        texto = _texto_de_la_receta()
        bloque = _etapa(texto, "lint")
        esperado = " ".join(ALCANCE)

        assert f"ruff check {esperado}" in bloque, (
            f"la etapa `lint` no mira {esperado}.\n  bloque:\n{bloque}"
        )

    def test_el_hook_lint_ea_los_tres(self) -> None:
        esperado = " ".join(ALCANCE)
        texto = _texto_del_hook()

        assert f"ruff check {esperado}" in texto, f"el hook no ejecuta `ruff check {esperado}`."
        assert f"ruff format --check {esperado}" in texto, (
            f"el hook no ejecuta `ruff format --check {esperado}`."
        )

    def test_la_receta_Y_el_hook_dicen_LO_MISMO(self) -> None:
        """**LA CONTRADICCION ENTRE LOS DOS ES UN DEFECTO POR SI MISMA.**

        Si el hook dijera `src tests scripts` y la receta `src tests`, el
        hook comprobaría más que la receta y quien lee el hook creería que el
        CI comprueba lo que él comprueba. Y al revés: si el hook se queda
        corto, el aviso local es más débil que el gate.

        Se comparan los dos alcances por extracción, no por igualdad de
        texto: lo que tiene que ser lo mismo es el CONJUNTO de directorios.
        """
        receta = set(_alcance_de_la_receta())
        hook = set(_alcance_del_hook())

        assert receta == hook, (
            f"la receta lint_ea {sorted(receta)} y el hook {sorted(hook)}: uno "
            f"de los dos comprueba mas que el otro y ninguno se entera"
        )
        assert receta == set(ALCANCE), (
            f"el alcance real es {sorted(receta)} y este fichero declara "
            f"{sorted(ALCANCE)}: el guard mide una lista que ya no es la del codigo"
        )


class TestElGateDeFormatoExiste:
    def test_la_receta_comprueba_el_formato(self) -> None:
        """**LA AUSENCIA QUE NO SE VE.**

        Una etapa que solo comprueba `check` deja pasar un fichero mal
        formateado. Antes de WI-117 esa era exactamente la situacion, y el
        fichero mal formateado existia de verdad en el arbol.

        Se mide que la etapa tiene las DOS lineas, no que tenga una: un gate
        de formato que se cuela como tercer `sh` de otra etapa no contaria.
        """
        bloque = _etapa(_texto_de_la_receta(), "lint")

        assert "ruff format --check" in bloque, (
            "la receta NO comprueba el formato: el hook comprueba, y el hook "
            "se salta con `--no-verify`. La via del CI no mira el formato.\n"
            f"  bloque:\n{bloque}"
        )
        assert "ruff check" in bloque, "la etapa dejo de comprobar el lint"


class TestNoHayGuardQueMidaElVacio:
    """**EL CONTRAEJEMPLO, Y POR QUE ESTA EN UN FICHERO DE TEST.**

    Los tres tests de arriba se pueden cumplir todos si `ALCANCE` no
    corresponde a nada real. Este test mide que `scripts/` tiene codigo, y es
    la con contraparte directa del M2 que WI-110 documento: una derivacion
    que devolviera siempre la lista vacia pasaria todo en verde.

    Se cuenta por convencion de nombre (`*.py` bajo `scripts/`) y no leyendo
    una lista, porque una lista de ficheros seria justo el tipo de lista que
    se desactualiza sin avisar.
    """

    def test_scripts_tiene_python_de_verdad(self) -> None:
        ficheros = sorted(p.name for p in (ROOT / "scripts").glob("*.py"))
        assert len(ficheros) >= 20, (
            f"solo {len(ficheros)} ficheros .py en scripts/: si esta lista "
            "cayo, los tres guards de arriba miden un alcance vacio"
        )

    def test_el_alcance_declarado_apunta_a_directorios_que_existenen(self) -> None:
        for d in ALCANCE:
            ruta = ROOT / d
            assert ruta.is_dir(), f"`{d}/` no existe: el alcance declarado nombra algo que no esta"

    def test_los_hooks_instalados_Y_los_versionados_dicen_lo_mismo(self) -> None:
        """`.git/hooks/pre-commit` es una COPIA de `scripts/hooks/pre-commit`.

        Se instala con `scripts/install-hooks.sh`. Si la copia se queda
        vieja, el hook que corre no es el que esta versionado, y este
        fichero estaria midiendo el texto equivocado.

        Solo se compara si la copia existe: un repo clonado sin
        `install-hooks.sh` no tiene hooks, y eso no es un defecto del repo.
        """
        instalado = ROOT / ".git" / "hooks" / "pre-commit"
        if not instalado.exists():
            return

        esperado = f"ruff check {' '.join(ALCANCE)}"
        assert esperado in instalado.read_text(encoding="utf-8"), (
            "el hook INSTALADO no mira el alcance declarado: corre un hook "
            "viejo. Se arregla con `scripts/install-hooks.sh`."
        )


def _etapa(texto: str, nombre: str) -> str:
    """El cuerpo de una etapa del `.pipeline.kts`, por nombre.

    Se busca el `stage("<nombre>") {` y se devuelve hasta la llave que lo
    cierra. Es una aproximacion por lineas y no un parser de Kotlin: la
    receta tiene doce etapas y una comilla desbalanceada haria fallar a todo,
    que es preferible a un parser que no ve el caso que importa.
    """
    inicio = texto.find(f'stage("{nombre}")')
    if inicio == -1:
        raise AssertionError(f"la receta no declara la etapa {nombre!r}")
    fin = texto.find("\n        }", inicio)
    if fin == -1:
        raise AssertionError(f"no se encontro el cierre de la etapa {nombre!r}")
    return texto[inicio : fin + 11]


def _alcance_de_la_receta() -> list[str]:
    bloque = _etapa(_texto_de_la_receta(), "lint")
    m = re.search(r"ruff check ([a-z ]+?) 2>&1", bloque)
    assert m, f"no se pudo leer el alcance de la receta:\n{bloque}"
    return m.group(1).split()


def _alcance_del_hook() -> list[str]:
    texto = _texto_del_hook()
    m = re.search(r"ruff check ([a-z ]+?) \|\|", texto)
    assert m, f"no se pudo leer el alcance del hook:\n{texto[:2000]}"
    return m.group(1).split()
