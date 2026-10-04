#!/usr/bin/env python3
"""B17 · el harness de mutacion del gate que ejecuta el ciclo de vida.

Por que existe
--------------
B16 demostro, con su propia autocomprobacion, que un harness que no se puede
tumbar no es un harness. Y demostro algo mas incomodo: que el suyo, al
escribirlo, mentia en dos sitios, y que la unica razon por la que se supiera
fue que el harness se negaba a arrancar con un diagnostico o un ancla que no
cuadraran.

Este tiene las dos cosas, y una mas que las anteriores:

1. **M6 no deforma el gate: deforma el INSTRUMENTO que el gate ejecuta.** Es
   la sonda que importa. Si el unico defecto posible fuera «el gate dejo de
   mirar», bastaria con una comprobacion de que el gate llama al
   instrumento, y un guard asi solo sabe mirar su propio telefono. M6
   neutraliza Q2 del medidor de B11 —la pregunta que EJECUTA `install` con un
   pack incompatible— y exige que el gate caiga. Si el gate cae, la cadena
   entera se sostiene de verdad: decision rota -> instrumento lo ve -> gate lo
   propaga. Si el gate no cae, la propiedad solo estaba mirando el cable y no
   lo que habia al otro extremo.

2. **Las sondas que se parecen unas a otras se separan por su CAUSA, no por su
   texto.** M1 quita la ejecucion; M4 la deja ejecutar pero ya no mira su
   codigo de salida; M3 la deja ejecutar y mirar el codigo de salida pero
   pierde el recuento de preguntas. Las tres hacen que la propiedad se quede
   verde con el ciclo roto, y por eso tienen que ser tres: un guard que solo
   sabe cazar una forma de mentir mide una forma de mentir.

La autocomprobacion es la de B13, B14, B15 y B16
-------------------------------------------------
Cuatro series de sondas han nacido rotas y las ha cazado el propio harness
antes de contarlas. Un harness que cuenta como verde una sonda que no midio
es peor que no tener harness, porque **publica un numero**. Por eso aqui, antes
de mutar nada, este script se niega a arrancar si:

- un **diagnostico** declarado no existe entre los ids colectados de verdad;
- un **ancla** no aparece exactamente una vez en su fichero;
- una **deformacion** es identica al texto que deberia cambiar.

Y el recuento final exige el arbol limpio: sin eso, un harness que rompe un
fichero y no lo devuelve deja el repo en un estado que existio de verdad.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

MUTABLES = (
    RAIZ / "scripts" / "measure_b9_gate_1_0.py",
    RAIZ / "scripts" / "measure_b11_pack_lifecycle.py",
)
SUITES = ("tests/test_b17_pack_lifecycle_exec.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo, y quien TIENE que caer."""

    nombre: str
    fichero: str
    antes: str
    despues: str
    esperados: frozenset[str]


def _sin_trabajo_sin_commitar() -> tuple[str, ...]:
    """Los mutables con cambios SIN commitear, que se perderian al restaurar.

    «Restaurar» y «borrar» son la misma operacion sin commit debajo: si el
    fichero esta sucio y el harness hace `git checkout --`, el trabajo se va y el
    harness sigue diciendo que el arbol esta limpio.
    """
    proc = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            *[str(p.relative_to(RAIZ)) for p in MUTABLES],
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(linea for linea in proc.stdout.splitlines() if linea.strip())


def _limpia_cache() -> None:
    for cache in RAIZ.rglob("__pycache__"):
        if ".venv" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)


