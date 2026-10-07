#!/usr/bin/env python3
"""B37 — sondas de mutacion del silencio del pre-commit.

Que tiene que demostrar
-----------------------
Que el guard de B37 vigila lo que dice vigilar. El defecto que B37 cerro no
era un bug de logica: era que el hook se **callaba** en dos de los tres
caminos por los que puede pasar, y su `OK` final era el mismo en los tres.
Un defecto asi no se caza buscando una cadena —el hook TIENE la cadena que
busca— sino ejecutando el hook y mirando lo que imprime.

Por eso estas sondas deshacen el **silencio**, no la logica: cada una quita
una de las ramas del bloque 4, o devuelve al bloque el defecto exacto que se
cerro, y exige que caiga el test que nombra ese camino.

Que son las sondas
------------------
    M1  el bloque 4 metido DENTRO del `if` del smoke -- el defecto exacto de
        antes del arreglo, en su forma literal
    M2  sin la rama de «nada stageado» (los 551 commits)
    M3  sin la rama del bypass (`HOOK_SKIP_TESTS=1`)
    M4  sin la rama `else` (el camino que si mide tampoco cierra declarando)
    M5  el hook MIENTE: dice que ha medido en el camino en que no ha medido
    M6  la declaracion se mueve DETRAS del `OK`

M1 y M6 son las que importan mas, porque un guard que solo comprueba «sale
algo sobre los tests» approves las dos: M1 ejecuta el bloque entero pero solo
en un camino, y M6 lo ejecuta en los tres pero debajo del `OK`. Las dos cosas
que el arreglo afirmaba —que se declara en TODOS los caminos, y que se declara
AL FINAL— son las que aqui se ven caer.

El harness se comprueba a si mismo antes de mutar
-------------------------------------------------
`CAZADA` exige que caiga el diagnostico NOMBRADO de esa sonda, no cualquier
test rojo: cuatro sondas que heredan el fallo de la quinta se contarian como
cuatro y el numero seria falso. El ancla de cada sonda se busca en el texto
leido justo antes de mutar, y si no aparece se reporta `SIN_SONDA` en vez de
contarse como cazada — que es lo que paso en B37 con el texto viejo tras un
`ruff format`.

Y el harness **restaura escribiendo** lo que leyo, no con `git checkout --`
(el defecto que B36 cerro: `git checkout --` restaura del indice, asi que
sin commit debajo «restaurar» y «borrar» son la misma operacion).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

HOOK = "scripts/hooks/pre-commit"
TEST = "tests/test_b37_smoke_subset.py"

#: Las tres lineas del bloque 4 del hook, y las tres ramas que las sostienen.
#: Se declaran como ancla y no se derivan: el bloque que se vigila son tres
#: lineas concretas y un `rstrip` sobre ellas seria mas fragil, no menos.
DECLARACION_SIN_RAMA = (
    'echo "[pre-commit] tests: NINGUNO stageado',
    'echo "[pre-commit] tests: OMITIDOS por HOOK_SKIP_TESTS=1',
    'echo "[pre-commit] tests: el smoke de arriba es lo UNICO',
)

#: El bloque 4 tal cual esta en el hook, con los mismos em-dash (U+2014): si
#: aqui se escriben guiones ASCII la sustitucion no ocurre, la sonda no muta
#: nada, y el harness se reportaria a si mismo como seis cosas cazadas.
BLOQUE_4 = """if [ "${HOOK_SKIP_TESTS:-0}" = "1" ]; then
    echo "[pre-commit] tests: OMITIDOS por HOOK_SKIP_TESTS=1 — este commit no ha ejecutado ninguno"
elif [ -z "$STAGED_PY" ]; then
    echo "[pre-commit] tests: NINGUNO stageado — este commit no ha medido nada"
else
    echo "[pre-commit] tests: el smoke de arriba es lo UNICO que ha corrido; el resto no se ha medido"
