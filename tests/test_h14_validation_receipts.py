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

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.governance.receipts import (
    RECEIPT_VERDICTS,
    ValidationReceipt,
    is_receipt_applicable,
    list_applicable_receipts,
    record_validation_receipt,
)
from skillgraph.knowledge.graph import Evidence, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ----- helpers ---------------------------------------------------------


def _storage(tmp_path: Path) -> Storage:
    return Storage(str(tmp_path / "h14.sqlite"))


def _controller(storage: Storage) -> KnowledgeController:
    return KnowledgeController(knowledge=storage, tenant_id="t1", project_id="p1")


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


# ----- WI-06: coverage hardening (Grupo A: dataclass validation) -------


def _valid_receipt_kwargs(**overrides: object) -> dict[str, object]:
    """Devuelve kwargs validos para construir un ValidationReceipt.

    Tests individuales sobreescriben el campo que quieren invalidar.
    """
    base: dict[str, object] = {
        "receipt_id": "r-base",
        "command": "pytest -q",
        "revision": "rev-a",
        "timestamp": "2026-09-26T13:00:00Z",
        "verdict": "pass",
        "tests_run": 6,
        "tests_passed": 6,
        "artifact_path": "/tmp/r.json",
        "scope": "tests/",
        "dependency_revisions": {},
        "extra_metadata": {},
    }
    base.update(overrides)
    return base


class TestReceiptDataclassValidation:
    """WI-06 Grupo A: ValidationReceipt.__post_init__ rechaza campos invalidos."""

    def test_receipt_id_vacio_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="receipt_id vacio"):
            ValidationReceipt(**_valid_receipt_kwargs(receipt_id=""))  # type: ignore[arg-type]

    def test_command_vacio_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="command vacio"):
            ValidationReceipt(**_valid_receipt_kwargs(command=""))  # type: ignore[arg-type]

    def test_revision_vacia_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="revision vacia"):
            ValidationReceipt(**_valid_receipt_kwargs(revision=""))  # type: ignore[arg-type]

    def test_timestamp_vacio_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="timestamp vacio"):
            ValidationReceipt(**_valid_receipt_kwargs(timestamp=""))  # type: ignore[arg-type]

    def test_verdict_invalido_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="verdict invalido"):
            ValidationReceipt(**_valid_receipt_kwargs(verdict="unknown"))  # type: ignore[arg-type]

    def test_tests_run_negativo_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="tests_run negativo"):
            ValidationReceipt(**_valid_receipt_kwargs(tests_run=-1))  # type: ignore[arg-type]

    def test_tests_passed_negativo_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="tests_passed negativo"):
            ValidationReceipt(**_valid_receipt_kwargs(tests_passed=-1))  # type: ignore[arg-type]

    def test_tests_run_bool_rechaza(self) -> None:
        """WI-49: bool hereda de int; `True` pasaria el chequeo `< 0` como 1.

        `record_validation_receipt(tests_run=True)` debe ser un
        ValidationError, no un recibo con 1 test corrido que nadie
        ejecuto. Misma clase que resourceRevision/max_visits.
        """
        with pytest.raises(ValidationError, match="tests_run debe ser int, no bool"):
            ValidationReceipt(**_valid_receipt_kwargs(tests_run=True))  # type: ignore[arg-type]

    def test_tests_passed_bool_rechaza(self) -> None:
        """WI-49: `tests_passed=True` tampoco es un contador valido."""
        with pytest.raises(ValidationError, match="tests_passed debe ser int, no bool"):
            ValidationReceipt(**_valid_receipt_kwargs(tests_passed=True))  # type: ignore[arg-type]

    def test_tests_passed_mayor_que_run_rechaza(self) -> None:
        with pytest.raises(ValidationError, match=r"tests_passed .* > tests_run"):
            ValidationReceipt(**_valid_receipt_kwargs(tests_run=3, tests_passed=4))  # type: ignore[arg-type]

    def test_artifact_path_vacio_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="artifact_path vacio"):
            ValidationReceipt(**_valid_receipt_kwargs(artifact_path=""))  # type: ignore[arg-type]

    def test_scope_vacio_rechaza(self) -> None:
        with pytest.raises(ValidationError, match="scope vacio"):
            ValidationReceipt(**_valid_receipt_kwargs(scope=""))  # type: ignore[arg-type]

    def test_is_pass_true_when_verdict_pass(self) -> None:
        """Grupo E: is_pass == verdict == 'pass'."""
        r = ValidationReceipt(**_valid_receipt_kwargs(verdict="pass"))  # type: ignore[arg-type]
        assert r.is_pass is True

    def test_is_pass_false_when_verdict_fail(self) -> None:
        """Grupo E: is_pass == verdict == 'fail' (cubre L122)."""
        r = ValidationReceipt(**_valid_receipt_kwargs(verdict="fail", tests_passed=0))  # type: ignore[arg-type]
        assert r.is_pass is False

    def test_coverage_ratio_vacio_es_uno(self) -> None:
        """Grupo E: tests_run == 0 -> coverage_ratio == 1.0 (regla defensiva)."""
        r = ValidationReceipt(**_valid_receipt_kwargs(tests_run=0, tests_passed=0))  # type: ignore[arg-type]
        assert r.coverage_ratio == 1.0

    def test_coverage_ratio_fraction_when_positive(self) -> None:
        """Grupo E: coverage_ratio = passed/run."""
        r = ValidationReceipt(**_valid_receipt_kwargs(tests_run=4, tests_passed=3))  # type: ignore[arg-type]
        assert r.coverage_ratio == 0.75

    def test_to_payload_roundtrip(self) -> None:
        """Grupo bonus: to_payload serializa todos los campos."""
        r = ValidationReceipt(**_valid_receipt_kwargs(extra_metadata={"k": 1}))  # type: ignore[arg-type]
        payload = r.to_payload()
        assert payload["receipt_id"] == "r-base"
        assert payload["verdict"] == "pass"
        assert payload["extra_metadata"] == {"k": 1}


