"""STEWARDSHIP-T3-S2-003 (cierre sub-gap claim_id de S2/I de ADR-0015).

Auditoria sistematica de los identificadores que cruzan el boundary
tenant en KnowledgeController. Despues de cerrar source_id (S2-001)
y entity_id (S2-002), queda 1 sitio pendiente en
``src/skillgraph/knowledge/knowledge_controller.py:508``:

    raise UnknownClaimError(f"Claim no encontrado: {claim_id!r}")

Mismo patron conceptual que source_id y entity_id: el caller de un
tenant A pidiendo un claim_id de tenant B aprende que ese claim_id
existe en OTRO tenant. Es la misma clase de fuga S2/I.

Estrategia identica a S2-001 y S2-002:
- Tipo de excepcion invariante (UnknownClaimError).
- ``str(exc)`` NO expone el claim_id pasado por el caller.
- Chain ``__cause__`` no aplica (lookup directo, no es path FK).

Auditoria completa: tras este ciclo, **todos** los mensajes de
error del KnowledgeController que filtran identificadores estaran
cerrados:

  S2-001 (dcbf81a): source_id en l.135, l.216, l.488
  S2-002 (eac6838): entity_id en l.179, l.490
  S2-003 (este):    claim_id en l.508

Los ``TypeError`` y ``ValidationError`` en otras lineas del
controlador (e.g. l.261, l.391) NO son gaps S2/I: son errores
de programador (kind/selector invalido) que no cruzan boundary
tenant en el sentido de Information Disclosure entre tenants.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import UnknownClaimError
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "k.sqlite")


# ---------------------------------------------------------------------------
# S2/I cierre (claim): claim_id NO debe aparecer en str(exc)
# ---------------------------------------------------------------------------


def test_get_claim_message_does_not_leak_claim_id(tmp_path: Path) -> None:
    """get_claim (knowledge_controller.py:508) lanza UnknownClaimError
    sin filtrar claim_id."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    leaked = "secret-claim-id-do-not-leak"

    with pytest.raises(UnknownClaimError) as exc_info:
        ctl.get_claim(claim_id=leaked)

    msg = str(exc_info.value)
    assert leaked not in msg, (
        f"get_claim filtra claim_id en mensaje: {msg!r}"
    )
    assert isinstance(exc_info.value, UnknownClaimError)


def test_get_claim_no_cause_chain(tmp_path: Path) -> None:
    """get_claim NO debe tener __cause__ (lookup directo, no FK)."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")

    with pytest.raises(UnknownClaimError) as exc_info:
        ctl.get_claim(claim_id="missing-claim")

    # Lookup directo: no hay excepcion interna que chain-ar.
    assert exc_info.value.__cause__ is None, (
        "get_claim no deberia preservar chain (no es path FK)"
    )
