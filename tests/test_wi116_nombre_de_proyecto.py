"""El nombre de un proyecto va a una RUTA, y el mensaje tiene que decirlo bien.

**EL DEFECTO, MEDIDO.** `sg project create` rechazaba un nombre inválido
diciendo «Use solo [a-z0-9-_] y hasta 64 caracteres». `is_safe_name` acepta
mayúsculas:

    'CON_MAYUSCULAS'         -> True
    'Demo'                   -> True
    'PROD'                   -> True
    'con espacio'            -> False
    'con.punto'              -> False
    'con/barra'              -> False
    'ñandú'                  -> False

El conjunto que el mensaje anunciaba era estrictamente más pequeño que el que
la función aplicaba. No es una trampa de seguridad —aceptar más de lo
anunciado no abre nada— pero es una afirmación falsa en la unica línea que ve
un operador con un nombre inválido: si le dicen «solo minúsculas» y el
proyecto que tiene dos líneas más abajo se llama `Demo`, deduce que su
malentendido le va a fallar otra vez y prueba una variante que tampoco
funciona.

**POR QUÉ NO BASTA CORREGIR EL TEXTO.** Porque un texto corregido a mano
vuelve a separarse de la función en cuanto cualquiera de las dos cambie, y
nadie se entera: no hay ningún fallo, solo un mensaje cada vez más mentiroso.
La regla vive ahora en `platform/paths.py` como `REGLAS_DE_NOMBRE_SEGURO` y
el CLI la IMPORTA. Este fichero mide que las dos digan lo mismo.

**LO QUE SE MIDE, Y CÓMO.** No se parsea la prosa del mensaje para adivinar
qué conjunto anuncia —eso sería medir el parsing de una frase—. Se mide que
el mensaje CONTENGA la regla compartida, y que esa regla describa el
comportamiento real de `is_safe_name` en una tabla de casos. Las dos mitades
juntas son lo que evita que el mensaje vuelva a mentir: si la función
cambia, la tabla falla; si el mensaje deja de importar la regla, la otra
falla.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from skillgraph.cli.runner import cmd_project_create
from skillgraph.platform.paths import REGLAS_DE_NOMBRE_SEGURO, is_safe_name

#: Que hace `is_safe_name` con un nombre, MEDIDO. Esta tabla es el contrato
#: que la regla escrita tiene que describir; si `is_safe_name` cambia, una
#: fila cambia y el guard dice cual.
CASOS = [
    ("demo", True),
    ("DEMO", True),
    ("Demo", True),
    ("CON_MAYUSCULAS", True),
    ("con-guion", True),
    ("con_guion_bajo", True),
    ("123", True),
    ("a" * 64, True),
    ("", False),
    ("a" * 65, False),
    ("con espacio", False),
    ("con.punto", False),
    ("con/barra", False),
    ("con\\barra", False),
    ("ñandú", False),
    ("con:dos-puntos", False),
]


def _anuncia_mayusculas(texto: str) -> bool:
    """Si el TEXTO dice que las mayusculas valen.

    Dos formas de decirlo, y las dos cuentan: la palabra (`mayusculas`) o el
    rango completo (`[A-Za-z0-9-_]`, que en minusculas es `a-za-z`). Se
    busca `a-za-z` y no `a-z` a proposito: `[a-z0-9-_]` contiene `a-z` y no
    contiene `a-za-z`, y esa es justo la diferencia entre el texto que miente
    y el que no.

    Es un predicado sobre la FORMA del conjunto anunciado, no sobre su
    comportamiento. Se complementa con la tabla de `CASOS`, que es la que
    mide si la regla dice la verdad; entre los dos, un cambio en cualquiera
    de las dos mitades se ve.
    """
    minusculas = texto.lower()
    return "mayuscula" in minusculas or "a-za-z" in minusculas


class TestLaReglaDiceLoQueHaceLaFuncion:
    def test_cada_caso_de_la_tabla_cumple_lo_que_dice_la_funcion(self) -> None:
        """La tabla se EJECUTA. Una regla escrita que no casa con el codigo falla aqui.

        Y no hay lista de excepciones: la tabla ES el contrato, y una fila
        nueva entra sin tocar el guard.
        """
        mentirosas = [(n, esperado) for n, esperado in CASOS if is_safe_name(n) != esperado]
        assert not mentirosas, (
            f"`is_safe_name` cambio y la regla escrita ya no lo describe: {mentirosas}"
        )

    def test_la_regla_anuncia_las_mayusculas(self) -> None:
        """**LA ASERCION QUE HACE FALLAR EL MENSAJE VIEJO.**

        Se mide por lo que la regla AFIRMA, no por lo que la funcion acepta:
        si `REGLAS_DE_NOMBRE_SEGURO` dijera `[a-z0-9-_]` —el texto viejo—, la
        regla volveria a anunciar un conjunto mas pequeño que el real aunque
        `is_safe_name` no hubiera cambiado.

        Es la asercion que hace que el arreglo no sea «cambiar la frase»: es
        que la frase diga el conjunto entero.
        """
        assert _anuncia_mayusculas(REGLAS_DE_NOMBRE_SEGURO), (
            f"la regla anuncia un conjunto que no incluye mayusculas y la "
            f"funcion si las acepta: {REGLAS_DE_NOMBRE_SEGURO!r}"
        )
        assert is_safe_name("DEMO"), (
            "la regla dice que las mayusculas valen pero la funcion las rechaza: "
            "la regla y la funcion ya no dicen lo mismo"
        )

    def test_la_regla_no_anuncia_mas_de_lo_que_la_funcion_acepta(self) -> None:
        """El otro sentido: la regla no puede PROMETER mas de lo que hay.

        Se mide con un nombre que la regla no anuncia y la funcion rechaza:
        el punto. Si alguien llegara a anunciar `[A-Za-z0-9-_.]` sin cambiar la
        funcion, este test falla. La contradiccion va en las dos direcciones
        porque en las dos dice algo falso.
        """
        assert "." not in REGLAS_DE_NOMBRE_SEGURO.replace("...", ""), (
            f"la regla anuncia el punto y la funcion lo rechaza: {REGLAS_DE_NOMBRE_SEGURO!r}"
        )
        assert not is_safe_name("con.punto")


class TestElComandoImprimeLaRegla:
    def test_el_error_del_comando_LLEVA_la_regla_compartida(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**LA ATADURA QUE FALTA SI SOLO SE CORRIGE EL TEXTO.**

        Una regla correcta en `paths.py` que el CLI no use es una constante
        muerta: el mensaje sigue mintiendo y el guard de arriba sigue verde.

        Se mide que el texto impreso CONTIENE la regla compartida. No que sea
        igual a ella —el mensaje tiene contexto alrededor— sino que la regla
        este dentro, porque es la regla entera la que tiene que estar.
        """
        data_root = tmp_path / "sg-data"
        assert _init(data_root, tmp_path).returncode == 0

        rc = cmd_project_create(argparse.Namespace(data_root=data_root, name="con.punto"))
        err = capsys.readouterr().err

        assert rc != 0
        assert REGLAS_DE_NOMBRE_SEGURO in err, (
            f"el error no imprime la regla compartida.\n  regla: {REGLAS_DE_NOMBRE_SEGURO!r}\n"
            f"  error: {err!r}"
        )
        assert "con.punto" in err, f"el error no nombra lo que se pidio: {err!r}"

    def test_la_regla_menciona_el_LIMITE_de_longitud_que_la_funcion_aplica(self) -> None:
        """El `64` del texto tiene que ser el `64` del codigo, no el del recuerdo.

        Se mide contra `is_safe_name` y no contra un numero escrito aqui: el
        limite se encuentra probando, luego si el codigo pasa a 128 este test
        pasa a exigir `128` en el texto. La fuente es la funcion.
        """
        limite_real = max((n for n in range(1, 200) if is_safe_name("a" * n)), default=0)
        assert limite_real == 64, (
            f"el limite real cambio a {limite_real} y la regla sigue diciendo lo que dice"
        )
        assert "64" in REGLAS_DE_NOMBRE_SEGURO, REGLAS_DE_NOMBRE_SEGURO


