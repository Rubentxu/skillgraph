#!/usr/bin/env python3
"""B38 — sondas de mutacion del pre-push.

Que tiene que demostrar
-----------------------
Que el guard de B38 vigila lo que dice vigilar. Un hook que exige una cadena
literal tiene una forma de fallo muy facil de no ver: que la cadena que exige
ya no sea la que emite el delegado. Un test que solo comprueba «el hook dice
lo que tiene que decir» pasaria con una cadena vieja, y el fallo apareceria en
el proximo push de todos, con el hook rehusando verificar por una frase que
nadie recuerda haber escrito.

Que son las sondas
------------------
    M1  el `grep` del veredicto desaparece -> el hook vuelve a HEREDAR el exit
        code, que es el defecto entero de B38
    M2  el `grep` pasa a buscar `SUCCESS` a secas -> el hook acepta
        «Pipeline finished with Successful»
    M3  el bypass vuelve a decir `OK: la receta dio SUCCESS`
    M4  el bypass vuelve a callarse (dice OK sin declarar)
    M5  el `OK` del camino bueno deja de citar el veredicto que exigio
    M6  la cadena exigida no es la que declara el resto del repo (contravariante
        del test derivado)
    M7  el hook no sale distinto de cero cuando el delegado no emite veredicto
    M8  sin la `x` del grep, vuelve a aceptar una linea que contiene el veredicto
    M9  el grep pasa a no-sensible-a-mayusculas

M6 y M7 son las que importan mas, porque las dos desarman la propiedad sin
quitar una sola palabra visible: M6 deja el hook exigeindo una frase que nadie
emite, y M7 deja el hook diciendo el error sin cortar el push. Un guard que
solo mira lo que el hook IMPRIMA no las ve — por eso los diagnosticos de este
harness miran tambien el CODIGO DE SALIDA.

El harness se comprueba a si mismo antes de mutar
-------------------------------------------------
`CAZADA` exige que caiga el diagnostico NOMBRADO de esa sonda. Y el ancla se
busca en el texto leido justo antes de mutar: el `ruff format` movió este
fichero al escribirse, y una sonda que apunta al texto viejo se reporta
`SIN_SONDA` en lugar de contarse como cazada.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

HOOK = "scripts/hooks/pre-push"
TEST = "tests/test_b38_pre_push_veracity.py"

#: Ancla CON su indentacion, y la unicidad se exige abajo. Sin los
#: cuatro espacios esta cadena es subcadena de dos sitios —el codigo y
#: el comentario que lo explica— y `replace(..., 1)` se come el que
#: aparece primero, que es el comentario. MEDIDO: asi la sonda M2 muto
#: la prosa, dejo el codigo intacto, el hook siguio vigilado y el
#: harness la reporto INOCUA.
GREP_VEREDICTO = '    if ! grep -qxF "$VEREDICTO_RECETA" "$_log"; then'

BLOQUE_BYPASS = (
    'echo "[pre-push] tests: OMITIDOS por HOOK_SKIP_PUSH_TESTS=1 — este push NO ha sido verificado"'
)

DECLARACION_CADENA = "VEREDICTO_RECETA='Pipeline finished with SUCCESS'"


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del hook, y el test DIAGNOSTICO que tiene que caer."""

    nombre: str
    fichero: str
    antes: str | tuple[str, ...]
    despues: str | None
    diagnostico: str


