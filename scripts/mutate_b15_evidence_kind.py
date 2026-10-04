#!/usr/bin/env python3
"""B15 · el harness de mutacion de la clase de evidencia del gate.

Por que existe
--------------
La clase de evidencia se **deriva** del AST del propio gate. Esa derivacion
puede estar rota de dos maneras, y ninguna se ve leyendo el codigo:

1. Declarar una clase que no corresponde. MEDIDO: la primera version de
   `clase_de_evidencia` devolvia **veinte de veinte `derivada`**, porque la
   busqueda del slug fallaba y el fallo devolvia un valor POR DEFECTO. Seis de
   esos predicados si lanzan subproceso. El numero salia con la autoridad de un
   `print` y no habia nada que lo contradijera.
2. Declarar la clase bien HOY y mañana dejar de seguir al codigo. Un guard que
   midiese «la lista es correcta» pasaria en verde el dia que un predicado
   anadiera un subproceso.

Lo que este harness hace es **poner la derivacion en rojo** y exigir que caigan
los tests que dicen vigilarla. Un guard que no se puede tumbar no es un guard.

Autocomprobacion, y por que el harness la exige a si mismo
----------------------------------------------------------
Tres sondas de B13 y una de B14 nacieron rotas y las cazo el propio harness
antes de contarlas: dos con los diagnosticos escritos con el nombre de la clase
mal, y dos con un ancla que aparece DOS veces —deshacer el texto equivocado sin
que se note—. Un harness que cuenta como verde una sonda que no midio es peor
que no tener harness, porque publica un numero.

Por eso aqui, ANTES de mutar nada, este script se niega a arrancar si:

- un **diagnostico** declarado no existe entre los ids colectados de verdad;
- un **ancla** no aparece exactamente una vez en su fichero;
- una **deformacion** es identica al texto que deberia cambiar.

Ese ultimo es el que mas veces ha catching: una sonda que no cambia el texto no
puede hacer caer a nadie, y se contaria como verde.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

MUTABLES = (RAIZ / "scripts" / "measure_b9_gate_1_0.py",)
SUITES = ("tests/test_b15_evidence_kind.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo, y quien TIENE que caer."""

    nombre: str
    fichero: str
    antes: str
    despues: str
    esperados: frozenset[str]


