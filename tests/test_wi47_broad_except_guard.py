"""Guarda: ningun `except Exception` sin justificacion documentada.

AGENTS.md 11.14.4 prohibe `except Exception` sin re-raise ni registro.
La regla existe, pero nada la hacia cumplir: los defectos que
WI-46 y WI-47 encontraron son exactamente casos donde nadie miraba.

Un `except Exception` ancho NO es siempre un defecto. Es legitimo en
tres situaciones concretas, y todas requieren el mismo tratamiento:
un comentario que explique POR QUE se captura todo.

  1. Frontera con codigo de terceros (un `Protocol` como
     `AgentAdapter`, un `apply_fn` que inyecta el caller). Ahi no
     puedes enumerar las excepciones porque no son tuyas.
  2. Conversion inmediata a un error de dominio tipado.
  3. Best-effort documentado, donde perder el dato es el
     comportamiento correcto y esta escrito que lo es.

Lo que esta PROHIBIDO es el patron que los dos workitems encontraron:
capturar `Exception` y decidir el significado mirando `str(exc)`.
Eso no es una frontera ni una conversion, es adivinar por el texto
del mensaje, y convierte cualquier error ajeno en un diagnostico
falso. Esta guarda lo prohibe por construccion.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "skillgraph"

# `except Exception` cuya EXPRESION DE MENSAJ se inspecciona para
# decidir que hacer. Es el patron prohibido.
MESSAGE_SNIFFING_CALLS = frozenset(
    {
        "str",
        "repr",
        "format",
        "format_exc",
    }
)

# Leer la exception por atributo en vez de por tipo.
_EXC_ATTRS = frozenset({"args", "msg", "message", "strerror", "errno"})

# Registrar el fallo cuenta como no tragarselo.
_LOGGING_CALLS = frozenset(
    {
        "warning",
        "warn",
        "error",
        "exception",
        "critical",
        "info",
        "debug",
        "log",
        "logger",
        "print",
    }
)


def _iter_handlers(path: Path) -> list[ast.ExceptHandler]:
    tree = ast.parse(_read(path), filename=str(path))
    return [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """True si el handler captura Exception o BaseException entero."""
    if handler.type is None:  # `except:` desnudo
        return True
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for t in types:
        name = t.id if isinstance(t, ast.Name) else getattr(t, "attr", "")
        if name in {"Exception", "BaseException"}:
            return True
    return False


def _sniffs_message(handler: ast.ExceptHandler) -> bool:
    """True si el cuerpo decide el significado leyendo el mensaje.

    Se recorre el cuerpo del handler buscando llamadas a `str()` /
    `repr()` etc. NO se baja a las funciones anidadas, porque ahi la
    inspeccion del mensaje es legitima.

    Solo aplica a handlers ANCHOS. Un `except sqlite3.IntegrityError`
    que mira el texto ya ha identificado el tipo: solo desempata
    DENTRO de una familia de errores, que es el uso legitimo de SQLite
    (no distingue tablas en el mensaje).
    """
    if not _is_broad(handler):
        return False
    stack: list[ast.stmt] = list(handler.body)
    while stack:
        node = stack.pop()
        # No se inspecciona dentro de defs anidadas.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            # `str(exc)`, `repr(err)`, `format(exc)`: todos convierten
            # la excepcion en texto para decidir que hacer. No se exige
            # que el argumento este vacio: `str(exc)` SI lleva.
            if name in MESSAGE_SNIFFING_CALLS:
                return True
        # `exc.args`, `exc.msg`, `e.errno`: leer la excepcion por
        # atributo en vez de por tipo es la misma enfermedad que
        # leerla por su texto, solo que con otra API.
        elif isinstance(node, ast.Attribute) and node.attr in _EXC_ATTRS:
            return True
        stack.extend(ast.iter_child_nodes(node))
    return False


def _has_rationale(handler: ast.ExceptHandler, lines: list[str]) -> bool:
    """El handler tiene un comentario que explica el por que.

    Se admite el comentario justo DESPUES de la linea del `except`
    (donde lo escribe la gente de forma natural, porque el bloque
    empieza en la linea siguiente) y tambien ARRIBA, donde se explica
    el por que de la operacion entera.

    NOTA sobre por que esto NO es trivial: sin esta guarda, la regla
    de AGENTS.md 11.14.4 sobre `except Exception` no la cumplia nadie.
    """
    # 1) El "por que" va encima del `try`, no del `except`: es ahi
    #    donde se explica por que la operacion entera captura
    #    Exception. Se sube saltando lineas en blanco y `try:`,
    #    parando en cualquier otra sentencia.
    lineno = handler.lineno - 1
    hops = 0
    while lineno >= 0 and hops < 10:
        hops += 1
        stripped = lines[lineno].strip()
        if stripped.startswith("#") and len(stripped) > 2:
            return True
        if not stripped or stripped in {"try:", "else:", "finally:", ")"}:
            lineno -= 1
            continue
        break

    # 2) El hueco entre la linea del `except` y la primera sentencia
    #    del cuerpo: es donde se escribe la justificacion del ancho.
    first_stmt = handler.body[0].lineno
    for lineno in range(handler.lineno, min(first_stmt, handler.lineno + 6)):
        if lineno < 0 or lineno >= len(lines):
            continue
        stripped = lines[lineno].strip()
        if stripped.startswith("#") and len(stripped) > 2:
            return True
    return False


def _silently_continues(handler: ast.ExceptHandler) -> bool:
    """El cuerpo descarta el fallo sin re-raise, sin registrar y sin valor.

    Esta es la forma DESTRUCTIVA de `except Exception`: no el ancho en
    si (que a veces es correcto en una frontera), sino que el error
    desaparece y el codigo sigue como si nada. El resultado es que un
    fallo de I/O o un bug se convierte en un dato incompleto, y nadie
    se entera porque no hay error, solo ausencia.

    Se marca como offenders cuando el cuerpo es un `pass`, un `...`,
    un `continue`, o un `return` de un valor por defecto, sin que
    antes haya un `raise` o una llamada de registro.
    """
    body = handler.body
    # Un re-raise o un registro legitimo invalida la sospecha.
    for node in ast.walk(ast.Module(body=list(body), type_ignores=[])):
        if isinstance(node, ast.Raise):
            return False
        if isinstance(node, ast.Call):
            name = (
                node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            )
            if name in _LOGGING_CALLS:
                return False

    first = body[0]
    if isinstance(first, (ast.Pass, ast.Continue)):
        return True
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return first.value.value is Ellipsis
    # `return []`, `return {}`, `return None`, `return ""` sin haber
    # Registered nada: el fallo se convierte en "no habia nada".
    if isinstance(first, ast.Return):
        return first.value is None or _is_empty_literal(first.value)
    return False


def _is_empty_literal(node: ast.expr | None) -> bool:
    """`[]`, `{}`, `()`, `""`, `set()`, `False` — el valor de "nada"."""
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return node.value in ("", b"", (), frozenset(), False) or node.value in ([], {})
    if isinstance(node, (ast.List, ast.Tuple, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        return name in {"list", "dict", "set", "tuple"} and not node.args
    return False


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py"))


ALL_SOURCES = _sources()


@pytest.mark.parametrize("path", ALL_SOURCES, ids=lambda p: p.name)
def test_no_message_sniffing_to_classify_errors(path: Path) -> None:
    """Prohibido decidir el significado de una exception por su texto.

    `except Exception` + `if "FOREIGN KEY" in str(exc)` convierte
    cualquier error que contenga esa frase (un CHECK, un trigger, un
    error de dominio que la mencione) en un diagnostico de dominio
    equivocado. Se discrimina por TIPO, y el texto solo desempata
    DENTRO de un tipo ya identificado.
    """
    offenders = [
        f"{path.name}:{handler.lineno}"
        for handler in _iter_handlers(path)
        if _sniffs_message(handler)
    ]
    assert not offenders, (
        "exception clasificada por el texto del mensaje, no por su tipo: " + ", ".join(offenders)
    )


@pytest.mark.parametrize("path", ALL_SOURCES, ids=lambda p: p.name)
def test_broad_except_does_not_silently_discard(path: Path) -> None:
    """`except Exception` no puede terminar en silencio.

    Un ancho de exception es legitimo en una frontera con codigo de
    terceros, siempre que el fallo se convierta en algo: un re-raise,
    un error de dominio, o un registro. Lo que NUNCA debe pasar es
    capturar Exception y seguir como si nada (`pass`, `continue`, o
    `return []`): ahi un error de I/O o un bug se transforma en un
    dato incompleto, sin error visible que lo delate.

    Este es el patron exacto de los defectos de WI-46 (el traversal de
    claims) y WI-47 (los branches de context): ambos devolvian "vacio"
    ante cualquier fallo, y "vacio" es indistinguible de "no hay datos".
    """
    offenders = [
        f"{path.name}:{handler.lineno}"
        for handler in _iter_handlers(path)
        if _is_broad(handler) and _silently_continues(handler)
    ]
    assert not offenders, (
        "except Exception que descarta el fallo en silencio (pass / continue / "
        "return de valor vacio, sin raise ni registro): " + ", ".join(offenders)
    )


@pytest.mark.parametrize("path", ALL_SOURCES, ids=lambda p: p.name)
def test_broad_except_is_documented(path: Path) -> None:
    """Todo `except Exception` lleva un comentario que explica el porque.

    Esta guarda es la mas debil de las tres y a proposito se queda
    como advertencia de estilo, NO como garantia: se falsifico y se
    vio que un comentario cerca satisface la regla aunque el `except`
    siga siendo `Exception`. Lo que de verdad protege el codigo son
    los otros dos tests (sin message-sniffing, sin descarte silencioso).
    """
    undocumented: list[str] = []
    lines = _read(path).splitlines()
    for handler in _iter_handlers(path):
        if not _is_broad(handler):
            continue
        if not _has_rationale(handler, lines):
            undocumented.append(f"{path.name}:{handler.lineno}")
    assert not undocumented, (
        "except Exception sin comentario que justifique el ancho: " + ", ".join(undocumented)
    )
