# WI-02 — Refactor B+C: puertos de persistencia + división por capabilities

> Spec derivada de la auditoría técnica integral 2026-09-26
> (HEAD `b1bb264` auditado; HEAD actual `e2cdc53` con WI-01 release
> `v0.14.1` aplicado). El WI-02 cierra los hallazgos #5 y #6
> (ALTA severidad) y avanza el #7 (MEDIA-ALTA, división de Storage
> por capabilities).

## 1. Contexto y motivación

La auditoría identificó tres violaciones de la arquitectura hexagonal
declarada en `AGENTS.md §4.3`:

1. `RunController.__init__(storage: Storage)` — el controlador
   depende de la clase concreta `Storage`, no de un Protocol.
2. `EventLog.__init__(conn: sqlite3.Connection)` — el log de
   eventos recibe directamente una conexión SQLite, no un
   repositorio abstracto.
3. `Storage.conn` como API pública (líneas 339-353 de
   `src/skillgraph/platform/storage.py:339`) — un escape hatch
   creado en H9-BSlice3-S8 para que `RunController` construya
   `EventLog`. `KnowledgeController` todavía accede a
   `storage._conn` (el atributo "privado" que convive con el
   "público" `conn`).

Adicionalmente, `Storage` (2148 líneas) expone ~60 métodos
públicos que cubren al menos 6 capabilities disjuntas
(resources, sources, claims/evidence, traces, runs, events,
budget, policy, promotions, knowledge). El modelo
"implementación profunda + interfaz enorme" produce alto
fan-out, dificultad para tests aislados y propagación de
cambios cruzados.

## 2. Objetivo

Introducir **Protocols pequeños por capability**, mantener
`Storage` como **fachada de compatibilidad**, y migrar el core
(`RunController`, `EventLog`, `KnowledgeController`) para que
dependa de los Protocols. La conexión SQLite queda contenida
en `src/skillgraph/platform/`.

## 3. Decisiones explícitas

- **D-08.** WI-02 adopta el híbrido **B + C** de la auditoría:
  puertos de capabilities pequeños + operaciones atómicas de
  alto nivel cuando exista invariante real
  (`start_node_atomically`, `complete_node_atomically`,
  `transition_with_event`, `recover_interrupted_node_executions`
  ya existen; se exponen vía el Protocol).
- **D-09.** `Storage` se mantiene como **fachada**: delega cada
  método a una clase interna por capability
  (`SqliteRunRepository`, `SqliteEventStore`,
  `SqliteKnowledgeRepository`, `SqlitePromotionRepository`,
  `SqlitePolicyStore`). Tests legacy y CLI existente siguen
  funcionando sin cambios. La fachada implementa los 5
  Protocols simultáneamente.
- **D-10.** `sqlite3.Connection` no sale de `platform/`. Los
  adapters SQLite son los únicos que reciben `conn`; el resto
  del código solo ve Protocols.
- **D-11.** Atomicidad transaccional sigue siendo responsabilidad
  del adapter SQLite. `RunRepository` expone operaciones
  compuestas cuando la invariante es real
  (`start_node_atomically` lo es: estado + evento + handoff
  en una transacción). No se crea un UnitOfWork algebraico.
- **D-12.** `Storage.conn` deja de ser API pública. Se elimina
  el `@property conn`; `RunController` deja de llamar a
  `storage.conn`. La conexión se inyecta explícitamente a las
  clases internas por capability en `Storage.__init__`.
- **D-13.** Bump PATCH: `__version__ = "0.14.2"` tras CI verde
  + tag anotado `v0.14.2`. Sin cambio de API CLI observable.
  Sigue AGENTS §12 Regla de release.

## 4. Contrato observable

### 4.1. Nuevos Protocols en `src/skillgraph/platform/ports/`