fi"""

#: El `OK` final. Ancla propia, porque M6 depende de poder moverlo.
OK_FINAL = 'echo "[pre-commit] OK"'


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del hook, y el test DIAGNOSTICO que tiene que caer.

    `diagnostico` es uno solo y nombrado a proposito: un `assert` que cubre
    una propiedad la puede cubrir cualquier test, y entonces la sonda pasa sin
    que nadie mire si ese test es el que la entendia.
    """

    nombre: str
    fichero: str
    antes: str | tuple[str, ...]
    despues: str | None
    diagnostico: str


SONDAS: tuple[Sonda, ...] = (
    # --- M1: el defecto exacto, en su forma literal ------------------------
    #
    # El bloque 4 metido dentro del `if` del smoke se EJECUTA: no hay error de
    # sintaxis, el hook sale con 0, y su salida sigue llevando la cadena que un
    # guard por busqueda miraria. Solo se cae si el test mira los tres caminos.
    Sonda(
        "M1_el_bloque_metido_dentro_del_if_del_smoke",
        HOOK,
        (
            "fi\n\n# -------------------------------------------------------------------\n"
            "# 4. Lo que este hook HA MEDIDO",
            BLOQUE_4,
        ),
        '    if [ -n "$STAGED_PY" ]; then\n'
        '        echo "[pre-commit] tests: NINGUNO stageado - este commit no ha medido nada"\n'
        '        echo "[pre-commit] tests: OMITIDOS por HOOK_SKIP_TESTS=1 - este commit no ha ejecutado ninguno"\n'
        '        echo "[pre-commit] tests: el smoke de arriba es lo UNICO que ha corrido; el resto no se ha medido"\n'
        "    fi\nfi\n\n# -------------------------------------------------------------------\n"
        "# 4. Lo que este hook HA MEDIDO",
        f"{TEST}::test_sin_ficheros_py_stageados_dice_que_no_ha_medido",
    ),
    # --- M2: se borra la rama de «nada stageado» --------------------------
    Sonda(
        "M2_sin_la_rama_de_nada_stageado",
        HOOK,
        (
            'elif [ -z "$STAGED_PY" ]; then\n'
            '    echo "[pre-commit] tests: NINGUNO stageado — este commit no ha medido nada"\n'
        ),
        "",
        f"{TEST}::test_sin_ficheros_py_stageados_dice_que_no_ha_medido",
    ),
    # --- M3: se borra la rama del bypass ----------------------------------
    Sonda(
        "M3_sin_la_rama_del_bypass",
        HOOK,
        (
            'if [ "${HOOK_SKIP_TESTS:-0}" = "1" ]; then\n'
            '    echo "[pre-commit] tests: OMITIDOS por HOOK_SKIP_TESTS=1 — este commit no ha ejecutado ninguno"\n'
            "elif"
        ),
        "if",
        f"{TEST}::test_con_bypass_dice_que_los_tests_se_omitieron",
    ),
    # --- M4: el camino que SI mide tampoco cierra declarando --------------
    Sonda(
        "M4_el_camino_que_si_mide_tampoco_cierra",
        HOOK,
        (
            "else\n"
            '    echo "[pre-commit] tests: el smoke de arriba es lo UNICO que ha corrido; el resto no se ha medido"\n'
        ),
        "",
        f"{TEST}::test_con_smoke_corriendo_lo_dice_tambien",
    ),
    # --- M5: el hook miente -----------------------------------------------
    #
    # No basta con que diga ALGO: tiene que decir lo que ES. Si el camino
    # silencioso pasa a declarar «medido», el hook miente con la misma
    # claridad con la que antes callaba.
    Sonda(
        "M5_el_hook_miente_en_el_camino_que_no_mide",
        HOOK,
        DECLARACION_SIN_RAMA[1],
        'echo "[pre-commit] tests: medido',
        f"{TEST}::test_con_bypass_dice_que_los_tests_se_omitieron",
    ),
    # --- M6: la declaracion se mueve detras del OK ------------------------
    Sonda(
        "M6_la_declaracion_detras_del_ok",
        HOOK,
        ("fi\n\n" + OK_FINAL),
        (
            "fi\n\n"
            + OK_FINAL
            + '\necho "[pre-commit] nota: todo lo anterior, mas lo que no se midio"\n'
        ),
        f"{TEST}::test_el_ok_cierra_despues_de_declarar_los_tests",
    ),
)

