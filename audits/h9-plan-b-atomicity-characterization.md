# H9 · Plan B — Caracterización de la grieta atómica workflow_runs ↔ runtime_events

> **SHA certificado**: `2ae1bca5d82f59ae257ed300d621368268e7d8a4` (tag `v0.7.0`).
> **HEAD al cierre de caracterización**: `22730158836351b5e04a235a4930044dd30e47d6` (post-auditoría).
> **Modo**: caracterización pura. CERO líneas de producción modificadas en este slice.

## 1. Modelo de concurrencia SQLite

Empiria observada:

- `Storage._conn = sqlite3.connect(..., isolation_level=None, check_same_thread=False)`
  (en `src/skillgraph/platform/storage.py:310`).
- `isolation_level=None` activa **autocommit** en `sqlite3`: cada `execute`
  fuera de un `with conn:` se commitea solo. Si se entra en `with conn:`
  se abre una transacción implícita: COMMIT al salir limpio, ROLLBACK
  si hay excepción.
- `PRAGMA journal_mode = WAL` y `PRAGMA foreign_keys = ON` activos.
- WAL permite **lectores concurrentes con un único escritor**, lo que es
  suficiente para atomicidad a nivel de par estado+evento dentro de
  la misma conexión SQLite.

**Conclusión**: la base de datos YA está configurada para soportar
transacciones multi-statement. El problema NO es el motor, es la
**falta de coordinación entre Storage y EventLog en el código de
orquestación**.

## 2. Estado actual de los pares estado+evento

| ID | Estado | Evento | Flujo HOY | ¿Atómico? | Cierre |
|---|---|---|---|---|---|
| A | `Storage.create_run` INSERT workflow_runs | `event.run_created` (emitido por Orchestrator.run) | `Storage.create_run_atomically` — 1 transaccion `BEGIN + INSERT run + INSERT event + COMMIT` (rollback conjunto si falla el evento) | **SÍ** | slice 4 — commit `13c118f` |
| B | `Storage.start_node_execution` INSERT node_executions RUNNING | `events.node_started` | `Storage.start_node_execution_atomically` — 1 transaccion | SÍ | slices previos |
| C | `Storage.complete_node_execution` UPDATE node_executions SUCCEEDED + result_json | `events.node_completed` + `events.evidence_produced` | `Storage.complete_node_execution_atomically` — 1 transaccion | SÍ | slices previos |
| D | `Storage.mark_node_failed` UPDATE node_executions FAILED + error | `events.node_failed` | `Storage.mark_node_failed_atomically` — 1 transaccion | SÍ | slices previos |
| E | `Storage.transition_run_state` UPDATE workflow_runs state (FAILED/CANCELLED) | `event.run_completed` (FAILED/CANCELLED) | `Storage.transition_run_state_atomically` — 1 transaccion | **SÍ** | slice 4 — commit `13c118f` |
| F | `Storage.recover_interrupted_node_executions` UPDATE FAILED en masa | usualmente sin evento (recovered, no failed por Adapter) | 1 commit único pero sin evento asociado | por contrato NO requiere | — |
| G | emparejamiento `outcome ` → `Storage.transition_run_state` del run a COMPLETED + emission de `run_completed` | (separado en otra rama del código) | `Storage.transition_run_state_atomically` — 1 transaccion | **SÍ** | slice 4 — commit `13c118f` |

Cada par atómico asegura **rollback conjunto**: si el INSERT del evento
falla, el UPDATE/INSERT previo del estado queda revertido y `workflow_runs`
y `runtime_events` permanecen consistentes (ambos antiguos o ambos nuevos).

Slice 4 (commit `13c118f`) cierra A, E y G reusando el helper
`_atomic_state_and_event` existente sin modificar su contrato. Las 4
rutas autorizadas en `RunController` que ahora son atomicas:

  - `RunController.create_run` (ruta A) — genera `run_id` con `new_run_id()`
    y delega en `Storage.create_run_atomically`.
  - 3 ramas terminales en `RunController.reconcile_run`: FAILED por nodo,
    FAILED por budget agotado, COMPLETED (rutas E y G) — delegan en
    `Storage.transition_run_state_atomically`.

Las pruebas focales viven en `tests/test_h9_run_lifecycle_atomic.py`
(4 tests RED→GREEN) y verifican el rollback conjunto cuando el INSERT
del evento falla a través del fault-injector `_FaultyConnection`.

Fuera del slice 4 (sigue siendo deuda pendiente):

  - Concurrencia: dos procesos llamando `transition_run_state_atomically`
    sobre el mismo `run_id` simultaneamente.
  - `recover_interrupted_node_executions` (ruta F).
  - Backup/restore: consistencia entre un snapshot SQLite externo y el
    event log.
  - Adaptador real y seguridad/permisos.

## 3. Contratos contractuales atómicos (los que vamos a cerrar)

Sólo ciñéndonos al alcance del RunController y al `Storage` propio:

- **B**: `start_node_execution` + `node_started` deben ser atómicos en ambos
  sentidos. La fila del NodeExecution queda RUNNING **con su evento** o no
  queda.
- **C**: `complete_node_execution` + `node_completed` + `evidence_produced`
  triple atómico. Sin esto, el sistema queda con `SUCCEEDED` sin evento
  (el path crítico que el auditor reportó).
- **D**: `mark_node_failed` + `node_failed` atómicos. Sin esto, el run
  queda `FAILED` sin evento ni rastro del error.

`A` (create_run) queda fuera del Plan B porque su única llamada es desde
`Orchestrator.run`, no desde RunController._execute_* — gestión distinta.
`E` (transition_run_state) puede ser incluido si acopla a un evento de
estado del run, pero requiere definir "qué transiciones disparan evento
contractualmente" y la consigna limita el cambio. **Plan B cubrirá B, C, D.**

