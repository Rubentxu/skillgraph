# CURRENT — puntero operativo

> Última verificación: 2026-09-25 10:08 (Europe/Madrid).
> Iniciativa `g-skillgraph-bootstrap` **COMPLETED** en v0.6.0 (2026-09-23).
> Etapa 7 (runtime/reconciliación) **CERRADA** en v0.14.0 (2026-09-24).
> Stewardship backlog P1 Opción A (H9 addendum honesto) **CERRADO** en `327a913` (2026-09-25).

## Goal

**COMPLETED** (2026-09-23, tag v0.6.0).

`g-skillgraph-bootstrap`: "Arrancar SkillGraph siguiendo el blueprint:
Etapa 0 (S0 + S1) → Etapa 1 → Etapa 2".

Re-abierto en sesión 2026-09-23 → v0.6.0-CLOSED (H6 + H7 ejecutados).
Refactor arquitectónico follow-up cerrado en v0.7.0 (2026-09-24).
Etapa 7 cerrada en v0.14.0 (2026-09-24, 6 slices MINOR + 1 refactor sin bump).

Detalle completo de rationale y criterios en `.next-decision.md` y
`STATE.yaml` (`goal.*`, `etapa7_*`, `refactor_v070_*`).

## Hito y trabajo activo

**Sin trabajo activo material.** Iniciativa y Etapa 7 cerradas.

- H0..H7: **cerrados**.
- H8 (Integración pública CLI): **cerrado** en v0.6.0 (ADR-0013).
- Etapa 7 slices 1-6: **cerrados** (v0.8.0 → v0.14.0).
- Refactor context_controller (sin bump): **cerrado** en `6c8c17f`.

# INITIATIVE-CLOSED

**Initiative g-skillgraph-bootstrap cerrada formalmente** (segundo
acto, sesion 2026-09-25T15:37:08Z por consigna del operador "1").
HEAD terminal: `f1b92ff`. Certificado completo en
`INITIATIVE-CLOSED.md`.

## Reactivacion autonoma 2026-09-25T16:07:01Z

Operador reabre con modo AUTO: "avanza con criterio propio buscando
entrega de valor sin dejar la calidad". Workflow STEWARDSHIP-T3-001
aplicado: T3 Threat model (ADR-0015 + tests de attestation + audit).

**HEAD terminal T3**: pendiente commit. 14/14 tests PASS.

## Ultimo estado comprobado

