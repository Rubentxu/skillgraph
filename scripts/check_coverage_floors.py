#!/usr/bin/env python3
"""Comprueba los suelos de cobertura que declara AGENTS.md §6.3.

Por que existe
--------------
El repositorio declara DOS contratos de cobertura distintos:

  1. `pyproject.toml` -> `[tool.coverage.report] fail_under = 80`.
     Lo hace cumplir `coverage report`, que solo acepta UN umbral global.

  2. `AGENTS.md §6.3` -> suelos por modulo:

         core (errors, bricks, parser, registry, storage, runtime,
         handoff, agent, workflow, runcontroller)   >= 90 %
         CLI                                           >= 70 %
         paths.py                                      >= 60 %

     **Este contrato no lo puede comprobar `coverage report`.** Solo admite
     un umbral global, y ningun test del repo lo miraba. Era una cifra que
     se declaraba y no se verificaba.

Este script es la parte que faltaba. Vive en `scripts/` y no en
`.pipelinek/`, porque un guard que no esta versionado no es un guard.

Los suelos van POR PAQUETE, no por modulo
-----------------------------------------
WI-93 implemento este contrato con una lista de 21 modulos escrita a mano, y
eso solo vigilaba `runtime/`: los otros siete paquetes podian recibir un
modulo nuevo al 40 % sin que nadie se enterara. Era el mismo fallo que el
propio WI-93 cerraba para `runtime/`, sin cerrar en el resto.

Aqui el suelo lo **hereda el modulo de su paquete**:

    SUELOS_POR_PAQUETE: prefijo de ruta -> suelo

Una sola fuente, sin lista que mantener, y un modulo nuevo en CUALQUIER
paquete cubierto queda vigilado en el momento de aparecer. La unica excepcion
es `paths.py`, al que §6.3 le da un suelo propio (60 %) distinto del de su
paquete; esta en `EXCEPCIONES` y se declara a proposito.

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

ROOT = Path(__file__).resolve().parent.parent
RC = ROOT / ".coverage.rc"

# AGENTS §6.3, por paquete. Todo modulo con codigo bajo uno de estos
# prefijos hereda su suelo; no hay que listar modulos, y por eso no se puede
# olvidar uno.
SUELOS_POR_PAQUETE: dict[str, float] = {
    "src/skillgraph/core/": 90.0,
    "src/skillgraph/resources/": 90.0,
    "src/skillgraph/runtime/": 90.0,
    "src/skillgraph/platform/": 90.0,
    "src/skillgraph/knowledge/": 90.0,
    "src/skillgraph/governance/": 90.0,
    "src/skillgraph/domain/": 90.0,
    "src/skillgraph/cli/": 70.0,
}

# Modulos con suelo PROPIO, distinto del de su paquete. §6.3 exime a
# `paths.py` explicitamente (`>= 60 %`): aplicarle el 90 % de `platform/`
# haria fallar al unico modulo que el propio contrato exonera.
EXCEPCIONES: dict[str, float] = {
    "src/skillgraph/platform/paths.py": 60.0,
}

# Comprobacion ADICIONAL, por conjunto. No sustituye a la por modulo: es la
# que atrapa el caso de un paquete entero que se degrada de golpe, que la
# suma de modulosflojos tambien veria, pero con un mensaje que lo dice.
SUELOS_AGGREGADOS: dict[str, float] = {
    "src/skillgraph/runtime/": 90.0,
    "src/skillgraph/cli/": 70.0,
}

# `pyproject.toml` -> [tool.coverage.report]. Se comprueba aparte porque
# `coverage report` ya lo aplica, pero solo si alguien lo ejecuta: aqui
# queda registrado que se comprobo, no solo que existe.
SUELO_GLOBAL = 80.0


def suelo_de(ruta: str) -> float | None:
    """Suelo que hereda `ruta`, o `None` si §6.3 no gobierna ese modulo.

    Precedencia: la excepcion propia gana al suelo del paquete. Se declara
    aqui, y no repartida por `main()`, para que la regla sea una sola
    pregunta y se pueda probar sola.
    """
    if ruta in EXCEPCIONES:
        return EXCEPCIONES[ruta]
    for prefijo, suelo in SUELOS_POR_PAQUETE.items():
        if ruta.startswith(prefijo):
            return suelo
    return None


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

    print("== AGENTS §6.3, por modulo (el suelo lo hereda del paquete) ==")
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

    print("== paquetes declarados que no aportan ningun modulo ==")
    for prefijo in sorted(SUELOS_POR_PAQUETE):
        con_codigo = [f for f in files if f.startswith(prefijo) and _tiene_codigo(files[f])]
        if con_codigo:
            continue
        # Con suelos por paquete desaparece la via por la que WI-93
        # detectaba un modulo fantasma (la lista lo nombraba). Esta es la
        # asercion que la sustituye: si un paquete declarado no aporta ni un
        # modulo, o se borro o se renombro, y hay que enterarse en vez de
        # medir en silencio sobre un paquete que ya no existe.
        msg = f"{prefijo}: paquete con suelo declarado y ningun modulo en el informe"
        lineas.append(f"  ?    {msg}")
        fallos.append(msg)
    if not fallos or not any("ningun modulo" in f for f in fallos):
        lineas.append("  OK   todo paquete declarado aporta modulos con codigo")

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
        fallos.append(f"global mide {p:.2f} %, por debajo de {SUELO_GLOBAL:.0f} %")

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
    print("VEREDICTO: todos los suelos declarados se cumplen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
