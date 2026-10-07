"""WI-47: los `except` deben discriminar por TIPO, no por texto del mensaje.

Tres defectos, los tres en el mismo patron: capturar `Exception` entera
y decidir el significado mirando `str(exc)`. La consecuencia es siempre
la misma: un error que no es el que se busca se reporta como si lo fuera.

1. `KnowledgeController.record_evidence` / `record_claim`:
   `"FOREIGN KEY" in str(exc)` convertia CUALQUIER error con esa
   cadena en el mensaje en `UnknownSourceError` / `UnknownEntityError`.
   Un `IntegrityError` de un CHECK, o un `ValueError` que mencionara
   la cadena, apuntaba al usuario a una causa falsa.

2. `context_controller`: los branches `entity` y `source` capturaban
   `Exception` entera para devolver `[]`. Un fallo de I/O se
   disfrazaba de "esa entidad no existe" y el compile terminaba con un
   grafo incompleto, sin error ni aviso.

TDD: los tests de abajo fallan contra el codigo anterior.
"""

from __future__ import annotations

from typing import Any

import pytest

from skillgraph.core.errors import (
    IntegrityError,
    UnknownEntityError,
    UnknownSourceError,
    ValidationError,
)


class _FakeKnowledge:
    """Storage que acepta todo y devuelve None en los lookups.

    **R0: EL FAKE LANZA EL ERROR DE DOMINIO, NO EL DE SQLITE.**

    Antes este fake lanzaba `sqlite3.IntegrityError` porque eso era lo que
    hacia el storage real. **R0 quito esa frontera**: `knowledge_controller`
    ya no importa `sqlite3`, y el que traduce es el adapter, via
    `traduciendo_integridad`. Un fake que siga lanzando el error de SQLite
    estaria probando un contrato que el codigo ya no tiene — y pasaria en
    verde mientras el camino realfalls.

    La traduccion se prueba en su sitio: `TestTraduciendoIntegridad` en
    `tests/test_r1_architecture.py`, contra SQLite de verdad.
    """

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def record_evidence(self, **kwargs: Any) -> None:
        raise self._exc

    def record_claim(self, **kwargs: Any) -> None:
        raise self._exc

    def get_entity(self, **kwargs: Any) -> None:
        return None


def _controller(exc: Exception) -> Any:
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    return KnowledgeController(
        knowledge=_FakeKnowledge(exc),  # type: ignore[arg-type]
        tenant_id="t1",
        project_id="p1",
    )


def _evidence() -> Any:
    from skillgraph.knowledge.graph import Evidence

    return Evidence(
        evidence_id="ev1",
        kind="note",
        content="c",
        source_id="src-missing",
        observed_at="2026-01-01T00:00:00Z",
    )


def _claim() -> Any:
    from skillgraph.knowledge.graph import Claim

    return Claim(
        claim_id="cl1",
        subject_entity_id="ent-missing",
        predicate="defines_symbol",
        object_literal="o",
        source_id="src-missing",
    )


class TestRecordEvidenceDiscriminatesByType:
    """Una violacion de FK real se sigue reportando como Source ausente."""

    def test_real_fk_violation_becomes_unknown_source(self) -> None:
        ctrl = _controller(IntegrityError("FOREIGN KEY constraint failed"))
        with pytest.raises(UnknownSourceError):
            ctrl.record_evidence(evidence=_evidence())

    def test_non_fk_integrity_error_propagates_untouched(self) -> None:
        """CHECK violation: mismo tipo, mensaje distinto. Debe propagar."""
        ctrl = _controller(IntegrityError("CHECK constraint failed: kind"))
        with pytest.raises(IntegrityError) as ei:
            ctrl.record_evidence(evidence=_evidence())

        assert "CHECK" in str(ei.value)
        assert "Source" not in str(ei.value)

    def test_domain_error_mentioning_foreign_key_is_not_blamed_on_source(self) -> None:
        """El caso que el codigo anterior no podia distinguir.

        Un `ValidationError` cuyo mensaje mencione "FOREIGN KEY" no es
        una violacion de FK. Antes se reportaba como
        UnknownSourceError, senalando a una entity que si existe.
        """
        ctrl = _controller(ValidationError("columna FOREIGN KEY ausente en el pack"))
        with pytest.raises(ValidationError) as ei:
            ctrl.record_evidence(evidence=_evidence())

        assert "FOREIGN KEY" in str(ei.value)

    def test_operational_error_propagates(self) -> None:
        """Fallo de I/O: no es un problema de dominio, debe propagar."""
        ctrl = _controller(OSError("disk full"))
        with pytest.raises(OSError):
            ctrl.record_evidence(evidence=_evidence())