- HEAD: `ffa03e9` (test(evidence): refresh UAT-08/09). HEAD anterior a T3.
- Tests: **830/830 PASS** en 189s (`mise exec -- uv run pytest -q`; baseline 821 → 830 con +9 nuevos: test_h15_improvement UAT-EVO-15..18).
- **17 releases** emitidas: v0.3.0 → v0.14.0 (incluye 4 PATCH/MINOR de refactor: v0.7.0/v0.7.1/v0.7.2/v0.7.3 + 1 refactor sin bump post-v0.14.0 + 1 v0.8.1 PATCH + 6 Etapa 7 S1..S6). Nota: H15 no requiere bump (no entrega capacidad nueva a nivel de release, añade superficie de governance).
- **UATs: 16/16 PASS** (uat_audit mantenible, invariante al avance).
- Cobertura núcleo re-medida: **83%** total. Modulos H11/H12/H13/H14/H15: file_signature.py 85%, file_scope.py 81%, file_handoff.py 80%, governance/receipts.py 73%, governance/improvement.py 84%.
- Working tree limpio. Sin ficheros pendientes.
- ruff format + ruff check: limpios.
- HEAD == origin/main (post push FF en este turno).
- `STATE.yaml.release` sincronizado con realidad: tag=v0.14.0, 17 releases, 30 capacidades_entregadas, tag_sha=241ccc9f.
- **H9 addendum honesto**: 4/5 entregables cumplidos por conformance (E1 Adapter real PENDIENTE, E2 Seguridad CUMPLIDA_PARCIAL, E3-E5 CUMPLIDAS). Ver `audits/h9-addendum-2026-09-25.md`.
- **H10 evolution-v2 COMPLETO**: mapa del recorrido real y baseline (audits/h10-recorrido-real-2026-09-25.md 325 LoC).
- **H11 evolution-v2 COMPLETO**: conocimiento tipado reutilizable (FileSignatures). Ver `src/skillgraph/knowledge/file_signature.py` (ADT cerrada, pure extractor) + `tests/test_h11_file_signature.py` (12 UAT-EVO-01..04 tests). Persistencia via Evidence(kind='file_signature') reusando tabla existente (regla AGENTS §1.5).
- **H12 evolution-v2 COMPLETO**: scopes y consultas composables (FileScope, ScopeQuery, ScopeResolution, aggregate_signatures). Ver `src/skillgraph/knowledge/file_scope.py` + `tests/test_h12_file_signature_scopes.py` (8 UAT-EVO-05..08 tests). Aislamiento E2E-08 estricto: source-en-otro-proyecto lanza `UnknownSourceError` SIN filtrar el source_id (mensaje generico).
- **H13 evolution-v2 COMPLETO**: handoff experto desde consultas (ScopeAwareRecipe, CoverageManifest, HandoffBlockedError, compile_handoff_from_scopes). Ver `src/skillgraph/knowledge/file_handoff.py` + `tests/test_h13_handoff_expert.py` (8 UAT-EVO-09..11 tests). Composicion pura sobre ContextRecipe (NO modifica Literal cerrada de ObligatorySelector). should_skip_adapter() decide skip LLM si manifest completo+fresco.
- **H14 evolution-v2 COMPLETO**: evidencia operativa temporal (ValidationReceipt, is_receipt_applicable, record_validation_receipt, list_applicable_receipts). Ver `src/skillgraph/governance/receipts.py` + `tests/test_h14_validation_receipts.py` (9 UAT-EVO-12..14 tests). Persistencia via Evidence(kind='validation_receipt') reusando tabla existente (regla AGENTS §1.5). is_receipt_applicable() pura: revision + dependency_revisions determinan aplicabilidad (UAT-EVO-14: recibo de A NO es validacion automatica de B).
- **H15 evolution-v2 COMPLETO**: evaluación y automejora acotada (ImprovementCandidate, detect_redundant_extraction, localize_omission, compare_recipes, promote_candidate, rollback_candidate). Ver `src/skillgraph/governance/improvement.py` + `tests/test_h15_improvement.py` (9 UAT-EVO-15..18 tests). Persistencia via Evidence(kind='promotion_decision'|'rollback') reusando tabla existente (regla AGENTS §1.5). UAT-EVO-18: promote_candidate() EXIGE human_approved=True, sin autocertificacion (SelfCertificationBlockedError tipado).
- **EVOLUTION-V2 COMPLETO** (H0..H15): roadmap evolution-v2 cerrado al 100%. 5 nuevos modulos (file_signature, file_scope, file_handoff, governance/receipts, governance/improvement), +58 tests nuevos UAT-EVO.

## Releases post-refactor v0.7.0

| Tag | Commit | Capacidad |
|---|---|---|
| v0.8.0 | `a4d749e` | `cancel_run` + `sg runs cancel` |
| v0.8.1 | `08caacd` | PATCH refactor `_fail_node_with` |
| v0.9.0 | `b4ff317` | `cancel_run` + refactors (`_transition_run_state_with_event`, `_is_budget_exhausted`) |
| v0.10.0 | `72152fe` | `list_runs` + `show_run` + `sg runs list/show` |
| v0.11.0 | `6ad5789` | `logs_run` + `sg runs logs` |
| v0.12.0 | `9d9ae09` | `RunBudget` + `sg runs budget` |
| v0.13.0 | `72651ee` | `RedactionPolicy` + `sg policy get/set` |
| v0.14.0 | `241ccc9` | `RunLock` + `sg run --lock-mode` (locks concurrentes por run) |

Refactor sin bump: `6c8c17f` (extract pure helpers from ContextController).

## Pendientes (sin spec operador explícita)

1. **S7+ del blueprint v1**: no definido en `external/blueprint-v1/`.
   Etapa 7 cierra con "futuros horizontes abiertos".
2. **Grieta de no-atomicidad workflow_runs ↔ runtime_events**: conocida,
   preservada por construcción (decisión arquitectónica con ADR pendiente).
   Los locks de S6 v0.14.0 mitigan interleaving a nivel de proceso,
   no cierran la grieta transaccional (que requeriría SQLite WAL
   transactions coordinando INSERT/UPDATE + event append).
3. **Concurrencia real entre procesos**: probada con `multiprocessing`
   en `test_locks.py` (2 procesos se serializan en el mismo run),
   pero no certificada con proveedores reales ni bajo carga.

## Próxima acción concreta

**Initiative cerrada formalmente** (2026-09-25T15:37:08Z, segundo
acto por consigna del operador "1"). Sin próxima acción autonoma.

Para reactivar la iniciativa o abrir una nueva:
- Operador aporta spec para uno de los 4 Trabajos pendientes de
  Etapa 7 (E1 Adapter real, T3 Threat model, T5 Backups CLI,
  T6 Observabilidad), formato libre ~1 parrafo.
