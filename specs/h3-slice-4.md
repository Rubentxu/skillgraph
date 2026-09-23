# Slice 4 — Invalidación transitiva + event

> Sub-spec del H3 (`specs/h3-knowledge.md`). Define el algoritmo
> de invalidación que recorre dependencias y marca Claims como stale.
> Depende de Slices 1, 2 y 3 implementados.
> NO se ejecuta antes de que el spec H3 esté firmado (D2, D3, D4).
> Estado: **DISEÑO**.

## 1. Objetivo

Implementar el algoritmo de invalidación del blueprint §8
literalmente:

```text
detect_source_change(source_id)
  -> locate_direct_claims(source_id)
  -> traverse_relevant_dependencies(transitively, max_hops)
  -> mark_affected_claims_stale(claim_ids)
  -> identify_active_consumers(claim_ids)
  -> schedule_required_refresh()
  -> verify_new_claims()        -- cuando el refresco se ejecuta
  -> publish_new_revisions()    -- emite event de KnowledgeUpdated
```

NO regenera todo el grafo. La invalidación es inmediata; la
actualización bajo demanda.

## 2. Decisiones de diseño

### D16 — Dependencias transitivas via `claim_evidence` + Findings

Una Claim depende de otra si:
- Comparten la misma `Evidence` (N:M).
- Una es `subject_entity_id` de un `Finding` que referencia otra.
- Comparten `source_id` y la misma `Entity` está afectada.

Para H3 (sin grafos completos): usar **shared Source** como
proxy de dependencia transitiva. Si un source cambia, todas las
Claims que referencian ese source (directa o transitivamente via
`checked_at_revision`) se invalidan.

### D17 — `max_hops` configurable, default 2

```python
DEFAULT_MAX_HOPS = 2
```

Hops: source→claim→evidence→claim. Con `max_hops=2` se cubren las
dependencias directas y las de "segundo nivel" (claim que usa
evidence de otra claim). Hops mayores se consideran H4+.

### D18 — Event `KnowledgeInvalidated` en EventLog

```python
# runtime_types.py
EventType = Literal[
    # ... existentes ...
    "KnowledgeInvalidated",
    "KnowledgeRefreshed",
]
```

El event NO contiene la lista de Claims stale (puede ser enorme).
Contiene: `source_id`, `count`, `hop_chain` (resumen), `correlation_id`.

### D19 — Refresh como operación bajo demanda

`KnowledgeController.refresh_source(source_id, *, new_revision)`:
1. Lee el source actual.
2. Captura nuevo content_hash vía Git (Slice 3).
3. Marca todas las Claims stale como `stale=0` solo si la nueva
   revision las valida (comparación hash-a-hash).
4. Emite event `KnowledgeRefreshed`.

NO se hace auto-refresh. El caller decide cuándo refrescar.

## 3. API pública

```python
class KnowledgeController:
    # ... Slice 2 ...

    def invalidate_from_source(
        self,
        *,
        source_id: SourceID,
        max_hops: int = DEFAULT_MAX_HOPS,
    ) -> list[ClaimID]:
        """Marca stale las Claims que dependen (transitivamente) del source.
        Devuelve la lista de ClaimIDs invalidados.
        """

    def refresh_source(
        self,
        *,
        source_id: SourceID,
        new_revision: str,
    ) -> list[ClaimID]:
        """Re-valida Claims contra nueva revision. Devuelve las reactivadas."""

    def list_stale_claims(self) -> list[Claim]:
        """Lista todas las Claims stale del proyecto actual."""
```

## 4. Errores nuevos

```python
class CyclicDependencyError(SkillGraphError):  code = "sg_cyclic_dependency"
class RefreshFailedError(SkillGraphError):     code = "sg_refresh_failed"
class HopLimitExceededError(SkillGraphWarning): code = "sg_hop_limit_exceeded"
```

`HopLimitExceededError` indica que se alcanzó `max_hops` sin
agotar la cadena. NO es fatal — el caller decide si continuar.

## 5. Tests (`tests/test_knowledge_invalidation.py`)

**10 tests propuestos:**

### Happy path (4)
1. `test_invalidate_marks_direct_claims_stale` — source A, claim C1
   con `source_id=A`. Invalidar A → C1 stale=1.
2. `test_invalidate_propagates_via_evidence` — source A, evidence E1
   de A; claim C1 con `evidence_ids=(E1,)`. Invalidar A → C1 stale
   (segundo hop).
3. `test_invalidate_respects_max_hops` — chain de 4 hops con
   `max_hops=2` solo invalida los 2 primeros niveles.
4. `test_refresh_reactivates_claims` — invalidar, refrescar con
   nueva revision, claims stale=0.

### Errores (3)
5. `test_invalidate_unknown_source_raises` — `UnknownSourceError`.
6. `test_refresh_with_same_revision_no_op` — `new_revision` igual
   a la actual → no cambia nada, no emite event.
7. `test_hop_limit_exceeded_emits_warning` — `max_hops=1` y chain
   de 3 hops → warning emitido pero no excepción.

### Eventos (2)
8. `test_invalidate_emits_knowledge_invalidated_event` — event
   contiene `source_id` + `count`.
9. `test_refresh_emits_knowledge_refreshed_event` — mismo shape.

### Edge cases (1)
10. `test_invalidate_with_no_claims_is_noop` — source sin claims
    → retorna lista vacía, NO emite event.

## 6. Criterios de aceptación

Slice 4 completado cuando:
1. 10 tests verdes (`bash scripts/ci.sh` → 161+17+14+8+10 = **210 passed**).
2. `KnowledgeInvalidated` event añadido a `EventType` Literal.
3. Algoritmo sigue blueprint §8 **literalmente** (mismo orden).
4. Commit: `feat(h3-s4): invalidación transitiva + KnowledgeInvalidated event`.

## 7. Out of scope

- **Auto-refresh** después de invalidación: NO. El caller decide.
- **Notificación a RunController ACTIVE**: eso es D3 (sync invalidación).
  Slice 4 solo emite el event; la integración con runs es slice 5
  o un slice 4.5 según la decisión D3.
- **Invalidación cruzada entre proyectos**: NO. Slice 4 es por-proyecto.

## 8. Riesgos

### R9 — Performance sobre grafos grandes

`traverse_dependencies` con `max_hops=2` puede ser O(N²) en el
número de Claims. Para H3 (<10k Claims) es aceptable. H4+
introduce índices adicionales.

### R10 — Ciclos en dependencias

`source→claim→evidence→claim→source` es un ciclo. La implementación
debe detectar ciclos y lanzar `CyclicDependencyError` en vez de
loop infinito. Estrategia: set de visitados por traversal.

### R11 — Refresh sin nueva evidence

Si `refresh_source` se llama con `new_revision` que NO tiene
evidences nuevas, las Claims stale permanecen stale. Es
correcto: significa que la nueva revisión no aporta datos para
revalidar.

## 9. Referencias

- Spec padre: `specs/h3-knowledge.md` §4.
- Blueprint §8 (algoritmo literal).
- ADR-0007 (invalidación propaga por dependencias relevantes).
- Slice 2 (KnowledgeController base).
