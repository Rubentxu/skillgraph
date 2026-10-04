#!/usr/bin/env python3
"""B10 — el harness de mutacion del guard de superficies.

Que es lo que tiene que demostrar
---------------------------------
Un guard que se pone verde es lo mas facil del mundo, y por eso B10
nacio de dos propiedades que **se cerraban en veinte segundos**: se
escribia un ``__all__`` y se hacia ``touch`` sobre el fichero de la
declaracion. Los predicados de B9 miraban la EXISTENCIA del snapshot, y
un ``is_file()`` es lo mas facil de falsificar que hay.

Este harness no prueba que el guard funcione: lo prueba tomando el texto
del guard y del test, deformandolo de una manera concreta, y exigiendo que
la deformacion se vea. Si el guard aguanta una deformacion, el guard no
mide lo que dice medir.

Por que hay sondas sobre el TEST y no solo sobre el guard
---------------------------------------------------------
La pregunta interesante no es «el guard detecta el arbol roto» —eso es lo
obvio— sino «los tests que lo comparan se ponen rojos cuando deben». Un
guard correcto sin tests que lo ejecuten es un script que nadie lanza, y
eso ya ocurrio en este repo: los predicados de B9 no los ejecutaba
nadie, y por eso dos propiedades de la lista de 1.0 estaban abiertas sin
que nadie supiera por que.

Las sondas comprueban la direccion contraria: que el test se ponga ROJO
cuando el defecto esta. Un test que sigue verde con el arbol roto no es
un test que mide: es decoracion. Y el criterio de este harness no es
«cazo el test X», es «cazo y la causa es distinta», porque dos sondas que
caen en el mismo test midiendo cosas distintas son dos guards con el
mismo disfraz.

El guard anti-destruccion se copio tal cual de B9, y por una razon
MEDIDA: la primera version de aquel harness se **borro a si mismo** y
reporto un numero como si nada. Ver `_sin_trabajo_sin_commitar`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

#: Ficheros que este harness restaura. Se restauran de `HEAD`, no de una
#: copia hecha al empezar: una copia puede tener el arbol ya sucio, y
#: entonces el harness «restaura» el defecto y lo cuenta como verde.
MUTABLES = (
    RAIZ / "src" / "skillgraph" / "core" / "__init__.py",
    RAIZ / "scripts" / "check_public_surfaces.py",
    RAIZ / "tests" / "test_b10_public_surface.py",
    RAIZ / "surfaces" / "core-surface.json",
    RAIZ / "surfaces" / "cli-surface.json",
)

#: Las suites que tienen que CAER. No se mira el rc global: se mira que
#: caigan los tests concretos de cada sonda, porque un `rc != 0` lo puede
#: dar un test que no es el que esta probando la deformacion.
SUITES = ("tests/test_b10_public_surface.py",)


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
    """Los mutables con cambios SIN commitear, que se perderian al restaurar.

    **ESTE GUARD SE COPIO DE B9 PORQUE SU AUSENCIA DESTRUYO TRABAJO ALLI,
    MEDIDO.** La primera version de aquel harness restauraba con
    `git checkout --`, que restaura **del indice**. Con el arreglo de B9 sin
    commitear —que es como se esta casi siempre mientras se escribe un
    bloque—, el primer `checkout` de la primera sonda se llevo por delante
    el arreglo entero, y el harness reporto «1 de 6 cazadas» sin decir que
    las demas sondas no habian encontrado codigo porque el harness se lo
    habia llevado por delante.

    Lo que lo hacia especialmente malo es que **parecia funcionar**: la
    base se verifico verde, la primera sonda cazo, y el informe salio con
    un numero. Un harness que destruye el arbol y ademas imprime un
    veredicto es peor que no tener harness.

    Un `Informe` con `__all__` vacio es el mismo defecto con otro nombre:
    un guard que deriva una superficie vacia y la da por buena mide
    exactamente cero y no se nota.
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


