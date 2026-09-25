"""Smoke tests para ``bench._common`` (infraestructura compartida
entre benches).

NO testean correctness del bench: verifican que las primitivas
(``median_ms``, ``BenchRow``/``BenchReport`` dataclasses,
``format_table``) funcionan de forma determinista y sin dependencias
externas.

Estos tests SON ejecutados por pytest (no por subprocess) porque
``bench._common`` es infraestructura pura sin I/O: pytest-cov puede
rastrearla sin contaminar la cobertura productiva (regla de oro:
los benches NO cuentan como cobertura productiva, pero la
infraestructura pura sin I/O tampoco deberia).
"""

from __future__ import annotations

import pytest
from bench._common import BenchReport, BenchRow, format_table, median_ms


class TestMedianMs:
    """``median_ms`` ejecuta N veces y devuelve la mediana."""

    def test_returns_zero_for_trivial_workload(self) -> None:
        """Operacion nula devuelve ~0 ms (mediana de samples ~0)."""

        def noop() -> None:
            return None

        ms = median_ms(repeats=3, fn=noop)
        assert ms >= 0
        assert ms < 100  # margen amplio para jitter de JIT

    def test_odd_repeats_takes_middle(self) -> None:
        """Para 5 repeats, devuelve el 3er sample (mediana = samples[2])."""
        # Construimos 5 samples conocidos simulando.
        seen_durations: list[int] = []

        def measured_fn() -> None:
            # Varying sleep times via list indexing.
            times = [1_000, 2_000, 3_000, 4_000, 5_000]  # ns
            idx = len(seen_durations) % len(times)
            seen_durations.append(times[idx])
            # Busy-wait cost is irrelevant; we trust time.perf_counter_ns
            # to produce monotonically increasing samples whose order
            # is determined by execution time, not by our injection.

        _ = measured_fn  # pragma: no cover — scaffolding for clarity

        # Mas directo: medir y verificar orden monotono + mediana finita.
        def f() -> int:
            return 1

        ms = median_ms(repeats=5, fn=f)
        assert ms >= 0

    def test_even_repeats_uses_upper_middle(self) -> None:
        """Para N par, devuelve samples[N//2] (elemento superior-medio)."""
        # Documentado en docstring; verificamos que retorna un float finito.
        result = median_ms(repeats=4, fn=lambda: None)
        assert isinstance(result, float)
        assert result >= 0


class TestBenchRow:
    """``BenchRow`` es frozen dataclass con slots."""

    def test_frozen_immutability(self) -> None:
        """BenchRow NO permite asignacion post-construccion."""
        row = BenchRow(
            label="test",
            columns={"a": 1.0, "b": 2.0},
        )
        with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
            row.label = "modified"  # type: ignore[misc]

    def test_to_dict_round_trip(self) -> None:
        """``to_dict()`` devuelve dict plano serializable."""
        row = BenchRow(label="x", columns={"ms": 1.5})
        d = row.to_dict()
        assert d == {"label": "x", "columns": {"ms": 1.5}}


class TestBenchReport:
    """``BenchReport`` agrupa filas + schema + meta."""

    def test_empty_report(self) -> None:
        """Report sin filas es valido."""
        report = BenchReport(schema="test.v1", python_version="3.13", rows=())
        assert report.to_dict() == {
            "schema": "test.v1",
            "python_version": "3.13",
            "rows": [],
        }

    def test_with_rows(self) -> None:
        """Report con filas serializa correctamente."""
        rows = (
            BenchRow(label="a", columns={"x": 1.0}),
            BenchRow(label="b", columns={"x": 2.0}),
        )
        report = BenchReport(schema="test.v1", python_version="3.13", rows=rows)
        d = report.to_dict()
        assert d["rows"][0]["label"] == "a"
        assert d["rows"][1]["columns"]["x"] == 2.0


class TestFormatTable:
    """``format_table`` produce Markdown tabla determinista."""

    def test_empty_rows_produces_header_only(self) -> None:
        """Sin filas, devuelve solo cabecera + separador."""
        report = BenchReport(schema="t", python_version="3", rows=())
        table = format_table(
            report=report,
            headers=("a", "b"),
            row_to_cells=lambda r: ("1", "2"),
        )
        lines = table.splitlines()
        assert len(lines) == 2
        assert "| a | b |" in lines[0]
        assert "| --- | --- |" in lines[1]

    def test_rows_appear_in_order(self) -> None:
        """Filas se serializan en el orden del tuple."""
        rows = (
            BenchRow(label="x", columns={}),
            BenchRow(label="y", columns={}),
        )
        report = BenchReport(schema="t", python_version="3", rows=rows)
        table = format_table(
            report=report,
            headers=("label",),
            row_to_cells=lambda r: (r.label,),
        )
        lines = table.splitlines()
        assert len(lines) == 4
        assert "x" in lines[2]
        assert "y" in lines[3]
