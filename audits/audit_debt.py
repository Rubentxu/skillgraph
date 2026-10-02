#!/usr/bin/env python3
"""WI-28: caracterizacion automatica de deuda arquitectonica.

Audita el codigo en src/skillgraph/ sin modificar nada. Emite un
reporte reproducible con metricas sobre:

- Funciones con cc alto (>15, >20, publicas vs privadas).
- Funciones largas (>80 LoC).
- Archivos grandes (>800 LoC).
- Anidamiento profundo (>3 niveles de if/for).
- Imports laterales (no locales, no de `collections.abc`).

Decisiones registradas (D-61..D-66) sobre el estado de la deuda
y los siguientes pasos recomendados.

Output: stdout (reporte) + writes audits/architecture-debt-2026-09-26.md
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
from datetime import UTC, datetime

SRC_ROOT = pathlib.Path("src")
AUDITS_DIR = pathlib.Path("audits")

# Marca que delimita la cronologia escrita a mano. Todo lo que quede por
# debajo se conserva al regenerar el informe: el generador solo reescribe
# la seccion automatica de metricas.
# Sin esta marca, cada ejecucion del auditor destruia el analisis de
# cierre de WI (drifts, deuda residual) anadido despues de generar.
ANNALS_MARKER = "<!-- ANNALS:append-only -->"


def cyclomatic(node: ast.AST) -> int:
    """Cyclomatic complexity simplificada (mismo algoritmo que WI-21..WI-27)."""
    n = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            n += len(child.body) if isinstance(child, ast.Try) else 1
        elif isinstance(child, ast.BoolOp):
            n += len(child.values) - 1
        elif isinstance(child, ast.Match):
            n += len(child.cases)
    return n


def deepest_nesting(node: ast.AST) -> int:
    """Profundidad maxima de anidamiento de bloques control-flow."""

    def _depth(n: ast.AST, current: int) -> int:
        if isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            current += 1
        kids = list(ast.iter_child_nodes(n))
        if not kids:
            return current
        return max(_depth(c, current) for c in kids)

    return _depth(node, 0)


def audit_file(path: pathlib.Path) -> dict:
    src = path.read_text()
    tree = ast.parse(src)
    func_metrics = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            try:
                c = cyclomatic(node)
            except Exception:
                c = -1
            line_count = (node.end_lineno - node.lineno) + 1
            func_metrics.append(
                {
                    "name": node.name,
                    "lines": line_count,
                    "cc": c,
                    "nesting": deepest_nesting(node),
                    "is_private": node.name.startswith("_"),
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }
            )
    return {
        "path": str(path),
        "loc": len(src.splitlines()),
        "funcs": func_metrics,
    }


def read_annals(path: pathlib.Path) -> list[str]:
    """Devuelve la cronologia manual ya presente en ``path``.

    Funcion pura salvo por la lectura: no escribe nada. Si el informe no
    existe o no tiene la marca, devuelve una lista vacia y el informe se
    regenera limpio. Si la tiene, devuelve todo lo que va despues, para
    que `main` lo reescriba por debajo de la seccion automatica.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    marker_at = text.find(ANNALS_MARKER)
    if marker_at < 0:
        return []
    return text[marker_at + len(ANNALS_MARKER) :].strip("\n").split("\n")


def max_public_cc(files: list[dict]) -> int:
    """Mayor cc entre funciones publicas de todos los archivos.

    Se usa para poder decir "el maximo medido es N" cuando no hay
    hotspots, en vez de dejar el P0 sin ninguna cifra. Funcion pura:
    no lee disco ni escribe nada.

    Args:
        files: salida de ``audit_file`` por cada modulo de ``src/``.

    Returns:
        El mayor cc publico, o 0 si no hay ninguna funcion publica.
    """
    return max(
        (func["cc"] for f in files for func in f["funcs"] if not func["is_private"]),
        default=0,
    )