def _restaura() -> None:
    subprocess.run(
        ["git", "checkout", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
        cwd=RAIZ,
        check=True,
    )
    _limpia_cache()


def _sondas() -> tuple[Sonda, ...]:
    """Las deformaciones, derivadas del texto REAL de los ficheros.

    MEDIDO en B9, y es el error 32 de WI-113 repetido: una sonda que apunta
    a un texto que ya no existe se cuenta como «no cazo», y eso se lee como
    «el guard aguanta» cuando lo que pasa es que el guard no se toco. Por
    eso cada sonda se **verifica contra el fichero antes de mutar**, y una
    sonda cuyo `antes` no esta ahi se cuenta como fallo del harness.
    """
    return (
        Sonda(
            nombre="M1_el_nucleo_deja_de_declarar_superficie",
            fichero="src/skillgraph/core/__init__.py",
            antes='__all__ = ["MODULOS", "SUPERFICIE", *SUPERFICIE]',
            despues="__all__: list[str] = []",
            esperados=frozenset(
                {
                    "TestElNucleoDeclaraSuSuperficie::test_el_paquete_declara_superficie",
                    "TestElNucleoDeclaraSuSuperficie::test_la_superficie_es_la_union_de_los_tres_modulos",
                    "TestElInstrumentoMide::test_la_superficie_real_no_es_de_nada",
                }
            ),
        ),
        Sonda(
            nombre="M2_el_nucleo_reexporta_una_copia",
            fichero="src/skillgraph/core/__init__.py",
            antes="del _nombre",
            # MEDIDO, y el motivo esta medido: las dos primeras versiones de
            # esta sonda NO fueron sondas. Envoltian los 60 simbolos con
            # `type('Copia', (valor,), {})`, y 28 de ellos —todos los
            # `NewType` y los `frozenset` de ADT— dan `TypeError: metaclass
            # conflict` al hacerlo. El modulo no importaba, `pytest` no
            # colectaba, y el harness veia `rc=4` con CERO lineas `FAILED`.
            #
            # Eso se leia como «el guard no muerde», cuando lo que pasaba es
            # que la sonda estaba rota: un `rc` de colecta no es un test en
            # rojo, y un test que no corre no ha medido nada. La sonda
            # correcta copia UN simbolo que sea clonable (una clase de
            # error) **despues** del bucle, de forma que el modulo sigue
            # importando y la identidad —lo que el test mide— se rompe de
            # verdad.
            despues=(
                "del _nombre\n"
                "ParseError = type('Copia', (ParseError,), {})  # sonda M2: copia, no reexporta"
            ),
            esperados=frozenset(
                {
                    "TestElNucleoDeclaraSuSuperficie::"
                    "test_los_simbolos_reexportados_son_los_mismos_objetos"
                }
            ),
        ),
        Sonda(
            nombre="M3_la_comparacion_se_queda_en_una_direccion",
            fichero="scripts/check_public_surfaces.py",
            antes="    perdidos = sorted(declarados - reales)",
            despues="    perdidos = sorted()  # una sola direccion: M3",
            esperados=frozenset(
                {
                    "TestLaComparacionVaEnDosDirecciones::"
                    "test_un_comando_inventado_en_el_snapshot_no_pasa"
                }
            ),
        ),
        Sonda(
            nombre="M4_el_subcomando_deja_de_comproparse",
            fichero="scripts/check_public_surfaces.py",
            antes="        if sub_reales != sub_declarados:",
            despues="        if False:",
            esperados=frozenset(
                {"TestLaComparacionVaEnDosDirecciones::test_un_subcomando_inventado_no_pasa"}
            ),
        ),
        Sonda(
            nombre="M5_runner_all_deja_de-compararse",
            fichero="scripts/check_public_surfaces.py",
            antes="        if reales_all != declarados_all:",
            despues="        if False:",
            esperados=frozenset(
                {
                    "TestLaComparacionVaEnDosDirecciones::test_un_simbolo_inventado_en_runner_all_no_pasa"
                }
            ),
        ),
        Sonda(
            nombre="M6_la_comparacion-del-nucleo-acepta-cualquier-cosa",
            fichero="scripts/check_public_surfaces.py",
            antes="    if declarados == esperados:\n        return ()",
            despues="    if True:\n        return ()",
            esperados=frozenset(
                {
                    "TestLaSuperficieNoSeHaMovido::"
                    "test_la_comparacion_del_nucleo_es_igual_que_la_de_la_cli"
                }
            ),
        ),
    )


def main() -> int:
    print("Harness de mutacion B10 — el guard de superficies publicas")
    print("=" * 78)

    pendientes = _sin_trabajo_sin_commitar()
    if pendientes:
        print("ABORTO: hay cambios SIN COMMITAR en ficheros que este harness restaura.")
        print("        `git checkout --` restaura del indice, luego restaurarlos")
        print("        BORRARIA el trabajo en vez de volver atras. Commitea antes.")
        for linea in pendientes:
            print(f"        {linea}")
        return 2

    _limpia_cache()
    rc, _ = _pytest(SUITES)
    if rc != 0:
        print(f"ABORTO: la suite NO esta verde antes de mutar (rc={rc}).")
        return 2
    print("Base verificada: suite verde sin tocar nada.\n")

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
        # La «causa» de una sonda es el conjunto de tests DIAGNOSTICOS que
        # solo ella puede tumbar (`esperados`), no todo lo que se puso rojo.
        # MEDIDO, y la distincion importa: al contar el rojo completo, M1
        # (el nucleo deja de declarar) y M3 (la comparacion CLI se queda en
        # una direccion) dan dos conjuntos que se pisan en los dos tests
        # «esta todo verde» —`test_el_snapshot_de_verdad_pasa` y el de
        # subproceso—, y el harness avisaba de causa compartida cuando lo
        # que hay es solapamiento legitimo de sentinelas.
        #
        # Las dos cosas se_INFO_miden igual: que caiga lo esperado, y que
        # dos sondas no dependan del MISMO diagnostico. Si dos sondasaran a
        # caer por el mismo test diagnostico, una de las dos no estaria
        # midiendo lo que dice medir.
        causas.add(frozenset(sonda.esperados))
        print(f"[CAZADA]    {sonda.nombre}: {len(caidos)} tests en rojo")

    print()
    print(f"sondas cazadas: {cazadas}/{len(sondas)}")
    print(f"causas DISTINTAS: {len(causas)} (una por sonda = {cazadas} esperadas)")
    if sin_sonda:
        print(f"sin sonda: {sin_sonda}")
    if sondas and len(causas) != len(sondas):
        print(
            "AVISO: dos sondas comparten el MISMO conjunto de tests diagnosticos. Una "
            "de las dos no esta midiendo lo que dice medir: o su guarda no muerde, o cae "
            "por otra causa."
        )

    _limpia_cache()
    rc, caidos = _pytest(SUITES)
    print()
    if rc == 0 and not caidos:
        print(f"Arbol restaurado y EJECUTANDO como estaba: {SUITES[0]} verde.")
    else:
        print(f"ABORTO: tras restaurar, la suite sigue en rojo (rc={rc}, {sorted(caidos)}).")
        return 2
    return 0 if cazadas == len(sondas) and not sin_sonda else 1


if __name__ == "__main__":
    sys.exit(main())
