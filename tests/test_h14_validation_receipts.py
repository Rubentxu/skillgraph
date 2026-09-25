"""UAT-EVO-12..14: H14 — Evidencia operativa temporal.

Cubre los 3 gates del workitem H14 (evolution-v2/plan/ROADMAP.md):

- UAT-EVO-12: dado una suite de prueba ejecutada, cuando termina,
  se registra un recibo vinculado al comando real, revision,
  resultado y artefacto.
- UAT-EVO-13: dado un recibo que cubre solo seis tests, cuando se
  consulta que quedo demostrado, NO se declara seguridad o
  correccion global sin criterios y evidencia adicionales.
- UAT-EVO-14: dado un recibo valido en revision A, cuando cambia
  una dependencia pertinente, permanece consultable historicamente
  y no se presenta como validacion automatica de B.

Workflow SDDK: A-min (single apply, scope acotado a knowledge/ +
governance/).

Pre-condiciones:
- H13 cerrado (ScopeAwareRecipe, CoverageManifest, compile_handoff).
- Evidence(kind=...) reusado: no introduce tabla nueva.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import SkillGraphError
from skillgraph.governance.receipts import (
    ValidationReceipt,
    is_receipt_applicable,
    list_applicable_receipts,
    record_validation_receipt,
)
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ----- helpers ---------------------------------------------------------


def _storage(tmp_path: Path) -> Storage:
    return Storage(str(tmp_path / "h14.sqlite"))


def _controller(storage: Storage) -> KnowledgeController:
    return KnowledgeController(storage=storage, tenant_id="t1", project_id="p1")


# ----- UAT-EVO-12: Recibo real ---------------------------------------


class TestUatEvo12RealReceipt:
    """UAT-EVO-12: un recibo persistido tras ejecutar una suite."""

    def test_receipt_persists_command_revision_result_artifact(self, tmp_path: Path) -> None:
        """El recibo incluye los 4 campos vinculantes: cmd, revision, result, artifact."""
        storage = _storage(tmp_path)
        ctrl = _controller(storage)

        # Crear un artefacto real en disco para que artifact_path exista.
        artifact = tmp_path / "report.json"
        artifact.write_text('{"passed": 6, "failed": 0}')

        receipt_id = record_validation_receipt(
            controller=ctrl,
            command="pytest -q tests/test_foo.py",
            revision="abc1234",
            result="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path=str(artifact),
            scope="tests/test_foo.py",
        )
        assert isinstance(receipt_id, str)
        assert len(receipt_id) > 0

    def test_receipt_is_retrievable_by_id(self, tmp_path: Path) -> None:
        """El recibo es consultable por receipt_id tras ser persistido."""
        storage = _storage(tmp_path)
        ctrl = _controller(storage)
        artifact = tmp_path / "report.json"
        artifact.write_text("{}")

        rid = record_validation_receipt(
            controller=ctrl,
            command="pytest -q",
            revision="rev-a",
            result="pass",
            tests_run=1,
            tests_passed=1,
            artifact_path=str(artifact),
            scope="tests/",
        )
        receipts = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
            dependency_revisions={},
        )
        assert any(r.receipt_id == rid for r in receipts)

    def test_receipt_artifact_must_exist(self, tmp_path: Path) -> None:
        """artifact_path debe existir en disco al persistir el recibo."""
        storage = _storage(tmp_path)
        ctrl = _controller(storage)

        with pytest.raises(SkillGraphError):
            record_validation_receipt(
                controller=ctrl,
                command="pytest -q",
                revision="rev-x",
                result="pass",
                tests_run=1,
                tests_passed=1,
                artifact_path=str(tmp_path / "nonexistent.json"),
                scope="tests/",
            )


# ----- UAT-EVO-13: Certificacion acotada ---------------------------


class TestUatEvo13BoundedCertification:
    """UAT-EVO-13: NO se declara seguridad global con N tests."""

    def test_receipt_declares_tests_run_and_passed(self, tmp_path: Path) -> None:
        """El recibo expone tests_run y tests_passed explicitamente."""
        r = ValidationReceipt(
            receipt_id="r-1",
            command="pytest",
            revision="rev-a",
            timestamp="2026-09-25T13:00:00Z",
            verdict="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path="/tmp/r.json",
            scope="tests/test_foo.py",
            dependency_revisions={},
            extra_metadata={},
        )
        assert r.tests_run == 6
        assert r.tests_passed == 6

    def test_receipt_is_bounded_by_scope(self, tmp_path: Path) -> None:
        """El scope del recibo declara el ambito acotado."""
        r = ValidationReceipt(
            receipt_id="r-2",
            command="pytest",
            revision="rev-a",
            timestamp="2026-09-25T13:00:00Z",
            verdict="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path="/tmp/r.json",
            scope="tests/test_foo.py",
            dependency_revisions={},
            extra_metadata={},
        )
        assert r.scope == "tests/test_foo.py"
        # El scope es un Literal cerrado.
        assert isinstance(r.scope, str)


# ----- UAT-EVO-14: Historia y aplicabilidad -------------------------


class TestUatEvo14HistoryAndApplicability:
    """UAT-EVO-14: un recibo historico permanece consultable pero NO aplica a revision distinta."""

    def test_receipt_applicable_when_revisions_match(self) -> None:
        """receipt.revision == current_revision y deps OK -> aplicable."""
        r = ValidationReceipt(
            receipt_id="r-3",
            command="pytest",
            revision="rev-a",
            timestamp="2026-09-25T13:00:00Z",
            verdict="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path="/tmp/r.json",
            scope="tests/",
            dependency_revisions={"dep-1": "sha-dep-1"},
            extra_metadata={},
        )
        assert (
            is_receipt_applicable(
                receipt=r,
                current_revision="rev-a",
                dependency_revisions={"dep-1": "sha-dep-1"},
            )
            is True
        )

    def test_receipt_not_applicable_when_revision_changed(self) -> None:
        """receipt.revision != current_revision -> NO aplicable (UAT-EVO-14)."""
        r = ValidationReceipt(
            receipt_id="r-4",
            command="pytest",
            revision="rev-a",
            timestamp="2026-09-25T13:00:00Z",
            verdict="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path="/tmp/r.json",
            scope="tests/",
            dependency_revisions={},
            extra_metadata={},
        )
        # Cambio la revision HEAD: el recibo de A NO aplica a B.
        assert (
            is_receipt_applicable(
                receipt=r,
                current_revision="rev-b",
                dependency_revisions={},
            )
            is False
        )

    def test_receipt_not_applicable_when_dependency_changed(self) -> None:
        """Si una dependencia cambio de revision -> NO aplicable."""
        r = ValidationReceipt(
            receipt_id="r-5",
            command="pytest",
            revision="rev-a",
            timestamp="2026-09-25T13:00:00Z",
            verdict="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path="/tmp/r.json",
            scope="tests/",
            dependency_revisions={"dep-1": "sha-old"},
            extra_metadata={},
        )
        # dep-1 cambio de sha.
        assert (
            is_receipt_applicable(
                receipt=r,
                current_revision="rev-a",
                dependency_revisions={"dep-1": "sha-new"},
            )
            is False
        )

    def test_historical_receipts_remain_consultable(self, tmp_path: Path) -> None:
        """Aunque un recibo no aplique, sigue consultable historicamente."""
        storage = _storage(tmp_path)
        ctrl = _controller(storage)
        artifact = tmp_path / "r.json"
        artifact.write_text("{}")

        # Persistir un recibo en rev-a.
        rid = record_validation_receipt(
            controller=ctrl,
            command="pytest",
            revision="rev-a",
            result="pass",
            tests_run=6,
            tests_passed=6,
            artifact_path=str(artifact),
            scope="tests/",
            dependency_revisions={"dep-1": "sha-old"},
        )

        # Cambiar revision -> el recibo NO debe listarse como aplicable.
        applicable = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-b",
            dependency_revisions={"dep-1": "sha-new"},
        )
        assert not any(r.receipt_id == rid for r in applicable)

        # Pero sigue consultable por revision historica.
        historical = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",  # la revision del recibo
            dependency_revisions={"dep-1": "sha-old"},
        )
        assert any(r.receipt_id == rid for r in historical)