def _pytest(objetivos: tuple[str, ...]) -> tuple[int, set[str], bool]:
    """Corre la suite y devuelve (rc, caidos, la_suite_no_colecto).

    MEDIDO en B16, y el defecto era de ESTE arnes: contar solo `FAILED` hacia
    que una rotura que tumba la COLECTA entera se|reportara como «no ha
    medido nada», que es la direccion del falso verde. Las dos formas valen y
    se distinguen al reportar, porque mezclarlas hace que el numero no diga
    que se midio.
    """
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *objetivos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    caidos = {
        linea.split("::", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED ") and "::" in linea
    }
    errores = {
        linea.split(" ", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("ERROR ") and " " in linea
    }
    no_colecto = bool(errores) or "Interrupted" in proc.stdout or proc.returncode in (2, 3)
    return proc.returncode, caidos | errores, no_colecto


def _colectados(objetivos: tuple[str, ...]) -> set[str]:
    """Los ids de test que EXISTEN de verdad en la suite del harness."""
    proc = subprocess.run(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "--collect-only",
            "-p",
            "no:cacheprovider",
            *objetivos,
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    return {
        linea.strip() for linea in proc.stdout.splitlines() if linea.startswith(f"{objetivos[0]}::")
    }


def _interprete_valido() -> str | None:
    """Por que no, si `PY` no puede importar el paquete. `None` si puede.

    MEDIDO en B14 y B16: lanzado con el Python del sistema, el harness se
    negaba con un sintoma de una causa que no era la que media, y en B16 el
    mismo desajuste produjo un `ModuleNotFoundError` que se leia como un
    defecto del producto cuando era del interprete que lanzo la sonda.
    """
    proc = subprocess.run(
        [PY, "-c", "import skillgraph"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode == 0:
        return None
    return (
        f"{PY} no puede importar `skillgraph`, y este harness corre sus sondas con el\n"
        f"interprete con el que se lanzo. Lanzalo con el del proyecto: `uv run python "
        f"{Path(__file__).relative_to(RAIZ)}`."
    )


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_el_predicado_vuelve_a_decidir_por_nombres",
        fichero="scripts/measure_b9_gate_1_0.py",
        # El defecto MEDIDO de este bloque, en su forma extrema: el `return`
        # va ANTES de la llamada, luego el instrumento no se ejecuta nunca. La
        # primera version de esta sonda anadia una comprobacion de nombres
        # delante y la dejaba SEGUIR AL INSTRUMENTO, asi que media otra cosa y
        # daba 5 de 5 en verde con el defecto puesto. Es el error 32 de B13:
        # una sonda que no desactiva lo que dice desactivar.
        # MEDIDO, y lo cazo la autocomprobacion de este mismo harness: la
        # primera version de estas dos anclas las partio en trozos de cadena y
        # el nombre del fichero se quedo SIN comillas, luego el ancla no
        # existia en el fichero. Sin el «el ancla aparece 0 veces» la sonda se
        # habria aplicado a la nada, la deformacion no habria ocurrido, los
        # tests habrian pasado y el 6/6 habria sido un numero sobre seis
        # deformaciones que no deformaron nada.
        antes=(
            '    proc = _corre([sys.executable, str(RAIZ / "scripts" / '
            '"measure_b11_pack_lifecycle.py")])\n'
            "    salida = (proc.stdout + proc.stderr).strip()"
        ),
        despues=(
            '    declarados = ("install", "update", "remove")\n'
            '    existentes = _subcomandos_de("pack")\n'
            "    faltan = [v for v in declarados if v not in existentes]\n"
            "    if faltan:\n"
            '        return "OPEN", f"`sg pack` expone {sorted(existentes)} y no {list(faltan)}"\n'
            '    return "PASS", f"`sg pack` expone el ciclo completo: {sorted(existentes)}"\n'
            '    proc = _corre([sys.executable, str(RAIZ / "scripts" / '
            '"measure_b11_pack_lifecycle.py")])\n'
            "    salida = (proc.stdout + proc.stderr).strip()"
        ),
        esperados=frozenset(
            {
                "TestUnNombreDeSubcomandoNoEsUnCicloDeVida::test_con_el_ciclo_roto_la_propiedad_es_open",
                "TestUnNombreDeSubcomandoNoEsUnCicloDeVida::test_el_open_nombra_la_pregunta_que_cae",
                "TestLaPropiedadNoVuelveALosNombres::test_la_evidencia_dice_que_se_ejecuto",
            }
        ),
    ),
    Sonda(
        nombre="M2_el_instrumento_que_no_arranca_vuelve_a_decir_que_se_ejecuto",
        fichero="scripts/measure_b9_gate_1_0.py",
        # Defecto PROPIO, introducido al escribir el arreglo y cazado por su
        # propio guard en la misma sesion: con el instrumento sin arrancar, el
        # predicado decia «se ha EJECUTADO para saberlo» y «Caen 0 de 0
        # preguntas». Publicaba una ejecucion que no habia ocurrido, con un
        # recuento que era cero sobre cero.
        antes="    if proc.returncode != 0 and not preguntas:",
        despues="    if False and proc.returncode != 0 and not preguntas:",
        esperados=frozenset(
            {
                "TestElInstrumentoNoSeDeclaraMedibleCuandoNoLoEs::"
                "test_un_instrumento_que_no_devuelve_nada_no_dice_que_no"
            }
        ),
    ),
    Sonda(
        nombre="M3_el_recuento_de_preguntas_se_pierde",
        fichero="scripts/measure_b9_gate_1_0.py",
        # El instrumento se ejecuta y su codigo de salida se mira, pero el
        # recuento de preguntas por las que cae se queda vacio. Con el ciclo
        # roto, el veredicto pasaria a NO_MEASURABLE —«no lo se»— en vez de
        # OPEN, que es otra manera de no dar el veredicto de una propiedad que
        # SI se puede decidir.
        antes="    preguntas = _preguntas_del_instrumento(salida)",
        despues="    preguntas = ()",
        esperados=frozenset(
            {
                "TestUnNombreDeSubcomandoNoEsUnCicloDeVida::test_con_el_ciclo_roto_la_propiedad_es_open"
            }
        ),
    ),
    Sonda(
        nombre="M4_el_codigo_de_salida_del_instrumento_deja_de_mirarse",
        fichero="scripts/measure_b9_gate_1_0.py",
        # El gate EJECUTA el instrumento, lee su salida y aun asi no decide por
        # el. Es la forma mas insidiousa de los tres, porque todo lo que se ve
        # —que se ejecuta, que hay salida, que se citan preguntas— sigue
        # pasando, y lo unico que falta es mirar el dato.
        antes='    if proc.returncode != 0:\n        caidas = [nombre for nombre, veredicto in preguntas if veredicto != "PASS"]',
        despues='    if False:\n        caidas = [nombre for nombre, veredicto in preguntas if veredicto != "PASS"]',
        esperados=frozenset(
            {
                "TestUnNombreDeSubcomandoNoEsUnCicloDeVida::test_con_el_ciclo_roto_la_propiedad_es_open"
            }
        ),
    ),
    Sonda(
        nombre="M5_el_parser_de_la_salita_se_nega_a_leer_el_veredicto",
        fichero="scripts/measure_b9_gate_1_0.py",
        # El recuento de preguntas se queda siempre vacio porque el parser no
        # encuentra el cierre del corchete. M3 y M5 hacen lo mismo desde dos
        # sitios distintos, y por eso son dos: si se fundieran en una, el guard
        # solo sabria cazar una forma de perder el dato.
        antes="        veredicto = limpia[1:cierre].strip()",
        despues="        veredicto = ''",
        esperados=frozenset(
            {
                "TestUnNombreDeSubcomandoNoEsUnCicloDeVida::test_con_el_ciclo_roto_la_propiedad_es_open"
            }
        ),
    ),
    Sonda(
        nombre="M6_el_instrumento_deja_de_ejecutar_lo_que_el_gate_le_encarga",
        fichero="scripts/measure_b11_pack_lifecycle.py",
        # **LA SONDA QUE IMPORTA.** No deforma el gate: deforma el INSTRUMENTO
        # que el gate ejecuta, neutralizando Q2 —la pregunta que EJECUTA
        # `install` con un pack incompatible—. Con esto, un `install` roto da
        # PASS en las dos capas y el gate se lo cree.
        #
        # Si el gate NO cae con esto, entonces la propiedad no estaba midiendo
        # la cadena decision -> instrumento -> gate, sino el cable. Y un guard
        # que solo sabe mirar el cable no mide lo que dice medir.
        antes="    r = informe.install_incompatible\n    if _exito(r):",
        despues="    r = informe.install_incompatible\n    if False and _exito(r):",
        esperados=frozenset(
            {
                "TestUnNombreDeSubcomandoNoEsUnCicloDeVida::test_con_el_ciclo_roto_la_propiedad_es_open"
            }
        ),
    ),
)


def main() -> int:
    problema = _interprete_valido()
    if problema is not None:
        print("NO SE EJECUTA: el interprete no es el del proyecto.")
        print(problema)
        return 2

    sucio = _sin_trabajo_sin_commitar()
    if sucio:
        print("NO SE EJECUTA: hay cambios sin commitear en los mutables.")
        print("«Restaurar» y «borrar» son la misma operacion sin commit debajo.")
        for linea in sucio:
            print(f"  {linea}")
        return 2

    print(f"B17 · {len(SONDAS)} sondas sobre {len(SUITES)} ficheros de test\n")

    ids = _colectados(SUITES)
    if not ids:
        print("NO SE EJECUTA: la colecta no devolvio ningun test.")
        return 2
    faltan = [
        f"{sonda.nombre}: no existe el diagnostico {esperado}"
        for sonda in SONDAS
        for esperado in sorted(sonda.esperados)
        if not any(i.endswith(esperado) for i in ids)
    ]
    if faltan:
        print("NO SE EJECUTA: hay diagnosticos que no existen.")
        print("Una sonda cuyo esperado no esta escrito bien se contaria como cazada con")
        print("menos causa, y el numero seria falso.")
        for linea in faltan:
            print(f"  {linea}")
        return 2
    print(f"diagnosticos verificados: {sum(len(s.esperados) for s in SONDAS)} nombres existen")

    invalidas: list[str] = []
    for sonda in SONDAS:
        texto = (RAIZ / sonda.fichero).read_text(encoding="utf-8")
        apariciones = texto.count(sonda.antes)
        if apariciones != 1:
            invalidas.append(
                f"{sonda.nombre}: el ancla aparece {apariciones} veces, y se sustituiria la primera"
            )
        if sonda.antes == sonda.despues:
            invalidas.append(f"{sonda.nombre}: la deformacion es identica al texto que cambia")
    if invalidas:
        print("NO SE EJECUTA: hay sondas invalidas.")
        for linea in invalidas:
            print(f"  {linea}")
        return 2
    print(f"anclas verificadas: {len(SONDAS)} textos unicos\n")

    rc, caidos, no_colecto = _pytest(SUITES)
    if rc != 0 or caidos or no_colecto:
        print(f"VERDE DE PARTIDA FALSA: {SUITES[0]} ya esta rojo sin mutar nada.")
        print(f"  rc={rc}  caidos={sorted(caidos)}  no_colecto={no_colecto}")
        return 2
    print(f"linea base: {SUITES[0]} verde sin mutar\n")

    causa_de: dict[str, str] = {}
    compartidas: list[str] = []
    invalidas = []
    for sonda in SONDAS:
        _limpia_cache()
        ruta = RAIZ / sonda.fichero
        texto = ruta.read_text(encoding="utf-8")
        try:
            ruta.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
            rc, caidos, no_colecto = _pytest(SUITES)
        finally:
            ruta.write_text(texto, encoding="utf-8")
        if not sonda.esperados <= caidos and not no_colecto:
            invalidas.append(
                f"{sonda.nombre}: cayo {sorted(caidos)}, pero no sus diagnosticos "
                f"{sorted(sonda.esperados)}"
            )
            print(f"  [SIN CAZAR] {sonda.nombre}")
            continue
        if no_colecto and not sonda.esperados <= caidos:
            forma = "la suite no pudo colectar"
        elif len(caidos) == len(sonda.esperados):
            forma = "solo sus diagnosticos"
        else:
            forma = f"+{sorted(caidos - sonda.esperados)}"
            compartidas.append(sonda.nombre)
        print(f"  [CAZADA]    {sonda.nombre}  ({forma})")
        causa_de[sonda.nombre] = ", ".join(sorted(sonda.esperados))

    if invalidas:
        print(f"\n{len(invalidas)} sonda(s) sin cazar:")
        for linea in invalidas:
            print(f"  {linea}")
        return 1
    print(f"\n{len(SONDAS)}/{len(SONDAS)} sondas cazadas, {len(causa_de)} causas")

    sucios = _sin_trabajo_sin_commitar()
    if sucios:
        print("\nVEREDICTO NO VALIDO: el harness dejo el arbol sucio.")
        for linea in sucios:
            print(f"  {linea}")
        return 1
    if compartidas:
        print(f"sondas que tiraron mas de lo suyo: {compartidas}")
    print("arbol limpio: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
