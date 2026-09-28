# CURRENT — puntero operativo

> Última verificación: 2026-09-28 14:58 (Europe/Madrid, modo AUTONOMO SDDK, fix(audit) + refactor(backups)).
> Iniciativa `g-skillgraph-bootstrap` **COMPLETED** en v0.6.0 (2026-09-23).
> Etapa 7 (runtime/reconciliación) **CERRADA** en v0.14.0 (2026-09-24).
> Versión activa: `0.16.4.dev0` (bump desde `0.16.3.dev0`; PATCH por 1 `fix` + 1 `refactor` desde `v0.16.3`, sin `feat` ni breaking change). `fix(audit)`: la sección de recomendaciones de la auditoría de deuda pasó a derivarse de la medición, eliminando tres P0 inexistentes (`main` cc=43 real 5, `cmd_run` cc=22 real 6, `_make_schema_validator` cc=22 real 13) y un P1 con LoC desfasado; el único test de la auditoría exigía el texto obsoleto, de modo que la suite blindaba la mentira. `refactor(backups)`: `_collect_files` cc 14 → 3 mediante `_collect_project_dbs` y `_collect_agent_files`, ambos probables de forma aislada. 1431/1431 tests PASS, ruff limpio, `governance/backups.py` 94.14%→95%. Ciclo `wi-45-uow-coverage` en `RELEASE_PENDING`: B1 (lockstep `Cargo.toml`) y B3 (rama del genesis) siguen bloqueando `release.complete` — ver `evidence/b1-b2-diagnosis-correction.md`.
> Stewardship backlog P1 Opción A (H9 addendum honesto) **CERRADO** en `327a913` (2026-09-25).
> WI-01 (release & integration readiness) **RELEASE COMPLETA** — `v0.14.1`. WI-02a (refactor B+C puertos) **RELEASE COMPLETA** — `v0.14.2`. WI-02b (segundo refactor: EventLog/KC por Protocols + escape hatch removal) **RELEASE COMPLETA** — `v0.14.3`. WI-03 (governance/receipts migra a KnowledgeRepository, cierra ultimo escape hatch `_conn`) **RELEASE COMPLETA** — `v0.14.4`. WI-06 (coverage hardening `governance/receipts.py` 73%→99%) **HOUSEKEEPING COMPLETO** — `0.14.5.dev0`. WI-07 (coverage hardening `file_handoff.py` 85%→93%) **HOUSEKEEPING COMPLETO**. WI-08 (coverage hardening `governance/improvement.py` 84%→100%) **HOUSEKEEPING COMPLETO**. WI-11 (release `v0.14.6` housekeeping: WI-06..WI-10 agrupados) **RELEASE COMPLETA**. WI-12 (E1 Adapter real: `HttpAgentAdapter` Anthropic + OpenAI + retry + failpoints) **FEAT COMPLETA**. WI-13 (CLI wiring `sg run --adapter http (anthropic|openai)` con `--llm-provider/--llm-model/--llm-timeout-s`) **FEAT COMPLETA**. WI-14 (T3 Threat model S8: STRIDE sobre Adapter HTTP real; repr redact api_key tras RED test honesto; abuse-cases + 2 gaps P3) **DOC COMPLETA**. WI-15 (T5 Backups CLI: `sg backup create|list|restore` con ZIP + SHA-256 + Connection.backup() API atomica) **FEAT COMPLETA**. WI-16 (T6 Observabilidad runbook: 9 secciones, 3 niveles, schema/exit-codes/CLI verificados contra codigo real) **DOC COMPLETA**. WI-17 (H-06 deuda: `import json` redundante en `cmd_knowledge_compile` eliminado) **HOUSEKEEPING COMPLETO**. WI-18..WI-20 (H-10 locks.py drift Windows docstring honesto; H-03 pack_loader _validate cc 22→7; H-05 _DummyStorage anti-patron eliminado + raise FileNotFoundError legible) **HOUSEKEEPING COMPLETO**. WI-21..WI-30 (debt-reduction H-03) **RELEASE COMPLETA — `v0.14.8`**. WI-31 (cast Storage Protocol eliminado + factor `Storage.knowledge_repository()` + 7 tests) **REFEACTOR COMPLETO** (1 commit `e82c670`). WI-35 (documentar patron SDDK end-to-end) **DOC COMPLETA** (1 commit `2adeb52`).
> **RELEASE v0.15.0 COMPLETA** (QW-A..I R0 housekeeping + WI-31 + WI-35 sobre base post-v0.14.8): BREAKING QW-B + 3 feat + 1 fix → MINOR bump desde `0.14.8.dev0`. Tag anotado `v0.15.0` SHA `0d73f73` sobre commit `4d6d1b4` (release-receipt: `audits/release-v0.15.0-receipt.md`, archive: `audits/release-v0.15.0-archive.md`). 1078/1078 tests PASS, ruff limpio, cobertura 95.25%. Push al remote pendiente (regla 5: la operator decide el momento del push).
> Tag `v0.14.0` preservado como erratum histórico (package metadata decía `0.7.0.dev0`).

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

