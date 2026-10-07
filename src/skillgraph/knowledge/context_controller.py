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
from typing import Literal

from skillgraph.core.errors import (
    MissingObligatoryError,
    StaleKnowledgeError,
    TokenBudgetExceededError,
    UnknownEntityError,
    UnknownSourceError,
)
from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.graph import OutcomeTrace
from skillgraph.platform.ports import StoredClaim, StoredEvidence
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
    return tuple(it for it in items if it.resource_kind == "claim" and it.body.get("stale") is True)


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
        raise StaleKnowledgeError(f"{len(stale)} obligatory Claim(s) stale y policy=strict")


@dataclass(frozen=True, slots=True)
class Omision:
    """**B30: un recurso que NO cabe en el presupuesto, nombrado.**

    Antes de este bloque el presupuesto truncaba en silencio: `apply_budget
    hacia un `break` y su llamante descartaba el resto con un `_`. El
    receptor del handoff recibía una lista más corta y **no tenía ninguna forma
    de saberlo** —ni de calcularlo, porque `included` guardaba lo que entró
    pero no el total de candidatos—.

    `chars` es lo que hace la omisión **accionable**: saber que se cayó
    «opt-2» sin saber cuánto era deja al receptor sin poder ni decidir si le
    importa ni pedirlo con otro presupuesto.

    **NO LLEVA `motivo` A PROPOSITO, Y ESTA MEDIDO.** Los tres valores de
    `OverflowStrategy` que producen una omisión (`drop_optional` y
    `truncate_finding`) la producen **por lo mismo**: no cabía. El tercero,
    `fail`, lanza `TokenBudgetExceededError` y no deja omisión ninguna. Luego
    un campo `motivo` con un único valor alcanzable sería el
    `empate_en_la_jerarquia` de B28: un Literal cerrado que nombra algo que
    ninguna ejecución puede distinctions. Si algún día hay un segundo motivo
    real, entonces se declara —y se mide antes.
    """

    kind: str
    namespace: str
    name: str
    chars: int

    def __post_init__(self) -> None:
        from skillgraph.core.errors import ValidationError

        if not self.kind:
            raise ValidationError("Omision.kind vacio")
        if not self.namespace:
            raise ValidationError("Omision.namespace vacio")
        if not self.name:
            raise ValidationError("Omision.name vacio")
        if self.chars <= 0:
            # Un omitido de 0 chars no es un omitido: es ruido, y hace que
            # quien lo lea dude de los demas.
            raise ValidationError(f"Omision.chars debe ser > 0, recibio {self.chars}")

    def como_tupla(self) -> tuple[str, str, str, int]:
        """La forma que viaja en `HandoffKnowledge.omitidos`.

        Una **tupla**, no un `dict`, por la misma razon que WI-113 midio en
        `AgentResult.result`: un `dict` dentro de un `frozen` deja la
        estructura mutable por dentro, y aqui el receptor es codigo externo al
        repo.
        """
        return (self.kind, self.namespace, self.name, self.chars)

    @classmethod
    def desde_recurso(cls, recurso: CompiledResource) -> Omision:
        """Construye la omision de un recurso que no cupo."""
        return cls(
            kind=recurso.resource_kind,
            namespace=recurso.resource_namespace,
            name=recurso.resource_name,
            chars=approx_chars(recurso.body),
        )


