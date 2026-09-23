# H9-BSlice3 · RunController ↔ Storage · caracterización

> Documento de caracterización para un refactor mayor. **No contiene
> cambios de código**: solo inventario y superficie de pruebas.
>
> Origen de la decisión: consigna del operador del 2026-09-23 18:03
> sobre `RunController` y `Storage`. Sustituye a la antigua idea
> "BSlice3 = eliminar `cmd_run.storage._conn`": esa ruta convertía
> un acoplamiento de implementación en una API pública sin realmente
> desacoplar `RunController` del storage.

## 1. Estado actual

`RunController` recibe dos dependencias de persistencia en su
constructor:

```python
RunController(*, storage: Storage, adapter: AgentAdapter, conn: sqlite3.Connection)
```

Y ejecuta SQL directo sobre `self._conn` en 10 sitios. `EventLog`
también depende del mismo `conn` y ejecuta SQL directo (en su propia
clase, no via `Storage`). Ambos abren transacciones por su lado.

El `cmd_run` del runner accede a `storage._conn` para pasárselo al
`RunController`. Eso ES un hueco de límites, pero el problema de
fondo es el de arriba.

## 2. Inventario de las 10 SQL sites

Inventario identificado por lectura directa de
`src/skillgraph/runtime/runcontroller.py` el 2026-09-23 17:54. Numeración
estable (`S#`) para referencia desde tests y commits futuros.

| S# | Línea método        | Línea SQL | Operación                                                                                | Tabla               | Evento próximo               | ¿Comparte transacción hoy? |
|----|---------------------|-----------|------------------------------------------------------------------------------------------|---------------------|-------------------------------|-----------------------------|
| S1 | `create_run`        | 184       | INSERT workflow_runs (run, state=CREATED, plan_json, current_node)                        | workflow_runs       | append `run_created`         | NO                          |
| S2 | `_load_run`         | 314       | SELECT * FROM workflow_runs WHERE tenant+project+run                                       | workflow_runs       | —                             | —                           |
| S3 | `_set_run_state`    | 334       | UPDATE workflow_runs SET state, current_node, updated_at                                  | workflow_runs       | opcional (llamadores emiten) | NO                          |
| S4 | `_recover_interrupted` | 347 + 357 | (lectura + UPDATE por fila) UPDATE node_executions SET state=READY, finished_at          | node_executions     | NO emite evento               | NO (bucle; cada fila abre tx) |
| S5 | `_execute_one` start | 470       | INSERT node_executions (state=RUNNING, started_at, context_hash, handoff_json)            | node_executions     | append `node_started`         | NO                          |
| S6 | `_execute_one` ok   | 533       | UPDATE node_executions SET state=SUCCEEDED, outcome, result_json, finished_at             | node_executions     | append `node_completed` + `evidence_produced` | NO |
| S7 | `_mark_node_failed` | 625       | UPDATE node_executions SET state=FAILED, error, finished_at                               | node_executions     | (en algunos paths, después)  | NO                          |
| S8 | `_node_executions_for` | 637    | SELECT * FROM node_executions WHERE tenant+project+run+node_name ORDER BY started_at       | node_executions     | —                             | —                           |
| S9 | `_executed_node_names` | 663    | SELECT DISTINCT node_name FROM node_executions WHERE state=SUCCEEDED ORDER BY node_name     | node_executions     | —                             | —                           |

(Sin número: la inserción de un `WorkflowExpansion` indirecto del flujo
no forma parte de la reconciliación; queda fuera de este inventario.)

### 2.1 Resumen por categoría

| Categoría          | Sitios | ¿Comparten transacción con EventLog hoy? |
|--------------------|--------|-------------------------------------------|
| Crear un Run       | S1     | NO — cada lado abre su propia transacción |
| Cargar Run (lectura) | S2    | N/A (solo lectura)                        |
| Cambiar estado Run | S3     | NO — el llamador emite el evento aparte   |
| Recuperar nodo huérfano | S4 | NO (bucle de 1-tx-por-fila, sin evento) |
| Insertar NodeRunning | S5   | NO — `node_started` aparte               |
| Marcar NodeSucceeded | S6  | NO — `node_completed` + `evidence_produced` aparte |
| Marcar NodeFailed  | S7     | NO — algunos llamadores emiten `node_failed` aparte |
| Lecturas de node_executions | S8, S9 | N/A |

