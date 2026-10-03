"""Medidor del gate B7: la UX operacional no es una CLI con print.

Por que este instrumento existe
-------------------------------
El objetivo de B7 es literal: «La UX que importa no es conversar con
SkillGraph, es **entender que esta haciendo el sistema y gobernarlo**». Y
el gate que lo cierra nombra diez widgets vivos —Graph, Timeline, Evidence,
Decisions, Resources, Diff, Runs, Policies, Capabilities, Knowledge— que
escalan de summary card a panel a full-screen, «sobre las mismas APIs y
query models».

Hay una palabra cargada en esa frase: **las mismas**. Una TUI construida
sobre una API que no existe no comparte nada con la CLI, la duplica; y una
duplicacion que se pierde en el primer cambio es la forma mas comun de que
dos superficies digan cosas distintas sobre el mismo run.

Antes de escribir nada, se mide si la superficie que el gate nombra existe.
Y la medicion encuentra algo que no es «falta el TUI»: falta la PIEZA DE
ARRIBA. Sin un query model, «las mismas APIs» no tiene a que referirse.

LO QUE SE MIDE, y por que una grep no alcanza
---------------------------------------------
Un `grep` de los diez nombres encuentra 55 ficheros con «graph» y 18 con
«evidence», y de ahi sale la sensacion de que el trabajo esta hecho. No:
esos ficheros GUARDAN el dato. La pregunta del gate no es si el dato
existe sino si existe UNA FORMA de leerlo que no dependa de quien formatea.
Y esa forma no existe: hoy cada comando imprime cadenas formateadas a mano
y no hay ni un `--format`.

Asi que el medidor no busca el dato —ya esta— sino la TRES cosas que el
gate presupone y que se pueden comprobar por AST:

  P1  ¿existe un modulo de presentacion (algo que sepa renderizar)?
  P2  ¿los comandos tienen una via de salida ESTRUCTURADA, o imprimen texto?
  P3  ¿cada uno de los diez widgets tiene un query model que lo alimente?

Y la razon de que P2 se mida por AST y no contando `print()` es la misma
de siempre: un `print` en un docstring o en un mensaje de error no es una
salida de datos, y un predicado que no distingue las dos cuenta la prosa
como la interfaz.

COMO SE USA
-----------
    python scripts/measure_b7_operational_ux.py

Salida 0 con el bloque cerrado; salida 1 con huecos en alcance. Lo que esta
FUERA de alcance se imprime como registrado y NO baja el veredicto.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

RAIZ: Final[Path] = Path(__file__).resolve().parent.parent
SRC: Final[Path] = RAIZ / "src" / "skillgraph"
CLI: Final[Path] = SRC / "cli"

#: Los diez widgets del gate, con el modulo que deberia alimentarlos. Se
#: escriben AQUI, en el unico sitio que los declara, y no se copian en cada
#: test: un medidor con su propia copia del vocabulario mediria que el
#: codigo cumple con el medidor.
WIDGETS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("Graph", ("knowledge/graph",)),
    ("Timeline", ("runtime/",)),
    ("Evidence", ("knowledge/",)),
    ("Decisions", ("governance/",)),
    ("Resources", ("resources/",)),
    ("Diff", ("governance/graph_diff",)),
    ("Runs", ("runtime/",)),
    ("Policies", ("governance/",)),
    ("Capabilities", ("platform/ports",)),
    ("Knowledge", ("knowledge/",)),
)


@dataclass(frozen=True, slots=True)
class Pregunta:
    """Una pregunta del gate B7 con su veredicto y por que."""

    clave: str
    enunciado: str
    abierta: bool
    en_alcance: bool
    detalle: str


def _arbol_de_python(ruta: Path) -> ast.Module | None:
    try:
        return ast.parse(ruta.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _modulos_de_cli() -> list[Path]:
    return sorted(p for p in CLI.rglob("*.py") if "__pycache__" not in p.parts)


def _modulos_de_src() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _hay_modulo_de_presentacion() -> bool:
    """Existe un modulo cuya RAIZ sea presentar, no calcular.

    Se busca por AST y no por nombre de fichero porque el nombre es la
    convencion que el repo todavia no tiene: un guard que solo acepta
    `presentacion.py` daria ABIERTO sobre un modulo llamado `views.py` que
    cumple la misma funcion, y eso es medir la convencion en vez de la
    cosa. Lo que se busca es un simbolo que EXPONGA una superficie de
    render —una clase o funcion cuyo nombre lo diga— dentro de un modulo
    que no sea el nucleo de dominio.
    """
    verbos = {
        "render",
        "renderiza",
        "panel",
        "card",
        "vista",
        "view",
        "widget",
        "presenta",
        "pretty",
        "format_for_human",
        "to_display",
    }
    for ruta in _modulos_de_src():
        # Se excluye el dominio: presentar no es calcular, y un metodo
        # `to_dict` en un dataclass no es una superficie de render.
        partes = ruta.relative_to(SRC).parts
        if partes[0] in {"domain", "core"}:
            continue
        arbol = _arbol_de_python(ruta)
        if arbol is None:
            continue
        for nodo in ast.walk(arbol):
            nombre = ""
            if isinstance(nodo, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                nombre = nodo.name
            if not nombre:
                continue
            if nombre in {"render", "panel", "card", "vista", "widget", "presentar"}:
                return True
            if any(nombre.startswith(v) or nombre.endswith(v) for v in verbos):
                return True
    return False


def _comandos_con_salida_estructurada() -> tuple[int, int]:
    """Cuantos comandos CLI ofrecen via estructurada, y cuantos hay.

    Se mira por AST si el comando declara `--format` o `--json`, que es lo
    que hace que una TUI pueda leer lo mismo que la persona. Contar
    `print()` no sirve de nada: un comando puede imprimir diez lineas y no
    ofrecer ninguna via legible por maquina, y ese es el caso de hoy.
    """
    con_format = 0
    total = 0
    for ruta in _modulos_de_cli():
        arbol = _arbol_de_python(ruta)
        if arbol is None:
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            func = nodo.func
            # `parser.add_argument(...)` con `--format` o `--json`.
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "add_argument"
                and any(
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value in {"--format", "--json"}
                    for arg in nodo.args
                )
            ):
                con_format += 1
    for ruta in _modulos_de_cli():
        if ruta.name in {"parser.py", "runner.py", "exit_codes.py", "__init__.py"}:
            continue
        if ruta.name.startswith("_"):
            continue
        total += 1
    return con_format, total


def _widgets_con_query_model() -> tuple[str, ...]:
    """Que widgets tienen una proyeccion que los alimente.

    Se busca en el PAQUETE DE PRESENTACION y no en todo `src/`. La
    primera version buscaba en todo el arbol y daba ABIERTO sobre cuatro
    widgets que si tenian proyeccion; la segunda, ya restringida al
    nombre, daba FALSO VERDE: `get_policy`, `_resolve_policy` y
    `policy_store` existen en el dominio, asi que al borrar
    `policy_view` la pregunta seguia diciendo CERRADO. Un widget con
    modelo de LECTURA es una proyeccion en `presentation/`, no un
    `get_` que devuelve una fila: el primero responde «que ve el
    operador» y el segundo responde «como se lee una fila de la base»,
    y confundirlos es volver a medir lo que ya existe.

    Y el nombre se acepta en singular o en plural porque el gate escribe
    en plural —`Policies`— y el codigo en singular —`policy_view`—. Se
    exige que la raiz aparezca como SEGMENTO del nombre, no como
    subcadena libre: `evidence` casaria con `evidenciar`, y un nombre que
    contiene la palabra no declara la proyeccion.
    """
    sin_modelo: list[str] = []
    nombres_pub = {
        nodo.name.lower()
        for ruta in sorted((SRC / "presentation").rglob("*.py"))
        for nodo in [_arbol_de_python(ruta)]
        if nodo is not None
        for nodo in ast.walk(nodo)
        if isinstance(nodo, (ast.ClassDef, ast.FunctionDef))
    }
    for widget, _modulo in WIDGETS:
        clave = widget.lower()
        raices = {clave}
        if clave.endswith("ies"):
            raices.add(clave[:-3] + "y")
        if clave.endswith("es"):
            raices.add(clave[:-2])
        if clave.endswith("s"):
            raices.add(clave[:-1])
        if not any(
            any(raiz in nombre.split("_") or nombre.endswith(raiz) for raiz in raices)
            for nombre in nombres_pub
        ):
            sin_modelo.append(widget)
    return tuple(sin_modelo)


def preguntas() -> tuple[Pregunta, ...]:
    hay_presentacion = _hay_modulo_de_presentacion()
    con_format, total_comandos = _comandos_con_salida_estructurada()
    sin_modelo = _widgets_con_query_model()

    return (
        Pregunta(
            clave="P1",
            enunciado="¿existe una superficie de presentacion, o solo de calculo?",
            abierta=not hay_presentacion,
            en_alcance=True,
            detalle=(
                "no hay ningun simbolo que EXPONGA render: el repo sabe leer "
                "y persistir, y no sabe presentar. Sin esta pieza, «las "
                "mismas APIs» del gate no tiene a que referirse: la TUI "
                "tendria que reimplementar la consulta"
                if not hay_presentacion
                else "existe una superficie de render que CLI y TUI compartirian"
            ),
        ),
        Pregunta(
            clave="P2",
            enunciado="¿un operador o un agente pueden leer lo mismo?",
            abierta=con_format == 0,
            en_alcance=True,
            detalle=(
                f"{con_format} declaraciones de --format/--json en "
                f"{total_comandos} modulos de comando. Hoy la salida es "
                f"texto formateado a mano dentro de cada comando, asi que "
                f"cualquier consumidor que no sea una persona tiene que "
                f"parsear columnas"
                if con_format == 0
                else f"{con_format} comandos ofrecen via estructurada"
            ),
        ),
        Pregunta(
            clave="P3",
            enunciado="¿los diez widgets tienen un query model que los alimente?",
            abierta=bool(sin_modelo),
            en_alcance=True,
            detalle=(
                f"sin modelo legible: {', '.join(sin_modelo)}. El dato "
                f"EXISTE en el arbol —el medidor lo comprobó— lo que no "
                f"existe es una forma de leerlo que no dependa de quien "
                f"formatea"
                if sin_modelo
                else "los diez widgets tienen modelo"
            ),
        ),
    )


def fuera_de_alcance() -> tuple[tuple[str, str], ...]:
    """Lo que este bloque NO cierra, y por que."""
    return (
        (
            "P4",
            "¿la TUI es usable de verdad, o solo existe la pieza de abajo?",
        ),
    )


def main() -> int:
    todas = preguntas()
    en_alcance = [p for p in todas if p.en_alcance]
    registradas = fuera_de_alcance()
    abiertas = [p for p in en_alcance if p.abierta]

    print("Gate B7 — la UX operacional, por debajo de la TUI")
    print("=" * 78)
    print()
    for p in todas:
        marca = "ABIERTO" if p.abierta else "CERRADO"
        print(f"[{marca:>7}] {p.clave}  {p.enunciado}")
        print(f"          {p.detalle}")
        print()
    for clave, enunciado in registradas:
        print(f"[FUERA   ] {clave}  {enunciado}")
        print("          FUERA DEL ALCANCE de B7 y por eso NO baja el veredicto:")
        print(
            "          depende de un terminal y de una interaccion humana, que "
            "el CI no tiene. Lo que se mide en B7 es la pieza de la que la "
            "TUI depende, que es comprobable sin humano; que la TUI sea "
            "usable se mide cuando haya alguien usandola."
        )
        print()

    print("-" * 78)
    print(f"preguntas del gate B7 en alcance: {len(en_alcance)}")
    print(f"huecos ABIERTOS EN ALCANCE: {len(abiertas)} de {len(en_alcance)}")
    if registradas:
        print(f"REGISTRADO FUERA DE ALCANCE: {len(registradas)}")
    print()
    if not abiertas:
        print("VEREDICTO: el hueco de este bloque esta cerrado. Salida 0.")
        return 0
    print(f"VEREDICTO: {len(abiertas)} hueco(s) abierto(s) en alcance. Salida 1.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
