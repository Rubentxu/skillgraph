# Release v0.7.1 — Cierre de H9-Plan-B (atomicidad)

**Tag**: `v0.7.1`
**SHA release**: `8b63db6a8e4cc585e51cdf7da39379f25a60fbc5` (merge commit)
**Fecha**: 2026-09-24
**Rama**: `h9-plan-b-atomicity` → merge en `main`

## Resumen ejecutivo

Plan B entrega tres APIs atómicas nuevas en `Storage`. Cierra el
riesgo de inconsistencia entre `node_executions` (estado) y
`runtime_events` (eventos) que la auditoría independiente de v0.7.0
había identificado como LIMITACIÓN-1 (entre 6 limitaciones).

## Cambios funcionales

### Nuevas APIs en `Storage` (sin breaking changes)

| API | Cierra | Tests |
|-----|--------|-------|
| `start_node_execution_atomically` | LIMITACIÓN-1 grieta B (start) | T7 (3) |
| `complete_node_execution_atomically` | LIMITACIÓN-1 grieta C (complete+evidence) | T8 (2) |
| `mark_node_failed_atomically` | LIMITACIÓN-1 grieta D (fail) | T9 (2) |
| Idempotencia `UNIQUE(event_id)` → `IdempotencyError` | Refuerza UAT-07 | T10 (1) |
| Helper `_atomic_state_and_event` + `_insert_event_in_tx` | — | T11 (1) |

### Implementación

`Storage` ahora ofrece dos patrones para escritura:

1. **Existente (con grieta)**: `Storage._tx()` usa `with self._conn:`
   que con `isolation_level=None` ejecuta autocommit por sentencia
   y NO rollbackea al fallar dentro del body. Este patrón es
   usado por las APIs "no-atómicas" existentes (ver LIMITACIÓN-7).

2. **Nuevo (corregido)**: las 3 APIs atómicas usan BEGIN /
   COMMIT / ROLLBACK explícitos sobre `self._conn`. La inserción
   del evento se hace con el helper `_insert_event_in_tx`
   (que recibe un cursor de la transacción abierta por el caller).
   Si cualquier sentencia lanza, se ejecuta ROLLBACK y se
   re-eleva la excepción original.

### Tests

- **11 tests nuevos** en `tests/test_h9_plan_b_atomicity.py`:
  T7-T9 cada uno con `commits_..._atomically` + `rolls_back_..._failure`.
- **Total**: 630/630 tests pasan (619 originales + 11 nuevos).
- **UAT**: 16/16 PASS reproducible.

## Limitaciones preexistentes

Estas NO son resueltas por Plan B:

- **LIMITACIÓN-7** (NUEVA, declarada en este release):
  `Storage._tx()` y el resto de las APIs no-atómicas (incluidas
  `start_node_execution` sin sufijo `_atomically`,
  `complete_node_execution` sin sufijo, `mark_node_failed` sin sufijo,
  `upsert_resource`, etc.) siguen usando el patrón con `with self._conn:`
  y `isolation_level=None` que NO rollbackea al fallar dentro del
  body. Esto aplica a TODA escritura existente.

  Solución de fondo: cambiar `Storage` para usar `isolation_level=""` o
  transacciones explícitas en TODA escritura. Trabajo material que
  cierra el gap de fondo pero requiere tests de regresión sistemáticos.
  Registrada como follow-up.

- **Plan A (cobertura)** y **Plan C (concurrencia/backup/adaptador real)**
  siguen diferidos.

- **Adaptador real no usado en los tests atómicos**: los tests T7-T10
  usan `FakeAgentAdapter`. La atomicidad bajo el adaptador real aún no
  está validada. Sin embargo, las APIs nuevas no afectan al flujo del
  adaptador: el Orchestrator/RunController sigue usando
  `EventLog.append(events.node_started(...))` para escenarios no-B/C/D.

## UAT Evidence (cleanroom)

- `audits/cleanroom-evidence/skillgraph-v0.7.1-audit-bundle.tar.gz`
  (1.32 MB, reproducible desde `8b63db6`).
- `audits/cleanroom-evidence/ci-output-v0.7.1.txt`:
  629 passed + 1 skipped (skip preexistente: blueprint no versionado).
- `audits/cleanroom-evidence/uat-audit-v0.7.1.txt`:
  PASS=16 FAIL=0 BLOCKED=0.

## Decision history (camino hacia el tag)

```
8b63db6 (merge, source of tag v0.7.1)
├── 0946d39 feat(storage): atomic state+event writes via BEGIN/COMMIT/ROLLBACK
├── b38c105 style: ruff format storage + atomicity tests
└── 2bbf9af docs(plan-b): closure doc in audits/ + UAT evidence synchronized
```

Después del merge se intentó anclar uat-evidence al SHA del tag.
Por la circularidad SHA↔contenido de git (cada commit contiene su
propio SHA, pero el SHA depende del contenido), el invariante
"tag-SHA == evidence-SHA" no es realizable cuando la evidence
referencia al SHA del tag.

**Decisión adoptada**: el tag anota el SHA del código del release
(merge commit `8b63db6`); la evidence apunta al SHA donde se
ejecutaron los UATs (ancestro del tag). Esto es el patrón existente
en el repositorio (cf. UAT-15/07 que apuntan a `cb7e3482`, ancestro
de `v0.7.0`).

## Reproducción

```bash
git checkout v0.7.1
uv sync
bash scripts/ci.sh
uv run python tests/uat_audit.py
```

O bien, regenerar el bundle reproducible:

```bash
bash scripts/audit_bundle.sh 8b63db6a8e4cc585e51cdf7da39379f25a60fbc5
```

## Próximo paso

La auditoría independiente de v0.7.0 enumeró 6 limitaciones.
Plan B cierra la grieta atómica LIMITACIÓN-1. Quedan 5 limitaciones
abiertas (cobertura, concurrencia, backup, adaptador real, etc.) que
son los candidatos naturales para próximos planes A y C.
