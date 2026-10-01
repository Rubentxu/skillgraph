# ADR-0017 — Atomicidad estado-evento del runtime: pares en TX única, eventos advisory convergentes

Estado: aceptado (sesión 2026-10-01, ciclo `wi-50-run-state-event-atomicity`).

## Contexto

`CURRENT.md` arrastra desde v0.14.0 un pendiente arquitectónico
abierto: la **grieta de no-atomicidad `workflow_runs` ↔
`runtime_events`** — "conocida, preservada por construcción (decisión
arquitectónica con ADR pendiente)". Los locks de S6 (v0.14.0)
mitigan interleaving a nivel de proceso, y el texto original planteaba
que cerrar la grieta transaccional "requeriría SQLite WAL transactions
coordinando INSERT/UPDATE + event append".

Este ADR existe porque esa premisa quedó **obsoleta en dos pasos**:

1. **H9/H10 (v0.7.x..v0.10)** introdujo variantes `*_atomically`
   (`create_run_atomically`, `transition_run_state_atomically`,
   `start_node_execution_atomically`, `complete_node_execution_atomically`,
   `mark_node_failed_atomically`) que ya ejecutan el par
   estado+evento en una sola transacción, con inyección de fallos
   verificada en tests (`test_h9_run_lifecycle_atomic.py`,
   `test_h10_runcontroller_atomic_integration.py`).
2. **ADR-0016 / WI-56 (v0.16.8)** descompuso `Storage` en
   repositorios reales que comparten `self._conn`, de modo que el SQL
   atómico vive en `SqliteRunRepository`/`SqliteEventStore` sobre la
   MISMA conexión: la coordinación ya no requiere nada nuevo.

Lo que faltaba no era implementación sino **la decisión formal**: qué
pares son atómicos, qué escrituras van sin evento y por qué, y qué
estatuto tienen los eventos advisory. Esta auditoría (barrido completo
de escritores de estado y de `EventLog.append` en
`src/skillgraph/runtime/runcontroller.py`) produce el mapa y cierra el
pendiente.

## Mapa verificado de escrituras (auditoría 2026-10-01)

### Pares estado+evento: atómicos por construcción

| Escritura de estado | Evento emparejado | Mecanismo | Fijado por |
|---|---|---|---|
| INSERT `workflow_runs` (CREATED) | `RunCreated` | `create_run_atomically` | `test_create_run_atomicity_with_fault_at_event_insert`, `test_create_run_atomically_produces_single_run_created_event` |
| →FAILED (nodo fallido) | `RunCompleted(FAILED)` | `transition_run_state_atomically` | `test_failed_terminal_atomicity_with_fault_at_event_insert` |
| →FAILED (budget agotado) | `RunCompleted(FAILED)` | ídem | ídem + integración H10 |
| →COMPLETED | `RunCompleted(COMPLETED)` | ídem | `test_completed_terminal_atomicity_with_fault_at_event_insert` |
| →CANCELLED | `RunCompleted(CANCELLED)` | ídem (`cancel_run`) | `test_cancel_active_run_marks_state_cancelled`, `test_cancel_emits_run_completed_event` |
| INSERT NodeExecution RUNNING | `NodeStarted` | `start_node_execution_atomically` | `test_runtime_start_is_atomic_when_event_fails` (H10) |
| NodeExecution →SUCCEEDED | `NodeCompleted` | `complete_node_execution_atomically` | `test_runtime_complete_is_atomic_when_evidence_fails` (H10) |
| NodeExecution →FAILED | `NodeFailed` | `mark_node_failed_atomically` | `test_runtime_fail_is_atomic_when_event_fails` (H10) |

Propiedad verificada además: *reopen tras fallo en el INSERT del
evento mantiene la consistencia*
(`test_reopen_after_fault_at_event_insert_keeps_consistency`) y cada
par produce **exactamente un** evento (tests
`*_produces_single_*_event`).

### Escrituras de estado SIN evento: intencionales

