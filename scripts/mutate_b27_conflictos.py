"""B27 — contrasalto: deshace una PROPIEDAD cada vez y mira que algo se ponga rojo.

**POR QUE UN HARNESS Y NO CONFiar EN LOS TESTS.** Un test que pasa no dice que
mida. Este script quita deliberadamente una propiedad del codigo —una sola por
sonda— y exige que la suite de B27 se ponga roja. Si alguna sonda deja la suite
verde, o la propiedad no existe o el test que la vigila no la vigila.

**HEREDA LAS TRES REGLAS DE B24/B25/B26, Y POR QUE:**

1. **Restaura desde un snapshot de bytes propio**, no con `git checkout`: en
   B26 ese fallo dejo cinco sondas montadas a la vez mientras el harness
   reportaba «5/5».
2. **Distingue `SIN_SONDA` de `CAZADA`.** Una sonda cuyo texto no esta no
   llego a ejecutarse; reportarlo como fallo es el error 32 de WI-113
   repetido, y una sonda mal anclada es indistinguible de un guard que no
   muerde.
3. **Compila el arbol antes de juzgar.** Una sonda que borra media expresion
   deja un `SyntaxError`, y eso no es una propiedad rota: es una sonda mal
   escrita que se disfraza de CAZADA.

**Y LAS SONDAS MIDEN LAS CINCO PROPIEDADES, EN ORDEN DE CUANTO ROMPEN.**

Uso: `.venv/bin/python scripts/mutate_b27_conflictos.py`
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESTS = "tests/test_b27_conflictos.py"

FICHEROS = (
    "src/skillgraph/platform/knowledge_claims.py",
    "src/skillgraph/platform/knowledge_conflicts.py",
    "src/skillgraph/platform/knowledge_repository.py",
    "src/skillgraph/knowledge/graph.py",
)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una sonda: que cambia, en que fichero, y que propiedad deja de ser cierta."""

    id: str
    fichero: str
    antes: str
    despues: str
    propiedad: str


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        id="M1",
        fichero="src/skillgraph/platform/knowledge_claims.py",
        # Deshace el AVISO, no la escritura: la fila anterior se queda como
        # estaba. Si la sonda borrase la fila en vez de avisar, estariamos
        # midiendo otra propiedad —la de B28— y el harness no diria nada.
        antes="    hubo_conflicto = previo_valor != intento_valor",
        despues="    hubo_conflicto = False  # M1: el overwrite vuelve a ser silencioso",
        propiedad="que el overwrite avise a quien escribe",
    ),
    Sonda(
        id="M2",
        fichero="src/skillgraph/platform/knowledge_conflicts.py",
        antes="    return len({_valor_de(r) for r in grupo}) > 1",
        despues="    return True  # M2: todo grupo es conflicto, aunque no se contradiga",
        propiedad="que un grupo de afirmaciones IGUALES no sea conflicto",
    ),
    Sonda(
        id="M3",
        fichero="src/skillgraph/platform/knowledge_conflicts.py",
        # Quita el filtro de proyecto: el aislamiento por proyecto es la
        # garantia de la que dependen B24 y B25, y aqui se pierde en silencio.
        antes="            WHERE subject_entity_id = ? AND tenant_id = ? AND project_id = ?\n"
        "            ORDER BY predicate ASC, claim_id ASC",
        despues="            WHERE subject_entity_id = ? AND tenant_id = ?\n"
        "            -- M3: sin filtro de proyecto",
        propiedad="que el conflict set no mezcle proyectos distintos",
    ),
    Sonda(
        id="M4",
        fichero="src/skillgraph/platform/knowledge_conflicts.py",
        # Quita la comparacion sobre `_valor_de`, que es lo que hace que dos
        # REFERENCIAS A ENTIDAD distintas se detecten como conflicto. Sin ella,
        # las dos tendrian `''` en el literal y serian iguales: el caso que
        # B25 abrio y que un `SELECT` ingenuo no ve.
        antes="    return len({_valor_de(r) for r in grupo}) > 1",
        despues="    return len({r['object_literal_json'] for r in grupo}) > 1  # M4: solo literales",
        propiedad="que un conflicto entre REFERENCIAS A ENTIDAD se detecte",
    ),
    Sonda(
        id="M5",
        fichero="src/skillgraph/platform/knowledge_repository.py",
        antes="        return self._conflicts.conflicts_for(\n"
        "            tenant_id=tenant_id,\n"
        "            project_id=project_id,\n"
        "            subject_entity_id=subject_entity_id,\n"
        "        )",
        # Se sustituye el `return` ENTERO, no su prefijo: dejarlos
        # desbalanceados es lo que hace que la sonda no compile, y una sonda
        # que no compila no mide nada —la clasifica como ROTA el guard de
        # sintaxis, que existe justo para no contarla como victoria.
        despues="        return ()  # M5: la fachada deja de poder preguntar por los conflictos",
        propiedad="que los conflictos sean CONSULTABLES por la fachada",
    ),
)


