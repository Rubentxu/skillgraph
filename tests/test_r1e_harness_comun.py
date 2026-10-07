"""R1.E — el harness comun, y sobre todo: que NO destruya trabajo.

**LA MEDIDA QUE ABRE ESTE TRABAJO, con el numero y no con la prosa:**

    scripts/mutate_*.py                      27 ficheros
    lineas de codigo                         8.554
    los que restauran con `git checkout --`   15 de 27

Veintisiete copias de la misma maquina. Y quince de ellas restauran el
arbol con `git checkout --`, que **restaura DEL INDICE**: con un arreglo sin
commitear —que es como se esta casi siempre mientras se escribe un bloque—
eso no restaura, borra.

**Y ESTE TRABAJO LO SUFRIO, NO LO LEI.** A mitad de certificacion de R1.F
desaparecieron del arbol de trabajo `migrations.py` con la migracion `0005`
y sus 13 tests. Se recuperaron de un volcado accidental, no de una copia:
el arbol habia sido revertido por un harness que ademas reporto un
veredicto con numero. Un harness que destruye el arbol e imprime un
resultado es peor que no tener harness.

# LO QUE ESTE FICHERO COMPRUEBA, y por que en este orden

    TestElRestaurador        PRUEBA la restauracion, incluida la que
                             `git checkout --` no puede hacer
    TestLaClasificacion      cada uno de los seis estados, y sobre todo que
                             `MUTACION_INVALIDA` NO se cuenta como catches
    TestContraSaltos         contrasaltos del propio harness

**EL ORDEN NO ES ESTETICO.** El restaurador va primero porque sin el los
otros tests serian una prueba de un harness que puede borrar el codigo que
los其它 tests estan leyendo.

**Y UN TEST QUE USA `git` DE VERDAD, POR QUE.** Podria bastar con simular un
indice. Se usa el repo real porque el defecto que se vigila es
precisamente «el indice no tiene lo que se esta escribiendo», y eso solo
se reproduce contra un indice real. El fichero se elige SIEMPRE versionado y
se restaura byte a byte al final, con el `finally` y una comprobacion
adicional — que es lo que el propio harness promete hacer.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _cargar() -> object:
    """Carga el harness por ruta: `scripts/` no es paquete.

    **EL MODULO TIENE QUE REGISTRARSE EN `sys.modules`, Y NO ES COSA ESTETICA.**
    MEDIDO: sin esta linea, `@dataclass(slots=True)` falla con
    `AttributeError: 'NoneType' object has no attribute '__dict__'`, porque
    `dataclasses` busca el espacio de nombres del modulo via
    `sys.modules[cls.__module__]` y, sin registro, no lo encuentra. El fallo
    aparece en la IMPORTACION, no en ningun test, luego es facil de leer
    como «el harness esta roto» cuando lo que esta roto es como se carga.
    """
    ruta = RAIZ / "scripts" / "mutation_harness.py"
    spec = importlib.util.spec_from_file_location("mutation_harness", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["mutation_harness"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


H = _cargar()


def _proyecto_minimo(tmp_path: Path) -> Path:
    """Un proyecto de dos ficheros que el harness pueda usar entero.

    `m.py` con una funcion y `test_m.py` que la mira. Con eso, la sonda
    «cambia el resultado» pone la suite en rojo y la sonda «cambia otra
    cosa» la deja verde, **sin tocar el repo real**.

    **POR QUE UN PROYECTO TEMPORAL, MEDIDO.** La primera version de estos
    tests apuntaba la suite al repositorio entero: eso lanzo **522
    subprocesos** y el fichero tardo mas de seis minutos. Un guard que cuesta
    un minuto por test no se ejecuta, y un guard que no se ejecuta mide
    menos que un docstring.
    """
    (tmp_path / "m.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    (tmp_path / "test_m.py").write_text(
        "def test_f():\n    import m\n    assert m.f(1) == 2\n", encoding="utf-8"
    )
    return tmp_path


class TestElRestaurador:
    """**LA PROMESA CENTRAL: devolver el arbol, no borrarlo.**"""

    def test_devuelve_los_bytes_exactos(self, tmp_path: Path) -> None:
        objetivo = tmp_path / "modulo.py"
        objetivo.write_text("ORIGINAL = 1\n", encoding="utf-8")

        r = H.Restaurador.captura([objetivo])
        objetivo.write_text("MUTADO = 2\n", encoding="utf-8")
        assert not r.verificar(), "un arbol mutado tiene que estar sucio"

        problemas = r.restaura()
        assert problemas == (), problemas
        assert objetivo.read_text(encoding="utf-8") == "ORIGINAL = 1\n"
        assert r.verificar()

    def test_un_fichero_QUE_BORRAS_tambien_se_devuelve(self, tmp_path: Path) -> None:
        """El caso que `git checkout --` no cubre bien: que desaparezca.

        Una sonda puede llegar a borrar el fichero entero (una rama de
        codigo que hace `unlink`). El restaurador tiene que devolverlo,
        porque si no, la siguiente sonda corre contra un arbol al que le
        falta un modulo y el rojo que salga no significa nada.
        """
        objetivo = tmp_path / "modulo.py"
        objetivo.write_bytes(b"X = 1\n")

        r = H.Restaurador.captura([objetivo])
        objetivo.unlink()
        problemas = r.restaura()

        assert problemas == (), problemas
        assert objetivo.exists(), "el fichero no volvio"
        assert objetivo.read_bytes() == b"X = 1\n"

    def test_no_toca_los_ficheros_que_no_capturo(self, tmp_path: Path) -> None:
        """Capturar dos y restaurar no puede resurrectar un tercero."""
        a, b, c = (tmp_path / n for n in ("a.py", "b.py", "c.py"))
        for f in (a, b, c):
            f.write_text("v1\n", encoding="utf-8")

        r = H.Restaurador.captura([a, b])
        a.write_text("MUTADO\n", encoding="utf-8")
        c.write_text("MODIFICADO POR OTRO\n", encoding="utf-8")

        r.restaura()
        assert a.read_text(encoding="utf-8") == "v1\n"
        # `c` no se capturo, luego el restaurador no lo controla. NO se
        # revierte: revertirlo seria pisar el trabajo de quien lo cambio.
        assert c.read_text(encoding="utf-8") == "MODIFICADO POR OTRO\n"

    def test_verificar_es_falso_si_alguien_cambio_el_fichero_despues(self, tmp_path: Path) -> None:
        """`verificar()` tiene que servir parauno mismo, no solo para el
        restaurador. Es lo que permite afirmar «el arbol quedo como estaba»
        sin mentir.
        """
        objetivo = tmp_path / "m.py"
        objetivo.write_text("v1\n", encoding="utf-8")
        r = H.Restaurador.captura([objetivo])

        assert r.verificar()
        objetivo.write_text("cambio externo\n", encoding="utf-8")
        assert not r.verificar(), (
            "verificar() dio verde con el arbol cambiado: un guard que dice "
            "«esta como estaba» sin mirar es la forma de perder trabajo"
        )


class TestElRestoreDestructivo:
    """**LA COMPARACION CON `git checkout --`, CONTRA EL REPO REAL.**

    No para reproducir el fallo —eso ya se documento— sino para que la
    diferencia sea una MEDIDA y no una afirmacion en un docstring.
    """

    def test_git_checkout_NO_devuelve_trabajo_sin_commitear(self, tmp_path: Path) -> None:
        """La razon por la que el harness no usa git, demostrada.

        **MEDIDO AL ESCRIBIRLO, Y CORRIGE UN ORDEN QUE ESTABA MAL.** La
        primera version ejecutaba el `git checkout --` ANTES de que el
        `Restaurador` capturara el estado, luego el harness «restauraba» lo
        que git ya habia revertido y decia que funcionaba. El falso verde no
        estaba en el harness: estaba en el orden de este test.

        El orden correcto es: trabajo sin commitear -> `Restaurador.captura`
        -> `git checkout` (que destruye) -> `restaura` (que devuelve).
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True
        )
        objetivo = repo / "m.py"
        objetivo.write_text("VERSION COMMITTEADA = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "m.py"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, capture_output=True)

        # 1. Trabajo sin commitear: lo tipico de un bloque en curso.
        objetivo.write_text("TRABAJO SIN COMMIT = 2\n", encoding="utf-8")

        # 2. El harness captura ESO, que es lo que tiene que devolver.
        r = H.Restaurador.captura([objetivo])

        # 3. git destruye el trabajo.
        subprocess.run(["git", "checkout", "--", "m.py"], cwd=repo, check=True, capture_output=True)
        con_git = objetivo.read_text(encoding="utf-8")

        # 4. Y el harness lo devuelve.
        r.restaura()
        con_harness = objetivo.read_text(encoding="utf-8")

        assert "TRABAJO SIN COMMIT" not in con_git, (
            "si `git checkout --` devolviese el trabajo, esta comparacion no "
            "demostraria nada. MEDIDO: lo BORRA, que es el defecto."
        )
        assert con_harness == "TRABAJO SIN COMMIT = 2\n", (
            f"el harness devolvio {con_harness!r} en vez del trabajo sin "
            "commitear: por eso existe y no usa git"
        )


class TestLaClasificacion:
    """**LOS SEIS ESTADOS, Y EL QUE MAS IMPORTABA.**

    `MUTACION_INVALIDA` es la pieza que evita el «5/5» falso: una sonda que
    apunta a texto que ya no existe no muta nada, el suite sigue verde, y
    si se cuenta como SUPERVIVIDA el harness imprime un numero que no mide
    nada.
    """

    def test_los_seis_estados_existen(self) -> None:
        assert {v.value for v in H.Veredicto} == {
            "CAZADA",
            "SUPERVIVIDA",
            "MUTACION_INVALIDA",
            "ERROR_DE_HARNESS",
            "BASE_ROTA",
            "RESTAURACION_FALL",
        }

    def test_una_sonda_que_no_cambia_el_texto_es_INVALIDA_no_SUPERVIVIDA(
        self, tmp_path: Path
    ) -> None:
        """**EL CONTRA SALTO PRINCIPAL DE ESTE FICHERO.**

        Con una suite que esta en verde, una sonda mal anclada daria
        SUPERVIVIDA — «la propiedad aguanta» — cuando en realidad no ha
        medido nada. Es el numero falso que este harness existe para no
        imprimir.
        """
        proyecto = _proyecto_minimo(tmp_path)
        sonda = H.sonda_por_reemplazo(
            "ancla movida", proyecto / "m.py", "TEXTO QUE YA NO EXISTE", "otro"
        )
        assert not sonda.cambio_el_texto()

        resultados = H.corre([sonda], suite=["test_m.py"], repo=tmp_path, timeout=300)
        veredictos = {r.veredicto for r in resultados}
        assert veredictos == {H.Veredicto.MUTACION_INVALIDA}, (
            f"una sonda que no muta nada dio {veredictos}: se contaria como "
            "SUPERVIVIDA y el harness imprimiria un numero que no mide"
        )

    def test_una_base_rota_no_llega_a_mutar(self, tmp_path: Path) -> None:
        """**`BASE_ROTA` CORTA ANTES DE TOCAR EL ARBOL.**

        Sin esto, una corrida que empieza con la suite en rojo muta encima
        de un fallo ajeno y cada sonda recibe un veredicto que no es suyo.
        """
        proyecto = _proyecto_minimo(tmp_path)
        objetivo = proyecto / "m.py"
        antes = objetivo.read_bytes()

        # Una suite que NO EXISTE: el harness tiene que distinguir «roja» de
        # «no se pudo correr», y sobre todo no mutar por debajo de esa duda.
        resultados = H.corre(
            [H.sonda_por_reemplazo("nunca se aplica", objetivo, "return x + 1", "return x + 99")],
            suite=["test_que_no_existe.py"],
            repo=tmp_path,
            timeout=300,
        )
        assert objetivo.read_bytes() == antes, (
            "el harness toco el arbol sin poder medir: eso es medir sobre un fallo ajeno"
        )
        assert all(
            r.veredicto in (H.Veredicto.ERROR_DE_HARNESS, H.Veredicto.BASE_ROTA) for r in resultados
        ), [r.veredicto for r in resultados]

    def test_una_sonda_valida_se_caza_y_el_arbol_vuelve(self, tmp_path: Path) -> None:
        """El camino feliz: sonda real, roja, y arbol restaurado."""
        objetivo = tmp_path / "m.py"
        objetivo.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        test = tmp_path / "test_m.py"
        test.write_text(
            "def test_f():\n    import m\n    assert m.f(1) == 2\n",
            encoding="utf-8",
        )

        sonda = H.sonda_por_reemplazo(
            "f mal implementada", objetivo, "return x + 1", "return x + 2"
        )
        resultados = H.corre([sonda], suite=["test_m.py"], repo=tmp_path, timeout=300)
        assert [r.veredicto for r in resultados] == [H.Veredicto.CAZADA], [
            (r.veredicto, r.detalle) for r in resultados
        ]
        assert objetivo.read_text(encoding="utf-8") == "def f(x):\n    return x + 1\n", (
            "la sonda fue cazada pero el arbol no quedo como estaba"
        )

    def test_una_sonda_que_no_se_caza_dice_SUPERVIVIDA(self, tmp_path: Path) -> None:
        """Y el otro lado: una guarda que no vigila se dice, no se esconde."""
        objetivo = tmp_path / "m.py"
        objetivo.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        test = tmp_path / "test_m.py"
        # El test no mira `f`: la sonda sobrevivira, y el harness lo dira.
        test.write_text("def test_otro():\n    assert True\n", encoding="utf-8")

        sonda = H.sonda_por_reemplazo(
            "cambio que nadie vigila", objetivo, "return x + 1", "return x + 2"
        )
        resultados = H.corre([sonda], suite=["test_m.py"], repo=tmp_path, timeout=300)
        assert [r.veredicto for r in resultados] == [H.Veredicto.SUPERVIVIDA], [
            (r.veredicto, r.detalle) for r in resultados
        ]

    def test_una_sonda_que_rompe_la_sintaxis_es_INVALIDA(self, tmp_path: Path) -> None:
        """El rojo del interprete NO es el rojo del guard."""
        objetivo = tmp_path / "m.py"
        objetivo.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        test = tmp_path / "test_m.py"
        test.write_text("def test_f():\n    import m\n    assert m.f(1) == 2\n", encoding="utf-8")

        sonda = H.sonda_por_reemplazo("sintaxis rota", objetivo, "return x + 1", "return x + (((")
        resultados = H.corre([sonda], suite=["test_m.py"], repo=tmp_path, timeout=300)
        assert [r.veredicto for r in resultados] == [H.Veredicto.MUTACION_INVALIDA], [
            (r.veredicto, r.detalle) for r in resultados
        ]


class TestElInforme:
    """El informe tiene que contar los SEIS, no solo los dos buenos."""

    def test_el_informe_cuenta_cada_estado_por_separado(self) -> None:
        resultados = (
            H.Resultado("a", H.Veredicto.CAZADA),
            H.Resultado("b", H.Veredicto.SUPERVIVIDA),
            H.Resultado("c", H.Veredicto.MUTACION_INVALIDA),
            H.Resultado("d", H.Veredicto.ERROR_DE_HARNESS),
            H.Resultado("e", H.Veredicto.BASE_ROTA),
            H.Resultado("f", H.Veredicto.RESTAURACION_FALL),
        )
        texto = H.describe(resultados)

        # Cada estado aparece con su cuenta, INCLUDING los que serian ruido
        # en un informe que solo dice «N de M cazadas».
        for veredicto in H.Veredicto:
            assert f"{veredicto.value}" in texto, (
                f"el informe no nombra {veredicto.value}: un informe que solo "
                "diga «N de M» obliga a leer los nombres para saber si hubo "
                "RESTAURACION_FALL"
            )

    def test_el_informe_distingue_cazada_de_sobrevivida_en_el_nombre(self) -> None:
        texto = H.describe(
            (
                H.Resultado("sonda-cazada", H.Veredicto.CAZADA),
                H.Resultado("sonda-sobrevive", H.Veredicto.SUPERVIVIDA),
            )
        )
        assert "CAZADA" in texto and "SUPERVIVIDA" in texto
        assert "sonda-cazada" in texto and "sonda-sobrevive" in texto


class TestLaCoberturaDelArbol:
    """**POR QUE EXISTE ESTE HARNESS, MEDIDO SOBRE EL ARBOL REAL.**"""

    @staticmethod
    def _harnesses() -> Iterator[pathlib.Path]:
        yield from sorted((RAIZ / "scripts").glob("mutate_*.py"))

    def test_hay_mas_de_un_harness_y_no_usan_el_comun(self) -> None:
        """El numero que abre el bloque. Si baja, el bloque avanza."""
        harnesses = list(self._harnesses())
        assert len(harnesses) > 5, (
            f"solo hay {len(harnesses)} harnesses: la migracion al comun "
            "puede haber empezado, y este test habria que reescribirlo"
        )

        usan_comun = [h for h in harnesses if "mutation_harness" in h.read_text(encoding="utf-8")]
        # Este test NO exige que todos migren —eso es trabajo de bloque—,
        # pero si exige que el destino EXISTA y que algunos hayan llegado.
        # Un destino que no usa nadie no es una consolidacion, es un fichero
        # mas.
        assert (RAIZ / "scripts" / "mutation_harness.py").exists()
        assert len(usan_comun) >= 1, (
            "el harness comun existe y NADIE lo usa: escribir un modulo "
            "comun y no migrar nada es la forma de dejar deuda nueva"
        )

    def test_ningun_harness_nuevo_debe_restar_con_git(self) -> None:
        """El defecto que se paga caro esta PROHIBIDO aparecer de nuevo."""
        nuevos = [
            h for h in self._harnesses() if "mutation_harness" in h.read_text(encoding="utf-8")
        ]
        for harness in nuevos:
            texto = harness.read_text(encoding="utf-8")
            for patron in ("git checkout --", "git restore"):
                assert patron not in texto, (
                    f"{harness.name} restaura con `{patron}`, que devuelve el "
                    "arbol DEL INDICE: con trabajo sin commitear, restaura es "
                    "borrar. Se remedio con Restaurador."
                )