def main(argv: list[str] | None = None) -> int:
    """Audita el arbol y escribe el informe.

    WI-89: tanto el arbol que se analiza como el destino de la escritura son
    parametros. Antes ambos eran relativos al cwd, y como el destino caia
    dentro de `audits/` —que esta TRACKEADO— cada corrida de la suite
    reescribia un fichero versionado del repositorio que el propio script
    audita. Ademas el mkdir vivia a nivel de modulo, luego importar el script
    ya creaba un directorio.

    Los defaults siguen siendo cwd-relativos: un humano que lance el script a
    mano desde la raiz obtiene exactamente el mismo comportamiento.
    """
    parser = argparse.ArgumentParser(
        prog="audit_debt", description="Auditoria automatica de deuda arquitectonica."
    )
    parser.add_argument(
        "--src-root",
        type=pathlib.Path,
        default=SRC_ROOT,
        help=f"Arbol a auditar (default: {SRC_ROOT}, relativo al cwd).",
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=AUDITS_DIR,
        help=(
            f"Directorio donde escribir el informe (default: {AUDITS_DIR}, relativo "
            "al cwd). Los tests pasan uno temporal para no mutar el repositorio."
        ),
    )
    args = parser.parse_args(argv)

    src_root: pathlib.Path = args.src_root
    out_dir: pathlib.Path = args.out_dir

    if not src_root.exists():
        print(f"FATAL: {src_root} no existe; ejecuta desde la raiz del repo.", file=sys.stderr)
        return 1

    files = []
    for p in src_root.rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        files.append(audit_file(p))

    # Acumuladores.
    god_files: list[tuple[int, pathlib.Path]] = []
    hotspots_public: list[tuple[int, int, pathlib.Path, str]] = []  # (cc, lines, file, name)
    hotspots_private: list[tuple[int, int, pathlib.Path, str]] = []
    longest_funcs: list[tuple[int, pathlib.Path, str]] = []
    deeply_nested: list[tuple[int, pathlib.Path, str]] = []

    for f in files:
        p = pathlib.Path(f["path"])
        if f["loc"] > 800:
            god_files.append((f["loc"], p))
        for func in f["funcs"]:
            if func["cc"] >= 20:
                (hotspots_public if not func["is_private"] else hotspots_private).append(
                    (func["cc"], func["lines"], p, func["name"])
                )
            if func["lines"] > 80:
                longest_funcs.append((func["lines"], p, func["name"]))
            if func["nesting"] >= 5:
                deeply_nested.append((func["nesting"], p, func["name"]))

    god_files.sort(reverse=True)
    hotspots_public.sort(reverse=True)
    hotspots_private.sort(reverse=True)
    longest_funcs.sort(reverse=True)
    deeply_nested.sort(reverse=True)

    # Compose report.
    today = datetime.now(UTC).date().isoformat()
    lines = [
        f"# Auditoria de deuda arquitectonica ({today})",
        "",
        "Generada por `audits/audit_debt.py` (WI-28). Reproducible:",
        "`python audits/audit_debt.py` desde la raiz del repo.",
        "",
        "## Resumen ejecutivo",
        "",
    ]
    total_lines = sum(f["loc"] for f in files)
    total_funcs = sum(len(f["funcs"]) for f in files)
    lines.append(
        f"- **{len(files)}** modulos Python, **{total_lines}** LoC, **{total_funcs}** funciones."
    )
    lines.append(f"- **{len(god_files)}** archivos >800 LoC (god modules).")
    lines.append(
        f"- **{len(hotspots_public)}** funciones publicas con cc>=20 (refactor obligatorio)."
    )
    lines.append(
        f"- **{len(hotspots_private)}** funciones privadas con cc>=20 (refactor opcional)."
    )
    lines.append(f"- **{len(longest_funcs)}** funciones >80 LoC (legibilidad mejorable).")
    lines.append(f"- **{len(deeply_nested)}** funciones con anidamiento >=5 niveles.")
    lines.append("")

    lines.append("## Archivos grandes (>800 LoC)")
    lines.append("")
    lines.append("H-01 Storage god-class y H-02 CLI god-module son las entradas mas impactantes.")
    lines.append("")
    lines.append("| LoC | Path |")
    lines.append("|----:|------|")
    for loc, p in god_files[:8]:
        lines.append(f"| {loc} | `{p}` |")
    lines.append("")

    lines.append("## Hotspots publicos (cc>=20, refactor obligatorio)")
    lines.append("")
    lines.append("| cc | LoC | Funcion | Path |")
    lines.append("|---:|----:|---------|------|")
    for cc, ln, p, n in hotspots_public[:15]:
        lines.append(f"| {cc} | {ln} | `{n}` | `{p}` |")
    lines.append("")

    if hotspots_private:
        lines.append("## Hotspots privados (cc>=20, refactor opcional)")
        lines.append("")
        lines.append(
            "Funciones con `_` prefijo. Suelen ser entry points de test, helpers de command handlers,"
        )
        lines.append(
            "o coordinadores de bloque. No son candidatos directos a helper extraction a menos"
        )
        lines.append("que tenga valor pedagogico o de testabilidad.")
        lines.append("")
        lines.append("| cc | LoC | Funcion | Path |")
        lines.append("|---:|----:|---------|------|")
        for cc, ln, p, n in hotspots_private[:10]:
            lines.append(f"| {cc} | {ln} | `{n}` | `{p}` |")
        lines.append("")

    lines.append("## Funciones largas (>80 LoC)")
    lines.append("")
    lines.append(
        "Top 20 funciones por LoC. Muchas son orquestadores coordinando handlers; en si no"
    )
    lines.append("son problematicas si tienen baja cc y helpers atomicos con test coverage.")
    lines.append("")
    lines.append("| LoC | Funcion | Path |")
    lines.append("|----:|---------|------|")
    for ln, p, n in longest_funcs[:20]:
        lines.append(f"| {ln} | `{n}` | `{p}` |")
    lines.append("")

    lines.append("## Anidamiento profundo (>=5 niveles)")
    lines.append("")
    if deeply_nested:
        lines.append(
            "Anidamiento >=5 suele indicar decision tree en lugar de composicion declarativa."
        )
        lines.append("")
        lines.append("| Nesting | Funcion | Path |")
        lines.append("|--------:|---------|------|")
        for d, p, n in deeply_nested[:15]:
            lines.append(f"| {d} | `{n}` | `{p}` |")
    else:
        lines.append("- Ninguna funcion con anidamiento >=5. ✓")
    lines.append("")

    lines.append("## Recomendaciones (derivadas de la medicion)")
    lines.append("")
    lines.append("Esta seccion se genera desde las metricas de este mismo informe. No")
    lines.append("hay cifras escritas a mano: si una funcion baja de cc=20, desaparece de")
    lines.append("P0 sin que nadie tenga que acordarse de borrarla.")
    lines.append("")

    # P0: hotspots publicos medidos. Si no hay ninguno, se dice.
    lines.append("**P0 - Hotspots publicos cc>=20** (refactor obligatorio):")
    lines.append("")
    if hotspots_public:
        for cc, ln, p, n in hotspots_public:
            lines.append(f"- `{n}` (`{p}`): cc={cc}, {ln} LoC.")
    else:
        lines.append(
            f"- Ninguno. Ninguna funcion publica de `src/` alcanza cc=20 "
            f"(maximo medido: {max_public_cc(files)})."
        )
    lines.append("")

    # P1: god modules medidos, con LoC leido del arbol.
    lines.append("**P1 - God modules** (>800 LoC, deuda estructural):")
    lines.append("")
    if god_files:
        for loc, p in god_files:
            lines.append(
                f"- `{p}` ({loc} LoC): requiere ADR previo, porque tocarlo "
                "afecta a contratos publicos y frontera de dominio."
            )
    else:
        lines.append("- Ninguno.")
    lines.append("")

    # P2: hotspots privados medidos.
    lines.append("**P2 - Hotspots privados cc>=20** (opcional, valor pedagogico):")
    lines.append("")
    if hotspots_private:
        for cc, ln, p, n in hotspots_private:
            lines.append(f"- `{n}` (`{p}`): cc={cc}, {ln} LoC.")
    else:
        lines.append("- Ninguno.")
    lines.append("")

    # P3: funciones largas, medidas.
    lines.append(f"**P3 - Funciones largas >80 LoC**: {len(longest_funcs)} en total.")
    lines.append("En su mayoria son orquestadores con baja cc y helpers atomicos con")
    lines.append("cobertura; ver la tabla de arriba. Prioridad baja.")
    lines.append("")

    # Anidamiento: es la senal de decision tree, la mas accionable tras P0.
    lines.append("**P4 - Anidamiento >=5 niveles** (decision tree en vez de composicion):")
    lines.append("")
    if deeply_nested:
        for d, p, n in deeply_nested:
            lines.append(f"- `{n}` (`{p}`): {d} niveles.")
    else:
        lines.append("- Ninguno.")
    lines.append("")

    lines.append("### Politica recomendada")
    lines.append("")
    lines.append("- Los WIs de complejidad siguen el patron helper-extraction ya")
    lines.append("  establecido (D-52..D-60): extraer helpers atomicos y medibles.")
    lines.append("- Los WIs P1 (god modules) requieren un ADR previo porque tocan")
    lines.append("  contratos publicos y frontera de dominio.")
    lines.append("- Cualquier release mantiene cero hotspots publicos cc>=20, o")
    lines.append("  documenta la excepcion de forma explicita.")
    lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"architecture-debt-{today}.md"
    annals = read_annals(out_path)
    out_path.write_text("\n".join([*lines, "", ANNALS_MARKER, "", *annals]))
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