def _init(data_root: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {"SKILLGRAPH_DATA_ROOT": str(data_root), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), "init"],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


class TestElMensajeViejoNoVuelve:
    """**EL CONTRAEJEMPLO, Y POR QUE ESTA EN UN FICHERO DE TEST.**

    Este test no mira `src/`: mira el TEXTO VIEJO y demuestra que el guard de
    arriba lo rechaza. Es el mismo motivo por el que
    `test_wi41_cli_dispatch.py` construye un `main` hotspot de verdad.

    Sin el, un guard que se puede cumplir con la frase equivocada no esta
    probado: pasaria en verde con el mensaje viejo mientras el repo lo
    escribiese.
    """

    def test_el_texto_viejo_no_pasa_el_guard_de_la_regla(self) -> None:
        """Si alguien vuelve a `[a-z0-9-_]`, esta asercion tiene que ponerse roja."""
        # **ESTE CONTRAEJEMPLO ENCONTRO UN DEFECTO DEL GUARD, Y POR ESO ESTA.**
        # La primera version del predicado era `"a-z" in texto`, y eso es
        # VERDADERO para el texto viejo —que contiene `[a-z0-9-_]`—, luego
        # el guard no distinguia el texto viejo del nuevo y el contraejemplo
        # se puso rojo a si mismo. Un discriminante tiene que ser algo que el
        # texto viejo NO tenga: el rango completo se escribe `A-Za-z`, y en
        # minusculas eso es `a-za-z`, que `[a-z0-9-_]` no contiene.
        viejo = "caracteres alfanumericos ASCII ([a-z0-9-_]), de 1 a 64 caracteres"

        assert not _anuncia_mayusculas(viejo), (
            "el texto viejo pasa el guard, luego el guard no mide lo que dice medir"
        )
        assert _anuncia_mayusculas(REGLAS_DE_NOMBRE_SEGURO), (
            "la regla nueva tampoco pasa su propio guard: el discriminante "
            "esta mal y haria que la regla pueda mentir igual"
        )
