"""Smoke tests para ``bench.bench_storage_reads``.

Mismo patron que ``test_bench_smoke.py``: NO testean correctness
del bench, solo ejecutabilidad + exit codes + schema JSON valido.

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
    """Helper: invoca ``python -m bench.bench_storage_reads``."""
    cmd = [sys.executable, "-m", "bench.bench_storage_reads", *args]
    return subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


class TestBenchStorageReadsSmoke:
    """Contratos minimos: ejecutabilidad, exit code, schema."""

    def test_default_runs_and_exits_zero(self) -> None:
        """Bench con sizes default -> exit 0 + tabla con N filas."""
        result = _run_bench()
        assert result.returncode == 0, (
            f"bench fallo:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        # Cabecera Markdown esperada.
        assert "| runs |" in result.stdout

    def test_json_output_is_valid(self) -> None:
        """``--json`` produce un JSON valido con el schema esperado."""
        result = _run_bench("--sizes", "10", "--runs", "1", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["schema"] == "skillgraph.bench.storage_reads.v1"
        assert "python_version" in payload
        assert isinstance(payload["rows"], list)
        assert len(payload["rows"]) == 1
        row = payload["rows"][0]
        assert row["node_executions"] == 10
        # 1 run principal + 1 de ruido (background_runs=1) = 2 runs totales.
        assert row["runs"] == 2
        # Mediciones en ms (floats positivos).
        assert row["load_run_ms"] >= 0
        assert row["list_node_executions_ms"] >= 0
        assert row["list_executed_node_names_ms"] >= 0

    def test_custom_sizes_produce_requested_rows(self) -> None:
        """``--sizes 5 25 --runs 1`` produce 2 filas con esos N."""
        result = _run_bench("--sizes", "5", "25", "--runs", "1", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert [r["node_executions"] for r in payload["rows"]] == [5, 25]
