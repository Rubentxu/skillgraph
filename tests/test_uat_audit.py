"""Tests pytest para los UATs que viven solo en tests/uat_audit.py.

Cierra el gap honesto documentado en specs/uat-coverage-gap.md:
estos UATs ya tienen implementacion verificada (status=PASS al
ejecutar uat_audit.py), pero NO corren automaticamente en CI
porque uat_audit.py es un script y scripts/ci.sh solo ejecuta
pytest.

Este modulo NO reimplementa la logica de los UATs: simplemente
invoca las funciones uat_NN() de tests/uat_audit.py y aserta
el campo status del Evidence devuelto.

Patron reutilizado: el helper _run_cli de tests/uat_audit.py se
usa tal cual (sin modificar), garantizando que pytest ejecuta
exactamente el mismo codigo que el script de audit manual.

Cobertura que AÑADE este modulo:
- UAT-05: handoff con ContextRecipe.
- UAT-10: invalidacion de conocimiento (H3 slice 4).
- UAT-11: asimilacion de skill (H5).
- UAT-15: fuente maliciosa (Adapter outcome JSON gobierna).
- UAT-16: estado historico (handoff_json persiste).

UATs ya cubiertos en pytest (NO duplicar):
- UAT-01..04, 06..07 en test_cli_uat.py y test_cli_run_uat.py.
- UAT-08, UAT-09 en test_h4_expansion_cli.py.
- UAT-14 en test_skill_importer.py (test_script_never_executes_during_import).

UATs esperados BLOCKED (cubiertos en test_uat_blocked.py):
- UAT-12 (H6 multipropósito), UAT-13 (H7 promoción).

Cada test aqui es un wrapper trivial; el valor NO es logica nueva
sino CI-coverage: si alguien modifica src/skillgraph/*.py sin
actualizar uat_audit.py, estos tests fallan en CI, no esperan
ejecucion manual.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tests/ no es un paquete Python; importamos el script via sys.path.
_TESTS_DIR = Path(__file__).parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import uat_audit  # type: ignore[import-not-found]  # noqa: E402

# Mapping (uat_id, uat_fn, expected_status).
# expected_status="PASS" para los 5 gaps reales.
_GAP_UATS: list[tuple[str, str, str]] = [
    ("UAT-05", "uat_05", "PASS"),
    ("UAT-10", "uat_10", "PASS"),
    ("UAT-11", "uat_11", "PASS"),
    ("UAT-15", "uat_15", "PASS"),
    ("UAT-16", "uat_16", "PASS"),
]


@pytest.mark.parametrize("uat_id,fn_name,expected", _GAP_UATS)
def test_uat_wrapper_runs_and_passes(uat_id: str, fn_name: str, expected: str) -> None:
    """Wrapper pytest para un UAT que solo vive en uat_audit.py.

    Invoca la funcion uat_NN() y aserta su Evidence.status. NO
    reimplementa la logica. Si uat_audit.py cambia y un UAT deja
    de pasar, este test falla en CI automaticamente.
    """
    fn = getattr(uat_audit, fn_name)
    evidence = fn()
    assert evidence.uat_id == uat_id, (
        f"{fn_name}() retorno uat_id={evidence.uat_id!r}, esperado {uat_id!r}"
    )
    assert evidence.status == expected, (
        f"{uat_id} status={evidence.status!r}, esperado {expected!r}.\n"
        f"observed: {evidence.observed}\nnotes: {evidence.notes}"
    )
