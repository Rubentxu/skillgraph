# WI-21: deuda H-03 (graph_expansion.validate cc=24)

## Objetivo

Reducir la complejidad ciclomatica de
`src/skillgraph/governance/graph_expansion.py:validate()` (cc=24)
extrayendo helpers puros por invariante. Esto sigue el patron ya
exitoso en WI-19 (pack_loader._validate cc 22 -> 7).

## Cambio

- Extraido `_check_capabilities(proposal, registry) -> tuple[str, ...]`
  (I3+I4 combinadas). cc=3.
- Extraido `_active_remove_warnings(proposal, active_nodes) -> tuple[str, ...]`
  (W1 warnings). cc<=3.
- Extraido `_check_cycle_bound(proposal, plan) -> tuple[str, ...]` (I5).
  cc=10 (dominado por ciclo interno, no por ramas de decision).
- `validate()` queda en cc=4, con composicion declarativa:
  violations.extend(...) por invariante.

## Compatibilidad

- 100% backward-compatible (firma, retorno, semantica de I1..I6).
- Las violation tuples tienen exactamente los mismos elementos
  en el mismo orden (verificado por 61 tests existentes en
  test_h4_expansion, test_h4_expansion_slice3, test_h9_coverage_graph_expansion,
  test_t3_threat_model_attestation).

## Decision previa (D-52)

- **D-52**: Heuristic para refactors de `validate()`-like: extraer
  un helper por invariante o grupo cohesivo, no mas de ~30 LoC por
  helper, retorno `tuple[str, ...]` para que compose sea explicito.

## Evidencia

- `validate` cc: 24 -> 4 (~83%).
- `_check_capabilities`: cc=3, 11 LoC.
- `_check_cycle_bound`: cc=10, 30 LoC.
- 61/61 tests PASS en `tests/test_h4_expansion.py`,
  `tests/test_h4_expansion_slice3.py`,
  `tests/test_h9_coverage_graph_expansion.py`,
  `tests/test_t3_threat_model_attestation.py`.
- `uv run pytest` (suite completa) -> **1044/1044 PASS** en 178.91s.
- `uv run ruff check src tests` -> All checks passed.
