#!/usr/bin/env python3
"""B30 — autocomprobacion del instrumento de contexto: cinco sondas.

**POR QUE EXISTE UN HARNESS QUE ROMPE EL CODIGO A PROPOSITO.** Un guard que
solo sabe ponerse en verde no esta probado: `measure_b30_contexto.py` podria
contar el nombre de un campo y devolver «0/5 ABIERTAS» sin que ninguna de las
cinco propiedades sea cierta. Este script **aplica una sonda que deliberadamente
rompe una propiedad, comprueba que el guard se pone rojo, y restaura el arbol**.

# QUE SE ROMPE EN CADA SONDA, Y POR QUE ESA PROPIEDAD

    M1  EL REGISTRO DE LO QUE SE CAYO   -> `apply_budget` deja de acumular omisiones
    M2  EL CAMPO DEL HANDOFF            -> `HandoffKnowledge.omitidos` deja de declararse
    M3  LA FIRMA DE LAS OMISIONES       -> `omitidos` sale del `to_dict` (NO del hash)
    M4  LA DECLARACION HONESTA         -> el presupuesto holgado tambien declara omisiones
    M5  LA CUARTA REGLA DEL SKIP        -> `should_skip_adapter` vuelve a no verlas (CONTRA SALTO)

**M3 ES LA SONDA QUE ESTA RECONSTRUYE UNA DISTANCIA YA MEDIDA.** `WI-111`
midio que el Core firma el hash en un instante y los eventos lo consumen en
otro. Aqui la distancia esta **dentro del propio handoff**: el campo
`omitidos` existe, el Adapter lo ve, y si `to_dict` no lo serializa el hash
**no lo firma**. Esa sonda no rompe la visibilidad —rompe la FIRMA—, y por eso
es distinta de M2, que rompe la visibilidad y deja la firma intacta. Un arreglo
que comprobara «el handoff declara omisiones» pasaria M2 sin ver M3.

**Y M5 ES EL CONTRA SALTO DEL HARNESS.** Sin ella, un arreglo que dejara
`should_skip_adapter` exactamente como estaba —mirando solo el manifest—
cumpliria P1 a P4 y dejaria al sistema **quedandose sin agente sobre una
respuesta cortada**, que es la mitad grave de la fila de B30. El instrumento
no podria distinguirlo de un arreglo completo.

# LAS SONDAS SON DE UN FICHERO, Y POR QUE (A DIFERENCIA DE B29)

En B29 hubo que renombrar identificadores **de punta a punta** porque las
propiedades cruzaban cinco ficheros. Aqui las cinco propiedades se apoyan en
**un contrato por fichero**: el registro vive en `context_controller`, el campo
y la firma en `handoff`, y la cuarta regla en `file_handoff`. No hace falta un
renombrado multiple porque **no hay un identificador compartido** entre ellos
—que es, de hecho, la medida de que B30 no cruza fronteras: lo que se anade es
un campo en un sitio y una regla en otro, y el hash es lo que los ata.

# LAS ANCLAS SON REGEX, Y POR QUE NO TEXTO LITERAL

La version de B28 anclaba con texto exacto y **`ruff format` las desanclo todas**.
Aqui las cinco sondas usan patron. Lo que se muta es la **semantica** —la
llamada al acumulador, el campo del dataclass, la linea del `to_dict`—, y eso
no cambia porque alguien parta la linea en otro sitio.

# EL GUARD DE SINTAXIS

Una sonda que rompe la sintaxis hace que el guard se ponga rojo por la razon
equivocada. Este harness **importa los modulos tocados antes de juzgar**, y una
sonda que no cargue se clasifica `ROTA`: no cuenta ni como cazada ni como
inocua, porque seria un fallo del harness. Solo se acepta `CAZADA` cuando el
arbol carga y el guard se pone rojo **por la propiedad**.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INSTRUMENTO = RAIZ / "scripts" / "measure_b30_contexto.py"
PY = RAIZ / ".venv" / "bin" / "python"

CAZADA = "CAZADA"
INOCUA = "INOCUA"
ROTA = "ROTA"
#: El instrumento no pudo terminar: el arbol esta roto, y eso ES un fallo de
#: las propiedades, no una sonda que no mordio.
CAIDA = -1

#: Todo lo que hay que importar para saber que el arbol SIGUE CARGANDO.
MODULOS = (
    "skillgraph.knowledge.context_controller",
    "skillgraph.runtime.handoff",
    "skillgraph.knowledge.file_handoff",
)


@dataclass(frozen=True, slots=True)
class Cambio:
    """Una sustitucion regex en UN fichero.

    `fichero` es relativo a `RAIZ`. `viejo` es **regex**, `nuevo` admite
    backreferences `\\g<1>` porque se expande con `Match.expand()`.

    `cuantas` es el numero exacto de apariciones que se sustituyen, y **`-1`
    significa «todas, pero al menos una»**.
    """

    fichero: str
    viejo: str
    nuevo: str
    cuantas: int = 1


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una mutacion y la propiedad que se supone que rompe."""

    nombre: str
    que_rompe: str
    cambios: tuple[Cambio, ...]
    p_abiertas_minimo: int = 1


