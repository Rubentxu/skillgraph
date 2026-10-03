"""Medidor del gate B6: cada afirmacion distingue SU ORIGEN EPISTEMICO.

Por que este instrumento existe
-------------------------------
El gate B6 dice, literal: «Cada afirmacion importante del Knowledge Graph
distingue `observed` · `derived-deterministically` · `agent-inferred` ·
`human-asserted`, y conserva su provenance».

Antes de escribir codigo, se mide si eso se sostiene. Y la medicion
encuentra algo que no es un campo que falte: es un campo que EXISTE y que
no dice lo que su nombre dice.

`Claim.extraction_method` parece el sitio donde vive la clasificacion. Es
un `str` libre, y sus valores medidos son:

    "static_analysis"    el default
    "regex_def"          la heuristica concreta de file_signature
    "manual"             10 escrituras, TODAS en tests/

Los tres son METODOS DE EXTRACCION, no ORIGENES EPISTEMICOS. La pregunta
del gate no es «como se extrajo esto?» sino «quien AFIRMA esto y con que
autoridad?». Son dos ejes ortogonales, y un solo campo no puede
representar los dos: con `extraction_method="regex_def"` no se sabe si lo
afirmo un regex, un agente o una persona, y `agent-inferred` —que si es un
origen— no se podria escribir sin perder el metodo.

Por eso el hueco no se cierra añadiendo el campo: se cierra SEPARANDO los
dos ejes, y eso es lo que este instrumento tiene que poder distinguir
antes y despues.

COMO SE USA
-----------
    python scripts/measure_b6_provenance.py

Salida 0 con el bloque cerrado; salida 1 con huecos en alcance. Lo que
esta FUERA de alcance se imprime como registrado y NO baja el veredicto:
son deuda, no un olvido.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

RAIZ: Final[Path] = Path(__file__).resolve().parent.parent
SRC: Final[Path] = RAIZ / "src" / "skillgraph"
TESTS: Final[Path] = RAIZ / "tests"

# El vocabulario del gate B6, escrito donde el gate lo escribe. Si esto
# se mueve, el medidor se mueve con el: un medidor con su propia copia
# del vocabulario mediria que el codigo cumple con el medidor.
ORIGENES_B6: Final[tuple[str, ...]] = (
    "observed",
    "derived-deterministically",
    "agent-inferred",
    "human-asserted",
)


@dataclass(frozen=True, slots=True)
class Pregunta:
    """Una pregunta del gate B6 con su veredicto y por que."""

    clave: str
    enunciado: str
    abierta: bool
    en_alcance: bool
    detalle: str


def _modulos() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _arbol_de_python(ruta: Path) -> ast.Module | None:
    try:
        return ast.parse(ruta.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _campo_de_claim(clase: str, campo: str) -> ast.expr | None:
    """El campo `campo` del dataclass `clase`, leido por AST.

    Se lee por AST y no por texto porque el nombre aparece en docstrings y
    en comentarios: `graph.py` documenta `extraction_method` en prosa, y
    un buscador de cadena contaria la prosa como el campo. Es el error 32
    de WI-113 aplicado a un buscador.

    El campo se PASA como argumento y no se deduce del nombre de la clase.
    La primera version hacia `nombre.lower()` —`Claim` -> `claim`—, y como
    el campo real se llama `extraction_method` no encontraba nada y
    devolvia None. El predicado que lo consume leia ese None como «ya no
    es str» y daba P2 CERRADO sobre un codigo que sigue siendo `str`. Un
    helper que devuelve None cuando no encuentra lo que busca, y un
    predicado que trata None como cerradura, se combinan en una mentira
    con codigo de salida 0: por eso None se distingue aqui de un
    resultado valido y el que llama lo comprueba.
    """
    grafo = _arbol_de_python(SRC / "knowledge" / "graph.py")
    if grafo is None:
        return None
    for nodo in grafo.body:
        if not isinstance(nodo, ast.ClassDef) or nodo.name != clase:
            continue
        for item in nodo.body:
            if (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id == campo
            ):
                return item.annotation
    return None


def _valores_de_extraction_method() -> dict[str, int]:
    """Cuantas veces se escribe cada valor, y en que capa.

    Separa `src/` de `tests/` porque la distincion ES el hallazgo: un
    valor que solo aparece en tests no es un metodo de extraccion que el
    sistema use, es una comodidad de fixture.
    """
    conteo: dict[str, int] = {}
    for base, etiqueta in ((SRC, "src"), (TESTS, "tests")):
        for ruta in sorted(base.rglob("*.py")):
            if "__pycache__" in ruta.parts:
                continue
            arbol = _arbol_de_python(ruta)
            if arbol is None:
                continue
            for nodo in ast.walk(arbol):
                if not isinstance(nodo, ast.Call):
                    continue
                for clave in nodo.keywords:
                    if clave.arg != "extraction_method":
                        continue
                    valor = clave.value
                    if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                        conteo[f"{valor.value} ({etiqueta})"] = (
                            conteo.get(f"{valor.value} ({etiqueta})", 0) + 1
                        )
    return conteo


def _existe_origen_b6() -> bool:
    """El vocabulario cerrado del gate existe como Literal con sus VALORES.

    Y se busca en el VALOR, no en el nombre. Es la leccion de B5, que
    sufrio dos veces la misma Mutation: el medidor de B5 buscaba el
    vocabulario de `ChangeSubject` en el NOMBRE del tipo, y el nombre no
    enumera nada —los valores si—. Buscar `agent-inferred` en el nombre
    `AssertionOrigin` no lo encuentra porque el nombre declara el
    CONCEPTO y el Literal declara la LISTA. Un predicado que busca la
    lista donde solo hay un concepto devuelve falso sobre codigo
    correcto, que es el mismo fallo de WI-113 con la M4: un verificador
    que no puede ver la solucion no verifica que se alcance.

    El nombre importa poco y se acepta por comodidad (`agent_inferred`,
    la forma snake_case que el gate escribiria si fuera Python). Los
    valores son los que_portan el vocabulario cerrado.
    """

    def declara(nombre: str) -> bool:
        return nombre in ORIGENES_B6 or nombre.replace("-", "_") in ORIGENES_B6

    for ruta in _modulos():
        arbol = _arbol_de_python(ruta)
        if arbol is None:
            continue
        for nodo in ast.walk(arbol):
            # (a) Un Literal cerrado: se miran sus valores.
            if isinstance(nodo, ast.Subscript):
                valores = {
                    v.value
                    for v in ast.walk(nodo.slice)
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                }
                if valores & set(ORIGENES_B6):
                    return True
            # (b) Una clase o campo cuyo nombre sea un origen.
            nombres: tuple[str, ...] = ()
            if isinstance(nodo, ast.ClassDef):
                nombres = (nodo.name,)
            elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
                nombres = (nodo.target.id,)
            for nombre in nombres:
                if declara(nombre):
                    return True
                underscored = re.sub(r"(?<!^)(?=[A-Z])", "_", nombre).lower()
                if declara(underscored):
                    return True
    return False


def _metodos_tienen_vocabulario() -> bool:
    """`extraction_method` sigue siendo `str` libre.

    Si sigue siendo `str`, el campo no puede restringir lo que se escribe
    en el, y la DDL (`TEXT NOT NULL`) lo confirma: no hay CHECK que
    imponga vocabulario en ningun sitio.

    Un campo que NO se encuentra NO cuenta como cerrado. Devolver False
    porque no se encontro seria dar por cumplida una propiedad que nadie
    midio, y es la forma mas barata de tener un medidor verde: por eso
    aqui no se busca un str cualquiera, se busca el campo con su nombre,
    y si no esta se dice que no esta.
    """
    anotacion = _campo_de_claim("Claim", "extraction_method")
    if anotacion is None:
        return False
    return isinstance(anotacion, ast.Name) and anotacion.id == "str"


def _ddl_tiene_check() -> bool:
    """La DDL impone el vocabulario con un CHECK, no solo con NOT NULL.

    Sin CHECK, el vocabulario solo existe en Python y la base acepta
    cualquier texto. Un gate que dice «cada afirmacion distingue su
    origen» y no lo puede exigir en el sitio donde se escribe no se
    sostiene: basta un INSERT directo.
    """
    esquema = SRC / "platform" / "schema.py"
    if not esquema.exists():
        return False
    texto = esquema.read_text(encoding="utf-8").upper()
    if "EXTRACTION_METHOD" not in texto:
        return False
    # La PRIMERA version de este predicado buscaba "CHECK" en todo el
    # fichero y decia CERRADO: hay tres CHECK en schema.py y ninguno es de
    # esta columna —uno es de `link_kind` y otro de `promotion.status`—.
    # Un predicado que busca la convencion por el fichero entero encuentra
    # la convencion de ALGO, y el detalle decia «la DDL restringe el
    # vocabulario» sobre una columna que no restringe nada. Es el error de
    # WI-99 por el lado del DDL: enumerar donde buscar es mas facil que
    # comprobar. Se mide la RESTRICCION DE ESTA COLUMNA: la linea que
    # declara extraction_method tiene que traer su propio CHECK.
    for linea in texto.splitlines():
        if "EXTRACTION_METHOD" in linea and "TEXT" in linea:
            return "CHECK" in linea
    return False


def preguntas() -> tuple[Pregunta, ...]:
    conteo = _valores_de_extraction_method()
    metodos = sorted(k for k in conteo if k.endswith("(src)"))
    # MEDIDO, y en contra de lo que parece: NO hay ninguna escritura
    # explicita de `extraction_method` en `src/`. Los cuatro valores que
    # se ven con grep —`manual` x10, `regex_def` x4— estan TODOS en
    # `tests/`, y el unico valor que aparece en produccion es el DEFAULT
    # de la declaracion del dataclass. Eso refuerza P4 en vez de
    # contradecirlo: en el codigo que corre, este campo no lo escribe
    # nadie, luego el metodo de extraccion no es un eje que el sistema
    # mantenga — es un relleno. Un eje que nadie rellena no puede ser el
    # sitio donde vive el origen epistemico.
    detalle_metodos = ", ".join(metodos) if metodos else "NINGUNO — no hay escritura en src/"
    # Se mide UNA vez y se usa para el veredicto y para el detalle. Si se
    # llamara dos veces, el detalle podria describir una medicion y el
    # veredicto otra, que es exactamente el defecto que se acaba de
    # corregir en P2.
    metodo_es_str = _metodos_tienen_vocabulario()
    ddl_restringe = _ddl_tiene_check()

    return (
        Pregunta(
            clave="P1",
            enunciado="¿existe el origen epistemico como vocabulario cerrado?",
            abierta=not _existe_origen_b6(),
            en_alcance=True,
            detalle=(
                "no hay ningun campo ni tipo que nombre uno de los cuatro origenes del gate"
                if not _existe_origen_b6()
                else "el origen epistemico existe como nombre en el dominio"
            ),
        ),
        Pregunta(
            clave="P2",
            enunciado="¿el metodo de extraccion esta tipado o es str libre?",
            abierta=metodo_es_str,
            en_alcance=True,
            # El detalle se DEDUCE de la predicado, no se escribe a mano.
            # La primera version de esta pregunta decia «es str, sin
            # restringir» en las dos ramas, y como la predicado dio
            # False por un fallo de busqueda, el medidor imprimio
            # CERRADO seguido de un texto que describia el hueco. Un
            # verificador que dice «falso» sin decir «donde» es un
            # callejon, y uno que ademas se contradice es peor: el
            # detalle tiene que salir de la misma medida que el veredicto.
            detalle=(
                f"Claim.extraction_method sigue siendo str libre: acepta "
                f"cualquier texto. Valores escritos en src/: "
                f"{detalle_metodos}. El default es 'static_analysis'."
                if metodo_es_str
                else "Claim.extraction_method ya no es str: tiene tipo propio"
            ),
        ),
        Pregunta(
            clave="P3",
            enunciado="¿la base impone el vocabulario, o solo Python?",
            abierta=not ddl_restringe,
            en_alcance=True,
            detalle=(
                "extraction_method es TEXT NOT NULL y no hay CHECK: un INSERT "
                "directo escribe cualquier texto y el gate no lo ve"
                if not ddl_restringe
                else "la DDL restringe el vocabulario"
            ),
        ),
        Pregunta(
            clave="P4",
            enunciado="¿los dos ejes (metodo y origen) estan separados?",
            abierta=True,
            en_alcance=True,
            detalle=(
                "CONFUNDIDOS en un solo campo. Un valor no puede decir las dos "
                "cosas: 'regex_def' no dice quien afirma, y 'agent-inferred' no "
                "diria como se extrajo. Medido: 'manual' aparece 10 veces y las "
                "10 estan en tests/ — es comodidad de fixture, no un metodo que "
                "el sistema use, luego no es ni metodo ni origen: es un valor "
                "que solo existe para que los tests construyan Claims"
            ),
        ),
    )


def fuera_de_alcance() -> tuple[tuple[str, str], ...]:
    """Lo que este bloque NO cierra, y por que."""
    return (
        (
            "P5",
            "¿el proveedor real puebla conocimiento o lo consume?",
        ),
    )


def main() -> int:
    todas = preguntas()
    en_alcance = [p for p in todas if p.en_alcance]
    registradas = fuera_de_alcance()
    abiertas = [p for p in en_alcance if p.abierta]

    print("Gate B6 — origen epistemico de cada afirmacion del Knowledge Graph")
    print("=" * 78)
    print()
    for p in todas:
        marca = "ABIERTO" if p.abierta else "CERRADO"
        print(f"[{marca:>7}] {p.clave}  {p.enunciado}")
        print(f"          {p.detalle}")
        print()
    for clave, enunciado in registradas:
        print(f"[FUERA   ] {clave}  {enunciado}")
        print("          FUERA DEL ALCANCE de B6 y por eso NO baja el veredicto:")
        print(
            "          depende de una credencial de proveedor real, que este "
            "entorno no tiene. Se mide cuando la haya."
        )
        print()

    print("-" * 78)
    print(f"preguntas del gate B6 en alcance: {len(en_alcance)}")
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
