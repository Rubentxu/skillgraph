"""Sondas de mutacion de B6: el gate tiene que MUERDIR, no solo relajar.

Por que sondas y no solo tests
-----------------------------
19 tests en verde prueban que las propiedades se sostienen HOY sobre este
codigo. No prueban que SE ROMPAN si alguien las toca. La diferencia es la
que importa: un guard que solo puede decir «todo bien» no vigila nada, y
este repo lo ha pagado antes (la M2 del harness de B0, la sonda que
apuntaba a texto inexistente y se contaba como victoria).

Cada sonda MUEVE el codigo para quitar una garantia, corre los tests, y
exige que ALGO se ponga rojo. Si una sonda no rompe nada, hay dos
posibilidades y las dos son defectos: o la garantia no existe, o el test
que deberia cubrirla no la cubre. Se reporta como NO CAZADA en vez de
darse por buena.

Lo que se midio AL ESCRIBIR ESTE HARNESS, y es su propio hallazgo:

    M4 no fue cazada en la primera version. La sonda sustituye
    `if self.assertion_origin not in ASSERTION_ORIGINS:` por `if False:`,
    y el medidor `scripts/measure_b6_provenance.py` seguia dando P6
    CERRADO, porque buscaba la MENCION de los dos nombres con
    `ast.dump` y la MENCION seguia ahi: el `raise` de abajo, con su
    mensaje, nombra `ASSERTION_ORIGINS`. Un predicado que busca la prosa
    del error encuentra la prosa del error. Se corrigio para exigir una
    comparacion `not in` real, y entonces la cazó. El guard que se escribe
    para vigilar al guard es donde se esconden estos fallos.

COMO SE USA
-----------
    python scripts/mutate_b6_provenance.py

Arbol restaurado byte a byte al terminar, comprobado por sha.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

RAIZ: Final[Path] = Path(__file__).resolve().parent.parent
TESTS: Final[tuple[str, ...]] = ("tests/test_b6_provenance.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una mutacion y la propiedad que se espera que rompa."""

    clave: str
    titulo: str
    ruta: str
    antiguo: str
    nuevo: str
    porque: str
    #: Si son varios sitios, se comprueban TODOS. Una sonda de dos sitios
    #: aplicada a medias se contaria como victoria si no se verificara,
    #: y ese fue un error real del harness de B5.
    esperado_ocurrencias: int = 1


