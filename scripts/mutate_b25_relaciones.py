"""B25 — contrasalto: deshace una PROPIEDAD cada vez y mira que algo se ponga rojo.

**POR QUE UN HARNESS Y NO CONFiar EN LOS TESTS.** Un test que pasa no dice que
mida. Este script quita deliberadamente una propiedad del codigo —una sola por
sonda— y exige que la suite de B25 se ponga roja. Si alguna sonda deja la suite
verde, o la propiedad no existe o el test que la vigila no la vigila.

**LA REGLA DE LAS TRES COSAS QUE ESTE SCRIPT NO HACE A PESAR.**

1. **Restaura desde un snapshot de bytes propio, no con `git checkout`.** Lo
   aprendio el harness de B24: `git checkout --` restaura del INDICE, luego con
   ficheros sin seguimiento es un no-op silencioso — y el harness decia «5/5
   cazadas» mientras dejaba las cinco sondas montadas a la vez en el arbol.
2. **Distingue `SIN_SONDA` de `CAZADA`.** Si el texto que la sonda busca ya no
   esta en el fichero, la sonda no fallo: no llego a ejecutarse. Reportar eso
   como fallo seria el error 32 de WI-113 repetido, y el harness lo distingue.
3. **Una sonda deshace UNA PROPIEDAD, no una linea.** Por eso M5 toca dos
   ficheros: la propiedad del round-trip no esta en uno solo.

Uso: `.venv/bin/python scripts/mutate_b25_relaciones.py`
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESTS = "tests/test_b25_relaciones.py"

#: Ficheros que las sondas tocan. El snapshot se toma de ESTA lista, no de
#: `git status`: si una sonda tocara un fichero que no esta aqui, su restauracion
#: no tendria de donde volver.
FICHEROS = (
    "src/skillgraph/knowledge/graph.py",
    "src/skillgraph/core/runtime_types.py",
    "src/skillgraph/platform/schema.py",
    "src/skillgraph/platform/migrations.py",
    "src/skillgraph/platform/knowledge_mappers.py",
    "src/skillgraph/platform/knowledge_claims.py",
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
        fichero="src/skillgraph/knowledge/graph.py",
        antes="        es_literal = self.object_literal is not None",
        despues="        es_literal = True  # M1: el XOR ya no pregunta por el literal",
        propiedad="la invariante «exactamente uno» en Python",
    ),
    Sonda(
        id="M2",
        fichero="src/skillgraph/platform/schema.py",
        antes="        CHECK ((object_literal_json = '') <> (object_entity_id = '')),",
        despues="        -- M2: CHECK de la base anulado",
        propiedad="el CHECK que hace la base cumplir «exactamente uno»",
    ),
    Sonda(
        id="M3",
        fichero="src/skillgraph/core/runtime_types.py",
        antes="    if not _FORMA_PREDICADO_DE_PACK.match(raw):",
        despues="    if False:  # M3: cualquier predicado pasa, con o sin namespace",
        propiedad="el criterio de namespace del pack",
    ),
    Sonda(
        id="M4",
        fichero="src/skillgraph/platform/migrations.py",
        antes='    Migracion("0003_claims_object_entity_id", _anade_object_entity_id),',
        despues="    # M4: la migracion desaparece del libro",
        propiedad="que la base migrada acabe como la base nueva",
    ),
    Sonda(
        id="M5",
        fichero="src/skillgraph/platform/knowledge_mappers.py",
        antes='    if "object_entity_id" not in row.keys():  # noqa: SIM118',
        despues='    if "object_entity_id" not in row:  # M5: el bug de ruff de verdad',
        propiedad="que el round-trip devuelva EntityRef y no se degrade a str",
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
            print("la suite de B25 ya está en rojo antes de mutar: no se mide nada")
            return 1
        print(f"linea base: {TESTS} en VERDE\n")

        cazadas, sin_sonda, inocuas = 0, [], []
        for sonda in SONDAS:
            if not aplica(sonda):
                sin_sonda.append(sonda.id)
                restaura(copia)
                continue
            rc, salida = corre_la_suite()
            restaura(copia)
            if rc != 0:
                cazadas += 1
                rojos = [ln for ln in salida.splitlines() if ln.startswith("FAILED")]
                print(f"  {sonda.id}  CAZADA    {sonda.propiedad}")
                for r in rojos[:3]:
                    print(f"            {r}")
            else:
                inocuas.append(sonda.id)
                print(f"  {sonda.id}  INOCUA    {sonda.propiedad}  <-- el guard no muerde")

        print(f"\nRESUMEN: {cazadas}/{len(SONDAS)} cazadas")
        if sin_sonda:
            print(f"SIN_SONDA (el texto no estaba; NO es que la sonda fallara): {sin_sonda}")
        if inocuas:
            print(f"INOCUAS (se aplicaron y nadie se puso rojo): {inocuas}")
        # NO se devuelve aqui, y es deliberado.
        #
        # Devolver dentro del `try` ejecuta el `finally` —que restaura— pero
        # SALTA la comprobacion de abajo, que es la unica que dice que el
        # arbol quedo como estaba. Un harness que dice «5/5» sin comprobar que
        # se puede volver a trabajar encima es el fallo de B24: sondas que se
        # tras restaurar. Aqui no se declara el exito hasta haberlo visto.
        ok = not sin_sonda and not inocuas
    finally:
        # El `finally` solo RESTAURA. Devolver desde dentro de un `finally`
        # silenciaria cualquier excepcion que este en vuelo (B012, y con
        # razon): si una sonda reventara el harness, `return 0` dentro del
        # `finally` lo convertiria en un exito. La comprobacion de que el
        # arbol quedo verde va DESPUES, y por eso puede devolver sin pisar a
        # nadie.
        restaura(copia)

    rc, salida = corre_la_suite()
    print(f"\ntras restaurar: rc={rc}", "VERDE" if rc == 0 else salida[-400:])
    # El codigo de salida exige LAS DOS cosas: que las sondas mordieron y que
    # el arbol quedo limpio. Devolver solo por `ok` seria volver al fallo de
    # B24 con otro disfraz.
    return 0 if (ok and rc == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
