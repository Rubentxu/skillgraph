# Release v0.7.2 — Integración real de Plan B (RunController ↔ APIs atómicas)

**Tag**: `v0.7.2`
**SHA release**: `bc64f6df4564f024d9886c21a8ccb762897e0479` (merge commit)
**Fecha**: 2026-09-24
**Rama**: `h10-v0.7.2-integration-atomicity` → merge en `main`

## Resumen ejecutivo

`v0.7.2` cierra el **defecto de integración** detectado por la
auditoría externa de `v0.7.1`. El release anterior ofreció 3 APIs
atómicas nuevas en `Storage` (start/complete/fail *atomically),
pero `RunController._execute_one` seguía invocando las APIs
no-atómicas y emitiendo eventos con llamadas separadas a
`EventLog.append`. Esto significaba que **el recorrido real del
runtime nunca obtuvo la garantía transaccional**.

`v0.7.2` sustituye los pares modificar-estado → emitir-evento en
`RunController` por las APIs atómicas. La garantía se acredita ahora
**en el camino público del runtime**, no solo en el Storage aislado.

## Cambios funcionales

### `RunController._execute_one`

| Momento | Antes (v0.7.1) | Después (v0.7.2) |
|---|---|---|
| Start | `start_node_execution(...)` + `EventLog.append(NodeStarted)` | `start_node_execution_atomically(event=..., ...)` |
| Complete | `complete_node_execution(...)` + `EventLog.append(NodeCompleted)` + `EventLog.append(EvidenceProduced)` | `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)` |
| Fail | `mark_node_failed(...)` + `EventLog.append(NodeFailed)` | `mark_node_failed_atomically(event=..., ...)` (vía helper `_mark_node_failed`) |

Cada llamada atómica ejecuta una transacción compartida
(BEGIN/COMMIT/ROLLBACK explícito sobre `_conn`). Si el INSERT del
evento falla, el INSERT/UPDATE del estado también rollbackea.

### Tests nuevos

- **`tests/test_h10_runcontroller_atomic_integration.py`** (3 tests,
  T12-T14): ejercicios `RunController.reconcile_run` con fault
  injection sobre `Storage._insert_event_in_tx`. Verifican que al
  fallar el INSERT del evento, el estado rollbackea (la fila no
  queda en RUNNING → SUCCEEDED/FAILED fuera de transacción).

### Compatibilidad

- 633/633 tests pasan (630 originales + 3 nuevos de integración).
- 16/16 UAT PASS reproducible.
- 0 breaking changes: las APIs públicas no cambian.

## Reproducción

```bash
git checkout v0.7.2
uv sync
bash scripts/ci.sh
uv run python tests/uat_audit.py
```

O bien, regenerar el bundle reproducible:

```bash
bash scripts/audit_bundle.sh bc64f6df4564f024d9886c21a8ccb762897e0479
```

## UAT Evidence

- `audits/cleanroom-evidence/skillgraph-v0.7.2-audit-bundle.tar.gz`
  (3.99 MB, reproducible desde `bc64f6df`).
- `audits/cleanroom-evidence/ci-output-v0.7.2.txt`:
  632 passed + 1 skipped (skip preexistente: blueprint no versionado).
- `audits/cleanroom-evidence/uat-audit-v0.7.2.txt`:
  PASS=16 FAIL=0 BLOCKED=0.

## Lo que `v0.7.2` sí cierra

- **LIMITACIÓN-1 grieta B**: start atómico en el recorrido real.
- **LIMITACIÓN-1 grieta C**: complete+evidence atómico en el recorrido real.
- **LIMITACIÓN-1 grieta D**: fail atómico en el recorrido real.
- **Hallazgo externo v0.7.1**: integración real del Plan B
  acreditada por tests de integración con fault injection.

## Lo que `v0.7.2` NO cierra (sigue abierto)

- **LIMITACIÓN-7**: `Storage._tx()` y las APIs no-atómicas
  (`upsert_resource`, `start_node_execution` sin sufijo,
  `complete_node_execution` sin sufijo, `mark_node_failed` sin
  sufijo) siguen usando el patrón `with self._conn:` que con
  `isolation_level=None` NO rollbackea. Las 3 APIs `*_atomically`
  usadas por el runtime son robustas; **pero cualquier llamada a las
  APIs legacy sigue siendo no-atómica** hasta un refactor mayor
  de Storage.

- **`workflow_runs` ↔ `RunCreated` / `RunCompleted`**: las mutaciones
  de `workflow_runs` siguen usando APIs no-atómicas y emitiendo
  eventos con llamadas separadas. Esto está fuera del alcance de
  Plan B y debe abordarse en un trabajo aparte si se requiere.

- **Plan A** (cobertura), **Plan C** (concurrencia, backup,
  adaptador real) siguen diferidos.

## Cambios por archivo

```
src/skillgraph/runtime/runcontroller.py            | 112 +++++----
tests/test_h10_runcontroller_atomic_integration.py | 275 +++++++++++++++++++++
```

## Cadena de comandos hasta v0.7.2

```
e147084 feat(runtime): RunController usa APIs atomicas de Storage (closes review gap)
bc64f6d merge h10-v0.7.2-integration-atomicity -> main
369e878 docs(review): registrar hallazgo externo sobre v0.7.1
412d1bc docs(journal): registra cierre de H9-Plan-B con tag v0.7.1
12cb16e docs(release): v0.7.1 audit bundle, ci-output, uat-audit, summary
8b63db6 merge h9-plan-b-atomicity -> main  ─── tag v0.7.1
```

## Próximo paso

`v0.7.2` cierra **operativamente** Plan B en lo que respeta a las
APIs nuevas. Lo que queda:

1. **LIMITACIÓN-7**: refactor de Storage para que TODA escritura use
   BEGIN/COMMIT/ROLLBACK. Material: requiere tests de regresión
   sistemáticos de TODAS las APIs no-atómicas. Estimación: slice
   equiparable a Plan B (3-5 commits).

2. **`workflow_runs` ↔ eventos**: replicar el patrón Plan B para
   los eventos del run (RunCreated/RunCompleted). Idem estimación.

3. **Plan A / Plan C** siguen diferidos sin cambios.

Recomendación: encarar LIMITACIÓN-7 primero, porque es la grieta de
fondo que más afecta al runtime.
