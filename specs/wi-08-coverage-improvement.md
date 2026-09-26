# WI-08 — Coverage hardening `governance/improvement.py` 84%→≥90%

**WorkItem ID**: WI-08
**Fecha**: 2026-09-26
**Workflow SDDK**: A-min (single apply, scope acotado a tests/ + docs)
**Status**: ✅ CLOSED

## Contexto

Auditoría técnica senior identificó 6 módulos con cobertura 81-89% (H-14).
Verificación con SDDK reveló que la mayoría ya estaban cerrados por stewardship
anterior (26-Sep 09:40: file_signature 100%, file_scope 100%, governance/receipts 99%).

**Gap material real restante**:
- `file_handoff.py` (85%→93%) → cerrado en WI-07.
- `governance/improvement.py` (84%→100%) → **WI-08 actual**.

## Decisiones

- **D-23**: WI-08 es solo tests; NO tocar producción. Mismo patrón que WI-06/WI-07.
- **D-24**: Stewardship créatif autorizado por operador (26-Sep 18:50).
- **D-25**: Bump `__version__` post-WI-08 innecesario (sigue en `0.14.5.dev0`).
- **D-26**: NO release/tag en este workitem.

## Scope

Único módulo objetivo: `src/skillgraph/governance/improvement.py`.

Ramas uncovered antes del WI-08:
- L110, 112, 114, 116 — `ImprovementCandidate.__post_init__` validations (4).
- L154, 156, 158, 160 — `PromotionDecision.__post_init__` validations (4).
- L213 — `detect_redundant_extraction` early-return sin firmas (1).
- L267 — `localize_omission` skip sid ya incluido (1).
- L273 — `localize_omission` skip sin firma vigente (1).
- L331 — `compare_recipes` correction=False (1).
- L381 — `promote_candidate` approver required (1).
- L458 — `rollback_candidate` policy="blocked" (1).

## Tests añadidos

`tests/test_h15_improvement.py` extendido con 6 clases nuevas (+14 tests):

| Clase | Tests | Cubre |
|---|---|---|
| `TestImprovementCandidateValidation` | 4 | L110, 112, 114, 116 |
| `TestPromotionDecisionValidation` | 4 | L154, 156, 158, 160 |
| `TestPromoteCandidateApproverRequired` | 1 | L381 |
| `TestRollbackBlockedPolicy` | 1 | L458 |
| `TestDetectRedundantExtractionEmptySigs` | 1 | L213 |
| `TestLocalizeOmissionDefensiveBranches` | 2 | L267, L273 |
| `TestCompareRecipesCorrectionFalse` | 1 | L331 |

## Resultado

```
Name                                       Stmts   Miss Branch BrPart  Cover
------------------------------------------------------------------------------
src/skillgraph/governance/improvement.py     140      0     38      0   100%
TOTAL                                        140      0     38      0   100%
23 passed in 2.70s
```

**Antes**: 84% cobertura (94 stmts, 14 branches uncovered).
**Después**: **100% cobertura** (140 stmts, 0 branches uncovered).
**Delta**: +16 pp.

Suite completa: **984/984 PASS** (era 957 → +27 tests: 14 WI-08 + 14 WI-07 -1 test dummy reemplazado).

## Definition of Done

- [x] Spec WI-08 creada (`specs/wi-08-coverage-improvement.md`).
- [x] Tests RED escritos antes de verificar cobertura.
- [x] Cobertura `governance/improvement.py` ≥ 90% (logrado: 100%).
- [x] Suite completa verde (984/984 PASS).
- [x] ruff format + check limpios.
- [x] `STATE.yaml` + `CURRENT.md` actualizados.
- [x] Commit atómico con mensaje conventional.
- [x] NO release/tag (regla D-22, D-26).

## Próximos pasos

- **WI-09**: sincronizar `CURRENT.md` línea 56 (file_signature 85%→100%, file_scope 81%→100%, governance/receipts 73%→99%) + entradas WI-07/WI-08.
- **WI-10**: README badges `405/405`→`984/984`, texto evolution-v2 H10..H15.
- Bump `0.14.5.dev0` post-WI-09/10; release/tag pendiente de aprobación operador.
