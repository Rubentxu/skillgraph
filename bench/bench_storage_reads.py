"""Bench: mide las 3 APIs de lectura de `Storage` que alimentan el
RunController tras H9-BSlice3-S1 (Etapa 7 S1 reads).

APIs medidas:
* `Storage.load_run` — fila completa de `workflow_runs`.
* `Storage.list_node_executions` — todas las ejecuciones de un nodo
  dentro de un run, ordenadas por `started_at ASC`.
* `Storage.list_executed_node_names` — nodos DISTINCT SUCCEEDED de un
  run, ordenados alfabeticamente.

Estrategia:
* Crea un Storage SQLite en tempdir.
* Para cada tamano N (numero de NodeExecutions), crea 1 run y N
  NodeExecutions (todos SUCCEEDED) + M runs adicionales (default 1)
  con 0 ejecuciones (ruido de fondo realista para `load_run`).
* Mide 3 fases por tamano:
    * **load_run_warm_median**: mediana de repeats.
    * **list_node_executions_warm_median**: mediana de repeats sobre
      un nodo arbitrario (todos los nodos estan en SUCCEEDED).
    * **list_executed_node_names_warm_median**: mediana de repeats.

Usage:
    python -m bench.bench_storage_reads                 # default (10/100/1000 node_executions, 1 run de ruido)
    python -m bench.bench_storage_reads --sizes 50 500  # custom
    python -m bench.bench_storage_reads --runs 5        # 5 runs adicionales de ruido
    python -m bench.bench_storage_reads --json          # solo JSON

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

# Asegurar import del paquete cuando se ejecuta como ``python -m bench.bench_storage_reads``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from skillgraph.platform.storage import Storage  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

# Tamaños por defecto del corpus: numero de NodeExecutions por run.
DEFAULT_SIZES: tuple[int, ...] = (10, 100, 1000)

# Runs adicionales de ruido (sin NodeExecutions) para que load_run
# tenga que filtrar entre varios runs. Default 1.
DEFAULT_BACKGROUND_RUNS: int = 1

# Repeticiones warm (mediana de 3 para suavizar ruido JIT).
WARM_REPEATS: int = 3

# Tenant + project del bench (constantes, no se persisten mas alla).
_TENANT = "bench"
_PROJECT = "bench"


@dataclass(frozen=True, slots=True)
class BenchRow:
    """Una fila de resultado: tamano N + 3 mediciones en ms."""

    runs: int
    node_executions: int
    load_run_ms: float
    list_node_executions_ms: float
    list_executed_node_names_ms: float

    def to_dict(self) -> dict[str, object]:
        """Serializa a dict plano (JSON-friendly)."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchReport:
    """Reporte completo: filas + meta + schema."""

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


def _build_corpus(
    *,
    n_node_executions: int,
    n_background_runs: int,
) -> tuple[Storage, str, int]:
    """Crea un Storage con 1 run "principal" + N NodeExecutions SUCCEEDED.

    Args:
        n_node_executions: numero de NodeExecutions a insertar en el run principal.
        n_background_runs: numero de runs adicionales sin NodeExecutions
            (ruido de fondo para `load_run`).

    Returns:
        Tupla ``(Storage, run_id_principal, n_node_executions_real)``.
        ``n_node_executions_real`` puede ser < ``n_node_executions`` si
        N=0 (caso limite trivial).
    """
    d = tempfile.mkdtemp(prefix="sg-bench-storage-reads-")
    storage = Storage(f"{d}/bench.sqlite")
    # 1 run principal.
    main_run_id = storage.create_run(
        tenant_id=_TENANT,
        project_id=_PROJECT,
        plan_json="{}",
        initial_node="start",
    )
    # N NodeExecutions SUCCEEDED en el run principal.
    for i in range(n_node_executions):
        node_exec_id = f"ne-{main_run_id}-{i}"
        storage.start_node_execution(
            node_execution_id=node_exec_id,
            tenant_id=_TENANT,
            project_id=_PROJECT,
            run_id=main_run_id,
            node_name=f"node_{i}",
            attempt=1,
            context_hash=f"hash-{i}",
            handoff_json="{}",
        )
        storage.complete_node_execution(
            node_execution_id=node_exec_id,
            outcome="ok",
            result_json="{}",
        )
    # M runs adicionales sin NodeExecutions (ruido de fondo).
    for _ in range(n_background_runs):
        storage.create_run(
            tenant_id=_TENANT,
            project_id=_PROJECT,
            plan_json="{}",
            initial_node="start",
        )
    return storage, main_run_id, n_node_executions


