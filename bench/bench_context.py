"""Bench: mide `compile_handoff` y `refresh_handoff` con corpus sintetico.

Estrategia:
- Crea un Storage SQLite en memoria (``Storage(":memory:")`` no es
  soportado en este proyecto, asi que usamos ``tempfile``).
- Genera N claims distribuidas en ``ceil(N/7)`` sources, una entity
  por source y los 7 predicados validos
  (``CLAIM_PREDICATES``) en orden.
- Mide 3 fases para cada N:
    * **compile_cold** — primera llamada (incluye warm-up de SQLite).
    * **compile_warm** — segunda llamada (cache de prepared stmts).
    * **refresh_warm** — `refresh_handoff` con `previous_hash` valido
      (deberia ser O(1) logico si no hay cambio, pero hoy siempre
      recompila — el bench revela el coste real).

Usage:
    python -m bench.bench_context                 # default (10/100/1000)
    python -m bench.bench_context --sizes 50 500  # custom
    python -m bench.bench_context --json          # solo JSON

Exit codes:
    0  — bench completo, todo OK.
    1  — error en build/medicion.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

# Asegurar import del paquete cuando se ejecuta como ``python -m bench.bench_context``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from skillgraph.core.recipe import ContextRecipe, ObligatorySelector  # noqa: E402
from skillgraph.knowledge.context_controller import ContextController  # noqa: E402
from skillgraph.knowledge.graph import Claim, Entity, Source  # noqa: E402
from skillgraph.knowledge.knowledge_controller import KnowledgeController  # noqa: E402
from skillgraph.platform.storage import Storage  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

# Predicados canonicos (7 en total segun CLAIM_PREDICATES).
# Usarlos en orden rotativo garantiza unicidad junto con (subject, source, rev).
_PREDICATES: tuple[str, ...] = (
    "line_count",
    "function_count",
    "imports_module",
    "defines_symbol",
    "test_passes",
    "file_exists",
    "spec_revision",
)

# Tamaños por defecto del corpus: small / medium / large.
DEFAULT_SIZES: tuple[int, ...] = (10, 100, 1000)

# Repeticiones warm (mediana de 3 para suavizar ruido JIT).
WARM_REPEATS: int = 3


@dataclass(frozen=True, slots=True)
class BenchRow:
    """Una fila de resultado: tamano N + 3 mediciones en ms."""

    claims: int
    sources: int
    entities: int
    compile_cold_ms: float
    compile_warm_median_ms: float
    refresh_warm_median_ms: float
    included_count: int
    context_hash: str

    def to_dict(self) -> dict[str, object]:
        """Serializa a dict plano (JSON-friendly)."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchReport:
    """Reporte completo: filas + meta + timestamp."""

    schema: str
    python_version: str
    rows: tuple[BenchRow, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Serializa a dict plano (JSON-friendly)."""
        return {
            "schema": self.schema,
            "python_version": self.python_version,
            "rows": [r.to_dict() for r in self.rows],
        }


def _build_corpus(*, n_claims: int) -> tuple[KnowledgeController, tuple[ObligatorySelector, ...]]:
    """Crea un KnowledgeController con N claims distribuidas.

    Distribucion:
    * ``n_sources = ceil(n_claims / 7)``.
    * Cada source tiene una entity asociada y hasta 7 claims
      (una por predicado canonico en orden).
    * Devuelve ademas los selectores `source` para la receta de bench.

    Returns:
        Tupla ``(KnowledgeController, selectores)``.
    """
    n_sources = (n_claims + len(_PREDICATES) - 1) // len(_PREDICATES)
    with tempfile.TemporaryDirectory() as d:
        # El storage vive solo dentro de esta funcion; el controller
        # queda usable mientras el path no se borre.
        # -> Usamos un directorio que persiste hasta que el caller
        # decida cerrarlo. Para bench, basta con uno temporal por
        # tamano: ``Storage`` cierra su conn al ``del``.
        storage = Storage(f"{d}/bench.sqlite")
        ctl = KnowledgeController(storage=storage, tenant_id="bench", project_id="bench")
        sels: list[ObligatorySelector] = []
        written = 0
        for i in range(n_sources):
            ent_id = f"e{i}"
            src_id = f"local:s{i}"
            ctl.upsert_entity(entity=Entity(entity_id=ent_id, kind="file", stable_key=ent_id))
            ctl.register_source(
                source=Source(
                    source_id=src_id,
                    kind="local_file",
                    content_hash=f"h{i}",
                    locator={"path": f"s{i}"},
                    git_commit_sha=None,
                    git_tree_sha=None,
                    working_tree_status=None,
                    checked_at="2026-01-01T00:00:00Z",
                    freshness="fresh",
                )
            )
            sels.append(ObligatorySelector(kind="source", value=src_id))
            for j, pred in enumerate(_PREDICATES):
                if written >= n_claims:
                    break
                ctl.record_claim(
                    claim=Claim(
                        claim_id=f"c{i}_{j}",
                        subject_entity_id=ent_id,
                        predicate=pred,
                        object_literal=written,
                        source_id=src_id,
                        extraction_method="manual",
                        extractor_version="skillgraph-rules/0.1.0",
                        checked_at_revision="rev1",
                    )
                )
                written += 1
        return ctl, tuple(sels)


def _measure_compile(
    *,
    ctx: ContextController,
    recipe: ContextRecipe,
    repeats: int,
) -> tuple[float, float]:
    """Mide compile_handoff: cold + mediana de `repeats` warm.

    Returns:
        Tupla ``(cold_ms, warm_median_ms)``.
    """
    # Cold (incluye preparacion, sin cache de prepared stmts).
    t0 = time.perf_counter_ns()
    h_cold = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
    cold_ns = time.perf_counter_ns() - t0

    # Warm (mediana de repeats para suavizar ruido).
    samples: list[int] = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    warm_median_ns = samples[len(samples) // 2]

    # Aseguramos que `h_cold` se usa (silencia linter de unused).
    _ = h_cold.context_hash

    return cold_ns / 1e6, warm_median_ns / 1e6


def _measure_refresh(
    *,
    ctx: ContextController,
    recipe: ContextRecipe,
    previous_hash: str,
    repeats: int,
) -> float:
    """Mide `refresh_handoff` con `previous_hash` dado (mediana)."""
    samples: list[int] = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        ctx.refresh_handoff(
            previous_hash=previous_hash, recipe=recipe, run_id="r1", node_execution_id="n1"
        )
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    return samples[len(samples) // 2] / 1e6


def run_bench(*, sizes: Sequence[int] = DEFAULT_SIZES) -> BenchReport:
    """Ejecuta el bench sobre los tamanos dados y devuelve el reporte."""
    rows: list[BenchRow] = []
    for n in sizes:
        ctl, sels = _build_corpus(n_claims=n)
        ctx = ContextController(knowledge=ctl)
        recipe = ContextRecipe(
            recipe_ref=f"bench-{n}",
            obligatory=sels,
            optional=(),
            token_budget=10**9,
            freshness_policy="best_effort",
            revision=1,
        )
        cold_ms, warm_ms = _measure_compile(ctx=ctx, recipe=recipe, repeats=WARM_REPEATS)
        # Para refresh necesitamos un hash inicial valido.
        h = ctx.compile_handoff(recipe=recipe, run_id="r1", node_execution_id="n1")
        refresh_ms = _measure_refresh(
            ctx=ctx,
            recipe=recipe,
            previous_hash=h.context_hash,
            repeats=WARM_REPEATS,
        )
        # Cierra storage para liberar el tempfile dir.
        del ctl, ctx
        rows.append(
            BenchRow(
                claims=n,
                sources=len(sels),
                entities=len(sels),
                compile_cold_ms=round(cold_ms, 4),
                compile_warm_median_ms=round(warm_ms, 4),
                refresh_warm_median_ms=round(refresh_ms, 4),
                included_count=len(h.knowledge.included),
                context_hash=h.context_hash[:12],
            )
        )
    return BenchReport(
        schema="skillgraph.bench.v1",
        python_version=sys.version.split()[0],
        rows=tuple(rows),
    )


def _format_table(report: BenchReport) -> str:
    """Formatea el reporte como tabla Markdown alineada."""
    headers = (
        "claims",
        "src",
        "compile_cold(ms)",
        "compile_warm(ms)",
        "refresh_warm(ms)",
        "included",
        "hash",
    )
    lines: list[str] = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in report.rows:
        lines.append(
            f"| {r.claims} | {r.sources} | {r.compile_cold_ms:.3f} | "
            f"{r.compile_warm_median_ms:.3f} | {r.refresh_warm_median_ms:.3f} | "
            f"{r.included_count} | `{r.context_hash}` |"
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m bench.bench_context",
        description="Bench de compile_handoff/refresh_handoff sobre corpus sintetico.",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=list(DEFAULT_SIZES),
        help="Tamanos de corpus a medir (default: 10 100 1000).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Solo imprime JSON (omite la tabla humana).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada CLI. Devuelve 0 OK, 1 error."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run_bench(sizes=args.sizes)
    except Exception as exc:
        print(f"bench fallo: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(_format_table(report))
        print()
        print(
            f"# schema={report.schema} python={report.python_version} warm_repeats={WARM_REPEATS}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(main())
