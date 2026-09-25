# CURRENT — puntero operativo

> Última verificación: 2026-09-24 22:14 (Europe/Madrid).
> Iniciativa `g-skillgraph-bootstrap` **COMPLETED** en v0.6.0 (2026-09-23).
> Etapa 7 (runtime/reconciliación) **CERRADA** en v0.14.0 (2026-09-24).

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

- HEAD: `3e6b1d7` (docs(journal): refactor context_controller helpers puros).
- Tests: **754/754 PASS** en 161s (`uv run pytest -q`).
- 16 releases emitidas: v0.3.0 → v0.14.0.
- **UATs: 16/16 PASS** (uat_audit mantenible, invariante al avance).
- Cobertura núcleo ≥85% en todos los módulos. Cambios post-v0.7.0:
  - `runtime/locks.py` (nuevo, S6): 89%.
  - `runtime/redaction.py` (nuevo, S5): 39% (módulo pequeño, 27 stmts).
  - `knowledge/context_controller.py`: 82% → **88%** (refactor helpers puros).
- Working tree limpio. Sin ficheros pendientes.
- ruff format + ruff check: limpios.

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
  1. Cerrar la iniciativa con Etapa 7 documentada (defendible: 754 tests,
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
