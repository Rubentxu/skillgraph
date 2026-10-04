"""B9 — el arreglo de WAL, y por que necesita un guard que no dependa del fallo.

**EL DEFECTO, MEDIDO, Y POR QUE NO SE VEIA.** B2 abrio ocho procesos sobre la
misma base y perdio diez eventos de ochenta sin excepcion en el padre. La
causa era `PRAGMA journal_mode = WAL` en `Storage.__init__`: el PRAGMA es
idempotente, pero **toma un lock de escritura para averiguar que no hace
nada**, y con ocho aperturas a la vez uno moria con `database is locked`
antes de escribir una sola fila.

B2 lo arreglo con un reintento. Y el reintento fue **insuficiente**, medido
en B9: 1 ronda de 12 seguia fallando, con 3 de 8 hijos muertos y 50 de 80
filas. Dos intentos pegados caen en la misma ventana que el primero, porque
`journal_mode` no honra el `busy_timeout` del `connect` —devuelve
`SQLITE_BUSY` de inmediato—, asi que esperar es cosa nuestra y no del
driver.

El arreglo que si cierra el problema tiene tres partes:

1. **Preguntar antes de cambiar.** `PRAGMA journal_mode` sin `= WAL` es una
   lectura, y una lectura no pide el lock exclusivo. Una base ya en WAL —el
   caso normal, y el unico que importa con concurrencia— no toca el lock de
   escritura ni una vez.
2. **Releer entre reintentos**, para que el que pierde el cambio se salga
   en vez de seguir peleando contra un modo que otro ya cambio.
3. **Dormir entre reintentos**, para que el ganador tenga tiempo de
   terminar su conversion.

**POR QUE HACE FALTA UN GUARD, Y POR QUE ESTE NO MIDE EL FALLO.** Un test
que abre ocho procesos y mira que no mueren seria una moneda: cuando pasa
no prueba que el arreglo este, y cuando falla dice que lo esta. Y no se
puede tapar subiendo un tiempo de espera, porque aqui no hay un tiempo de
espera que mover: lo que se arreglo es una pregunta que no hacia falta.

Lo que si se mide de forma estable son las tres **propiedades** del
arreglo. Y se miden por su efecto, no por su codigo: se mira que pasa por
la conexion, que es donde se nota la diferencia entre preguntar y escribir.

**POR QUE NO SE MONKEYPATCHEA `sqlite3.Connection`.** Porque es un tipo de
la extension y `setattr` sobre el revienta. Lo que se usa es
`set_trace_callback`, que es la via que la propia libreria ofrece para ver
que SQL pasa por una conexion, y `monkeypatch` sobre `sqlite3.connect`,
que si es un atributo de modulo y se puede sustituir.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
import time
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from skillgraph.platform.storage import Storage  # noqa: E402

#: El SQL de la LECTURA del modo, y el del CAMBIO. Se comparan con
#: espacios normalizados porque `sqlite3` no reescribe lo que se le pasa.
LEE_MODO = "pragma journal_mode"
ESCRIBE_MODO = "pragma journal_mode = wal"


def _normaliza(sql: str) -> str:
    return " ".join(sql.strip().lower().split())


@pytest.fixture
def sql_por_conexion(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Todo el SQL que pasa por cualquier conexion que se abra durante el test.

    Se sustituye `sqlite3.connect` por una envoltura que engancha un
    `set_trace_callback` a cada conexion que devuelve. Es observacion, no
    intervencion: la conexion es la de verdad y ejecuta el SQL de verdad.
    """
    registro: list[str] = []
    original = sqlite3.connect

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conexion = original(*args, **kwargs)
        conexion.set_trace_callback(lambda sql: registro.append(_normaliza(sql)))
        return conexion

    monkeypatch.setattr(sqlite3, "connect", connect)
    return registro


def _modo(db: Path) -> str:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        fila = conn.execute("PRAGMA journal_mode").fetchone()
        return str(fila[0]).lower() if fila is not None else ""
    finally:
        conn.close()