def _sin_trabajo_sin_commitar() -> tuple[str, ...]:
    """Los mutables con cambios SIN commitear, que se perderian al restaurar.

    «Restaurar» y «borrar» son la misma operacion sin commit debajo: si el
    fichero esta sucio y el harness hace `git checkout --`, el trabajo se va y
    el harness sigue diciendo que el arbol esta limpio.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(linea for linea in proc.stdout.splitlines() if linea.strip())


def _limpia_cache() -> None:
    for cache in RAIZ.rglob("__pycache__"):
        if ".venv" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)


def _pytest(objetivos: tuple[str, ...]) -> tuple[int, set[str]]:
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *objetivos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    caidos = {
        linea.split("::", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED ")
    }
    return proc.returncode, caidos


def _colectados(objetivos: tuple[str, ...]) -> set[str]:
    """Los ids de test que EXISTEN de verdad en la suite del harness."""
    proc = subprocess.run(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "--collect-only",
            "-p",
            "no:cacheprovider",
            *objetivos,
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    return {
        linea.strip() for linea in proc.stdout.splitlines() if linea.startswith(f"{objetivos[0]}::")
    }


def _interprete_valido() -> str | None:
    """Por que no, si `PY` no puede importar el paquete. `None` si puede.

    MEDIDO: lanzado con el Python del sistema, el harness de B14 se negaba con
    «la colecta no devolvio ningun test» —el sintoma de una causa que no era la
    que el harness mide, y sin decir donde estaba—. Falla cerrada, que es lo
    importante; pero obliga a un viaje por el shell para descubrirlo, y ese viaje
    es donde un guard se queda sin correr y otro, sin querer, lo declara verde.
    """
    proc = subprocess.run(
        [PY, "-c", "import skillgraph"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode == 0:
        return None
    return (
        f"{PY} no puede importar `skillgraph`, y este harness corre sus sondas con el\n"
        f"interprete con el que se lanzo. Lanzalo con el del proyecto: `uv run python "
        f"{Path(__file__).relative_to(RAIZ)}`."
    )


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_todas_las_clases_declaran_ejecutada",
        fichero="scripts/measure_b9_gate_1_0.py",
        # El fallo de la primera version, en su forma extrema: la clase deja de
        # mirar el grafo. Siete propiedades son `derivada` de verdad, y aqui
        # pasarian a decir `ejecutada`, que es la clase que NO se puede retirar
        # sola. Lo caza el contrasalto que quita `subprocess` de todo el modulo.
        antes='    return "ejecutada" if _alcanza_proceso(funcion, grafo, frozenset()) else "derivada"',
        despues='    return "ejecutada"',
        esperados=frozenset(
            {"TestLaClaseSigueAlCodigo::test_cortar_el_subproceso_gira_todas_las_clases_a_derivada"}
        ),
    ),
    Sonda(
        nombre="M2_todas_las_clases_declaran_derivada",
        fichero="scripts/measure_b9_gate_1_0.py",
        # La direccion contraria. Con esto, anadir un subproceso a un predicado
        # no cambia nada, y es el falso exacto que produjo el veinte de veinte.
        antes='    return "ejecutada" if _alcanza_proceso(funcion, grafo, frozenset()) else "derivada"',
        despues='    return "derivada"',
        esperados=frozenset(
            {"TestLaClaseSigueAlCodigo::test_anadir_un_subproceso_gira_la_clase_a_ejecutada"}
        ),
    ),
    Sonda(
        nombre="M3_una_busqueda_que_no_encuentra_devuelve_una_clase_inventada",
        fichero="scripts/measure_b9_gate_1_0.py",
        # El fallo MEDIDO de este bloque: el slug no se encontraba y la funcion
        # devolvia `derivada` por defecto en vez de levantar. Aqui se cambia el
        # fallo por un valor inventado, que es la misma mentira con otro disfraz.
        antes='    raise LookupError(\n        f"el slug {slug!r} no corresponde a ninguna funcion de este modulo.',
        despues=(
            "    return candidatos[0]\n    raise LookupError(\n"
            '        f"el slug {slug!r} no corresponde a ninguna funcion de este modulo.'
        ),
        esperados=frozenset(
            {
                "TestUnaBusquedaQueNoEncuentraNoInventaUnaRespuesta::"
                "test_un_slug_inexistente_no_devuelve_una_clase",
                "TestUnaBusquedaQueNoEncuentraNoInventaUnaRespuesta::"
                "test_el_mensaje_dice_las_dos_mitades_del_fallo",
            }
        ),
    ),
    Sonda(
        nombre="M4_la_clase_vuelve_a_poder_escribirse",
        fichero="scripts/measure_b9_gate_1_0.py",
        # `init=True` reabre la puerta: un constructor futuro puede pasar
        # `"ejecutada"` y las veinte clases vuelven a ser una lista escrita a
        # mano, que es WI-106 y WI-99 otra vez, en silencio.
        antes="    clase_evidencia: ClaseEvidencia = field(init=False)",
        despues='    clase_evidencia: ClaseEvidencia = "derivada"',
        esperados=frozenset(
            {
                "TestLaClaseSeDerivaYNoSeDeclara::test_el_campo_de_clase_no_se_puede_pasar_al_constructor"
            }
        ),
    ),
    Sonda(
        nombre="M5_la_evidencia_de_reproducibilidad_vuelve_a_ser_una_afirmacion",
        fichero="scripts/measure_b9_gate_1_0.py",
        # La frase antigua, textual. El predicado vuelve a decir que se
        # construye sin mirar si dos construcciones coinciden, que es
        # exactamente el defecto que el commit anterior cerro.
        antes='        f"la distribucion es REPRODUCIBLE, medido: {len(primera)} artefactos "',
        despues='        f"la distribucion se construye: {len(primera)} artefactos "',
        esperados=frozenset(
            {
                "TestLaReproducibilidadSeMideYNoSeAfirma::"
                "test_la_evidencia_nombra_la_medida_y_los_dos_sha"
            }
        ),
    ),
    Sonda(
        nombre="M6_la_construccion_no_produce_artefactos_que_comparar",
        fichero="scripts/measure_b9_gate_1_0.py",
        # Si la construccion devuelve una lista vacia, comparar dos listas
        # vacias da «identicas» y el gate passaria sin haber medido nada. Es el
        # cero silencioso de WI-115, un nivel mas abajo.
        antes="    return {\n        p.name: hashlib.sha256(p.read_bytes()).hexdigest()",
        despues='    return {\n        p.name: "" for p in ()  # sonda M6: sin construir nada',
        esperados=frozenset(
            {
                "TestLaReproducibilidadSeMideYNoSeAfirma::"
                "test_construir_dos_veces_con_distinta_fecha_da_los_mismos_bytes"
            }
        ),
    ),
)


def main() -> int:
    problema = _interprete_valido()
    if problema is not None:
        print("NO SE EJECUTA: el interprete no es el del proyecto.")
        print(problema)
        return 2

    sucio = _sin_trabajo_sin_commitar()
    if sucio:
        print("NO SE EJECUTA: hay cambios sin commitear en los mutables.")
        print("«Restaurar» y «borrar» son la misma operacion sin commit debajo.")
        for linea in sucio:
            print(f"  {linea}")
        return 2

    print(f"B15 · {len(SONDAS)} sondas sobre {len(SUITES)} ficheros de test\n")

    ids = _colectados(SUITES)
    if not ids:
        print("NO SE EJECUTA: la colecta no devolvio ningun test.")
        return 2
    faltan = [
        f"{sonda.nombre}: no existe el diagnostico {esperado}"
        for sonda in SONDAS
        for esperado in sorted(sonda.esperados)
        if not any(i.endswith(esperado) for i in ids)
    ]
    if faltan:
        print("NO SE EJECUTA: hay diagnosticos que no existen.")
        print("Una sonda cuyo esperado no esta escrito bien se contaria como cazada con")
        print("menos causa, y el numero seria falso. M5 de B13 fue exactamente eso.")
        for linea in faltan:
            print(f"  {linea}")
        return 2
    print(f"diagnosticos verificados: {sum(len(s.esperados) for s in SONDAS)} nombres existen")

    invalidas: list[str] = []
    for sonda in SONDAS:
        texto = (RAIZ / sonda.fichero).read_text(encoding="utf-8")
        apariciones = texto.count(sonda.antes)
        if apariciones != 1:
            invalidas.append(
                f"{sonda.nombre}: el ancla aparece {apariciones} veces, y se sustituiria la primera"
            )
        if sonda.antes == sonda.despues:
            invalidas.append(f"{sonda.nombre}: la deformacion es identica al texto que cambia")
    if invalidas:
        print("NO SE EJECUTA: hay sondas invalidas.")
        for linea in invalidas:
            print(f"  {linea}")
        return 2
    print(f"anclas verificadas: {len(SONDAS)} textos unicos\n")

    rc, caidos = _pytest(SUITES)
    if rc != 0 or caidos:
        print("VERDE DE PARTIDA FALSA: la suite ya esta roja sin mutar nada.")
        print(f"  rc={rc}  caidos={sorted(caidos)}")
        return 2
    print("linea base: suite verde sin mutar\n")

    causa_de: dict[str, str] = {}
    compartidas: list[str] = []
    invalidas = []
    for sonda in SONDAS:
        _limpia_cache()
        ruta = RAIZ / sonda.fichero
        texto = ruta.read_text(encoding="utf-8")
        try:
            ruta.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
            rc, caidos = _pytest(SUITES)
        finally:
            ruta.write_text(texto, encoding="utf-8")
        if not sonda.esperados <= caidos:
            invalidas.append(
                f"{sonda.nombre}: cayo {sorted(caidos)}, pero no sus diagnosticos "
                f"{sorted(sonda.esperados)}"
            )
            print(f"  [SIN CAZAR] {sonda.nombre}")
            continue
        if len(caidos) == len(sonda.esperados):
            print(f"  [CAZADA]    {sonda.nombre}  (solo sus diagnosticos)")
        else:
            print(f"  [CAZADA]    {sonda.nombre}  (+{sorted(caidos - sonda.esperados)})")
            compartidas.append(sonda.nombre)
        causa_de[sonda.nombre] = ", ".join(sorted(sonda.esperados))

    if invalidas:
        print(f"\n{len(invalidas)} sonda(s) sin cazar:")
        for linea in invalidas:
            print(f"  {linea}")
        return 1
    print(f"\n{len(SONDAS)}/{len(SONDAS)} sondas cazadas, {len(causa_de)} causas")

    sucios = _sin_trabajo_sin_commitar()
    if sucios:
        print("\nVEREDICTO NO VALIDO: el harness dejo el arbol sucio.")
        for linea in sucios:
            print(f"  {linea}")
        return 1
    if compartidas:
        print(f"sondas que tiraron mas de lo suyo: {compartidas}")
    print("arbol limpio: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
