#!/usr/bin/env python3
"""R1 — el ratchet arquitectónico, y **sale distinto de cero**.

QUÉ ES, Y LA DIFERENCIA CON UN AUDIT
====================================

Un **audit** informa: dice «hay 2 módulos de más de 800 líneas» y sale 0.
Un **ratchet** cierra: dice lo mismo y sale **distinto de cero**, de modo
que la construcción falla.

La diferencia es toda la propuesta de R1: *una propiedad que llegó a cero
no vuelve a convertirse en advertencia*. Sin código de salida distinto de
cero, «god modules > 800 = 0» es una frase.

# LAS CINCO PROPIEDADES, Y POR QUÉ ESTAS CINCO

    1. god modules > 800                = 0
    2. complejidad publica cc >= 20     = 0
    3. SQL en el dominio                = 0
    4. dominio -> platform (no ports)  = 0
    5. referencias normativas rotas    = 0

**POR QUÉ EL UMBRAL DE 800 Y NO OTRO.** Es el que ya usan la auditoría de
deuda y los guardas de `docs/`; cambiarlo aquí sería inventar una métrica
nueva para un gate nuevo, y un gate con métrica inventada mide la métrica.

# LAS TRAMPAS, Y LAS DOS SON DE DOCSTRINGS

Este script cuenta **código, no prosa**, y en los dos casos hay razón:

1. **SQL en el dominio.** `grep -r sqlite3 src/skillgraph/knowledge/`
   marca cuatro ficheros, y **tres solo lo nombran en un docstring**
   (`errors.py`, `engine.py`, `runcontroller.py`). Un gate que señale la
   mitad de las cosas correctas entrena a ignorar el gate.
2. **Referencias normativas.** `blueprint-v1` es un **directorio** con 12
   documentos y vive en `external/`, fuera de git **por decisión del
   repo**. Buscar solo ficheros marca rota la referencia más importante
   del repositorio.

# POR QUÉ SALTA UN MÓDULO COMPLEJO ENTERO Y NO UNA PORCION

El umbral es de módulo, no de función. Un fichero de 900 líneas con cinco
funciones de 30 es legible; uno de 900 con una de 850 no lo es. Cortar por
líneas produce troceados que no son unidades, que es la razón por la que el
partido de `knowledge_repository.py` de R1 es **por responsabilidad** y no
por tamaño.

# USO

    python scripts/check_architecture_ratchet.py [--raiz DIR]

Sale 0 si las cinco propiedades se cumplen, y distinto de cero nombrando
cada una que no.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

MAX_LOC = 800
CC_MAX = 20

DOMINIO = ("knowledge", "core", "runtime", "handoff", "agent", "workflow", "dsl")

#: Nombres quecedentan «hablar SQL» cuando aparecen en CODIGO.
METODOS_SQL = frozenset({"execute", "executemany", "executescript"})


@dataclass(frozen=True, slots=True)
class Incumplimiento:
    """Una propiedad que no se cumple, con el dónde."""

    propiedad: str
    donde: str

    def __str__(self) -> str:
        return f"{self.propiedad}: {self.donde}"


def _modulos(raiz: Path) -> list[Path]:
    base = raiz / "src" / "skillgraph"
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.rglob("*.py") if "__pycache__" not in p.parts and not p.name.startswith("_")
    )


def _de_dominio(raiz: Path) -> list[Path]:
    salida: list[Path] = []
    for paquete in DOMINIO:
        base = raiz / "src" / "skillgraph" / paquete
        if not base.is_dir():
            continue
        salida.extend(
            p
            for p in base.rglob("*.py")
            if "__pycache__" not in p.parts and not p.name.startswith("_")
        )
    return sorted(salida)


def _arbol(ruta: Path) -> ast.Module | None:
    try:
        return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    except SyntaxError:
        return None


# ---------------------------------------------------------------------------
# 1. god modules
# ---------------------------------------------------------------------------


def incumple_tamano(raiz: Path) -> list[Incumplimiento]:
    fuera: list[Incumplimiento] = []
    for ruta in _modulos(raiz):
        loc = len(ruta.read_text(encoding="utf-8").splitlines())
        if loc > MAX_LOC:
            fuera.append(Incumplimiento("god module", f"{ruta.relative_to(raiz)} ({loc} LoC)"))
    return fuera


# ---------------------------------------------------------------------------
# 2. complejidad publica
# ---------------------------------------------------------------------------


def _cc(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    cc = 1
    for hijo in ast.walk(nodo):
        if isinstance(hijo, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            cc += 1
        elif isinstance(hijo, ast.BoolOp):
            cc += len(hijo.values) - 1
        elif isinstance(hijo, ast.IfExp):
            cc += 1
        elif isinstance(hijo, ast.comprehension):
            cc += 1 + len(hijo.ifs)
        elif isinstance(hijo, ast.Assert):
            cc += 1
        elif isinstance(hijo, ast.Match):
            cc += len([c for c in hijo.cases if c.guard is not None]) + 1
    return cc


def incumple_complejidad(raiz: Path) -> list[Incumplimiento]:
    fuera: list[Incumplimiento] = []
    for ruta in _modulos(raiz):
        arbol = _arbol(ruta)
        if arbol is None:
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if nodo.name.startswith("_"):
                continue
            cc = _cc(nodo)
            if cc >= CC_MAX:
                fuera.append(
                    Incumplimiento(
                        "complejidad publica",
                        f"{ruta.relative_to(raiz)}:{nodo.name} (cc={cc})",
                    )
                )
    return fuera


# ---------------------------------------------------------------------------
# 3. SQL en el dominio — por AST, NO por grep
# ---------------------------------------------------------------------------


def _usa_sql(ruta: Path) -> list[str]:
    arbol = _arbol(ruta)
    if arbol is None:
        return []
    usos: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.split(".")[0] == "sqlite3":
                    usos.append(f"linea {nodo.lineno}: import sqlite3")
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] == "sqlite3":
                usos.append(f"linea {nodo.lineno}: from sqlite3 import ...")
        elif isinstance(nodo, ast.Attribute):
            base = nodo
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id == "sqlite3":
                usos.append(f"linea {nodo.lineno}: sqlite3.{nodo.attr}")
        elif (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in METODOS_SQL
        ):
            usos.append(f"linea {nodo.lineno}: .{nodo.func.attr}()")
    return usos


def incumple_sql_en_dominio(raiz: Path) -> list[Incumplimiento]:
    fuera: list[Incumplimiento] = []
    for ruta in _de_dominio(raiz):
        for uso in _usa_sql(ruta):
            fuera.append(Incumplimiento("SQL en el dominio", f"{ruta.relative_to(raiz)}: {uso}"))
    return fuera


# ---------------------------------------------------------------------------
# 4. dominio -> platform (el puerto NO cuenta)
# ---------------------------------------------------------------------------


def incumple_dependencia(raiz: Path) -> list[Incumplimiento]:
    """Dominio -> implementacion de `platform`.

    **LOS IMPORTS DE `if TYPE_CHECKING` NO CUENTAN, Y POR QUE.** Un import
    bajo `TYPE_CHECKING` no existe en runtime: no abre una conexion, no
    crea un ciclo de importacion y no puede meter la implementacion dentro
    del dominio. Contarlo haria que el gate pidiera borrar el bloque de
    tipos, que es lo correcto — y borrarlo haria que el type-checker
    dejara de saber que hay un `Storage` ahi.

    Distinguir uno de otro es barato y es la diferencia entre una ley y una
    cita: se recorre el AST buscando el `if TYPE_CHECKING` y se ignoran
    los imports que caen dentro.
    """
    fuera: list[Incumplimiento] = []
    for ruta in _de_dominio(raiz):
        arbol = _arbol(ruta)
        if arbol is None:
            continue

        # Lineas cubiertas por un `if TYPE_CHECKING:` — no cuentan.
        solo_tipos: set[int] = set()
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.If):
                continue
            prueba = nodo.test
            nombre = ""
            if isinstance(prueba, ast.Name):
                nombre = prueba.id
            elif isinstance(prueba, ast.Attribute):
                nombre = prueba.attr
            if nombre != "TYPE_CHECKING":
                continue
            for hijo in ast.walk(nodo):
                solo_tipos.add(getattr(hijo, "lineno", -1))

        for nodo in ast.walk(arbol):
            # `Module` no tiene `lineno`: sin el default, el bucle revienta en
            # el nodo raiz del arbol, que es el primero que se visita.
            if getattr(nodo, "lineno", -1) in solo_tipos:
                continue
            destinos: list[str] = []
            if isinstance(nodo, ast.ImportFrom):
                destinos.append(nodo.module or "")
            elif isinstance(nodo, ast.Import):
                destinos.extend(a.name for a in nodo.names)
            for destino in destinos:
                if not destino.startswith("skillgraph.platform"):
                    continue
                if destino.startswith("skillgraph.platform.ports"):
                    continue  # el puerto: es lo correcto
                fuera.append(
                    Incumplimiento(
                        "dominio -> platform",
                        f"{ruta.relative_to(raiz)}:{nodo.lineno}: {destino}",
                    )
                )
    return fuera


# ---------------------------------------------------------------------------
# 5. referencias normativas rotas
# ---------------------------------------------------------------------------


def incumple_referencias(raiz: Path) -> list[Incumplimiento]:
    import re

    cita = re.compile(r"\b((?:\d{2}-SPEC-[A-Z0-9-]+)|(?:ADR-\d{4})|(?:blueprint-v1))")
    citadas: set[str] = set()
    for patron in ("*.md", "*.py", "*.yaml", "*.kts"):
        for ruta in raiz.glob(patron):
            if ".git" in ruta.parts:
                continue
            try:
                citadas.update(cita.findall(ruta.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue

    fuera: list[Incumplimiento] = []
    for nombre in sorted(citadas):
        if _existe(raiz, nombre):
            continue
        fuera.append(Incumplimiento("referencia normativa rota", nombre))
    return fuera


def _existe(raiz: Path, nombre: str) -> bool:
    """¿Existe un fichero O un directorio con contenido que sea esta autoridad?

    `blueprint-v1` es un directorio de 12 documentos en `external/`, que
    está **fuera de git por decisión del repo** y es el source of truth de
    `AGENTS.md` §0. Contarlo como roto sería exigir deshacer esa decisión.
    """
    for directorio in (
        raiz,
        raiz / "external",
        raiz / "docs",
        raiz / "decisions",
        raiz / "specs",
    ):
        if not directorio.is_dir():
            continue
        for p in directorio.rglob("*"):
            if p.name.startswith(nombre):
                if p.is_file():
                    return True
                if p.is_dir() and any(p.iterdir()):
                    return True
    return False


# ---------------------------------------------------------------------------


TODAS = (
    ("god modules > 800", incumple_tamano),
    ("complejidad publica >= 20", incumple_complejidad),
    ("SQL en el dominio", incumple_sql_en_dominio),
    ("dominio -> platform", incumple_dependencia),
    ("referencias normativas rotas", incumple_referencias),
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raiz", default=None, help="raiz del repo (por defecto: la del script)")
    args = ap.parse_args()
    raiz = Path(args.raiz).resolve() if args.raiz else Path(__file__).resolve().parent.parent

    incumplimientos: list[Incumplimiento] = []
    for nombre, fn in TODAS:
        found = fn(raiz)
        incumplimientos.extend(found)
        estado = "OK  " if not found else "FALLA"
        print(f"[{estado}] {nombre}: {len(found)}")

    if incumplimientos:
        print(f"\n{len(incumplimientos)} incumplimiento(s):")
        for inc in incumplimientos:
            print(f"  - {inc}")
        print(
            "\nEl ratchet NO baja a advertencia: cada propiedad que llega a cero se queda en cero."
        )
        return 1

    print("\nLas cinco propiedades llegan a cero.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