SONDAS: Final[tuple[Sonda, ...]] = (
    Sonda(
        clave="M1",
        titulo="el origen deja de validarse al construir el Claim",
        ruta="src/skillgraph/knowledge/graph.py",
        antiguo="if self.assertion_origin not in ASSERTION_ORIGINS:",
        nuevo="if False:",
        porque=(
            "Sin esta comprobacion, con `from __future__ import annotations` "
            "la anotacion es una cadena que el runtime no mira, y un origen "
            "inventado llega intacto al INSERT. Lo rechaza SQLite con un "
            "error que no es del dominio — el hueco que WI-114 cerro por el "
            "otro lado de la misma frontera."
        ),
    ),
    Sonda(
        clave="M2",
        titulo="la base deja de imponer el vocabulario",
        ruta="src/skillgraph/platform/schema.py",
        antiguo="""    assertion_origin      TEXT NOT NULL DEFAULT 'observed'
        CHECK (assertion_origin IN (
            'observed',
            'derived-deterministically',
            'agent-inferred',
            'human-asserted'
        )),
""",
        nuevo="    assertion_origin      TEXT NOT NULL DEFAULT 'observed',\n",
        porque=(
            "Sin CHECK, el vocabulario vive solo en Python y un INSERT "
            "directo —sin pasar por Claim— cuela cualquier texto. El gate "
            "deja de poder exigirse donde se escribe de verdad."
        ),
    ),
    Sonda(
        clave="M3",
        titulo="el origen se pierde al leer de la base",
        ruta="src/skillgraph/platform/knowledge_claims.py",
        antiguo='                    assertion_origin=row["assertion_origin"],\n',
        nuevo="",
        porque=(
            "La fila trae el origen y la rehidratacion lo tira: el Claim "
            "vuelve a su default. Es la perdida de provenance mas facil de "
            "no ver, porque el valor sigue en disco y solo se pierde al "
            "leer."
        ),
        esperado_ocurrencias=2,
    ),
    Sonda(
        clave="M4",
        titulo="el medidor busca la mencion en vez de la comparacion",
        ruta="scripts/measure_b6_provenance.py",
        antiguo="""                if not isinstance(izq, ast.Attribute):
                    continue
                if izq.attr != "assertion_origin":
                    continue
                if isinstance(der, ast.Name) and der.id == "ASSERTION_ORIGINS":
                    return True""",
        nuevo="""                cuerpo = ast.dump(item)
                return "assertion_origin" in cuerpo and "ASSERTION_ORIGINS" in cuerpo""",
        porque=(
            "ESTA sonda es sobre el guard. La version que Busca la "
            "mencion pasa en verde con la validacion gutiada, porque el "
            "mensaje del `raise` sigue nombrando el conjunto. Un guard que "
            "mide la prosa del error en vez de la comparacion no mide la "
            "validacion."
        ),
    ),
    Sonda(
        clave="M5",
        titulo="los dos ejes se vuelven el mismo campo",
        ruta="src/skillgraph/knowledge/graph.py",
        antiguo='    assertion_origin: AssertionOrigin = "observed"\n',
        nuevo="",
        porque=(
            "Si el origen desaparece como campo, vuelve a esconderse en el "
            "metodo, que es el estado en el que estaba antes del bloque: un "
            "campo, dos preguntas, y ninguna respondible."
        ),
    ),
    Sonda(
        clave="M6",
        titulo="la promocion revierte el origen a observed",
        ruta="src/skillgraph/cli/commands/promotion.py",
        antiguo='            assertion_origin=c.get("assertion_origin", "observed"),\n',
        nuevo="",
        porque=(
            "Sin propagar el origen, un Claim promovido entre proyectos "
            "vuelve al default en silencio. Una afirmacion de una persona "
            "llega al proyecto destino como `observed`, que es "
            "exactamente la perdida de provenance que el gate prohibe."
        ),
    ),
    Sonda(
        clave="M7",
        titulo="la migracion de una base previa desaparece",
        ruta="src/skillgraph/platform/storage.py",
        antiguo="            self._anade_column_claims_assertion_origin(cur)\n",
        nuevo="",
        porque=(
            "Una base NUEVA funciona y una VIEJA no, y el fallo sale en "
            "produccion y no en los tests, porque los tests construyen la "
            "base desde cero cada vez. `CREATE TABLE IF NOT EXISTS` no "
            "anade columnas a una tabla que ya existe."
        ),
    ),
    Sonda(
        clave="M8",
        titulo="el conjunto derivado se escribe a mano y se queda corto",
        ruta="src/skillgraph/core/runtime_types.py",
        antiguo="ASSERTION_ORIGINS: Final[frozenset[str]] = frozenset(get_args(AssertionOrigin))",
        nuevo='ASSERTION_ORIGINS: Final[frozenset[str]] = frozenset({"observed"})',
        porque=(
            "El error de QW-E: un conjunto a mano se queda corto cuando "
            "alguien anade un valor al Literal, y entonces la validacion "
            "rechaza el valor nuevo que el tipo si acepta. Sin derivarlo, "
            "el conjunto y el tipo son dos fuentes de verdad."
        ),
    ),
)


def _aplicar(sonda: Sonda) -> tuple[bool, str]:
    """Aplica la sonda. Devuelve (aplicada, motivo del fallo).

    Una sonda que NO se aplica no es una victoria: se reporta aparte. Es
    la distincion que evita el error 32 de WI-113, donde una sonda que
    apuntaba a texto inexistente se contaba como haber cazado.
    """
    objetivo = RAIZ / sonda.ruta
    if not objetivo.exists():
        return False, f"el fichero {sonda.ruta} no existe"
    texto = objetivo.read_text(encoding="utf-8")
    ocurrencias = texto.count(sonda.antiguo)
    if ocurrencias != sonda.esperado_ocurrencias:
        return False, (
            f"se esperaban {sonda.esperado_ocurrencias} ocurrencias y hay "
            f"{ocurrencias}: la sonda apunta a texto que el repo ya no "
            f"escribe asi"
        )
    objetivo.write_text(texto.replace(sonda.antiguo, sonda.nuevo), encoding="utf-8")
    return True, ""


