"""B26 — contrasalto: deshace una PROPIEDAD cada vez y mira que algo se ponga rojo.

**POR QUE UN HARNESS Y NO CONFiar EN LOS TESTS.** Un test que pasa no dice que
mida. Este script quita deliberadamente una propiedad del codigo —una sola por
sonda— y exige que la suite de B26 se ponga roja. Si alguna sonda deja la suite
verde, o la propiedad no existe o el test que la vigila no la vigila.

**LAS CINCO SONDAS, Y POR QUE M1 Y M4 SON LA MISMA PROPIEDAD POR DOS LADOS.**
M1 quita `observed_at` de la semilla del `claim_id`; M4 mete el reloj dentro del
normalizador. Los dos rompen **lo mismo**: que la misma observacion produzca el
mismo id dos veces. Por eso el harness exige que las dos caigan — si el reloj
vuelve a colarse dentro del normalizador, la idempotencia se rompe aunque la
prueba de pureza siga verde, porque el sintoma aparece en el `claim_id`, no en
la funcion.

**Y POR QUE M5 TOCA EL INSTRUMENTO, NO SOLO EL CODIGO.** La primera version de
`measure_b26_ingesta.py` media «¿esta la clave `object_entity` en el payload?».
Eso no es la propiedad: es un nombre. Con el arreglo puesto, el payload lleva
`object_entity_id`, y la pregunta se quedaba ABIERTA con el bug ya cerrado;
con el bug puesto, si hubiera escrito el nombre viejo, habria dado CERRADA. Un
guard que mide un nombre no puede distinguir «la referencia viaja» de «hay una
clave parecida». M5 deshace esa correccion para que se vea que la version que
mide la propiedad ejecuta el camino entero y se pone roja con el bug real.

**LAS TRES REGLAS QUE PESA, HEREDADAS DEL HARNESS DE B24/B25.**

1. **Restaura desde un snapshot de bytes propio, no con `git checkout`.** Este es
   un fichero NUEVO y sin trackear: `git checkout --` lo restauraria del indice
   —donde no esta— y serian sondas que se quedan montadas.
2. **Distingue `SIN_SONDA` de `CAZADA`.** Si el texto que la sonda busca ya no
   esta en el fichero, no llego a ejecutarse. Reportarlo como fallo seria el
   error 32 de WI-113 repetido.
3. **No declara exito hasta haber comprobado que el arbol quedo verde.** Un
   harness que dice «5/5» y deja el arbol con sondas puestas es peor que uno que
   no mide nada.

Uso: `.venv/bin/python scripts/mutate_b26_ingesta.py`
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESTS = "tests/test_b26_ingesta.py"

#: Ficheros que las sondas tocan. El snapshot se toma de ESTA lista: si una
#: sonda tocara un fichero que no esta aqui, su restauracion no tendria de
#: donde volver — y en B26 el fichero principal todavia no esta trackeado.
FICHEROS = (
    "src/skillgraph/knowledge/observation.py",
    "src/skillgraph/cli/commands/promotion.py",
    "scripts/measure_b26_ingesta.py",
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
        fichero="src/skillgraph/knowledge/observation.py",
        # Ancla en la CONSTRUCCION del id, no en la del Claim: hay dos
        # apariciones de `checked_at_revision=env.revision` y la que forma la
        # semilla del UUIDv5 es la primera. Anclar en la segunda haria que la
        # sonda se aplicase donde no toca el id, y la idempotencia seguiria
        # intacta sin que nadie lo notara. Esa es la razon de que el harness
        # distinga SIN_SONDA de CAZADA: una sonda mal anclada es
        # indistinguible de un guard que no muerde.
        antes=(
            "        claim_id=make_claim_id(\n"
            "            subject_entity_id=entity_id(env.subject),\n"
            "            predicate=obs.predicate,\n"
            "            source_id=env.source_id,\n"
            "            checked_at_revision=env.revision,\n"
        ),
        despues=(
            "        claim_id=make_claim_id(\n"
            "            subject_entity_id=entity_id(env.subject),\n"
            "            predicate=obs.predicate,\n"
            "            source_id=env.source_id,\n"
            '            checked_at_revision="constante",  # M1: la revision sale de la semilla\n'
        ),
        propiedad="el claim_id sale del contenido, y el contenido incluye la revision",
    ),
    Sonda(
        id="M2",
        fichero="src/skillgraph/knowledge/observation.py",
        antes="    if env.version != VERSION_ENVELOPE:",
        despues="    if False:  # M2: la puerta de la version es decorativa",
        propiedad="que un envelope de otra version falle en la frontera",
    ),
    Sonda(
        id="M3",
        fichero="src/skillgraph/knowledge/observation.py",
        # **NO** se «deshace» anadiendo una linea muerta delante: el
        # `record_claim` seguia ejecutandose y la propiedad —«ingerir
        # escribe»— se sostenia entera. Una sonda que anade ruido sin quitar
        # el comportamiento no deshace nada, y su INOCUA midio la sonda, no el
        # guard. Aqui se QUITA la escritura.
        # Se sustituye la LLAMADA COMPLETA, no su prefijo: una sonda que solo borra
        # el prefijo deja una linea que no compila, y un `SyntaxError` no es una
        # propiedad rota — es un harness roto que se disfraza de CAZADA.
        antes=(
            "    for claim in ingesta.claims:\n"
            "        storage.record_claim(tenant_id=tenant_id, project_id=project_id, claim=claim)"
        ),
        despues=("    for claim in ingesta.claims:\n        pass  # M3: normaliza pero no escribe"),
        propiedad="que ingerir escriba las filas que dice escribir",
    ),
    Sonda(
        id="M4",
        fichero="src/skillgraph/knowledge/observation.py",
        antes="        checked_at=env.observed_at,",
        despues="        checked_at=_reloj(),  # M4: el reloj se cuela en el normalizador",
        propiedad="que el normalizador sea puro (reloj incluido)",
    ),
    Sonda(
        id="M5",
        fichero="scripts/measure_b26_ingesta.py",
        antes='            llegas = destino.get_claim(tenant_id="t", project_id="destino", claim_id="c-b26-p5")',
        despues="            llegas = None  # M5: el guard mira un nombre, no la propiedad",
        propiedad="que la medida de P5 EJECUTE el camino y no mire una clave",
    ),
)

#: Sondas cuyo fallo se juzga por la SALIDA DEL INSTRUMENTO y no por el rc de
#: pytest: el instrumento sale siempre en 0 —es una medicion, no un gate— asi
#: que «se puso rojo» se lee en su texto.
JUZGA_INSTRUMENTO = {"M5"}

#: La sonda que hace que el reloj exista en el modulo para que M4 pueda meterlo.
#: Sin esto, M4 seria `SIN_SONDA` en vez de cazada: importaria un nombre que no
#: esta. Se anade SOLO durante la sonda y se retira al restaurar.
AYUDA_M4 = "from skillgraph.runtime.engine import now_iso as _reloj\n"


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


def corre_el_instrumento() -> tuple[int, str]:
    proc = subprocess.run(
        [".venv/bin/python", "scripts/measure_b26_ingesta.py"],
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


def prepara_m4() -> None:
    """Mete el reloj en el modulo para que M4 tenga algo que meter."""
    ruta = RAIZ / "src/skillgraph/knowledge/observation.py"
    texto = ruta.read_text(encoding="utf-8")
    ruta.write_text(
        texto.replace("from dataclasses import dataclass\n", AYUDA_M4, 1), encoding="utf-8"
    )


def compila() -> tuple[bool, str]:
    """¿Compila el arbol tras la sonda?

    **POR QUE ESTA COMPROBACION Y POR QUE ESTA EN EL HARNESS.** Una sonda que
    borra media expresion deja el fichero sin compilar, y pytest se pone rojo
    con un `SyntaxError`. Eso NO es una propiedad rota: es una sonda mal
    escrita. Si no se distingue, el harness reporta CAZADA por haber roto el
    codigo, que es la forma mas comoda de que un harness diga «5/5» sin haber
    medido nada — y es exactamente el fallo que la instrumentacion se supone que
    existe para cazar.
    """
    proc = subprocess.run(
        [".venv/bin/python", "-m", "compileall", "-q", "-x", r"__pycache__", "src/skillgraph"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-400:]


def main() -> int:
    if len(SONDAS) < 5:
        print(f"el harness declara {len(SONDAS)} sondas y exige 5: contrasalto")
        return 1

    copia = snapshot()
    try:
        rc, _ = corre_la_suite()
        if rc != 0:
            print("la suite de B26 ya esta en rojo antes de mutar: no se mide nada")
            return 1
        _, linea_base = corre_el_instrumento()
        if "RESULTADO: 0/5" not in linea_base:
            print("el instrumento de B26 no dice 0/5 antes de mutar: no se mide nada")
            print(linea_base[-400:])
            return 1
        print(f"linea base: {TESTS} en VERDE y el instrumento en 0/5\n")

        cazadas, sin_sonda, inocuas, rotas = 0, [], [], []
        for sonda in SONDAS:
            if sonda.id == "M4":
                prepara_m4()
            if not aplica(sonda):
                sin_sonda.append(sonda.id)
                restaura(copia)
                continue
            ok_sintaxis, error = compila()
            if not ok_sintaxis:
                rotas.append(sonda.id)
                restaura(copia)
                print(f"  {sonda.id}  ROTA      {sonda.propiedad}")
                print(f"            la sonda deja el codigo SIN COMPILAR: {error.strip()[:150]}")
                continue
            if sonda.id in JUZGA_INSTRUMENTO:
                _, salida = corre_el_instrumento()
                mordio = "RESULTADO: 0/5" not in salida
                detalle = [ln for ln in salida.splitlines() if "P5" in ln and "CERRADA" in ln]
            else:
                rc, salida = corre_la_suite()
                mordio = rc != 0
                detalle = [ln for ln in salida.splitlines() if ln.startswith("FAILED")]
                if not detalle:
                    # Un verificador que dice «falso» sin decir dónde es un
                    # callejón: hay que poder llegar al test sin reejecutar a
                    # mano. M4 cae por el instrumento, no por pytest, y su
                    # unica salida visible es la linea de P3.
                    _, mid = corre_el_instrumento()
                    detalle = [ln.strip() for ln in mid.splitlines() if ln.strip().startswith("P3")]
            restaura(copia)
            if mordio:
                cazadas += 1
                print(f"  {sonda.id}  CAZADA    {sonda.propiedad}")
                for d in detalle[:3]:
                    print(f"            {d.strip()[:150]}")
            else:
                inocuas.append(sonda.id)
                print(f"  {sonda.id}  INOCUA    {sonda.propiedad}  <-- el guard no muerde")

        print(f"\nRESUMEN: {cazadas}/{len(SONDAS)} cazadas")
        if sin_sonda:
            print(f"SIN_SONDA (el texto no estaba; NO es que la sonda fallara): {sin_sonda}")
        if rotas:
            print(f"ROTAS (la sonda no deja el codigo compilable; el guard no se midio): {rotas}")
        if inocuas:
            print(f"INOCUAS (se aplicaron y nadie se puso rojo): {inocuas}")
        # Una sonda rota NO cuenta como cazada, y hace fallar el harness igual
        # que una inocua: un «3/5» con dos rotas y tres cazadas no es un
        # contrasaltoemption, es un inventario de lo que el harness todavia no
        # sabe medir.
        ok = not sin_sonda and not inocuas and not rotas
    finally:
        restaura(copia)

    rc, salida = corre_la_suite()
    _, linea_base = corre_el_instrumento()
    instrumento_ok = "RESULTADO: 0/5" in linea_base
    print(
        f"\ntras restaurar: rc={rc}",
        "VERDE" if rc == 0 else salida[-400:],
        f"| instrumento {'0/5' if instrumento_ok else 'NO ESTA EN 0/5'}",
    )
    return 0 if (ok and rc == 0 and instrumento_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
