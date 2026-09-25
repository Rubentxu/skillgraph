"""UAT-EVO-09..11: H13 — Handoff experto desde consultas.

Cubre los 3 gates del workitem H13 (evolution-v2/plan/ROADMAP.md):

- UAT-EVO-09: un nodo que exige firmas, cuando compila su handoff,
  recibe conocimiento completo VIGENTE con fuentes, revisiones y
  limites de cobertura (CoverageManifest explicito).
- UAT-EVO-10: cuando falta conocimiento obligatorio, el handoff
  se bloquea con explicitud (HandoffBlockedError) o se programa
  su adquisicion autorizada. NUNCA se presenta como completo.
- UAT-EVO-11: consulta determinista de firmas completas ->
  respuesta estructurada SIN invocar al adaptador LLM.

Workflow SDDK: A-min (single apply, scope acotado a knowledge/ +
runtime/handoff.py opcionalmente).

Pre-condiciones:
- H11 cerrado (FileSignature + extract_file_signatures + persistencia).
- H12 cerrado (FileScope + ScopeQuery + aggregate_signatures +
  KnowledgeController.aggregate_file_signatures con aislamiento).
- ContextRecipe + ContextController.compile_handoff existentes
  (no se tocan: H13 los envuelve por composicion).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.context_controller import ContextController
from skillgraph.knowledge.file_handoff import (
    CoverageManifest,
    HandoffBlockedError,
    ScopeAwareRecipe,
    build_coverage_manifest,
    compile_handoff_from_scopes,
    should_skip_adapter,
)
from skillgraph.knowledge.file_scope import ScopeQuery
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


def _proc(method: str = "regex_def") -> SignatureProcedencia:
    return SignatureProcedencia(
        extraction_method=method,
        extractor_version="skillgraph-rules/0.1.0",
    )


def _vig(
    state: ExtractionState = "complete",
) -> SignatureVigencia:
    return SignatureVigencia(state=state, fresh=(state == "complete"), stale=(state != "complete"))


def _sig(
    *,
    foco: str,
    contrato: str = "def",
    cobertura: int = 1,
    state: ExtractionState = "complete",
) -> FileSignature:
    return FileSignature(
        foco=foco,
        contrato=contrato,
        cobertura=cobertura,
        procedencia=_proc(),
        vigencia=_vig(state),
    )


def _register_source(
    controller: KnowledgeController,
    source_id: str,
    *,
    kind: str = "local_file",
) -> None:
    controller.register_source(
        source=Source(
            source_id=source_id,
            kind=kind,
            content_hash="h1",
            locator={"path": source_id},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    )


def _seed_signature(
    controller: KnowledgeController,
    *,
    source_id: str,
    foco: str,
    cobertura: int = 1,
    state: ExtractionState = "complete",
) -> None:
    _register_source(controller, source_id)
    controller.record_evidence_for_file_signature(
        source_id=source_id,
        file_signature=_sig(foco=foco, cobertura=cobertura, state=state),
    )


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(str(tmp_path / "h13.sqlite"))


@pytest.fixture
def controller(storage: Storage) -> KnowledgeController:
    return KnowledgeController(storage=storage, tenant_id="t1", project_id="p1")


@pytest.fixture
def ctx_controller(controller: KnowledgeController) -> ContextController:
    return ContextController(knowledge=controller)


# ----- UAT-EVO-09: Handoff experto ----------------------------------


class TestUatEvo09HandoffExpert:
    """UAT-EVO-09: el handoff compilado incluye manifest explicito."""

    def test_handoff_receives_coverage_manifest_with_sources_and_revisions(
        self, controller: KnowledgeController, ctx_controller: ContextController
    ) -> None:
        """El manifest declara fuentes, revisiones y limites de cobertura."""
        # Sembrar 3 sources con firmas completas.
        _seed_signature(controller, source_id="src/a.py", foco="src/a.py::def::foo")
        _seed_signature(controller, source_id="src/b.py", foco="src/b.py::def::bar")
        _seed_signature(controller, source_id="src/c.py", foco="src/c.py::def::baz")

        recipe = ScopeAwareRecipe(
            base_recipe=ContextRecipe(recipe_ref="node-foo"),
            scope_queries=(
                ScopeQuery(scope_kind="directory", target="src/"),
            ),
            member_source_ids=("src/a.py", "src/b.py", "src/c.py"),
        )

        handoff, manifest = compile_handoff_from_scopes(
            context_controller=ctx_controller,
            scope_recipe=recipe,
            run_id="run-1",
            node_execution_id="ne-1",
        )

        # Manifest explicito.
        assert isinstance(manifest, CoverageManifest)
        # Cobertura total = suma de coberturas (3 firmas x 1 cobertura cada una).
        assert manifest.cobertura_total == 3
        # Procedencia preservada por firma.
        assert len(manifest.procedencia_por_firma) == 3
        # Las firmas declaradas son las fuentes.
        assert set(manifest.fuentes) == {"src/a.py", "src/b.py", "src/c.py"}
        # Limites: budget y freshness.
        assert manifest.limites["token_budget"] == recipe.base_recipe.token_budget
        # Handoff compila OK y es valido.
        assert handoff.knowledge.recipe_ref == "node-foo"
        # Manifest representa el alcance del handoff.
        assert len(manifest.signatures) == 3

    def test_handoff_only_includes_fresh_signatures(
        self, controller: KnowledgeController, ctx_controller: ContextController
    ) -> None:
        """Solo se incluyen firmas con vigencia fresh (state='complete')."""
        _seed_signature(controller, source_id="src/a.py", foco="src/a.py::def::foo")
        _seed_signature(
            controller, source_id="src/b.py", foco="src/b.py::def::bar", state="partial"
        )

        recipe = ScopeAwareRecipe(
            base_recipe=ContextRecipe(recipe_ref="node-foo"),
            scope_queries=(ScopeQuery(scope_kind="directory", target="src/"),),
            member_source_ids=("src/a.py", "src/b.py"),
        )

        _handoff, manifest = compile_handoff_from_scopes(
            context_controller=ctx_controller,
            scope_recipe=recipe,
            run_id="run-1",
            node_execution_id="ne-1",
        )
        # Solo fresh cuenta en cobertura. b.py tiene partial -> no fresh.
        # Manifest reporta cobertura total sobre TODAS las firmas,
        # pero exclude_fresh=True filtra para el handoff.
        fresh_count = sum(1 for s in manifest.signatures if s.vigencia.fresh)
        assert fresh_count == 1


# ----- UAT-EVO-10: Carencia visible ----------------------------------


class TestUatEvo10GapVisible:
    """UAT-EVO-10: carencia se bloquea, nunca se oculta."""

    def test_missing_required_scope_raises_handoff_blocked(
        self, controller: KnowledgeController, ctx_controller: ContextController
    ) -> None:
        """Scope obligatorio sin firmas -> HandoffBlockedError explicito."""
        # NO sembramos firmas: la consulta es sobre src/ pero no hay firmas.
        _register_source(controller, "src/a.py")
        _register_source(controller, "src/b.py")

        recipe = ScopeAwareRecipe(
            base_recipe=ContextRecipe(recipe_ref="node-foo"),
            scope_queries=(ScopeQuery(scope_kind="directory", target="src/"),),
            member_source_ids=("src/a.py", "src/b.py"),
            require_complete_coverage=True,
        )

        with pytest.raises(HandoffBlockedError) as exc_info:
            compile_handoff_from_scopes(
                context_controller=ctx_controller,
                scope_recipe=recipe,
                run_id="run-1",
                node_execution_id="ne-1",
            )
        # El error NUNCA dice 'completado' cuando hay carencia.
        assert "completado" not in str(exc_info.value).lower()
        # El error lista las firmas/carencias.
        assert "src/a.py" in str(exc_info.value) or "firma" in str(exc_info.value).lower()

    def test_partial_coverage_blocked_when_required(
        self, controller: KnowledgeController, ctx_controller: ContextController
    ) -> None:
        """Cobertura parcial + require_complete -> bloqueo explicito."""
        _register_source(controller, "src/a.py")
        _register_source(controller, "src/b.py")
        # Solo a.py tiene firma (b.py sin firma = ausencia).
        _seed_signature(controller, source_id="src/a.py", foco="src/a.py::def::foo")

        recipe = ScopeAwareRecipe(
            base_recipe=ContextRecipe(recipe_ref="node-foo"),
            scope_queries=(ScopeQuery(scope_kind="directory", target="src/"),),
            member_source_ids=("src/a.py", "src/b.py"),
            require_complete_coverage=True,
        )

        with pytest.raises(HandoffBlockedError):
            compile_handoff_from_scopes(
                context_controller=ctx_controller,
                scope_recipe=recipe,
                run_id="run-1",
                node_execution_id="ne-1",
            )


# ----- UAT-EVO-11: Respuesta sin LLM ----------------------------------


class TestUatEvo11NoLLM:
    """UAT-EVO-11: firmas completas -> respuesta determinista sin LLM."""

    def test_should_skip_adapter_when_complete(self) -> None:
        """should_skip_adapter True si manifest completo y fresh."""
        # Manifest sintetico con todas las firmas fresh.
        sigs = (
            _sig(foco="src/a.py::def::foo"),
            _sig(foco="src/b.py::def::bar"),
        )
        recipe = ContextRecipe(recipe_ref="node-foo")
        manifest = build_coverage_manifest(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            signatures=sigs,
            required_coverage=2,
            recipe=recipe,
        )
        assert should_skip_adapter(manifest=manifest) is True

    def test_should_not_skip_adapter_when_incomplete(self) -> None:
        """should_skip_adapter False si manifest incompleto."""
        sigs = (_sig(foco="src/a.py::def::foo"),)
        recipe = ContextRecipe(recipe_ref="node-foo")
        manifest = build_coverage_manifest(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            signatures=sigs,
            required_coverage=2,  # requiere 2, solo 1 presente
            recipe=recipe,
        )
        assert should_skip_adapter(manifest=manifest) is False

    def test_should_not_skip_adapter_when_stale(self) -> None:
        """should_skip_adapter False si hay firmas stale."""
        sigs = (
            _sig(foco="src/a.py::def::foo"),
            _sig(foco="src/b.py::def::bar", state="partial"),
        )
        recipe = ContextRecipe(recipe_ref="node-foo")
        manifest = build_coverage_manifest(
            scope_query=ScopeQuery(scope_kind="directory", target="src/"),
            signatures=sigs,
            required_coverage=2,
            recipe=recipe,
        )
        assert should_skip_adapter(manifest=manifest) is False

    def test_skip_adapter_decision_is_independent_of_invocation(
        self, controller: KnowledgeController, ctx_controller: ContextController
    ) -> None:
        """E2E: compile + manifest completo -> should_skip_adapter True.

        El Adapter NO se invoca porque la consulta determinista es
        completa y fresca (UAT-EVO-11). Aqui solo verificamos la
        decision; el caller real (runcontroller) es quien decide
        cuando invocar o no segun esta decision.
        """
        _seed_signature(controller, source_id="src/a.py", foco="src/a.py::def::foo")
        _seed_signature(controller, source_id="src/b.py", foco="src/b.py::def::bar")

        recipe = ScopeAwareRecipe(
            base_recipe=ContextRecipe(recipe_ref="node-foo"),
            scope_queries=(ScopeQuery(scope_kind="directory", target="src/"),),
            member_source_ids=("src/a.py", "src/b.py"),
        )

        _handoff, manifest = compile_handoff_from_scopes(
            context_controller=ctx_controller,
            scope_recipe=recipe,
            run_id="run-1",
            node_execution_id="ne-1",
        )

        # Cobertura completa (2 firmas, ambas fresh) -> skip adapter.
        assert should_skip_adapter(manifest=manifest) is True
        # El manifest sirve de evidencia operativa: el Adapter, si lo
        # hubiera, sabria que la consulta esta cubierta.
        assert manifest.is_complete is True
        assert manifest.all_fresh is True
