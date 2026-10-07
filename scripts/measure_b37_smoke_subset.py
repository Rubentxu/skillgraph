"""La medicion que abre B37 — el bypass que queda, y lo que el smoke no mide.

B36 dejo el guard de estado en su sitio: `HOOK_SKIP_TESTS=1` sigue siendo
necesario para commitear `src/`, porque el smoke corre **sobre lo stageado** y
el fichero de guards suele estar entre ellos. Ese bypass es lo que queda, y
apunta a un agujero mas grande: **que mide el smoke, y que no**.

El hook, MEDIDO en `scripts/hooks/pre-commit:113`:

    STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.py$')
    pytest -q $STAGED_PY

Luego el smoke corre UN SUBCONJUNTO del arbol, y hay tres formas de que ese
subconjunto no mida lo que parece. Se cuentan sobre el historial real.

Ejecutar:  uv run python scripts/measure_b37_smoke_subset.py
"""

from __future__ import annotations

import pathlib
import subprocess

RAIZ = pathlib.Path(__file__).resolve().parent.parent

if not (RAIZ / ".git").exists():
    # MEDIDO HOY en el instrumento de B36: ejecutado fuera del repo, midi `0`
    # commits sin quejarse. Una medicion que reporta cero sin avisar es
    # indistinguible de una que mide.
    raise SystemExit(
        f"RAIZ no es el repositorio: {RAIZ}\n"
        "Este script vive en scripts/ y deriva la raiz de donde esta."
    )


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(RAIZ), capture_output=True, text=True, check=False
    )
    return proc.stdout


def es_test(ruta: str) -> bool:
    return ruta.startswith("tests/") and ruta.endswith(".py")


def main() -> None:
    print("B37 — que mide el smoke del pre-commit, y que no")
    print(f"raiz: {RAIZ}\n")

    commits = [c for c in git("rev-list", "HEAD").split() if c]
    print(f"RONDA 1 — LOS commits DEL REPO: {len(commits)}\n")

    con_py = sin_py = 0
    solo_no_test = 0
    test_y_codigo = 0
    solo_codigo = 0
    for commit in commits:
        ficheros = git("show", "--name-only", "--format=", commit).splitlines()
        py = [f for f in ficheros if f.endswith(".py")]
        if not py:
            sin_py += 1
            continue
        con_py += 1
        tests = [f for f in py if es_test(f)]
        codigo = [f for f in py if not es_test(f)]
        if codigo and not tests:
            solo_codigo += 1
        elif codigo and tests:
            test_y_codigo += 1
        if not tests:
            solo_no_test += 1

    print("RONDA 2 — QUE LLEVA EL SMOKE EN CADA commit")
    print(f"    commits con .py stageado                    : {con_py}")
    print(f"    commits SIN .py stageado (smoke no corre)   : {sin_py}")
    print(f"    de los .py: stagean tests y codigo a la vez : {test_y_codigo}")
    print(f"    de los .py: stagean SOLO codigo            : {solo_codigo}")
    print(
        "\n    De los que stagean solo codigo, el smoke corre\n"
        "    `pytest -q src/...` sobre ficheros de produccion: no colecta\n"
        "    nada y sale con el codigo 5, que el hook trata como «nada que\n"
        "    ejecutar» y sigue. MEDIDO en el propio hook, linea 117.\n"
    )

    print("RONDA 3 — CUANTOS FICHEROS LLEGA A VER EL SMOKE CUANDO CORRE")
    print("    commits que stagean UN solo .py de test     : ", end="")
    uno = 0
    for commit in commits:
        ficheros = git("show", "--name-only", "--format=", commit).splitlines()
        tests = [f for f in ficheros if es_test(f)]
        if len(tests) == 1:
            uno += 1
    print(uno)
    print(
        "\n    Un commit que stagea un test y toca codigo ejecuta ESE test\n"
        "    y nada mas. Ningun otro guard corre, y el hook no lo dice.\n"
    )

    print("RONDA 4 — EL AGUJO DE ESTE MISMO BLOQUE, CONTADO")
    guard = "tests/test_wi116_suelos_de_cobertura.py"
    cruzan = 0
    for commit in commits:
        ficheros = git("show", "--name-only", "--format=", commit).splitlines()
        py = [f for f in ficheros if f.endswith(".py")]
        if guard in py and any(f.startswith(("src/", "scripts/")) for f in py):
            cruzan += 1
    print(f"    commits que stagean el guard Y tocaron codigo : {cruzan}")
    print(
        "\n    Es el unico caso en que el bypass se ha usado por el guard.\n"
        "    Los demos eran el suelo de cobertura y la cifra de tests, que\n"
        "    dependen del arbol ENTERO y un subconjunto no los puede validar.\n"
    )


if __name__ == "__main__":
    main()
