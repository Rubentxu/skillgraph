#!/usr/bin/env python3
"""B28 — autocomprobacion del instrumento: cinco sondas, cinco propiedades rotas.

**POR QUE EXISTE UN HARNESS QUE ROMPE EL CODIGO A PROPOSITO.** Un guard que
solo sabe ponerse en verde no esta probado: `measure_b28_autoridad.py` podria
estar midiendo el nombre de una funcion y devolver «0/5 cerradas» sin que ninguna
de las cinco propiedades sea certaina. Este script **aplica una sonda que
deliberadamente rompe una propiedad, comprueba que el guard se pone rojo, y
restaura el arbol**.

Es el mismo argumento que `mutate_b27_conflictos.py` y que el M2 de WI-110:
una derivacion que devolviera siempre la lista vacia pasaria todos los tests
en verde porque no mediria nada.

# QUE SE ROMPE EN CADA SONDA, Y POR QUE ESA PROPIEDAD

    M1  UN RANKING GLOBAL         -> los dos intents dan el mismo ganador
    M2  EL GUARD DEL AGENTE       -> el agente gana por posicion, no por guard
    M3  LA EXPLICABILIDAD         -> `descartadas` vuelve vacia
    M4  EL VOCABULARIO CERRADO    -> `query_intent` acepta cualquier string
    M5  EL ORDEN DE ENTRADA       -> la eleccion lee la lista en vez del rango

Cada sonda ataca la PROPIEDAD, no el texto: M1 no borra el ranking, hace que
los dos perfiles compartan preferencia, que es exactamente el defecto que la
fila del roadmap acusa.

# LAS ANCLAS SON REGEX, Y POR QUE NO TEXTO LITERAL

La primera version anclaba cada sonda con el texto exacto, y **`ruff format`
las desanclo todas**: las cinco pasaron a `ROTA` en la misma corrida. Volver a
anclar a mano funciona una vez y se rompe en el proximo `format`, asi que las
sondas se anclan con patron y espacios como `\\s+`. Lo que se muta es la
**semantica** —`permitir_inferencia_de_agente: bool = False`—, y eso no cambia
porque alguien parta la linea en otro sitio.

# EL GUARD DE SINTAXIS, Y POR QUE B27 LO NECESITO TAMBIEN

M5 de B27 se aplicaba a la mitad de un `return` multilinea y **rompia la
compilacion del modulo entero**. La sonda fallaba —que es lo que se pedia— pero
por una razon equivocada: el harness decia «la propiedad aguanto» cuando lo que
habia pasado es que el modulo ni siquiera cargaba. Un fallo de sintaxis **no
es una propiedad rota**.

Por eso este harness **compila el arbol antes de juzgar**. Una sonda que rompe
la sintaxis se clasifica `ROTA` y no cuenta ni como cazada ni como
inocua: se cuenta como **error del harness**, y sale con codigo 2. Solo se
acepta `CAZADA` cuando el modulo carga y el guard se pone rojo por la
propiedad.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODULO = RAIZ / "src" / "skillgraph" / "knowledge" / "authority.py"
INSTRUMENTO = RAIZ / "scripts" / "measure_b28_autoridad.py"
PY = RAIZ / ".venv" / "bin" / "python"

CAZADA = "CAZADA"
INOCUA = "INOCUA"
ROTA = "ROTA"


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una mutacion y la propiedad que se supone que rompe."""

    nombre: str
    que_rompe: str
    #: **Regex, no texto literal** (ver la nota del modulo). Compila una vez
    #: y se aplica con `re.sub`, `count=1`.
    viejo: str
    nuevo: str
    p_abiertas_minimo: int = 1


#: Las cinco sondas. Todas apuntan a `authority.py`, que es donde vive la
#: politica y donde un cambio razonable podria dejarla en verde sin dejar de
#: funcionar para quien no mira.
SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1",
        que_rompe="un ranking global: los dos perfiles declaran la MISMA preferencia",
        # Se absorbe el nombre del perfil Y su tupla entera, porque hay que
        # cambiar los cuatro origenes. La primera version de esta sonda
        # cambiaba solo los dos primeros y dejaba `observed` DOS veces en la
        # tupla — que `__post_init__` rechaza como origen repetido, luego la
        # sonda no llegó a crear el ranking global que queria medir. El
        # rechazo es correcto; la sonda estaba mal.
        viejo=r'(name="arquitectura-intencionada",(?:.|\n)*?preferencia=\()'
        r'\s*"human-asserted",\s*"derived-deterministically",'
        r'\s*"observed",\s*"agent-inferred",\s*\)',
        nuevo=r'\g<1>"observed", "derived-deterministically", '
        r'"human-asserted", "agent-inferred")',
    ),
    Sonda(
        nombre="M2",
        que_rompe="el guard del agente depende de la POSICION y no del flag",
        viejo=r"permitir_inferencia_de_agente: bool = False",
        nuevo="permitir_inferencia_de_agente: bool = True",
    ),
    Sonda(
        nombre="M3",
        que_rompe="la resolucion deja de explicar que descarta",
        # Se absorbs TODO el enunciado —incluida la comprehension— porque
        # cambiar solo la cabecera deja codigo colgando y rompe la compilacion.
        # El guard la clasifica ROTA, que es lo correcto, pero no mide nada.
        viejo=r"descartadas = tuple\(\s*\n(?:\s*[^\n]*\n)+?\s*\)",
        nuevo="descartadas = tuple()",
    ),
    Sonda(
        nombre="M4",
        que_rompe="la intencion vuelve a ser un string libre",
        viejo=r"if s not in QUERY_INTENTS:",
        nuevo="if False:",
    ),
    Sonda(
        nombre="M5",
        que_rompe="la eleccion lee la lista en vez del mejor rango",
        viejo=r"rangos = \[\s*perfil\.rango_de\(c\.assertion_origin\)\s*"
        r"for c in candidatas\s*if _es_admisible\(c, perfil\)\s*\]",
        nuevo="rangos = [perfil.rango_de(candidatas[0].assertion_origin)]",
    ),
)


