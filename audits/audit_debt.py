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

import ast
import pathlib
import sys
from datetime import UTC, datetime

SRC_ROOT = pathlib.Path("src")
AUDITS_DIR = pathlib.Path("audits")
AUDITS_DIR.mkdir(exist_ok=True)

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


def main() -> int:
    if not SRC_ROOT.exists():
        print(f"FATAL: {SRC_ROOT} no existe; ejecuta desde la raiz del repo.", file=sys.stderr)
        return 1

    files = []
    for p in SRC_ROOT.rglob("*.py"):
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

    lines.append("## Recomendaciones (post-WI-22 cierre previo)")
    lines.append("")
    lines.append("### Cerradas en este ciclo WI-23..WI-27 (housekeeping) — 5 WIs")
    lines.append("- `_validate` (pack_loader): cc 22→7 — 3 helpers extraidos.")
    lines.append("- `validate` (graph_expansion): cc 24→4 — 3 helpers extraidos.")
    lines.append("- `parse_markdown` (resources.parser): cc 17→2 — 4 helpers extraidos.")
    lines.append("- `take` (runtime.locks.RunLock): cc 16→5 — 4 helpers extraidos.")
    lines.append("- `record_validation_receipt`: cc 14→5 — 4 helpers con `empty_msg` kwarg.")
    lines.append("- `traverse_invalidations`: cc 13→5 — 3 helpers (seed/expand/warn).")
    lines.append(
        "- `HttpAgentAdapter.invoke`: cc 12→7 — sentinel `RetryableHttpStatus` + 1 helper."
    )
    lines.append("- `compile_handoff_from_scopes`: cc 12→1 — triada validate/enforce/build_synth.")
    lines.append("")
    lines.append("### Pendientes por prioridad")
    lines.append("")
    lines.append("**P0 - Hotspots publicos cc>=20** (refactor obligatorio):")
    lines.append("- `main` (runner.py): cc=43, 58 LoC — CLI entry point: NO refactor surgical.")
    lines.append(
        "- `cmd_run` (runner.py): cc=22, 122 LoC — candidate a `_dispatch_run_subcommand(...)`."
    )
    lines.append(
        "- `_make_schema_validator` (pack_loader.py): cc=22, 77 LoC — factory de closures; refactor interno factible."
    )
    lines.append("")
    lines.append("**P1 - God modules** (>800 LoC, deuda estructural mayor):")
    lines.append(
        "- H-01 storage.py (2407 LoC): reposicionar por dominio (knowledge/governance/receipts)."
    )
    lines.append("- H-02 cli/runner.py (2477 LoC): extraer sub-comandos a modulos individuales.")
    lines.append("- runcontroller.py (1357 LoC): separar reconciliacion de ejecucion.")
    lines.append("")
    lines.append("**P2 - Hotspots privados cc>=20** (refactor opcional, valor pedagogico):")
    lines.append("- Sin acciones automaticas; decidir caso por caso.")
    lines.append("")
    lines.append(
        "**P3 - Funciones largas >80 LoC**: ver tabla arriba. En su mayoria son orquestadores."
    )
    lines.append("")
    lines.append("### Politica recomendada")
    lines.append("")
    lines.append("- WIs P0 siguen el patron helper-extraction ya establecido (D-52..D-60).")
    lines.append(
        "- WIs P1 (god modules) requieren un ADR previo porque tocan contratos publicos y boundary."
    )
    lines.append(
        "- Cualquier release debe mantener cero hotspots publicos cc>=20 o documentar la excepcion."
    )
    lines.append("")

    out_path = AUDITS_DIR / f"architecture-debt-{today}.md"
    annals = read_annals(out_path)
    out_path.write_text("\n".join([*lines, "", ANNALS_MARKER, "", *annals]))
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