def _tests_en_rojo() -> tuple[bool, str]:
    # SIN `-x`. La primera version lo llevaba, y eso hacia que el harness
    # CONTARA como cazadas sondas que no cazaban: `-x` para en el primer
    # fallo, y como las sondas se ejecutan en orden, M3, M6, M7 y M8
    # heredaban el fallo de la sonda anterior y se contaban como
    # cazadas. Medido: quitando `-x`, esas cuatro dan rc=0 con su mutacion
    # puesta —es decir, ningun test las cubre—. Es el error del harness de
    # B5 (la sonda de dos sitios aplicada a medias) y el M2 de B0 (una
    # medicion que devuelve siempre algo): el contador daba 8/8 y cuatro
    # no eran cazadas. Un total que no se puede desarmar no es un total.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TESTS],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode != 0, proc.stdout[-2000:]


def _tests_que_caen() -> tuple[str, ...]:
    """Los NOMBRES de los tests que fallan, para distinguir las sondas.

    Sin esto, ocho sondas que se rompen todas por el mismo aserto
    cuentan como ocho propiedades medidas cuando son una. Se mide el
    fallo, no solo el codigo de salida.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TESTS],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    return tuple(
        linea.split("::")[-1]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED")
    )


def main() -> int:
    # Se guarda el CONTENIDO, no solo su sha. La primera version guardaba
    # el sha y «restauraba» reescribiendo el fichero con sus propios
    # bytes, que es no hacer nada: el arbol se queda mutado y el harness
    # imprime «arbol restaurado: True» porque compara el fichero con
    # el mismo fichero. Un sha se usa para COMPROBAR que se restauro,
    # nunca para restaurar.
    guardados: dict[str, bytes] = {}
    for s in SONDAS:
        ruta = RAIZ / s.ruta
        if ruta.exists():
            guardados[s.ruta] = ruta.read_bytes()

    cazadas = 0
    no_cazadas: list[str] = []
    sin_sonda: list[tuple[str, str]] = []
    rotas: list[tuple[str, str]] = []

    try:
        for sonda in SONDAS:
            aplicada, motivo = _aplicar(sonda)
            if not aplicada:
                sin_sonda.append((sonda.clave, motivo))
                print(f"[SIN_SONDA] {sonda.clave} {sonda.titulo}")
                print(f"            {motivo}")
                print()
                continue
            try:
                roja, salida = _tests_en_rojo()
            except Exception as exc:
                rotas.append((sonda.clave, str(exc)))
                print(f"[ROTA     ] {sonda.clave} {sonda.titulo}")
                print(f"            el harness fallo: {exc}")
                print()
                continue
            if roja:
                cazadas += 1
                print(f"[CAZADA   ] {sonda.clave} {sonda.titulo}")
                print(f"            {sonda.porque}")
                primera = [
                    linea
                    for linea in salida.splitlines()
                    if linea.startswith("FAILED") or linea.startswith("E ")
                ]
                if primera:
                    print(f"            {primera[0][:110]}")
                print()
            else:
                no_cazadas.append(sonda.clave)
                print(f"[NO CAZADA] {sonda.clave} {sonda.titulo}")
                print(f"            {sonda.porque}")
                print(
                    "            Y NO LA CAZO NADIE: o la garantia no existe, o "
                    "el test que deberia cubrirla no la cubre. Las dos son "
                    "defectos, y se reportan en vez de contarse como "
                    "victoria."
                )
                print()
    finally:
        for ruta_rel, contenido in guardados.items():
            (RAIZ / ruta_rel).write_bytes(contenido)
        restaurado = all(
            hashlib.sha256((RAIZ / ruta_rel).read_bytes()).hexdigest()
            == hashlib.sha256(contenido).hexdigest()
            for ruta_rel, contenido in guardados.items()
        )

    print("-" * 78)
    print(
        f"cazadas {cazadas}/{len(SONDAS)}   NO cazadas {len(no_cazadas)}   "
        f"sin sonda {len(sin_sonda)}   rotas {len(rotas)}"
    )
    print(f"arbol restaurado byte a byte: {restaurado}")
    if not restaurado:
        print("ERROR: el arbol NO quedo como estaba.")
        return 1
    if cazadas == len(SONDAS):
        print("OK: el gate muerde en todas las propiedades medidas.")
        return 0
    print("ERROR: hay propiedades que nadie vigila.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