def compila_el_arbol() -> tuple[bool, str]:
    """¿El arbol COMPILA tras la sonda?

    **POR QUE ESTE GUARD EXISTE.** Una sonda que rompe la sintaxis hace que el
    guard se ponga rojo por la razon equivocada, y el harness contaria «la
    propiedad aguanto» siendo verdad que lo que se rompio fue el modulo. Es el
    error 32 de B26 repetido en el bloque siguiente, y se detecta aqui antes de
    contar.
    """
    proc = subprocess.run(
        [str(PY), "-c", "import skillgraph.knowledge.authority"],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-600:]


def preguntas_abiertas() -> tuple[int, str]:
    """Corre el instrumento y cuenta las preguntas ABIERTAS."""
    proc = subprocess.run(
        [str(PY), str(INSTRUMENTO)],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        check=False,
    )
    salida = proc.stdout + proc.stderr
    for ln in salida.splitlines():
        if ln.startswith("RESULTADO:"):
            return int(ln.split(":")[1].strip().split("/")[0]), salida
    return -1, salida


@dataclass
class Informe:
    resultados: list[tuple[str, str, str]] = field(default_factory=list)
    rotas: list[str] = field(default_factory=list)


def aplica(texto: str, sonda: Sonda) -> str | None:
    """Aplica la sonda por regex. `None` si el patron ya no esta: eso es
    `ROTA` (sonda desanclada), nunca «inocua».

    **`m.expand()`, no el retorno crudo.** Con `repl` como funcion, Python usa
    el valor devuelto **literalmente**: un `\\g<1>` en el retorno se escribiria
    como texto en vez de expandirse, y la sonda escribiria basura en vez de
    mutar. `Match.expand()` es la que procesa los backreferences.
    """
    patron = re.compile(sonda.viejo)
    if not patron.search(texto):
        return None
    mutado, n = patron.subn(lambda m: m.expand(sonda.nuevo), texto, count=1)
    return mutado if n == 1 else None


def main() -> int:
    original = MODULO.read_text(encoding="utf-8")

    print("B28 — autocomprobacion del instrumento de autoridad")
    print(f"  modulo: {MODULO.relative_to(RAIZ)}")
    print(f"  sondas: {len(SONDAS)}\n")

    base_abiertas, salida_base = preguntas_abiertas()
    print(f"  sin sondas: {base_abiertas} preguntas abiertas")
    if base_abiertas != 0:
        print("  el bloque NO esta cerrado: se mide sobre un arbol que ya falla")
        print(salida_base[-600:])
        return 2

    informe = Informe()
    for sonda in SONDAS:
        mutado = aplica(original, sonda)
        if mutado is None:
            informe.resultados.append(
                (
                    sonda.nombre,
                    ROTA,
                    f"el texto a mutar NO existe (desanclada): {sonda.viejo[:60]!r}",
                )
            )
            informe.rotas.append(sonda.nombre)
            print(f"  {sonda.nombre}  {ROTA:<7} {sonda.que_rompe}")
            continue

        MODULO.write_text(mutado, encoding="utf-8")
        try:
            compila, salida_compila = compila_el_arbol()
            if not compila:
                informe.resultados.append(
                    (sonda.nombre, ROTA, "la sonda rompe la compilacion del modulo")
                )
                informe.rotas.append(sonda.nombre)
                print(f"  {sonda.nombre}  {ROTA:<7} {sonda.que_rompe}")
                print(f"      {salida_compila.strip()[:200]}")
                continue

            abiertas, salida = preguntas_abiertas()
            cazada = abiertas >= sonda.p_abiertas_minimo
            veredicto = CAZADA if cazada else INOCUA
            detalle = f"abre {abiertas} pregunta(s); {sonda.que_rompe}"
            informe.resultados.append((sonda.nombre, veredicto, detalle))
            print(f"  {sonda.nombre}  {veredicto:<7} {sonda.que_rompe}")
            print(f"      {detalle}")
            if not cazada:
                print(f"      SIN CAZAR: {salida[-400:]}")
        finally:
            MODULO.write_text(original, encoding="utf-8")

    cazadas = [n for n, v, _ in informe.resultados if v == CAZADA]
    inocuas = [n for n, v, _ in informe.resultados if v == INOCUA]
    rotas = [n for n, v, _ in informe.resultados if v == ROTA]

    print()
    print(f"  cazadas: {len(cazadas)}/{len(SONDAS)}  {cazadas}")
    if inocuas:
        print(f"  INOCUAS: {inocuas}  <-- el guard no muerde, o la sonda no rompe nada")
    if rotas:
        print(f"  ROTAS (error del harness, no del bloque): {rotas}")

    print("\n  tras restaurar el modulo:")
    restauradas, salida = preguntas_abiertas()
    print(
        f"  RESULTADO: {salida.splitlines()[-2].strip() if len(salida.splitlines()) > 1 else '?'}"
    )
    if restauradas != 0:
        print("  FALLA: el arbol no volvio a su estado")
        print(salida[-600:])
        return 1
    print("  VERDE: el bloque vuelve a dar 0/5 abiertas")

    if rotas:
        print("\n  FALLA del harness: hay sondas ROTAS")
        return 2
    if inocuas:
        print("\n  FALLA: alguna sonda NO fue cazada")
        return 1
    print(f"\n  OK: {len(cazadas)}/{len(SONDAS)} sondas cazadas, y el bloque cerrado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