class TestRecordClaimDiscriminatesByType:
    def test_real_fk_violation_becomes_unknown_entity(self) -> None:
        ctrl = _controller(IntegrityError("FOREIGN KEY constraint failed"))
        with pytest.raises(UnknownEntityError):
            ctrl.record_claim(claim=_claim())

    def test_non_fk_integrity_error_propagates_untouched(self) -> None:
        ctrl = _controller(IntegrityError("UNIQUE constraint failed: claim_id"))
        with pytest.raises(IntegrityError) as ei:
            ctrl.record_claim(claim=_claim())
        assert "UNIQUE" in str(ei.value)
        assert "no existe" not in str(ei.value).lower()

    def test_domain_error_mentioning_foreign_key_is_not_blamed_on_entity(self) -> None:
        ctrl = _controller(ValidationError("la FK FOREIGN KEY declarada no existe"))
        with pytest.raises(ValidationError):
            ctrl.record_claim(claim=_claim())


class TestContextControllerBranchesDoNotSwallowFailures:
    """Un branch ausente devuelve []; un fallo real NO se disfraza de eso."""

    @staticmethod
    def _resolver() -> Any:
        from skillgraph.knowledge.context_controller import ContextController

        return ContextController.__new__(ContextController)

    @staticmethod
    def _ctrl_raising_entity(exc: Exception) -> Any:
        ctrl = object.__new__(type("Ctrl", (), {}))

        def get_entity(*a: Any, **k: Any) -> Any:
            raise exc

        ctrl.get_entity = get_entity  # type: ignore[attr-defined]
        ctrl.list_claims_for_subject = lambda **k: []  # type: ignore[attr-defined]
        return ctrl

    @staticmethod
    def _ctrl_raising_source(exc: Exception) -> Any:
        ctrl = object.__new__(type("Ctrl", (), {}))

        def get_source(*a: Any, **k: Any) -> Any:
            raise exc

        ctrl.get_source = get_source  # type: ignore[attr-defined]
        ctrl.list_claims_for_source = lambda **k: []  # type: ignore[attr-defined]
        return ctrl

    def test_missing_entity_yields_empty_branch(self) -> None:
        resolver = self._resolver()
        ctrl = self._ctrl_raising_entity(UnknownEntityError("no existe"))
        assert resolver._resolve_entity_selector(ctrl, "ent1") == []

    def test_operational_failure_is_not_reported_as_missing_entity(self) -> None:
        """El defecto: un OSError se disfrazaba de entidad inexistente."""
        resolver = self._resolver()
        ctrl = self._ctrl_raising_entity(OSError("connection reset"))
        with pytest.raises(OSError):
            resolver._resolve_entity_selector(ctrl, "ent1")

    def test_missing_source_yields_empty_branch(self) -> None:
        resolver = self._resolver()
        ctrl = self._ctrl_raising_source(UnknownSourceError("no existe"))
        assert resolver._resolve_source_selector(ctrl, "src1", "") == []

    def test_operational_failure_is_not_reported_as_missing_source(self) -> None:
        resolver = self._resolver()
        ctrl = self._ctrl_raising_source(OSError("connection reset"))
        with pytest.raises(OSError):
            resolver._resolve_source_selector(ctrl, "src1", "")
