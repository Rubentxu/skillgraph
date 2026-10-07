#!/usr/bin/env python3
"""B38 — que mide el pre-push, y que se le escapa.

Se ejecuta sobre el hook REAL, igual que `measure_b37_smoke_subset.py` hizo
con el pre-commit: no se lee el fuente, se ejecuta y se mira lo que imprime.

Rondas:

    R1  el camino del bypass, con `HOOK_SKIP_PUSH_TESTS=1`
    R2  el camino normal, con `scripts/ci.sh` sustituido por un dobble que dice
        SUCCESS — para ver si el hook distingue una receta que corrio de una
        que no
    R3  si el hook esta instalado en `.git/hooks/`, y si es el versionado
    R4  los hooks que existen de verdad, y los que el docstring declara

Nada de esto modifica el repo: el dobble de `scripts/ci.sh` se inyecta por
PATH y el `git push` no llega a salir nunca — el hook corre con
`--dry-run` apuntando a un remoto de `/dev/null`.
"""

from __future__ import annotations

import os
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


if __name__ == "__main__":
    print(f"B38 — medicion del pre-push sobre {HOOK}\n")
    r1_bypass()
    r2_fallo_del_doblo()
    r3_instalado()
    r4_declarado()
    r5_que_exige_el_guard_del_bypass()
