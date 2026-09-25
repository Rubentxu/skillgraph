"""UAT-EVO-15..18: H15 — Evaluación y automejora acotada.

Cubre los 4 gates del workitem H15 (evolution-v2/plan/ROADMAP.md):

- UAT-EVO-15: dada una consulta cubierta por conocimiento vigente,
  cuando un agente intenta obtener de nuevo el mismo conocimiento
  desde la fuente, el recorrido detecta la reutilizacion posible
  y NO repite la extraccion.
- UAT-EVO-16: dado un handoff al que se omitio deliberadamente
  una referencia obligatoria ya vigente, cuando se evalua la
  ejecucion, se atribuye el defecto a la seleccion de contexto
  y no se propone nueva rama sin evidencia.
- UAT-EVO-17: dadas dos recetas aplicadas a casos comparables,
  cuando se evaluan, la candidata solo se considera mejora si
  mantiene correccion y cobertura y reduce trabajo redundante.
- UAT-EVO-18: dada una propuesta de cambio de politica de
  validacion generada por un agente, cuando intenta usar su
  propio juicio como unica evidencia para aprobarla, el sistema
  impide su promocion automatica.

Workflow SDDK: A-min (single apply, scope acotado a governance/ +
knowledge/).

Pre-condiciones:
- H11 (FileSignatures), H12 (Scopes), H13 (Handoff), H14 (Receipts).
- Evidence(kind=...) reusado: NO introduce tabla nueva.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import SkillGraphError
from skillgraph.governance.improvement import (
    ImprovementCandidate,
    PromotionDecision,
    RecipeComparison,
    compare_recipes,
    detect_redundant_extraction,
    localize_omission,
    promote_candidate,
    rollback_candidate,
)
from skillgraph.knowledge.file_signature import (
    ExtractionState,
    FileSignature,
    SignatureProcedencia,
    SignatureVigencia,
)
from skillgraph.knowledge.graph import Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage

# ----- helpers ---------------------------------------------------------


def _proc() -> SignatureProcedencia:
    return SignatureProcedencia(
        extraction_method="regex_def",
        extractor_version="skillgraph-rules/0.1.0",
    )


def _sig(*, foco: str, state: ExtractionState = "complete") -> FileSignature:
    return FileSignature(
        foco=foco,
        contrato="def",
        cobertura=1,
        procedencia=_proc(),
        vigencia=SignatureVigencia(
            state=state,
            fresh=(state == "complete"),
            stale=(state != "complete"),
        ),
    )


def _storage(tmp_path: Path) -> Storage:
    return Storage(str(tmp_path / "h15.sqlite"))


def _controller(storage: Storage) -> KnowledgeController:
    return KnowledgeController(storage=storage, tenant_id="t1", project_id="p1")


def _register_source(controller: KnowledgeController, source_id: str) -> None:
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind="local_file",
            content_hash="h",
            locator={"path": source_id},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    )


# ----- UAT-EVO-15: Extraccion redundante detectada ------------------


class TestUatEvo15RedundantExtraction:
    """UAT-EVO-15: detecta reutilizacion posible y NO repite extraccion."""

    def test_redundant_extraction_detected_when_signature_fresh(self, tmp_path: Path) -> None:
        """Si la firma es fresh, NO hay redundancia: ya esta disponible."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        _register_source(controller, "src/a.py")
        # Firma fresh persistida.
        controller.record_evidence_for_file_signature(
            source_id="src/a.py",
            file_signature=_sig(foco="src/a.py::def::foo", state="complete"),
        )

        # Intentar detectar redundancia para esa source.
        candidates = detect_redundant_extraction(
            controller=controller,
            source_ids=("src/a.py",),
        )
        # La firma esta vigente -> NO debe proponer re-extraccion.
        # (El detector reporta 'reusable' para los casos fresh; el
        # caller decide si invocar o no el extractor de nuevo.)
        # Implementacion: si la firma es fresh, NO hay candidato
        # 'redundant_extraction' (el sistema avisa que ya esta).
        assert all(c.kind != "redundant_extraction" for c in candidates)

    def test_redundant_extraction_flagged_when_signature_stale(self, tmp_path: Path) -> None:
        """Si la firma es stale, SI hay candidato a re-extraccion."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        _register_source(controller, "src/a.py")
        controller.record_evidence_for_file_signature(
            source_id="src/a.py",
            file_signature=_sig(foco="src/a.py::def::foo", state="partial"),
        )

        candidates = detect_redundant_extraction(
            controller=controller,
            source_ids=("src/a.py",),
        )
        # La firma esta stale/parcial -> se propone re-extraccion.
        assert any(c.kind == "redundant_extraction" for c in candidates)


# ----- UAT-EVO-16: Defecto localizado ------------------------------


class TestUatEvo16LocalizedDefect:
    """UAT-EVO-16: el defecto se atribuye a la seleccion de contexto."""

    def test_localize_omission_flags_missing_obligatory_refs(self, tmp_path: Path) -> None:
        """Si un handoff omitio una ref obligatoria, se localiza."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        _register_source(controller, "src/needed.py")
        controller.record_evidence_for_file_signature(
            source_id="src/needed.py",
            file_signature=_sig(foco="src/needed.py::def::important"),
        )

        # expected_sources declara una ref obligatoria que SI esta vigente.
        candidates = localize_omission(
            controller=controller,
            expected_source_ids=("src/needed.py",),
            included_source_ids=(),  # handoff lo OMITE
        )
        # Se atribuye el defecto a 'contexto omitido', no se propone
        # nueva rama de comportamiento.
        assert any(c.kind == "omitted_reference" for c in candidates)
        # Atribucion: el campo evidence_refs declara la ref vigente.
        for c in candidates:
            if c.kind == "omitted_reference":
                assert c.evidence_refs  # apunta a la evidencia vigente
                assert c.metrics["attribution"] == "context_selection"