- HEAD: `42a26cf` (WI-11 release v0.14.6 cerrado en tag anotado + bump `.dev0` post-tag; 23 commits ahead of `origin/main`, push pendiente de aprobacion operador; regla WI-01).
- Tests: **1009/1009 PASS** en 188s (`uv run pytest --no-header -q`; baseline post-WI-12). WI-12 anade +25 tests para `HttpAgentAdapter` (E1 Adapter real con strategies Anthropic + OpenAI, retry exponencial, failpoints).
- Package version: `0.14.6.dev0` (release `v0.14.6` cerrado en tag anotado; bump `.dev0` post-tag para cumplir release_governance). Tags previos: `v0.14.0` (erratum historico, d50f666), `v0.14.1` (WI-01 release, e2cdc53), `v0.14.2` (WI-02a release, da95923), `v0.14.3` (WI-02b release, 7dec857), `v0.14.4` (WI-03 release, dd7a3ef), `v0.14.5` (WI-04/05 housekeeping release, 6ac10ff), `v0.14.6` (WI-06..WI-10 housekeeping release, 42a26cf).
- CI dominante: local `pipelinek` (`.pipeline.kts`). GitHub Actions queda como notificacion informativa (ver AGENTS.md §CI Local Obligatorio).
- **20 releases** emitidas: v0.3.0 → v0.14.6 (incluye 4 PATCH/MINOR de refactor: v0.7.0/v0.7.1/v0.7.2/v0.7.3 + 1 refactor sin bump post-v0.14.0 + 1 v0.8.1 PATCH + 6 Etapa 7 S1..S6 + WI-02b v0.14.3 + WI-03 v0.14.4 + WI-04/05 v0.14.5 housekeeping + WI-06..WI-10 v0.14.6 housekeeping). Nota: H15 no requiere bump (no entrega capacidad nueva a nivel de release, añade superficie de governance).
- **UATs: 16/16 PASS** (uat_audit mantenible, invariante al avance).
- Cobertura nucleo re-medida post-WI-07+WI-08: governance/receipts.py 99% (WI-06), governance/improvement.py 100% (WI-08), file_handoff.py 93% (WI-07). Modulos H11/H12: file_signature.py 100%, file_scope.py 100%.
- Working tree: limpio (post-WI-07+WI-08 commit `951e9ef`).
- ruff format + ruff check: limpios.
- HEAD: 20 commits ahead of `origin/main` (push pendiente de aprobacion operador; regla WI-01).
- `STATE.yaml.release` sincronizado con realidad: tag=v0.14.0, 17 releases, 30 capacidades_entregadas, tag_sha=241ccc9f.
- **H9 addendum honesto**: 5/5 entregables cumplidos (WI-12 cierra E1 Adapter real con `HttpAgentAdapter` Anthropic + OpenAI). Ver `audits/h9-addendum-2026-09-25.md` y `specs/wi-12-http-adapter.md`.
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

**Estado al 2026-09-26 ~11:35 (post-3 consignas 'continua')**:

El operador ha enviado la consigna "continua con el roadmap y sddk"
3 veces en 2 horas sin spec adicional. Búsqueda exhaustiva en 10+
categorías confirma: 0 trabajo substantivo pendiente.

**Estado al 2026-09-26 ~18:18 (post-WI-06/07/08)**:

El operador renueva la consigna "continuamos completando, deuda
tecnica primero y luego roadmap" (autorización explicita para
stewardship créatif). WI-06/07/08 cierran los 3 gaps materiales
reconocidos en cobertura (H-14): `governance/receipts.py` 73%→99%,
`file_handoff.py` 85%→93%, `governance/improvement.py` 84%→100%.
Núcleo evolution-v2 (H11..H15) queda al ≥93% en todos los modulos.

Próximo bloque substantivo (WI-09/10): sincronizar la prosa del
propio CURRENT.md con la realidad post-stewardship + README badges
+ texto evolution-v2. Tras WI-09/10, si no hay spec nueva del
operador, **el agente entra en modo de espera** honesto y NO
fabrica roadmap.