### 2.2 Consecuencia de la NO atomicidad actual

Cada par (state change, evento) tiene la grieta clásica:

> si la inserción SQL se commitea pero el append del evento lanza
> (p.ej. `IdempotencyError`), el estado queda movido sin su evento.
> Si el orden es el inverso — evento emitido antes de commitear el
> estado — el evento aparece cuando el state aún no ha movido.

Esta grieta **ya existe**, no se introduce al refactorizar. Las
pruebas de hoy no la ejercitan ni la bloquean; bloquean cada
operación de forma independiente. Cualquier refactor de S3..S7 debe
preservar el comportamiento observable actual o cerrar la grieta,
pero **no debe introducir regresiones** sin evidencia.

## 3. APIs equivalentes que ya existen en `Storage`

Cruce del inventario contra `src/skillgraph/platform/storage.py`:

| S# | Hoy                                              | API en Storage         |
|----|---------------------------------------------------|------------------------|
| S1 | INSERT workflow_runs                             | **no existe**          |
| S2 | SELECT run                                        | **no existe**          |
| S3 | UPDATE state+current_node                          | **no existe**          |
| S4 | UPDATE node_executions READY                      | **no existe**          |
| S5 | INSERT node_executions RUNNING                   | **no existe**          |
| S6 | UPDATE state SUCCEEDED + outcome + result         | **no existe**          |
| S7 | UPDATE state FAILED + error                       | **no existe**          |
| S8 | SELECT node_executions por (tenant+project+run+node_name) | **no existe** (existe `find_active_run` para runs, no para nodos) |
| S9 | SELECT DISTINCT node_name state=SUCCEEDED         | **no existe**          |

**Implicación**: ningún método de `Storage` cubre hoy el ciclo de
vida de un Run. Cualquier refactor **debe primero añadir las APIs
transaccionales en Storage**, antes de cambiar `RunController`.

`Storage` ya tiene un context manager `_tx()` (línea 332) que se usa
en algunas inserciones, pero su propio cuerpo sigue recurriendo a
`with self._conn:` en otros puntos. Esa inconsistencia NO se aborda
en este refactor — es un slice aparte.

## 4. Atomicidad requerida por operación

Decisión que se aplicará cuando lleguen los slices de implementación:

| S# | Operación de Storage a crear                          | Atomicidad con EventLog          |
|----|-------------------------------------------------------|-----------------------------------|
| S1 | `create_run_atomic(plan) -> run_id`                   | **una sola transacción** con append `run_created` |
| S2 | `load_run(tenant_id, project_id, run_id) -> row`      | — (lectura)                        |
| S3 | `transition_run_state(...)`                            | NO atómica a nivel SQL; pero debe invocarse **antes** del append para que el evento refleje el nuevo state |
| S4 | `recover_interrupted_node(node_execution_id) -> bool`  | sin evento                         |
| S5 | `start_node_execution(...)`                            | **una sola transacción** con append `node_started` |
| S6 | `complete_node_execution(...)`                         | **una sola transacción** con append `node_completed` y `evidence_produced` |
| S7 | `fail_node_execution(...)`                             | **una sola transacción** con append `node_failed` (si aplica) |
| S8 | `list_node_executions(tenant_id, project_id, run_id, node_name)` | — (lectura)         |
| S9 | `list_executed_node_names(...)`                        | — (lectura)                        |

> **Regla**: si una operación `RunController` cambia estado y debe
> emitir un evento, **el método de `Storage` realiza ambos o ninguno**
> dentro de la misma transacción. El controlador deja de orquestar
> la atomicidad y pasa a ser un consumidor directo.

## 5. Estado de cobertura de pruebas

`tests/test_runcontroller.py` cubre (10 tests):

