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

     **Este contrato no lo puede comprobar ninguna herramienta.**
     `coverage report` no acepta umbrales por ruta, y ningun test del
     repo lo mira. Es una cifra que se declara y no se verifica.

Este script es la parte que faltaba: lee el informe JSON de coverage y
comprueba los suelos por modulo. Vive en `scripts/` y no en
`.pipelinek/`, porque un guard que no esta versionado no es un guard.

Como anadir el suelo de un modulo nuevo
----------------------------------------
Anadir una entrada a `SUELOS` con su ruta EXACTA (la clave de
`coverage json`, que es relativa a la raiz del proyecto, con prefijo
`src/skillgraph/`). La clave tiene que existir en el informe: si el
modulo desaparece, el script aborta en vez de medir en silencio.

Trampa conocida: la agregacion
------------------------------
`coverage` con `branch = true` reporta un porcentaje que combina
sentencias y ramas, y una rama parcial cuenta como media. Por eso este
script **agrega recuentos, no porcentajes**: promediar porcentajes da
mas de lo que hay, y un paquete al 95 % de media puede esconder un
modulo al 60 %.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RC = ROOT / ".coverage.rc"

# Ruta del informe (tal como la keya `coverage json`) -> suelo minimo.
# Un mapa, no una lista de sueltos: asi el suelo viaja JUNTO al modulo
# que gobierna y no puede olvidarse uno de los dos.
SUELOS: dict[str, float] = {
    # AGENTS §6.3, "modulos del core", nombrados uno a uno.
    "src/skillgraph/core/errors.py": 90.0,
    "src/skillgraph/core/recipe.py": 90.0,
    "src/skillgraph/core/runtime_types.py": 90.0,
    "src/skillgraph/resources/bricks.py": 90.0,
    "src/skillgraph/resources/parser.py": 90.0,
    "src/skillgraph/resources/registry.py": 90.0,
    "src/skillgraph/resources/workflow.py": 90.0,
    "src/skillgraph/resources/plan_loader.py": 90.0,
    "src/skillgraph/platform/storage.py": 90.0,
    "src/skillgraph/runtime/handoff.py": 90.0,
    "src/skillgraph/runtime/agent.py": 90.0,
    "src/skillgraph/runtime/engine.py": 90.0,
    "src/skillgraph/runtime/runcontroller.py": 90.0,
    "src/skillgraph/runtime/locks.py": 90.0,
    "src/skillgraph/runtime/redaction.py": 90.0,
    "src/skillgraph/runtime/http_adapter.py": 90.0,
    "src/skillgraph/runtime/run_types.py": 90.0,
    "src/skillgraph/runtime/node_execution_delegations.py": 90.0,
    "src/skillgraph/runtime/run_budget_delegations.py": 90.0,
    "src/skillgraph/runtime/run_observability_delegations.py": 90.0,
    # AGENTS §6.3, resto del contrato.
    "src/skillgraph/platform/paths.py": 60.0,
}

# Prefijos que se comprueban como conjunto agregado.
SUELOS_AGGREGADOS: dict[str, float] = {
    "src/skillgraph/runtime/": 90.0,
    "src/skillgraph/cli/": 70.0,
}

# `pyproject.toml` -> [tool.coverage.report]. Se comprueba aparte porque
# `coverage report` ya lo aplica, pero solo si alguien lo ejecuta: aquí
# queda registrado que se comprobo, no solo que existe.
SUELO_GLOBAL = 80.0


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


def main() -> int:
    files = informe()
    fallos: list[str] = []

    print("== AGENTS §6.3, modulos con suelo individual ==")
    for ruta, suelo in sorted(SUELOS.items()):
        entrada = files.get(ruta)
        if entrada is None:
            msg = f"{ruta}: no aparece en el informe de coverage"
            print(f"  ?    {msg}")
            fallos.append(msg)
            continue
        p = porcentaje([entrada])
        ok = p >= suelo
        print(f"  {'OK  ' if ok else 'BAJO'} {p:6.2f} %  (suelo {suelo:5.1f} %)  {ruta}")
        if not ok:
            fallos.append(f"{ruta} mide {p:.2f} %, por debajo de su suelo del {suelo:.0f} %")

    print()
    print("== AGENTS §6.3, conjuntos agregados ==")
    for prefijo, suelo in sorted(SUELOS_AGGREGADOS.items()):
        entradas = [e for f, e in files.items() if f.startswith(prefijo)]
        if not entradas:
            msg = f"{prefijo}: no hay modulos en el informe"
            print(f"  ?    {msg}")
            fallos.append(msg)
            continue
        p = porcentaje(entradas)
        ok = p >= suelo
        print(
            f"  {'OK  ' if ok else 'BAJO'} {p:6.2f} %  (suelo {suelo:5.1f} %)  "
            f"{prefijo} = {len(entradas)} modulos"
        )
        if not ok:
            fallos.append(f"{prefijo} mide {p:.2f} %, por debajo del suelo del {suelo:.0f} %")

    print()
    print("== pyproject.toml, suelo global ==")
    p = porcentaje(list(files.values()))
    ok = p >= SUELO_GLOBAL
    print(f"  {'OK  ' if ok else 'BAJO'} {p:6.2f} %  (fail_under = {SUELO_GLOBAL:.0f} %)")
    if not ok:
        fallos.append(f"global mide {p:.2f} %, por debajo de {SUELO_GLOBAL:.0f} %")

    print()
    print("== todo modulo de runtime/ tiene suelo (el paquete que §6.3 nombra) ==")
    # Sin esto, el checker solo comprueba lo que le dijeron: anadir un
    # modulo nuevo a runtime/ sin suelo pasaria desapercibido, que es
    # exactamente el fallo que este guard viene a cerrar. Un guard que
    # solo vigila la lista que el mismo mantiene no vigila nada.
    #
    # Se excluyen los modulos SIN NADA que cubrir (0 sentencias y 0
    # ramas, tipicamente `__init__.py` de reexport): exigirles un suelo
    # seria exigir medir un fichero vacio, y ademas hace division por
    # cero. Un guard que revienta con ruido sobre lo que no importa
    # teaches a ignorar al guard.
    sin_suelo: list[str] = []
    for f in sorted(files):
        if not f.startswith("src/skillgraph/runtime/") or not f.endswith(".py"):
            continue
        if f in SUELOS:
            continue
        s = files[f]["summary"]  # type: ignore[index]
        if int(s["num_statements"]) + int(s["num_branches"]) == 0:  # type: ignore[index]
            continue
        sin_suelo.append(f)
    for f in sin_suelo:
        msg = f"{f}: modulo de runtime/ con codigo y sin suelo declarado en SUELOS"
        print(f"  ?    {msg}")
        fallos.append(msg)
    if not sin_suelo:
        print("  OK   todo modulo de runtime/ con codigo tiene suelo declarado")

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