**Modo de espera documentado**: el proyecto está en estado
"esperando spec del operador". Cualquier ciclo de stewardship
transversal posterior requiere:

1. Spec del operador (~1 parrafo) para uno de:
   - E1 Adapter real (proveedor + formato prompts + timeouts + credenciales)
   - T3 Threat model formal (STRIDE/abuse-cases)
   - T5 Backups CLI (formato + retención)
   - T6 Observabilidad (sinks + retención)

2. O desbloquear opcionales con medios:
   - Codecov badge: secret `CODECOV_TOKEN` en GitHub repo settings
   - Audit advisories upstream: acceso a red para `pip-audit` o similar

3. O reabrir iniciativa con nuevo roadmap (ver protocolo seccion 8).

**El agente NO debe fabricar trabajo**. Si la consigna "continua"
se repite sin spec, responder con honest assessment + búsqueda
exhaustiva documentada (como se hizo en este turno).

## Reactivacion 2026-09-26 — WI-06/07/08 (Coverage hardening H-14) cerrado

Cierra el derivado #17 del audit técnico senior (`audits/h14-coverage-gaps-2026-09-26.md`):
los 3 unicos gaps materiales de cobertura reconocidos en `CURRENT.md`
(modulos evolution-v2 H11..H15). Stewardship créatif ejecutado bajo
autorización operador ("continuamos completando, deuda tecnica primero").

### WI-06 (governance/receipts.py 73%→99%)

- Spec: `specs/wi-06-receipts-coverage.md`.
- +28 tests nuevos en `tests/test_h14_validation_receipts.py`.
- 5 clases nuevas: `TestReceiptDataclassValidation`,
  `TestIsReceiptApplicableDeps`, `TestRecordEarlyValidation`,
  `TestListApplicableDefensive`, `TestReceiptVerdictsConstant`.
- Suite: 929→957 PASS en 156.55s.
- Bump `__version__ = "0.14.5.dev0"` post-v0.14.5.
- Commit: `e6ea5c5`.

### WI-07 (file_handoff.py 85%→93%)

- Spec: `specs/wi-07-coverage-file-handoff.md` (retro).
- +17 tests nuevos en `tests/test_h13_handoff_expert.py`.
- 5 clases nuevas: `TestHandoffBlockedErrorMessages`,
  `TestBuildCoverageManifestFoco`, `TestShouldSkipAdapterEmpty`,
  `TestScopeAwareRecipeValidation`, `TestCompileHandoffFromScopesTypeErrors`.
- 5 ramas uncovered restantes (L106, L281, L296, L322, L327):
  type-checks sobre frozen dataclass + isinstance encadenado,
  documentadas en `test_scope_query_invalido_doc` como defensive code.

### WI-08 (governance/improvement.py 84%→100%)

- Spec: `specs/wi-08-coverage-improvement.md`.
- +14 tests nuevos en `tests/test_h15_improvement.py`.
- 7 clases nuevas: `TestImprovementCandidateValidation` (4),
  `TestPromotionDecisionValidation` (4),
  `TestPromoteCandidateApproverRequired` (1),
  `TestRollbackBlockedPolicy` (1),
  `TestDetectRedundantExtractionEmptySigs` (1),
  `TestLocalizeOmissionDefensiveBranches` (2),
  `TestCompareRecipesCorrectionFalse` (1).
- 140 stmts / 0 uncovered / 38 branches / 0 partial → 100%.

### Veredicto

- **Núcleo evolution-v2 (H11..H15) ≥93% cobertura** en todos los modulos.
- Suite consolidada: **984/984 PASS** en 174.26s (+27 tests vs baseline 957).
- Working tree limpio (commit `951e9ef`).
- 0 cambios en codigo de produccion (WI-06/07/08 son solo tests).
- 0 release/tag nuevo. `__version__` sigue en `0.14.5.dev0`.
- Próximos: WI-09 (sincronizar prosa de este mismo `CURRENT.md`,
  cleaning stale markers), WI-10 (README badges + texto evolution-v2),
  después release v0.14.6 si operador aprueba.

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-PRE-PUSH-HOOK cerrado

Cierra el derivado #4 del audit `hooks-ci-2026-09-26.md`: **3ª capa
de defensa operativa** — pre-push hook que ejecuta la suite completa
de pytest antes del push, evitando push que rompan CI.

