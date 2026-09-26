# WI-02b — Tasks atómicas (EventLog + KnowledgeController + escape hatch)

> Complemento de `specs/wi-02-persistence-ports.md`. Cubre Fases 3, 4, 5
> del WI-02 §8. Las Fases 1-2 ya se cerraron en WI-02a (`v0.14.2`,
> commits `87d56ba` + `4381591` + `da95923`).
>
> **WorkItem**: WI-02b (last slice of WI-02).
> **Goal**: cerrar las 3 violaciones restantes: `EventLog(conn)`,
> `KnowledgeController.storage._conn`, y `Storage.conn` como `@property`.

## Tareas (5 commits, cada uno cierra un AC verificable)

### T-12 · protocol: ampliar `EventStore` y `KnowledgeRepository`
- **Cierra**: base para AC-3, AC-5.
- **Cambios**:
  - `src/skillgraph/platform/ports/__init__.py`:
    - Añadir `EventStore.ensure_schema() -> None` (idempotente).
    - Añadir `EventStore.fetch_event_raw(*, event_id: str) -> Any | None`
      (para el caso de `RuntimeEventLog` si lo necesita; si no, se omite
      tras verificar que no se usa).
    - Ampliar `KnowledgeRepository` con:
      - `find_entity(tenant_id, project_id, kind, stable_key) -> Entity | None`
      - `source_exists_anywhere(source_id) -> bool` (cross-tenant detection).
      - `list_claims_for_subject(tenant_id, project_id, subject_entity_id) -> list[Claim]`
        que pre-cargue `evidence_ids` en una sola query (sin N+1).
  - Verificar que `Storage` sigue cumpliendo el Protocol estructuralmente
    (test rápido con `hasattr` por cada método nuevo).
- **Test (TDD)**: extender `tests/test_persistence_ports.py` con
  asserts de presencia de los nuevos métodos en `Storage`. ROJO primero.
- **AC parcial**: sienta las bases. NO cierra AC-3, AC-5 ni AC-4
  todavía (solo el Protocol).

### T-13 · refactor(runtime): EventLog acepta EventStore (cierra AC-3)
- **Cierra**: AC-3 del WI-02.
- **Cambios**:
  - `src/skillgraph/runtime/engine.py`:
    - `EventLog.__init__(self, events: EventStore, *, policy_resolver=None)`
      (antes `conn: sqlite3.Connection`).
    - Eliminar `self._conn = conn` y todo uso interno.
    - `_migrate()` se sustituye por `events.ensure_schema()` (llamado
      una vez al final de `__init__`).
    - `append(event: RuntimeEvent)` se reescribe para delegar a
      `events.record_event(...)` con los kwargs correspondientes.
    - Eliminar `_tx()` context manager (ya no hay transacción local;
      la atomicidad es responsabilidad del `EventStore` adapter si
      es necesaria).
  - **`grep "sqlite3.Connection" src/skillgraph/runtime/engine.py` solo
    debería aparecer en `_SCHEMA_SQL`** (AC-3 verbatim).
- **Test (TDD)**: `tests/test_runtime_events.py` y `tests/test_redaction.py`
  deben usar la nueva firma. `EventLog(storage.event_store(), policy_resolver=...)`
  en lugar de `EventLog(conn, ...)`.
- **AC**: AC-3 PASS.

### T-14 · refactor(runtime): RunController usa EventStore explícito
- **Cierra**: parte de la integración T-13 + RunController ya no toca `.conn`.
- **Cambios**:
  - `src/skillgraph/runtime/runcontroller.py:283`: cambiar
    `events.conn` (escape hatch actual) por paso explícito del
    `EventStore` que `RunController` ya recibe por constructor.
  - Eliminar el comentario WI-02a ("`EventLog` aún consume
    `sqlite3.Connection` directamente; la migración a `EventStore`
    queda en WI-02b").
- **AC**: prepara AC-4 (escape hatch removal).

### T-15 · refactor(knowledge): KC y KI usan KnowledgeRepository Protocol (cierra AC-5)
- **Cierra**: AC-5 del WI-02.
- **Cambios**:
  - `src/skillgraph/knowledge/knowledge_controller.py`:
    - `find_entity()` → `self.knowledge.find_entity(...)` (Protocol).
    - Site línea ~408 (cross-tenant detection) →
      `self.knowledge.source_exists_anywhere(source_id)`.
    - `list_claims_for_subject()` →
      `self.knowledge.list_claims_for_subject(...)` (una sola query,
      no dos separadas).
  - `src/skillgraph/knowledge/knowledge_invalidator.py`:
    - 5 sitios `_conn.execute` se reemplazan por métodos del Protocol
      (los necesarios se añaden al Protocol en T-12; los que no
      encajan, se añade un `KnowledgeQueryPort` específico).
  - `KnowledgeController.__init__` ahora recibe
    `knowledge: KnowledgeRepository` además del resto.
- **Test (TDD)**: tests KC/KI ya verdes deben seguir verdes tras la
  migración; tests nuevos con un stub fake `KnowledgeRepository`
  para verificar que NO se accede a `_conn`.
- **`grep "_conn" src/skillgraph/knowledge/knowledge_controller.py`
  debe dar exit 1** (AC-5 verbatim).
- **AC**: AC-5 PASS.

### T-16 · refactor(platform): eliminar `Storage.conn` escape hatch (cierra AC-4)
- **Cierra**: AC-4 del WI-02.
- **Cambios**:
  - `src/skillgraph/platform/storage.py:371-386`: eliminar `@property def
    conn`. `_conn` sigue siendo privado (sigue siendo necesario para
    los adapters internos).
  - Verificar que NINGÚN código en `src/` ni `tests/` accede a
    `storage.conn` (los call sites habrían migrado en T-13/T-14/T-15).
    Si queda alguno, falla y se migra en este mismo commit
    (estrictamente: este commit puede contener fixes de call sites
    **del propio Storage.conn**; los de `_conn` ya se trataron en T-15).
- **`grep "@property\|def conn" src/skillgraph/platform/storage.py`
  no debe exponer `conn`**.
- **AC**: AC-4 PASS.

### T-17 · docs(release): bump + tag v0.14.3 (cierra AC-10)
- **Cierra**: AC-10 (bump + tag). Reordena para dejar la release al final.
- **Cambios**:
  - `__version__` bump de `"0.14.2"` → `"0.14.3.dev0"` en commit work
    (`CHANGELOG` + `CURRENT` + `STATE` + `__init__.py`).
  - Commit puro + commit bump final `"0.14.3"` + tag anotado `v0.14.3`.
- **AC**: AC-10 PASS (bump + tag).

## Definition of Done (WI-02 acumulado: a + b)

- AC-1..AC-11 todos PASS.
- Tests: **927/927 → 933/933 PASS** (los +6 son tests nuevos de
  ampliación de Protocols en T-12, migración EventLog, KC/KI
  independiente de _conn).
- coverage ≥ 60% sin regresión.
- `Storage` sigue siendo fachada compatible (AC-11).
- `Storage.conn` eliminado (escape hatch cerrado).
- `__version__ = "0.14.3"` + tag `v0.14.3` creado.
- `pipelinek run` SUCCESS.
- Commits atómicos (5 commits work + 2 commits bump/tag = 7 total).

## Trazabilidad

- Spec integral: `specs/wi-02-persistence-ports.md` (Fases 3-5, AC-3/4/5).
- WI-02a (cerrado en `v0.14.2`): T-01..T-11.
- WI-01 (cerrado en `v0.14.1`): governance release.
- Pendiente push a origin (waiver del WI-01 sin revocar).