#: B30. `07-SPEC` §7 lista `complete`/`partial`/`blocked`, y **solo dos son
#: alcanzables**: `blocked` no se puede representar en un `Handoff` que EXISTE,
#: porque cuando falta algo `compile_handoff` LANZA
#: `TokenBudgetExceededError`, `StaleKnowledgeError` o
#: `MissingObligatoryError` — una excepcion tipada, no un handoff. Declararlo
#: seria repetir el valor inalcanzable que B28 elimino de `MotivoDescarte`.
#: La cobertura de `blocked` no se pierde: cambia de forma, y una excepcion que
#: lo nombra es mas fuerte que un campo que valdria `blocked`.
#:
#: **Y NO HAY CONSTANTE `Final` AL LADO, A PROPOSITO.** `AGENTS.md` §2.4 pide
#: la constante cuando el `Literal` se usa para VALIDAR entrada. Aqui no se
#: valida entrada: `PresupuestoAplicado.cobertura` es una PROPIEDAD DERIVADA de
#: si hay omisiones, y nadie la comprueba contra un conjunto. Publicar el
#: conjunto seria un segundo sitio donde la verdad vive, y este bloque entero
#: va de que no haya dos verdades que puedan discrepar.
Cobertura = Literal["complete", "partial"]


@dataclass(frozen=True, slots=True)
class PresupuestoAplicado:
    """**B30: el resultado del presupuesto, con lo que quedo FUERA.**

    Sustituye a la tupla `(incluidos, total_chars)`. El contrato viejo no
    puede expresar la propiedad que B30 arregla, y anadir una segunda funcion
    que si la exprese dejaria dos responsabilidades donde hace falta una —que
    es la duplicacion que `AGENTS.md` prohibe—.
    """

    incluidos: tuple[CompiledResource, ...]
    omitidos: tuple[Omision, ...]
    chars_usados: int
    budget_chars: int

    @property
    def cobertura(self) -> Cobertura:
        """**Derivada, no declarada.** `07-SPEC` §7 dice que el slice «declara»
        la cobertura; declararla seria un campo, y un campo lo puede mentir
        sin que nada lo note. Aqui es una propiedad derivada de si hay
        omisiones, luego **no hay dos verdades que puedan discrepar**.
        """
        return "partial" if self.omitidos else "complete"


def apply_budget(
    obligatory: Sequence[CompiledResource],
    optional: Sequence[CompiledResource],
    *,
    budget_chars: int,
    overflow_strategy: str,
) -> PresupuestoAplicado:
    """Aplica el budget de caracteres a obligatorios + opcionales.

    Pasos:
    1. Suma obligatorios. Si exceden budget_chars -> TokenBudgetExceededError
       (los obligatorios NO se truncan).
    2. Itera opcionales en orden. Cada uno que cabe se incluye. Si no
       cabe: si overflow_strategy=='fail' -> TokenBudgetExceededError;
       en caso contrario ('drop_optional' | 'truncate_finding') -> para.

    Returns:
        `PresupuestoAplicado` con lo que ENTRA **y lo que se queda FUERA**.
    """
    incluidos: list[CompiledResource] = list(obligatory)
    total_chars = sum(approx_chars(it.body) for it in incluidos)
    if total_chars > budget_chars:
        raise TokenBudgetExceededError(
            f"obligatorio ({total_chars} chars) excede budget ({budget_chars})"
        )
    omitidos: list[Omision] = []
    opcionales_vistos = 0
    for opt in optional:
        opcionales_vistos += 1
        opt_chars = approx_chars(opt.body)
        if total_chars + opt_chars <= budget_chars:
            incluidos.append(opt)
            total_chars += opt_chars
            continue
        if overflow_strategy == "fail":
            raise TokenBudgetExceededError(
                f"obligatory+opcional no caben en budget {budget_chars} (acumulado {total_chars})"
            )
        # drop_optional o truncate_finding: paramos sin incluir el opt.
        #
        # **B30: Y DECIMOS QUE SE PARÓ, Y DECIMOS TODO LO QUE SE PERDIÓ.**
        #
        # El `break` de antes era un silencio. Lo que se acumula desde aquí es
        # eso, con **una decisión que merece nombre**: se declara **el que no
        # cupo Y todos los que iban detrás**, no solo el primero.
        #
        # MEDIDO, y lo decidió una propiedad: quien pidió un contexto con
        # `opt-1, opt-2, opt-3` y no obtuvo ninguno tiene que poder reconstruir
        # que los tres estaban disponibles. Declarar solo `opt-1` deja un
        # número que **subestima lo que se perdió**, y un informe que
        # subestima la pérdida se lee como «se cayó casi nada».
        #
        # El corte sigue siendo un corte —lo que entra **no** cambia—; lo que
        # cambia es lo que se declara. `opcionales_vistos` lleva la cuenta sin
        # depender de aritmética sobre `incluidos`, que mezcla obligatorios y
        # opcionales y haría la posición fragile.
        omitidos.extend(Omision.desde_recurso(r) for r in optional[opcionales_vistos - 1 :])
        break
    return PresupuestoAplicado(
        incluidos=tuple(incluidos),
        omitidos=tuple(omitidos),
        chars_usados=total_chars,
        budget_chars=budget_chars,
    )


