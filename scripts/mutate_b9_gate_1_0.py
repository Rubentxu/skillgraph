#!/usr/bin/env python3
"""B9 — el harness de mutacion del arreglo de WAL y de la puerta de B2.

Que hace y por que existe
-------------------------
El arreglo de B9 son **dos** cosas, y las dos se pueden deshacer sin que
nadie se entere:

  1. `Storage._asegura_wal` — preguntar el modo antes de cambiarlo, releer
     entre reintentos y dormir entre ellos.
  2. La puerta de `test_b2_real_concurrency.py` — que el padre no abra hasta
     que los ocho hijos esten listos.

Las dos se pueden volver a su forma anterior sin romper ningun test, y por
eso este harness existe: no para certificar que hoy estan, sino para
certificar que **si alguien las deshace, algo se pone rojo**.

El fallo que este harness cierra, y que ya se cometio una vez
-----------------------------------------------------------------------
En B8 el harness de B8umento dejo escrito que «el arbol queda restaurado
byte a byte» y se conto como exito. No era cierto: el `.pyc` compilado con
la mutacion seguia ejecutandose. Restaurar el fichero no es restaurar el
proceso. Este harness, por eso:

  - borra `__pycache__` ANTES de mutar y DESPUES de restaurar;
  - y al final vuelve a pasar la suite entera, para que el ultimo veredicto
    sea el del codigo original y no el de un residuo.

Que tiene que demostrar cada sonda
----------------------------------
No basta con que la suite se ponga roja. Tiene que ponerse roja **por el
test que dice**, y no por el primero que encuentre: cuatro sondas que
heredan el fallo de la anterior dan un 4/4 que no se puede desarmar. Por
eso cada sonda lleva el conjunto de tests que se espera que caigan, y el
harness lo comprueba.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

#: Ficheros que se pueden mutar, y de donde se restaura cada uno. Se
#: restauran de `HEAD`, no de una copia hecha al empezar: una copia puede
#: tener el arbol ya sucio, y entonces el harness «restaura» el defecto y se
#: lo cuenta como verde.
MUTABLES = (
    RAIZ / "src" / "skillgraph" / "platform" / "storage.py",
    RAIZ / "src" / "skillgraph" / "platform" / "journal.py",
    RAIZ / "tests" / "test_b2_real_concurrency.py",
    RAIZ / "tests" / "fixtures" / "b2_concurrency_child.py",
)

SUITES = (
    "tests/test_b9_wal_lock.py",
    "tests/test_b2_real_concurrency.py",
)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo y los tests que TIENEN que caer con ella."""

    nombre: str
    fichero: str
    antes: str
    despues: str
    esperados: frozenset[str]


def _limpia_cache() -> None:
    for cache in RAIZ.rglob("__pycache__"):
        if ".venv" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)


