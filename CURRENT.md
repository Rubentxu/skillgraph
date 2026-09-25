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

## Último estado comprobado

- HEAD: `327a913` (docs(state): addendum honesto H9 (Release candidate) - 4/5 conformance).
- Tests: **772/772 PASS** en 166s (`uv run pytest -q`; baseline 754 post-v0.14.0 → 772 con +18 nuevos: 11 evidence_lock + 4 argparse + 3 bench smoke).
- **17 releases** emitidas: v0.3.0 → v0.14.0 (incluye 4 PATCH/MINOR de refactor: v0.7.0/v0.7.1/v0.7.2/v0.7.3 + 1 refactor sin bump post-v0.14.0 + 1 v0.8.1 PATCH + 6 Etapa 7 S1..S6).
- **UATs: 16/16 PASS** (uat_audit mantenible, invariante al avance).
- Cobertura núcleo ≥85% en todos los módulos (post-refactor context_controller 88%).
- Working tree limpio. Sin ficheros pendientes.
- ruff format + ruff check: limpios.
- HEAD == origin/main (post push FF en este turno).
- `STATE.yaml.release` sincronizado con realidad: tag=v0.14.0, 17 releases, 30 capacidades_entregadas, tag_sha=241ccc9f.
- **H9 addendum honesto**: 4/5 entregables cumplidos por conformance (E1 Adapter real PENDIENTE, E2 Seguridad CUMPLIDA_PARCIAL, E3-E5 CUMPLIDAS). Ver `audits/h9-addendum-2026-09-25.md`.

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

- Esperar consigna explícita del operador sobre si:
  1. Cerrar la iniciativa con Etapa 7 documentada (defendible: 769 tests,
     16/16 UAT, blueprint + Etapa 7 cerrados al 100%).
  2. Especificar y arrancar S7+ (nuevo goal).
  3. Otro trabajo distinto (audit transversal, stewardship cli.py,
     integración con proveedor real, etc.).

Mientras tanto, el repo está en estado estable con checkpoint sincronizado
en este turno.

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

## Pendientes post-T8

- **P1 opciones A/B/C** (Adapter real / grieta transaccional /
  certificación de concurrencia) — siguen requiriendo spec operador
  explícito. D (T8) ya cerrada.
- **No bump**: T8 no introduce breaking change ni capacidad nueva
  observable para el usuario. Es observabilidad interna. No genera
  release.