def snapshot() -> dict[str, bytes]:
    return {f: (RAIZ / f).read_bytes() for f in FICHEROS}


def restaura(copia: dict[str, bytes]) -> None:
    for f, datos in copia.items():
        (RAIZ / f).write_bytes(datos)


def corre_la_suite() -> tuple[int, str]:
    proc = subprocess.run(
        [".venv/bin/python", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", TESTS],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    return proc.returncode, proc.stdout + proc.stderr


def compila() -> tuple[bool, str]:
    proc = subprocess.run(
        [".venv/bin/python", "-m", "compileall", "-q", "-x", r"__pycache__", "src/skillgraph"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-400:]


def aplica(sonda: Sonda) -> bool:
    """True si la sonda se APLICO. False = SIN_SONDA, que no es lo mismo que verde."""
    ruta = RAIZ / sonda.fichero
    texto = ruta.read_text(encoding="utf-8")
    if sonda.antes not in texto:
        return False
    ruta.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
    return True


def main() -> int:
    if len(SONDAS) < 5:
        print(f"el harness declara {len(SONDAS)} sondas y exige 5: contrasalto")
        return 1

    copia = snapshot()
    try:
        rc, _ = corre_la_suite()
        if rc != 0:
            print("la suite de B27 ya esta en rojo antes de mutar: no se mide nada")
            return 1
        print(f"linea base: {TESTS} en VERDE\n")

        cazadas, sin_sonda, inocuas, rotas = 0, [], [], []
        for sonda in SONDAS:
            if not aplica(sonda):
                sin_sonda.append(sonda.id)
                restaura(copia)
                print(f"  {sonda.id}  SIN_SONDA  el texto no estaba: no llego a ejecutarse")
                continue
            ok_sintaxis, error = compila()
            if not ok_sintaxis:
                rotas.append(sonda.id)
                restaura(copia)
                print(f"  {sonda.id}  ROTA      deja el codigo SIN COMPILAR")
                print(f"            {error.strip()[:140]}")
                continue
            rc, salida = corre_la_suite()
            restaura(copia)
            if rc != 0:
                cazadas += 1
                rojos = [ln for ln in salida.splitlines() if ln.startswith("FAILED")]
                print(f"  {sonda.id}  CAZADA    {sonda.propiedad}")
                for r in rojos[:2]:
                    print(f"            {r.strip()[:140]}")
            else:
                inocuas.append(sonda.id)
                print(f"  {sonda.id}  INOCUA    {sonda.propiedad}  <-- el guard no muerde")

        print(f"\nRESUMEN: {cazadas}/{len(SONDAS)} cazadas")
        if sin_sonda:
            print(f"SIN_SONDA: {sin_sonda}")
        if rotas:
            print(f"ROTAS (el guard no se midio): {rotas}")
        if inocuas:
            print(f"INOCUAS: {inocuas}")
        ok = not sin_sonda and not inocuas and not rotas
    finally:
        restaura(copia)

    rc, salida = corre_la_suite()
    print(f"\ntras restaurar: rc={rc}", "VERDE" if rc == 0 else salida[-400:])
    return 0 if (ok and rc == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
