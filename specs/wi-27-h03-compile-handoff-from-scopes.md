# WI-27: deuda H-03 (file_handoff.compile_handoff_from_scopes cc=12)

## Objetivo

Reducir cc de `compile_handoff_from_scopes` (cc=12) en
`src/skillgraph/knowledge/file_handoff.py`. El alto cc venia de:
1. Cadena de 5 checks `isinstance + raise TypeError`.
2. Cobertura completa con bucles anidados + `HandoffBlockedError`.
3. Construccion in-line de la `ContextRecipe` sintetica.

## Cambio

Extraidos 3 helpers privados:

- `_validate_inputs(*, context_controller, scope_recipe) -> (ctx, kc, sq)`
  (cc=6): valida tipos de entrada via isinstance+raise TypeError.
- `_enforce_coverage_or_raise(*, ..., require_complete_coverage)` (cc=7):
  early-return si `require_complete_coverage=False`. Si no,
  calcula `missing_sources`, `missing_signatures` y lanza
  `HandoffBlockedError` si hay carencia o firmas no-fresh.
- `_build_synth_recipe(base_recipe) -> ContextRecipe` (cc=1):
  construye ContextRecipe con `obligatory=()` (las firmas viven
  en el manifest).

`compile_handoff_from_scopes` queda como orquestador puro (cc=1):
secuencia declarativa validate -> aggregate -> manifest ->
enforce -> synth -> compile_handoff -> return.

## Compatibilidad

- 100% backward-compatible:
  - Mismas excepciones (TypeError, NotImplementedError, HandoffBlockedError)
    con mismos mensajes.
  - Mismo orden de las firmas en la lista `missing_signatures`.
  - Misma sintesis de ContextRecipe (mismos campos copiados).
- 21/21 tests PASS en `tests/test_h13_handoff_expert.py`.

## Decision previa (D-60)

- **D-60**: Orquestadores de pipeline de 5+ pasos suelen tener
  exactamente 3 helpers: `_validate_inputs`, `_enforce_*_or_raise`,
  `_build_synth_*`. Esta triada aparece naturalmente y reduce cc
  del orquestador a 1.

## Evidencia

- `compile_handoff_from_scopes` cc: 12 -> 1 (-92%).
- 3 helpers extraidos: cc=6, cc=7, cc=1.
- 1044/1044 PASS en suite completa (185.42s).
- ruff: All checks passed.