```python
# ports/__init__.py — exporta los 5 Protocols

class RunRepository(Protocol):
    """Operations sobre runs y node_executions."""
    def find_active_run(self, *, tenant_id: str, project_id: str) -> dict | None: ...
    def list_runs(self, *, tenant_id: str, project_id: str, limit: int = 50) -> list[dict]: ...
    def get_run(self, *, tenant_id: str, project_id: str, run_id: str) -> dict | None: ...
    def list_events_for_run(self, *, tenant_id: str, project_id: str, run_id: str) -> list[dict]: ...
    def load_run(self, *, tenant_id: str, project_id: str, run_id: str) -> dict | None: ...
    def list_node_executions(self, *, run_id: str) -> list[dict]: ...
    def list_executed_node_names(self, *, run_id: str) -> list[str]: ...
    def recover_interrupted_node_executions(self, *, run_id: str) -> int: ...
    def transition_run_state(self, *, run_id: str, new_state: str) -> None: ...
    def start_node_execution(self, *, run_id: str, node_name: str, attempt: int, ...) -> str: ...
    def complete_node_execution(self, *, node_execution_id: str, result_json: str) -> None: ...
    def mark_node_failed(self, *, node_execution_id: str, error: str) -> None: ...
    def update_node_execution_handoff(self, *, node_execution_id: str, handoff_json: str) -> None: ...
    # Operaciones atómicas de alto nivel:
    def start_node_execution_atomically(self, *, run_id: str, node_name: str, attempt: int, ...) -> tuple[str, int]: ...
    def complete_node_execution_atomically(self, *, run_id: str, node_name: str, result_json: str) -> tuple[str, int]: ...
    def mark_node_failed_atomically(self, *, run_id: str, node_name: str, error: str) -> tuple[str, int]: ...
    def create_run(self, *, tenant_id: str, project_id: str, plan_json: str, ...) -> str: ...

class EventStore(Protocol):
    """Append-only log de runtime_events."""
    def append(self, event: RuntimeEvent) -> int: ...
    def list_events(self, *, tenant_id: str, project_id: str, run_id: str | None = None, limit: int = 100) -> list[dict]: ...
    def record_event(self, *, event_id: str, tenant_id: str, project_id: str, ...) -> None: ...
    def list_events_for_run(self, *, tenant_id: str, project_id: str, run_id: str) -> list[dict]: ...

class KnowledgeRepository(Protocol):
    """Operaciones sobre sources, entities, claims, evidence, traces."""
    def register_source(self, *, ...) -> str: ...
    def get_source(self, *, ...) -> dict | None: ...
    def update_source_freshness(self, *, ...) -> None: ...
    def upsert_entity(self, *, ...) -> str: ...
    def get_entity(self, *, ...) -> dict | None: ...
    def record_evidence(self, *, ...) -> str: ...
    def get_evidences_for_claim(self, *, ...) -> list[dict]: ...
    def record_claim(self, *, ...) -> str: ...
    def get_claim(self, *, ...) -> dict | None: ...
    def list_claims_for_source(self, *, ...) -> list[dict]: ...
    def list_claims_by_predicate(self, *, ...) -> list[dict]: ...
    def list_evidences_for_source(self, *, ...) -> list[dict]: ...
    def list_resource_refs_for_run(self, *, ...) -> list[str]: ...
    def attach_evidence_to_claim(self, *, ...) -> None: ...
    def record_finding(self, *, ...) -> str: ...
    def record_trace(self, *, ...) -> str: ...
    def link_trace(self, *, ...) -> None: ...

class PromotionRepository(Protocol):
    """Outbox de promoción entre proyectos (H7)."""
    def register_promotion(self, *, ...) -> str: ...
    def get_promotion(self, *, proposal_id: str) -> dict | None: ...
    def list_pending_promotions(self, *, ...) -> list[dict]: ...

class PolicyStore(Protocol):
    """Políticas de redacción y budgets por tenant."""
    def get_policy(self, *, tenant_id: str) -> str | None: ...
    def upsert_policy(self, *, tenant_id: str, policy: str) -> None: ...
    def upsert_budget(self, *, tenant_id: str, project_id: str, run_id: str, ...) -> None: ...
    def get_budget(self, *, tenant_id: str, project_id: str, run_id: str) -> dict | None: ...
```

### 4.2. Migración de RunController

```python
class RunController:
    def __init__(
        self,
        *,
        runs: RunRepository,        # antes: storage
        events: EventStore,          # antes: derivado de storage.conn
        policy: PolicyStore,         # antes: derivado de storage.get_policy
        adapter: AgentAdapter,
        recipe_resolver: ... = None,
        lock_dir: ... = None,
        lock_mode: ... = "none",
        lock_timeout_seconds: ... = 30.0,
    ) -> None:
        self._runs = runs
        self._events = events
        self._policy = policy
        ...
```

