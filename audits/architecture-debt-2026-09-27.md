# Auditoria de deuda arquitectonica (2026-09-27)

Generada por `audits/audit_debt.py` (WI-28). Reproducible:
`python audits/audit_debt.py` desde la raiz del repo.

## Resumen ejecutivo

- **48** modulos Python, **17609** LoC, **625** funciones.
- **5** archivos >800 LoC (god modules).
- **0** funciones publicas con cc>=20 (refactor obligatorio).
- **1** funciones privadas con cc>=20 (refactor opcional).
- **11** funciones >80 LoC (legibilidad mejorable).
- **2** funciones con anidamiento >=5 niveles.

## Archivos grandes (>800 LoC)

H-01 Storage god-class y H-02 CLI god-module son las entradas mas impactantes.

| LoC | Path |
|----:|------|
| 2814 | `src/skillgraph/platform/storage.py` |
| 2248 | `src/skillgraph/cli/runner.py` |
| 1393 | `src/skillgraph/runtime/runcontroller.py` |
| 927 | `src/skillgraph/platform/ports/__init__.py` |
| 813 | `src/skillgraph/governance/graph_expansion.py` |

## Hotspots publicos (cc>=20, refactor obligatorio)

| cc | LoC | Funcion | Path |
|---:|----:|---------|------|

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
| 409 | `build_parser` | `src/skillgraph/cli/parser.py` |
| 136 | `_execute_one` | `src/skillgraph/runtime/runcontroller.py` |
| 116 | `extract_file_signatures` | `src/skillgraph/knowledge/file_signature.py` |
| 101 | `analyze_skill` | `src/skillgraph/domain/skill_importer.py` |
| 95 | `_reconcile_run_locked` | `src/skillgraph/runtime/runcontroller.py` |
| 92 | `cmd_expansion_apply` | `src/skillgraph/cli/runner.py` |
| 90 | `compile_handoff` | `src/skillgraph/knowledge/context_controller.py` |
| 89 | `_resolve_run_inputs` | `src/skillgraph/cli/runner.py` |
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


<!-- ANNALS:append-only -->

## WI-38 R1 strict — delta tras auditoria de boundary Storage (2026-09-27)

**Objetivo**: auditar TODOS los metodos publicos de `Storage` y eliminar retornos de `sqlite3.Row` / `dict[str, object]` raw sustituyendolos por DTOs `Stored*` inmutables.

**Drifts encontrados** (5):
1. `list_events` retornaba `list[sqlite3.Row]` → fixed con `_row_to_stored_event`.
2. `list_pending_promotions` retornaba `list[dict[str, Any]]` → fixed con `_row_to_stored_promotion` + DTO `StoredPromotion`.
3. `list_promotions` retornaba `list[dict[str, Any]]` → fixed idem.
4. `get_promotion` retornaba `dict[str, Any] | None` → fixed idem.
5. `get_budget` retornaba `dict[str, Any] | None` → fixed con `_row_to_stored_budget` + DTO `StoredBudget`.

**DTOs nuevos** (en `src/skillgraph/platform/ports/__init__.py`):
- `StoredPromotion`: 12 campos frozen+slots + `__getitem__` compat legacy.
- `StoredBudget`: 6 campos frozen+slots + `__getitem__` compat legacy.
- `StoredEvent`: añadida `__getitem__` para subscript legacy.

**Tests**:
- `tests/test_wi38_storage_boundary.py` (5 tests): exhaustivo, audita firmas publicas + retornos runtime.

**Deuda residual (cerrada por WI-39)**:
- `list_claims_by_predicate` y `list_evidences_for_source` retornaban `tuple[dict[str, object], ...]`.

## WI-39 R1 strict — cierre de frontera Claim/Evidence (2026-09-27)

**Objetivo**: cerrar el ultimo drift R1 que WI-38 dejo abierto, sustituyendo los
retornos `dict` crudos de la capa de conocimiento por DTOs inmutables.

**Cambios**:
- DTOs `StoredClaim` y `StoredEvidence` en `platform/ports/__init__.py` (`frozen=True, slots=True`).
- Mappers privados `_row_to_stored_claim` y `_row_to_stored_evidence` en `storage.py`.
- `ContextController` y `KnowledgeController` consumen los DTOs por atributo, no por subscript.
- El `*_json` queda encapsulado dentro del mapper: ningun consumidor deserializa a mano.