- `test_create_run_inserts_workflow_runs_row` (S1 — parcial: solo el INSERT)
- `test_create_run_emits_run_created_event` (S1 — lado EventLog)
- `test_single_node_completes_run` (S5+S6 happy path)
- `test_completed_run_does_not_emit_on_reconcile`
- `test_two_nodes_advance_via_two_reconciles` (S5+S6+S9)
- `test_missing_fixture_fails_node` (S7)
- `test_outcome_not_declared_in_plan_fails` (S7)
- `test_running_node_without_finished_at_is_recovered` (S4)
- `test_replaying_run_created_event_id_raises` (S1 idempotencia vía
  `event_id`)
- `test_adapter_called_once_per_node`

### 5.1 Huecos que SÍ conviene cerrar antes de cualquier refactor

| # | Test que falta                                              | Invariante que bloquea                                 |
|---|-------------------------------------------------------------|---------------------------------------------------------|
| T1 | `test_create_run_state_persists_when_event_append_fails`    | S1: si append lanza, el INSERT del Run debe hacer rollback |
| T2 | `test_complete_node_execution_atomic_state_plus_events`    | S6: si append final lanza, el UPDATE debe hacer rollback |
| T3 | `test_recover_interrupted_is_per_row_atomic`                | S4: cada `UPDATE` es atómica (sin "mitad aplicada")     |
| T4 | `test_state_change_visible_before_event_invariant`         | S3 + llamador: el state se commit antes que el emit del evento |
| T5 | `test_node_executions_for_lists_in_started_order`          | S8: orden por `started_at ASC`                           |
| T6 | `test_executed_node_names_distinct_sorted`                  | S9: DISTINCT + ORDER BY node_name                        |

> T1 y T2 son los más sensibles: si pasan HOY con cualquier conn
> compartida, también pasarán tras el refactor. Si pasan AL CAMBIAR
> el orden de `with self._conn:` + `events.append(...)`, ese test
> será la primera red de seguridad del refactor.

## 6. Criterios de cierre del refactor completo

Tomados literalmente de la consigna:

1. `RunController` **no recibe** `sqlite3.Connection` en su `__init__`.
2. `RunController` **no accede** a `self._conn.execute(...)` (eliminar
   las 10 SQL sites listadas arriba).
3. Las transiciones de estado (`workflow_runs`) y los eventos
   (`runtime_events`) conservan sus garantías de atomicidad
   observables — T1 y T2 en verde.
4. Las pruebas existentes siguen pasando. T3..T6 nuevas en verde.
5. La cobertura de `tests/test_runcontroller.py` se mantiene ≥ 90%.

## 7. NO-objetivos

- **No** se introduce un `Storage.connection()` público para
  sustituir `_conn` como API intermedia. Esa ruta fue descartada
  por la consigna.
- **No** se cambia el esquema SQLite.
- **No** se modifica `EventLog.append` ni su contrato de idempotencia.
- **No** se introduce un ORM.
- **No** se combinan nuevos features de producto con este refactor.

## 8. Roadmap de slices previsto (no comprometidos)

Esto NO es un plan comprometido; son los pasos que la caracterización
sugiere para una eventual ejecución. Cada uno debe ser verificable
de forma aislada y pedirá su propia consigna material si la hubiera.

| #  | Slice                                                                  | Estado        |
|----|------------------------------------------------------------------------|---------------|
| S0 | Caracterización (este documento) y tests T1..T6                          | **aquí**      |
| S1 | `Storage.list_node_executions` y `Storage.list_executed_node_names`     | pendiente      |
| S2 | `Storage.load_run`, `Storage.transition_run_state` (sin atomicidad)     | pendiente      |
| S3 | `Storage.create_run_atomic` con `run_created` en la misma transacción    | pendiente      |
| S4 | `Storage.start_node_execution_atomic` con `node_started`                  | pendiente      |
| S5 | `Storage.complete_node_execution_atomic` con `node_completed` + `evidence_produced` | pendiente |
| S6 | `Storage.fail_node_execution_atomic` con `node_failed`                  | pendiente      |
| S7 | `Storage.recover_interrupted_node`                                       | pendiente      |
| S8 | Migrar `RunController` a las nuevas APIs y quitar `conn` del `__init__` | pendiente      |
| S9 | Eliminar `storage._conn` del `cmd_run` y del fixture de tests           | pendiente      |
