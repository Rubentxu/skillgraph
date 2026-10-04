"""B2 — concurrencia REAL: procesos separados, SQLite real, locks reales.

Este fichero certifica la segunda mitad del gate de B2, y **encontró un
defecto de produccion en el camino**. El defecto, medido:

```
8 procesos abriendo la misma base a la vez, con el codigo de ANTES:

  fallos: 1
  File "src/skillgraph/platform/storage.py", line 214, in __init__
  sqlite3.OperationalError: database is locked
  eventos: 70   (esperados 80)
```

Ocho procesos, diez escrituras cada uno, y **diez eventos perdidos sin
dejar rastro**: no hay excepcion en el padre, no hay log, no hay nada. El
proceso que fallo murio en su `Storage(...)` antes de escribir, y el run
sigue «funcionando» —solo que le faltan eventos.

**LA CAUSA, Y POR QUE ERA INVISIBLE.** `Storage.__init__` ejecuta
`PRAGMA journal_mode = WAL`, y ese PRAGMA **toma un lock de escritura
sobre la base**. Es idempotente —la base ya esta en WAL y el PRAGMA no
hace nada— pero sigue necesitando el lock para saberlo. Con dos procesos
abriendo a la vez, uno espera; y como no habia `busy_timeout`, no espera:
falla.

`sqlite3.connect` tiene un `timeout` de 5 s **por defecto**, asi que
parecia que habia uno. No lo habia: el default se aplica a las
operaciones, pero el `PRAGMA journal_mode` se lanza durante la
construccion del objeto, en un momento en que la gestion de reintentos
de Python todavia no protege al llamante de forma util. El arreglo es
**pasar el `timeout` explicitamente al `connect`**, de modo que el PRAGMA
nasca dentro de la politica de espera en vez de fuera.

**LO QUE ESTE FICHERO MIDE, Y POR QUE NO BASTA CON «NO SE ROMPIO».** La
pregunta debil es «¿el programa se rompio?». La fuerte es **«¿se perdio
alguna escritura?»**. Un defecto de concurrencia que pierde una fila de
veinte es invisible: el run termina, la base abre, `integrity_check` dice
`ok`, y nadie se entera hasta que alguien busca un evento que no
encuentra. Por eso estos tests comparan **el numero exacto** de filas
contra el numero exacto de escritores, y por eso hay un test que exige
que los hijos **realmente** se solapen en el tiempo.

**Y POR QUE PROCESOS, NO THREADS.** Con threads, el GIL serializa el
bytecode: dos hilos no se ejecutan a la vez, luego el test mide una
interleaving que el sistema real no tiene. Ademas, un `sqlite3.connect`
usado desde dos hilos obliga a `check_same_thread=False`, que es la
concesion que hace que el test mida algo que el producto no hace. Con
procesos, cada hijo es un programa aparte con su memoria, su conexion y
su transaccion, y lo unico que los une es el fichero —que es la frontera
que B2 quiere certificar—.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# El hijo se LITERALMENTE tiene que estar junto a este test, y en el
# arbol de git. Antes vivia en `.pipelinek/`, que esta en `.gitignore`:
# el test estaba versionado pero su hijo no, y MEDIDO clon en limpio eso
# hace que los cinco tests de este modulo fallen con FileNotFoundError.
# Un test que solo funciona en la maquina donde se escribio no es un test.
CHILD = Path(__file__).resolve().parent / "fixtures" / "b2_concurrency_child.py"

#: Los valores de la espera se IMPORTAN del hijo y no se reescriben aqui.
#: El padre y el hijo tienen que esperar lo mismo, y dos constantes con el
#: mismo numero en dos ficheros son dos numeros que divergen el dia que
#: uno se cambia. Importarlo de mas tiene un efecto secundario que vale:
#: si el hijo dejara de ser importable, este modulo ni siquiera carga, y el
#: fallo se ve al arrancar y no tres minutos despues dentro del arnes.
_especificacion = importlib.util.spec_from_file_location("_b2_hijo", CHILD)
assert _especificacion is not None and _especificacion.loader is not None
_hijo = importlib.util.module_from_spec(_especificacion)
sys.modules[_especificacion.name] = _hijo
_especificacion.loader.exec_module(_hijo)
PUERTA_TIMEOUT_S: float = _hijo.PUERTA_TIMEOUT_S
SONDEO_S: float = _hijo.SONDEO_S

# Procesos y escrituras por proceso. Ocho x diez = 80 filas esperadas.
#
# **POR QUE 8 Y NO 2.** Con dos, la ventana de colision en el `PRAGMA` es
# estrecha y el defecto aparece de forma intermitente: un test que falla
# una vez de cada tres no es un guard, es una moneda. Con ocho, la
# probabilidad de que al menos dos caigan en la ventana es alta y el
# defecto se ve SIEMPRE. Un guard intermitente es peor que no tener guard,
# porque entrena a leer el «a veces pasa» como ruido.
PROCESOS = 8
POR_PROCESO = 10
TOTAL_ESPERADO = PROCESOS * POR_PROCESO


def _procesos(db: Path, n: int, modo: str = "escribir") -> list[tuple[int, str, str]]:
    """Lanza `n` hijos A LA VEZ y devuelve (returncode, stdout, stderr).

    Se lanzan sin esperar entre ellos a proposito: `Popen` en bucle y
    `communicate` despues es lo que hace que compitan de verdad. Lanzarlos
    en serie —uno, esperar, otro— serializaria el test y no probaria
    nada.

    **LA PUERTA, Y POR QUE NO BASTA CON LANZARLOS A LA VEZ.** Lanzar ocho
    procesos en un bucle NO los hace competir: los hace empezar, y cada uno
    tarda lo que tarde en arrancar el interprete e importar
    `skillgraph.platform.storage`. Ese arranque es el mismo para todos en
    teoria y en la practica no lo es, y la diferencia crece con la carga
    de la maquina. MEDIDO en B9: con los ocho hijos esperando en una puerta
    comun y soltados a la vez, el solape es estructural. Sin ella, el test
    de solape fallo 1 de las 5 corridas del medidor del gate de 1.0 con la
    maquina ocupada, y 0 de 10 en solitario. Un fallo que solo aparece
    cuando la maquina esta ocupada es un fallo, y la puerta lo quita en
    vez de taparlo con una ventana mas ancha.

    La puerta es un directorio: cada hijo escribe su fichero de «listo» y
    espera a que aparezca `abre`. El padre no abre hasta que estan todos, o
    hasta que se acaba el plazo, en cuyo caso abre igual: asi un hijo que
    no llega produce un fallo que NOMBRA al hijo que falta, en vez de un
    cuelgue del arnes.
    """
    puerta = db.parent / f"puerta-{modo}"
    puerta.mkdir(parents=True, exist_ok=True)
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                str(CHILD),
                "--db",
                str(db),
                "--tag",
                f"h{i}",
                "--n",
                str(POR_PROCESO),
                "--modo",
                modo,
                "--puerta",
                str(puerta),
            ],
            cwd=RAIZ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(n)
    ]
    _abre_la_puerta(puerta, n)
    salidas = []
    for p in procs:
        out, err = p.communicate(timeout=180)
        salidas.append((p.returncode, out, err))
    return salidas


def _abre_la_puerta(puerta: Path, esperados: int) -> bool:
    """Espera a que los `esperados` hijos esten listos y abre la puerta.

    Devuelve si llegaron todos. El valor no se usa para decidir el
    veredicto: el veredicto lo dan los hijos, que si uno no llego fallara
    al no tener ventana o al morirse. Aqui solo se decide si abrir ya o
    seguir esperando.
    """
    limite = time.monotonic() + PUERTA_TIMEOUT_S
    while time.monotonic() < limite:
        if len(list(puerta.glob("listo-*"))) >= esperados:
            break
        time.sleep(SONDEO_S)
    todos = len(list(puerta.glob("listo-*"))) >= esperados
    (puerta / "abre").write_text("abre\n", encoding="utf-8")
    return todos


def _filas(db: Path) -> int:
    import sqlite3

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0])
    finally:
        conn.close()


def _integridad(db: Path) -> str:
    import sqlite3

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


class TestNadiePierdeEscrituras:
    """La propiedad fuerte, y la que un failpoint no puede dar."""

    def test_ocho_procesos_escriben_y_no_se_pierde_nada(self, tmp_path: Path) -> None:
        """80 filas, 80 escrituras. Si falta una, hay una perdida silenciosa.

        Este es el test que **estaba en rojo** antes del arreglo, con 70
        de 80. El mensaje nombra el numero bueno porque un verificador
        que dice «falso» sin decir «cuanto» deja al que corrige haciendo
        la cuenta a mano.
        """
        db = tmp_path / "p.sqlite"
        salidas = _procesos(db, PROCESOS)
        fallidos = [(rc, err) for rc, _, err in salidas if rc != 0]
        assert not fallidos, (
            f"{len(fallidos)} de {PROCESOS} procesos murieron. El primero:\n"
            f"{fallidos[0][1][-400:]}\n\n"
            "Un proceso que muere al abrir la base se lleva SUS escrituras: "
            "no hay excepcion en el padre ni registro de que faltara nada."
        )
        filas = _filas(db)
        assert filas == TOTAL_ESPERADO, (
            f"se esperaban {TOTAL_ESPERADO} eventos ({PROCESOS} procesos x "
            f"{POR_PROCESO}) y hay {filas}. Perder escrituras en silencio es "
            "el defecto mas dificil de ver en produccion: el run termina, "
            "la base abre, y lo que falta es un evento que nadie busca."
        )

    def test_la_base_queda_integra_despues_de_la_concurrencia(self, tmp_path: Path) -> None:
        """Que 8 escritores no dejen la base ilegible."""
        db = tmp_path / "p.sqlite"
        _procesos(db, PROCESOS)
        assert _integridad(db) == "ok"

    def test_cada_proceso_escribe_su_propio_conjunto(self, tmp_path: Path) -> None:
        """Que el total correcto no venga de que dos hijos escribieron lo mismo.

        Un `event_id` duplicado lo impediria el `UNIQUE`, pero un
        `resource_ref` repetido pasaria el recuento. Este test ata cada
        fila a su escritor: `PROCESOS` autores distintos, `POR_PROCESO`
        filas cada uno.
        """
        import sqlite3

        db = tmp_path / "p.sqlite"
        _procesos(db, PROCESOS)
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            autores = conn.execute(
                "SELECT resource_ref, COUNT(*) FROM runtime_events GROUP BY resource_ref"
            ).fetchall()
        finally:
            conn.close()
        assert len(autores) == PROCESOS, (
            f"se esperaban {PROCESOS} autores distintos y hay {len(autores)}: "
            f"{autores}. El total puede cuadrar y ser la MISMA fila contada."
        )
        assert all(n == POR_PROCESO for _, n in autores), f"reparto desigual: {autores}"


class TestLosHijosSeSolapanDeVerdad:
    """Sin solape real, todo lo de arriba mide concurrencia que no hubo."""

    def test_los_hijos_tienen_solape_en_el_tiempo(self, tmp_path: Path) -> None:
        """Que dos hijos estuvieran vivos a la vez, no uno tras otro.

        Se mide por el intervalo `sg_inicio..sg_fin` que cada hijo
        imprime. Si los intervalos no se cruzan, los hijos se
        serializaron y el test de arriba paso sin probar nada: serializar
        es el resultado que se obtiene tambien cuando el sistema **no**
        soporta concurrencia, asi que un test verde sin solape no
        distingue las dos cosas.
        """
        import json

        db = tmp_path / "p.sqlite"
        salidas = _procesos(db, PROCESOS)
        ventanas = []
        for rc, out, err in salidas:
            assert rc == 0, (
                f"un hijo fallo antes de poder medir el solape: rc={rc}. "
                f"Sin su stderr esto no dice nada: en B16 el fallo real era un "
                f"`IntegrityError` de la migracion, y el mensaje no lo decia: se "
                f"buscaba en el producto lo que estaba en la ultima linea del "
                f"hijo.\n"
                f"--- stderr del hijo ---\n{err.strip()[-2000:]}\n---------------------"
            )
            marca = [linea for linea in out.splitlines() if linea.startswith("SG_VENTANA ")]
            assert marca, f"el hijo no declaro su ventana temporal: {out[-300:]}"
            d = json.loads(marca[0][len("SG_VENTANA ") :])
            ventanas.append((d["inicio"], d["fin"]))
        solapes = 0
        for i, (a1, f1) in enumerate(ventanas):
            for a2, f2 in ventanas[i + 1 :]:
                if a1 < f2 and a2 < f1:
                    solapes += 1
        assert solapes > 0, (
            f"ningun par de hijos se solapo en el tiempo: {ventanas}. "
            "El test de escrituras habria pasado por serializacion, que es "
            "lo que pasa TAMBIEN cuando el sistema no aguanta concurrencia."
        )


class TestLectoresConcurrentes:
    """`read/write`, la mitad de WAL que B1 no podia mirar."""

    def test_leer_mientras_ocho_escriben_no_rompe_nada(self, tmp_path: Path) -> None:
        """Con WAL, un lector no bloquea al escritor.

        Este test **no puede** afirmar hoy la garantia completa de WAL
        (lectores que no bloquean a los escritores), porque el lector puede
        terminar antes de que empiece el escritor. Lo que si afirma —y lo
        que antes fallaba— es que la combinacion no rompe ni la base ni
        las escrituras.
        """
        db = tmp_path / "p.sqlite"
        escritores = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(CHILD),
                    "--db",
                    str(db),
                    "--tag",
                    f"w{i}",
                    "--n",
                    str(POR_PROCESO),
                    "--modo",
                    "escribir",
                ],
                cwd=RAIZ,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for i in range(PROCESOS)
        ]
        lectores = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(CHILD),
                    "--db",
                    str(db),
                    "--tag",
                    f"r{i}",
                    "--n",
                    str(POR_PROCESO),
                    "--modo",
                    "leer",
                ],
                cwd=RAIZ,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for i in range(2)
        ]
        fallos = []
        for p in escritores + lectores:
            _, err = p.communicate(timeout=180)
            if p.returncode != 0:
                fallos.append(err[-300:])
        assert not fallos, f"{len(fallos)} procesos de lectura/escritura fallaron:\n{fallos[0]}"
        assert _filas(db) == TOTAL_ESPERADO, (
            f"con lectores en medio quedan {_filas(db)} de {TOTAL_ESPERADO} escrituras"
        )
        assert _integridad(db) == "ok"