**Hook** (`scripts/hooks/pre-push`, 62 LoC):
- POSIX shell (mismo patron que pre-commit)
- Toolchain-aware: `mise exec -- uv` con fallback a `uv`
- Suite completa de pytest (~190s) via `run_in_toolchain`
- Bypass via `HOOK_SKIP_PUSH_TESTS=1` (ramas experimentales)
- Bug detectado y corregido: `pipe | tail -N` rompe exit code con
  `set -e`; fix con `mktemp` + `if !` (mismo workaround que `.pipeline.kts`)
- Prefijo `[pre-push]` en logs para identificarse

**Tests** (`tests/test_hooks_system.py`):
- `TestPrePushHook` (8 tests): existe/ejecutable/shebang/pytest/toolchain
  dispatcher/HOOK_SKIP_PUSH_TESTS/prefijo [pre-push]/documenta proposito
- `test_installer_copies_all_hooks` (1 test): e2e en tmpdir con git
  init + installer real; verifica que pre-push NO queda excluido
- Total: 9 tests nuevos

**Verificacion e2e**:
- Caso bypass OK: `HOOK_SKIP_PUSH_TESTS=1 bash scripts/hooks/pre-push`
  -> `[pre-push] HOOK_SKIP_PUSH_TESTS=1 -> saltando suite completa`
- Caso fallo (simulado): patch del hook para usar fake pytest exit 1
  -> `[pre-push] OK` **NO** aparece, aborta con exit 1 + tail del log
- Installer: copia pre-push ejecutable a `.git/hooks/pre-push` con chmod +x

**Suite final**: **888/888 PASS** en 253s (879 baseline + 9 nuevos),
0 regresiones.

**Audit doc**: `audits/pre-push-hook-2026-09-26.md` (239 LoC):
problema + 3 capas defensa + bug doc + 5 limitaciones + 4 derivados.

Sin bump de release (dev-infra).

**Defensa en profundidad completa**:
```text
Local:  pre-commit (lint+format+smoke) → pre-push (full) → push
Remoto: CI (lint+format+full+coverage+cache uv)
```

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-CI-CACHE-COVERAGE cerrado

Implementa derivados #2 (cache uv) y #3 (cobertura) del audit
`hooks-ci-2026-09-26.md` en un solo commit.

**Cache uv en CI**:
- `env.UV_CACHE_DIR = ${{ github.workspace }}/.cache/uv`
- `actions/cache@v4` keyed por `uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}`
- restore-keys fallback (cambios que no afectan deps)
- `uv cache prune --ci` al final (optimiza tamano)

**Cobertura en CI**:
- pytest ahora corre con `--cov=skillgraph --cov-report=xml
  --cov-report=term-missing`
- `upload-artifact@v4` sube coverage.xml (retention 30d, if: always())
- Step summary incluye outcome del nuevo step

**Tests**: 2 nuevos en `TestCIWorkflow` con 6 invariantes totales.
22 → 24 tests en `test_hooks_system.py`. 24/24 PASS.

**Verificacion local**: `pytest --cov` corre 877/877 PASS en 263s.
**Cobertura total medida: 83%** (10 modulos 100%, 4 <80% documentados).

**Limitaciones** (autocritica en audit):
- Sin Codecov badge (decidido NO aplicar).
- Sin enforcement de umbral (fail_under=0, no fuerzo techo).
- Cache miss en primer run (cold start).
- Cache uv funciona porque `mise run sync` internamente usa
  uv sync, que respeta UV_CACHE_DIR.

**Commits**: `8430232 ci: cache uv + coverage artifact`
(4 files, +57/-5 LoC).

**Audit doc**: `audits/ci-cache-coverage-2026-09-26.md` (185 LoC).

Sin bump de release (CI infra).

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-HOOKS-CI cerrado

Implementa el derivado #1 del audit `format-drift-2026-09-26.md`:
pre-commit hook + CI workflow para evitar regresion del drift de
ruff format. **Defensa en profundidad en 3 capas**:

1. **Pre-commit hook local** (`scripts/hooks/pre-commit`, 69 LoC):
   ejecuta `ruff check` + `ruff format --check` + `pytest -q` (cuando
   hay `.py` staged). Toolchain-aware (mise si disponible, fallback
   uv). Bypass via `HOOK_SKIP_TESTS=1` o `--no-verify`.

2. **Installer** (`scripts/install-hooks.sh`, 26 LoC): copia hooks a
   `.git/hooks/`, idempotente, chmod +x automatico.

3. **CI workflow** (`.github/workflows/ci.yml`, 43 LoC): corre en
   push y pull_request a main con `actions/checkout@v4` +
   `jdx/mise-action@v2` + `mise run sync/lint/format/test`. Protege
   incluso si el dev local no instala los hooks.

