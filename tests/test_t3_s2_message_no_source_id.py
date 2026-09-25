"""STEWARDSHIP-T3-S2-001 (cierre gap S2/I de ADR-0015).

Cierra el gap descubierto en T3: KnowledgeController filtra
``source_id`` en el mensaje de error cuando esa informacion cruza
el boundary tenant (S2 / Information Disclosure).

Tres sitios en src/skillgraph/knowledge/knowledge_controller.py
filtraban el source_id (enumerados en el commit message y en
audits/t3-s2-message-redaction-2026-09-25.md):

  - get_source:          f"Source no encontrada: {source_id!r}"
  - record_evidence FK:  f"Source no existe: {evidence.source_id!r}"
  - record_claim FK:     f"Source no existe: {claim.source_id!r}"

El fix cambia esos tres mensajes a una forma opaca al client
(NO expone el source_id) preservando el tipo de excepcion y el
chain (``from exc``) para que el contexto de debug siga disponible
en logs internos (vía `__cause__`, no en `str(exc)`).

Contrato verificado:
  - ``UnknownSourceError`` se sigue lanzando (no se cambia el
    comportamiento observable de control flow).
  - ``str(exc)`` no contiene el source_id pasado por el caller.
  - El chain ``__cause__`` se preserva (para diagnostico interno).

Las pruebas existentes (test_knowledge_controller.py) que solo
validan el tipo de excepcion siguen siendo validas; el contrato
nuevo es estrictamente aditivo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import UnknownSourceError
from skillgraph.knowledge.graph import Claim, Entity, Evidence, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers (locales: solo se usan aqui)
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


def _ent(eid: str = "file:src/foo.py") -> Entity:
    return Entity(entity_id=eid, kind="file", stable_key="src/foo.py")


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
# S2/I cierre: source_id NO debe aparecer en str(exc) en los 3 sitios
# ---------------------------------------------------------------------------


def test_get_source_message_does_not_leak_source_id(tmp_path: Path) -> None:
    """get_source (knowledge_controller.py:135) lanza UnknownSourceError
    sin filtrar source_id."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    leaked = "secret-source-id-do-not-leak"

    with pytest.raises(UnknownSourceError) as exc_info:
        ctl.get_source(source_id=leaked)

    msg = str(exc_info.value)
    assert leaked not in msg, (
        f"get_source filtra source_id en mensaje: {msg!r}"
    )
    assert isinstance(exc_info.value, UnknownSourceError)


def test_record_evidence_fk_message_does_not_leak_source_id(tmp_path: Path) -> None:
    """record_evidence FK violation (knowledge_controller.py:216)
    sin filtrar source_id."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    leaked = "ghost-source-id-do-not-leak"

    with pytest.raises(UnknownSourceError) as exc_info:
        ctl.record_evidence(
            evidence=Evidence(
                evidence_id="ev1",
                kind="metric",
                content={"x": 1},
                source_id=leaked,
                observed_at="2026-01-01",
            ),
        )

    msg = str(exc_info.value)
    assert leaked not in msg, (
        f"record_evidence FK filtra source_id en mensaje: {msg!r}"
    )


def test_record_claim_fk_message_does_not_leak_source_id(tmp_path: Path) -> None:
    """record_claim FK violation source (knowledge_controller.py:488)
    sin filtrar source_id. Para llegar al path source (no entity), la
    entity debe existir y la source NO."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    # Source valida (para no caer en el path de entity / source doble-failure)
    ctl.register_source(source=_src(sid="local:src/exists.py"))
    ctl.upsert_entity(entity=_ent(eid="file:src/foo.py"))
    leaked = "phantom-source-id-do-not-leak"

    with pytest.raises(UnknownSourceError) as exc_info:
        ctl.record_claim(
            claim=_claim(
                claim_id="cl1",
                subject_entity_id="file:src/foo.py",
                source_id=leaked,  # esta NO existe -> path l.488
            ),
        )

    msg = str(exc_info.value)
    assert leaked not in msg, (
        f"record_claim FK source filtra source_id en mensaje: {msg!r}"
    )


# ---------------------------------------------------------------------------
# Garantia de no-regresion: el chain ``__cause__`` se preserva para los casos FK
# ---------------------------------------------------------------------------


def test_record_evidence_fk_preserves_cause_chain(tmp_path: Path) -> None:
    """El __cause__ debe seguir apuntando a la excepcion original."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")

    with pytest.raises(UnknownSourceError) as exc_info:
        ctl.record_evidence(
            evidence=Evidence(
                evidence_id="ev1",
                kind="metric",
                content={"x": 1},
                source_id="missing",
                observed_at="2026-01-01",
            ),
        )

    assert exc_info.value.__cause__ is not None, (
        "record_evidence FK debe preservar el chain via `from exc`"
    )


def test_record_claim_fk_preserves_cause_chain(tmp_path: Path) -> None:
    """El __cause__ debe seguir apuntando a la excepcion original (path source)."""
    ctl = KnowledgeController(storage=_storage(tmp_path), tenant_id="tA", project_id="p")
    ctl.register_source(source=_src(sid="local:src/exists.py"))
    ctl.upsert_entity(entity=_ent(eid="file:src/foo.py"))

    with pytest.raises(UnknownSourceError) as exc_info:
        ctl.record_claim(
            claim=_claim(
                claim_id="cl1",
                subject_entity_id="file:src/foo.py",
                source_id="missing-source",
            ),
        )

    assert exc_info.value.__cause__ is not None, (
        "record_claim FK source debe preservar el chain via `from exc`"
    )
