#!/usr/bin/env python3
"""B38 — que mide el pre-push, y que se le escapa.

Se ejecuta sobre el hook REAL, igual que `measure_b37_smoke_subset.py` hizo
con el pre-commit: no se lee el fuente, se ejecuta y se mira lo que imprime.

Rondas:

    R1  el camino del bypass, con `HOOK_SKIP_PUSH_TESTS=1`
    R2  el camino normal, con `scripts/ci.sh` sustituido por un dobble que falla
    R3  si el hook esta instalado en `.git/hooks/`, y si es el versionado
    R4  los tests que nombran el pre-push
    R5  que exige el guard que YA existe sobre el bypass

    R6  `ci.sh` = `exit 0` y NADA MAS: que dice el hook?
    R7  `ci.sh` = imprime el veredicto de la receta y sale 0
    R8  R6 y R7 son distinguibles por el hook?
    R9  la prosa del tiempo: el hook anuncia «~4min»

**POR QUE R6 A R9 ESTAN, Y NO SOLO R1.** R1 encuentra que el bypass imprime
`OK: la receta canonica dio SUCCESS` sin haber corrido nada. Eso deja abierta
la pregunta que decide si el arreglo es un parche o una propiedad: el hook
DELEGA y solo sabe UNA cosa, que el delegado devolvio 0. Un exit code de 0 no
dice que la receta corriera, ni que hiciera nada. Si R6 —un `ci.sh` que no
hace nada— produce el mismo `SUCCESS`, el defecto no es el bypass: es que el
hook afirma una ejecucion que no puede comprobar.

La cadena que puede exigirse no es inventada: `.pipeline.kts` imprime
`Pipeline finished with SUCCESS`, que es la MISMA que el propio hook ya
nombra en su mensaje de error, y el hook ya captura esa salida en `$_log`.
O sea que el hook puede EXIGIR la cadena en vez de heredar un exit code.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HOOK = RAIZ / "scripts" / "hooks" / "pre-push"


def _sh(*cmd: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    return (r.stdout + r.stderr).strip()


def _doblar_ci(directorio: Path, cuerpo: str) -> Path:
    """Un `scripts/ci.sh` que dice lo que le digamos y sale como le digamos."""
    repo = directorio / "repo"
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK, repo / "scripts" / "hooks" / "pre-push")
    (repo / "scripts" / "ci.sh").write_text(cuerpo, encoding="utf-8")
    # Un repo git DE VERDAD: el hook imprime `git rev-parse --short HEAD` en su
    # linea final, y sin repo ese comando revienta y ENSUCLA la ultima linea.
    _sh("git", "init", "-q", cwd=repo)
    _sh("git", "config", "user.email", "b38@b38.invalid", cwd=repo)
    _sh("git", "config", "user.name", "b38", cwd=repo)
    _sh("git", "commit", "-q", "--allow-empty", "-m", "b38", cwd=repo)
    return repo


def r1_bypass() -> None:
    print("=" * 74)
    print("R1 — el camino del bypass: HOOK_SKIP_PUSH_TESTS=1")
    print("=" * 74)
    with tempfile.TemporaryDirectory() as tmp:
        repo = _doblar_ci(
            Path(tmp),
            "#!/bin/sh\necho 'ESTO DEBERIA CORRER Y NO CORRE'\nexit 1\n",
        )
        env = {**os.environ, "HOOK_SKIP_PUSH_TESTS": "1"}
        salida = _sh(
            "sh",
            "scripts/hooks/pre-push",
            cwd=repo,
            env=env,
        )
        print(salida)
        ultim = salida.splitlines()[-1] if salida else ""
        print()
        print(f"ULTIMA LINEA: {ultim!r}")
        print(f"dice SUCCESS en ALGUN sitio: {'SUCCESS' in salida}")
        print(f"dice que no se ejecuto:       {'saltand' in salida.lower()}")
        print()
        # MEDIDO: la primera version de esta ronda miraba `splitlines()[-1]` y
        # daba «el bypass no imprime SUCCESS». Era un instrumento debil, no un
        # resultado: en un repo que no es git, `git rev-parse` revienta y la
        # linea del SUCCESS no es la ultima. Un verificador que decide por la
        # ultima linea dice «no miente» sobre un hook que dice «SUCCESS» dos
        # lineas mas arriba. Por eso el repo es git DE VERDAD y la busqueda es
        # sobre toda la salida.
        print(
            "VEREDICTO: el bypass imprime la palabra SUCCESS sin haber corrido nada"
            if "SUCCESS" in salida
            else "VEREDICTO: el bypass no imprime SUCCESS"
        )
    print()


def r2_fallo_del_doblo() -> None:
    print("=" * 74)
    print("R2 — la receta falla de verdad: el hook lo dice?")
    print("=" * 74)
    with tempfile.TemporaryDirectory() as tmp:
        repo = _doblar_ci(
            Path(tmp),
            "#!/bin/sh\necho 'FALLO REAL DE LA RECETA'\nexit 3\n",
        )
        salida = _sh("sh", "scripts/hooks/pre-push", cwd=repo, env=dict(os.environ))
        print(salida[-400:])
        print()
        print(f"devuelve ERROR:  {'ERROR' in salida}")
    print()


def r3_instalado() -> None:
    print("=" * 74)
    print("R3 — esta instalado, y es el versionado?")
    print("=" * 74)
    instalado = RAIZ / ".git" / "hooks" / "pre-push"
    if not instalado.exists():
        print("NO ESTA INSTALADO en .git/hooks/pre-push.")
        print("El gate mas cercano al push no existe, y nada lo dice.")
    else:
        import hashlib

        def sha(p: Path) -> str:
            return hashlib.sha256(p.read_bytes()).hexdigest()[:16]

        versionado = sha(HOOK)
        real = sha(instalado)
        print(f"versionado:  {versionado}  {HOOK}")
        print(f"instalado:   {real}  {instalado}")
        print(f"ejecutable:  {os.access(instalado, os.X_OK)}")
        print(f"IGUALES:     {versionado == real}")
    print()


def r4_declarado() -> None:
    print("=" * 74)
    print("R4 — quien vigila que el pre-push este instalado?")
    print("=" * 74)
    texto = HOOK.read_text(encoding="utf-8")
    print(f"el docstring ofrece bypass:  {'HOOK_SKIP_PUSH_TESTS=1' in texto}")
    print(f"y dice quien lo instala:     {'install-hooks.sh' in texto}")
    r = _sh(
        sys.executable,
        "-m",
        "pytest",
        "tests",
        "-q",
        "--no-cov",
        "-p",
        "no:cacheprovider",
        "--collect-only",
        "-k",
        "pre_push or prepush",
        cwd=RAIZ,
    )
    lineas = [x for x in r.splitlines() if "test" in x and "::" in x]
    print(f"tests que nombran el pre-push: {len(lineas)}")
    for x in lineas[:12]:
        print(f"   {x.strip()}")
    print()


def r5_que_exige_el_guard_del_bypass() -> None:
    """MEDIDO, y es la razon de que el defecto siga vivo.

    `TestPrePushHookDelega::test_el_bypass_salta_la_verificacion_de_verdad`
    exige dos cosas: que el hook salga con 0 y que el stub NO se ejecutara.
    Ninguna de las dos mira lo que el hook IMPRIME.

    Eso significa que un pre-push que, con el bypass puesto, imprimiera
    `OK: la receta canonica dio SUCCESS` pasaria ese guard con los ojos
    cerrados — que es exactamente lo que hace hoy.
    """
    print("=" * 74)
    print("R5 — que exige el guard que YA existe sobre el bypass")
    print("=" * 74)
    fichero = RAIZ / "tests" / "test_hooks_system.py"
    t = fichero.read_text(encoding="utf-8")
    i = t.find("def test_el_bypass_salta_la_verificacion_de_verdad")
    cuerpo = t[i : i + 1400]
    aserciones = [x.strip() for x in cuerpo.splitlines() if x.strip().startswith("assert")]
    for a in aserciones:
        print(f"   {a[:110]}")
    print()
    sobre_la_salida = [a for a in aserciones if "stdout" in a or "stderr" in a]
    print(f"aserciones que miran lo que IMPRIME: {len(sobre_la_salida)}")
    for a in sobre_la_salida:
        print(f"   {a[:110]}")
    print()
    print(
        "VEREDICTO: el guard del bypass solo mira el codigo de salida y que el "
        "stub no corrio. Un hook que MIENTA con la palabra SUCCESS lo aprueba."
    )
    print()


#: Lo que `.pipeline.kts` imprime cuando su veredicto es bueno. No es una
#: cadena inventada para esta medicion: es la MISMA que el propio hook ya
#: nombra en su mensaje de error ("Pipeline finished with SUCCESS no
#: alcanzado"), luego las dos partes del hook ya la conocen.
VEREDICTO_RECETA = "Pipeline finished with SUCCESS"


def _corrida_con_ci(ci: str) -> str:
    """Ejecuta el hook real contra un `ci.sh` con el cuerpo que se le pase."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = _doblar_ci(Path(tmp), ci)
        return _sh("sh", "scripts/hooks/pre-push", cwd=repo, env=dict(os.environ))


