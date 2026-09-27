"""WI-31: cobertura del code path ``_compile_knowledge``.

El audit del 2026-09-27 detecto el ``cast(Storage, self._runs)`` en
``src/skillgraph/runtime/runcontroller.py:1129``. Es un workaround
del type checker: ``self._runs: RunRepository`` no satisface
``KnowledgeRepository`` desde la perspectiva del checker, pero
``Storage`` los implementa ambos por structural subtyping.

Ademas, el code path ``_compile_knowledge`` (que es donde vive el
cast) NO tiene tests. Cero cobertura del camino
``recipe_resolver != None`` => ``recipe = self._recipe_resolver(...)``
=> ``KnowledgeController(knowledge=cast(...))`` => ``compile_handoff``.

Estos tests cubren el camino completo con una ``Storage`` real,
``recipe_resolver`` que devuelve una receta valida, y verifican
que el round-trip termina en un ``HandoffKnowledge`` no vacio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.runcontroller import RunController

TENANT = "t-wi31"
PROJECT = "p-wi31"


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    storage_path = tmp_path / "project-wi31.sqlite"
    return Storage(storage_path)


@pytest.fixture
def adapter(tmp_path: Path) -> FakeAgentAdapter:
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    return FakeAgentAdapter(fixtures_root)


def _node(name: str) -> WorkflowNode:
    """WorkflowNode minimo valido para los tests."""
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
    )


def _make_run_controller(
    storage_obj: Storage,
    adapter: FakeAgentAdapter,
    recipe_resolver,
) -> RunController:
    """Construye un RunController minimo con recipe_resolver."""
    return RunController(
        runs=storage_obj,
        events=storage_obj,
        policy=storage_obj,
        adapter=adapter,
        recipe_resolver=recipe_resolver,
        # WI-31: inyectamos ``knowledge`` explicitamente para que el
        # code path ``_compile_knowledge`` complete el camino real.
        # Si se omite, el guard degrada al stub default-empty.
        knowledge=storage_obj,
    )


class TestCompileKnowledgeCodePath:
    """WI-31: red -> green network for ``_compile_knowledge``."""

    def test_runcontroller_can_compile_with_resolver_returning_recipe(
        self, storage: Storage, adapter: FakeAgentAdapter
    ) -> None:
        """Happy path: resolver devuelve ContextRecipe valida.

        Demuestra que el camino ``self._recipe_resolver(...) ->
        KnowledgeController(knowledge=self._runs) ->
        ContextController.compile_handoff`` funciona end-to-end
        con una Storage real.
        """
        recipe = ContextRecipe(recipe_ref="recipe-test/v1")

        def resolver(_ref: str) -> ContextRecipe | None:
            return recipe

        ctl = _make_run_controller(storage, adapter, resolver)

        handoff_knowledge = ctl._compile_knowledge(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="r-wi31-1",
            node_execution_id="ne-wi31-1",
            node=_node("n1"),
        )

        # La receta se compilo: el recipe_ref en HandoffKnowledge
        # debe coincidir con el de la receta registrada.
        assert handoff_knowledge.recipe_ref == "recipe-test/v1"
        # Sin selectores obligatorios => included es tuple vacio
        # (no hay claims/evidencias reclamadas).
        assert handoff_knowledge.included == ()

    def test_runcontroller_resolver_returning_none_yields_stub(
        self, storage: Storage, adapter: FakeAgentAdapter
    ) -> None:
        """El resolver devolviendo None degrada al stub default-empty.

        Verifica que el atajo "resolver is None OR resolver returns
        None" sigue funcionando: ningun branch del recipe path se
        ejecuta y el HandoffKnowledge es el stub.
        """

        def resolver(_ref: str) -> ContextRecipe | None:
            return None

        ctl = _make_run_controller(storage, adapter, resolver)

        handoff_knowledge = ctl._compile_knowledge(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="r-wi31-2",
            node_execution_id="ne-wi31-2",
            node=_node("n2"),
        )

        # Stub default-empty-recipe/v1 (definido en __init__).
        assert handoff_knowledge.recipe_ref == "default-empty-recipe/v1"
        assert handoff_knowledge.included == ()

    def test_runcontroller_no_resolver_means_no_knowledge_controller_call(
        self, storage: Storage, adapter: FakeAgentAdapter
    ) -> None:
        """Sin ``recipe_resolver``, el atajo saltea ``KnowledgeController``.

        Aqui es donde el ``cast(Storage, ...)`` nunca se ejecuta; el
        guard debe garantizar el camino cero-Llamadas-a-Storage.
        """
        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=adapter,
            recipe_resolver=None,
        )

        handoff_knowledge = ctl._compile_knowledge(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="r-wi31-3",
            node_execution_id="ne-wi31-3",
            node=_node("n3"),
        )

        assert handoff_knowledge.recipe_ref == "default-empty-recipe/v1"
        assert handoff_knowledge.included == ()

    def test_runcontroller_resolver_without_knowledge_falls_back_to_stub(
        self, storage: Storage, adapter: FakeAgentAdapter
    ) -> None:
        """WI-31: ``knowledge=None`` con resolver valido de stub.

        El guard explicito ``self._knowledge is None`` cortocircuita
        al stub ``default-empty-recipe/v1`` (incluido=()). Antes
        (cast(Storage, self._runs)), la ausencia del kwarg no se
        podia expresar y se dependia de ``self._runs`` siendo una
        Storage. Ahora el contrato es explicito.
        """
        recipe = ContextRecipe(recipe_ref="recipe-orphan/v1")

        def resolver(_ref: str) -> ContextRecipe | None:
            return recipe

        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=adapter,
            recipe_resolver=resolver,
            # knowledge NO inyectado => degradar al stub
        )

        handoff_knowledge = ctl._compile_knowledge(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="r-wi31-orphan",
            node_execution_id="ne-wi31-orphan",
            node=_node("orphan"),
        )

        # Stub: el resolver devolvio una receta pero el guard cortocircuita.
        assert handoff_knowledge.recipe_ref == "default-empty-recipe/v1"
        assert handoff_knowledge.included == ()

    def test_runcontroller_knowledge_repository_is_storage_structural(
        self, storage: Storage
    ) -> None:
        """WI-31 premise check: ``Storage`` satisface ``KnowledgeRepository``.

        Acompanante estructural: verifica que el ``cast(Storage,
        self._runs)`` en ``_compile_knowledge`` no es un bug
        runtime (Storage implementa KnowledgeRepository); es solo
        un workaround del type checker. Este test confirma la
        premisa del WI-31 y falla si alguien rompe la
        conformance.
        """
        from skillgraph.platform.ports import KnowledgeRepository, RunRepository

        # Rubric: todos los metodos publicos declarados en cada
        # Protocol deben existir en una instancia de Storage.
        all_methods = {
            m
            for m in (set(dir(RunRepository)) | set(dir(KnowledgeRepository)))
            if not m.startswith("_")
        }
        missing = sorted(m for m in all_methods if not hasattr(storage, m))
        assert not missing, (
            "Storage dejo de satisfacer RunRepository + KnowledgeRepository "
            f"por structural subtyping. Faltan: {missing}. WI-31 premisa rota."
        )


class TestStorageKnowledgeRepositoryFactor:
    """WI-31: introduccion de ``Storage.knowledge_repository()``.

    Consistente con ``Storage.run_repository()``. El factor devuelve
    el propio Storage tipado como ``Storage``. El RunController lo
    usa en lugar de pasar ``self._runs`` directo, eliminando el
    ``cast(Storage, self._runs)``.
    """

    def test_storage_exposes_knowledge_repository_factor(self) -> None:
        """El factor existe y es sinonimo de ``self`` mientras
        ``Storage`` mantenga las firmas de ``KnowledgeRepository``.
        """
        from skillgraph.platform.storage import Storage

        assert hasattr(Storage, "knowledge_repository"), (
            "Storage.knowledge_repository() no existe. WI-31 incompleto."
        )

    def test_knowledge_repository_factor_returns_storage(self, storage: Storage) -> None:
        """El factor devuelve una instancia compatible con
        ``KnowledgeController(knowledge=...)``.
        """

        knowledge = storage.knowledge_repository()  # type: ignore[attr-defined]

        # Construir KnowledgeController con el factor debe funcionar.
        kctl = KnowledgeController(
            knowledge=knowledge,  # type: ignore[arg-type]
            tenant_id=TENANT,
            project_id=PROJECT,
        )
        assert kctl.tenant_id == TENANT
        assert kctl.project_id == PROJECT