# ----- WI-06: Grupo B (is_receipt_applicable rama deps) -----------------


class TestIsReceiptApplicableDeps:
    """WI-06 Grupo B: branch dependency_revisions provided, caller pasa None."""

    def test_not_applicable_when_deps_provided_but_caller_none(self) -> None:
        """Si el receipt declara deps y el caller no las aporta -> NO aplicable (L184)."""
        r = ValidationReceipt(**_valid_receipt_kwargs(dependency_revisions={"dep-1": "sha-a"}))  # type: ignore[arg-type]
        assert (
            is_receipt_applicable(
                receipt=r,
                current_revision="rev-a",
                dependency_revisions=None,
            )
            is False
        )


# ----- WI-06: Grupo C (record_validation_receipt early validation) ----


def _ctrl(tmp_path: Path) -> KnowledgeController:
    storage = Storage(str(tmp_path / "h14-wi06.sqlite"))
    return KnowledgeController(knowledge=storage, tenant_id="t1", project_id="p1")


class TestRecordEarlyValidation:
    """WI-06 Grupo C: record_validation_receipt corta temprano en inputs invalidos."""

    def test_command_vacio(self, tmp_path: Path) -> None:
        ctrl = _ctrl(tmp_path)
        artifact = tmp_path / "r.json"
        artifact.write_text("{}")
        with pytest.raises(ValidationError, match="command vacio"):
            record_validation_receipt(
                controller=ctrl,
                command="",
                revision="rev-a",
                result="pass",
                tests_run=1,
                tests_passed=1,
                artifact_path=str(artifact),
                scope="tests/",
            )

    def test_revision_vacia(self, tmp_path: Path) -> None:
        ctrl = _ctrl(tmp_path)
        artifact = tmp_path / "r.json"
        artifact.write_text("{}")
        with pytest.raises(ValidationError, match="revision vacia"):
            record_validation_receipt(
                controller=ctrl,
                command="pytest",
                revision="",
                result="pass",
                tests_run=1,
                tests_passed=1,
                artifact_path=str(artifact),
                scope="tests/",
            )

    def test_result_invalido(self, tmp_path: Path) -> None:
        ctrl = _ctrl(tmp_path)
        artifact = tmp_path / "r.json"
        artifact.write_text("{}")
        with pytest.raises(ValidationError, match="result invalido"):
            record_validation_receipt(
                controller=ctrl,
                command="pytest",
                revision="rev-a",
                result="unknown",  # type: ignore[arg-type]
                tests_run=1,
                tests_passed=1,
                artifact_path=str(artifact),
                scope="tests/",
            )

    def test_artifact_path_vacio(self, tmp_path: Path) -> None:
        ctrl = _ctrl(tmp_path)
        with pytest.raises(ValidationError, match="artifact_path vacio"):
            record_validation_receipt(
                controller=ctrl,
                command="pytest",
                revision="rev-a",
                result="pass",
                tests_run=1,
                tests_passed=1,
                artifact_path="",
                scope="tests/",
            )

    def test_scope_vacio(self, tmp_path: Path) -> None:
        ctrl = _ctrl(tmp_path)
        artifact = tmp_path / "r.json"
        artifact.write_text("{}")
        with pytest.raises(ValidationError, match="scope vacio"):
            record_validation_receipt(
                controller=ctrl,
                command="pytest",
                revision="rev-a",
                result="pass",
                tests_run=1,
                tests_passed=1,
                artifact_path=str(artifact),
                scope="",
            )


# ----- WI-06: Grupo D (list_applicable_receipts defensive paths) -------


