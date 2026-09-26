# Auditoria de deuda arquitectonica (2026-09-26)

Generada por `audits/audit_debt.py` (WI-28). Reproducible:
`python audits/audit_debt.py` desde la raiz del repo.

## Resumen ejecutivo

- **46** modulos Python, **16061** LoC, **561** funciones.
- **4** archivos >800 LoC (god modules).
- **1** funciones publicas con cc>=20 (refactor obligatorio).
- **1** funciones privadas con cc>=20 (refactor opcional).
- **11** funciones >80 LoC (legibilidad mejorable).
- **2** funciones con anidamiento >=5 niveles.

## Archivos grandes (>800 LoC)

H-01 Storage god-class y H-02 CLI god-module son las entradas mas impactantes.

| LoC | Path |
|----:|------|
| 2539 | `src/skillgraph/cli/runner.py` |
| 2407 | `src/skillgraph/platform/storage.py` |
| 1357 | `src/skillgraph/runtime/runcontroller.py` |
| 813 | `src/skillgraph/governance/graph_expansion.py` |

## Hotspots publicos (cc>=20, refactor obligatorio)

| cc | LoC | Funcion | Path |
|---:|----:|---------|------|
| 43 | 58 | `main` | `src/skillgraph/cli/runner.py` |

## Hotspots privados (cc>=20, refactor opcional)

Funciones con `_` prefijo. Suelen ser entry points de test, helpers de command handlers,
o coordinadores de bloque. No son candidatos directos a helper extraction a menos
que tenga valor pedagogico o de testabilidad.

| cc | LoC | Funcion | Path |
|---:|----:|---------|------|
| 22 | 77 | `_make_schema_validator` | `src/skillgraph/domain/pack_loader.py` |

## Funciones largas (>80 LoC)

Top 20 funciones por LoC. Muchas son orquestadores coordinando handlers; en si no
son problematicas si tienen baja cc y helpers atomicos con test coverage.

| LoC | Funcion | Path |
|----:|---------|------|
| 409 | `_build_parser` | `src/skillgraph/cli/runner.py` |
| 136 | `_execute_one` | `src/skillgraph/runtime/runcontroller.py` |
| 116 | `extract_file_signatures` | `src/skillgraph/knowledge/file_signature.py` |
| 101 | `analyze_skill` | `src/skillgraph/domain/skill_importer.py` |
| 95 | `_reconcile_run_locked` | `src/skillgraph/runtime/runcontroller.py` |
| 92 | `cmd_expansion_apply` | `src/skillgraph/cli/runner.py` |
| 91 | `_resolve_run_inputs` | `src/skillgraph/cli/runner.py` |
| 90 | `compile_handoff` | `src/skillgraph/knowledge/context_controller.py` |
| 86 | `aggregate_file_signatures` | `src/skillgraph/knowledge/knowledge_controller.py` |
| 85 | `compile_handoff_from_scopes` | `src/skillgraph/knowledge/file_handoff.py` |
| 84 | `promote_candidate` | `src/skillgraph/governance/improvement.py` |

## Anidamiento profundo (>=5 niveles)

Anidamiento >=5 suele indicar decision tree en lugar de composicion declarativa.

| Nesting | Funcion | Path |
|--------:|---------|------|
| 5 | `_validate` | `src/skillgraph/domain/pack_loader.py` |
| 5 | `_make_schema_validator` | `src/skillgraph/domain/pack_loader.py` |

## Recomendaciones (post-WI-22 cierre previo)

### Cerradas en este ciclo WI-23..WI-27 (housekeeping) — 5 WIs
- `_validate` (pack_loader): cc 22→7 — 3 helpers extraidos.
- `validate` (graph_expansion): cc 24→4 — 3 helpers extraidos.
- `parse_markdown` (resources.parser): cc 17→2 — 4 helpers extraidos.
- `take` (runtime.locks.RunLock): cc 16→5 — 4 helpers extraidos.
- `record_validation_receipt`: cc 14→5 — 4 helpers con `empty_msg` kwarg.
- `traverse_invalidations`: cc 13→5 — 3 helpers (seed/expand/warn).
- `HttpAgentAdapter.invoke`: cc 12→7 — sentinel `RetryableHttpStatus` + 1 helper.
- `compile_handoff_from_scopes`: cc 12→1 — triada validate/enforce/build_synth.

### Pendientes por prioridad

**P0 - Hotspots publicos cc>=20** (refactor obligatorio):
- `main` (runner.py): cc=43, 58 LoC — CLI entry point: NO refactor surgical.
- `cmd_run` (runner.py): cc=22, 122 LoC — candidate a `_dispatch_run_subcommand(...)`.
- `_make_schema_validator` (pack_loader.py): cc=22, 77 LoC — factory de closures; refactor interno factible.

**P1 - God modules** (>800 LoC, deuda estructural mayor):
- H-01 storage.py (2407 LoC): reposicionar por dominio (knowledge/governance/receipts).
- H-02 cli/runner.py (2477 LoC): extraer sub-comandos a modulos individuales.
- runcontroller.py (1357 LoC): separar reconciliacion de ejecucion.

**P2 - Hotspots privados cc>=20** (refactor opcional, valor pedagogico):
- Sin acciones automaticas; decidir caso por caso.

**P3 - Funciones largas >80 LoC**: ver tabla arriba. En su mayoria son orquestadores.

### Politica recomendada

- WIs P0 siguen el patron helper-extraction ya establecido (D-52..D-60).
- WIs P1 (god modules) requieren un ADR previo porque tocan contratos publicos y boundary.
- Cualquier release debe mantener cero hotspots publicos cc>=20 o documentar la excepcion.