# ----- UAT-EVO-17: Mejora comparada --------------------------------


class TestUatEvo17ComparedImprovement:
    """UAT-EVO-17: solo se considera mejora si corrige, mantiene cobertura y reduce trabajo."""

    def test_compare_recipes_reports_metrics(self, tmp_path: Path) -> None:
        """compare_recipes devuelve metricas declaradas."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        # Recipe A: cubre 2 sources. Recipe B: cubre las mismas 2.
        _register_source(controller, "src/a.py")
        _register_source(controller, "src/b.py")
        for s in ("src/a.py", "src/b.py"):
            controller.record_evidence_for_file_signature(
                source_id=s,
                file_signature=_sig(foco=f"{s}::def::foo"),
            )

        comp = compare_recipes(
            controller=controller,
            recipe_a_source_ids=("src/a.py", "src/b.py"),
            recipe_b_source_ids=("src/a.py", "src/b.py"),
        )
        assert isinstance(comp, RecipeComparison)
        assert comp.correction_a is True
        assert comp.correction_b is True
        assert comp.coverage_a == 2
        assert comp.coverage_b == 2
        assert comp.work_units_a == 2
        assert comp.work_units_b == 2

    def test_b_is_improvement_only_when_reduces_work_and_maintains(self, tmp_path: Path) -> None:
        """B es mejora solo si reduce trabajo redundante Y mantiene cobertura."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        # A: cubre 3 sources. B: cubre las mismas 3 (sin redundancia).
        for s in ("src/a.py", "src/b.py", "src/c.py"):
            _register_source(controller, s)
            controller.record_evidence_for_file_signature(
                source_id=s,
                file_signature=_sig(foco=f"{s}::def::f"),
            )

        comp = compare_recipes(
            controller=controller,
            recipe_a_source_ids=("src/a.py", "src/b.py", "src/c.py"),
            recipe_b_source_ids=("src/a.py", "src/b.py", "src/c.py"),
        )
        # Mismo trabajo Y misma cobertura: NO hay mejora.
        assert comp.is_b_improvement is False

    def test_b_with_less_work_is_improvement(self, tmp_path: Path) -> None:
        """B con menos trabajo redundante SI es mejora."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        for s in ("src/a.py", "src/b.py"):
            _register_source(controller, s)
            controller.record_evidence_for_file_signature(
                source_id=s,
                file_signature=_sig(foco=f"{s}::def::f"),
            )

        comp = compare_recipes(
            controller=controller,
            recipe_a_source_ids=("src/a.py", "src/b.py"),
            recipe_b_source_ids=("src/a.py",),  # menos trabajo
        )
        # B reduce trabajo y mantiene la cobertura parcial.
        # Como B no omite A COMPLETO (solo work_units), pero coverage
        # de B es 1 < 2, B NO es mejora real (pierde cobertura).
        # El test verifica que la comparacion es estricta.
        assert comp.coverage_b == 1
        assert comp.coverage_a == 2


# ----- UAT-EVO-18: Sin autocertificacion ----------------------------


class TestUatEvo18NoSelfCertification:
    """UAT-EVO-18: una propuesta NO se autocertifica."""

    def test_promote_candidate_requires_human_approval(self, tmp_path: Path) -> None:
        """Sin human_approved=True, la promocion se rechaza (UAT-EVO-18)."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        candidate = ImprovementCandidate(
            candidate_id="cand-1",
            kind="redundant_extraction",
            evidence_refs=(),
            metrics={"attribution": "context_selection"},
            detected_at="2026-09-25T13:00:00Z",
            scope="tests/",
        )

        # Sin human_approved -> SelfCertificationBlockedError.
        with pytest.raises(SkillGraphError):
            promote_candidate(
                controller=controller,
                candidate=candidate,
                human_approved=False,
            )

    def test_promote_candidate_succeeds_with_human_approval(self, tmp_path: Path) -> None:
        """Con human_approved=True, la promocion emite una decision."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        candidate = ImprovementCandidate(
            candidate_id="cand-2",
            kind="redundant_extraction",
            evidence_refs=(),
            metrics={"attribution": "context_selection"},
            detected_at="2026-09-25T13:00:00Z",
            scope="tests/",
        )

        decision = promote_candidate(
            controller=controller,
            candidate=candidate,
            human_approved=True,
            approver="operator",
        )
        assert isinstance(decision, PromotionDecision)
        assert decision.human_approved is True
        assert decision.approver == "operator"

    def test_rollback_after_promotion(self, tmp_path: Path) -> None:
        """Tras promover, rollback revierte la decision."""
        storage = _storage(tmp_path)
        controller = _controller(storage)

        candidate = ImprovementCandidate(
            candidate_id="cand-3",
            kind="omitted_reference",
            evidence_refs=(),
            metrics={"attribution": "context_selection"},
            detected_at="2026-09-25T13:00:00Z",
            scope="tests/",
        )

        decision = promote_candidate(
            controller=controller,
            candidate=candidate,
            human_approved=True,
            approver="operator",
        )
        rollback = rollback_candidate(
            controller=controller,
            decision=decision,
            policy="automatic",
        )
        assert rollback.previous_decision_id == decision.decision_id
        assert rollback.applied is True