#: Las cinco sondas.
SONDAS: tuple[Sonda, ...] = (
    # ------------------------------------------------------------------ M1
    # P1 pregunta si el presupuesto DECLARA lo que dejo fuera. La sonda quita
    # el acumulador: `break` sin `extend` deja el truncamiento mudo otra vez,
    # que es exactamente el defecto original. El codigo sigue cargando y el
    # corte sigue siendo el corte —solo desaparece el registro—, luego P4
    # tambien se abre (no declara lo que se cayo) pero el hash sigue firmando
    # una lista vacia, que es coherente.
    Sonda(
        nombre="M1",
        que_rompe="el presupuesto vuelve a truncar EN SILENCIO",
        cambios=(
            Cambio(
                fichero="src/skillgraph/knowledge/context_controller.py",
                viejo=r"(?m)^        omitidos\.extend\(Omision\.desde_recurso\(r\) for r in optional\[opcionales_vistos - 1 :\]\)$",
                nuevo="        pass",
            ),
        ),
    ),
    # ------------------------------------------------------------------ M2
    # P2 pregunta si el `HandoffKnowledge` DECLARA el campo. Se renombra el
    # campo del dataclass y su lectura en `compile_handoff`, de punta a punta
    # en el par, para que el arbol siga cargando: si solo se renombrara el
    # dataclass, `compile_handoff` pasaria un argumento que ya no existe y
    # reventaria con `TypeError` —una «cazada» por crash, que es el error 32
    # por cuarta vez.
    Sonda(
        nombre="M2",
        que_rompe="el handoff deja de declarar las omisiones (el registro sigue)",
        cambios=(
            Cambio(
                fichero="src/skillgraph/runtime/handoff.py",
                viejo=r"(?m)^    omitidos: tuple\[tuple\[str, str, str, int\], \.\.\.\] = field\(default_factory=tuple\)$",
                nuevo="    descartados: tuple[tuple[str, str, str, int], ...] = field("
                "default_factory=tuple)",
            ),
            Cambio(
                fichero="src/skillgraph/knowledge/context_controller.py",
                viejo=r"(?m)^            omitidos=tuple\(o\.como_tupla\(\) for o in presupuesto\.omitidos\),$",
                nuevo="            descartados=tuple(o.como_tupla() for o in presupuesto.omitidos),",
            ),
        ),
    ),
    # ------------------------------------------------------------------ M3
    # P3 pregunta si lo omitido entra en el hash firmado. **La sonda borra la
    # serializacion, NO el campo**: el handoff sigue declarado y visible, y el
    # Adapter sigue viendo las omisiones —lo que deja de estar es la FIRMA.
    # Por eso es una sonda distinta de M2, y por eso P2 sigue cerrada: un
    # arreglo que comprobara «el handoff declara omisiones» pasaria M2 sin ver
    # M3. Es el mismo patron que WI-111, a otra escala.
    Sonda(
        nombre="M3",
        que_rompe="las omisiones dejan de entrar en el hash (siguen visibles)",
        cambios=(
            Cambio(
                fichero="src/skillgraph/runtime/handoff.py",
                viejo=r'(?m)^                "omitidos": \[list\(item\) for item in self\.knowledge\.omitidos\],\n',
                nuevo="",
            ),
        ),
    ),
    # ------------------------------------------------------------------ M4
    # P4 es el CONTRA SALTO DEL INSTRUMENTO: un truncado lo dice **y uno holgado
    # NO se inventa omisiones**. La sonda hace que la holgura tambien declare:
    # un campo que siempre dice tres es tan mentiroso como el que no dice
    # ninguna. Sin esta sonda, un arreglo que declarara `omitidos` lleno
    # siempre pasaria P1 y P3.
    Sonda(
        nombre="M4",
        que_rompe="el presupuesto HOLGADO tambien declara omisiones (se inventa)",
        cambios=(
            Cambio(
                fichero="src/skillgraph/knowledge/context_controller.py",
                viejo=r"(?m)^    omitidos: list\[Omision\] = \[\]$",
                nuevo="    omitidos: list[Omision] = ["
                'Omision(kind="claim", namespace="claim:fantasma", '
                'name="fantasma", chars=1)]',
            ),
        ),
    ),
    # ------------------------------------------------------------------ M5
    # P5 pregunta si el SKIP puede siquiera VER las omisiones. La sonda quita
    # el parametro entero, que es lo que hace la cuarta regla. El arbol carga
    # y el skip vuelve a mirar solo el manifest: es la sonda que separa «se
    # implemento el bloque» de «se implemento la mitad que importa».
    Sonda(
        nombre="M5",
        que_rompe="el SKIP vuelve a declarar completo un slice truncado",
        cambios=(
            Cambio(
                fichero="src/skillgraph/knowledge/file_handoff.py",
                viejo=r"(?m)^    manifest: CoverageManifest,\n    omitidos: tuple\[tuple\[str, str, str, int\], \.\.\.\] = \(\),$",
                nuevo="    manifest: CoverageManifest,",
            ),
            Cambio(
                fichero="src/skillgraph/knowledge/file_handoff.py",
                viejo=r"(?m)^    if omitidos:\n"
                r"        # B30: hay contexto que no cupo\. La cobertura de firmas puede estar\n"
                r"        # completa y aun asi faltar contexto, y saltarse al Adapter dejaria\n"
                r"        # al sistema sin agente sin que nadie lo dijera\.\n"
                r"        return False$",
                nuevo="    if False:\n        return False",
            ),
        ),
    ),
)


