"""H9-context-in-run: conectar la receta de contexto real al handoff del run.

Antes de este slice, `RunController._build_handoff` usaba siempre el stub
`default-empty-recipe/v1` con `knowledge.included=()`. La receta declarada
por el brick (`ctx_recipe_ref`) no se resolvía en la ruta de ejecución,
aunque `ContextController.compile_handoff` (H3) existiera.

Contrato nuevo (opt-in, sin romper la firma blindada del constructor):
- `RunController(storage=..., adapter=..., recipe_resolver=...)` donde
  `recipe_resolver` es `Callable[[str], ContextRecipe | None]`.
- Si el resolver devuelve una receta, el handoff lleva
  `recipe_ref=<ref de la receta>` y `knowledge.included` poblado por
  ContextController (claims/evidencias compiladas).
- Si el resolver devuelve None (o no se pasa resolver), comportamiento
  degradado explícito: stub `default-empty-recipe/v1`, included=().
- Si el resolver lanza SkillGraphError (p.ej. StaleKnowledgeError con
  policy strict), el error se propaga: el nodo falla, no se ejecuta
  el adapter con contexto incompleto.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from skillgraph.core.recipe import ContextRecipe, ObligatorySelector
from skillgraph.knowledge.graph import Claim, Entity, Source
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"


@pytest.fixture
def storage(tmp_path: Path) -> tuple[Storage, FakeAgentAdapter]:
    storage_path = tmp_path / "project.sqlite"
    storage = Storage(storage_path)
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    adapter = FakeAgentAdapter(fixtures_root)
    return storage, adapter


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )


def _plan(*names: str, ctx_recipe_ref: str | None = None) -> WorkflowPlan:
    metadata: dict = {"ctx_recipe_ref": ctx_recipe_ref} if ctx_recipe_ref else {}
    nodes = tuple(
        WorkflowNode(
            name=n,
            kind="ActionNode",
            namespace="shared",
            api_version="skillgraph.dev/v1alpha1",
            resource_revision=1,
            expected_result="text",
            metadata=metadata,
        )
        for n in names
    )
    return WorkflowPlan(nodes=nodes, transitions=(), initial=nodes[0].name)


def _seed_knowledge(storage: Storage) -> None:
    """Registra una source fresh con un claim para que la receta compile."""
    ctl = KnowledgeController(storage=storage, tenant_id=TENANT, project_id=PROJECT)
    ctl.register_source(
        source=Source(
            source_id="src-gate",
            kind="local_file",
            content_hash="deadbeef",
            locator={"path": "local:src-gate"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        )
    )
    ctl.upsert_entity(entity=Entity(entity_id="file:spec", kind="file", stable_key="file:spec"))
    ctl.record_claim(
        claim=Claim(
            claim_id="claim-gate-1",
            subject_entity_id="file:spec",
            predicate="line_count",
            object_literal=42,
            source_id="src-gate",
            extraction_method="manual",
            extractor_version="skillgraph-rules/0.1.0",
            checked_at_revision="rev1",
        )
    )


def _handoff_of_last_execution(storage: Storage) -> dict:
    row = storage.conn.execute(
        "SELECT handoff_json FROM node_executions ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return json.loads(row[0])


class TestRecipeResolverOptIn:
    def test_without_resolver_keeps_stub_recipe(
        self, storage: tuple[Storage, FakeAgentAdapter]
    ) -> None:
        """Sin resolver, comportamiento degradado explícito (stub actual)."""
        s, adapter = storage
        ctl = RunController(storage=s, adapter=adapter)
        rid = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a"))
        ctl.reconcile_run(run_id=rid, tenant_id=TENANT, project_id=PROJECT)
        h = _handoff_of_last_execution(s)
        assert h["knowledge"]["recipe_ref"] == "default-empty-recipe/v1"
        assert h["knowledge"]["included"] == []

    def test_resolver_returning_none_also_degrades(
        self, storage: tuple[Storage, FakeAgentAdapter]
    ) -> None:
        """Resolver que no conoce la receta -> stub, sin excepción."""
        s, adapter = storage
        resolver: Callable[[str], object] = lambda ref: None  # noqa: E731
        ctl = RunController(storage=s, adapter=adapter, recipe_resolver=resolver)
        rid = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a"))
        ctl.reconcile_run(run_id=rid, tenant_id=TENANT, project_id=PROJECT)
        h = _handoff_of_last_execution(s)
        assert h["knowledge"]["recipe_ref"] == "default-empty-recipe/v1"
        assert h["knowledge"]["included"] == []

    def test_resolver_with_recipe_populates_knowledge_included(
        self, storage: tuple[Storage, FakeAgentAdapter], tmp_path: Path
    ) -> None:
        """Receta resuelta -> handoff con recipe_ref real e included poblado."""
        s, adapter = storage
        _seed_knowledge(s)
        # Fixture para el FakeAgentAdapter: nodo "a" con outcome ok.
        fx = tmp_path / "fixtures" / TENANT / PROJECT / "a.json"
        fx.parent.mkdir(parents=True, exist_ok=True)
        fx.write_text(
            json.dumps({"outcome": "ok", "result": {"answer": "ok"}, "evidence_ref": "ev-a"})
        )

        def resolver(ref: str) -> ContextRecipe | None:
            if ref != "gate.recipe/v1":
                return None
            return ContextRecipe(
                recipe_ref=ref,
                obligatory=(ObligatorySelector(kind="source", value="src-gate", label=""),),
                freshness_policy="best_effort",
                token_budget=8000,
                overflow_strategy="drop_optional",
            )

        ctl = RunController(storage=s, adapter=adapter, recipe_resolver=resolver)
        rid = ctl.create_run(
            tenant_id=TENANT,
            project_id=PROJECT,
            plan=_plan("a", ctx_recipe_ref="gate.recipe/v1"),
        )
        ctl.reconcile_run(run_id=rid, tenant_id=TENANT, project_id=PROJECT)
        h = _handoff_of_last_execution(s)
        assert h["knowledge"]["recipe_ref"] == "gate.recipe/v1"
        # included: los claims de la source obligatoria compilados.
        # El compilador emite resource_kind="claim" para selectores
        # kind="source" (contrato de CompiledResource).
        kinds = [item[0] for item in h["knowledge"]["included"]]
        assert "claim" in kinds
        # el nodo se ejecutó (el adapter recibió el handoff con contexto)
        row = s.conn.execute(
            "SELECT state FROM node_executions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "SUCCEEDED"

    def test_resolver_receives_node_recipe_ref(
        self, storage: tuple[Storage, FakeAgentAdapter]
    ) -> None:
        """El resolver recibe la ctx_recipe_ref del nodo (plumbing correcto)."""
        s, adapter = storage
        received: list[str] = []

        def resolver(ref: str) -> None:
            received.append(ref)
            return None

        ctl = RunController(storage=s, adapter=adapter, recipe_resolver=resolver)
        rid = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a"))
        ctl.reconcile_run(run_id=rid, tenant_id=TENANT, project_id=PROJECT)
        assert received == ["default-empty-recipe/v1"]

    def test_resolver_error_fails_node_without_invoking_adapter(
        self, storage: tuple[Storage, FakeAgentAdapter]
    ) -> None:
        """Error tipado del resolver -> nodo FAILED; el adapter NO se invoca."""
        from skillgraph.core.errors import StaleKnowledgeError

        s, _adapter = storage

        class ExplodingAdapter:
            def invoke(self, handoff: object) -> object:
                raise AssertionError("el adapter no debe invocarse con receta rota")

        def resolver(ref: str) -> ContextRecipe:
            raise StaleKnowledgeError("claim stale y policy=strict")

        ctl = RunController(storage=s, adapter=ExplodingAdapter(), recipe_resolver=resolver)
        rid = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan("a"))
        ctl.reconcile_run(run_id=rid, tenant_id=TENANT, project_id=PROJECT)
        row = s.conn.execute(
            "SELECT state, error FROM node_executions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "FAILED"
        assert "stale" in (row[1] or "").lower()

    def test_constructor_blindaje_sigue_en_pie(self) -> None:
        """La firma sigue sin aceptar conn (no-regresión del blindaje H9)."""
        import inspect

        params = list(inspect.signature(RunController.__init__).parameters)
        assert params[:3] == ["self", "storage", "adapter"]
        assert "conn" not in params