`F` (recover) explícitamente no requiere atomicidad porque no emite
evento del Adapter; la recuperación es **estado-only** por diseño
(documentado en H9-BSlice3-S4).

## 4. Operaciones atómicas candidatas en Storage (propuesta, sin implementar)

| Operación Storage | Contrato |
|---|---|
| `Storage.create_node_execution_atomically(event, **mutation_kwargs)` | INSERT node_executions RUNNING + INSERT runtime_events en **una transacción** |
| `Storage.complete_node_execution_atomically(event, **mutation_kwargs)` | UPDATE node_executions SUCCEEDED + INSERT node_completed + INSERT evidence_produced en **una transacción** |
| `Storage.mark_node_failed_atomically(event, **mutation_kwargs)` | UPDATE node_executions FAILED + INSERT node_failed en **una transacción** |

Las 3 operaciones reciben:
1. El `RuntimeEvent` que se va a persistir.
2. Los `kwargs` para la mutación de la tabla `node_executions`.

Ambas escrituras viven en `self._conn` con `with self._conn:`. La
transacción cubre ambas. Si algo falla, ROLLBACK natural.

**Importante**: `EventLog.append` actual llama `with self._tx():` que a
su vez hace `with self._conn:`. La nueva API no usa `_tx()` ni llama a
`EventLog.append` desde dentro de la transacción — escribe directamente
sobre `self._conn`, evitando así la doble-transacción.

`RuntimeEvent` ya lleva `schema_version`, `causation_id`, `correlation_id`,
`payload` — todo lo necesario para generarlo fuera de `EventLog`.

## 5. Idempotencia

El constraint `UNIQUE(event_id) ON runtime_events` es el mecanismo de
idempotencia actual. Si un proceso cae **DESPUÉS** de commitear la
transacción completa, el evento queda en disco. Si el proceso intenta
insertarlo de nuevo **al reintentar**, el UNIQUE lanza `IntegrityError`
que se traduce a `IdempotencyError`. Esto cumple UAT-07.

Pero hay un punto sutil: si la transacción combinada hace
INSERT state + INSERT event con el mismo `event_id`, el segundo intento
ve solo el primer commit (efectivo) y rollbackea el segundo INSERT
state — el resultado: estado **sin segunda confirmación** + evento
existente del intento anterior. Equivalente semántico. Aceptable.

## 6. Política de commit/rollback

- Commit: salir del `with self._conn:` sin excepción.
- Rollback: cualquier excepción dentro del `with` (sea `raise ValueError`,
  `sqlite3.Error`, `MemoryError`, etc.) hace ROLLBACK automático por el
  context manager.
- Excepciones se propagan al RunController sin tragar; el RunController
  decide si relanzarlas o convertirlas.

## 7. Riesgos detectados

1. **WAL + transacción larga**: SQLite con WAL funciona bien con transacciones
   cortas. Las 3 operaciones candidatas son <5 INSERT cada una, ejecutan en
   <1ms. OK.

2. **Recuperación tras `os._exit`**: SQLite WAL checkpointea automáticamente
   en el próximo open, pero **no testeo esto en Plan B** (queda para
   Plan C). El auditor externo lo señaló.

3. **MemoryError dentro del INSERT**: rollback automático. OK.

4. **Orden de las instrucciones**: la mutación de estado debe ir ANTES
   del INSERT del evento, porque si la mutación falla (e.g. violación
   de FK) no quiero un evento huérfano. Si el evento falla después
   de que la mutación commiteó... **eso es el bug que estamos cerrando**.
   Solución: UN SOLO `with self._conn:` que cubre INSERT state + INSERT event.
   Si cualquier INSERT falla, ROLLBACK de todo.

## 8. Pruebas de caracterización necesarias

Las pruebas T1..T6 de `test_h9_runcontroller_characterization.py` ya
existen. Su estado actual:

- T1 atomicidad idempotency: comprueba que `create_run` corre dos veces
  con mismo `run_id` falla la 2ª con `IdentityConflictError`. Sigue
  válida como caracterización de comportamiento idempotente (no toca el
  nuevo mecanismo).
- T2 happy path state+events: tras `reconcile` de un run completo, los
  eventos esperados están en `runtime_events`. Sigue válida.
- T3 recover all running: `recover_interrupted_node_executions` recupera
  TODOS los RUNNING del run. Sigue válida.
- T4 state+events consistentes: tras recover+reconcile, state y events son
  consistentes. Sigue válida.
- T5 ordering node_executions: orden por started_at ASC.
- T6 distinct sorted executed_node_names.

**Tests que FALTAN y voy a añadir como caracterización de la grieta** (sin tocar producción):

- T7: simulación de excepción DESPUÉS del commit de `start_node_execution`
  pero ANTES del `events.append` — verificar que **HOY** deja el
  NodeExecution RUNNING sin evento `node_started` (grieta observada).
- T8: análogo para `complete_node_execution` + `node_completed`.
- T9: análogo para `mark_node_failed` + `node_failed`.

Estos 3 tests son RED (observan la grieta) y se vuelven GREEN tras el
refactor de Plan B.

## 9. Lo que NO hace este Plan B

- No usa transactions si los eventos NO contractualmente requieren
  par con estado (los eventos de recetas, los `_OutcomeTraced`, etc.
  no entran).
- No cambia la política de idempotencia (UNIQUE constraint).
- No toca `Storage.conn` (sigue siendo propiedad pública para diagnóstico
  del auditor).
- No rediseña EventLog.
- No hace Plan A ni Plan C.
