"""FileHandoff — H13 Handoff experto desde consultas.

Destino (evolution-v2/plan/ROADMAP.md H13):
una receta existente utiliza resultados tipados (FileSignatures
agregadas por scope) y entrega contexto pertinente al trabajo
(via Handoff compilado por ContextController), con manifest de
cobertura/procedencia/fuentes explicito y decision de skip del
adapter cuando la cobertura es completa y fresca.

Adaptado a las primitivas H11+H12:
- H11: FileSignature + extract_file_signatures (sin red, sin I/O).
- H12: FileScope + ScopeQuery + aggregate_signatures + KnowledgeController.
- ContextRecipe + ContextController.compile_handoff (sin tocar su API).
- FakeAgentAdapter para verificacion (sin red, determinista).

Composicion (no herencia):
- ScopeAwareRecipe envuelve ContextRecipe con ``scope_queries`` y
  ``member_source_ids``. Esto evita modificar ``ObligatorySelector.kind``
  (Literal cerrada) y mantiene el contrato de ContextRecipe intacto.
- CoverageManifest es el output observable de la consulta agregada:
  incluye signatures, fuentes, revisiones, procedencia por firma,
  cobertura total y limites (budget + freshness).
- HandoffBlockedError es subclase tipada de SkillGraphError (regla
  AGENTS §1.2): NUNCA se presenta como completo cuando hay carencia.
- should_skip_adapter() decide si la consulta determinista tiene
  cobertura completa+fresca (regla UAT-EVO-11: respuesta sin LLM).

Funciones puras (sin I/O, sin reloj):
- build_coverage_manifest(): agrega firmas + metadatos del scope.
- should_skip_adapter(): evalua manifest sin side effects.
- compile_handoff_from_scopes(): orquestador con I/O minimo
  (Storage read via KnowledgeController); produce (Handoff, Manifest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from skillgraph.core.errors import SkillGraphError
from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.file_signature import FileSignature

# --- Errores tipados (regla AGENTS §1.2) ----------------------------


class HandoffBlockedError(SkillGraphError):
    """Handoff NO compilable por carencia explicita (UAT-EVO-10).

    Se lanza cuando una consulta declarativa exige firmas que no
    estan disponibles o no estan vigentes. NUNCA debe presentarse
    como completado: el caller recibe este error y decide como
    programar la adquisicion autorizada.
    """

    def __init__(
        self,
        *,
        recipe_ref: str,
        missing_sources: tuple[str, ...],
        missing_signatures: tuple[str, ...],
        reason: str,
    ) -> None:
        self.recipe_ref = recipe_ref
        self.missing_sources = missing_sources
        self.missing_signatures = missing_signatures
        self.reason = reason
        # Mensaje que NO dice "completado" cuando hay carencia.
        detalle = f"recipe_ref={recipe_ref!r}"
        if missing_sources:
            detalle += f"; sources_sin_firma={list(missing_sources)}"
        if missing_signatures:
            detalle += f"; firmas_requeridas_no_presentes={list(missing_signatures)}"
        detalle += f"; motivo={reason}"
        super().__init__(detalle)


# --- Dataclasses frozen ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ScopeAwareRecipe:
    """ContextRecipe enriquecida con consultas por scope (H13).

    Composicion (no herencia): no modifica la ``Literal`` cerrada
    de ``ObligatorySelector.kind``. ``base_recipe`` aporta los
    campos estandar (recipe_ref, budget, freshness_policy, etc.);
    ``scope_queries`` aporta la consulta por scopes (H12).

    Attributes:
        base_recipe: ContextRecipe original (sin modificar).
        scope_queries: tuple de ScopeQuery a resolver.
        member_source_ids: source_ids miembros (se usan para la
            agregacion via KnowledgeController).
        require_complete_coverage: si True, lanza HandoffBlockedError
            cuando alguna fuente del scope no tiene firma (UAT-EVO-10).
    """

    base_recipe: ContextRecipe
    scope_queries: tuple[object, ...]  # tuple[ScopeQuery, ...] forward ref
    member_source_ids: tuple[str, ...]
    require_complete_coverage: bool = False

    def __post_init__(self) -> None:
        if not self.base_recipe.recipe_ref:
            raise ValueError("base_recipe.recipe_ref vacio")
        if not self.scope_queries:
            raise ValueError("scope_queries vacio")
        if not self.member_source_ids:
            raise ValueError("member_source_ids vacio")


@dataclass(frozen=True, slots=True)
class CoverageManifest:
    """Manifest de cobertura/procedencia/fuentes (UAT-EVO-09).

    Estructura observable que accompany al Handoff compilado.
    Permite al caller saber QUE incluyo el handoff, DE DONDE vino,
    y cuales son los LIMITES (budget, freshness policy).
    """

    scope: object  # ScopeQuery forward ref
    signatures: tuple[FileSignature, ...]
    fuentes: tuple[str, ...]
    procedencia_por_firma: dict[str, str]  # foco -> extraction_method
    revisiones_por_fuente: dict[str, str]  # source_id -> revision
    cobertura_total: int
    required_coverage: int
    limites: dict[str, Any] = field(default_factory=dict)
    metadatos: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """True si la cobertura actual cumple la requerida."""
        return self.cobertura_total >= self.required_coverage

    @property
    def all_fresh(self) -> bool:
        """True si TODAS las firmas tienen vigencia fresh."""
        return all(s.vigencia.fresh for s in self.signatures)


# --- Funciones puras -------------------------------------------------


def build_coverage_manifest(
    *,
    scope_query: object,
    signatures: tuple[FileSignature, ...],
    required_coverage: int,
    recipe: ContextRecipe,
    revisiones_por_fuente: dict[str, str] | None = None,
) -> CoverageManifest:
    """Construye un CoverageManifest (funcion pura, sin I/O).

    Args:
        scope_query: ScopeQuery que produjo la agregacion.
        signatures: tupla de FileSignatures (post agregacion H12).
        required_coverage: minimo de firmas necesario.
        recipe: ContextRecipe (para extraer limites como budget y policy).
        revisiones_por_fuente: opcional dict source_id -> revision.

    Returns:
        CoverageManifest frozen con cobertura, procedencia y limites.
    """
    procedencia: dict[str, str] = {}
    for s in signatures:
        procedencia[s.foco] = s.procedencia.extraction_method

    # Fuentes deducidas del foco (cada foco es "<source>::..." o "<source>").
    fuentes_set: set[str] = set()
    for s in signatures:
        foco = s.foco
        # Extraer el primer segmento antes de "::".
        if "::" in foco:
            fuentes_set.add(foco.split("::", 1)[0])
        else:
            fuentes_set.add(foco)

    return CoverageManifest(
        scope=scope_query,
        signatures=signatures,
        fuentes=tuple(sorted(fuentes_set)),
        procedencia_por_firma=procedencia,
        revisiones_por_fuente=revisiones_por_fuente or {},
        cobertura_total=sum(s.cobertura for s in signatures),
        required_coverage=required_coverage,
        limites={
            "token_budget": recipe.token_budget,
            "freshness_policy": recipe.freshness_policy,
            "overflow_strategy": recipe.overflow_strategy,
        },
        metadatos={
            "signatures_count": len(signatures),
        },
    )


def should_skip_adapter(*, manifest: CoverageManifest) -> bool:
    """Decide si la consulta determinista puede saltarse el adapter (UAT-EVO-11).

    Reglas:
    - Cobertura completa (manifest.is_complete).
    - TODAS las firmas tienen vigencia fresh (manifest.all_fresh).
    - Al menos una firma presente.

    Returns:
        True si NO se necesita invocar al Adapter LLM.

    Notes:
        Funcion pura: solo lee el manifest. El caller decide si
        invoca o no segun el resultado. Esto permite que el caller
        mantenga la responsabilidad de orquestar adapter/invoke.
    """
    if not manifest.signatures:
        return False
    return manifest.is_complete and manifest.all_fresh


# --- Orquestador (compila handoff a partir de scopes) ---------------


def compile_handoff_from_scopes(
    *,
    context_controller: object,  # ContextController forward ref
    scope_recipe: ScopeAwareRecipe,
    run_id: str,
    node_execution_id: str,
    attempt: int = 1,
    workspace_ref: str = "local",
    source_revision: str = "HEAD",
    definition_kind: str = "ActionNode",
    definition_name: str = "node",
    definition_namespace: str = "default",
    definition_revision: int = 1,
    api_version: str = "skillgraph.io/v1",
    expected_result: str = "",
) -> tuple[object, CoverageManifest]:
    """Compila un Handoff desde ScopeAwareRecipe + ContextController.

    Pasos:
    1. Validar ScopeAwareRecipe (tipos y campos).
    2. Resolver scopes via ``KnowledgeController.aggregate_file_signatures``
       (reusa H12, con aislamiento E2E-08).
    3. Construir CoverageManifest con las firmas agregadas.
    4. Si ``require_complete_coverage=True`` y hay carencia, lanzar
       ``HandoffBlockedError`` (UAT-EVO-10).
    5. Construir una ``ContextRecipe`` sintetica a partir del scope_recipe
       con ``obligatory`` derivado de los member_source_ids, y delegar
       en ``ContextController.compile_handoff`` (H4).

    Args:
        context_controller: ContextController (ya inyecta KnowledgeController).
        scope_recipe: ScopeAwareRecipe (H13).
        run_id, node_execution_id, ...: parametros de compile_handoff (H4).

    Returns:
        Tupla ``(Handoff, CoverageManifest)``.

    Raises:
        HandoffBlockedError: si require_complete_coverage=True y la
            cobertura no es completa o falta alguna firma obligatoria.
    """
    # Lazy imports para evitar ciclos (regla AGENTS §11.7).
    from skillgraph.knowledge.context_controller import ContextController
    from skillgraph.knowledge.file_scope import ScopeQuery
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    if not isinstance(context_controller, ContextController):
        raise TypeError(
            f"context_controller debe ser ContextController, recibio "
            f"{type(context_controller).__name__}"
        )
    if not isinstance(scope_recipe, ScopeAwareRecipe):
        raise TypeError(
            f"scope_recipe debe ser ScopeAwareRecipe, recibio "
            f"{type(scope_recipe).__name__}"
        )

    knowledge = context_controller.knowledge  # KnowledgeController
    if not isinstance(knowledge, KnowledgeController):
        raise TypeError(
            f"context_controller.knowledge debe ser KnowledgeController, recibio "
            f"{type(knowledge).__name__}"
        )

    # Paso 2: resolver cada scope y agregar firmas.
    # Por ahora implementamos el caso comun: un scope por recipe.
    # Multi-scope es extension natural si la receta lo exige.
    if len(scope_recipe.scope_queries) > 1:
        raise NotImplementedError(
            "multi-scope_queries en una sola recipe: soportado en H13 "
            "con un solo scope_queries por ahora"
        )
    scope_query = scope_recipe.scope_queries[0]
    if not isinstance(scope_query, ScopeQuery):
        raise TypeError(
            f"scope_query debe ser ScopeQuery, recibio {type(scope_query).__name__}"
        )

    # Aggregate via KnowledgeController (reusa H12).
    aggregated = knowledge.aggregate_file_signatures(
        scope_query=scope_query,
        member_source_ids=scope_recipe.member_source_ids,
    )

    # Paso 3: manifest.
    # required_covenance = total miembros declarados (cada uno debe aportar firma).
    required_coverage = len(scope_recipe.member_source_ids)
    manifest = build_coverage_manifest(
        scope_query=scope_query,
        signatures=aggregated.signatures,
        required_coverage=required_coverage,
        recipe=scope_recipe.base_recipe,
    )

    # Paso 4: validar cobertura completa si se requiere.
    if scope_recipe.require_complete_coverage:
        sources_con_firma: set[str] = set()
        for sig in aggregated.signatures:
            foco = sig.foco
            if "::" in foco:
                sources_con_firma.add(foco.split("::", 1)[0])
            else:
                sources_con_firma.add(foco)
        missing_sources = tuple(
            s for s in scope_recipe.member_source_ids if s not in sources_con_firma
        )
        missing_signatures = tuple(
            s.foco for s in aggregated.signatures if not s.vigencia.fresh
        )
        if missing_sources or missing_signatures or not manifest.is_complete:
            raise HandoffBlockedError(
                recipe_ref=scope_recipe.base_recipe.recipe_ref,
                missing_sources=missing_sources,
                missing_signatures=missing_signatures,
                reason="coverage incompleta o firmas no-fresh",
            )

    # Paso 5: construir ContextRecipe sintetica.
    # Estrategia: NO incluir las FileSignatures como resources individuales
    # (eso duplicaria el manifest y consumiria budget inutilmente). El
    # manifest via H13 es la representacion canonica; el handoff compila
    # OK con un obligatory vacio (las firmas ya estan en el manifest).
    # El caller que necesite las firmas individuales puede pedirlas via
    # ``knowledge.list_file_signatures_for_source`` por su cuenta.
    synth_recipe = ContextRecipe(
        recipe_ref=scope_recipe.base_recipe.recipe_ref,
        obligatory=(),
        optional=scope_recipe.base_recipe.optional,
        relation_selectors=scope_recipe.base_recipe.relation_selectors,
        freshness_policy=scope_recipe.base_recipe.freshness_policy,
        token_budget=scope_recipe.base_recipe.token_budget,
        overflow_strategy=scope_recipe.base_recipe.overflow_strategy,
        revision=scope_recipe.base_recipe.revision,
    )

    # Delegar en compile_handoff (H4) — produce Handoff inmutable.
    handoff = context_controller.compile_handoff(
        recipe=synth_recipe,
        run_id=run_id,
        node_execution_id=node_execution_id,
        attempt=attempt,
        workspace_ref=workspace_ref,
        source_revision=source_revision,
        definition_kind=definition_kind,
        definition_name=definition_name,
        definition_namespace=definition_namespace,
        definition_revision=definition_revision,
        api_version=api_version,
        expected_result=expected_result,
    )

    return handoff, manifest
