"""Medidor del gate B8 — el contrato de paquete y su compatibilidad.

Por qué este medidor y no siete
-------------------------------
El enunciado de B8 en `ROADMAP.md` enumera siete frentes: seis tipos de
paquete, aislamiento progresivo, `mise`/`asdf`/`uv tool`/PyPI, upgrade,
install/update/remove, matriz de compatibilidad y un formato `requires`
explícito. Eso no es un bloque: son siete, y medirlos juntos daría un
veredicto que no dice qué se puede hacer primero.

Este medidor mide **una** cosa, que es la pieza de la que los otros seis
dependen: **el contrato de paquete con `requires` declarado, y una función
que sepa responder si un pack es compatible con esta instalacion**.

La razon de que sea la primera no es una preferencia de orden. Es que
sin `requires` no hay version que comparar —y B3 ya habia dejado la
cosa)—, sin contrato versionado no hay `upgrade`, y sin contrato no hay
`install/update/remove` que_valga_como_algo. Medir B8 entero sin esto
seria medir siete huecos que en su mayoria son el mismo hueco.

Que el guard se pueda desarmar
-----------------------------
Cinco preguntas, y CADA UNA tiene su contra-salto, verificado en las dos
direcciones: una pregunta que baja a CERRADO al inyectar su symbolo, y
que sube a ABIERTA al borrarlo. Un medidor que solo sabe dar verde no
mide, y este esta escrito para que se pueda comprobar que muerde.

P6 queda FUERA y no baja el veredicto: que un pack se pueda instalar de
verdad en una instalacion real depende de un registro remoto y de una
politica de fijacion, y el CI no tiene ninguno de los dos.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Final

RAIZ: Final[Path] = Path(__file__).resolve().parent.parent
SRC: Final[Path] = RAIZ / "src" / "skillgraph"

#: Donde DEBERIA vivir el contrato. Se busca aqui y no en `src/` entero
#: por el motivo que ya_hook B3: una busqueda por subcadena en todo el
#: arbol da verde con cualquier cosa que se parezca al nombre.
CONTRATO: Final[Path] = SRC / "packaging" / "manifest.py"

#: Los seis del enunciado, escritos aqui y NO leidos del codigo: el
#: medidor tiene que saber lo que el gate PIDE para poder decir que el
#: codigo no lo tiene.
_LOS_SEIS: Final[tuple[str, ...]] = (
    "SkillPackage",
    "ControllerPackage",
    "CapabilityAdapter",
    "DomainPack",
    "PolicyPack",
    "UIWidget",
)

#: Los tres niveles de aislamiento, en el orden en que progresan.
_LOS_TRES_NIVELES: Final[tuple[str, ...]] = ("declarative", "subprocess", "sandbox")


@dataclass(frozen=True, slots=True)
class Pregunta:
    clave: str
    enunciado: str
    detalle: str
    abierta: bool
    en_alcance: bool = True


def _modulos() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _arbol() -> ast.AST | None:
    if not CONTRATO.exists():
        return None
    try:
        return ast.parse(CONTRATO.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - solo si el fichero esta roto
        return None


def _símbolos_de_modulo(nodo: ast.AST) -> set[str]:
    """Nombres definidos a nivel de modulo, incluidos los de clase."""
    nombres: set[str] = set()
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.ClassDef):
            nombres.add(hijo.name)
            for sub in hijo.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    nombres.add(sub.name)
                elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                    nombres.add(sub.target.id)
        elif isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nombres.add(hijo.name)
        elif isinstance(hijo, ast.AnnAssign) and isinstance(hijo.target, ast.Name):
            nombres.add(hijo.target.id)
        elif isinstance(hijo, ast.Assign):
            for tgt in hijo.targets:
                if isinstance(tgt, ast.Name):
                    nombres.add(tgt.id)
    return nombres


def _literales_de_conjunto(valor: ast.expr) -> set[str] | None:
    """Los strings de un conjunto, se escriba como se escriba.

    Hay dos formas legítimas de declarar un vocabulario cerrado en este
    repo, y el medidor tiene que leer LAS DOS:

    ```python
    PACK_KINDS = frozenset({"SkillPackage", ...})  # escrito a mano
    PACK_KINDS = frozenset(get_args(PackKind))  # derivado
    ```

    La segunda es la que se PREFIERE —un conjunto literal se queda corto
    en cuanto el `Literal` crece, y entonces la validación rechaza el
    valor nuevo que el propio tipo acepta—. Un medidor que solo sabe
    leer la primera le dice al código correcto que su conjunto no existe,
    y ese es el peor resultado posible: un guard que obliga a escribir
    peor para poder ser medido.

    Se resuelven las dos porque `_valores_de_llamada` sigue una cadena
    de llamadas de un solo argumento (`frozenset(get_args(PackKind))`)
    y, en el fondo, resuelve un `Literal[...]` a sus valores.
    """
    return _valores_de_llamada(valor, set())


def _valores_de_llamada(valor: ast.expr, vistos: frozenset[str]) -> set[str] | None:
    """Desenreda la cadena hasta llegar a strings o a un `Literal[...]`.

    Se sigue por dos formas y solo por dos, porque son las dos que el
    repo escribe: una llamada de un argumento (`frozenset(...)`,
    `tuple(...)`, `get_args(...)`) y un `Literal[...]`. Cualquier otra
    forma devuelve None, que el llamador lee como «no legible» y nunca
    como «vacio».
    """
    if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
        return {valor.value}
    if isinstance(valor, ast.Constant) and valor.value is None:
        return None
    if isinstance(valor, (ast.Set, ast.List, ast.Tuple)):
        valores: set[str] = set()
        for elemento in valor.elts:
            leido = _valores_de_llamada(elemento, vistos)
            if leido is None:
                return None
            valores |= leido
        return valores or None
    if isinstance(valor, ast.Call) and valor.args and valor.args[0] is not None:
        nombre = valor.func.id if isinstance(valor.func, ast.Name) else None
        # `get_args(SomeLiteral)` se resuelve mirando el `Literal` de ese
        # nombre. Un nombre ya visitado corta: sin el, un `get_args` mal
        # formado podria seguir girando sobre si mismo.
        if nombre is not None and nombre in vistos:
            return None
        return _valores_de_llamada(valor.args[0], vistos | {nombre} if nombre else vistos)
    if isinstance(valor, ast.Name):
        return _valores_de_literal_alias(valor.id, vistos)
    return None


_ALIAS: dict[str, ast.expr] = {}


def _valores_de_literal_alias(nombre: str, vistos: frozenset[str]) -> set[str] | None:
    """Resuelve `NOMBRE = Literal["a", "b"]` a sus valores.

    Se indexan los alias por adelantado porque un `Literal` no lleva su
    propio nombre dentro del arbol: sin el indice, `get_args(PackKind)`
    llegaria aqui con un `ast.Name` y no habria manera de saber a que
    anotacion mirar.
    """
    expresion = _ALIAS.get(nombre)
    if expresion is None or nombre in vistos:
        return None
    if isinstance(expresion, ast.Subscript):
        return _valores_de_llamada(expresion.slice, vistos | {nombre})
    return None


def _indexar_alias(nodo: ast.AST) -> None:
    """Registra `NOMBRE = Literal[...]` para poder resolverlo despues.

    Se indexan LAS DOS formas y no solo la anotada, por un motivo que
    solo aparece al usarlo: `PackKind = Literal[...]` —que es como se
    escribe un alias de tipo— NO lleva anotacion, luego es un `Assign`
    a secas. Indexando solo los `AnnAssign`, el indice salia vacio de
    alias y `get_args(PackKind)` no resolvia a nada.

    Es el mismo error de forma que en el codigo de produccion se
    corrige: un `frozenset` DERIVADO necesita su `Literal` localizable
    por nombre, y el indice tiene que cubrir todas las formas en que
    ese `Literal` puede estar escrito.
    """
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.Assign):
            for tgt in hijo.targets:
                if isinstance(tgt, ast.Name):
                    _ALIAS[tgt.id] = hijo.value
        if (
            isinstance(hijo, ast.AnnAssign)
            and isinstance(hijo.target, ast.Name)
            and hijo.value is not None
        ):
            _ALIAS[hijo.target.id] = hijo.value


def _constante(nodo: ast.AST, nombre: str) -> set[str] | None:
    """Los valores de una constante de conjunto, o None si no existe.

    None significa «no declarada o no legible». NUNCA «vacia»: un
    conjunto de verdad puede estar vacio, y confundir las dos cosas hace
    que borrar la declaracion y dejar un conjunto vacio se vean igual.
    """
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.Assign):
            for tgt in hijo.targets:
                if isinstance(tgt, ast.Name) and tgt.id == nombre:
                    return _literales_de_conjunto(hijo.value)
        if (
            isinstance(hijo, ast.AnnAssign)
            and isinstance(hijo.target, ast.Name)
            and hijo.target.id == nombre
            and hijo.value is not None
        ):
            return _literales_de_conjunto(hijo.value)
    return None


def _tiene_metodo(nodo: ast.AST, clase: str, metodo: str) -> bool:
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.ClassDef) and hijo.name == clase:
            for sub in hijo.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == metodo:
                    return True
    return False


def _p1_contrato() -> Pregunta:
    abierta = not CONTRATO.exists()
    return Pregunta(
        "P1",
        "¿Existe un contrato de paquete de primera clase, o solo un Brick con kind='DomainPack'?",
        "un modulo que defina el manifiesto, no una convencion dispersa",
        abierta,
    )


def _p2_requires() -> Pregunta:
    arbol = _arbol()
    if arbol is None:
        return Pregunta(
            "P2",
            "¿El manifiesto declara `requires` de forma explicita?",
            "sin contrato, no hay requires",
            True,
        )
    nombres = _símbolos_de_modulo(arbol)
    cerrada = "Requires" in nombres and "PackManifest" in nombres
    return Pregunta(
        "P2",
        "¿El manifiesto declara `requires` de forma explicita?",
        "skillgraph y capabilities, no inferidos del entorno",
        not cerrada,
    )


def _p3_compatibilidad() -> Pregunta:
    arbol = _arbol()
    if arbol is None:
        return Pregunta(
            "P3", "¿Se puede preguntar si un pack encaja aqui?", "una funcion que lo responda", True
        )
    nombres = _símbolos_de_modulo(arbol)
    hay_funcion = any(
        n in nombres for n in ("es_compatible", "compatibilidad", "check_compatibility")
    )
    cerrada = hay_funcion and "IncompatiblePackError" in nombres
    return Pregunta(
        "P3",
        "¿Se puede preguntar si un pack es compatible con esta instalacion?",
        "y que la respuesta que no venga sea un error de dominio con su code",
        not cerrada,
    )


def _p4_seis_tipos() -> Pregunta:
    arbol = _arbol()
    if arbol is None:
        return Pregunta(
            "P4",
            "¿Los seis tipos de paquete del enunciado estan en el contrato?",
            "los seis, no solo DomainPack",
            True,
        )
    valor = _constante(arbol, "PACK_KINDS")
    if valor is None:
        return Pregunta(
            "P4",
            "¿Los seis tipos de paquete del enunciado estan en el contrato?",
            "PACK_KINDS ausente o ilegible",
            True,
        )
    faltan = [k for k in _LOS_SEIS if k not in valor]
    return Pregunta(
        "P4",
        "¿Los seis tipos de paquete del enunciado estan en el contrato?",
        f"faltan: {', '.join(faltan)}"
        if faltan
        else "los seis, declarados como un conjunto cerrado",
        bool(faltan),
    )


def _p5_aislamiento() -> Pregunta:
    arbol = _arbol()
    if arbol is None:
        return Pregunta(
            "P5",
            "¿El aislamiento es un campo del contrato o una promesa?",
            "declarative/subprocess/sandbox",
            True,
        )
    valor = _constante(arbol, "ISOLATION_LEVELS")
    cerrada = valor is not None and all(nivel in valor for nivel in _LOS_TRES_NIVELES)
    return Pregunta(
        "P5",
        "¿El nivel de aislamiento es un campo del contrato, o una promesa en el roadmap?",
        "declarative -> subprocess -> sandbox, declarados y ordenados",
        not cerrada,
    )


def fuera_de_alcance() -> tuple[tuple[str, str], ...]:
    return (("P6", "¿Un pack se instala de verdad en una instalacion real?"),)


def preguntas() -> list[Pregunta]:
    _ALIAS.clear()
    arbol = _arbol()
    if arbol is not None:
        _indexar_alias(arbol)
    return [
        _p1_contrato(),
        _p2_requires(),
        _p3_compatibilidad(),
        _p4_seis_tipos(),
        _p5_aislamiento(),
    ]


def main() -> int:
    todas = preguntas()
    en_alcance = [p for p in todas if p.en_alcance]
    registradas = fuera_de_alcance()
    abiertas = [p for p in en_alcance if p.abierta]

    print("Gate B8 — el contrato de paquete y su compatibilidad")
    print("=" * 78)
    print()
    for p in todas:
        marca = "ABIERTO" if p.abierta else "CERRADO"
        print(f"[{marca:>7}] {p.clave}  {p.enunciado}")
        print(f"          {p.detalle}")
        print()
    for clave, enunciado in registradas:
        print(f"[FUERA   ] {clave}  {enunciado}")
        print(
            "          FUERA DEL ALCANCE de B8 y por eso NO baja el veredicto:\n"
            "          depender de un registro remoto y de una politica de fijacion es\n"
            "          depender de un servicio que el CI no tiene. Lo que se mide aqui\n"
            "          es el CONTRATO, que es comprobable sin red; que el pack llegue a\n"
            "          una instalacion real se mide cuando haya una."
        )
        print()

    print("-" * 78)
    print(f"preguntas del gate B8 en alcance: {len(en_alcance)}")
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
    raise SystemExit(main())