def _median_ms(repeats: int, fn: object) -> float:
    """Ejecuta `fn` `repeats` veces y devuelve la mediana en ms."""
    samples: list[int] = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        fn()  # type: ignore[operator]
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    return samples[len(samples) // 2] / 1e6


def _bench_one(
    *,
    storage: Storage,
    main_run_id: str,
    target_node: str,
) -> tuple[float, float, float]:
    """Mide las 3 APIs de lectura para una instancia de Storage.

    Returns:
        Tupla ``(load_ms, list_ne_ms, list_names_ms)``.
    """
    s = storage
    rid = main_run_id
    tn = target_node
    load_ms = _median_ms(
        WARM_REPEATS,
        lambda: s.load_run(tenant_id=_TENANT, project_id=_PROJECT, run_id=rid),
    )
    list_ne_ms = _median_ms(
        WARM_REPEATS,
        lambda: s.list_node_executions(
            tenant_id=_TENANT,
            project_id=_PROJECT,
            run_id=rid,
            node_name=tn,
        ),
    )
    list_names_ms = _median_ms(
        WARM_REPEATS,
        lambda: s.list_executed_node_names(tenant_id=_TENANT, project_id=_PROJECT, run_id=rid),
    )
    return load_ms, list_ne_ms, list_names_ms


def run_bench(
    *,
    sizes: Sequence[int] = DEFAULT_SIZES,
    background_runs: int = DEFAULT_BACKGROUND_RUNS,
) -> BenchReport:
    """Ejecuta el bench sobre los tamanos dados y devuelve el reporte."""
    rows: list[BenchRow] = []
    for n in sizes:
        storage, main_run_id, n_real = _build_corpus(
            n_node_executions=n,
            n_background_runs=background_runs,
        )
        # Warm-up (no medido): una llamada de cada API para "calentar"
        # el cache de prepared stmts.
        storage.load_run(tenant_id=_TENANT, project_id=_PROJECT, run_id=main_run_id)
        # `list_node_executions` necesita un node_name: usamos "node_0"
        # que existe si n_real > 0; si n_real == 0, devolvemos lista
        # vacia sin error.
        target_node = "node_0" if n_real > 0 else "nonexistent"
        storage.list_node_executions(
            tenant_id=_TENANT,
            project_id=_PROJECT,
            run_id=main_run_id,
            node_name=target_node,
        )
        storage.list_executed_node_names(tenant_id=_TENANT, project_id=_PROJECT, run_id=main_run_id)

        load_ms, list_ne_ms, list_names_ms = _bench_one(
            storage=storage,
            main_run_id=main_run_id,
            target_node=target_node,
        )
        del storage
        rows.append(
            BenchRow(
                runs=background_runs + 1,
                node_executions=n,
                load_run_ms=round(load_ms, 4),
                list_node_executions_ms=round(list_ne_ms, 4),
                list_executed_node_names_ms=round(list_names_ms, 4),
            )
        )
    return BenchReport(
        schema="skillgraph.bench.storage_reads.v1",
        python_version=sys.version.split()[0],
        rows=tuple(rows),
    )


def _format_table(report: BenchReport) -> str:
    """Formatea el reporte como tabla Markdown alineada."""
    headers = (
        "runs",
        "node_executions",
        "load_run(ms)",
        "list_node_executions(ms)",
        "list_executed_node_names(ms)",
    )
    lines: list[str] = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in report.rows:
        lines.append(
            f"| {r.runs} | {r.node_executions} | {r.load_run_ms:.3f} | "
            f"{r.list_node_executions_ms:.3f} | "
            f"{r.list_executed_node_names_ms:.3f} |"
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m bench.bench_storage_reads",
        description=(
            "Bench de las 3 APIs de lectura de Storage "
            "(load_run, list_node_executions, list_executed_node_names)."
        ),
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=list(DEFAULT_SIZES),
        help="Numero de NodeExecutions por run (default: 10 100 1000).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_BACKGROUND_RUNS,
        help="Runs adicionales de ruido para load_run (default: 1).",
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
        report = run_bench(sizes=args.sizes, background_runs=args.runs)
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
