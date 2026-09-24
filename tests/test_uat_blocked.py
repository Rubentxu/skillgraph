"""Gap explicito: tests pytest para UAT-12 (H6) y UAT-13 (H7).

Estos UATs ya NO estan BLOCKED. La evidencia real vive en:
- tests/uat-evidence/UAT-12.json (criteria h6, status=PASS)
- tests/uat-evidence/UAT-13.json (criteria h7, status=PASS)

Los tests reales son:
- tests/test_h6_multiproposito.py (12 tests, criterios declarativos)
- tests/test_h7_promocion.py (16 tests, criterios outbox/reconciliacion)

Este modulo cierra el gap de cobertura CI verificando que:
1. Las evidencias JSON dicen PASS con la revision actual.
2. Los tests reales pasan.
3. La implementacion existe en los modulos esperados.

Si en algun momento H6 o H7 se rompen (alguien borra un test,
la evidencia vuelve a BLOCKED, etc.), CI lo detectara automaticamente.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# tests/ no es un paquete Python; importamos modulos via sys.path.
_TESTS_DIR = Path(__file__).parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

_EVIDENCE_DIR = _TESTS_DIR / "uat-evidence"


def _read_evidence(uat_id: str) -> dict[str, object]:
    path = _EVIDENCE_DIR / f"{uat_id}.json"
    if not path.exists():
        pytest.fail(f"Evidencia {uat_id} no existe en {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_evidence_passes(uat_id: str) -> dict[str, object]:
    evidence = _read_evidence(uat_id)
    assert evidence["uat_id"] == uat_id
    assert evidence["status"] == "PASS", (
        f"{uat_id} status={evidence['status']!r}, esperado 'PASS'. "
        f"Si esto es BLOCKED, alguien revirtio la feature sin actualizar "
        f"la evidencia. observed={evidence.get('observed', '')}"
    )
    return evidence


def _run_pytest(test_file: str) -> tuple[int, str]:
    """Ejecuta pytest sobre un archivo y retorna (exit, output)."""
    result = subprocess.run(
        ["uv", "run", "pytest", test_file, "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(_TESTS_DIR.parent),
    )
    return result.returncode, result.stdout + result.stderr


def test_uat_12_evidence_passes() -> None:
    """UAT-12 evidencia debe estar en PASS con SHA real."""
    evidence = _assert_evidence_passes("UAT-12")
    sha = evidence["revision"]
    assert isinstance(sha, str) and len(sha) >= 12, f"SHA invalido: {sha!r}"
    assert evidence["tests_passed"] == 12
    assert evidence["tests_failed"] == 0


def test_uat_13_evidence_passes() -> None:
    """UAT-13 evidencia debe estar en PASS con SHA real."""
    evidence = _assert_evidence_passes("UAT-13")
    sha = evidence["revision"]
    assert isinstance(sha, str) and len(sha) >= 12, f"SHA invalido: {sha!r}"
    assert evidence["tests_passed"] == 16
    assert evidence["tests_failed"] == 0


def test_uat_12_h6_real_tests_pass() -> None:
    """Los tests reales de H6 deben estar en verde."""
    rc, output = _run_pytest("tests/test_h6_multiproposito.py")
    assert rc == 0, (
        f"tests/test_h6_multiproposito.py FALLO (exit={rc}). "
        f"Esto contradice UAT-12 PASS. Output:\n{output[-1500:]}"
    )
    assert "12 passed" in output, f"Salida inesperada: {output[-500:]}"


def test_uat_13_h7_real_tests_pass() -> None:
    """Los tests reales de H7 deben estar en verde."""
    rc, output = _run_pytest("tests/test_h7_promocion.py")
    assert rc == 0, (
        f"tests/test_h7_promocion.py FALLO (exit={rc}). "
        f"Esto contradice UAT-13 PASS. Output:\n{output[-1500:]}"
    )
    assert "16 passed" in output, f"Salida inesperada: {output[-500:]}"


def test_h6_pack_loader_module_exists() -> None:
    """skillgraph.domain.pack_loader debe existir y exponer declare_types_from_pack.

    Post-ADR-0014: el modulo vive en el bounded context `domain`, no en la
    raiz del paquete. La capa de shim de compat se elimino.
    """
    from skillgraph.domain import pack_loader  # type: ignore[import-not-found]

    assert hasattr(pack_loader, "declare_types_from_pack")
    assert hasattr(pack_loader, "validate_instance_against_registry")


def test_h7_promotion_module_exists() -> None:
    """skillgraph.governance.promotion debe existir y exponer las 3 funciones.

    Post-ADR-0014: el modulo vive en el bounded context `governance`, no en
    la raiz del paquete. La capa de shim de compat se elimino.
    """
    from skillgraph.governance import promotion  # type: ignore[import-not-found]

    assert hasattr(promotion, "submit_proposal")
    assert hasattr(promotion, "apply_proposal")
    assert hasattr(promotion, "reconcile_pending")
