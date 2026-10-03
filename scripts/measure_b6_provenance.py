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


def _origen_esta_tipado() -> bool:
    """`Claim.assertion_origin` esta anotado, no es un str libre.

    La pregunta P2 cambio de objetivo al cerrar el bloque, y hay que
    decirlo en vez de reutilizar el predicado viejo: `extraction_method`
    SEGUIRA siendo `str` a proposito —describe la heuristica concreta y no
    tiene un vocabulario cerrado que—justificar——. Lo que el gate exige
    es que el ORIGEN este tipado, y se mide en su campo.

    Un campo que NO se encuentra NO cuenta como cerrado. Devolver False
    porque no se encontro seria dar por cumplida una propiedad que nadie
    midio, y es la forma mas barata de tener un medidor verde.
    """
    anotacion = _campo_de_claim("Claim", "assertion_origin")
    if anotacion is None:
        return False
    if isinstance(anotacion, ast.Constant) and isinstance(anotacion.value, str):
        # La anotacion llega como cadena por `from __future__ import
        # annotations`. Se compara contra los cuatro origenes; si no esta
        # en la lista, NO esta tipada con el vocabulario del gate.
        return anotacion.value in ORIGENES_B6 or (
            anotacion.value.replace("-", "_") in {o.replace("-", "_") for o in ORIGENES_B6}
        )
    return isinstance(anotacion, ast.Name)


def _ejes_estan_separados() -> bool:
    """El origen y el metodo son CAMPOS DISTINTOS de `Claim`.

    Separados, no confundidos. La version anterior de esta pregunta
    estaba escrita para dar ABIERTO siempre y medi una confusion de
    valores; la confusion real se mide sobre los CAMPOS, que es donde se
    puede arreglar: si `assertion_origin` y `extraction_method` son el
    mismo atributo, un valor no puede decir quien afirma y como se
    extrajo, y el gate no tiene donde escribir.
    """
    return (
        _campo_de_claim("Claim", "assertion_origin") is not None
        and _campo_de_claim("Claim", "extraction_method") is not None
    )


def _ddl_tiene_check() -> bool:
    """La DDL impone el vocabulario del ORIGEN con un CHECK en su columna.

    Sin CHECK, el vocabulario solo existe en Python y la base acepta
    cualquier texto. Un gate que dice «cada afirmacion distingue su
    origen» y no lo puede exigir en el sitio donde se escribe no se
    sostiene: basta un INSERT directo.

    Se mide la RESTRICCION DE ESTA COLUMNA, no «hay un CHECK en el
    fichero». La primera version hacia lo segundo y decia CERRADO sobre
    una columna sin restringir: hay tres CHECK en schema.py y uno es de
    `link_kind`, otro de `promotion.status`. Un predicado que busca la
    convencion por el fichero entero encuentra la convencion de ALGO.

    El CHECK de `assertion_origin` ocupa CUATRO lineas en el esquema, asi
    que no se busca «CHECK en la linea que declara la columna» —eso solo
    serviria para columnas de una linea— sino el bloque DDL completo de
    la tabla `claims`, que es donde vive la restriccion entera.
    """
    esquema = SRC / "platform" / "schema.py"
    if not esquema.exists():
        return False
    texto = esquema.read_text(encoding="utf-8")
    if "assertion_origin" not in texto:
        return False
    # El bloque de la tabla `claims`: desde su CREATE hasta su cierre.
    inicio = texto.find("CREATE TABLE IF NOT EXISTS claims")
    if inicio < 0:
        return False
    fin = texto.find(");", inicio)
    bloque = texto[inicio:fin] if fin > inicio else texto[inicio:]
    return "assertion_origin" in bloque and "CHECK" in bloque


def _valida_en_post_init() -> bool:
    """`__post_init__` rechaza un origen fuera del vocabulario.

    No basta con que el campo este anotado: con `from __future__ import
    annotations` la anotacion es una cadena que el runtime no comprueba,
    luego un valor inventado llega intacto al INSERT. Y si llega al
    INSERT, lo rechaza SQLite con un error que NO es del dominio — que es
    exactamente el hueco que WI-114 cerro por el otro lado de la misma
    frontera.

    Se busca por AST la COMPARACION, no la MENCION. La primera version
    hacia `ast.dump` del cuerpo y comprobaba que aparecieran las dos
    cadenas, y eso la hacia pasar sobre un `__post_init__` gutiado: la
    sonda M1 sustituye la comparacion por `if False:` y el `raise` de
    abajo —con su mensaje, que NOMBRA `ASSERTION_ORIGINS`— se queda
    intacto. Un predicado que busca la mencion encuentra la prosa del
    error, y la prosa del error no es la validacion. Es el error 32 de
    WI-113 aplicado a un predicado: el nombre de la convencion no es la
    convencion.

    Se exige una comparacion de pertenencia real: un `Compare` con
    `NotIn` (o `In` con la comparacion negada) donde el lado izquierdo es
    el atributo `assertion_origin` y el derecho el conjunto. Anyo asi, si
    alguien borra la comprobacion, el `raise` puede quedarse y el
    veredicto sigue bajando a rojo.
    """
    grafo = _arbol_de_python(SRC / "knowledge" / "graph.py")
    if grafo is None:
        return False
    for nodo in grafo.body:
        if not isinstance(nodo, ast.ClassDef) or nodo.name != "Claim":
            continue
        for item in nodo.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "__post_init__":
                continue
            for sub in ast.walk(item):
                if not isinstance(sub, ast.Compare):
                    continue
                if not any(isinstance(op, ast.NotIn) for op in sub.ops):
                    continue
                izq = sub.left
                der = sub.comparators[0] if sub.comparators else None
                if not isinstance(izq, ast.Attribute):
                    continue
                if izq.attr != "assertion_origin":
                    continue
                if isinstance(der, ast.Name) and der.id == "ASSERTION_ORIGINS":
                    return True
    return False


