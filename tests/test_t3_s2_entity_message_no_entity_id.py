"""STEWARDSHIP-T3-S2-002 (cierre gap entidad de S2/I de ADR-0015).

Mismo patron que STEWARDSHIP-T3-S2-001 pero para ``entity_id`` (no
source_id). Al cerrar el gap source_id en dcbf81a, descubrimos que
``KnowledgeController.get_entity`` y la rama entity de
``record_claim`` (FK violation) filtran el ``entity_id`` del tenant
atacado en su mensaje de error.

Este ciclo cierra ese gap con el mismo criterio que el source_id:
- Tipo de excepcion invariante.
- Chain ``__cause__`` preservado en paths FK.
- ``str(exc)`` NO contiene el entity_id pasado por el caller.

Contrato verificado:
  - ``UnknownEntityError`` se sigue lanzando (control flow invariante).
  - ``str(exc)`` no contiene el entity_id pasado por el caller.
  - El chain ``__cause__`` se preserva en el path FK de record_claim.

Las pruebas existentes (test_knowledge_controller.py) que solo
validan el tipo de excepcion siguen siendo validas; el contrato
nuevo es estrictamente aditivo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import UnknownEntityError
from skillgraph.knowledge.graph import Claim, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers (locales)
# ---------------------------------------------------------------------------


def _storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "k.sqlite")


def _src(sid: str = "local:src/foo.py") -> Source:
    return Source(
        source_id=sid,
        kind="local_file",
        content_hash="abc",
        locator={"path": "src/foo.py"},
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-01-01T00:00:00Z",
        freshness="fresh",
    )


def _claim(
    *,
    claim_id: str,
    subject_entity_id: str,
    source_id: str,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject_entity_id=subject_entity_id,
        predicate="file_exists",
        object_literal=True,
        source_id=source_id,
        checked_at_revision="rev-1",
    )


# ---------------------------------------------------------------------------
# S2/I cierre (entity): entity_id NO debe aparecer en str(exc) en los 2 sitios
# ---------------------------------------------------------------------------


def test_get_entity_message_does_not_leak_entity_id(tmp_path: Path) -> None:
    """get_entity (knowledge_controller.py:179) lanza UnknownEntityError
    sin filtrar entity_id."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    leaked = "secret-entity-id-do-not-leak"

    with pytest.raises(UnknownEntityError) as exc_info:
        ctl.get_entity(entity_id=leaked)

    msg = str(exc_info.value)
    assert leaked not in msg, f"get_entity filtra entity_id en mensaje: {msg!r}"
    assert isinstance(exc_info.value, UnknownEntityError)


def test_record_claim_fk_entity_message_does_not_leak_entity_id(tmp_path: Path) -> None:
    """record_claim FK violation entity (knowledge_controller.py:490)
    sin filtrar entity_id. Para llegar al path entity, la entity NO debe
    existir; la source puede o no existir, pero SQLite evalua FKs por
    orden de insercion y la entity viene primero en el tuple."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    ctl.register_source(source=_src(sid="local:src/exists.py"))
    leaked = "phantom-entity-id-do-not-leak"

    with pytest.raises(UnknownEntityError) as exc_info:
        ctl.record_claim(
            claim=_claim(
                claim_id="cl1",
                subject_entity_id=leaked,  # NO existe -> path l.490
                source_id="local:src/exists.py",
            ),
        )

    msg = str(exc_info.value)
    assert leaked not in msg, f"record_claim FK entity filtra entity_id en mensaje: {msg!r}"


# ---------------------------------------------------------------------------
# Garantia de no-regresion: chain ``__cause__`` se preserva en path FK
# ---------------------------------------------------------------------------


def test_record_claim_fk_entity_preserves_cause_chain(tmp_path: Path) -> None:
    """El __cause__ debe seguir apuntando a la excepcion original (path entity)."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    ctl.register_source(source=_src(sid="local:src/exists.py"))

    with pytest.raises(UnknownEntityError) as exc_info:
        ctl.record_claim(
            claim=_claim(
                claim_id="cl1",
                subject_entity_id="missing-entity",
                source_id="local:src/exists.py",
            ),
        )

    assert exc_info.value.__cause__ is not None, (
        "record_claim FK entity debe preservar el chain via `from exc`"
    )


def test_get_entity_no_cause_chain(tmp_path: Path) -> None:
    """get_entity NO debe tener __cause__ (no es FK, es lookup directo)."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")

    with pytest.raises(UnknownEntityError) as exc_info:
        ctl.get_entity(entity_id="missing-entity")

    # Lookup directo: no hay excepcion interna que chain-ar.
    assert exc_info.value.__cause__ is None, "get_entity no deberia preservar chain (no es path FK)"