| Escritura | Por qué no hay evento |
|---|---|
| CREATED→ACTIVE (activación al inicio de `reconcile_run`) | El vocabulario de eventos del runtime (`engine.EventBuilder`: `run_created`, `node_scheduled`, `node_started`, `node_completed`, `node_failed`, `run_completed`, `budget_exceeded`, `handoff_created`) no incluye transición de activación: la activación no es un hecho observable del dominio, es un cambio de puntero interno. Sin evento no hay par que desincronizar. |
| ACTIVE→ACTIVE (avance de `current_node` al siguiente nodo) | Ídem: el progreso observable vive en `NodeExecution`/eventos de nodo, no en el puntero. |
| NodeExecution RUNNING→READY (recuperación UAT-06) | Escritura de recuperación; la re-ejecución posterior emite sus propios eventos (`NodeScheduled`/`NodeStarted` nuevos). |

Estas escrituras usan `_set_run_state`/delegados de escritura simple
**por decisión de 2026-09-23 18:24** (separación Storage↔emisor de
eventos): sin evento emparejado, la separación no abre ninguna grieta.

### Eventos advisory: persistencia individual con ventana convergente

| Evento | Ventana si hay crash antes de la consecuencia | Por qué converge |
|---|---|---|
| `BudgetExceeded` | Queda el evento y el run sigue ACTIVE | El siguiente `reconcile_run` re-evalúa el budget y termina el run en FAILED vía TX atómica; el evento es trazabilidad, no estado |
| `HandoffCreated` | NodeExecution RUNNING sin handoff persistido | `_recover_interrupted` (UAT-06) devuelve RUNNING→READY y la re-ejecución genera uno nuevo |
| `NodeScheduled` | Evento sin NodeExecution aún | El reconcile recalcula la frontier; un scheduled huérfano no altera el estado del run |

Ninguno de los tres es un hecho de transición de estado: son
trazabilidad. La ventana de crash deja como máximo un evento duplicado
o adelantado tras la recuperación, nunca un run en estado que sus
eventos no respalden.

## Decision

1. **La grieta transaccional queda CERRADA tal como está**: todo par
   estado+evento semántico del runtime se escribe en una única
   transacción SQLite vía las variantes `*_atomically` sobre la
   conexión compartida (substrate de ADR-0016). No se necesita ni se
   quiere una "transacción coordinadora" adicional: la alternativa
   que planteaba el pendiente original quedó superada por las
   variantes H9/H10.
2. **Las escrituras de estado sin evento son intencionales** y se
   mantienen separadas del emisor de eventos (decisión
   2026-09-23 18:24, ahora ratificada): acoplar `Storage` a un
   emisor genérico para escrituras sin pareja añadiría acoplamiento
   sin cerrar ninguna ventana real.
3. **Los eventos advisory se persisten individualmente** y su ventana
   de crash converge por `_recover_interrupted` + reconcile
   determinista. Se documenta como propiedad, no como accidente.
4. **Interleaving entre procesos**: sigue siendo dominio de `RunLock`
   (S6, v0.14.0, `test_locks.py` con `multiprocessing`); lectores
   concurrentes, de WAL. La certificación bajo carga con proveedores
   reales sigue fuera de alcance (ítem operativo separado, requiere
   infraestructura del operador).
5. Regla hacia adelante: **toda nueva transición de estado que
   emita evento debe nacer como variante `*_atomically`**; un
   `append` suelto solo se admite para eventos advisory, con la
   ventana de convergencia documentada junto al código.

## Consecuencias

- Se cierra el pendiente #2 de `CURRENT.md` ("grieta de
  no-atomicidad… ADR pendiente"): no hay ADR que escribir porque la
  grieta exista, sino para dejar constancia de que ya no existe.
- El pendiente #3 (certificación de concurrencia real bajo carga)
  permanece abierto como ítem operativo, no arquitectónico.
- Mantenimiento: si `EventBuilder` incorpora un evento nuevo de
  transición, la regla 5 obliga a la variante atómica en el mismo
  ciclo; el audit de deuda (`audits/audit_debt.py`) no mide esta
  propiedad, así que la red son los tests de inyección de fallos
  existentes y este documento.

## Referencias

- H9 (slices de lifecycle atómico): commits y tests listados arriba.
- ADR-0016 (descomposición de Storage): el substrate de conexión
  compartida que hace triviales las TX coordinadas.
- Decisión 2026-09-23 18:24 (separación Storage↔emisor), ratificada
  en el punto 2.
- `CURRENT.md` pendientes #2/#3 (estado previo a este ADR).