def _sin_trabajo_sin_commitar() -> tuple[str, ...]:
    """Los mutables que tienen cambios SIN commitear, y por tanto se perderian.

    **ESTE GUARD EXISTE PORQUE SU AUSENCIA DESTRUYO TRABAJO, MEDIDO.**
    La primera version de este harness restauraba con `git checkout --`, que
    restaura **del indice**. Con el arreglo de B9 sin commitear —que es como
    esta mientras se esta escribiendo el bloque—, el primer `checkout` de la
    primera sonda se llevo por delante el arreglo entero: tres ficheros
    volvieron al estado previo al fix, las sondas M2 a M6 se encontraron sin
    texto que deformar, y el harness reporto «1 de 6 cazadas» sin decir que
    el 5 era el codigo que el propio harness habia borrado.

    Lo que lo hace especialmente malo es que **parecia funcionar**: la base
    se verifico verde, la primera sonda cazo, y el informe salio con un
    numero. Un harness que destruye elArbol y ademas imprime un veredicto
    es peor que no tener harness.

    Asi que el harness se niega a empezar si hay trabajo sin commitear en los
    ficheros que va a restaurar. No escomsodad: es que «restaurar» y
    «borrar» son la misma operacion si no hay nada commiteado debajo, y la
    unica manera de que no sean la misma es commitear antes.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(linea for linea in proc.stdout.splitlines() if linea.strip())


def _pytest(objetivos: tuple[str, ...]) -> tuple[int, set[str]]:
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *objetivos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    caidos = {
        linea.split("::", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED ")
    }
    return proc.returncode, caidos


#: El contenido de los ficheros mutables ANTES de que este harness toque nada.
ORIGINALES: dict[str, str] = {}


def _congela() -> None:
    """Lee los ficheros mutables una vez, antes de que el harness escriba."""
    for ruta in MUTABLES:
        ORIGINALES[str(ruta.relative_to(RAIZ))] = ruta.read_text(encoding="utf-8")


def _restaura() -> None:
    """Vuelve a lo que habia, ESCRIBIENDO. No pidiendo a git que lo haga.

    **B36: MEDIDO AL ABRIR EL BLOQUE, ESTO ERA `git checkout --`** con
    `cwd=RAIZ`, que restaura **del indice**. Con trabajo sin stagear debajo, el
    checkout devuelve el fichero a la ultima version commiteada y no a la que
    habia: es decir, se lo lleva. El docstring de este harness ya explicaba que
    asi perdio el arreglo de B9 entero, y su unica defensa era negarse a
    empezar cuando habia trabajo sin commitear.

    **La defensa correcta no es negarse a empezar: es no destruir.** Escribir lo
    que se leyo antes de mutar no puede perder nada, y deja que el harness se
    pueda usar con un arbol sucio —que es como se trabaja entre bloques.
    """
    for relativo, texto in ORIGINALES.items():
        (RAIZ / relativo).write_text(texto, encoding="utf-8")
    _limpia_cache()


def _sondas() -> tuple[Sonda, ...]:
    """Las deformaciones, derivadas del texto REAL de los ficheros.

    MEDIDO, y es el error 32 de WI-113 repetido: una sonda que apunta a un
    texto que ya no existe se cuenta como «no cazo», y eso se lee como «el
    guard aguanta» cuando lo que pasa es que el guard no se toco. Por eso
    cada sonda se **verifica contra el fichero antes de mutar**, y una sonda
    cuyo `antes` no esta en el fichero se considera un fallo del harness,
    no un fallo del codigo.
    """
    return (
        Sonda(
            nombre="M1_el_pragma_vuelve_a_escribirse_siempre",
            fichero="src/skillgraph/platform/journal.py",
            antes='if modo_de_journal(conexion) == "wal":',
            despues="if False:",
            esperados=frozenset(
                {
                    "TestLaBaseYaEstaEnWAL::test_reabrir_una_base_ya_en_wal_no_escribe_el_modo",
                    "TestLaBaseYaEstaEnWAL::test_el_modo_se_pregunta_antes_de_cambiarse",
                }
            ),
        ),
        Sonda(
            nombre="M2_un_solo_intento",
            fichero="src/skillgraph/platform/journal.py",
            antes="INTENTOS_WAL: Final[int] = 3",
            despues="INTENTOS_WAL: Final[int] = 1",
            esperados=frozenset(
                {"TestLaEsperaEsDelProcesoYNoDelDriver::test_hay_mas_de_un_intento"}
            ),
        ),
        Sonda(
            nombre="M3_sin_espera_entre_intentos",
            fichero="src/skillgraph/platform/journal.py",
            antes="ESPERA_ENTRE_INTENTOS_S: Final[float] = 0.01",
            despues="ESPERA_ENTRE_INTENTOS_S: Final[float] = 0.0",
            esperados=frozenset(
                {
                    "TestLaEsperaEsDelProcesoYNoDelDriver::"
                    "test_la_espera_entre_intentos_existe_y_es_positiva"
                }
            ),
        ),
        Sonda(
            nombre="M4_el_error_final_se_traga",
            fichero="src/skillgraph/platform/journal.py",
            antes=(
                "    # fallo visible a una base en `delete` que nadie sabe que esta en `delete`.\n"
                '    conexion.execute("PRAGMA journal_mode = WAL")\n'
            ),
            despues=(
                "    # fallo visible a una base en `delete` que nadie sabe que esta en `delete`.\n"
                "    try:\n"
                '        conexion.execute("PRAGMA journal_mode = WAL")\n'
                "    except sqlite3.OperationalError:\n"
                "        pass\n"
            ),
            esperados=frozenset(
                {"TestLaEsperaEsDelProcesoYNoDelDriver::test_el_error_final_no_se_traga"}
            ),
        ),
        Sonda(
            nombre="M5_el_padre_abre_sin_esperar_a_todos",
            fichero="tests/test_b2_real_concurrency.py",
            antes='if len(list(puerta.glob("listo-*"))) >= esperados:\n            break',
            despues="if True:\n            break",
            esperados=frozenset(
                {"TestLaBarreraDeLosHijos::test_el_padre_no_abre_antes_de_tener_todos"}
            ),
        ),
        Sonda(
            nombre="M6_el_hijo_no_espera_en_la_puerta",
            fichero="tests/fixtures/b2_concurrency_child.py",
            antes='    while not (puerta / "abre").exists():',
            despues="    while False:",
            esperados=frozenset(
                {"TestLaBarreraDeLosHijos::test_el_hijo_espera_en_la_puerta_y_no_antes"}
            ),
        ),
    )


def main() -> int:
    print("Harness de mutacion B9 — el arreglo de WAL y la puerta de B2")
    print("=" * 78)

    pendientes = _sin_trabajo_sin_commitar()
    if pendientes:
        # **B36: ESTE MOTIVO CAMBIO, Y ANTES MENTIA.** Decia que
        # `git checkout --` «BORRARIA el trabajo». Ya no restoration por checkout:
        # `_restaura()` escribe lo que leyo, luego no se pierde nada. Lo que
        # queda de este aviso es otro, mas pequeno: las sondas deforman el
        # texto REAL de estos ficheros, asi que con trabajo sin commitear
        # debajo el resultado mezcla tu cambio con el de la sonda y no sabes
        # que ha cazado. Se avisa igual, pero por el motivo que queda.
        print("ABORTO: hay cambios SIN COMMITAR en ficheros que este harness restaura.")
        print("        Las sondas deforman el texto REAL de estos ficheros, luego")
        print("        con trabajo debajo el resultado mezcla tu cambio con el de")
        print("        la sonda. Commitea antes de medir.")
        for linea in pendientes:
            print(f"        {linea}")
        return 2

    _limpia_cache()
    rc, _ = _pytest(SUITES)
    if rc != 0:
        print(f"ABORTO: la suite NO esta verde antes de mutar (rc={rc}).")
        return 2
    print("Base verificada: suite verde sin tocar nada.\n")

    _congela()  # antes del primer `_restaura()`: sin foto, no hay a que volver

    sondas = _sondas()
    causas: set[frozenset[str]] = set()
    sin_sonda: list[str] = []
    cazadas = 0

    for sonda in sondas:
        ruta = RAIZ / sonda.fichero
        original = ruta.read_text(encoding="utf-8")
        if sonda.antes not in original:
            sin_sonda.append(sonda.nombre)
            print(f"[SIN SONDA] {sonda.nombre}: el texto anterior no esta en {sonda.fichero}")
            print("             El harness esta mirando algo que ya no existe.")
            continue

        ruta.write_text(original.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
        _limpia_cache()
        rc, caidos = _pytest(SUITES)
        _restaura()

        if rc == 0 or not (sonda.esperados & caidos):
            print(f"[NO CAZADA] {sonda.nombre}: rc={rc}, cayeron {sorted(caidos)}")
            continue
        if not sonda.esperados <= caidos:
            print(f"[PARCIAL]   {sonda.nombre}: cayeron {sorted(caidos)}")
            print(f"             se esperaban {sorted(sonda.esperados)}")
            continue

        cazadas += 1
        causas.add(frozenset(caidos))
        print(f"[CAZADA]    {sonda.nombre}: {len(caidos)} tests en rojo")

    print()
    print(f"sondas cazadas: {cazadas}/{len(sondas)}")
    print(f"causas DISTINTAS: {len(causas)} (una por sonda = {cazadas} esperadas)")
    if sin_sonda:
        print(f"sin sonda: {sin_sonda}")
    if sondas and len(causas) != len(sondas):
        print(
            "AVISO: dos sondas comparten conjunto de tests. Una de las dos no esta "
            "midiendo lo que dice medir: o su guarda no muerde, o cae por otra causa."
        )

    # El ultimo veredicto tiene que ser el del codigo original. Sin esto, el
    # harness termina mudo y su ultimo estado conocido es una deformacion.
    _limpia_cache()
    rc, caidos = _pytest(SUITES)
    print()
    if rc == 0 and not caidos:
        print(f"Arbol restaurado y EJECUTANDO como estaba: {SUITES[0]} + {SUITES[1]} verdes.")
    else:
        print(f"ABORTO: tras restaurar, la suite sigue en rojo (rc={rc}, {sorted(caidos)}).")
        return 2
    return 0 if cazadas == len(sondas) and not sin_sonda else 1


if __name__ == "__main__":
    sys.exit(main())