- Operador reabre con consigna explicita; el protocolo de
  reapertura esta en `INITIATIVE-CLOSED.md` seccion 8.

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-FORMAT-DRIFT cerrado

Inspeccion de salud del repo al iniciar sesion detecta **drift de
ruff format en 15 archivos** introducido por los commits H11-H15
evolution-v2 (5c52750 + dc1ef18 + c5f8a94 + 116a2b5) + t3/t3-s2.
El CI gate `format/format --check` estaba **roto**.

Drift puramente cosmetico: collapse de f-strings multilinea,
reorganizacion de kwargs, reordenamiento de tuplas en fixtures.
0 cambios semanticos. Aplicar `ruff format` cierra el gap sin
regresiones.

Verificacion:
- `ruff format src tests` -> 15 files reformatted, 122 unchanged.
- `ruff check src tests` -> All checks passed.
- `ruff format --check src tests` -> 137 files already formatted.
- `pytest -q` -> 855/855 PASS en 251s.

Resultado: **-91 LoC netos** (97 insertions, 188 deletions). CI
gate `format/format --check` desbloqueado.

Commit `3031795 style(format)`. Audit doc en
`audits/format-drift-2026-09-26.md` (117 LoC, tabla 15 archivos
+ trazabilidad origen + derivado pre-commit hook).

Sin bump de release (style/format). HEAD `3031795`.

Recomendacion derivada (futuro ciclo, sin accion ahora): pre-commit
hook + CI workflow para evitar regresion. Coste ~30 min.

## Reactivacion 2026-09-26 — STEWARDSHIP-T-WARNINGS-AUDIT cerrado

Operador reabre con modo AUTO: "continua con tareas roadmap y deuda
tecnica a tu criterio". Sigo el follow-up explicito de
`T-SECURITY-AUDIT-FULL`: "Auditar mensajes `WARNING` y `INFO`".

Inventario: 3 sitios `warnings.warn(...)` en `src/skillgraph`:
- `knowledge/knowledge_invalidator.py:128` (HopLimitExceededWarning):
  expone `max_hops` (param caller) + `len(frontier)` (cardinalidad).
  NO gap.
- `knowledge/knowledge_controller.py:115` (StaleKnowledgeWarning):
  expone `source.source_id` (caller-provided, mismo tenant, mismo
  caller que acaba de pasar el `source`). NO gap, mismo principio
  que `storage.py:446` (uid caller-provided).
- `core/errors.py:125` docstring (N/A).

Verificacion transversal: **0 imports de logging/structlog** en
`src/skillgraph`. El codebase no usa logging estandar, solo CLI
prints (caller-provided) + warnings.warn (cubierto aqui).

Endurecimiento de tests: 3 tests existentes que solo verificaban
TIPO de warning ahora verifican CONTENIDO con `pytest.warns(match=...)`.
Esto convierte la cobertura "verifica tipo" en "verifica tipo +
contenido" y protege contra regresiones futuras.

Commit `5cda0c0 test(security): harden warning content matchers per
ADR-0015`. Audit doc en `audits/warnings-audit-2026-09-26.md`
(234 LoC, tabla 3 sitios + tracing + limitacion autocritica).

HEAD `5cda0c0`, 855/855 tests PASS, 0 regresiones vs baseline.
Sin bump de release (tests-only + docs).

## Reactivacion 2026-09-25T22:20Z — STEWARDSHIP-T-SECURITY-AUDIT-FULL cerrado

Operador reabre con modo AUTO. Auditoria exhaustiva S2/I (ADR-0015)
de los 38 sitios f-string sin `!r` restantes tras mini-audit
previo (244ddf3, 5 sitios). Inventario total: 43 sitios.

Resultado: **0 gaps S2/I** en los 38 sitios restantes.

Trazabilidad uno-por-uno:
- `platform/storage.py:446` (IdentityConflictError uid): caller-provided
- `platform/storage.py:1265/1405` (NotFoundError run_id): caller-provided
- `governance/graph_expansion.py:103` (RuntimeError reason): API misuse
- `knowledge/context_controller.py:92` (StaleKnowledgeError count): cuenta, no ID

+ 26 sitios triviales (path filesystem, source nombre, field validation
  programador): grep transversal confirma callers CLI local o programador.

HEAD `21a096d` == origin/main, working dir limpio. ADR-0015
implementado al 100% para f-strings con identificadores.

Mientras tanto, el repo esta en estado estable con checkpoint
sincronizado en `f1b92ff` (HEAD terminal) y certificado de cierre
en `INITIATIVE-CLOSED.md`.

## Auditoría 2026-09-25

