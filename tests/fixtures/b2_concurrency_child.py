"""B2 — el hijo que escribe desde su PROPIO proceso, contra la misma base.

    python .pipelinek/b2_concurrency_child.py --db RUTA --tag T --n N

Cada hijo abre su **propia** conexion a la misma base y escribe `n`
eventos. No comparte ni una linea de memoria con los demas: no hay GIL,
no hay hilo, no hay lock en Python. Lo unico que los une es el fichero
SQLite, que es exactamente la frontera que B2 quiere certificar.

**POR QUE PROCESOS Y NO THREADS, Y POR QUE ESTO NO ES UN DETALLE.** Con
threads, el GIL serializa el acceso al interprete: dos hilos no pueden
ejecutar bytecode a la vez, luego los tests de threads miden una
interleaving que **el sistema real no tiene**. Peor: un `sqlite3.connect`
creado en el hilo principal y usado en otro viola el uso previsto de la
libreria, y `Storage` tiene que pedir `check_same_thread=False` —que es
justo la concession que hace que el test mida algo que el producto no
hace—.

Con procesos, cada hijo es un programa independiente con su memoria, su
conexion y su transaccion. Si dos compiten por la misma fila, el conflicto
es real: es el del sistema de ficheros y el de SQLite, no el del GIL.

**LO QUE SE MIDE.** No «no se rompio», que es debil: se mide que **no se
pierde ninguna escritura**. Si los `n*n_procesos` eventos estan todos, la
base acepto la concurrencia. Si falta uno, hay una perdida silenciosa: el
escenario mas dificil de detectar en produccion, porque el run «funciona»
y solo falta un evento.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

#: MEDIDO EN B16, y no es cosmetica. Este calculo era `.parent.parent`, que
#: era correcto mientras el fichero vivia en `.pipelinek/` —ahi `.parent.parent`
#: es la raiz del repo— y dejo de serlo cuando se movio a `tests/fixtures/`, sin
#: que nadie lo tocara: ahi `.parent.parent` es `tests/`, luego la linea de
#: abajo metia `tests/src` en el path, que NO EXISTE. El hijo solo podia
#: importar `skillgraph` porque el paquete esta instalado en el interprete
#: que lo lanza; en cuanto no lo estuviera, los cinco tests de este modulo
#: caerian todos con `ModuleNotFoundError` —que es un fallo que dice «no se
#: puede» y no «el nucleo no aguanta ocho escritores».
#:
#: Lo que no se puede es que un arnes dependa de un accidente del entorno. Si
#: la intencion era —y la sigue siendo— probar el ARBOL DE TRABAJO y no lo
#: que este instalado, `parents[2]` la cumple. Y hoy no cambia nada, porque el
#: paquete se instala en modo editable y ya apunta al arbol: la diferencia se
#: ve el dia que alguien clone en limpio y lance con un interprete sin el
#: proyecto, y entonces el hijo debe poder importar su codigo.
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

# Este fichero TIENE que estar versionado: `tests/test_b2_real_concurrency.py`
# lo lanza como proceso y, si no viaja, los cinco tests de ese modulo fallan.
# Estuvo antes en `.pipelinek/`, que esta en `.gitignore`.
assert (RAIZ / "src" / "skillgraph").is_dir(), (
    f"el hijo no encuentra su codigo: {RAIZ / 'src' / 'skillgraph'} no existe. "
    f"Este fallo significa que el path de arriba no apunta a la raiz del repo, "
    f"y no que falte el paquete: son dos cosas distintas y se arreglan distinto."
)

# Las escrituras de cada hijo se separan en el tiempo a proposito: sin esta
# pausa, los hijos se serializan solos por el GIL del disco y el test
# mide concurrencia que no hubo. Con la pausa hay solape de verdad, que es
# lo que obliga a SQLite a usar su mecanismo de bloqueo.
#
# MEDIDO en B8: con 0.002 la ventana de cada hijo es de ~20 ms, y el
# ARRANQUE de ocho procesos de Python —importar `skillgraph.platform.storage`
# ocho veces a la vez— puede tardar mas que eso. Entonces el primero
# termina su trabajo antes de que el ultimo haya tomado su `inicio`, las
# ventanas no se cruzan, y el test falla DICIENDO QUE NO HUBO CONCURRENCIA
# cuando lo que no hubo fue solape. Medido: 1 fallo de 30 en solitario y 2
# de 4 en la suite completa, donde hay mas procesos compitiendo.
#
# Subir la pausa NO debilita lo que el test mide: si los hijos se
# serializaran, seguirian sin solaparse por muy anchas que sean sus
# ventanas. Lo que hace es que el solape sea estructural y no una carrera
# que se gana o se pierde.
PAUSA_S = 0.01

#: Cada cuanto se mira si la puerta se ha abierto. Es el unico sitio donde
#: hay espera, y espera a un FICHERO de otro proceso, no a un reloj.
SONDEO_S = 0.002

#: Cuanto se espera a la puerta antes de rendirse. Es un techo, no una
#: medida: si un hijo no llega, el padre abre la puerta igualmente y el
#: test falla luego por el hijo que falta, que es el fallo que dice algo.
PUERTA_TIMEOUT_S = 120.0


def _espera_en_la_puerta(puerta: Path, tag: str) -> None:
    """Anuncia que este hijo esta listo y espera a que el padre lo suelte.

    El fichero de listo se escribe ANTES de esperar, y el padre no abre la
    puerta hasta tener todos: asi la espera no depende de cuando llego el
    ultimo, sino de que llego.
    """
    (puerta / f"listo-{tag}").write_text("listo\n", encoding="utf-8")
    limite = time.monotonic() + PUERTA_TIMEOUT_S
    while not (puerta / "abre").exists():
        if time.monotonic() > limite:
            return
        time.sleep(SONDEO_S)


def main() -> int:
    ap = argparse.ArgumentParser(description="hijo que escribe N eventos en la base compartida")
    ap.add_argument("--db", required=True)
    ap.add_argument("--tag", required=True, help="identificador unico de este hijo")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--modo", default="escribir", choices=["escribir", "leer"])
    ap.add_argument(
        "--puerta",
        default=None,
        help="Directorio donde esperar a que el padre suelte a todos los hijos a la vez.",
    )
    args = ap.parse_args()

    from skillgraph.platform.storage import Storage

    if args.puerta is not None:
        _espera_en_la_puerta(Path(args.puerta), args.tag)

    # La ventana temporal de este hijo, para que el padre pueda medir si
    # hubo SOLAPE real entre procesos. Sin esto, «8 procesos en paralelo»
    # es una suposicion del arnes, no una medicion: si el padre los
    # lanzara en serie por accidente, el test de escritorias pasaria
    # igual —y pasaria por serializacion, que es justo lo que daria un
    # sistema que NO soporta concurrencia.
    #
    # Se toma DESPUES de la puerta, a proposito. Si se tomara antes, cada
    # hijo mediria desde su propio arranque y las ocho ventanas seguirian
    # dependiendo de cuando arranco cada uno, que es exactamente la carrera
    # que la puerta viene a quitar.
    inicio = time.monotonic()
    storage = Storage(args.db)
    try:
        if args.modo == "leer":
            _lee(storage, args.tag, args.n)
        else:
            _escribe(storage, args.tag, args.n)
    finally:
        storage.close()
        sys.stdout.write(
            f"SG_VENTANA {json.dumps({'tag': args.tag, 'inicio': inicio, 'fin': time.monotonic()})}\n"
        )
        sys.stdout.flush()
    return 0


def _escribe(storage: object, tag: str, n: int) -> None:
    """Escribe `n` eventos, cada uno en su propia transaccion.

    Una transaccion por evento, no una sola para todos: es lo que hace
    que dos hijos compitan de verdad. Con una unica transaccion por hijo,
    los hijos se serializan en el BEGIN y no hay conflicto que resolver.
    """
    events = storage.event_store()
    for i in range(n):
        events.record_event(
            tenant_id="t",
            project_id="p",
            event_id=f"ev-{tag}-{i}",
            event_kind="NodeScheduled",
            resource_ref=f"ref://b2/{tag}",
            payload={"i": i, "tag": tag},
            run_id=None,
            timestamp="2026-10-03T00:00:00Z",
        )
        time.sleep(PAUSA_S)


def _lee(storage: object, tag: str, n: int) -> None:
    """Lector: `list_events` sobre una base que otros estan escribiendo.

    El lector es la mitad de la prueba de `read/write`. Con WAL, un lector
    no debe bloquear al escritor ni ver una base a medias; sin WAL, este
    test seria el que lo detectaria.
    """
    for _ in range(max(1, n // 2)):
        storage.event_store().list_events(tenant_id="t", project_id="p")
        time.sleep(PAUSA_S)


if __name__ == "__main__":
    raise SystemExit(main())