def _filas(db: Path) -> int:
    """Cuantas filas hay en `runtime_events`, o 0 si la tabla aun no existe."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        fila = conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()
        return int(fila[0]) if fila is not None else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


class TestLaBaseYaEstaEnWAL:
    """La propiedad que mas importa: una base en WAL no se vuelve a preguntar."""

    def test_una_base_creada_por_storage_queda_en_wal(self, tmp_path: Path) -> None:
        """El invariante: `Storage` deja la base en WAL. Sin el, no hay nada.

        Es el contrasalto de los otros dos: sin esta, «no se cambia el modo
        cuando ya esta en WAL» se cumpliria igual en una base que nunca
        estuvo en WAL, que es una base donde la propiedad no dice nada.
        """
        db = tmp_path / "p.sqlite"
        with Storage(db):
            pass
        assert _modo(db) == "wal", "Storage dejo la base fuera de WAL"

    def test_reabrir_una_base_ya_en_wal_no_escribe_el_modo(
        self, tmp_path: Path, sql_por_conexion: list[str]
    ) -> None:
        """El caso que rompia ocho procesos, medido aqui sin ocho procesos.

        No se mide si la base ACABA en WAL —eso lo mide el test de arriba—,
        sino si se **reescribe** el modo, que es distinto: una base que
        acaba en WAL puede haber pasado por cinco reescrituras. Lo que se
        mide es que no se reescriba, y eso es lo que evita el lock.
        """
        db = tmp_path / "p.sqlite"
        with Storage(db):
            pass

        sql_por_conexion.clear()
        with Storage(db):
            pass

        escrituras = [s for s in sql_por_conexion if _normaliza(ESCRIBE_MODO) == s]
        assert escrituras == [], (
            "reabrir una base ya en WAL ejecuto el PRAGMA de escritura: "
            f"{escrituras}. Ese PRAGMA es idempotente y aun asi pide un lock "
            "exclusivo, y ese lock es exactamente lo que hacia morir a los "
            "ocho procesos a la vez."
        )

    def test_el_modo_se_pregunta_antes_de_cambiarse(
        self, tmp_path: Path, sql_por_conexion: list[str]
    ) -> None:
        """Que exista la LECTURA, no solo que el cambio no ocurra.

        MEDIDO: el test de arriba mide el efecto y este mide el mecanismo, y
        los dos hacen falta, porque un efecto correcto puede venir de un
        mecanismo equivocado. Un `except: repetir` sin la lectura puede dar
        verde el test de arriba en una maquina donde el PRAGMA idempotente
        parece que no pide lock — y volveria a pedirlo en la de al lado.
        """
        db = tmp_path / "p.sqlite"
        with Storage(db):
            pass

        sql_por_conexion.clear()
        with Storage(db):
            pass

        lecturas = [s for s in sql_por_conexion if s == LEE_MODO]
        assert lecturas, (
            "no se lee el modo de journal antes de decidir cambiarlo: sin la "
            "lectura el unico camino es escribir, y escribir es el defecto"
        )


class TestLaEsperaEsDelProcesoYNoDelDriver:
    """Por que hay un `time.sleep`, y por que el reintento tiene que releer."""

    def test_hay_mas_de_un_intento(self) -> None:
        """Un solo intento es el defecto original, con otro nombre.

        El contrasalto tiene que existir aunque hoy el numero valga: lo que
        se vigila es que nadie lo baje a 1 creyendo que la lectura previa
        basta. Y no basta —MEDIDO: sin dormir entre intentos, el fallo
        seguia saliendo—, y este test es el que lo dice.

        Se lee de `platform.journal` y no de `Storage`, porque el arreglo
        vive ahi: `Storage` es la fachada y solo delega. Un guard que
        mirara la fachada no distinguiria «la politica desaparecio» de
        «la politica se movio», y se pondria rojo por un refactor que no
        toco el comportamiento.
        """
        from skillgraph.platform import journal

        assert journal.INTENTOS_WAL > 1, (
            f"journal.INTENTOS_WAL == {journal.INTENTOS_WAL}: con un solo "
            "intento, ocho procesos abriendo una base nueva vuelven a perder "
            "escrituras, que es el defecto que B2 vino a cerrar"
        )

    def test_la_espera_entre_intentos_existe_y_es_positiva(self) -> None:
        """`journal_mode` ignora el `busy_timeout`; sin dormir no hay reintento.

        MEDIDO en B9: con tres intentos PEGADOS el fallo seguia saliendo
        (1 ronda de 12, 3 de 8 hijos muertos). Los tres caian en el mismo
        instante, antes de que el ganador terminase. Dormir entre ellos es
        la diferencia entre reintentar y volver a chocar.
        """
        from skillgraph.platform import journal

        assert journal.ESPERA_ENTRE_INTENTOS_S > 0, (
            "sin espera entre intentos, los reintentos caen en la misma "
            "ventana que el primer intento y no son un reintento"
        )

    def test_el_error_final_no_se_traga(self, tmp_path: Path) -> None:
        """Si el modo no se puede cambiar, la excepcion sube.

        Es la frontera que el arreglo declara: tragarse el error y seguir
        seria afirmar que la base esta en WAL sin haberlo comprobado, que es
        la clase de mentira que este bloque mide.

        Se fuerza con una base **de solo lectura y en modo `delete`**, que
        es la unica combinacion donde el cambio de modo falla de verdad sin
        necesitar otro proceso: hay que cambiarlo y no se puede. Y el modo
        se pone a mano, no con `Storage`, para que el fallo sea del cambio de
        modo y no de otra cosa.
        """
        db = tmp_path / "p.sqlite"
        conexion = sqlite3.connect(str(db))
        try:
            conexion.execute("PRAGMA journal_mode = DELETE")
            conexion.execute("CREATE TABLE t(x)")
            conexion.commit()
        finally:
            conexion.close()
        os.chmod(db, stat.S_IRUSR)  # type: ignore[arg-type]
        try:
            assert _modo(db) == "delete", "el caso de prueba no esta en delete"
            with pytest.raises(sqlite3.OperationalError):
                Storage(db)
        finally:
            os.chmod(db, stat.S_IRUSR | stat.S_IWUSR)  # type: ignore[arg-type]


class TestLaBarreraDeLosHijos:
    """La otra mitad del arreglo: que el solape sea estructural y no una carrera.

    Se prueba que el padre ESPERA a que todos los hijos esten listos antes de
    abrirles la puerta. Sin esa espera, el padre abriria en cuanto viera al
    primero, que es volver a la carrera de siempre con otro envoltorio.
    """

    def test_el_hijo_espera_en_la_puerta_y_no_antes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La puerta no se abre sola: el hijo tiene que ver el fichero.

        Se arranca un hijo de verdad contra la puerta, se espera a que
        anuncie que esta listo, y se comprueba que sigue vivo y sin hacer
        nada mientras `abre` no existe. Un hijo que no respeta la puerta
        volveria a mide desde su propio arranque, que es la carrera que la
        puerta viene a quitar.
        """
        import subprocess

        hijo = RAIZ / "tests" / "fixtures" / "b2_concurrency_child.py"
        db = tmp_path / "p.sqlite"
        puerta = tmp_path / "puerta"
        puerta.mkdir()
        # Se pre-crea la base para que el hijo no compita por crearla: aqui
        # lo que se mide es la PUERTA, no la creacion concurrente, que tiene
        # sus propios tests en el modulo de WAL.
        with Storage(db):
            pass

        proc = subprocess.Popen(
            [
                sys.executable,
                str(hijo),
                "--db",
                str(db),
                "--tag",
                "h0",
                "--n",
                "3",
                "--puerta",
                str(puerta),
            ],
            cwd=RAIZ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            # MEDIDO, y este es el bug que hacia intermitente a ESTE test:
            # la primera version sumaba `waited += 0.01` en vez de DORMIR.
            # Sin el `sleep`, el bucle consumia los 60 s de plazo en
            # milisegundos, se rendia antes de que el hijo llegara, y
            # fallaba ~1 de cada 6. Un fallo intermitente en el guard del
            # guard es la peor combinacion: entrena a leer el «a veces
            # pasa» como ruido, que es justo lo que este bloque dice que
            # hace un guard intermitente.
            limite = time.monotonic() + 60.0
            while not (puerta / "listo-h0").exists() and time.monotonic() < limite:
                assert proc.poll() is None, (
                    f"el hijo murio antes de llegar a la puerta: rc={proc.returncode}"
                )
                time.sleep(0.01)
            assert (puerta / "listo-h0").exists(), "el hijo no anuncio que estaba listo"

            # **POR QUE SE MIDE LA BASE Y NO EL PROCESO.** La primera
            # version comprobaba `proc.poll() is None`: que el hijo siga
            # vivo. Y la sonda M6 —que le quita la espera al hijo— NO la
            # cazo, porque un hijo sin puerta tarda ~30 ms en terminar sus
            # tres escrituras y el test lo mira antes. Un hijo vivo que ya
            # esta trabajando es justo lo que hay que cazar, y «vivo» no lo
            # distingue de «esperando».
            #
            # Lo que los separa es si ha escrito algo: la puerta esta
            # cerrada, luego un hijo que la respeta tiene cero filas. Y se
            # espera un segundo antes de mirar, porque el hijo sin puerta
            # necesita abrir la base antes de poder escribir: mirarlo en el
            # instante en que anuncia «listo» seria medir el arranque, no
            # la espera. Un segundo es de sobra para lo que se quiere
            # distinguir y no hace el test intermitente.
            time.sleep(1.0)
            assert _filas(db) == 0, (
                f"el hijo escribio {_filas(db)} filas con la puerta CERRADA: no esta "
                "esperando a que el padre lo suelte, y su ventana empieza desde su "
                "propio arranque, que es la carrera que la puerta viene a quitar"
            )
        finally:
            (puerta / "abre").write_text("abre\n", encoding="utf-8")
            proc.communicate(timeout=60)

    def test_el_padre_no_abre_antes_de_tener_todos(self, tmp_path: Path) -> None:
        """Con dos de tres, el padre SIGUE ESPERANDO, y se mide que espera.

        **POR QUE SE MIDE CON UN HILO Y NO CON EL VALOR DE RETORNO.** La
        primera version solo comprobaba que `_abre_la_puerta` devolviera
        `False` con dos de tres. Y la sonda M5 —que hace que el padre rompa
        el bucle en la primera iteracion— NO la cazo, porque el valor de
        retorno es el MISMO: se mide cuantos ficheros hay al terminar, y eso
        no cambia por abrir antes. Un guard que mide el resultado de una
        funcion y no su comportamiento mide la mitad de la funcion.

        Asi que el tercero llega TARDE, desde un hilo, y lo que se mide es
        si al volver el padre ya lo tiene delante. Si abre en cuanto ve a
        los dos primeros, vuelve antes de que el hilo escriba, y el
        `listo-h2` no esta.
        """
        import importlib.util
        import threading

        especificacion = importlib.util.spec_from_file_location(
            "_b2_padre", RAIZ / "tests" / "test_b2_real_concurrency.py"
        )
        assert especificacion is not None and especificacion.loader is not None
        padre = importlib.util.module_from_spec(especificacion)
        sys.modules[especificacion.name] = padre
        especificacion.loader.exec_module(padre)

        puerta = tmp_path / "puerta"
        puerta.mkdir()
        for etiqueta in ("listo-h0", "listo-h1"):
            (puerta / etiqueta).write_text("listo\n", encoding="utf-8")

        def llega_tarde() -> None:
            time.sleep(0.3)
            (puerta / "listo-h2").write_text("listo\n", encoding="utf-8")

        hilo = threading.Thread(target=llega_tarde)
        hilo.start()
        try:
            padre._abre_la_puerta(puerta, 3)
            # **EL ESTADO SE MIRA EN EL INSTANTE DEL RETORNO, NO DESPUES.**
            # MEDIDO: la primera version hacia `hilo.join()` en el `finally`
            # y comprobaba despues. Con eso el hilo ya habia escrito su
            # fichero para cuando se miraba, y la sonda M5 —que hace que el
            # padre rompa el bucle en la primera iteracion— pasaba en verde.
            # Un guard que espera a que pase lo que quiere medir, mide que lo
            # que quiere medir ya ha pasado.
            tercero_llego = (puerta / "listo-h2").exists()
        finally:
            hilo.join()

        assert (puerta / "abre").exists(), "el padre nunca abrio la puerta: el arnes se cuelga"
        assert tercero_llego, (
            "el padre abrio y volvio ANTES de que el tercer hijo anunciara "
            "estar listo: el que no ha llegado sale cuando le de la gana, que "
            "es la carrera original. Con dos de tres, el padre tiene que "
            "seguir esperando."
        )
