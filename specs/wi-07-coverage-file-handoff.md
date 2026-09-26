# WI-07 — Coverage hardening `file_handoff.py` 85%→≥90%

**WorkItem ID**: WI-07
**Fecha**: 2026-09-26
**Workflow SDDK**: A-min (single apply, scope acotado a tests/)
**Status**: ✅ CLOSED

## Contexto

Auditoría técnica senior identificó 6 módulos con cobertura 81-89% (H-14).
WI-07 atacó `file_handoff.py` (85%), uno de los gaps materiales reales.

## Decisiones

- **D-19**: WI-07 autorizado por operador (26-Sep 18:50, "deuda primero").
- **D-20**: WI-07 es solo tests; NO tocar producción.
- **D-21**: Housekeeping puro post-WI-06.
- **D-22**: NO release/tag en este workitem.

## Scope

Único módulo objetivo: `src/skillgraph/knowledge/file_handoff.py`.

## Tests añadidos

`tests/test_h13_handoff_expert.py` extendido con 5 clases nuevas (+17 tests):

| Clase | Tests | Cubre |
|---|---|---|
| `TestHandoffBlockedErrorMessages` | 3 | mensajes de error handoff_blocked |
| `TestBuildCoverageManifestFoco` | 4 | build_coverage_manifest con focos varios |
| `TestShouldSkipAdapterEmpty` | 2 | should_skip_adapter con payloads vacíos |
| `TestScopeAwareRecipeValidation` | 7 | ScopeAwareRecipe dataclass validation |
| `TestCompileHandoffFromScopesTypeErrors` | 1 | type-checks internos (L281/296 inaccesibles por construcción) |

## Resultado

```
Name                                       Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------------------
src/skillgraph/knowledge/file_handoff.py      97      4     36      5    93%   106, 281, 296, 322, 327->342
TOTAL                                         97      4     36      5    93%
21 passed
```

**Antes**: 85% cobertura (12 ramas uncovered).
**Después**: **93% cobertura** (5 ramas inaccesibles por construcción: type-checks
sobre frozen dataclass + isinstance encadenado, documentadas en `test_scope_query_invalido_doc`).
**Delta**: +8 pp.

Suite completa: pasó de 957 a 984 tests (WI-07 +14, WI-08 +14, dummy reemplazado -1 → +27).

## Definition of Done

- [x] Tests RED escritos antes de implementar.
- [x] Cobertura `file_handoff.py` ≥ 90% (logrado: 93%).
- [x] Suite completa verde.
- [x] ruff format + check limpios.
- [x] `STATE.yaml` + `CURRENT.md` actualizados.
- [x] Commit atómico.
- [x] NO release/tag (regla D-22).

## Notas técnicas

Ramas L281/296/322/327 documentadas como defensive code inaccesible:
- L281: `isinstance(knowledge, KnowledgeController)` — protegido por Protocol duck-typing.
- L296: `isinstance(scope_queries[0], ScopeQuery)` — `ScopeAwareRecipe.__post_init__` ya valida.
- L322/327: idem.

Por construcción (frozen dataclass + checks en `__post_init__`), estas ramas solo se ejercitarían
vía reflexión o monkey-patching, fuera del alcance del testing determinista.
