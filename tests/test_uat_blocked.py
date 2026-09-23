"""Tests pytest explicitos para UATs esperados BLOCKED.

Estos UATs NO pasan y NO deben pasar todavia. La razon es que
los hitos del blueprint que los cubren (H6, H7) no estan
implementados.

Este modulo cierra un gap de honestidad: si en algun momento
estos UATs cambian a PASS o FAIL (porque alguien implemento
H6/H7 parcialmente, o porque uat_audit.py cambio), CI lo
detectara automaticamente. Sin este test, el cambio pasaria
desapercibido hasta una auditoria manual.

Cobertura:
- UAT-12: Dominio especializado (H6 multipropósito Character/StoryArc).
- UAT-13: Promocion entre bases (H7 release candidate).

Para que estos tests sean robustos ante refactors futuros,
NO acoplamos al texto literal de `notes` (puede cambiar).
Acoplamos solo al status y al uat_id.
"""

from __future__ import annotations

import sys
from pathlib import Path

# tests/ no es un paquete Python; importamos el script via sys.path.
_TESTS_DIR = Path(__file__).parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import uat_audit  # type: ignore[import-not-found]  # noqa: E402


def test_uat_12_h6_multiproposito_blocked() -> None:
    """UAT-12 debe seguir BLOCKED hasta que H6 multipropósito se implemente.

    H6 = Domain Pack de software + Domain Pack narrativo/educativo
    + tipos y relaciones extensibles. Sin H6, UAT-12 NO puede pasar.
    Si este test falla con status=PASS, alguien implemento H6 sin
    actualizar el STATE/audit (signal para revisar).
    """
    evidence = uat_audit.uat_12()
    assert evidence.uat_id == "UAT-12"
    assert evidence.status == "BLOCKED", (
        f"UAT-12 status={evidence.status!r}. Si esto es PASS, "
        f"H6 multipropósito ha sido implementado y STATE.yaml "
        f"debe actualizarse (mover UAT-12 a PASS, no a BLOCKED). "
        f"observed: {evidence.observed}"
    )


def test_uat_13_h7_promocion_blocked() -> None:
    """UAT-13 debe seguir BLOCKED hasta que H7 promoción se implemente.

    H7 = release candidate, promoción entre bases, reconciliación
    tras interrupción. Sin H7, UAT-13 NO puede pasar.
    """
    evidence = uat_audit.uat_13()
    assert evidence.uat_id == "UAT-13"
    assert evidence.status == "BLOCKED", (
        f"UAT-13 status={evidence.status!r}. Si esto es PASS, "
        f"H7 promoción ha sido implementado y STATE.yaml debe "
        f"actualizarse. observed: {evidence.observed}"
    )