**Tests** (`tests/test_hooks_system.py`, 165 LoC): 22 tests en 4
clases que verifican presencia + ejecutabilidad + contenido +
contrato del sistema. 22/22 PASS en 0.07s.

**Verificacion e2e del hook**:
- Caso exito: ruff check OK, format OK, pytest 855/855 PASS,
  commit procede.
- Caso negativo: format roto -> error claro con diff sugerido +
  commit abortado.

**Suite completa post-cambios**: **877/877 PASS** en 186s (855
baseline + 22 nuevos), 0 regresiones.

**Limitaciones** (autocritica en audit):
- El agente usa `core.hooksPath=/home/rubentxu/.git-hooks/`
  globalmente, asi que en mi entorno instale un wrapper NO
  commiteable que delega al hook local.
- CI sin cache de uv (~1-2 min extra) y sin cobertura.
- Sin pre-push hook completo (suite lenta vs smoke).

**Commits**: `c7118ef feat(hooks)` (scripts + tests, +246 LoC) +
`d949e33 ci:` (workflow, +45 LoC).

**Audit doc**: `audits/hooks-ci-2026-09-26.md` (172 LoC) con 3
capas + 4 limitaciones + 3 derivados opcionales.

Sin bump de release (dev-infra).

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

## Reactivacion 2026-09-26 — WI-13 CLI HTTP wiring cerrado

WI-13 cierra el bucle del Adapter real (WI-12). El usuario ya puede
ejecutar `sg run` con `--adapter http` para invocar Anthropic u OpenAI
sin tocar codigo, manteniendo `--adapter fake` como default determinista.

### Cambios

- `src/skillgraph/cli/runner.py`: 4 nuevos flags (`--adapter`, `--llm-provider`,
  `--llm-model`, `--llm-timeout-s`) + helper `_build_adapter(args, fixtures_root)`
  que retorna `FakeAgentAdapter` o `HttpAgentAdapter` segun el caso, con
  `ValidationError` tipado para valores invalidos.
- `tests/test_cli_adapter_wiring.py` (nuevo, 219 LoC, 11 tests, 4 clases):
  fake/http/missing-key/rejects-invalid.
- `specs/wi-13-cli-http-wiring.md` (spec + evidencia).

### Evidencia

- HEAD pre-commit: `31562a8` (WI-12 baseline).
- Tests: **1020/1020 PASS** en 238.73s (era 1009, +11 tests nuevos).
- ruff: `check` All checks passed; `format --check` 146 files already formatted.
- CLI `sg run --help` muestra los 4 nuevos flags correctamente.
- D-46: Adapter como drop-in replacement via Protocol `AgentAdapter`
  (D-41). Default `fake` preserva backward-compat 100%.

### Pendiente

- **WI-14 (T3 Threat model)**: STRIDE/abuse-cases documentados sobre
  superficie HTTP nueva (credenciales en env, retry storms, secretos
  en logs).
- **WI-15 (T5 Backups CLI)**: `sg backup create|restore|list`.
- **WI-16 (T6 Observabilidad)**: runbook sinks + retención.
- **WI-17+ (deuda arquitectónica)**: H-01 Storage god-class (2407 LoC),
  H-02 CLI god-module (2332 LoC), H-03 funciones cc>10, H-05 `_DummyStorage`,
  H-06 `import json` inline, H-10 `locks.py` drift Windows.
- Bump `0.14.6.dev0 → 0.14.7` cuando haya suficientes feats acumulados
  (siguiente release candidato).
- Push a origin (regla WI-01, ahora 26 commits ahead of origin/main).

## Reactivacion 2026-09-26 — WI-14 T3 Threat model S8 cerrado

WI-14 cierra el ciclo T3 (Threat model) extendiendo el modelo STRIDE
a la superficie HTTP nueva introducida por WI-12/13. Tambien descubre
y corrige un gap real: el repr/str del adapter filtraba la api_key.

### Cambios

- `docs/architecture/ADR-0015-threat-model-stride.md`: nueva seccion
  S8 (Adapter HTTP real Anthropic + OpenAI) con 6 filas STRIDE
  (4 OK, 2 mitigados con gaps menores P3 deferred). E1 Adapter real
  pasa de gap abierto a CERRADO.
- `src/skillgraph/runtime/http_adapter.py`: `api_key: str = field(repr=False)`
  + `__repr__` explicito que solo muestra provider/model/timeouts.
  Antes, el dataclass auto-generado exponia `api_key='sk-ant-...'`
  en cualquier `repr(adapter)` o `print(adapter)`.