def preguntas() -> tuple[Pregunta, ...]:
    conteo = _valores_de_extraction_method()
    metodos = sorted(k for k in conteo if k.endswith("(src)"))
    detalle_metodos = ", ".join(metodos) if metodos else "NINGUNO — no hay escritura en src/"
    # Se mide UNA vez cada predicado y se usa para el veredicto Y para el
    # detalle. Si se llamara dos veces, el detalle podria describir una
    # medicion y el veredicto otra, que es el defecto que se corrigio en
    # P2 durante la primera version de este instrumento.
    origen_tipado = _origen_esta_tipado()
    ejes_separados = _ejes_estan_separados()
    ddl_restringe = _ddl_tiene_check()
    valida_en_post_init = _valida_en_post_init()

    return (
        Pregunta(
            clave="P1",
            enunciado="¿existe el origen epistemico como vocabulario cerrado?",
            abierta=not _existe_origen_b6(),
            en_alcance=True,
            detalle=(
                "no hay ningun Literal que nombre los cuatro origenes del gate"
                if not _existe_origen_b6()
                else "AssertionOrigin es un Literal cerrado con los cuatro "
                "valores del gate, y ASSERTION_ORIGINS se deriva de el"
            ),
        ),
        Pregunta(
            clave="P2",
            enunciado="¿el origen esta TIPADO, no en un str libre?",
            abierta=not origen_tipado,
            en_alcance=True,
            detalle=(
                "Claim.assertion_origin no esta anotado con el vocabulario"
                if not origen_tipado
                else "Claim.assertion_origin: AssertionOrigin, y el default es "
                "'observed' — el unico origen que no promete autoridad"
            ),
        ),
        Pregunta(
            clave="P3",
            enunciado="¿la base impone el vocabulario, o solo Python?",
            abierta=not ddl_restringe,
            en_alcance=True,
            detalle=(
                "assertion_origin no tiene CHECK en la DDL: un INSERT directo "
                "escribe cualquier texto y el gate no lo ve"
                if not ddl_restringe
                else "la columna lleva CHECK con los cuatro origenes, y la "
                "migracion de una base previa lo declara tambien"
            ),
        ),
        Pregunta(
            clave="P4",
            enunciado="¿quien AFIRMA se distingue de COMO se extrajo?",
            abierta=not ejes_separados,
            en_alcance=True,
            detalle=(
                f"CONFUNDIDOS: un solo campo no puede decir las dos cosas. "
                f"Medido antes de arreglarlo: los unicos valores escritos de "
                f"extraction_method estan todos en tests/ ({detalle_metodos}), "
                f"y en src/ solo existe su default 'static_analysis' — un eje "
                f"que nadie rellena no puede ser donde viva el origen."
                if not ejes_separados
                else "separados: extraction_method dice COMO (regex_def, "
                "static_analysis) y assertion_origin dice QUIEN (los cuatro "
                "orígenes). Se propaga por el INSERT, el SELECT, los mappers, "
                "el DTO, la promocion y la proyeccion de query"
            ),
        ),
        Pregunta(
            clave="P6",
            enunciado="¿un valor fuera del vocabulario se rechaza al construir?",
            abierta=not valida_en_post_init,
            en_alcance=True,
            detalle=(
                "Claim.__post_init__ no valida assertion_origin, luego un valor "
                "inventado pasa hasta la base —y la base lo rechaza con un error "
                "de SQLite, no con un error de dominio (WI-114: el error del "
                "adaptador no es del dominio)"
                if not valida_en_post_init
                else "__post_init__ valida contra ASSERTION_ORIGINS y lanza "
                "InvalidAssertionOriginError, que es del dominio y con code "
                "propio (sg_invalid_assertion_origin)"
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