`Storage` se mantiene como constructor de compatibilidad que
recibe `path` y crea los 5 adapters; ofrece un factory
`Storage.run_repository()` etc. para inyección granular.

### 4.3. Migración de EventLog

```python
class EventLog:
    def __init__(
        self,
        events: EventStore,          # antes: sqlite3.Connection
        *,
        policy: PolicyStore | None = None,
    ) -> None:
        self._events = events
        self._policy = policy
        # _migrate() se mueve a la primera llamada de append()
        # o se delega al adapter SQLite via el EventStore.
```

### 4.4. Migración de KnowledgeController

`KnowledgeController` deja de acceder a `storage._conn`. Si
necesita ejecutar SQL ad-hoc (queries no cubiertas por el
Protocol), se añade un método al `KnowledgeRepository` o se
crea un `KnowledgeQueryPort` específico.

### 4.5. Eliminación de escape hatch

`Storage.conn` se elimina. Cualquier consumidor que lo use
rompe con error explícito en el momento de la migración. Los
tests que dependían de `storage._conn` se migran a
`storage.run_repository()` o equivalente.

## 5. Criterios de aceptación

| ID | Criterio | Comprobación | Estado al cierre |
|---|---|---|---|
| AC-1 | 5 Protocols exportados en `src/skillgraph/platform/ports/` | `python -c "from skillgraph.platform.ports import RunRepository, EventStore, KnowledgeRepository, PromotionRepository, PolicyStore"` exit 0 | PASS |
| AC-2 | `RunController.__init__` ya no menciona `Storage` | `grep -L "storage:" src/skillgraph/runtime/runcontroller.py` exit 0 | PASS |
| AC-3 | `EventLog.__init__` ya no menciona `sqlite3.Connection` | `grep "sqlite3.Connection" src/skillgraph/runtime/engine.py` solo aparece en `_SCHEMA_SQL` | PASS |
| AC-4 | `Storage.conn` removido (no es `@property`) | `grep "@property\|def conn" src/skillgraph/platform/storage.py` no expone `conn` | PASS |
| AC-5 | `KnowledgeController` ya no accede a `storage._conn` | `grep "_conn" src/skillgraph/knowledge/knowledge_controller.py` exit 1 | PASS |
| AC-6 | 920/920 tests PASS | `uv run pytest --no-header -q` -> 920 passed | PASS |
| AC-7 | coverage ≥ 60% sin regresión | `uv run pytest --cov=skillgraph --cov-fail-under=60` -> ≥ 60% | PASS |
| AC-8 | ruff limpio | `mise run lint` exit 0 | PASS |
| AC-9 | pipelinek run SUCCESS | `REPO_ROOT=$(pwd) pipelinek run ...` -> "Pipeline finished with SUCCESS" | PASS |
| AC-10 | Bump PATCH + tag `v0.14.2` | `git tag -l 'v0.14*'` muestra v0.14.0/1/2; `__version__ == "0.14.2"` | PASS |
| AC-11 | `Storage` sigue siendo fachada compatible | `Storage(path).upsert_resource(...)` sigue funcionando; tests legacy sin cambios | PASS |

## 6. Out of scope (declarado)

- WI-03: división de `cli/runner.py` por command groups.
- WI-04: type checker progresivo (mypy/pyright).
- WI-05: división de `Storage` en módulos físicos separados
  (en este WI la división es **lógica** — clases dentro del
  mismo módulo — no física; mover a archivos separados
  separados cuando se justifique por tamaño).
- Funcionales pendientes E1 (adapter real), T5 (backups),
  T6 (observabilidad), grieta workflow↔event (P3).

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `RunController` migrado rompe 919 tests | Fachada `Storage` mantiene la API vieja; tests legacy siguen usando `Storage(path)` directamente. Solo cambian los tests de `runcontroller` que usaban `storage.conn` |
| `EventLog._migrate()` debe ejecutarse en algún momento | Se ejecuta lazy en el primer `append()` o se delega al adapter SQLite vía el `EventStore` |
| Atomicidad transaccional rota al pasar de `storage._conn` a `RunRepository` | `RunRepository.start_node_execution_atomically` envuelve la transacción; tests de atomicidad T1/T4/T5 ya existentes (Storage) siguen verdes |
| `Storage.conn` se usa en algún test legacy que no detecté | Los tests fallarán con AttributeError explícito; se migran atómicamente en el mismo PR |
| `pytest` falla en orden de descubrimiento | Las migraciones se hacen en commits separados: 1) ports + adapters sin tocar consumidores; 2) migrar RunController; 3) migrar EventLog; 4) migrar KnowledgeController; 5) eliminar Storage.conn |