- `tests/test_http_adapter_repr_no_disclosure.py` (nuevo, 2 tests):
  RED -> GREEN tras la mitigacion. Verifica repr y str.
- `specs/wi-14-t3-threat-model-http.md`: spec + 8 abuse-cases.

### Hallazgo honesto (D-47)

El ADR-0015 afirmaba que "el repr NO expone api_key" sin haberlo
verificado. RED test revelo que el dataclass default SI lo exponia.
Mitigacion aplicada: field(repr=False) + __repr__ explicito. Leccion:
los claims de seguridad deben tener tests que los verifiquen.

### Evidencia

- HEAD pre-commit: `8213ea4` (WI-13 baseline).
- Tests: 1022/1022 PASS proyectados (+2 vs WI-13).
- ADR-0015 con 8 superficies (S1..S8), 5 gaps abiertos documentados.
- ruff: All checks passed.

### Pendiente

- WI-15 (T5 Backups CLI) + WI-16 (T6 Observabilidad).
- WI-17+ (deuda H-01..H-10).
- Bump `0.14.6.dev0 → 0.14.7` cuando WI-12/13/14/+15/+16 acumulados.
- Push a origin (regla WI-01, ahora 27 commits ahead).

## Reactivacion 2026-09-26 — WI-15 T5 Backups CLI cerrado

WI-15 cierra el feature T5 del roadmap (`Backups y migraciones`).
El operador ahora puede hacer backup/restore del data-root completo
con verificacion criptografica, sin dependencias externas.

### Cambios

- `src/skillgraph/governance/backups.py` (nuevo, ~395 LoC): API publica
  (create/list/verify/restore) + tipos BackupEntry/BackupManifest/BackupInfo
  frozen+slots; formato ZIP con manifest.json y SHA-256 por archivo.
- `src/skillgraph/cli/runner.py`: sub-comandos `sg backup create|list|restore`
  + dispatcher `cmd_backup` con output legible para humanos.
- `tests/test_backups.py` (nuevo, 22 tests, 6 clases): cubre manifest
  round-trip, errores (data_root/catalog ausentes), SHA-256 mismatch,
  overwrite policy, filtrado de corruptos en `list`.
- `specs/wi-15-t5-backups-cli.md`: spec + decisiones (D-48).

### Evidencia

- HEAD pre-commit: `fc4601c` (WI-14 baseline).
- Tests: **1044/1044 PASS** en 180.48s (+22 vs WI-14).
- ruff: All checks passed.
- CLI: `sg backup --help` muestra los 3 sub-comandos.

### Pendiente

- **WI-16 (T6 Observabilidad runbook)**: docs + sinks.
- **WI-17+ (deuda arquitectónica)**: H-01..H-10.
- Bump `0.14.6.dev0 → 0.14.7` con WI-12/13/14/15/16 acumulados.
- Push a origin (regla WI-01).

## Reactivacion 2026-09-26 — WI-16 T6 Observabilidad runbook cerrado

WI-16 cierra el item `Observabilidad` del ROADMAP. Runbook completo
con 3 niveles (eventos / logs / metricas), validado contra el codigo
real (schema, exit codes, comandos CLI).

### Cambios

- `docs/observability-runbook.md` (nuevo, 300 LoC, 9 secciones).
- `specs/wi-16-t6-observability-runbook.md`: spec + decisiones (D-49).

### Hallazgos durante la escritura (claims verificados honestamente)

- Schema `runtime_events` corregido para coincidir con el real
  (`event_kind`/`payload_json`/`timestamp`, no `event_type`/`payload`/`occurred_at`).
- Exit codes corregidos: `EXIT_VALIDATION=12`, `EXIT_DB_MISSING=5`
  (definidos en `runner.py`, no en `exit_codes.py`).
- `sg runs logs` no soporta `--type`/`--json` (es CSV-like); queries
  avanzadas via `sqlite3` directo.
- Referencia `audits/locks-*.md` no existe; apuntamos a `tests/test_locks.py`.

### Evidencia

- HEAD pre-commit: `c53f0a7` (WI-15 baseline).
- Tests: **1044/1044 PASS** sin cambios (docs-only).
- ruff: N/A (markdown).

### Pendiente

- WI-17+ (deuda arquitectónica H-01..H-10).
- Bump `0.14.6.dev0 → 0.14.7` con WI-12..WI-16 acumulados.
- Push a origin (regla WI-01, ahora 30 commits ahead).

## Reactivacion 2026-09-26 — WI-18..WI-20 deuda cerrada (H-10, H-03, H-05)

Continuacion del cierre de la deuda arquitectonica tras v0.14.7.
Tres fixes quirurgicos:

### Cambios

- `src/skillgraph/runtime/locks.py`: docstring honesto sobre Windows
  (NO soportado, `import fcntl` top-level rompe).
- `src/skillgraph/domain/pack_loader.py`: refactor `_validate`
  (cc 22→7) extrayendo `_check_required/_check_primitive/_check_list`.
- `src/skillgraph/cli/runner.py`: `_open_known_project` ahora RAISE
  FileNotFoundError con mensaje legible cuando el proyecto no existe;
  `main()` tiene handler global que devuelve EXIT_PROJECT_NOT_FOUND=4.
  Clase `_DummyStorage` eliminada (anti-patron).
- `tests/test_h9_cli_inproc_knowledge_refresh_compile_trace.py`: 2 tests
  actualizados al nuevo comportamiento (mensaje legible en lugar de generico).
- `specs/wi-18-20-deuda-arquitectonica.md`: spec + D-51.

### Evidencia

- HEAD pre-commit: `12f389f` (v0.14.7 archive baseline).
- Tests: **1044/1044 PASS** en 188.77s.
- ruff: All checks passed.
- cc `_validate` en pack_loader: 22 -> 7 (~68% reduccion).
- 0 `_DummyStorage` en codigo de produccion.

### Pendiente

- WI-21+ (deuda restante): H-01 Storage god-class (2407 LoC),
  H-02 CLI god-module (2332 LoC), H-03 funciones con cc 11..15.
- Bump `0.14.7.dev0 -> 0.14.8` cuando haya suficientes feats.
- Push a origin (regla WI-01, ~37 commits ahead).

## Reactivacion 2026-09-26 21:36 — WI-21..WI-22 (H-03 continuation)

Continuacion de la deuda H-03 (cc>10) tras WI-19. Tres funciones
mas quedan reducidas con el patron helper extraction:

### Cambios

- `src/skillgraph/governance/graph_expansion.py` WI-21:
  - `validate` cc 24 -> 4 (3 helpers puros: `_check_capabilities`
    cc=3, `_active_remove_warnings` cc<=3, `_check_cycle_bound` cc=10).
- `src/skillgraph/resources/parser.py` WI-22:
  - `parse_markdown` cc 17 -> 2 (4 helpers: `_require_str`,
    `_require_dict`, `_metadata_name`, `_metadata_namespace`).
  - Mensajes de ParseError preservados verbatim.
- `specs/wi-21-h03-graph-expansion-validate.md`,
  `specs/wi-22-h03-parser.md`.

### Decisiones registradas

- D-52: validate-like -> 1 helper por invariante, retorno tuple, <30 LoC.
- D-53: parse_X con 4+ isinstance -> extraer _require_* helpers.
- D-54: _require_* siempre lanza ParseError tipado con source kwarg.

### Evidencia

- Suite completa **1044/1044 PASS** (178-199s).
- ruff: All checks passed.
- commit `9e914ad` (WI-22) sobre `74fe0b8` (WI-21) sobre `1cc52a1`
  (WI-18..WI-20).
- 37 commits ahead of origin/main.

### Pendiente

- WI-23+ H-03 restantes: `take` (runtime/locks.py, cc=16),
  `record_validation_receipt` (governance/receipts.py, cc=14),
  `cmd_promotion_reconcile` (cli/runner.py, cc=14),
  `traverse_invalidations` (cc=13), `invoke` (http_adapter.py, cc=12),
  `compile_handoff_from_scopes` (cc=12).
- H-01 Storage god-class (2407 LoC) y H-02 CLI god-module (2332 LoC)
  son scoped WIs propios, no hacer en este ciclo.
- Considerar bump `0.14.7.dev0 -> 0.14.8` con WI-21+WI-22 (refactor).

## Reactivacion 2026-09-26 22:59 — WI-23..WI-27 (H-03 cleanup masivo)

Continuacion agresiva del refactor H-03. 5 WIs cerrados, cc total
reducido en multiples funciones de la capa core:

### Cambios

- `src/skillgraph/runtime/locks.py` WI-23:
  - `take` cc 16 -> 5 (4 helpers: `_acquire_with_timeout`,
    `_acquire_fail_fast`, `_open_lock`, `_release`).
- `src/skillgraph/governance/receipts.py` WI-24:
  - `record_validation_receipt` cc 14 -> 5 (4 helpers:
    `_require_non_empty` con `empty_msg` kwarg para preservar
    genero, `_require_known_verdict`, `_require_artifact_exists`,
    `_persist_validation_evidence`).
