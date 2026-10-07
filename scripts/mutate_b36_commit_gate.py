"""Sondas de mutacion de B36 — un guard que obliga a apagar el gate que lo contiene.

La regla del repo, desde WI-113: un guard que no se ha visto caer no es un
guard. Y desde B26/WI-114: una sonda que reventa el modulo en vez de romper la
propiedad no es «cazada», es el arbol roto.

B36 tiene DOS guards que se pueden medir por separado, y esa separacion es el
bloque:

    E1..E3  el ESTADO     — que solo account lo que un `git checkout --` pierde
    I1..I2  la CAPACIDAD  — que ningun instrumento pueda ejecutar git destructivo

Las sondas de `ESTADO` atacan el parser; las de `CAPACIDAD` plantan una llamada
real en un instrumento real.

Ejecutar:  uv run python scripts/mutate_b36_commit_gate.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent

TEST = "tests/test_wi116_suelos_de_cobertura.py"
INSTRUMENTO = "scripts/mutate_b9_gate_1_0.py"

#: Cada sonda es (nombre, fichero, PARES, objetivo), y PARES es una tupla de
#: (antes, despues). Son tuplas y no un solo par porque MEDIDO que hay sondas
#: que NO caben en un cambio solo: la que planta una llamada destructiva tiene
#: que cambiar la importacion Y el cuerpo.
SONDAS: tuple[tuple[str, str, object, str], ...] = (
    # --- E1: el estado STAGEADO vuelve a contar como trabajo sucio --------
    #
    # El defecto que B36 arregla. Volver a tratar `M ` como sucio es
    # exactamente lo que hacia que todo commit que tocara `src/` o `scripts/`
    # se pusiera rojo, y lo que obligaba a `HOOK_SKIP_TESTS=1`.
    (
        "E1_el_stageado_vuelve_a_contar_como_sucio",
        TEST,
        '        if estado[1] != " ":',
        '        if estado[0] != " ":',
        f"{TEST}::TestLaDecisionDelGuardEsMedible::test_un_cambio_STAGEADO_no_culpa_al_operador",
    ),
    # --- E2: la foto de `_restaura()` desaparece --------------------------
    #
    # Sin la restauracion, el guard de estado no falla: el fallo lo produce el
    # trabajo sin stagear que queda debajo. Lo que se mide aqui es que el
    # criterio del guard sigue teniendo una sola condicion, y esa condicion se
    # puede vaciar sin que nadie lo note.
    (
        "E2_la_decision_del_guard_se_vacia",
        TEST,
        '        if estado[1] != " ":\n            sucio.append(linea)',
        "        if False:  # sonda: la decision se ha vaciado\n            sucio.append(linea)",
        f"{TEST}::TestLaDecisionDelGuardEsMedible::test_un_cambio_SIN_STAGEAR_si_culpa",
    ),
    # --- E3: `??` deja de contar ------------------------------------------
    #
    # Un fichero NUEVO no lo destruye `checkout --`, pero si `git clean -fd`,
    # que es el otro extremo del mismo antipatron. MEDIDO AL ESCRIBIR ESTE
    # HARNESS: sin `?` en COLUMNAS_INDICE, `??` se colaba y el guard perdiaba
    # justo el caso que un `git add -A` todavia no ha cubIERTO.
    (
        "E3_un_fichero_nuevo_deja_de_contar",
        TEST,
        'COLUMNAS_INDICE = frozenset(" MADRCU?!")',
        'COLUMNAS_INDICE = frozenset(" MADRCU")',
        f"{TEST}::TestLaDecisionDelGuardEsMedible::test_un_fichero_NUEVO_tambien_culpa",
    ),
    # --- I1: se planta una llamada destructiva de verdad ------------------
    #
    # La sonda de CAPACIDAD por excelencia: se mete `git checkout --` en un
    # instrumento REAL, con la forma que el guard rastrea, y el guard tiene que
    # ponerse rojo. Es el antipatron que el guard existe para impedir.
    (
        "I1_se_planta_un_git_destructivo_en_un_instrumento",
        INSTRUMENTO,
        (
            (
                "import subprocess",
                "import subprocess\n\n\ndef _sonda_b36() -> None:\n"
                '    """MEDIDO: esto es lo que el guard tiene que cazar."""\n'
                '    subprocess.run(["git", "checkout", "--", "x"], cwd=RAIZ, check=False)',
            ),
        ),
        None,
        f"{TEST}::TestNingunInstrumentoPuedeBorrarTrabajo::test_ningun_instrumento_llama_a_un_git_DESTRUCTIVO",
    ),
    # --- I2: el derivado se vacia ----------------------------------------
    #
    # Sin esto, una derivacion rota —un `rglob` que no encuentra `scripts/`, un
    # filtro que se come el directorio entero— daria VERDE con la propiedad
    # rota. Es el contrasalto, attacking el contrasalto.
    (
        "I2_el_contrasalto_del_derivado_no_dispara",
        TEST,
        "        assert len(self._instrumentos()) >= self.MINIMO_INSTRUMENTOS, (",
        "        assert len(self._instrumentos()) >= 10_000, (",
        f"{TEST}::TestNingunInstrumentoPuedeBorrarTrabajo::test_el_derivado_NO_sale_vacio",
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
    print("B36 — sondas de mutacion")
    print("=" * 74)

    base = _pytest(*BASELINE)
    print(f"\nbaseline rc={base.returncode}: {base.stdout.strip().splitlines()[-1]}")
    if base.returncode != 0:
        print("BASELINE ROTO: las sondas no dirian nada. Se para aqui.")
        return 1

    cazadas = invalidas = sin_sonda = 0
    print()
    for nombre, fichero, antes, despues, objetivo in SONDAS:
        ruta = RAIZ / fichero
        original = ruta.read_text(encoding="utf-8")
        lista = antes if isinstance(antes, tuple) else ((antes, despues),)
        try:
            faltan = [a for a, _ in lista if a not in original]
            if faltan:
                print(f"  SIN_SONDA  {nombre}: el ancla no esta en {fichero}")
                print("             (ruff format cambio el texto; apunta al estado viejo)")
                sin_sonda += 1
                continue
            mutado = original
            for a, d in lista:
                mutado = mutado.replace(a, d, 1)
            ruta.write_text(mutado, encoding="utf-8")
            resultado = _pytest(objetivo)
            salida = resultado.stdout + resultado.stderr
            if _rojos(resultado.returncode, salida):
                print(f"  CAZADA     {nombre}")
                cazadas += 1
            elif "INTERNALERROR" in salida or "SyntaxError" in salida:
                print(f"  INVALIDA   {nombre}: la sonda revienta el modulo")
                invalidas += 1
            else:
                print(f"  INOCUA     {nombre}: el arbol sigue en verde")
        finally:
            ruta.write_text(original, encoding="utf-8")

    print()
    print("=" * 74)
    print(f"cazadas {cazadas}/{len(SONDAS)}   invalidas {invalidas}   sin sonda {sin_sonda}")
    control = _pytest(*BASELINE)
    print(f"tras restaurar: rc={control.returncode}")
    print("=" * 74)
    return 0 if cazadas == len(SONDAS) and invalidas == 0 and sin_sonda == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
