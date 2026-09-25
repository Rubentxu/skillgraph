# Cobertura fresh snapshot — 2026-09-25 10:14

## Objetivo

Re-medir la cobertura real del proyecto con la suite completa de 772
tests (incluyendo los +18 nuevos de la sesión 2026-09-25) y
compararla con el snapshot declarado en STATE.yaml (que data del
2026-09-24). Detectar drift y sincronizar.

## Metodología

```bash
mise exec -- uv run pytest \
  --cov=src/skillgraph \
  --cov-report=term-missing \
  --cov-branch \
  -q
```

Suite completa: **772 tests** (754 baseline post-v0.14.0 + 11
evidence_lock + 4 argparse errors + 3 bench smoke).
Tiempo: 170s.
Warnings: 241 (no fallos).

## Cobertura real medida (2026-09-25 10:14)

| Módulo | Stmts | Miss | Branch | BrPart | Cover |
| --- | ---:| ---:| ---:| ---:| ---:|
| src/skillgraph/__main__.py | 3 | 3 | 2 | 0 | **0%** |
| src/skillgraph/cli/__init__.py | 2 | 0 | 0 | 0 | 100% |
| src/skillgraph/cli/runner.py | 1077 | 501 | 294 | 39 | **49%** |
| src/skillgraph/core/errors.py | 62 | 0 | 0 | 0 | 100% |
| src/skillgraph/core/recipe.py | 68 | 0 | 30 | 0 | 100% |
| src/skillgraph/core/runtime_types.py | 39 | 1 | 0 | 0 | 97% |
| src/skillgraph/domain/dsl.py | 49 | 1 | 14 | 1 | 97% |
| src/skillgraph/domain/pack_loader.py | 68 | 1 | 46 | 2 | 97% |
| src/skillgraph/domain/skill_importer.py | 126 | 1 | 32 | 2 | 98% |
| src/skillgraph/governance/graph_expansion.py | 285 | 4 | 100 | 5 | 98% |
| src/skillgraph/governance/promotion.py | 40 | 0 | 12 | 0 | 100% |
| src/skillgraph/knowledge/context_controller.py | 132 | 11 | 38 | 4 | **90%** |
| src/skillgraph/knowledge/git_source.py | 135 | 5 | 42 | 4 | 95% |
| src/skillgraph/knowledge/graph.py | 92 | 2 | 12 | 2 | 96% |
| src/skillgraph/knowledge/knowledge_controller.py | 115 | 3 | 22 | 3 | 96% |
| src/skillgraph/knowledge/knowledge_invalidator.py | 86 | 2 | 28 | 1 | 97% |
| src/skillgraph/platform/paths.py | 35 | 5 | 12 | 2 | 81% |
| src/skillgraph/platform/storage.py | 395 | 13 | 58 | 4 | 96% |
| src/skillgraph/resources/bricks.py | 22 | 0 | 0 | 0 | 100% |
| src/skillgraph/resources/catalog.py | 46 | 0 | 6 | 0 | 100% |
| src/skillgraph/resources/parser.py | 52 | 0 | 18 | 0 | 100% |
| src/skillgraph/resources/plan_loader.py | 49 | 0 | 16 | 0 | 100% |
| src/skillgraph/resources/registry.py | 72 | 1 | 32 | 4 | 95% |
| src/skillgraph/resources/workflow.py | 105 | 0 | 60 | 0 | 100% |
| src/skillgraph/runtime/agent.py | 60 | 1 | 14 | 1 | 97% |
| src/skillgraph/runtime/engine.py | 106 | 0 | 12 | 0 | 100% |
| src/skillgraph/runtime/handoff.py | 100 | 3 | 32 | 3 | 95% |
| src/skillgraph/runtime/locks.py | 77 | 7 | 12 | 3 | 89% |
| src/skillgraph/runtime/redaction.py | 27 | 0 | 14 | 0 | **100%** |
| src/skillgraph/runtime/runcontroller.py | 286 | 8 | 70 | 5 | **96%** |
| **TOTAL** | **3811** | **573** | **1028** | **85** | **83%** |

## Drift respecto a STATE.yaml

Comparación cifra-a-cifra entre STATE.yaml.coverage_snapshot_2026-09-24_post_v140
y la medición real de hoy:

| Módulo | STATE (24-09) | Real (25-09) | Delta | Veredicto |
| --- | ---:| ---:| ---:| --- |
| runtime/locks.py | 89% | 89% | 0 | OK |
| runtime/redaction.py | 39% | **100%** | **+61** | **drift MAYOR** (cifra heredada falsa) |
| runtime/runcontroller.py | 89% | **96%** | **+7** | drift heredado (subset T1) |
| knowledge/context_controller.py | 88% | **90%** | **+2** | drift menor (tests sesión) |
| platform/storage.py | 97% | 96% | -1 | drift menor (rama defensiva) |
| platform/paths.py | 81% | 81% | 0 | OK |
| core/runtime_types.py | 97% | 97% | 0 | OK |
| domain/dsl.py | 97% | 97% | 0 | OK |
| domain/pack_loader.py | 97% | 97% | 0 | OK |
| domain/skill_importer.py | 98% | 98% | 0 | OK |
| governance/graph_expansion.py | 98% | 98% | 0 | OK |
| governance/promotion.py | 100% | 100% | 0 | OK |
| knowledge/git_source.py | 95% | 95% | 0 | OK |
| knowledge/graph.py | 96% | 96% | 0 | OK |
| knowledge/knowledge_controller.py | 96% | 96% | 0 | OK |
| knowledge/knowledge_invalidator.py | 97% | 97% | 0 | OK |
| resources/registry.py | 95% | 95% | 0 | OK |
| resources/workflow.py | 100% | 100% | 0 | OK |
| resources/bricks.py | 100% | 100% | 0 | OK |
| core/errors.py | 100% | 100% | 0 | OK |
| runtime/engine.py | 100% | 100% | 0 | OK |
| runtime/agent.py | 97% | 97% | 0 | OK |
| core/recipe.py | 100% | 100% | 0 | OK |

**Drifts mayores**:

1. **`runtime/redaction.py`: 39% → 100%** (+61 puntos). La cifra 39%
   era heredada del subset T1 (4 ficheros) que no incluía los 21
   tests de `tests/test_redaction.py`. El audit
   `audits/redaction-2026-09-25.md` ya documentó la verdad pero
   STATE.yaml seguía con la cifra falsa.

2. **`runtime/runcontroller.py`: 89% → 96%** (+7 puntos). El
   audit `audits/runtime-2026-09-25.md` se midió con subset T1
   (4 ficheros, 367 tests) en lugar de la suite completa
   (actualmente 772). Cobertura real más alta porque más tests
   tocan paths de RunController.

**Drift menor**:

3. **`knowledge/context_controller.py`: 88% → 90%** (+2 puntos).
   El refactor `6c8c17f` añadió 15 tests; el delta real posterior
   (+2) probablemente viene del branch coverage adicional que esos
   tests ejercitan.

4. **`platform/storage.py`: 97% → 96%** (-1 punto). Probable
   rama defensiva no cubierta por test adicional nuevo.

## Módulos nuevos en STATE.yaml (faltan en el snapshot)

Hay **5 módulos de producción** con cobertura alta que NO están
listados en STATE.yaml.coverage_snapshot_2026-09-24_post_v140:

- `src/skillgraph/governance/promotion.py`: **100%**
- `src/skillgraph/runtime/handoff.py`: **95%**
- `src/skillgraph/resources/catalog.py`: **100%**
- `src/skillgraph/resources/parser.py`: **100%**
- `src/skillgraph/resources/plan_loader.py`: **100%**
- `src/skillgraph/cli/__init__.py`: **100%** (trivial re-export)
- `src/skillgraph/__main__.py`: **0%** (3 líneas; gap estructural)

Total: **30 módulos de producción** (vs 23 listados en STATE.yaml).

## Casos especiales

### `__main__.py` (0%)

3 líneas: `from skillgraph.cli import main` + `if __name__ ==
"__main__": raise SystemExit(main())`. Gap estructural: las
subprocess tests ejercitan `main()` pero pytest-cov no rastrea
subprocess child processes (mismo gap documentado en
`audits/runner-coverage-2026-09-25.md`). Tests InProcess que
importen `__main__` no aportan valor (rompen contrato). El 0%
es **aceptable por diseño** y NO es un gap testeable.

### `cli/runner.py` (49%)

Gap **estructural** (no testeable sin refactor mayor). El audit
`audits/runner-coverage-2026-09-25.md` ya documenta:

- 24 comandos cubiertos por subprocess (acceptance real).
- 6 InProcess tests añadidos en commit 32197db.
- 4 argparse errors tests añadidos en commit 32197db.
- pytest-cov NO rastrea subprocess child processes.

Subir la cifra sin duplicar subprocess tests violaría CALIDAD §4.
**Aceptado por conformidad** con el criterio de cierre real: 49%
es la cifra medible honesta, no un gap real.

## Resumen ejecutivo

- **Cobertura total real**: **83%** (3811 stmts, 573 miss, 1028
  branches).
- **Total de módulos productivos**: **30** (vs 23 listados en
  STATE.yaml).
- **Drift detectado**: 4 módulos con cifras desactualizadas
  (redaction 39%→100%, runcontroller 89%→96%, context_controller
  88%→90%, storage 97%→96%).
- **Decisión recomendada**: sincronizar STATE.yaml con el
  snapshot fresco de 2026-09-25 10:14.

## Acción de cierre

1. `STATE.yaml.coverage_snapshot_2026-09-25_post_session`:
   nuevo bloque con los 30 módulos y cifra real (83% total).
2. `STATE.yaml.coverage_snapshot_2026-09-24_post_v140`: marcar
   como `superseded_by_2026_09_25` para trazabilidad histórica.
3. `STATE.yaml.coverage.total`: 85% → 83% (refleja realidad).
4. `CURRENT.md` último estado: añadir línea de cobertura real.
5. `SESSION-JOURNAL.md`: nueva entrada del ciclo.

Sin LoC producción. Sin tests nuevos (regla 1: testing
quirúrgico; nada cambió en código). Riesgo: nulo.