SONDAS: tuple[Sonda, ...] = (
    # --- M1: sin el grep, el defecto entero de B38 vuelve ------------------
    Sonda(
        # MEDIDO INOCUA la primera vez: apuntaba al test del camino MALO, y ahi
        # no puede caer — con la frase cambiada el grep tampoco la encuentra
        # cuando el delegado no emite nada, luego `rc != 0` se cumple igual y
        # el test pasa. La frase equivocada rompe el camino BUENO, que es el
        # que exige `rc == 0`. Es el error de razonar sobre «que cambia» en
        # vez de sobre «que se rompe».
        "M1_el_grep_exige_una_frase_que_nadie_emite",
        HOOK,
        GREP_VEREDICTO,
        '    if ! grep -qxF "Pipeline finished with Successful" "$_log"; then',
        f"{TEST}::test_un_delegado_que_si_ejecuta_dice_un_success_verificado",
    ),
    # --- M2: grep por `SUCCESS` a secas ------------------------------------
    #
    # Es la sonda que separa EXIGIR de BUSCAR: con `grep -q SUCCESS` el
    # delegado de M2 pasa, porque «Successful» contiene la palabra.
    Sonda(
        # MEDIDO INOCUA la primera vez, y por el motivo mas tonto: el
        # contraejemplo era «Successful» y `Successful` NO contiene `SUCCESS`,
        # porque grep distingue mayusculas. Se reconstruye sobre el caso que
        # si distingue: una linea que CONTIENE el veredicto sin SER el
        # veredicto.
        "M2_el_grep_acepta_una_linea_que_contiene_el_veredicto",
        HOOK,
        GREP_VEREDICTO,
        '    if ! grep -qF "$VEREDICTO_RECETA" "$_log"; then',
        f"{TEST}::test_el_hook_exige_la_linea_entera_y_no_una_subcadena",
    ),
    # --- M3: el bypass vuelve a decir SUCCESS ------------------------------
    Sonda(
        "M3_el_bypass_vuelve_a_afirmar_SUCCESS",
        HOOK,
        BLOQUE_BYPASS,
        'echo "[pre-push] OK: la receta canonica dio SUCCESS sobre $(git rev-parse --short HEAD)"',
        f"{TEST}::test_el_bypass_dice_que_no_ha_sido_verificado",
    ),
    # --- M4: el bypass vuelve a callarse ----------------------------------
    Sonda(
        "M4_el_bypass_vuelve_a_callarse",
        HOOK,
        BLOQUE_BYPASS,
        'echo "[pre-push] OK"',
        f"{TEST}::test_el_bypass_dice_que_no_ha_sido_verificado",
    ),
    # --- M5: el OK deja de citar el veredicto que exigio -------------------
    Sonda(
        "M5_el_ok_deja_de_citar_el_veredicto",
        HOOK,
        (
            'echo "[pre-push] OK: verificado — el delegado imprimio '
            "'$VEREDICTO_RECETA' sobre $(git rev-parse --short HEAD)\"",
        ),
        'echo "[pre-push] OK: la receta dio SUCCESS"',
        f"{TEST}::test_un_delegado_que_si_ejecuta_dice_un_success_verificado",
    ),
    # --- M6: la cadena exigida no es la que declara el repo ---------------
    #
    # La frase se conserva INTACTA en el log de error, luego un guard que
    # buscase la cadena no lo notaria: el defecto es que se EXIGE otra.
    Sonda(
        "M6_el_hook_exige_una_frase_que_nadie_emite",
        HOOK,
        (DECLARACION_CADENA,),
        "VEREDICTO_RECETA='Pipeline finished con exito'",
        f"{TEST}::test_el_veredicto_exigido_es_el_que_emite_la_receta",
    ),
    # --- M7: dice el error y deja pasar el push ----------------------------
    Sonda(
        "M8_sin_la_x_vuelve_a_aceptar_la_subcadena",
        HOOK,
        GREP_VEREDICTO,
        '    if ! grep -qF "$VEREDICTO_RECETA" "$_log"; then',
        f"{TEST}::test_el_hook_exige_la_linea_entera_y_no_una_subcadena",
    ),
    Sonda(
        # MEDIDO INOCUA la primera vez: apuntaba al contraejemplo «Successful»,
        # que NO distingue mayusculas porque `Successful` no es `SUCCESS` con
        # otra capitalizacion sino otra palabra mas larga —el grep la rechazaba
        # con y sin `-i`. Una sonda que no puede distinguir no mide nada, y hay
        # que cazarla ahi, no dejarla pasar como si midiera.
        "M9_el_grep_pasa_a_no_sensible_a_mayusculas",
        HOOK,
        GREP_VEREDICTO,
        '    if ! grep -qxiF "$VEREDICTO_RECETA" "$_log"; then',
        f"{TEST}::test_el_veredicto_no_se_acepta_en_otra_capitalizacion",
    ),
    Sonda(
        "M7_dice_el_error_pero_no_corta_el_push",
        HOOK,
        '        echo "Bypass siempre: git push --no-verify"\n        exit 1\n    fi\n'
        '    echo "[pre-push] OK: verificado',
        '        echo "Bypass siempre: git push --no-verify"\n'
        "        VEREDICTO_EN_VERDE=1\n    fi\n"
        '    echo "[pre-push] OK: verificado',
        f"{TEST}::test_un_delegado_que_no_hace_nada_no_produce_un_success",
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
    print("B38 — sondas de mutacion")
    print("=" * 74)

    hook = RAIZ / HOOK
    original = hook.read_text(encoding="utf-8")

    for etiqueta, ancla in (
        ("el grep del veredicto", GREP_VEREDICTO),
        ("la declaracion de la cadena", DECLARACION_CADENA),
        ("la linea del bypass", BLOQUE_BYPASS),
    ):
        if ancla not in original:
            print(f"ANCLA AUSENTE: {etiqueta}. Las sondas apuntan al texto viejo.")
            for linea in original.splitlines():
                if "grep" in linea or "VEREDICTO_RECETA" in linea or "OMITIDOS" in linea:
                    print(f"   el hook tiene: {linea.strip()[:100]}")
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
            # La unicidad es la parte que faltaba. MEDIDO: un ancla que
            # aparece dos veces hace que `replace(..., 1)` mute la primera, que
            # puede ser la PROSA que explica el codigo; la sonda no cambia el
            # hook, el hook sigue bien, y el harness cuenta una sonda que no
            # midio. Es la tercera vez que sale en este repo (B13 M4, B36 y
            # aqui), y por eso es una comprobacion y no una nota.
            counts = [original.count(a) for a in antes]
            if any(n == 0 for n in counts):
                print(f"  SIN_SONDA  {sonda.nombre}: el ancla no esta en {sonda.fichero}")
                sin_sonda += 1
                continue
            if any(n > 1 for n in counts):
                print(
                    f"  SIN_SONDA  {sonda.nombre}: el ancla aparece {counts} veces. "
                    "Un ancla no unica hace que replace mute la primera, que puede "
                    "ser la prosa."
                )
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
            elif "INTERNALERROR" in salida or "SyntaxError" in salida:
                print(f"  INVALIDA   {sonda.nombre}: la sonda revienta el hook")
                invalidas += 1
            else:
                print(f"  INOCUA     {sonda.nombre}: el hook sigue,vigilado")
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