Producido `audits/runtime-2026-09-25.md` (367 LoC, 0 modificado en
producción). Resultado: RunController post-Etapa 7 está en buen
estado. 0 hallazgos materiales, 5 menores (opcionales), 1 deuda
defendible (transaccional cross-proceso). Sin bump recomendado.
163 tests PASS verificados en este turno (23s).

## Stewardship backlog P2 (DT-2 lock) — cerrado 2026-09-25 08:44

3 commits (9889ee8, 8bebaf3, 984d739 + docs en f31fa53) cierran
DT-2 (lock preventivo `tests/uat-evidence/`):

- **9889ee8** `style(format)`: cerrar drift de ruff format (CI gate
  desbloqueado) + SIM117 nested-with en `test_locks.py`. 10 archivos,
  100% cosmetico, 765/765 PASS post-fix.
- **8bebaf3** `feat(tests)`: helper `tests/_evidence_lock.py` (162 LoC)
  + 11 tests en `tests/test_evidence_lock.py` que cubren escritura
  simple, dir auto-creacion, 8 escritores concurrentes al mismo
  uat_id (exactamente 1 payload), 6 a uat_ids distintos (locking
  granular), `history_keep` True/False, fallback Windows, payload
  no serializable, 4-thread barrier sync.
- **984d739** `refactor(tests)`: callers (`_save_evidence` en
  `uat_audit.py`, `_emit_uat_08/09_evidence` en
  `test_h4_expansion_cli.py`) usan el helper. DRY: -18 LoC. Fixtures
  UAT-08/09.json reescritas con HEAD `b53de0d3`.

Suite final: **765/765 PASS** en 166s, ruff limpio, 3 commits
pushados FF a origin/main.

Pendientes stewardship backlog:
- P1: spec S7+ del operador (4 opciones: A Adapter real, B grieta
  transaccional, C cert. concurrencia, D multi-tenancy).
- P3: auditoria `src/skillgraph/runtime/redaction.py` (cifra heredada
  39% vs gaps reales).
- P4: cobertura `cli/runner.py` 55% → 70%+.
- P5: ejecucion S7+ (depende P1).

## Stewardship backlog P3 + P4 (audit redaction + runner) — cerrado 2026-09-25 09:04

3 commits cierran P3 y P4 del stewardship backlog:

- **32197db** `feat(tests)`: 4 tests argparse errors InProcess en
  `tests/test_cli_branches.py` (TestCliArgparseErrors). Cierran el
  contrato observable del parser ante invocaciones inválidas:
  `--bogus-flag`, subcommand inválido, positional extra, `--help`.
- **5de1717** `docs(audit)`: 2 auditorías nuevas
  (`audits/redaction-2026-09-25.md` 170 LoC +
  `audits/runner-coverage-2026-09-25.md` 270 LoC).
- **cda56fa** `docs(state)`: P3 y P4 marcados completed.

### P3 verdict (redaction.py)

- Cifra 39% en STATE.yaml era **heredada** del snapshot T1
  (subset focal de 4 ficheros).
- Re-medido con suite completa: **100% real** (27/27 stmts, 14/14
  branches, 0 miss).
- Módulo puro (sin I/O, sin globales, sin reloj).
- 21 tests en 8 clases cubren cada contrato observable.
- 0 LoC producción modificados, 0 tests nuevos, **sin gaps**.

### P4 verdict (cli/runner.py)

- Cifra 55% en STATE.yaml era **heredada** del subset T1.
- Re-medido con suite completa: **49% real** (1077 stmts, 501 miss).
- Gap **estructural**, no de tests: pytest-cov NO rastrea código
  ejecutado en proceso hijo. 24 comandos cubiertos por subprocess
  (acceptance real) + 6 InProcess.
- Subir cifra sin duplicar subprocess tests violaría CALIDAD §4
  (no duplicar acceptance).
- 4 tests argparse errors aplicados cierran **contrato** de argparse
  (NO suben cifra: argparse eleva SystemExit antes del main()).
- Sin acción adicional posible sin refactor mayor (subprocess-coverage
  plugin, 2-3h, frágil).

## Stewardship backlog P1 Opción D (T8 benchmark) — cerrado 2026-09-25 09:37

3 commits cierran la Opción D de P1 (suite mínima de benchmarks,
ejecutable sin spec del operador):

- **3b4dc7d** `feat(bench)`: `bench/__init__.py` (16 LoC) +
  `bench/bench_context.py` (322 LoC) + `bench/README.md` (104 LoC).
  Mide `compile_handoff` y `refresh_handoff` sobre corpus sintetico
  (Storage SQLite en tempdir). 3 fases por tamaño: `compile_cold`,
  `compile_warm` (mediana de 3), `refresh_warm` (mediana de 3).
  Salida humana (tabla Markdown) o JSON con schema
  `skillgraph.bench.v1`.
