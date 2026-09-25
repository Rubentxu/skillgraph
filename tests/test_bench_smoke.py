"""Smoke tests para ``bench.bench_context``.

NO testean correctness del bench (eso seria un bench-test, distinto):
verifican que el modulo es ejecutable, produce un reporte con el
schema esperado y devuelve exit codes correctos.

Los tests se ejecutan como ``subprocess`` para no contaminar la
cobertura de pytest-cov con el codigo de bench (regla de oro:
los benches NO cuentan como cobertura productiva).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_bench(*args: str) -> subprocess.CompletedProcess[str]:
    """Helper: invoca ``python -m bench.bench_context``."""
    cmd = [sys.executable, "-m", "bench.bench_context", *args]
    return subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


class TestBenchSmoke:
    """Contratos minimos: ejecutabilidad, exit code, schema."""

    def test_default_runs_and_exits_zero(self) -> None:
        """Bench con sizes default -> exit 0 + tabla con 3 filas."""
        result = _run_bench()
        assert result.returncode == 0, (
            f"bench fallo:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        # Cabecera Markdown esperada.
        assert "| claims | src |" in result.stdout
        # Default sizes = 10, 100, 1000 -> 3 filas de datos.
        data_rows = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("| ") and "---" not in line and "claims" not in line
        ]
        assert len(data_rows) == 3, f"esperaba 3 filas, encontre {len(data_rows)}"

    def test_json_output_is_valid(self) -> None:
        """``--json`` produce un JSON valido con el schema esperado."""
        result = _run_bench("--sizes", "7", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["schema"] == "skillgraph.bench.v1"
        assert "python_version" in payload
        assert isinstance(payload["rows"], list)
        assert len(payload["rows"]) == 1
        row = payload["rows"][0]
        assert row["claims"] == 7
        # Una row con N=7 claims debe tener exactamente 7 included.
        assert row["included_count"] == 7
        # context_hash: 12 chars hex (prefijo SHA-256).
        assert len(row["context_hash"]) == 12
        # Mediciones en ms (floats positivos).
        assert row["compile_cold_ms"] >= 0
        assert row["compile_warm_median_ms"] >= 0
        assert row["refresh_warm_median_ms"] >= 0

    def test_custom_sizes_produce_requested_rows(self) -> None:
        """``--sizes 5 25`` produce exactamente 2 filas con esos N."""
        result = _run_bench("--sizes", "5", "25", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert [r["claims"] for r in payload["rows"]] == [5, 25]