**Tests**: `tests/test_wi39_storage_boundary.py` (96 LoC nuevos) fija el contrato
de la frontera; `tests/test_wi38_storage_boundary.py` se reduce al alcance de WI-38.

**Estado R1 tras WI-39**: cerrado. Todo `sqlite3.Row` que queda en `storage.py`
esta dentro de un mapper privado `_row_to_*`, que es la frontera correcta.

**Delta LoC**:
- storage.py: +~356 LoC (DTOs + helpers + metodos refactorizados).
- ports/__init__.py: +~75 LoC (StoredPromotion + StoredBudget + `__getitem__`).
- runner.py: ~+0 LoC (sin cambios netos despues de la migration compat).

## WI-40 — cierre de fugas de conexion en la suite (2026-09-27)

**Objetivo**: la suite completa emitia 224 `ResourceWarning: unclosed database`.
No era ruido: `Storage` expone `close()` y context manager desde v0.15.0, y 159
creators en 60 ficheros de test nunca lo invocaban.

**Defecto real (1)**: el fixture `storage_cleanup` de `tests/conftest.py` resolvia
esta clase de fuga, pero era opt-in y solo lo adoptaban 6 ficheros. La disciplina
se pagaba fichero a fichero en vez de pagarse una vez en el conftest.

**Defecto real (2, encontrado al medir)**: `storage_cleanup` solo ve las
instancias de `Storage`. Tras volverlo `autouse`, la suite bajo de ~224 a 35
avisos, NO a cero. Esos 35 los-producia `sqlite3.connect` directo, invisible al
fixture, por dos vias: helpers que abren la base para inspeccionarla, y el idiom
`with sqlite3.connect(path) as conn`, que NO cierra (el context manager de
`sqlite3` solo confirma la transaccion). Un plugin de diagnostico que rastrea
`sqlite3.connect` atribuyo las 35 a 6 ficheros: `test_runtime_events`,
`test_redaction`, `test_skill_importer`, `test_h9_coverage_skill_importer`,
`test_uat_audit` y `test_cli_*`.

**Cambios**:
- `storage_cleanup` pasa a `autouse=True`: el cierre deja de ser opt-in.
- Eliminado los 7 marcadores `usefixtures("storage_cleanup")`, que quedan redundantes.
- `sqlite_cleanup` nuevo fixture `autouse=True` que envuelve `sqlite3.connect` y
  cierra en teardown lo que el test dejo abierto. Se instrumenta el punto de
  creacion en vez de parchear los ~10 sitios porque `with sqlite3.connect` es un
  error sistemico, no un descuido puntual: corregirlo a mano no cierra la clase.
  Es seguro porque la suite no tiene fixtures `module`/`session` que reutilicen
  una conexion entre tests (verificado: 0 ocurrencias).
- `tests/test_wi40_storage_leak.py` (8 tests) fija la invariante.
- `audits/audit_debt.py`: la cronologia manual se conserva bajo
  `<!-- ANNALS:append-only -->`; antes, cada ejecucion del auditor sobrescribia el
  informe completo y destruia el analisis de cierre de WI-38.

**Redundancia evitada**: `Storage.close()` ya es idempotente y suprime
`sqlite3.ProgrammingError`, asi que el cleanup NO necesita un `try/except`
adicional. Se descarto esa version por ser codigo muerto.

**Evidencia**:
- Ciclo TDD rojo→verde verificado en ambos fixtures: revertir `autouse=True`
  rompe `test_cleanup_runs_around_every_test`; restaurarlo, verde.
- Suite completa: 1131 passed, 0 `unclosed database` (antes: 224).
- Diagnostico de fugas: `sin conexiones vivas tras teardown` (antes: 35 en 6
  ficheros). Evidencia reproducible: plugin en `.pipelinek/wi40_leakdiag.py`.
- `ruff check` y `ruff format --check` limpios.

**Deuda residual**: ninguna en lifecycle de test. La fuga equivalente en
produccion esta cerrada por el context manager y por WI-37/WI-15.