- **ee00a9f** `test(bench)`: 3 smoke tests subprocess en
  `tests/test_bench_smoke.py` (78 LoC). Subprocess (NO pytest-cov
  in-process) por el gap estructural documentado en
  `audits/runner-coverage-2026-09-25.md`.
- **cd51732** `docs(bench)`: `audits/t8-benchmark-2026-09-25.md`
  (132 LoC, auditoría de entrega) + `audits/bench/baseline-2026-09-25.json`
  (snapshot primera corrida) + refresh UAT-08/09 con HEAD actual.

### Baseline 2026-09-25

| claims | src | compile_cold(ms) | compile_warm(ms) | refresh_warm(ms) |
| ---    | --- | ---              | ---              | ---              |
| 10     | 2   | 0.526            | 0.310            | 0.318            |
| 100    | 15  | 2.667            | 2.368            | 2.489            |
| 1000   | 143 | 34.245           | 31.985           | 33.323           |

Conclusiones:

- **Linealidad**: ~30 µs/claim en `compile_warm`.
- **Sin cache en refresh**: `refresh_warm ≈ compile_warm`. Hoy
  `refresh_handoff` SIEMPRE recompila aunque no haya cambios
  (oportunidad de optimización documentada).
- **Cold ≈ warm**: gap < 2x en todos los tamaños (sin warm-up patológico).

### Verificación final

- `mise exec -- uv run pytest` — **772/772 PASS** (769 → 772; +3 nuevos).
- `mise exec -- uv run ruff check .` — All checks passed.
- HEAD: `cd51732` (3b4dc7d + ee00a9f + cd51732 pendientes de push).

### Verificación T3 Threat model (2026-09-25 ~16:25)

- HEAD post-ciclo: `fdb2398` (`a25e8f9` + state sync), push OK.
- 14/14 tests PASS en `tests/test_t3_threat_model_attestation.py` (0.97s).
- 167/167 tests PASS en T2 (t3 + redaction + locks + storage + runcontroller + graph_expansion).
- ADR-0015 vive en filesystem local (`external/` gitignored por diseno).
- Audit dedicado: `audits/t3-threat-model-2026-09-25.md`.

### Verificación T3-S2 gap cierre (2026-09-25 ~17:00)

- HEAD post-ciclo: pendiente (commit en este mismo turno).
- 5/5 tests nuevos PASS en `tests/test_t3_s2_message_no_source_id.py` (0.83s).
- 789/789 tests PASS en suite completa (T2; 195s) — 0 regresiones.
- ruff check limpio.
- Audit dedicado: `audits/t3-s2-message-redaction-2026-09-25.md`.
- 3 sitios en `knowledge_controller.py` corregidos (l.135, l.216, l.488).
- Sin bump de release (regla SEMVER: fix sin breaking en contrato observable, acumulado a proxima release).

### Verificación T3-S2-002 entity_id (2026-09-25 ~17:20)

- HEAD post-ciclo: `026747e` == origin/main.
- 4/4 tests nuevos PASS en `tests/test_t3_s2_entity_message_no_entity_id.py` (0.67s).
- T4 completa: **853/853 PASS en 478s, exit 0**, 0 regresiones.
- Audit dedicado: `audits/t3-s2-entity-message-redaction-2026-09-25.md`.
- 2 sitios en `knowledge_controller.py` corregidos (l.179, l.490).
- Housekeeping adicional: T3 test E2E-08 endurecido (ya exige no source_id ni tenant_id), UAT-08/09 refresh pointers.
- Sin bump de release (4 commits coherentes acumulados a proxima release).

## Pendientes (sin cambio)

- **P1 opciones A/B/C** (Adapter real / grieta transaccional /
  certificación de concurrencia) — siguen requiriendo spec operador
  explícito. D (T8) ya cerrada.
- **Gap S2/I** (mensaje filtra source_id): **CERRADO** en `STEWARDSHIP-T3-S2-001` (mensaje opaco al client, chain preservado).
- Quedan: E1 Adapter real (spec: proveedor, prompts, timeouts, credenciales),
  T5 Backups CLI (spec: formato + retención), T6 Observabilidad (spec: sinks + retención),
  Gap A (grieta workflow_runs↔runtime_events, bloqueado por H9-Plan-B).
- **No bump**: T8 no introduce breaking change ni capacidad nueva
  observable para el usuario. Es observabilidad interna. No genera
  release.
