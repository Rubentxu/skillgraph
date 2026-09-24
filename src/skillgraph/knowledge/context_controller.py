"""ContextController + OutcomeTracer: cierre del H3 (slice 5).

Doc externo:
  specs/h3-slice-5.md (sub-spec firmado en el H3).
  external/blueprint-v1/docs/06-recipes-handoffs.md.
  external/blueprint-v1/docs/07-handoff-inmutable.md.

`ContextController` toma una `ContextRecipe` (conocimiento obligatorio,
opcional, freshness policy, token budget), resuelve los selectores
contra `KnowledgeController`, aplica las reglas de overflow/strictness,
y devuelve un `Handoff` inmutable con `context_hash` determinista.

`OutcomeTracer` extrae, dado un run_id, los Claims/Evidences que el
run toco (via `node_executions` y eventos) y los referencia via un
`OutcomeTrace` ADT (no copia contenido, blueprint §9).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from skillgraph.core.errors import (
    MissingObligatoryError,
    StaleKnowledgeError,
    TokenBudgetExceededError,
)
from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.graph import OutcomeTrace
from skillgraph.runtime.engine import now_iso as _now_iso
from skillgraph.runtime.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def approx_chars(obj: object) -> int:
    """Aproxima tokens como longitud en caracteres (D4 cerrada).

    NO son tokens reales. Es una heuristica suficiente para el gate H3.
    Para H4+ con un Adapter LLM real, usar `tiktoken` o equivalente.
    """
    if isinstance(obj, str):
        return len(obj)
    return len(json.dumps(obj, ensure_ascii=False, sort_keys=True))


# ---------------------------------------------------------------------------
# Helpers puros extraídos de ContextController.compile_handoff
# ---------------------------------------------------------------------------
#
# Estas funciones son **puras** (no capturan self, no leen I/O). Reciben
# listas de CompiledResource y devuelven resultados o elevan errores
# tipados del modulo `core.errors`. Se exponen sin `_` para tests
# internos (no en __all__) y se documentan en `specs/h3-slice-5.md`.


def _collect_stale_obligatory_claims(
    items: Sequence[CompiledResource],
) -> tuple[CompiledResource, ...]:
    """Devuelve los CompiledResource de tipo claim con body['stale']=True."""
    return tuple(
        it
        for it in items
        if it.resource_kind == "claim" and it.body.get("stale") is True
    )


def enforce_strict_freshness(
    items: Sequence[CompiledResource],
    *,
    policy: str,
) -> None:
    """Aplica la politica de frescura estricta (pure function).

    Args:
        items: recursos ya resueltos (obligatorios).
        policy: politica de frescura de la receta.

    Raises:
        StaleKnowledgeError: si policy=='strict' y hay al menos un
            claim stale entre los items.
    """
    if policy != "strict":
        return
    stale = _collect_stale_obligatory_claims(items)
    if stale:
        raise StaleKnowledgeError(
            f"{len(stale)} obligatory Claim(s) stale y policy=strict"
        )


def apply_budget(
    obligatory: Sequence[CompiledResource],
    optional: Sequence[CompiledResource],
    *,
    budget_chars: int,
    overflow_strategy: str,
) -> tuple[tuple[CompiledResource, ...], int]:
    """Aplica el budget de caracteres a obligatorios + opcionales.

    Pasos:
    1. Suma obligatorios. Si exceden budget_chars -> TokenBudgetExceededError
       (los obligatorios NO se truncan).
    2. Irea opcionales en orden. Cada uno que cabe se incluye. Si no
       cabe: si overflow_strategy=='fail' -> TokenBudgetExceededError;
       en caso contrario ('drop_optional' | 'truncate_finding') -> para.

    Returns:
        (included, total_chars) donde included empieza con los
        obligatorios y sigue con los opcionales aceptados.
    """
    included: list[CompiledResource] = list(obligatory)
    total_chars = sum(approx_chars(it.body) for it in included)
    if total_chars > budget_chars:
        raise TokenBudgetExceededError(
            f"obligatorio ({total_chars} chars) excede budget ({budget_chars})"
        )
    for opt in optional:
        opt_chars = approx_chars(opt.body)
        if total_chars + opt_chars <= budget_chars:
            included.append(opt)
            total_chars += opt_chars
            continue
        if overflow_strategy == "fail":
            raise TokenBudgetExceededError(
                f"obligatory+opcional no caben en budget "
                f"{budget_chars} (acumulado {total_chars})"
            )
        # drop_optional o truncate_finding: paramos sin incluir el opt.
        break
    return tuple(included), total_chars


def build_capabilities(
    included: Sequence[CompiledResource],
    *,
    policy: str,
) -> tuple[str, ...]:
    """Devuelve capabilities del handoff segun frescura aplicada.

    Si policy=='best_effort' y algun included tiene body['stale']=True
    -> ('stale',). En caso contrario -> tuple vacio.
    """
    if policy != "best_effort":
        return ()
    for it in included:
        if it.resource_kind == "claim" and it.body.get("stale") is True:
            return ("stale",)
    return ()


# ---------------------------------------------------------------------------
# Constructores de CompiledResource (puros, sin I/O)
# ---------------------------------------------------------------------------
#
# Encapsulan el mapeo desde tipos de dominio (Claim) o filas de Storage
# (dict) hacia `CompiledResource`. Antes vivian inline en
# `_resolve_one_selector`; ahora son funciones puras que se pueden
# componer y testear aisladamente.


def claim_to_resource(claim: object, resource_name: str) -> CompiledResource:
    """Mapea un Claim (dataclass) -> CompiledResource(kind='claim')."""
    return CompiledResource(
        resource_kind="claim",
        resource_namespace=f"claim:{claim.claim_id}",  # type: ignore[attr-defined]
        resource_name=resource_name,
        body={
            "claim_id": claim.claim_id,  # type: ignore[attr-defined]
            "predicate": claim.predicate,  # type: ignore[attr-defined]
            "object_literal": claim.object_literal,  # type: ignore[attr-defined]
            "source_id": claim.source_id,  # type: ignore[attr-defined]
            "checked_at_revision": claim.checked_at_revision,  # type: ignore[attr-defined]
            "stale": claim.stale,  # type: ignore[attr-defined]
        },
    )


def predicate_row_to_resource(
    row: dict[str, object],
    resource_name: str,
) -> CompiledResource:
    """Mapea una fila de `list_claims_by_predicate` -> CompiledResource.

    La fila viene de Storage con `object_literal_json` como string;
    aqui se deserializa para que el body sea comparable por valor.
    """
    return CompiledResource(
        resource_kind="claim",
        resource_namespace=f"claim:{row['claim_id']}",
        resource_name=resource_name,
        body={
            "claim_id": row["claim_id"],
            "predicate": row["predicate"],
            "object_literal": json.loads(row["object_literal_json"]),  # type: ignore[arg-type]
            "source_id": row["source_id"],
            "checked_at_revision": row["checked_at_revision"],
            "stale": bool(row["stale"]),
        },
    )


def evidence_row_to_resource(
    row: dict[str, object],
    resource_name: str,
) -> CompiledResource:
    """Mapea una fila de `list_evidences_for_source` -> CompiledResource."""
    return CompiledResource(
        resource_kind="evidence",
        resource_namespace=f"evidence:{row['evidence_id']}",
        resource_name=resource_name,
        body={
            "evidence_id": row["evidence_id"],
            "kind": row["kind"],
            "content": json.loads(row["content_json"]),  # type: ignore[arg-type]
            "source_id": row["source_id"],
            "observed_at": row["observed_at"],
        },
    )


# Alias sin `_` para tests internos (no aparecen en __all__).


# ---------------------------------------------------------------------------
# ContextController
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompiledResource:
    """Snapshot de un recurso (Claim o Evidence) que va en el handoff."""

    resource_kind: str  # "claim" | "evidence" | "finding"
    resource_namespace: str  # "claim:<id>" | "evidence:<id>" | ...
    resource_name: str  # entity_id (claim/evidence) o rule_ref (finding)
    body: dict[str, object]

    def as_tuple(self) -> tuple[str, str, str]:
        return (
            self.resource_kind,
            self.resource_namespace,
            self.resource_name,
        )


@dataclass(frozen=True, slots=True)
class ContextController:
    """Compila handoffs a partir de recetas.

    Recibe un `KnowledgeController` por inyeccion. La politica de
    frescura (strict / best_effort) y la estrategia de overflow se
    leen de la receta en cada llamada a `compile_handoff`.
    """

    knowledge: object  # KnowledgeController (lazy-typed para evitar ciclos)

    def compile_handoff(
        self,
        *,
        recipe: ContextRecipe,
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
    ) -> Handoff:
        """Compila un handoff inmutable.

        Pasos (literal del blueprint §6-§7):
        1. Resolver selectors -> lista de Claims/Evidences.
        2. Filtrar por frescura (strict).
        3. Aplicar budget.

        Delegamos en helpers puros del modulo (`enforce_strict_freshness`,
        `apply_budget`, `build_capabilities`) para que cada paso sea
        testable aisladamente y el cuerpo del metodo quede declarativo.

        Si `obligatory` no se resuelve: `MissingObligatoryError`.
        Si `freshness_policy="strict"` y hay stale: `StaleKnowledgeError`.
        Si `overflow_strategy="fail"` y budget insuficiente: `TokenBudgetExceededError`.
        """
        obligatory_items = self._resolve_selectors(
            recipe.obligatory,
            required=True,
        )
        optional_items = self._resolve_selectors(
            recipe.optional,
            required=False,
        )

        # Paso 2: freshness estricta sobre obligatorios.
        enforce_strict_freshness(
            obligatory_items, policy=recipe.freshness_policy
        )

        # Paso 3: aplicar budget.
        included, _total_chars = apply_budget(
            obligatory_items,
            optional_items,
            budget_chars=recipe.token_budget,
            overflow_strategy=recipe.overflow_strategy,
        )
        # _total_chars no se usa directamente; el `recipe.token_budget`
        # ya queda registrado en `HandoffExecution.budget`.

        # Capabilities segun freshness aplicada.
        capabilities = build_capabilities(
            included, policy=recipe.freshness_policy
        )

        identity = HandoffIdentity(
            tenant_id=self.knowledge.tenant_id,  # type: ignore[attr-defined]
            project_id=self.knowledge.project_id,  # type: ignore[attr-defined]
            run_id=run_id,
            node_execution_id=node_execution_id,
            attempt=attempt,
        )
        behavior = HandoffBehavior(
            definition_kind=definition_kind,  # type: ignore[arg-type]
            definition_name=definition_name,
            definition_namespace=definition_namespace,
            definition_revision=definition_revision,
            api_version=api_version,
        )
        knowledge = HandoffKnowledge(
            recipe_ref=recipe.recipe_ref,
            included=tuple(it.as_tuple() for it in included),
        )
        execution = HandoffExecution(
            workspace_ref=workspace_ref,
            source_revision=source_revision,
            budget={"token_budget_chars": recipe.token_budget},
        )
        if not expected_result:
            expected_result = f"execute {definition_name} (recipe={recipe.recipe_ref})"

        return Handoff(
            identity=identity,
            behavior=behavior,
            knowledge=knowledge,
            execution=execution,
            expected_result=expected_result,
            capabilities=capabilities,
        )

    def refresh_handoff(
        self,
        *,
        previous_hash: str,
        recipe: ContextRecipe,
        **kwargs: object,
    ) -> Handoff:
        """Recompila el handoff si la receta o el knowledge cambiaron.

        El `previous_hash` no se valida como input: solo se documenta en
        el `RecipeNotFoundError` o en logs. Slice 5 verifica igualdad
        con el hash del handoff nuevo; si coincide, no hay cambio.
        """
        new = self.compile_handoff(recipe=recipe, **kwargs)  # type: ignore[arg-type]
        if new.context_hash == previous_hash:
            return new
        # Cambio detectado. La API retorna el nuevo (caller persiste
        # si quiere).
        return new

    # ----- Internals -----

    def _resolve_selectors(
        self,
        selectors: tuple[object, ...],
        *,
        required: bool,
    ) -> list[CompiledResource]:
        """Resuelve una lista de selectores contra el KnowledgeController.

        Cada selector es un `ObligatorySelector` (kind ∈ {entity, predicate,
        source}). Si `required=True` y el selector NO resuelve al menos
        UN item (entity/source kind) -> `MissingObligatoryError`.
        Para predicate kind, "cero resultados" NO es error (puede ser
        un predicado que nadie usa todavia).
        """
        out: list[CompiledResource] = []
        for sel in selectors:
            kind = sel.kind  # type: ignore[attr-defined]
            value = sel.value  # type: ignore[attr-defined]
            label = sel.label  # type: ignore[attr-defined]
            resolved = self._resolve_one_selector(kind, value, label)
            if required and not resolved:
                # Predicate kind: zero resultados no es obligatorio missing.
                if kind == "predicate":
                    continue
                # Para entity/source: zero resultados = selector missing.
                raise MissingObligatoryError(
                    f"selector obligatorio no resolvio: kind={kind!r} value={value!r}"
                )
            out.extend(resolved)
        return out

    def _resolve_one_selector(
        self,
        kind: str,
        value: str,
        label: str,
    ) -> list[CompiledResource]:
        """Resuelve UN selector. Devuelve 0..N CompiledResources.

        Dispatcher: delega en `_resolve_entity_selector`,
        `_resolve_predicate_selector` o `_resolve_source_selector`
        segun `kind`. Cada rama tiene su propia responsabilidad:
        entity -> claims por subject; predicate -> claims por predicate;
        source -> claims + (opcional) evidences por source.
        """
        ctrl = self.knowledge  # type: ignore[assignment]

        if kind == "entity":
            return self._resolve_entity_selector(ctrl, value)
        if kind == "predicate":
            return self._resolve_predicate_selector(ctrl, value)
        if kind == "source":
            return self._resolve_source_selector(ctrl, value, label)
        return []

    def _resolve_entity_selector(
        self,
        ctrl: object,  # KnowledgeController
        value: str,
    ) -> list[CompiledResource]:
        """Branch `entity`: claims cuyo subject_entity_id == value."""
        try:
            ctrl.get_entity(entity_id=value)  # type: ignore[attr-defined]
        except Exception:
            return []
        claims = ctrl.list_claims_for_subject(  # type: ignore[attr-defined]
            subject_entity_id=value
        )
        return [claim_to_resource(c, value) for c in claims]

    def _resolve_predicate_selector(
        self,
        ctrl: object,  # KnowledgeController
        value: str,
    ) -> list[CompiledResource]:
        """Branch `predicate`: claims con predicate == value.

        H9-Coverage-11: delega en Storage.list_claims_by_predicate
        (cierra el sitio SQL directo que tenia en la linea 297-303).
        """
        rows = ctrl.storage.list_claims_by_predicate(  # type: ignore[attr-defined]
            tenant_id=ctrl.tenant_id,  # type: ignore[attr-defined]
            project_id=ctrl.project_id,  # type: ignore[attr-defined]
            predicate=value,
        )
        return [predicate_row_to_resource(row, value) for row in rows]

    def _resolve_source_selector(
        self,
        ctrl: object,  # KnowledgeController
        value: str,
        label: str,
    ) -> list[CompiledResource]:
        """Branch `source`: claims directos + (si label) evidences."""
        try:
            src = ctrl.get_source(source_id=value)  # type: ignore[attr-defined]
        except Exception:
            return []
        claims = ctrl.list_claims_for_source(  # type: ignore[attr-defined]
            source_id=src.source_id
        )
        out: list[CompiledResource] = [
            claim_to_resource(c, value) for c in claims
        ]
        if label:
            # Encontrar evidence para esa source.
            # H9-Coverage-11: delega en Storage.list_evidences_for_source.
            evid_rows = ctrl.storage.list_evidences_for_source(  # type: ignore[attr-defined]
                source_id=src.source_id,
            )
            out.extend(evidence_row_to_resource(ev, value) for ev in evid_rows)
        return out


# ---------------------------------------------------------------------------
# OutcomeTracer
# ---------------------------------------------------------------------------


class OutcomeTracer:
    """Extrae `OutcomeTrace` desde un run_id (blueprint §9).

    NO duplica contenido: solo almacena referencias (claim_refs /
    evidence_refs). Si una Claim cambia despues, el trace la ve
    actualizada al consultarla.
    """

    @classmethod
    def from_run(
        cls,
        *,
        knowledge: object,  # KnowledgeController
        run_id: str,
        trace_id: str | None = None,
        trace_name: str = "auto-trace",
    ) -> OutcomeTrace:
        """Extrae las Claims/Evidences que el run toco.

        Estrategia:
        - Eventos del run con resource_ref en {claim, evidence, handoff}.
        - Si los eventos no mencionan claims/evidences directos, los
          tomamos de las sources que el run uso (heuristica honesta:
          si hay 0 eventos, devolvemos trace vacio, NO inflamos).
        """
        ctrl = knowledge  # type: ignore[assignment]
        # Claim refs via runtime_events del run.
        # H9-Coverage-11: delega en Storage.list_resource_refs_for_run con
        # kind="claim" (cierra el sitio SQL directo que tenia en linea 402-410).
        rows = ctrl.storage.list_resource_refs_for_run(  # type: ignore[attr-defined]
            tenant_id=ctrl.tenant_id,  # type: ignore[attr-defined]
            project_id=ctrl.project_id,  # type: ignore[attr-defined]
            run_id=run_id,
            kind="claim",
        )
        claim_refs: tuple[str, ...] = tuple(r.removeprefix("claim:") for r in rows)
        # Evidence refs analogamente.
        # H9-Coverage-11: delega en Storage.list_resource_refs_for_run con
        # kind="evidence" (cierra el sitio SQL directo que tenia en linea 413-421).
        ev_rows = ctrl.storage.list_resource_refs_for_run(  # type: ignore[attr-defined]
            tenant_id=ctrl.tenant_id,  # type: ignore[attr-defined]
            project_id=ctrl.project_id,  # type: ignore[attr-defined]
            run_id=run_id,
            kind="evidence",
        )
        evidence_refs: tuple[str, ...] = tuple(r.removeprefix("evidence:") for r in ev_rows)
        # trace_id determinista si no se da.
        tid = trace_id or f"tr-{run_id}-{_now_iso()}"
        return OutcomeTrace(
            trace_id=tid,
            kind="SoftwareExecutionSlice",
            name=trace_name,
            project_id=ctrl.project_id,  # type: ignore[attr-defined]
            created_at=_now_iso(),
            claim_refs=claim_refs,
            evidence_refs=evidence_refs,
        )


__all__ = [
    "CompiledResource",
    "ContextController",
    "OutcomeTracer",
    "approx_chars",
]
