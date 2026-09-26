# WI-25: deuda H-03 (knowledge_invalidator.traverse_invalidations cc=13)

## Objetivo

Reducir cc de `traverse_invalidations` (cc=13) en
`src/skillgraph/knowledge/knowledge_invalidator.py`. El alto cc
venia del bucle por hop con `for claim_id` -> `for evidence`
-> `for other` anidados, mas el `try/except` interno y el check
de frontera para HopLimitExceededWarning.

## Cambio

Extraidos 3 helpers privados:

- `_seed_hop_zero(controller, source_id) -> (frontier, hop_dist, visited)` (cc=3):
  buildea el estado inicial (claims directas que referencian source_id).
- `_expand_one_hop(frontier_in, *, visited_claims, visited_evidence, controller)`
  (cc=7): un hop de expansion via evidencia compartida.
- `_warn_if_truncated(frontier, *, hop, max_hops) -> bool` (cc=3):
  emite HopLimitExceededWarning si la frontera no se agoto.

`traverse_invalidations` queda como orquestador (cc=5) que:
1. seed hop 0
2. itera hops expandiendo frontier
3. marca truncated al final del ultimo hop si toca

## Compatibilidad

- 100% backward-compatible: misma semantica BFS con max_hops,
  mismo handling de cycles (visited_claims), mismo HopLimitExceededWarning,
  mismo contrato InvalidationResult.
- 10/10 tests PASS en `tests/test_knowledge_invalidation.py`.

## Decision previa (D-58)

- **D-58**: Traversal BFS hops se descompone en seed + expand + warn.
  El expand helper muta visited_claims/visited_evidence in-place
  (acuerdos: parametros `set` por referencia) y devuelve SOLO el
  new_frontier. El caller reconstruye next_frontier explicitamente.

## Evidencia

- `traverse_invalidations` cc: 13 -> 5.
- 3 helpers, cc <= 7.
- 1044/1044 PASS en suite completa (180.31s).
- ruff: All checks passed.