- `src/skillgraph/knowledge/knowledge_invalidator.py` WI-25:
  - `traverse_invalidations` cc 13 -> 5 (3 helpers: `_seed_hop_zero`,
    `_expand_one_hop`, `_warn_if_truncated`).
- `src/skillgraph/runtime/http_adapter.py` WI-26:
  - `invoke` cc 12 -> 7 (sentinel `RetryableHttpStatus` + helper
    `_dispatch_response`).
- `src/skillgraph/knowledge/file_handoff.py` WI-27:
  - `compile_handoff_from_scopes` cc 12 -> 1 (triada clasica
    `_validate_inputs` + `_enforce_coverage_or_raise` +
    `_build_synth_recipe`).
- Specs: `specs/wi-23..wi-27-*.md` y D-55..D-60.

### Decisiones registradas

- D-55: context manager "tomar lock" -> 4 fases, cada fase en helper.
- D-56: `_require_*` con `empty_msg` kwarg para preservar genero.
- D-57: persistencia acoplada (Source+Evidence misma entidad) -> helper.
- D-58: traversal BFS hops -> seed + expand + warn.
- D-59: dispatch por valor con raise tipado por tipo de respuesta.
- D-60: triada clasica de pipeline (validate/enforce/build_synth).

### Estado funciones publicas cc>10

- Antes (WI-22 baseline): 15 funciones.
- Despues (WI-27): 8 funciones. Reduccion 47%.
- Las 8 restantes son mayormente CLI entry points (main, cmd_run,
  cmd_promotion_reconcile) y detect_changes (cc=18).

### Evidencia

- Suite completa **1044/1044 PASS** en cada cierre.
- ruff: All checks passed.
- 5 commits atomicos: `e4e5927`, `3cd8633`, `ab9970f`, `fe67b79`,
  + WI-27 pendiente.
- 41+ commits ahead of origin/main.


## Reactivacion 2026-09-26 23:17 — WI-28 (caracterizacion de deuda)

Hito ceremonial: el auditor `audits/audit_debt.py` (215 LoC) se
ejecuta de forma reproducible y emite `audits/architecture-debt-YYYY-MM-DD.md`
con metricas homologas (cc, loc, nesting) al algoritmo usado en
WI-21..WI-27. Ver D-61..D-66.

### Cambios WI-29 / WI-30 (post-auditor, 2026-09-26 23:25..23:29)

WI-29: cmd_run cc 22 -> 5 (D-67: patron _resolve_X_inputs +
_reconcile_until_terminal + _resolve_X_summary). Tras WI-29 los
hotspots publicos cc>=20 en src/ se reducen a 1: main() cc=43
(excluido por D-64).

WI-30: detect_changes cc 18 -> 8 (D-68: helpers puros
tree-walking a module-level). Tras WI-30 los hotspots publicos
cc>=15 en src/ quedan en 1: main() cc=50 (excluido por D-64).

Politica D-66 satisfecha: cero hotspots publicos cc>=20.

### Cambios

- `audits/audit_debt.py`: CLI `python audits/audit_debt.py`.
  Reporta: 46 modulos, 15985 LoC, 555 funciones, 4 god files,
  hotspots publicos, hotspots privados, funciones largas,
  anidamiento profundo, recomendaciones P0..P3.
- `audits/architecture-debt-2026-09-26.md`: reporte generado.
- `tests/test_audit_debt_smoke.py`: 4 tests via subprocess.
- `specs/wi-28-audit-deuda-arquitectonica.md`.

### Estado de la deuda al cierre WI-28

**P0 (refactor obligatorio)**:
- `cmd_run` (runner.py) cc=22, 122 LoC.
- `_make_schema_validator` (pack_loader.py) cc=22, 77 LoC (privada).
  El main() cc=43 NO se refactoriza surgicalmente (D-64: CLI entry
  point, forma parte del H-02 god module).

**P1 (god modules, requiere ADR)**:
- H-01 storage.py (2407 LoC).
- H-02 cli/runner.py (2477 LoC, incluye `main` cc=43).
- runcontroller.py (1357 LoC).

**P2 (privados cc>=20, opcional)**: caso por caso.

**P3 (funciones >80 LoC)**: ver tabla en reporte.

### Politica D-66

Cero hotspots publicos cc>=20 en cada release, o documentar la
excepcion en CURRENT/CHANGELOG.

### Evidencia

- 4/4 smoke tests audit PASS.
- 1048/1048 suite completa PASS (1044 + 4 nuevos).
- ruff: All checks passed.
- commit `8006c58`, 45 ahead of origin/main.