def carga_el_arbol() -> tuple[bool, str]:
    """¿Cargan TODOS los modulos que las sondas tocan?

    **POR QUE EL `import` Y NO UNA COMPILACION.** Una sonda puede dejar el texto
    sintacticamente valido y aun asi romper el arbol en tiempo de importacion,
    y `py_compile` la daria por buena. Lo que tiene que funcionar es el modulo
    **cargado**, porque es lo que el instrumento importa.
    """
    proc = subprocess.run(
        [str(PY), "-c", "import " + ", ".join(MODULOS)],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]


def preguntas_abiertas() -> tuple[int, str]:
    """Corre el instrumento y cuenta las preguntas ABIERTAS.

    **Y DEVUELVE VEREDICTO AUNQUE EL INSTRUMENTO REVENTE** (leccion de B28,
    error 32): una caida es `CAZADA`, porque un arbol que ni siquiera puede
    ejecutar el instrumento NO satisface las propiedades. Lo que el harness
    clasifica aparte es la *caida*, porque esa es la razon y no el veredicto.
    """
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
    return CAIDA, salida


@dataclass
class Informe:
    resultados: list[tuple[str, str, str]] = field(default_factory=list)
    rotas: list[str] = field(default_factory=list)


def aplica(originales: dict[str, str], sonda: Sonda) -> dict[str, str] | None:
    """Devuelve los ficheros mutados, o `None` si alguna sonda esta DESANCLADA.

    **`Match.expand()`, no el retorno crudo.** Con `repl` como funcion, Python
    usa el valor devuelto **literalmente**: un `\\g<1>` en el retorno se
    escribiria como texto en vez de expandirse y la sonda escribiria basura en
    vez de mutar.
    """
    mutados: dict[str, str] = {}
    for cambio in sonda.cambios:
        if cambio.fichero not in originales:
            return None
        patron = re.compile(cambio.viejo)
        texto = originales[cambio.fichero]
        if not patron.search(texto):
            return None
        count = 0 if cambio.cuantas < 0 else cambio.cuantas
        nuevo_texto, n = patron.subn(
            lambda m, nuevo=cambio.nuevo: m.expand(nuevo), texto, count=count
        )
        if cambio.cuantas < 0:
            if n < 1:
                return None
        elif n != cambio.cuantas:
            return None
        mutados[cambio.fichero] = nuevo_texto
    return mutados


