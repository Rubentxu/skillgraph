"""WI-40: el auditor de deuda no debe destruir la cronologia escrita a mano.

Contexto: `audits/audit_debt.py` reescribe el informe completo cada vez que se
ejecuta. Antes de WI-40 no tenia ninguna seccion preservada, asi que cualquier
analisis de cierre de WI (drifts encontrados, deuda residual) anadido despues
de generar el informe se perdia en la siguiente ejecucion. Se perdio asi la
seccion de cierre de WI-38, que es justamente la que define el alcance de
WI-39.

Estos tests fijan el contrato de `read_annals`: la parte automatica del
informe se regenera, la cronologia marcada se conserva.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "audits" / "audit_debt.py"


def _load_auditor() -> object:
    """Importa `audits/audit_debt.py` como modulo.

    `audits/` no es un paquete, asi que se carga por ruta. El modulo solo
    define funciones y una constante `AUDITS_DIR` relativo; importarlo no
    ejecuta el analisis (eso vive en `main`).
    """
    spec = importlib.util.spec_from_file_location("audit_debt_wi40", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def auditor() -> object:
    return _load_auditor()


def test_read_annals_returns_empty_when_file_missing(
    auditor: object, tmp_path: pathlib.Path
) -> None:
    """Un informe que no existe no tiene cronologia que preservar."""
    assert auditor.read_annals(tmp_path / "nope.md") == []


def test_read_annals_returns_empty_without_marker(auditor: object, tmp_path: pathlib.Path) -> None:
    """Un informe sin la marca se considera autogenerado entero.

    Es el caso de los informes previos a WI-40: no tienen cronologia que
    recuperar, y regenerarlos debe produzir un informe limpio.
    """
    legacy = tmp_path / "legacy.md"
    legacy.write_text("# Informe\n\n## Solo metricas\n", encoding="utf-8")
    assert auditor.read_annals(legacy) == []


def test_read_annals_returns_content_below_marker(auditor: object, tmp_path: pathlib.Path) -> None:
    """La cronologia marcada se devuelve completa y en orden."""
    report = tmp_path / "report.md"
    report.write_text(
        f"# Informe\n\n## Metricas\n\n{auditor.ANNALS_MARKER}\n\n## WI-38 cierre\n\ntexto\n",
        encoding="utf-8",
    )
    annals = auditor.read_annals(report)
    assert any("WI-38 cierre" in line for line in annals)
    assert any("texto" in line for line in annals)


def test_main_preserves_annals_end_to_end(tmp_path: pathlib.Path) -> None:
    """`main()` real conserva la cronologia y es idempotente.

    Test de integracion del contrato completo, y el unico que invoca el
    generador de verdad (`main`) en vez de reimplementar su escritura: una
    version anterior de este test replicaba la logica a mano y pasaba
    aunque `main` siguiera sobrescribiendo el informe entero.

    Se ejecuta en un sandbox porque `main` usa rutas relativas al proceso
    (`src/`, `audits/`), asi que se cambia el cwd a un arbol minimo con un
    modulo Python de ejemplo.
    """
    auditor_mod = _load_auditor()
    sandbox = tmp_path / "repo"
    src = sandbox / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    audits = sandbox / "audits"
    audits.mkdir()

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    report = audits / f"architecture-debt-{today}.md"
    report.write_text(
        f"# Informe\n{auditor_mod.ANNALS_MARKER}\n\n## WI-38 cierre\n\ndeuda residual: X\n",
        encoding="utf-8",
    )

    previous = Path.cwd()
    os.chdir(sandbox)
    try:
        assert auditor_mod.main() == 0
        first = report.read_text(encoding="utf-8")
        assert auditor_mod.main() == 0
        second = report.read_text(encoding="utf-8")
    finally:
        os.chdir(previous)

    assert "deuda residual: X" in first
    assert first == second, "main() no es idempotente"
    assert first.count("WI-38 cierre") == 1
    assert first.count(auditor_mod.ANNALS_MARKER) == 1
