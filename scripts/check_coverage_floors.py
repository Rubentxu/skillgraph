#!/usr/bin/env python3
"""Comprueba los suelos de cobertura que declara AGENTS.md §6.3.

Por que existe
--------------
El repositorio declara DOS contratos de cobertura distintos:

  1. `pyproject.toml` -> `[tool.coverage.report] fail_under = 80`.
     Lo hace cumplir `coverage report`, que solo acepta UN umbral global.

  2. `AGENTS.md §6.3` -> suelos por modulo:

         todo modulo que cuelgue de un subdirectorio de
         `src/skillgraph/`                                  >= 90 %
         CLI                                                 >= 70 %
         paths.py                                            >= 60 %

     **Este contrato no lo puede comprobar `coverage report`.** Solo admite
     un umbral global, y ningun test del repo lo miraba. Era una cifra que
     se declaraba y no se verificaba.

Este script es la parte que faltaba. Vive en `scripts/` y no en
`.pipelinek/`, porque un guard que no esta versionado no es un guard.

El suelo es la NORMA; las listas son las desviaciones (WI-107)
--------------------------------------------------------------
El recorrido de este contrato tiene tres etapas, y cada una tapo una a una
la anterior:

  * WI-93 lo implemento con una lista de 21 modulos escrita a mano. Solo
    vigilaba `runtime/`: los otros siete paquetes podian recibir un modulo
    nuevo al 40 % sin que nadie se enterara.

  * WI-94 cambio el eje: el suelo lo hereda el modulo de su PAQUETE, con
    `SUELOS_POR_PAQUETE` como unica fuente. Pero el **conjunto de
    prefijos** seguia siendo un diccionario escrito a mano, de ocho
    entradas. Medido el 2026-10-03: un paquete nuevo, versionado en git y
    con un modulo al 0 %, daba `VEREDICTO: todos los suelos declarados se
    cumplen` y exit 0. La lista habia cambiado de eje, no de naturaleza.

  * Aqui la lista desaparece. `SUELO_POR_DEFECTO` es la regla y alcanza a
    todo lo que cuelga de un subdirectorio de `src/skillgraph/`, un paquete
    nuevo incluido, sin que nadie lo declare. Lo que queda escrito son las
    DESVIACIONES, que son datos y no pueden derivarse del arbol: el CLI al
    70 % porque §6.3 lo exime, y `paths.py` al 60 % porque §6.3 le da un
    suelo propio.

    De ocho entradas escritas a mano quedan dos, y las dos son el contrato
    diciendo algo que el codigo no puede deducir. Si un paquete necesita
    otra cosa, se declara aqui con su motivo, y ese es el unico sitio donde
    anadir un paquete es una decision.

Lo que §6.3 NO gobierna, y por que
----------------------------------
`src/skillgraph/__init__.py` y `src/skillgraph/__main__.py` estan en la
raiz, no cuelgan de un subdirectorio, y `pyproject.toml` los pone en
`omit`. Medir un fichero que el instrumento ni recoge es ruido. La regla es
«cuelga de un subdirectorio», no «esta bajo src/skillgraph/», y la
distincion esta en `_cuelga_de_paquete()` para que se pueda probar sola.

Trampa conocida: la agregacion
------------------------------
`coverage` con `branch = true` reporta un porcentaje que combina
sentencias y ramas, y una rama parcial cuenta como media. Por eso este
script **agrega recuentos, no porcentajes**: promediar porcentajes da
mas de lo que hay, y un paquete al 95 % de media puede esconder un
modulo al 60 %. Los agregados se conservan como comprobacion ADICIONAL
(`SUELOS_AGGREGADOS`), nunca en lugar de la comprobacion por modulo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parent.parent
RC = ROOT / ".coverage.rc"

# Raiz del paquete distribuible. Todo lo que cuelgue de un subdirectorio
# de aqui hereda `SUELO_POR_DEFECTO`.
RAIZ: Final = "src/skillgraph/"

# AGENTS §6.3, la NORMA. Un modulo nuevo en un paquete que todavia no
# existe hereda este suelo, y esa es toda la diferencia con WI-94.
SUELO_POR_DEFECTO: Final = 90.0

# Desviaciones por PAQUETE: suelo distinto del general. §6.3 exime al CLI
# al 70 %, y es la unica excepcion por paquete.
SUELOS_ESPECIALES: dict[str, float] = {
    "src/skillgraph/cli/": 70.0,
}

# Desviaciones por MODULO: suelo distinto del de su paquete. §6.3 exime a
# `paths.py` explicitamente (60 %), y aplicarle el 90 % de `platform/`
# haria fallar al unico modulo que el propio contrato exonera.
EXCEPCIONES: dict[str, float] = {
    "src/skillgraph/platform/paths.py": 60.0,
}

# Comprobacion ADICIONAL, por conjunto. No sustituye a la por modulo: es la
# que atrapa el caso de un paquete entero que se degrada de golpe, que la
# suma de modulos flojos tambien veria, pero con un mensaje que lo dice.
SUELOS_AGGREGADOS: dict[str, float] = {
    "src/skillgraph/runtime/": 90.0,
    "src/skillgraph/cli/": 70.0,
}

# `pyproject.toml` -> [tool.coverage.report]. Se comprueba aparte porque
# `coverage report` ya lo aplica, pero solo si alguien lo ejecuta: aqui
# queda registrado que se comprobo, no solo que existe.
SUELO_GLOBAL = 80.0


def _cuelga_de_paquete(ruta: str) -> bool:
    """¿`ruta` esta dentro de un PAQUETE, o en la raiz del distribuible?

    Un paquete es un subdirectorio. Lo que cuelga de uno hereda
    `SUELO_POR_DEFECTO` aunque el paquete no figure en ninguna parte: esa
    pregunta es la que WI-94 no se hacia y por la que un paquete nuevo
    pasaba sin suelo.
    """
    if not ruta.startswith(RAIZ):
        return False
    return "/" in ruta[len(RAIZ) :]


def suelo_de(ruta: str) -> float | None:
    """Suelo que hereda `ruta`, o `None` si §6.3 no gobierna ese modulo.

    Precedencia, de mas especifico a mas general: la excepcion propia, el
    especial de paquete, y el suelo por defecto. Se declara en una sola
    pregunta para que la regla se pueda probar sola.
    """
    if ruta in EXCEPCIONES:
        return EXCEPCIONES[ruta]
    for prefijo, suelo in SUELOS_ESPECIALES.items():
        if ruta.startswith(prefijo):
            return suelo
    if _cuelga_de_paquete(ruta):
        return SUELO_POR_DEFECTO
    return None


def _desviaciones() -> tuple[tuple[str, float], ...]:
    """Los suelos que NO se deducen del arbol, con su etiqueta.

    Prefijos de paquete y rutas de modulo se distinguen porque se
    comprueban de forma distinta: a un prefijo se le exige que aporta
    ALGUN modulo, a un modulo se le exige que EXISTA.
    """
    prefijos = tuple(sorted((p, s) for p, s in SUELOS_ESPECIALES.items()))
    modulos = tuple(sorted((r, s) for r, s in EXCEPCIONES.items()))
    return prefijos + modulos


def informe() -> dict[str, dict[str, object]]:
    if not RC.exists():
        print(f"ABORTA: no existe {RC}. Ejecuta antes `bash scripts/coverage.sh`.")
        raise SystemExit(2)
    salida = subprocess.run(
        [sys.executable, "-m", "coverage", "json", "--rcfile", str(RC), "-o", "-"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(json.loads(salida.stdout)["files"])  # type: ignore[return-value]


def _recuentos(entradas: list[dict[str, object]]) -> tuple[int, int]:
    """(total, cubierto) con la misma aritmetica que usa coverage.py."""
    total = cubierto = 0
    for e in entradas:
        s = e["summary"]  # type: ignore[index]
        stmts = int(s["num_statements"])  # type: ignore[index]
        branches = int(s["num_branches"])  # type: ignore[index]
        faltan = int(s["missing_lines"]) + int(s["missing_branches"])  # type: ignore[index]
        total += stmts + branches
        cubierto += stmts + branches - faltan
    return total, cubierto


def porcentaje(entradas: list[dict[str, object]]) -> float:
    total, cubierto = _recuentos(entradas)
    return 100.0 * cubierto / total if total else 100.0


def _tiene_codigo(entrada: dict[str, object]) -> bool:
    s = entrada["summary"]  # type: ignore[index]
    return int(s["num_statements"]) + int(s["num_branches"]) > 0  # type: ignore[index]


def evaluar(files: dict[str, dict[str, object]]) -> tuple[list[str], list[str]]:
    """Funcion PURA: informe de coverage -> (lineas para imprimir, fallos).

    Separada de `main()` a proposito. El contrato se puede probar con
    informes sinteticos, sin disco y sin subprocess, y un test que solo
    lee el informe real no distingue «el contrato se cumple» de «el
    contrato no mira aqui».

    Recuentos, no porcentajes: ver la nota de la cabecera del modulo.
    """
    lineas: list[str] = []
    fallos: list[str] = []

    print("== AGENTS §6.3, por modulo (suelo por defecto; el paquete no se declara) ==")
    for ruta in sorted(files):
        suelo = suelo_de(ruta)
        if suelo is None:
            continue  # §6.3 no gobierna este modulo
        entrada = files[ruta]
        if not _tiene_codigo(entrada):
            # 0 sentencias y 0 ramas (los `__init__.py` de reexport):
            # exigirle un suelo es medir un fichero vacio, y ademas hace
            # division por cero. Un guard que revienta con ruido sobre lo
            # que no importa teaches a ignorar al guard.
            continue
        p = porcentaje([entrada])
        ok = p >= suelo
        marca = " (excepcion §6.3)" if ruta in EXCEPCIONES else ""
        lineas.append(
            f"  {'OK  ' if ok else 'BAJO'} {p:6.2f} %  (suelo {suelo:5.1f} %)  {ruta}{marca}"
        )
        if not ok:
            fallos.append(f"{ruta} mide {p:.2f} %, por debajo de su suelo del {suelo:.0f} %")

    lineas.append("== suelos declarados a mano, y si lo que nombran existe ==")
    for nombre, suelo in _desviaciones():
        en_informe = [f for f in files if f == nombre or f.startswith(nombre)]
        if any(_tiene_codigo(files[f]) for f in en_informe):
            continue
        # Con suelo por defecto, «un paquete declarado que desaparece» ya no
        # puede ocurrir: los paquetes no se declaran. Lo que queda escrito
        # son las desviaciones, y una desviacion que nombra algo inexistente
        # es una regla sobre la nada que ademas apaga el suelo que si
        # existe. Sin esta asercion, borrar `paths.py` dejaria su 60 % sin
        # vigilantar y el checker no diria nada.
        msg = f"{nombre}: suelo declarado a mano ({suelo:.0f} %) y sin ningun modulo en el informe"
        lineas.append(f"  ?    {msg}")
        fallos.append(msg)
    if not any("sin ningun modulo" in f for f in fallos):
        lineas.append("  OK   todo suelo declarado a mano nombra algo que existe")

    lineas.append("")
    lineas.append("== AGENTS §6.3, conjuntos agregados (comprobacion adicional) ==")
    for prefijo, suelo in sorted(SUELOS_AGGREGADOS.items()):
        entradas = [e for f, e in files.items() if f.startswith(prefijo) and _tiene_codigo(e)]
        if not entradas:
            continue  # ya reportado arriba, con un mensaje mas claro
        p = porcentaje(entradas)
        ok = p >= suelo
        lineas.append(
            f"  {'OK  ' if ok else 'BAJO'} {p:6.2f} %  (suelo {suelo:5.1f} %)  "
            f"{prefijo} = {len(entradas)} modulos"
        )
        if not ok:
            fallos.append(
                f"{prefijo} agregado mide {p:.2f} %, por debajo del suelo del {suelo:.0f} %"
            )

    lineas.append("")
    lineas.append("== pyproject.toml, suelo global ==")
    p = porcentaje([e for e in files.values() if _tiene_codigo(e)])
    ok = p >= SUELO_GLOBAL
    lineas.append(f"  {'OK  ' if ok else 'BAJO'} {p:6.2f} %  (fail_under = {SUELO_GLOBAL:.0f} %)")
    if not ok:
        fallos.append(f"global mide {p:.2f} %, por debajo del suelo del {SUELO_GLOBAL:.0f} %")

    return lineas, fallos


def main() -> int:
    files = informe()
    lineas, fallos = evaluar(files)
    for linea in lineas:
        print(linea)

    print()
    if fallos:
        print(f"VEREDICTO: {len(fallos)} incumplimiento(s) del contrato declarado")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("VEREDICTO: todo modulo gobernado por §6.3 cumple su suelo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
