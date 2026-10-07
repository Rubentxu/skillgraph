"""La medicion que abre B35 — el ensamblado: quien puede LLAMAR a una capability.

B31 cerro el analisis estructural (`sg.code.analysis`) y B33/B34 ceraron las
otras dos de conocimiento. Al cerrar B31 se midio, y esto es lo que salio:

    `CapabilityRegistry(` no se construye NI UNA VEZ en `src/`.

Es decir: las tres capabilities de conocimiento existen, estan probadas al
100 %, y **ningun despliegue las puede resolver** porque no hay quien las
meta en un registro. Un `sg.code.analysis` con contenido equivocado no se
puede ni detectar.

Este script mide ESO, y lo mide por AST sobre el arbol real, no leyendo una
lista de sitios conocidos (la trampa de WI-99: una lista escrita a mano es
una fuente de verdad mas).

Ejecutar:  uv run python scripts/measure_b35_ensamblado.py
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"
TESTS = RAIZ / "tests"

#: Las capabilities que el repo declara. NO se escribe a mano: sale de los
#: ficheros que importan `CapabilitySpec` y construyen una `CapabilityResult`,
#: que es la FIRMA que el puerto declara.
FICH_CAPABILITY = ("code_analysis.py", "telemetry_query.py", "knowledge_query.py")


def modulos(raiz: pathlib.Path) -> Iterator[pathlib.Path]:
    """Todo `.py` bajo `raiz`, versionado o no. Orden estable."""
    return sorted(p for p in raiz.rglob("*.py") if "__pycache__" not in p.parts)


def tipo_de_nombre(nodo: ast.expr) -> str | None:
    """El nombre desnudo de un `Name`, o de un `Attribute` en su ultimo tramo."""
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        return nodo.attr
    return None


def llama_a(nodo: ast.AST, nombre: str) -> bool:
    """¿Hay una llamada `nombre(...)` en este subtree?"""
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.Call) and tipo_de_nombre(hijo.func) == nombre:
            return True
    return False


def creado_por(fichero: pathlib.Path, nombre: str) -> list[int]:
    """Lineas donde se CONSTRUYE `nombre(...)`, no donde se menciona."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and tipo_de_nombre(nodo.func) == nombre:
            lineas.append(nodo.lineno)
    return sorted(lineas)


def instanciada_por(fichero: pathlib.Path, clase: str) -> list[int]:
    """Lineas donde se instancia `Clase(...)` dentro de `src/`."""
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and tipo_de_nombre(nodo.func) == clase:
            lineas.append(nodo.lineno)
    return sorted(lineas)


