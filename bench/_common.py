"""Infraestructura compartida entre benches.

Este modulo concentra las primitivas que cualquier bench de
SkillGraph reusa:

* ``median_ms`` — mide `fn` N veces y devuelve la mediana en ms.
* ``BenchRow`` — fila generica con un label + dict de columnas.
* ``BenchReport`` — agrupa filas + schema + meta.
* ``format_table`` — renderiza un ``BenchReport`` como Markdown.

Se prefiere ``BenchRow`` generico (label + dict de columnas) sobre
dataclasses especializadas por bench porque (a) cubre los 2 benches
actuales con la misma representacion, (b) permite que ``format_table``
sea compartido sin acoplar a columnas concretas, (c) la serializacion
JSON es trivial (dict plano).

Los benches que necesiten columnas fuertemente tipadas pueden
declarar dataclasses propias y usar ``format_table`` con un
``row_to_cells`` adaptador.

Nota: este modulo NO cuenta como cobertura productiva por la misma
razon que el resto de ``bench/``: pytest-cov lo excluye via
``pyproject.toml`` (``tool.coverage.source = ["src/skillgraph"]``).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any


def median_ms(repeats: int, fn: Callable[[], object]) -> float:
    """Ejecuta ``fn`` ``repeats`` veces y devuelve la mediana en ms.

    Args:
        repeats: numero de muestras (>= 1).
        fn: callable sin argumentos. Su valor de retorno se ignora.

    Returns:
        Mediana en milisegundos. Para ``repeats`` par, devuelve
        ``samples[N//2]`` (elemento superior-medio, coherente con
        ``statistics.median_low`` NO; esto es el upper-middle como
        documenta el smoke test).

    Raises:
        ValueError: si ``repeats < 1``.
    """
    if repeats < 1:
        raise ValueError(f"repeats debe ser >= 1, recibio {repeats}")
    samples: list[int] = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        fn()  # type: ignore[func-returns-value]
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    return samples[len(samples) // 2] / 1e6


@dataclass(frozen=True, slots=True)
class BenchRow:
    """Fila de un bench: un label + un dict de columnas metricas.

    ``columns`` es plano (str -> float/int/str). Esto facilita:
    * serializacion JSON sin transformacion,
    * adaptacion a ``format_table`` sin dataclass especializada,
    * adicion de metricas sin cambiar el shape de la fila.
    """

    label: str
    columns: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict plano (JSON-friendly)."""
        return {"label": self.label, "columns": dict(self.columns)}


@dataclass(frozen=True, slots=True)
class BenchReport:
    """Reporte completo: filas + meta + schema."""

    schema: str
    python_version: str
    rows: tuple[BenchRow, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict plano (JSON-friendly)."""
        return {
            "schema": self.schema,
            "python_version": self.python_version,
            "rows": [r.to_dict() for r in self.rows],
        }


# ``format_table`` usa duck typing via ``Any``: el adaptador
# ``row_to_cells`` cierra el gap entre el ``BenchRow`` generico
# (de este modulo) y filas especializadas de cada bench. Esto
# preserva el shape del schema JSON externo (columnas top-level
# del bench) sin acoplar ``format_table`` a columnas concretas.


def format_table(
    *,
    report: Any,  # BenchReport[BenchRow] | BenchReport[BenchRowLocal]; el adaptador row_to_cells cierra el gap
    headers: Sequence[str],
    row_to_cells: Callable[[Any], Sequence[str]],
) -> str:
    """Renderiza un ``BenchReport`` (o subclase/instancia compatible) como tabla Markdown alineada.

    Acepta ``row_to_cells`` para adaptar filas locales (e.g.
    ``BenchRow`` especializado de un bench concreto) a la
    representacion ``BenchRow`` generica de este modulo. Esto
    preserva el shape del schema JSON externo (columnas top-level
    del bench) sin acoplar ``format_table`` a columnas concretas.

    Args:
        report: el reporte a renderizar.
        headers: nombres de columna (primera fila del Markdown).
        row_to_cells: adaptador de fila a celdas. Una celda por
            columna. Coherencia con ``headers`` es responsabilidad
            del caller (mismo length, mismo orden).

    Returns:
        String con la tabla Markdown (cabecera + separador + filas).
    """
    lines: list[str] = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in report.rows:
        cells = row_to_cells(r)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
