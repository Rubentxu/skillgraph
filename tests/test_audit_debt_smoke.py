"""Smoke tests para ``audits.audit_debt``.

NO testean correctness de las metricas en detalle (eso es auditoria
manual sobre el reporte generado): verifican que el modulo es
ejecutable, produce un archivo con el schema esperado y devuelve
exit code 0.

Los tests se ejecutan como ``subprocess`` para no contaminar la
cobertura de pytest-cov con el codigo de auditoria (regla de
oro: scripts de auditoria / bench NO cuentan como cobertura
productiva).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_audit() -> subprocess.CompletedProcess[str]:
    """Helper: invoca ``python audits/audit_debt.py`` desde la raiz."""
    cmd = [sys.executable, "audits/audit_debt.py"]
    return subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_audit_script_is_executable() -> None:
    """El script corre sin traceback y devuelve exit code 0."""
    proc = _run_audit()
    assert proc.returncode == 0, (
        f"audit_debt.py fallo: rc={proc.returncode}\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    )


def test_audit_produces_markdown_report() -> None:
    """Genera un .md bajo audits/ con las secciones esperadas."""
    proc = _run_audit()
    assert proc.returncode == 0
    out_path = Path(proc.stdout.strip())
    assert out_path.exists(), f"no se creo {out_path}"
    text = out_path.read_text()
    # Cabeceras obligatorias (orden no garantiza; cualquier presencia vale).
    expected_headers = [
        "# Auditoria de deuda arquitectonica",
        "## Resumen ejecutivo",
        "## Archivos grandes",
        "## Hotspots publicos",
        "## Funciones largas",
        "## Anidamiento profundo",
        "## Recomendaciones",
    ]
    for h in expected_headers:
        assert h in text, f"falta seccion {h!r} en {out_path}"


def test_audit_includes_post_wi22_recommendations() -> None:
    """El reporte refleja las decisiones D-52..D-60 (cierre previo) y los P0..P3 actuales."""
    proc = _run_audit()
    out_path = Path(proc.stdout.strip())
    text = out_path.read_text()
    # Comprobacion de contenido: top-3 hotspots publicos deben quedar citados.
    assert "main" in text, "falta mencion de main() cc=43"
    assert "runner.py" in text, "falta path runner.py"
    # Recomendaciones por prioridad.
    for prio in ("**P0", "**P1", "**P2", "**P3"):
        assert prio in text, f"falta bloque {prio}"


def test_audit_table_format_is_markdown_compatible() -> None:
    """Las tablas tienen al menos una fila y formato Markdown valido."""
    proc = _run_audit()
    out_path = Path(proc.stdout.strip())
    text = out_path.read_text()
    # Cuenta lineas que parecen tablas: empiezan con `|` y contienen otro `|`.
    table_rows = [ln for ln in text.splitlines() if ln.startswith("|") and ln.count("|") >= 3]
    assert len(table_rows) >= 10, f"esperaba >=10 filas de tabla, hay {len(table_rows)}"
