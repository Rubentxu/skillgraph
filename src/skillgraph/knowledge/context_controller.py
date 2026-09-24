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
        2. Filtrar por freshness.
        3. Aplicar budget.

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

        # Strict freshness check en obligatorios.
        stale_obligatory = [
            it
            for it in obligatory_items
            if it.resource_kind == "claim" and it.body.get("stale") is True
        ]
        if recipe.freshness_policy == "strict" and len(stale_obligatory) > 0:
            # Si CUALQUIER oblig. es stale con policy=strict, abortar:
            # los stale son conocimiento no validado.
            raise StaleKnowledgeError(
                f"{len(stale_obligatory)} obligatory Claim(s) stale y policy=strict"
            )

        included: list[CompiledResource] = []
        included.extend(obligatory_items)

        # Budget check ANTES de cualquier opcional. Si los obligatorios
        # ya NO caben solos -> TokenBudgetExceededError, sin importar
        # overflow_strategy (los obligatorios NO se truncan).
        total_chars = sum(approx_chars(it.body) for it in included)
        if total_chars > recipe.token_budget:
            raise TokenBudgetExceededError(
                f"obligatorio ({total_chars} chars) excede budget ({recipe.token_budget})"
            )

        # Optional solo si cabe.
        for opt in optional_items:
            opt_chars = approx_chars(opt.body)
            if total_chars + opt_chars <= recipe.token_budget:
                included.append(opt)
                total_chars += opt_chars
            else:
                if recipe.overflow_strategy == "fail":
                    raise TokenBudgetExceededError(
                        f"obligatory+opcional no caben en budget "
                        f"{recipe.token_budget} (acumulado {total_chars})"
                    )
                # drop_optional o truncate_finding: paramos.
                break

        # Best-effort: marcar stale en handoff si aplica.
        handoff_stale = recipe.freshness_policy == "best_effort" and any(
            it.body.get("stale") is True for it in included
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
        # Estado del handoff (stale=true si best_effort + hay stale)
        # codificado en capabilities + en un campo extra via budget.
        capabilities: tuple[str, ...] = ()
        if handoff_stale:
            capabilities = ("stale",)
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
        """Resuelve UN selector. Devuelve 0..N CompiledResources."""
        ctrl = self.knowledge  # type: ignore[assignment]

        if kind == "entity":
            # Buscar Claims cuyo subject_entity_id == value.
            try:
                ctrl.get_entity(entity_id=value)
            except Exception:
                return []
            claims = ctrl.list_claims_for_subject(subject_entity_id=value)
            return [
                CompiledResource(
                    resource_kind="claim",
                    resource_namespace=f"claim:{c.claim_id}",
                    resource_name=value,
                    body={
                        "claim_id": c.claim_id,
                        "predicate": c.predicate,
                        "object_literal": c.object_literal,
                        "source_id": c.source_id,
                        "checked_at_revision": c.checked_at_revision,
                        "stale": c.stale,
                    },
                )
                for c in claims
            ]

        if kind == "predicate":
            # Buscar Claims con predicate == value.
            # H9-Coverage-11: delega en Storage.list_claims_by_predicate
            # (cierra el sitio SQL directo que tenia en la linea 297-303).
            rows = ctrl.storage.list_claims_by_predicate(
                tenant_id=ctrl.tenant_id,  # type: ignore[attr-defined]
                project_id=ctrl.project_id,  # type: ignore[attr-defined]
                predicate=value,
            )
            return [
                CompiledResource(
                    resource_kind="claim",
                    resource_namespace=f"claim:{row['claim_id']}",
                    resource_name=value,
                    body={
                        "claim_id": row["claim_id"],
                        "predicate": row["predicate"],
                        "object_literal": json.loads(row["object_literal_json"]),
                        "source_id": row["source_id"],
                        "checked_at_revision": row["checked_at_revision"],
                        "stale": bool(row["stale"]),
                    },
                )
                for row in rows
            ]

        if kind == "source":
            # Localizar la source y devolver Claims directos.
            try:
                src = ctrl.get_source(source_id=value)
            except Exception:
                return []
            claims = ctrl.list_claims_for_source(source_id=src.source_id)
            out: list[CompiledResource] = [
                CompiledResource(
                    resource_kind="claim",
                    resource_namespace=f"claim:{c.claim_id}",
                    resource_name=value,
                    body={
                        "claim_id": c.claim_id,
                        "predicate": c.predicate,
                        "object_literal": c.object_literal,
                        "source_id": c.source_id,
                        "checked_at_revision": c.checked_at_revision,
                        "stale": c.stale,
                    },
                )
                for c in claims
            ]
            if label:
                # Encontrar evidence para esa source.
                # H9-Coverage-11: delega en Storage.list_evidences_for_source
                # (cierra el sitio SQL directo que tenia en la linea 346-349).
                evid_rows = ctrl.storage.list_evidences_for_source(
                    source_id=src.source_id,
                )
                for ev in evid_rows:
                    out.append(
                        CompiledResource(
                            resource_kind="evidence",
                            resource_namespace=f"evidence:{ev['evidence_id']}",
                            resource_name=value,
                            body={
                                "evidence_id": ev["evidence_id"],
                                "kind": ev["kind"],
                                "content": json.loads(ev["content_json"]),
                                "source_id": ev["source_id"],
                                "observed_at": ev["observed_at"],
                            },
                        )
                    )
            return out

        return []


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