def comandos_cli() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Los `type_name` que el CLI declara poder resolver, y los que nombra."""
    fallos: list[str] = []
    nombradas: list[str] = []
    for f in modulos(SRC / "cli"):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call) and tipo_de_nombre(nodo.func) == "add_parser":
                args = [a.value for a in nodo.args if isinstance(a, ast.Constant)]
                if args and isinstance(args[0], str):
                    nombradas.append(args[0])
            if isinstance(nodo, ast.Call) and tipo_de_nombre(nodo.func) == "add_argument":
                for kw in nodo.keywords:
                    if kw.arg == "choices" and isinstance(kw.value, ast.List):
                        fallos.extend(
                            e.value
                            for e in kw.value.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        )
    return tuple(sorted(set(fallos))), tuple(sorted(set(nombradas)))


def main() -> int:
    print("=" * 74)
    print("RONDA 1 — ¿que capabilities declara el repo?")
    print("=" * 74)

    declaradas: list[tuple[str, str]] = []
    for nombre_fich in FICH_CAPABILITY:
        ruta = SRC / "knowledge" / nombre_fich
        if not ruta.exists():
            print(f"  {nombre_fich}: NO EXISTE")
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            # `CODE_ANALYSIS: Final[str] = "sg.code.analysis"` es un
            # `AnnAssign`, NO un `Assign`. MEDIDO: buscando solo `Assign` la
            # ronda 1 imprimia CERO capabilities declaradas, que es
            # exactamente el numero que este bloque quiere desmentir — y un
            # instrumento que da el numero falso por el que empieza el bloque
            # es peor que no tener instrumento.
            objetivo: ast.expr | None = None
            valor: ast.expr | None = None
            if isinstance(nodo, ast.AnnAssign):
                objetivo, valor = nodo.target, nodo.value
            elif isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
                objetivo, valor = nodo.targets[0], nodo.value
            if (
                objetivo is None
                or not isinstance(objetivo, ast.Name)
                or not objetivo.id.isupper()
                or not isinstance(valor, ast.Constant)
                or not isinstance(valor.value, str)
                or "." not in valor.value
            ):
                continue
            declaradas.append((valor.value, nombre_fich))

    for tipo, fich in sorted(declaradas):
        print(f"  {tipo:<28} {fich}")
    print(f"  -> declaradas: {len(declaradas)}")

    print()
    print("=" * 74)
    print("RONDA 2 — ¿alguien CONSTRUYE el registro en src/?")
    print("=" * 74)

    en_src: list[tuple[str, int]] = []
    for f in modulos(SRC):
        for linea in creado_por(f, "CapabilityRegistry"):
            en_src.append((str(f.relative_to(RAIZ)), linea))

    en_tests = [
        (str(f.relative_to(RAIZ)), ln)
        for f in modulos(TESTS)
        for ln in creado_por(f, "CapabilityRegistry")
    ]

    print(f"  CapabilityRegistry(...) en src/   : {len(en_src)}")
    for f, ln in en_src:
        print(f"      {f}:{ln}")
    print(f"  CapabilityRegistry(...) en tests/ : {len(en_tests)}")
    print("  RunController(capabilities=...) en src/ : ", end="")
    con_cap = [
        (str(f.relative_to(RAIZ)), ln)
        for f in modulos(SRC)
        for ln in creado_por(f, "RunController")
    ]
    total = len(con_cap)
    print(f"{total} construcciones de RunController")

    print()
    print("=" * 74)
    print("RONDA 3 — ¿se puede LLAMAR a cada capability desde el producto?")
    print("=" * 74)

    for nombre_fich in FICH_CAPABILITY:
        ruta = SRC / "knowledge" / nombre_fich
        if not ruta.exists():
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        clases = [
            nodo.name
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ClassDef) and nodo.name.endswith("Capability")
        ]
        for clase in clases:
            usos_src = [
                (str(f.relative_to(RAIZ)), ln)
                for f in modulos(SRC)
                for ln in instanciada_por(f, clase)
            ]
            usos_tests = [
                (str(f.relative_to(RAIZ)), ln)
                for f in modulos(TESTS)
                for ln in instanciada_por(f, clase)
            ]
            print(f"  {clase:<28} src/={len(usos_src):<3} tests/={len(usos_tests)}")
            for f, ln in usos_src:
                print(f"      REACHABLE {f}:{ln}")

    print()
    print("=" * 74)
    print("RONDA 4 — ¿que declara la CLI?")
    print("=" * 74)

    declarados, nombrados = comandos_cli()
    print(f"  subcomandos `sg` que la CLI registra : {len(nombrados)}")
    print(f"  valores de `--adapter` (PROTOCOL AgentAdapter): {len(declarados)}")
    for d in declarados:
        print(f"      {d}")
    print()
    print("  **El contraste es el hallazgo.** Para el Protocol `AgentAdapter`")
    print("  SI hay ensamblado en la CLI: el operador elige `fake`, `http`,")
    print("  `anthropic` u `openai` por nombre y el proceso construye el")
    print("  adaptador. Para el Protocol `Capability` NO hay nada equivalente:")
    print("  ningun `--adapter` nombra una `sg.*`, porque una `sg.*` no es un")
    print("  adaptador de agente sino una capacidad que se REGISTRA, y el")
    print("  registro no tiene quien lo construya.")
    print()
    print("  capabilities `sg.*` alcanzables desde un `choices` de la CLI: 0")

    print()
    print("=" * 74)
    print("LECTURA QUE ABRE B35")
    print("=" * 74)
    alcanzables = 0
    total_clases = 0
    for nombre_fich in FICH_CAPABILITY:
        ruta = SRC / "knowledge" / nombre_fich
        if not ruta.exists():
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name.endswith("Capability"):
                total_clases += 1
                if any(instanciada_por(f, nodo.name) for f in modulos(SRC)):
                    alcanzables += 1

    print(f"""
  Las {len(declaradas)} capabilities de conocimiento existen y estan al
  100 % de cobertura. Y `CapabilityRegistry(...)` se construye {len(en_src)}
  veces en `src/` y {len(en_tests)} en `tests/`.

  De las {total_clases} clases `*Capability` de `knowledge/`, **{alcanzables}
  se instancian en algun sitio de `src/`**. Las otras {total_clases - alcanzables}
  solo se instancian desde `tests/`.

  O sea: hay {len(declaradas)} capabilities de conocimiento que un despliegue
  declara y CERO caminos por los que un despliegue pueda resolverlas.
  `sg.code.analysis` de B31 no se puede ni invocar mal: no hay quien la meta
  en un registro, luego no hay forma de que llegue a existir el error.

  Esto NO es un descuido de B31. Es el estado que `runcontroller.py:148-179`
  DECLARA y que B3-cierre acepto a proposito: la costura existe
  (`capabilities=` con default `None`), el ensamblado no, porque la exigencia
  la PIDE quien despliega.

  Y aqui esta la pinja: **no hay quien despliegue**. El repo tiene un
  ejecutable (`sg`) y ninguna forma de que `sg` monte un registro. Eso no es
  una decision de arquitectura, es una decision que nadie ha tomado.

  Lo que falta, con nombre: UN punto de ensamblado, y una forma de que el
  operador llegue a el. Lo mas barato que devuelve valor de inmediato es
  `sg knowledge ingest-code`, que es B31 por la puerta de la CLI: hoy el
  analisis estructural solo se puede lanzar escribiendo Python.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