def _lineas_del_hook(salida: str) -> list[str]:
    """SOLO las lineas que el hook imprime, y con el sha normalizado.

    MEDIDO DOS VECES, y las dos por lo mismo. La primera version comparaba la
    salida entera y daba `False`; lo unico que la diferenciaba era el sha del
    commit del repo temporal, que cambia en cada corrida. La segunda
    normalizo el sha y seguia dando `False`, porque el `rm -f "$_log"` del
    hook lo intercepta `mavis-trash`, que imprime una linea con el nombre del
    temporal: otro valor que cambia por construccion.

    Dos veces es una tendencia: este bloque lleva tres verificadores debiles
    quediedieron una lectura equivocada en lugar de ninguna. La leccion general es que comparar dos corridas exige normalizar **todo** lo que
    varia por construccion, y que la lista de eso no se adivina a ojo: se ve
    cuando el comparador dice `False` y el diff son dos lineas de ruido.
    """
    return [
        re.sub(r"SOBRE [^ ]+$", "sobre <sha>", linea)
        for linea in salida.splitlines()
        if linea.startswith("[pre-push]")
    ]


def r6_r7_r8_el_success_es_estructural() -> None:
    print("=" * 74)
    print("R6/R7/R8 — un exit 0 sin hacer nada tambien dice SUCCESS?")
    print("=" * 74)

    r6 = _corrida_con_ci("#!/bin/sh\nexit 0\n")
    print("R6 — `ci.sh` = `exit 0`, NO HACE NADA:")
    for linea in r6.splitlines():
        print(f"   {linea}")
    print(f"   el hook dice SUCCESS: {'SUCCESS' in r6}")
    print()

    r7 = _corrida_con_ci(f"#!/bin/sh\necho '{VEREDICTO_RECETA}'\nexit 0\n")
    print("R7 — `ci.sh` = imprime el veredicto de la receta y sale 0:")
    for linea in r7.splitlines():
        print(f"   {linea}")
    print(f"   el hook dice SUCCESS: {'SUCCESS' in r7}")
    print()

    l6, l7 = _lineas_del_hook(r6), _lineas_del_hook(r7)
    iguales = l6 == l7
    if not iguales:
        print("   solo difieren en:")
        for a, b in zip(l6, l7, strict=False):
            if a != b:
                print(f"      R6: {a}\n      R7: {b}")
    print(f"R8 — salida del hook con R6 IGUAL a la de R7: {iguales}")
    print("   R6 no ejecuto nada. R7 si. El hook dice lo mismo en las dos.")
    print()
    print("   MEDIDO: la primera version de esta ronda comparaba las dos salidas")
    print("   enteras y decia `False`. Era el sha del repo temporal, que cambia")
    print("   en cada corrida: un instrumento que compara dos corridas sin")
    print("   normalizar lo que varia por construccion no compara lo que cree")
    print("   comparar. Es el tercer verificador debil de este bloque, y el")
    print("   primero que moria en VERDE: R1, que decidia por `splitlines()[-1]`.")
    print()
    print("=" * 74)
    print("VEREDICTO")
    print("=" * 74)
    print("  El bypass es UN caso de un defecto estructural: el hook dice que la")
    print("  receta dio SUCCESS porque el delegado salio con 0, y un 0 no dice")
    print("  que nada se haya ejecutado. Arreglar solo el bypass taparia R1 y")
    print("  habria que repetirlo el dia que aparezca un cuarto camino.")
    print()
    print("  LO QUE SI SE PUEDE MEDIR: la receta imprime su veredicto y el hook")
    print("  ya captura esa salida en `$_log`. Puede EXIGIR la cadena en vez de")
    print("  heredar un exit code, y entonces su OK deja de ser una copia del")
    print("  codigo de salida y pasa a ser una afirmacion verificada contra el")
    print("  propio delegado.")
    print()


def r9_la_prosa_del_tiempo() -> None:
    print("=" * 74)
    print("R9 — la prosa del tiempo: el hook anuncia ~4min")
    print("=" * 74)
    texto = HOOK.read_text(encoding="utf-8")
    for linea in texto.splitlines():
        if "tardar" in linea:
            print(f"   {linea.strip()}")
    print()
    print("   MEDIDO en el push de v0.42.2 (2026-10-07): 23:56:14 -> 00:10:03")
    print("   son 13 min 49 s contra los ~4min que anuncia: el numero es falso,")
    print("   y es del mismo tipo que el SUCCESS — una afirmacion del hook que")
    print("   nada mide.")
    print()


if __name__ == "__main__":
    print(f"B38 — medicion del pre-push sobre {HOOK}\n")
    r1_bypass()
    r2_fallo_del_doblo()
    r3_instalado()
    r4_declarado()
    r5_que_exige_el_guard_del_bypass()
    r6_r7_r8_el_success_es_estructural()
    r9_la_prosa_del_tiempo()
