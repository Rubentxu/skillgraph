#!/usr/bin/env python3
"""B18 · el harness de mutacion de la frontera del nucleo.

Por que existe
--------------
B16, B17 y este bloque han encontrado sus propios instrumentos al escribirlos.
De las sondas de B16 y B17 que no median, todas las escribio la misma persona
que las iba a contar, y ese es el argumento para que la autocomprobacion se
exija a si misma en vez de ofrecerse: **no es que convenga comprobarlo, es que
la comprobacion es lo unico que separa un numero de un numero.**

Las tres sondas de aqui degradan UN defecto cada una, y cada una tiene que
caer SOLO su test. Tres sondas que tiran los seis tests no distinguen nada: un
guard que no sabes que deformacion cazo no sabe que mide.

Y un cuarto requisito que las anteriores no tenian, y que es la cuarta vez
que aparece: **el interprete**.

    MEDIDO: una comprobacion de este bloque lanzo la suite con el Python del
    SISTEMA en vez del del proyecto. La colecta no arranco, no hubo ni un
    `FAILED`, y las tres sondasaparecieron como «0 de 6 caidos» —que es
    indistinguible de «el guard no vio nada»—. Con el interprete correcto las
    tres cazan 1 cada una.

    Es el mismo sintoma que hizo que el arnes de B14 se negara con «la colecta
    no devolvio ningun test», y la quinta vez que aparece en este repo. Por eso
    `_interprete_valido()` se niega a arrancar si `PY` no puede importar
    `skillgraph`: fallar cerrado con el motivo es lo unico que evita que un
    fallo del entorno se cuente como un fallo —o como un acierto— del guard.

La autocomprobacion
-------------------
Cuatro series de sondas han nacido rotas y las ha cazado el propio harness
antes de contarlas. Antes de mutar nada, este script se niega a arrancar si:

- un **diagnostico** declarado no existe entre los ids colectados de verdad;
- un **ancla** no aparece exactamente una vez en su fichero;
- una **deformacion** es identica al texto que deberia cambiar.

Y una mas, que es la que hoy importa mas: **que el fichero deforme PARSEE**.
MEDIDO: la primera version de M1 dejaba codigo huerfano tras el `if` y el
modulo no parseaba, luego los seis tests caian —por no importar, no por
detectar nada— y la sonda seeria contada como la mas fuerte de las tres. Un
guard que cae porque el arbol se rompio no ha medido nada.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

MUTABLES = (RAIZ / "scripts" / "measure_b9_gate_1_0.py",)
SUITES = ("tests/test_b18_core_frontier.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo, y quien TIENE que caer."""

    nombre: str
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
        ["git", "status", "--porcelain", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
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

    MEDIDO en B16, y el defecto era de ESE arnes: contar solo `FAILED` hacia
    que una rotura que tumba la COLECTA entera se|reportara como «no ha medido
    nada», que es la direccion del falso verde. Las dos formas valen y se
    distinguen al reportar.
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

    MEDIDO en B14, B16 y B18: tres veces el mismo fallo con tres sintomas
    distintos, y el mas caro de B18 fue silencioso —las sondas dieron
    «0 de 6 caidos», que es indistinguible de «el guard no vio nada»—. Falla
    cerrado con el motivo es lo unico que evita que un fallo del entorno se
    cuente como un acierto del guard.
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
        nombre="M1_los_imports_relativos_vuelven_a_ignorarse",
        antes="            elif isinstance(nodo, ast.ImportFrom):\n                if nodo.level == 0:",
        # El `if True: pass` / `if False:` es lo que mantiene el cuerpo
        # PARSEANDO. MEDIDO: la primera version de esta sonda devolvia el `elif`
        # a una sola linea y dejaba las cuatro siguientes colgando de un `if`
        # que ya no existia; el modulo no parseaba, los seis tests caian por no
        # importar, y la sonda seeria contada como la mas fuerte de las tres.
        # Un guard que cae porque el arbol se rompio no ha medido nada.
        despues=(
            "            elif isinstance(nodo, ast.ImportFrom) and nodo.module "
            "and nodo.level == 0:\n"
            "                if True:\n"
            "                    pass\n"
            "                if False:"
        ),
        esperados=frozenset(
            {
                "TestUnImportRelativoNoSeEscapa::test_un_relativo_de_nivel_dos_que_sale_del_nucleo_es_open"
            }
        ),
    ),
    Sonda(
        nombre="M2_la_estandar_vuelve_a_ser_trece_renglones",
        antes="_MODULOS_ESTANDAR: frozenset[str] = frozenset(sys.stdlib_module_names) - _ESTANDAR_QUE_NO_ES_API",
        despues=(
            "_MODULOS_ESTANDAR: frozenset[str] = frozenset(\n"
            '    {"__future__", "ast", "collections", "dataclasses", "datetime", "enum",\n'
            '     "functools", "hashlib", "itertools", "json", "re", "typing", "uuid"}\n'
            ")"
        ),
        esperados=frozenset(
            {
                "TestLaEstandarNoEsUnaListaEscritaAMano::"
                "test_un_modulo_de_la_estandar_que_no_figuraba_no_da_open"
            }
        ),
    ),
    Sonda(
        nombre="M3_la_evidencia_vuelve_a_cerrarse_con_un_numero_sin_nombre",
        antes='        f"ficheros va aqui porque sin ella no se puede saber si el recorrido fue completo",',
        despues="        f\"({len(_imports_de('core'))} modulos)\",",
        esperados=frozenset(
            {
                "TestLoQueNoSeMiraNoSeDeclaraMirado::"
                "test_la_evidencia_no_dice_modulos_cuando_mide_imports"
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

    print(f"B18 · {len(SONDAS)} sondas sobre {len(SUITES)} ficheros de test\n")

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
    base = (RAIZ / MUTABLES[0]).read_text(encoding="utf-8")
    for sonda in SONDAS:
        apariciones = base.count(sonda.antes)
        if apariciones != 1:
            invalidas.append(
                f"{sonda.nombre}: el ancla aparece {apariciones} veces, y se sustituiria la primera"
            )
        if sonda.antes == sonda.despues:
            invalidas.append(f"{sonda.nombre}: la deformacion es identica al texto que cambia")
        # Y QUE EL RESULTADO PARSEE. MEDIDO: una sonda que rompe la sintaxis hace
        # caer la suite entera, luego parece la mas fuerte de todas y no ha
        # detectado NADA.
        try:
            ast.parse(base.replace(sonda.antes, sonda.despues, 1))
        except SyntaxError as exc:
            invalidas.append(
                f"{sonda.nombre}: la deformacion deja el modulo SIN PARSEAR ({exc}). "
                f"Una sonda asi hace caer la suite por no importar, no por detectar, "
                f"y seeria contada como la mejor de todas"
            )
    if invalidas:
        print("NO SE EJECUTA: hay sondas invalidas.")
        for linea in invalidas:
            print(f"  {linea}")
        return 2
    print(
        f"anclas verificadas: {len(SONDAS)} textos unicos, y las {len(SONDAS)} deformaciones parsean\n"
    )

    rc, caidos, no_colecto = _pytest(SUITES)
    if rc != 0 or caidos or no_colecto:
        print(f"VERDE DE PARTIDA FALSA: {SUITES[0]} ya esta rojo sin mutar nada.")
        print(f"  rc={rc}  caidos={sorted(caidos)}  no_colecto={no_colecto}")
        return 2
    print(f"linea base: {SUITES[0]} verde sin mutar\n")

    causa_de: dict[str, str] = {}
    invalidas = []
    for sonda in SONDAS:
        _limpia_cache()
        ruta = MUTABLES[0]
        texto = ruta.read_text(encoding="utf-8")
        try:
            ruta.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
            rc, caidos, no_colecto = _pytest(SUITES)
        finally:
            ruta.write_text(texto, encoding="utf-8")
        if no_colecto and not sonda.esperados <= caidos:
            invalidas.append(
                f"{sonda.nombre}: la suite no pudo colectar, luego la sonda no midio: {sorted(caidos)}"
            )
            print(f"  [SIN CAZAR] {sonda.nombre}  (la suite no colecto)")
            continue
        if not sonda.esperados <= caidos:
            invalidas.append(
                f"{sonda.nombre}: cayo {sorted(caidos)}, pero no sus diagnosticos "
                f"{sorted(sonda.esperados)}"
            )
            print(f"  [SIN CAZAR] {sonda.nombre}")
            continue
        extra = sorted(caidos - sonda.esperados)
        forma = "solo su diagnostico" if not extra else f"+{extra}"
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
    print("arbol limpio: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