def main() -> int:
    originales: dict[str, str] = {}
    for sonda in SONDAS:
        for cambio in sonda.cambios:
            f = cambio.fichero
            if f not in originales:
                originales[f] = (RAIZ / f).read_text(encoding="utf-8")

    print("B30 — autocomprobacion del instrumento de contexto")
    print("  ficheros: " + ", ".join(sorted(originales)))
    print(f"  sondas: {len(SONDAS)}\n")

    base_abiertas, salida_base = preguntas_abiertas()
    print(f"  sin sondas: {base_abiertas} preguntas abiertas")
    if base_abiertas == CAIDA:
        print("  el instrumento NO TERMINA sobre el arbol sin sondas")
        print(salida_base[-600:])
        return 2
    if base_abiertas != 0:
        print("  el bloque NO esta cerrado: se mide sobre un arbol que ya falla")
        print(salida_base[-600:])
        return 2

    informe = Informe()
    for sonda in SONDAS:
        mutados = aplica(originales, sonda)
        if mutados is None:
            informe.resultados.append(
                (sonda.nombre, ROTA, "sonda DESANCLADA: el texto ya no existe")
            )
            informe.rotas.append(sonda.nombre)
            continue

        for f, txt in mutados.items():
            (RAIZ / f).write_text(txt, encoding="utf-8")

        try:
            carga_ok, detalle = carga_el_arbol()
            if not carga_ok:
                informe.resultados.append(
                    (sonda.nombre, ROTA, f"el arbol NO CARGA: {detalle[-300:]}")
                )
                informe.rotas.append(sonda.nombre)
                continue

            abiertas, _salida = preguntas_abiertas()
            if abiertas == CAIDA:
                # El arbol carga y el instrumento revienta: la propiedad esta
                # rota, aunque por un camino que no es el del veredicto.
                informe.resultados.append(
                    (sonda.nombre, CAZADA, "el instrumento revienta con el arbol sano")
                )
                continue
            if abiertas >= sonda.p_abiertas_minimo:
                informe.resultados.append(
                    (sonda.nombre, CAZADA, f"{abiertas} pregunta(s) abierta(s): {sonda.que_rompe}")
                )
            else:
                informe.resultados.append(
                    (
                        sonda.nombre,
                        INOCUA,
                        f"solo {abiertas} abierta(s) y hacia falta "
                        f"{sonda.p_abiertas_minimo}: la sonda no muerde",
                    )
                )
        finally:
            for f, txt in originales.items():
                (RAIZ / f).write_text(txt, encoding="utf-8")

    print()
    cazadas = sum(1 for _, v, _ in informe.resultados if v == CAZADA)
    inocuas = [n for n, v, _ in informe.resultados if v == INOCUA]
    for nombre, veredicto, detalle in informe.resultados:
        print(f"  {nombre}  {veredicto:<7} {detalle}")

    print(f"\nMutaciones: {cazadas}/{len(SONDAS)} cazadas")
    if inocuas:
        print(f"  INOCUAS: {', '.join(inocuas)}")
    if informe.rotas:
        print(f"  ROTAS (fallo del harness, no de la propiedad): {', '.join(informe.rotas)}")
        return 2
    return 0 if cazadas == len(SONDAS) and not inocuas else 1


if __name__ == "__main__":
    raise SystemExit(main())