## 8. Plan de aplicación (resumen)

### Fase 1: introduce ports + adapters (sin tocar consumidores)
1. Crear `src/skillgraph/platform/ports/__init__.py` con los 5 Protocols.
2. Crear `src/skillgraph/platform/sqlite_adapters.py` con
   `SqliteRunRepository`, `SqliteEventStore`,
   `SqliteKnowledgeRepository`, `SqlitePromotionRepository`,
   `SqlitePolicyStore`. Cada adapter recibe `conn` y
   implementa su Protocol delegando a los métodos actuales
   de `Storage` (mover el cuerpo de cada método al adapter
   correspondiente).
3. `Storage.__init__` crea los 5 adapters pasándoles `self._conn`.
4. `Storage` mantiene todos sus métodos públicos existentes
   pero ahora delegan al adapter correspondiente.
5. Verificar que `Storage(path).upsert_resource(...)` sigue
   funcionando byte-por-byte (test de no-regresión).

### Fase 2: migrar RunController
6. Cambiar firma de `RunController.__init__` para aceptar
   `runs`, `events`, `policy` (Protocols) en lugar de
   `storage` (Storage concreto).
7. Actualizar los call-sites de `RunController`:
   - tests que construyen `RunController(storage=Storage(path), ...)`
     pasan a `RunController(runs=storage.run_repository(), ...)`.
   - `cli/runner.py` (líneas donde se construye RunController).
8. Tests verdes.

### Fase 3: migrar EventLog
9. Cambiar firma de `EventLog.__init__` para aceptar
   `events: EventStore` y opcionalmente `policy: PolicyStore`.
10. Mover `_migrate()` al `EventStore` adapter (lazy).
11. Tests verdes.

### Fase 4: migrar KnowledgeController
12. Identificar los usos de `storage._conn` en
    `knowledge_controller.py` y `knowledge_invalidator.py`.
13. Añadir métodos al `KnowledgeRepository` o crear un
    `KnowledgeQueryPort` específico.
14. Reemplazar accesos directos por llamadas al Protocol.
15. Tests verdes.

### Fase 5: eliminar escape hatch
16. Remover `@property def conn` de `Storage`.
17. Re-correr suite completa. Cualquier test que use
    `storage.conn` debe haber migrado en fases previas.
18. `ruff format && ruff check`.

### Fase 6: bump + tag
19. `__version__ = "0.14.2"`, commit, tag `v0.14.2`.

### Fase 7: CI verde
20. `pipelinek run` SUCCESS.

## 9. Definition of Done

- AC-1..AC-11 todos PASS.
- 920/920 tests verde.
- coverage ≥ 60% sin regresión.
- `Storage` sigue siendo fachada compatible (AC-11).
- `Storage.conn` eliminado.
- `__version__ = "0.14.2"` + tag `v0.14.2` creado.
- `pipelinek run` SUCCESS.
- Commits atómicos por fase (8-12 commits pequeños).

## 10. Trazabilidad

- Auditoría origen: informe técnico integral 2026-09-26
  (HEAD `b1bb264`); hallazgos #5 y #6 cierran en este WI.
- WI-01: `v0.14.1` release & integration readiness (cerrado).
- Decisión del operador 2026-09-26T13:19Z: "avanza con criterio
  propio sobre lo que priorizas"; WI-02 = ruta B+B híbrida.
- Canon: `external/blueprint-v1/06-controladores.md` §"Storage
  encapsula SQL"; `external/blueprint-v1/09-persistencia.md`
  §"transacciones explícitas"; `external/evolution-v2/plan/`
  no contradice.
- Specs previas: `specs/wi-01-release-readiness.md` (release
  governance), `specs/wi-01-tasks.md`.
- AGENTS.md §4.3 (Protocol para dependencias inyectables) es
  la regla arquitectónica que este WI restaura.