def build_capabilities(
    included: Sequence[CompiledResource],
    *,
    policy: str,
) -> tuple[str, ...]:
    """Devuelve capabilities del handoff segun frescura aplicada.

    Si policy=='best_effort' y algun included tiene body['stale']=True
    -> ('stale',). En caso contrario -> tuple vacio.

    ── LO QUE DEVUELVE NO ES SIEMPRE UNA CAPABILITY. ──

    `'stale'` es un valor de `FreshnessState`
    (`core/runtime_types.py::FreshnessState`), no un tipo de capacidad.
    Sale de aqui, entra en el hash firmado de `Handoff`, y el Adapter lo
    imprime bajo un encabezado que dice «## Capabilities». Medido con
    Storage real (`.pipelinek/b3_stale_measure.py`):

        best_effort -> capabilities=('stale',)
        strict      -> StaleKnowledgeError (el handoff ni se construye)

    **DECIDIDO EL 2026-10-03: se queda asi, y es deuda declarada, no
    descuido.** Sacarlo de `capabilities` cambia `context_hash` de todo
    handoff que hoy lo lleva, y el hash firmado es ruptura de datos:
    materia de B8. El estado de frescura YA viaja por otra via
    (`HandoffKnowledge.included` lleva el recurso con su `stale`), asi
    que moverlo no perderia informacion — solo moveria el hash.

    El guard que vigila el comportamiento actual, en las dos
    direcciones, es
    `tests/test_b3_capability_kernel.py::TestLaSenalDeFrescuraPorElCaminoQueSiLlega`
    (y su hermano, que fija que por el camino del runtime NO llega).
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


def stored_claim_to_resource(
    claim: StoredClaim,
    resource_name: str,
) -> CompiledResource:
    """Mapea un ``StoredClaim`` a ``CompiledResource``."""
    return CompiledResource(
        resource_kind="claim",
        resource_namespace=f"claim:{claim.claim_id}",
        resource_name=resource_name,
        body={
            "claim_id": claim.claim_id,
            "predicate": claim.predicate,
            "object_literal": claim.object_literal,
            "source_id": claim.source_id,
            "checked_at_revision": claim.checked_at_revision,
            "stale": claim.stale,
        },
    )


def stored_evidence_to_resource(
    evidence: StoredEvidence,
    resource_name: str,
) -> CompiledResource:
    """Mapea un ``StoredEvidence`` a ``CompiledResource``."""
    return CompiledResource(
        resource_kind="evidence",
        resource_namespace=f"evidence:{evidence.evidence_id}",
        resource_name=resource_name,
        body={
            "evidence_id": evidence.evidence_id,
            "kind": evidence.kind,
            "content": evidence.content,
            "source_id": evidence.source_id,
            "observed_at": evidence.observed_at,
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
        enforce_strict_freshness(obligatory_items, policy=recipe.freshness_policy)

        # Paso 3: aplicar budget.
        #
        # **B30: `presupuesto` SE USA ENTERO, Y ANTES NO SE PODIA.** Antes era
        # `included, _total_chars = apply_budget(...)`: el `_total_chars` no se
        # usaba y lo que se caia **no se decia por ninguna parte**. Un handoff
        # truncado era indistinguible de uno completo, y quien lo recibia no
        # tenia ni forma de calcular la diferencia.
        presupuesto = apply_budget(
            obligatory_items,
            optional_items,
            budget_chars=recipe.token_budget,
            overflow_strategy=recipe.overflow_strategy,
        )
        included = presupuesto.incluidos

        # Capabilities segun freshness aplicada.
        capabilities = build_capabilities(included, policy=recipe.freshness_policy)

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
            # B30: lo que se quedó fuera viaja en el handoff, y por tanto
            # entra en el `context_hash` firmado. Un campo fuera del hash
            # repetiría la distancia que WI-111 midió: el Adapter vería unas
            # omisiones que el Core no firmó.
            omitidos=tuple(o.como_tupla() for o in presupuesto.omitidos),
        )
        execution = HandoffExecution(
            workspace_ref=workspace_ref,
            source_revision=source_revision,
            # El límite **y** lo usado: con los dos, el receptor sabe cuánto
            # margen quedó, que es lo que convierte «se cayó algo» en «se cayó
            # algo y por mucho».
            budget={
                "token_budget_chars": recipe.token_budget,
                "chars_usados": presupuesto.chars_usados,
                "omitidos": len(presupuesto.omitidos),
            },
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
        except UnknownEntityError:
            # Una entidad ausente produce un branch vacio, que es el
            # resultado legitimo. Antes se capturaba `Exception` entera
            # (AGENTS.md 11.14.4), con lo que un fallo de I/O o un bug
            # del controller se disfrazaba de "esa entidad no existe"
            # y el compile terminaba con un grafo incompleto, sin
            # senal ni error.
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
        rows = ctrl.knowledge.list_claims_by_predicate(  # type: ignore[attr-defined]
            tenant_id=ctrl.tenant_id,  # type: ignore[attr-defined]
            project_id=ctrl.project_id,  # type: ignore[attr-defined]
            predicate=value,
        )
        return [stored_claim_to_resource(row, value) for row in rows]

    def _resolve_source_selector(
        self,
        ctrl: object,  # KnowledgeController
        value: str,
        label: str,
    ) -> list[CompiledResource]:
        """Branch `source`: claims directos + (si label) evidences."""
        try:
            src = ctrl.get_source(source_id=value)  # type: ignore[attr-defined]
        except UnknownSourceError:
            # Igual que en el branch `entity`: la ausencia es un branch
            # vacio legitimo; cualquier otro fallo debe propagar.
            return []
        claims = ctrl.list_claims_for_source(  # type: ignore[attr-defined]
            source_id=src.source_id
        )
        out: list[CompiledResource] = [claim_to_resource(c, value) for c in claims]
        if label:
            # Encontrar evidence para esa source.
            # H9-Coverage-11: delega en Storage.list_evidences_for_source.
            evid_rows = ctrl.knowledge.list_evidences_for_source(  # type: ignore[attr-defined]
                source_id=src.source_id,
            )
            out.extend(stored_evidence_to_resource(ev, value) for ev in evid_rows)
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
        rows = ctrl.knowledge.list_resource_refs_for_run(  # type: ignore[attr-defined]
            tenant_id=ctrl.tenant_id,  # type: ignore[attr-defined]
            project_id=ctrl.project_id,  # type: ignore[attr-defined]
            run_id=run_id,
            kind="claim",
        )
        claim_refs: tuple[str, ...] = tuple(r.removeprefix("claim:") for r in rows)
        # Evidence refs analogamente.
        # H9-Coverage-11: delega en Storage.list_resource_refs_for_run con
        # kind="evidence" (cierra el sitio SQL directo que tenia en linea 413-421).
        ev_rows = ctrl.knowledge.list_resource_refs_for_run(  # type: ignore[attr-defined]
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
