"""WI-115: `tests.total` declara una cifra y nadie comprueba que sea cierta.

`STATE.yaml` usa `tests.total` como contexto del proyecto entero: cada
bloque anade su «+N sobre M» y con eso se lee la historia del repo. La
cifra **deberia** ser una propiedad medida. MEDIDO que no lo es, en las
dos direcciones (`.pipelinek/wi115_measure.py`, con restauracion byte a
byte y sha verificado):

    STATE.yaml tests.total : 2834
    tests colectados       : 2834
    hoy coinciden: True

    M1  tests.total = 2834 -> 2971:  governance rc=0  VERDE (NO LO VE)
    M2  anadido 1 test (2835 colectados, estado en 2834):  rc=0  VERDE

Lo que le da gravedad: en WI-109 la primera certificacion de ese bloque
dio `2753 passed + 1 failed`, y **el fallo era este campo**. Su hermano
`package_version` quedo vigilado desde entonces; este sigue a oscuras.

**EL RECUENTO VIENE DEL ARBOL, NO DEL ESTADO.** Un guard que comparase
la cifra de `STATE.yaml` contra una copia escrita en el propio test
seria un guard que compara contra su propia copia (el error de WI-106):
hoy coinciden, y el dia que la verdad se mueva dira lo contrario con
toda la autoridad de un test. Aqui la verdad es
`pytest --collect-only` sobre el arbol real.

**POR QUE UN TEST Y NO UNA ETAPA DE LA RECETA.** `.pipeline.kts` tiene
un SHA-256 declarado invariante desde WI-110 (`7541ced5…`). Anadir una
etapa seria cambiar ese invariante por un fallo que se cierra dentro de
la suite. Un test es un test; una etapa nueva es un contrato de CI.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
STATE = RAIZ / "STATE.yaml"

# pytest escribe «N tests collected in Xs», y en dependencias puede decir
# «N tests collected» a secas. Se acepta el singular porque el patron
# cambia con la version y un guard que se rompe al actualizar una
# dependencia no vigila el codigo, vigila la cadena de texto.
_COLECTADOS = re.compile(r"(\d+)\s+tests?\s+collected")


def _estado() -> dict:
    return yaml.safe_load(STATE.read_text(encoding="utf-8"))


def _total_declarado() -> int:
    return _estado()["tests"]["total"]


def _colectados_reales() -> int:
    """El recuento, derivado del arbol. Nunca del estado.

    Se lanza pytest en un subproceso con `-p no:cacheprovider` y fuera
    de pytest: llamar a pytest desde pytest sin subproceso colecta la
    sesion que ya esta colectando y contaria cada test dos veces.

    El resultado se cachea por sesion. Sin cache, este fichero lanzaria
    cuatro subprocesos de colecta completa —unos cuatro segundos en
    cada run— para leer siempre el mismo numero, sin medir nada que el
    primero no midiera. El cache es de sesion, no global: si alguien
    anade un test a mitad de la suite, se compara con el numero que
    tenia cuando la sesion empezo, que es el que ve el resto de la suite.
    """
    if _CACHE["total"] is not None:
        return int(_CACHE["total"])
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--collect-only"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        env={**os.environ, "TMPDIR": tempfile.gettempdir()},
    )
    m = _COLECTADOS.search(proc.stdout)
    # **EL CODIGO DE SALIDA, Y POR QUE SE COMPRUEBA AHORA Y NO ANTES.**
    #
    # MEDIDO al certificar R0.A: este guard pasa en la suite completa y falla
    # en aislamiento, con el MISMO arbol:
    #
    #     suite completa   3717 passed + 3 skipped  -> verde
    #     este test solo   3720 declarado vs 3728    -> rojo, con la verdad
    #
    # 3720 es justo 3717 + 3, o sea **el numero de PASSED**, y tambien lo que
    # el estado declaraba. Lo que hacia era esto:
    #
    #     la colecta del subproceso salia con rc != 0,
    #     pytest imprimia «3720 tests collected» como conteo PARCIAL,
    #     aqui no se miraba el rc, se leia el numero,
    #     y 3720 == lo declarado, luego VERDE.
    #
    # **Un guard que pasa porque su propio instrumento fallo.** Es la clase
    # que este repo ya ha pagado en `total_colectado()` de project_truth.py,
    # que si avisa del rc, y que aqui se leia el numero y se aceptaba.
    assert proc.returncode == 0, (
        f"la colecta de tests fallo (rc={proc.returncode}) y su numero NO es "
        "el recuento real: un conteo parcial comparado con el declarado "
        "puede coincidir por casualidad y dar verde. "
        f"stdout:\n{proc.stdout[-600:]}\nstderr:\n{proc.stderr[-600:]}"
    )
    if m is None:
        pytest.fail(
            "no he podido leer el recuento real de tests. Un guard que no "
            "puede leer su propia medicion y aun asi pasa es peor que no "
            "tener guard, asi que esto es un fallo, no una excepcion. "
            f"Ultimas lineas de la salida:\n{proc.stdout[-600:]}\n"
            f"stderr:\n{proc.stderr[-400:]}"
        )
    _CACHE["total"] = int(m.group(1))
    return int(_CACHE["total"])


_CACHE: dict[str, int | None] = {"total": None}


class TestLaCifraEsMedida:
    def test_el_total_declarado_es_el_total_colectado(self) -> None:
        """La propiedad, tal y como la declaraba el estado.

        Falla con la cifra buena en el mensaje: un verificador que dice
        «falso» sin decir «cual es la verdad» deja al que corrige
        haciendo la cuenta a mano, que es el trabajo que el guard existe
        para evitar.
        """
        declarado = _total_declarado()
        real = _colectados_reales()
        assert declarado == real, (
            f"STATE.yaml tests.total dice {declarado} y el arbol colecta "
            f"{real}. Si has anadido o quitado tests, la cifra se actualiza "
            f"al FINAL del bloque, con el run ya ejecutado: ponle {real}."
        )


class TestElGuardDegrada:
    """Un guard que solo sabe pasar en verde no esta probado."""

    def test_el_campo_existe_y_es_un_entero(self) -> None:
        """Distinto de «discrepa»: aqui no hay nada que comparar.

        Sin esta separacion, borrar el campo daria un `KeyError` que
        parece un fallo del guard en vez de un fallo del estado, y quien
        lo lea buscaria el bug en el sitio equivocado.
        """
        declared = _estado()["tests"].get("total")
        assert isinstance(declared, int), (
            f"tests.total es {declared!r} ({type(declared).__name__}), no un "
            "entero. Sin el numero no hay nada que medir, y un guard que "
            "no puede medir tiene que decirlo, no pasar."
        )

    def test_el_estado_sigue_leyendose_como_yaml(self) -> None:
        """Si STATE.yaml se rompe, el guard debe decirlo aqui.

        `tests.total` es el unico campo numerico de la seccion `tests:`
        que el repo usa como cifra oficial, y WI-85 ya demostro que esa
        seccion puede quedar tapada por un snapshot de cobertura
        anidado por error. Este test no evita eso: hace que cuando
        ocurra, el sintoma sea «el estado no parsea» y no «el numero no
        cuadra», que es un sintoma que senala al sitio equivocado.
        """
        try:
            _estado()
        except yaml.YAMLError as exc:  # pragma: no cover
            pytest.fail(f"STATE.yaml no parsea como YAML: {exc}")

    def test_el_recuento_real_se_puede_leer(self) -> None:
        """El patron de la salida de pytest, vigilado.

        `_colectados_reales` falla si no encuentra el recuento, asi que
        este test no es un extra: es la garantia de que el guard de
        arriba no esta comparando contra un cero silencioso cuando el
        formato de la salida cambia en una actualizacion de pytest.
        """
        real = _colectados_reales()
        assert real > 0, (
            f"el recuento real salio {real}. Un cero aqui haria que el "
            "guard de arriba se quejara de un estado correcto."
        )
        assert real > 1000, (
            f"el recuento real salio {real}, que es sospechosamente bajo "
            "para un repo con ~2800 tests. Antes de quejarse de STATE.yaml "
            "hay que suponer que el recuento esta mal leido."
        )