BASELINE: tuple[str, ...] = (TEST,)


def _rojos(rc: int, salida: str) -> bool:
    return rc != 0 and ("failed" in salida or "error" in salida)


def _pytest(*objetivos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *objetivos, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )


def main() -> int:
    print("=" * 74)
    print("B37 — sondas de mutacion")
    print("=" * 74)

    hook = RAIZ / HOOK
    original = hook.read_text(encoding="utf-8")

    # Las tres lineas de la declaracion tienen que estar AHORA, con este texto.
    # Si `ruff format` o un retoque las movieron, el numero de sondas cazadas
    # seria falso y es mejor pararse aqui que reportar un verde inventado.
    faltan = [a for a in DECLARACION_SIN_RAMA if a not in original]
    if faltan:
        print("BLOQUE 4 CAMBIADO: estas lineas ya no estan en el hook:")
        for a in faltan:
            print(f"  {a}")
        print("Las sondas apuntan al texto anterior. Actualizalas antes de contar.")
        return 1

    base = _pytest(*BASELINE)
    print(f"\nbaseline rc={base.returncode}: {base.stdout.strip().splitlines()[-1]}")
    if base.returncode != 0:
        print("BASELINE ROTO: las sondas no dirian nada. Se para aqui.")
        return 1

    cazadas = invalidas = sin_sonda = inocuas = 0
    print()
    try:
        for sonda in SONDAS:
            antes = sonda.antes if isinstance(sonda.antes, tuple) else (sonda.antes,)
            if any(a not in original for a in antes):
                print(f"  SIN_SONDA  {sonda.nombre}: el ancla no esta en {sonda.fichero}")
                print("             (el texto se movio; la sonda apunta al estado viejo)")
                sin_sonda += 1
                continue

            mutado = original
            for a in antes:
                mutado = mutado.replace(a, sonda.despues or "", 1)
            if mutado == original:
                print(f"  SIN_SONDA  {sonda.nombre}: la sustitucion no cambio nada")
                sin_sonda += 1
                continue

            hook.write_text(mutado, encoding="utf-8")
            resultado = _pytest(sonda.diagnostico)
            salida = resultado.stdout + resultado.stderr
            if _rojos(resultado.returncode, salida):
                print(f"  CAZADA     {sonda.nombre}  -> {sonda.diagnostico.split('::')[-1]}")
                cazadas += 1
            elif "INTERNALERROR" in salida or "SyntaxError" in salida or "No such file" in salida:
                print(f"  INVALIDA   {sonda.nombre}: la sonda revienta el hook, no lo deja callar")
                invalidas += 1
            else:
                print(f"  INOCUA     {sonda.nombre}: el hook sigue diciendo lo que debe")
                inocuas += 1
    finally:
        hook.write_text(original, encoding="utf-8")

    print()
    print("=" * 74)
    print(
        f"cazadas {cazadas}/{len(SONDAS)}   invalidas {invalidas}   "
        f"inocuas {inocuas}   sin sonda {sin_sonda}"
    )
    control = _pytest(*BASELINE)
    restaurado = hook.read_text(encoding="utf-8") == original
    print(f"tras restaurar: rc={control.returncode}, hook intacto={restaurado}")
    print("=" * 74)
    return 0 if cazadas == len(SONDAS) and invalidas == 0 and sin_sonda == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