class TestListApplicableDefensive:
    """WI-06 Grupo D: list_applicable_receipts omite filas corruptas/foreign."""

    def _seed_source(
        self,
        storage: Storage,
        *,
        source_id: str,
        kind: str = "local_file",
    ) -> None:
        storage.register_source(
            tenant_id="t1",
            project_id="p1",
            source=Source(
                source_id=source_id,
                kind=kind,
                content_hash=source_id,
                locator={"path": f"/tmp/{source_id}"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-09-26T13:00:00Z",
                freshness="fresh",
            ),
        )

    def test_omite_evidence_con_kind_distinto(self, tmp_path: Path) -> None:
        """Grupo D: row.kind != 'validation_receipt' -> se omite (L367)."""
        storage = Storage(str(tmp_path / "h14-wi06-d1.sqlite"))
        self._seed_source(storage, source_id="s-other")
        storage.record_evidence(
            tenant_id="t1",
            project_id="p1",
            evidence=Evidence(
                evidence_id="ev-other",
                kind="metric",
                content={"value": 1},
                source_id="s-other",
                observed_at="2026-09-26T13:00:00Z",
            ),
        )
        out = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
        )
        assert out == ()

    def test_omite_evidence_con_content_json_no_string(self, tmp_path: Path) -> None:
        """Grupo D: row.content_json no es str -> se omite (L370).

        Inyectamos manualmente un row con content_json numerico via SQLite
        directo (defensa frente a migracion corrupta).
        """
        storage = Storage(str(tmp_path / "h14-wi06-d2.sqlite"))
        self._seed_source(storage, source_id="s-bad")
        # Acceso surgical para sembrar el caso defensivo (Storage encapsula
        # SQL, pero el _conn sigue siendo accesible para tests con
        # precondiciones explícitas; ver tests/_helpers).
        storage._conn.execute(  # type: ignore[attr-defined]
            "INSERT INTO evidences (evidence_id, tenant_id, project_id, kind, "
            "content_json, source_id, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("ev-bad", "t1", "p1", "validation_receipt", 42, "s-bad", "2026-09-26T13:00:00Z"),
        )
        storage._conn.commit()  # type: ignore[attr-defined]
        out = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
        )
        assert out == ()

    def test_omite_evidence_con_json_invalido(self, tmp_path: Path) -> None:
        """Grupo D: json.JSONDecodeError -> se omite (L373-374)."""
        storage = Storage(str(tmp_path / "h14-wi06-d3.sqlite"))
        self._seed_source(storage, source_id="s-broken")
        storage._conn.execute(  # type: ignore[attr-defined]
            "INSERT INTO evidences (evidence_id, tenant_id, project_id, kind, "
            "content_json, source_id, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "ev-broken",
                "t1",
                "p1",
                "validation_receipt",
                "{not valid json",
                "s-broken",
                "2026-09-26T13:00:00Z",
            ),
        )
        storage._conn.commit()  # type: ignore[attr-defined]
        out = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
        )
        assert out == ()

    def test_omite_evidence_con_payload_incompleto(self, tmp_path: Path) -> None:
        """Grupo D: _payload_to_receipt lanza KeyError/ValueError -> se omite (L377-378)."""
        storage = Storage(str(tmp_path / "h14-wi06-d4.sqlite"))
        self._seed_source(storage, source_id="s-incomplete")
        storage._conn.execute(  # type: ignore[attr-defined]
            "INSERT INTO evidences (evidence_id, tenant_id, project_id, kind, "
            "content_json, source_id, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "ev-incomplete",
                "t1",
                "p1",
                "validation_receipt",
                '{"receipt_id": "x"}',  # faltan todos los demas campos
                "s-incomplete",
                "2026-09-26T13:00:00Z",
            ),
        )
        storage._conn.commit()  # type: ignore[attr-defined]
        out = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
        )
        assert out == ()

    def test_scope_filter_excluye_receipts_de_otro_scope(self, tmp_path: Path) -> None:
        """Grupo D: scope != filter -> se omite (L380).

        Persistir un recibo real con scope 'X', luego consultar con scope='Y'.
        """
        storage = Storage(str(tmp_path / "h14-wi06-d5.sqlite"))
        ctrl = KnowledgeController(knowledge=storage, tenant_id="t1", project_id="p1")
        artifact = tmp_path / "r.json"
        artifact.write_text("{}")
        rid = record_validation_receipt(
            controller=ctrl,
            command="pytest",
            revision="rev-a",
            result="pass",
            tests_run=1,
            tests_passed=1,
            artifact_path=str(artifact),
            scope="scope-X",
        )
        out = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
            scope="scope-Y",
        )
        assert out == ()
        # Sanity: con scope='X' aparece.
        out_same = list_applicable_receipts(
            storage=storage,
            tenant_id="t1",
            project_id="p1",
            current_revision="rev-a",
            scope="scope-X",
        )
        assert any(r.receipt_id == rid for r in out_same)


# ----- WI-06: bonus (RECEIPT_VERDICTS shape) ----------------------------


class TestReceiptVerdictsConstant:
    """RECEIPT_VERDICTS es la fuente canonica de la Literal cerrada."""

    def test_verdicts_contiene_pass_y_fail(self) -> None:
        assert frozenset({"pass", "fail"}) == RECEIPT_VERDICTS

    def test_verdicts_es_frozenset(self) -> None:
        # Garantiza inmutabilidad en runtime.
        assert isinstance(RECEIPT_VERDICTS, frozenset)
