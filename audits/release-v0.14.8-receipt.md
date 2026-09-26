# Release Receipt v0.14.8 (WI-21..WI-30: debt-reduction H-03)

> Artifact durable ligado a `release-receipt` v0.14.8 (tag anotado `de503b7`).
> Sincroniza los specs delta y preserva la trazabilidad del ciclo de
> deuda tecnica H-03 que cerro 8 hotspots publicos.

## Metadata del release

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.14.8` |
| Commit del tag | `de503b7cafd9551e2dc53a0d6a56faf1cb7415df` |
| Bump | MINOR (`0.14.7.dev0` -> `0.14.8`) |
| Tipo de release | refactor surgical + auditor reproducible (sin breaking changes) |
| Suite al tag | 1048/1048 PASS en 176.30s |
| ruff | All checks passed (check + format) |
| Tests nuevos | +4 (WI-28 audit smoke); resto son refactors 100% backward-compat |
| Hotspots publicos cc≥20 al tag | 0 (D-66 satisfecha) |
| Unico cc≥15 restante | `main()` cc=50 (D-64: CLI entry point, parte de H-02) |

## Alcance del ciclo WI-21..WI-30

10 WIs (WI-21..WI-30), 16 commits total (refactor + docs + bump):

| WI | Foco | Antes | Despues | Decision | Helpers |
|----|------|-------|---------|----------|---------|
| WI-21 | `graph_expansion.validate` | cc 24 | cc 4 | D-52 | helpers puros |
| WI-22 | `parser.parse_markdown` | cc 17 | cc 2 | D-53/D-54 | helpers + fix gender bug |
| WI-23 | `locks.take` | cc 16 | cc 5 | D-55 | 4 helpers privados |
| WI-24 | `record_validation_receipt` | cc 14 | cc 5 | D-56/D-57 | 4 helpers |
| WI-25 | `traverse_invalidations` | cc 13 | cc 5 | D-58 | 3 helpers (seed/expand/warn) |
| WI-26 | `HttpAgentAdapter.invoke` | cc 12 | cc 7 | D-59 | sentinel + `_dispatch_response` |
| WI-27 | `compile_handoff_from_scopes` | cc 12 | cc 1 | D-60 | triada validate/build |
| WI-28 | auditor reproducible | n/a | audit-debt.py | D-61..D-66 | CLI + smoke tests |
| WI-29 | `cli.runner.cmd_run` | cc 22 | cc 5 | D-67 | _resolve/_reconcile/_fixtures |
| WI-30 | `detect_changes` | cc 18 | cc 8 | D-68 | 3 helpers (1 metodo + 2 mod) |

## Delta specs sincronizados

Los specs creados durante este ciclo (versionados en `specs/`):

- `specs/wi-21-h03-graph-expansion.md` — H-03 cleanup graph_expansion.
- `specs/wi-22-h03-parser-markdown.md` — H-03 cleanup parse_markdown.
- `specs/wi-23-h03-locks-take.md` — H-03 cleanup locks.take.
- `specs/wi-24-h03-record-validation-receipt.md` — H-03 cleanup record_validation_receipt.
- `specs/wi-25-h03-traverse-invalidations.md` — H-03 cleanup traverse_invalidations.
- `specs/wi-26-h03-http-adapter.md` — H-03 cleanup HttpAgentAdapter.invoke.
- `specs/wi-27-h03-compile-handoff.md` — H-03 cleanup compile_handoff_from_scopes.
- `specs/wi-28-audit-deuda-arquitectonica.md` — auditor reproducible.
- `specs/wi-29-h03-cmd-run.md` — H-03 cleanup cmd_run.
- `specs/wi-30-h03-detect-changes.md` — H-03 cleanup detect_changes.

## Delta docs

- `audits/audit_debt.py` (nuevo, ~215 LoC) — auditor reproducible CLI.
- `audits/architecture-debt-2026-09-26.md` (nuevo) — reporte emitido por auditor.
- `tests/test_audit_debt_smoke.py` (nuevo, 4 tests) — smoke del auditor.

## Decisiones (D-52..D-68)

- **D-52** Refactor surgical `graph_expansion.validate`: extraer `validate_*` puros sin self.
- **D-53/D-54** Refactor `parse_markdown`: helpers + preservar verbatim errores user-facing.
- **D-55** Refactor `locks.take`: 4 helpers privados (lock_chain/release_chain/...).
- **D-56/D-57** Refactor `record_validation_receipt`: 4 helpers; `empty_msg` kwarg preservado.
- **D-58** Refactor `traverse_invalidations`: 3 helpers (seed/expand/warn).
- **D-59** Refactor `HttpAgentAdapter.invoke`: sentinel `RetryableHttpStatus` + `_dispatch_response`.
- **D-60** Refactor `compile_handoff_from_scopes`: triada validate/enforce/build.
- **D-61** Auditor reproducible como herramienta canonica de caracterizacion.
- **D-62** Metricas homologas (cc/loc/nesting) entre manual WI-21..WI-27 y auditor WI-28.
- **D-63** God module thresholds: >1500 LoC = H-tier, requiere ADR.
- **D-64** Exclusion de `main()` cc=43 del refactor surgical (CLI entry / H-02).
- **D-65** Privados cc≥20 son candidatos P2 caso-por-caso (no automatico).
- **D-66** Politica: cero hotspots publicos cc≥20 en cada release o documentar.
- **D-67** Patron CLI cmd_X = `_resolve_X_inputs` + `_reconcile_until_terminal` + `_resolve_X_summary`.
- **D-68** Helpers puros de tree-walking en `git_source` van a module-level.

## Hallazgos (no-bugs pero utiles)

- **WI-22**: helper default `"vacio"` masculino vs `"revision vacia"` femenino esperado
  en el caller. TDD catches via test que verifica mensaje verbatim. Fix en `parse_markdown`.
- **WI-25**: kwarg `hop` quedo en helper sin uso. TDD catches via 9 tests rojos.
- **WI-27**: triple F821 + UP035 + UP037 requiere TYPE_CHECKING imports + `Sequence`
  from `collections.abc` (no `typing.Sequence`).
- **WI-28**: `cmd_run` cc=43 → cc=50 al re-auditar (las herramientas oficiales cuentan
  mas estrictamente que el analisis manual WI-23..WI-27); pero D-66 ya estaba
  satisfecha por exclusion D-64.
- **WI-29**: tuple-shape mismatch (7-tuple → 6-tuple) en `_resolve_run_inputs` —
  el caller espera unpacking de 6 elementos pero helper devuelvia 7. Tests rojos.

## Compatibilidad

- 100% backward-compatible: ninguna firma publica cambia.
- Mensajes stderr, exit codes, summary prints: preservados verbatim.
- `__version__` bump: `0.14.7.dev0` → `0.14.8` (unico cambio observable).
- Sin migracion de datos (SQLite schema intacto).

## Backlog post-release

- **P1 god modules** (requieren ADR operador):
  - H-01 storage.py (2407 LoC)
  - H-02 cli/runner.py (2477 LoC, incluye `main` cc=50)
  - runcontroller.py (1357 LoC)
- **Formal** `prioridad_1_spec_s7plus` y `prioridad_5_s7plus_ejecucion`
  siguen abiertos en `STATE.yaml.stewardship_backlog`. Requieren
  decision de operador sobre S7+ scope (Opcion A/B/C/D).
- Debt-reduction H-03: AGOTADA por completo (D-66 satisfecha).
- Debt-reduction H-01/H-02: pendiente de ADR (fuera del scope surgical).

## Procedimiento post-tag (housekeeping)

1. Commit bump housekeeping: `0.14.8` → `0.14.8.dev0`.
2. SDDK archive-manifest + sync STATE.yaml/CURRENT/CHANGELOG.
3. Push a `origin/main` (autorizacion operador requerida).
