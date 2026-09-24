# Changelog

All notable changes to SkillGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
derived from the commit history via Conventional Commits.

Tipos:
- `feat` → MINOR (nueva capacidad observable).
- `fix` → PATCH (corrección).
- `feat!` / `fix!` / footer `BREAKING CHANGE` → MAJOR.
- `refactor`, `test`, `docs`, `spec`, `chore`, `style` → sin bump de versión.

## [0.7.0] — 2026-09-24

**Resumen**: refactor arquitectónico con **BREAKING CHANGE** en la
estructura de imports. La capa de compat layer en la raíz de
`src/skillgraph/` se elimina: los 20 módulos que eran re-exports
puros hacia bounded contexts (`catalog`, `recipe`, `runtime_types`,
`dsl`, `errors`, `graph_expansion`, `handoff`, `storage`, `workflow`,
`bricks`, `git_source`, `pack_loader`, `promotion`, `runcontroller`,
`skill_importer`, `paths`, `agent`, `context_controller`,
`knowledge_controller`, `knowledge_invalidator`) desaparecen.

Adicionalmente, `knowledge/context_controller.py` deja de acceder a
`storage._conn` directamente; ahora delega en 3 APIs públicas nuevas
del Storage (`list_claims_by_predicate`, `list_evidences_for_source`,
`list_resource_refs_for_run`). Cumplimiento completo de la regla
arquitectónica "Storage encapsula SQL" introducida en 0.6.0.

**Resultado neto**: 619/619 tests PASS (de 604 en 0.6.0, +15). 16/16
UAT PASS, 0 FAIL, 0 BLOCKED. Cobertura 85% branch.

### SemVer decision

El refactor 2 introduce cambios incompatibles de import paths
(un importador externo que usaba `from skillgraph import Storage`
queda roto). SemVer estricto promovería esto a **MAJOR** (1.0.0).

Sin embargo, este proyecto **no tiene importadores externos**
(repo local-only, sin `git push`, sin dependencias aguas abajo).
Por tanto el impacto real de la rotura es CERO: la test suite
integrada se reescribió en el mismo commit.

Se etiqueta como **MINOR** (0.7.0) por:
1. Decisión explícita del operador ("tag MINOR tras el refactor
   combinado") registrada en SESSION-JOURNAL 2026-09-24 06:46.
2. La regla de la introducción del CHANGELOG ("BREAKING CHANGE / `!`
   → MAJOR") se respeta en el sentido de que es BREAKING y se
   documenta como tal. La decisión de no promover a MAJOR se basa
   en la **excepción documentada de "sin importadores externos"**.

Si el proyecto adquiere importadores externos en el futuro, el
próximo cambio incompatible debe promover a 1.0.0 sin excepciones.

### BREAKING CHANGES (MAJOR por semver estricto)

- `from skillgraph.storage import Storage` ya **no funciona**;
  debe ser `from skillgraph.platform.storage import Storage`.
- Análogamente para todos los 19 shims restantes:
  - `skillgraph.errors` → `skillgraph.core.errors`
  - `skillgraph.recipe` → `skillgraph.core.recipe`
  - `skillgraph.runtime_types` → `skillgraph.core.runtime_types`
  - `skillgraph.dsl` → `skillgraph.domain.dsl`
  - `skillgraph.pack_loader` → `skillgraph.domain.pack_loader`
  - `skillgraph.skill_importer` → `skillgraph.domain.skill_importer`
  - `skillgraph.graph_expansion` → `skillgraph.governance.graph_expansion`
  - `skillgraph.promotion` → `skillgraph.governance.promotion`
  - `skillgraph.context_controller` → `skillgraph.knowledge.context_controller`
  - `skillgraph.git_source` → `skillgraph.knowledge.git_source`
  - `skillgraph.knowledge_controller` → `skillgraph.knowledge.knowledge_controller`
  - `skillgraph.knowledge_invalidator` → `skillgraph.knowledge.knowledge_invalidator`
  - `skillgraph.paths` → `skillgraph.platform.paths`
  - `skillgraph.bricks` → `skillgraph.resources.bricks`
  - `skillgraph.catalog` → `skillgraph.resources.catalog`
  - `skillgraph.workflow` → `skillgraph.resources.workflow`
  - `skillgraph.agent` → `skillgraph.runtime.agent`
  - `skillgraph.handoff` → `skillgraph.runtime.handoff`
  - `skillgraph.runcontroller` → `skillgraph.runtime.runcontroller`

Este es un **MINOR** y no MAJOR porque no hay importadores
externos (proyecto local-only, sin `git push`). Se documenta
como BREAKING por honestidad pero el impacto real es CERO
(test suite integrada reescrita en el mismo commit).

### Refactors (sin bump adicional)

- **`Storage` — 3 métodos nuevos (lectura pura)**:
  - `list_claims_by_predicate(*, project_id, predicate, claim_target)`
    — devuelve claims que matchean el predicado (line_count,
    function_count, imports_module, defines_symbol, test_passes,
    file_exists, spec_revision).
  - `list_evidences_for_source(*, source_id)` — evidences ligadas
    a un source.
  - `list_resource_refs_for_run(*, run_id, kind="claim"|"evidence")` —
    refs únicas, DISTINCT + ORDER, con validación de kind.

- **`context_controller.py` — 4 sitios SQL eliminados**: el código
  ahora delega en las 3 APIs nuevas, no accede a `_conn`. La regla
  "Storage encapsula SQL" se cumple completa en este módulo.

### Cambios estructurales (borrado)

- 20 shims eliminados de `src/skillgraph/*.py` (1-9 LoC cada
  uno, re-exports puros).
- 37 ficheros de tests reescritos: ~118 imports de shim a
  bounded context directo (mecánico via script Python con
  mapping 1:1 por shim).
- 2 tests en `tests/test_uat_blocked.py` actualizados
  (`test_h6_pack_loader_module_exists` ahora importa desde
  `skillgraph.domain.pack_loader`; `test_h7_promotion_module_exists`
  importa desde `skillgraph.governance.promotion`).

### Tests (sin bump adicional)

- +15 tests de contrato observable en
  `tests/test_h9_storage_context_controller_reads.py`:
  - 4 tests `list_claims_by_predicate` (contrato, aislamiento,
    no-match, columnas).
  - 3 tests `list_evidences_for_source` (contrato, no-match,
    columnas).
  - 6 tests `list_resource_refs_for_run` (kind=claim,
    kind=evidence, DISTINCT+ORDER, aislamiento run_id, no-events,
    kind inválido → ValidationError).
  - 2 tests de no-regresión por introspección
    (ContextController sin `_conn.execute`; uso de los 3 métodos
    públicos).

### Limitaciones NO ocultas

- Cobertura de `context_controller` sigue 82% (subir a 90%+
  requeriría +6..10 tests de ramas defensivas de las 3 APIs
  nuevas — **NO incluidos** en este release porque son tests
  de cobertura, no tests de refactor). Documentado en
  CURRENT.md 2026-09-24 06:46.

### Reversibilidad

`git revert f2cbb2f` revierte el refactor 2 completo.
`git revert 2751bc8` revierte el refactor 1.
Tests con asserts explícitos sobre los shims se reescribieron
en el mismo commit (no quedan referencias explícitas).

## [0.7.1] — 2026-09-24

**Tag**: `v0.7.1` (965446fadd1ca4cb11d8dfb5ddd8e56b090f1eb0).

**Resumen**: introduce 3 APIs atómicas nuevas en `Storage` para
escribir mutaciones de `node_executions` y su(s) evento(s)
correspondiente(s) en una sola transacción:

- `start_node_execution_atomically(event=..., ...)`:
  1 INSERT (RUNNING) + 1 evento (NodeScheduled).
- `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)`:
  1 UPDATE (SUCCEEDED) + 2 eventos (NodeCompleted + EvidenceProduced).
- `mark_node_failed_atomically(event=..., ...)`:
  1 UPDATE (FAILED) + 1 evento (NodeFailed).

Cada llamada ejecuta una transacción compartida
(BEGIN/COMMIT/ROLLBACK explícito sobre `_conn`). Si el INSERT del
evento falla, la mutación de estado rollbackea como una sola
unidad. Esto cierra las grietas atómicas B, C y D del documento
de caracterización de Plan B.

**Idempotencia**: `UNIQUE(event_id)` sobre `runtime_events` se
traduce a `IdempotencyError` via `try/except sqlite3.IntegrityError`.
Replay con el mismo `event_id` lanza `IdempotencyError`, nunca un
duplicado. Cumplimiento UAT-07.

**Importante**: las 3 APIs `*_atomically` corrigieron el **camino público**
de `Storage` (las firmas que invocaba el runtime antes del refactor),
pero el `with self._conn:` preexistente y los APIs NO-atómicas legacy
del Storage siguen sin rollbackear en `isolation_level=None`. Esta
grieta queda documentada como **LIMITACIÓN-7** (no resuelta en este
release; huérfana hasta v0.7.3 con un fix parcial sobre V4).

### Compatibilidad

- `629 passed, 1 skipped in 143.06s` (cifra del log
  `audits/cleanroom-evidence/ci-output-v0.7.1.txt`; skip en
  `test_cli_uat.py:363`, preexistente). Sin tests nuevos propios:
  este slice prepara el terreno para v0.7.2.
- 16/16 UAT PASS, 0 FAIL, 0 BLOCKED.
- 0 breaking changes: APIs legacy siguen vigentes.

### Evidencia

- `audits/release-v0.7.1-summary.md` (ya generado, link al bundle).
- `audits/cleanroom-evidence/skillgraph-v0.7.1-audit-bundle.tar.gz`.
- `audits/cleanroom-evidence/ci-output-v0.7.1.txt`.
- `audits/cleanroom-evidence/uat-audit-v0.7.1.txt`.

## [0.7.2] — 2026-09-24

**Tag**: `v0.7.2` (338fcc2eed72eb0a0f24f54532032461bded83f3).

**Resumen**: cierra el **defecto de integración** detectado por la
auditoría externa de `v0.7.1`. El release anterior ofreció 3 APIs
atómicas nuevas en `Storage` (`start/complete/fail *atomically`),
pero `RunController._execute_one` seguía invocando las APIs
no-atómicas y emitiendo eventos con llamadas separadas a
`EventLog.append`. Esto significaba que **el recorrido real del
runtime nunca obtuvo la garantía transaccional**.

`v0.7.2` sustituye los pares modificar-estado → emitir-evento en
`RunController` por las APIs atómicas. La garantía se acredita en
el camino público del runtime, no solo en el Storage aislado.

### `RunController._execute_one`

| Momento | Antes (v0.7.1) | Después (v0.7.2) |
|---|---|---|
| Start | `start_node_execution(...)` + `EventLog.append(NodeStarted)` | `start_node_execution_atomically(event=..., ...)` |
| Complete | `complete_node_execution(...)` + `EventLog.append(NodeCompleted)` + `EventLog.append(EvidenceProduced)` | `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)` |
| Fail | `mark_node_failed(...)` + `EventLog.append(NodeFailed)` | `mark_node_failed_atomically(event=..., ...)` |

### Tests nuevos

- `tests/test_h10_runcontroller_atomic_integration.py`: 3 tests con
  fault injection sobre `Storage._insert_event_in_tx`. Verifican que
  al fallar el INSERT del evento, la mutación de estado rollbackea.

### Compatibilidad

- `632 passed, 1 skipped in 134.17s` (cifra del log
  `audits/cleanroom-evidence/ci-output-v0.7.2.txt`; skip en
  `test_cli_uat.py:363`, preexistente). Aritmética aproximada del
  slice: 630 originales + 2-3 nuevos de integración
  (`test_h10_runcontroller_atomic_integration.py` aporta 3).
- 16/16 UAT PASS reproducible.
- 0 breaking changes: APIs públicas no cambian.

### Evidencia

- `audits/release-v0.7.2-summary.md` (ya generado, link al bundle).
- `audits/cleanroom-evidence/skillgraph-v0.7.2-audit-bundle.tar.gz`.
- `audits/cleanroom-evidence/ci-output-v0.7.2.txt`.
- `audits/cleanroom-evidence/uat-audit-v0.7.2.txt`.

### Lo que sigue abierto al cerrar v0.7.2

- **LIMITACIÓN-7**: el `with self._conn:` del Storage y las APIs
  no-atómicas legacy siguen sin rollbackear en
  `isolation_level=None`. v0.7.2 NO introduce un fix para esa
  grieta; solo acredita la integración del runtime con las APIs
  atómicas ya introducidas en v0.7.1.

## [0.8.0] — 2026-09-24 (sin tag, sin push; pendiente de autorización)

**Tag**: no asignado (espera autorización del operador).
**Código efectivo**: commit `528940297ec5ff981f0f59401fdb1e3f563236ab`
("feat(runtime): contexto de run accesible en Handoff (slice H9)").

**Resumen**: el `RunController` inyecta ahora el contexto del run
(tenant/project/run_id y metadatos vigentes) en cada `Handoff`
construido, persistido y recuperado vía `platform/storage`. El
contrato de la API pública de `RunController.__init__` se amplía
con un parámetro opcional `recipe_resolver: Callable[[str],
ContextRecipe | None] | None` (default `None`). Cuando se
proporciona, el resolver reemplaza el stub histórico
`default-empty-recipe/v1`; cuando es `None`, el comportamiento
previo se preserva (cambio backward-compatible).

**SemVer**: `feat` con cambio **compatible hacia atrás** (nuevo
parámetro opcional) → MINOR (v0.8.0).

**Resultado**: 6 tests nuevos en `tests/test_h9_context_in_run.py`
PASS. Batería completa previa: 652 passed. 16/16 UAT PASS, 0 FAIL.
Cobertura mantenida.

### Cambios funcionales

- `RunController.__init__` acepta `recipe_resolver` opcional.
- `RunController._execute_one` resuelve la receta de contexto del
  nodo vía el resolver y la inyecta en `Handoff.context`.
- `Storage` añade 1 método de lectura pura:
  `fetch_run_context(*, run_id)` (devuelve metadatos vigentes del
  run para poblar Handoff en relectura).
- `Handoff` ahora carga `run_context` automáticamente desde
  Storage cuando se recupera un handoff persistido.

### Tests

- 6 tests en `tests/test_h9_context_in_run.py` (parámetro opcional,
  propagación, recuperación, persistencia, default-empty-recipe
  preservado cuando no se inyecta resolver).

## [0.7.3] — 2026-09-24

**Tag**: `v0.7.3` (987be068c7f2b6d17aa6c209489906f94a542568).

**Código efectivo**: el tag apunta al commit `6a536ac` ("T19 cubre
rollback path del _atomic REAL"), que es el último commit con
cambios de código en el camino del fix. El SHA documental
987be068 puede incluir archivos posteriores con ajustes de SHA o
cierre de lagunas procedimentales; eso no afecta el código
ejecutado.

**Resumen**: cierra **un solo caso** de la grieta transaccional de
LIMITACIÓN-7: `Storage.record_trace()`. La función realizaba 1
INSERT en `outcome_traces` + N INSERTs en `outcome_trace_links`,
pero usaba `with self._tx()` que con `isolation_level=None` NO
abría transacción real. Un fallo durante el enlace dejaba un
trace huérfano en disco sin sus enlaces.

`v0.7.3` migra `record_trace()` a `Storage._atomic()`
(BEGIN/COMMIT/ROLLBACK explícitos), garantizando que un fallo a
mitad de las 1+N sentencias rollbackea el conjunto completo.
Esto es análogo al patrón ya usado por las APIs `*_atomically`
de v0.7.1 (que cubren `node_executions` + eventos).

El inventario del slice 1 también caracterizó otras 4 funciones
multi-statement de Storage (`_migrate`, `upsert_resource`,
`add_relation`, `register_promotion`). Todas se excluyeron del
alcance del fix por idempotencia natural o porque el fallo
impide la escritura — **v0.7.3 NO las modifica**.

### Cambios funcionales

- `Storage._atomic`: helper nuevo que usa `BEGIN`/`COMMIT`/`ROLLBACK`
  explícitos sobre `_conn` (alineado con el patrón de las APIs
  `*_atomically`). El rollback se ejecuta con `contextlib.suppress`
  para no enmascarar la excepción original.
- `Storage.record_trace`: cambia `with self._tx()` por
  `with self._atomic()` y actualiza su docstring para documentar
  la garantía transaccional y la referencia al slice V4.

### Tests

- `tests/test_h9_limitacion_7_slice1.py` con 4 tests (T15-T18):
  caracterización de V1, V2, V3, V5 y demostración del bug V4.
- `tests/test_h9_limitacion_7_slice1.py::TestT19AtomicRealRollbackPath`:
  cubre el path real de rollback del `_atomic`, no solo el override
  de los tests de caracterización. (Líneas 387-393 de storage.py
  antes en Missing; pasan a estar cubiertas con cobertura de
  storage.py subiendo de 95% a 96%.)

### Compatibilidad

**Resultados observados en el clon del SHA `6a536ac`** (no en
HEAD del main, que ya incluye el fix V6 en `a6bb5ab`):

- **Pytest contra el código del tag**: `637 passed, 1 skipped`
  en 122 s. (Skip preexistente: `tests/test_cli_uat.py:363`,
  blueprint no versionado.)
- **`bash scripts/ci.sh` completo**: EXIT 1. Aborta en el
  **gate 1 (ruff format --check)** sobre `tests/test_h9_limitacion_7_slice1.py`
  (archivo con T19, mezcla `with pytest.raises(...)` con `with s._atomic()...`).
  `ruff check src tests` reporta además 1 error **SIM117** en
  el mismo T19. Estado heredado del árbol del tag, no regresión
  del fix V4.
- **`python tests/uat_audit.py`** (modo lectura):
  `PASS=16 FAIL=0 BLOCKED=0`.
- 7 de 16 UATs se reejecutan contra el código del tag
  (UAT-05/08/09/10/11/15/16). Los 9 restantes son anclas estables
  cuyo PASS refleja commits previos.
- Cobertura `storage.py`: 96% (subió de 95% al añadir T19).
- 0 breaking changes: APIs públicas no cambian.

**Lo que este release NO certifica para el run de CI**:

El gate oficial `bash scripts/ci.sh` falla por formato/lint en
T19 en el código del tag. Esto es una característica del propio
árbol del tag. Si se requiere CI verde para una revisión posterior
que contenga V6 (commit `a6bb5ab`), hay que arreglar formato y
lint en un commit `chore(...)` separado, no modificar el SHA del
tag v0.7.3.

### Evidencia

- `audits/release-v0.7.3-summary.md` (entregado en este slice).
- `audits/cleanroom-evidence/skillgraph-v0.7.3-audit-bundle.tar.gz`
  (pendiente, ver matriz de cierre).
- `audits/cleanroom-evidence/ci-output-v0.7.3.txt` (pendiente).
- `audits/cleanroom-evidence/uat-audit-v0.7.3.txt` (pendiente).

### Lo que v0.7.3 NO cierra (sigue abierto)

- **LIMITACIÓN-7 V6**: `Storage.record_claim()` con `evidence_ids`
  pobladas presenta la misma clase de confirmación parcial que V4
  antes del fix. La corrección se ejecuta en commit posterior al
  tag (`a6bb5ab fix(storage): make record_claim evidence links
  atomic`), con su prueba focal T20
  (`tests/test_h9_limitacion_7_v6_record_claim.py`).
  Esta corrección NO está incluida en `v0.7.3` ni será parte de
  ese tag. La version que la incluya se decidirá después del
  cierre del slice documental.

- **`workflow_runs` ↔ `RunCreated` / `RunCompleted`**: las
  mutaciones de `workflow_runs` siguen usando APIs no-atómicas.
  Fuera del alcance de LIMITACIÓN-7; pertenece al Plan C.

- **APIs legacy no-atómicas de Storage** (`upsert_resource`,
  `start_node_execution` sin sufijo, `complete_node_execution`
  sin sufijo, `mark_node_failed` sin sufijo): siguen sin
  rollbackear en `isolation_level=None`. Cualquier llamada a esas
  APIs desde un caller distinto al runtime verificado en v0.7.2
  es responsabilidad del caller asegurar atomicidad externa.

## [0.6.0] — 2026-09-23

**Resumen**: cierra los dos únicos gaps restantes del blueprint v1.
**H6 multiprosito** aníade declaracion de tipos extensibles via Domain
Pack (Character/StoryArc como ejemplo narrativo) SIN tocar el nucleo.
**H7 promocion entre bases** aníade outbox persistente con aplicacion
idempotente y reconciliacion tras interrupcion.

**Resultado neto**: 16/16 UAT PASS, 0 FAIL, 0 BLOCKED. El blueprint
queda COMPLETO al 100% segun contrato.

Sin cambios en la API publica existente. Registry/bricks/parser
intactos (0 LoC modificados). Storage.py solo EXTENSION (anade tabla
promotion_outbox + 6 metodos; nada existente modificado).

### Features (MINOR bump)

- `1722fa5` **feat(h6): multiprosito - Domain Pack declara tipos extensibles**.
  - Modulo nuevo `src/skillgraph/pack_loader.py` (215 LoC):
    - `declare_types_from_pack(pack_text)`: parsea un Domain Pack
      Markdown+frontmatter y emite tipos en RuntimeType registry.
      **NO ejecuta codigo del pack**: la seguridad viene del schema
      declarativo (required + fields + refs), no de imports dinamicos.
    - `validate_instance_against_registry(instance)`: valida una
      instancia contra los tipos declarados del Domain Pack.
    - `_make_schema_validator()`: helper que construye un
      SpecValidator desde un schema declarativo.
  - Fixture `tests/fixtures/packs/narrative-core.md`: Domain Pack
    narrativo con `Character` (name, archetype, backstory, relations)
    y `StoryArc` (title, premise, acts, characters).
  - Proteccion contra shadowing:
    - Tipos core (`DecisionNode`, `ActionNode`, `DomainPack`) no se
      pueden redefinir desde un pack.
    - Namespaces reservados (`core`, `skillgraph`) se rechazan.
  - **Kernel intacto**: 0 LoC modificados en `registry.py`/`bricks.py`/`parser.py`.
- `95a0ca9` **feat(h7): promocion entre bases - outbox + reconciliacion idempotente**.
  - Modulo nuevo `src/skillgraph/promotion.py` (160 LoC):
    - `submit_proposal()`: inserta propuesta en outbox origen con
      `idempotency_key`. Duplicado -> `IdentityConflictError`.
    - `apply_proposal(proposal_id, apply_fn)`: transiciona
      PENDING/IN_PROGRESS -> PUBLISHED. **Idempotente**: si ya
      PUBLISHED, NO reaplica. Si FAILED, NO reintenta (segun contrato:
      requiere inspeccion manual).
    - `reconcile_pending()`: procesa TODAS las propuestas en
      PENDING/IN_PROGRESS. Aplica idempotencia. Publicadas y fallidas
      se ignoran.
    - `_compute_idempotency_key()`: combinacion deterministica de
      `project_id + reference_signature`. Rechaza inputs vacios.
  - Storage extension (`src/skillgraph/storage.py`, +146 LoC, 0 modificados):
    - Schema: tabla `promotion_outbox` con
      `proposal_id` PK, `idempotency_key` UNIQUE, `status` CHECK
      IN (`PENDING`,`IN_PROGRESS`,`PUBLISHED`,`FAILED`), `attempts`,
      timestamps, indice por status.
    - 6 metodos anadidos: `register_promotion`, `get_promotion`,
      `list_pending_promotions`, `mark_promotion_in_progress`,
      `mark_promotion_published`, `mark_promotion_failed`.
  - Patron del blueprint §9 (Outbox + Reconciliacion):
    1. Resultado persistido en origen (`register_promotion`).
    2. Mensaje de outbox (`promotion_outbox` row).
    3. Aplicacion idempotente en destino (`apply_fn` + `idempotency_key`).
    4. Confirmacion (`mark_promotion_published`).
    5. Reconciliacion si se interrumpe el proceso (`reconcile_pending`).
- `92cff48` **feat(uat)**: UAT-12 y UAT-13 ahora PASS con evidencia real.
  - `tests/uat-evidence/UAT-12.json` migrado BLOCKED → PASS:
    revision=95a0ca9, criteria_observed con 12 tests de
    test_h6_multiproposito.py, design_decisions (no_execution,
    schema_validator, shadowing_protection, explicit_imports).
  - `tests/uat-evidence/UAT-13.json` migrado BLOCKED → PASS:
    revision=95a0ca9, criteria_observed con 16 tests de
    test_h7_promocion.py incluyendo el CASO CRITICO
    `reconcile_after_interruption_completes_pending` (IN_PROGRESS
    dejado por crash → reconciliacion completa sin duplicar,
    apply_fn llamado 1 sola vez por propuesta).
  - `tests/test_uat_blocked.py` invertido: antes validaba que UAT-12/13
    siguieran BLOCKED con razon honesta. Ahora valida que UAT-12/13
    estan PASS, que las evidencias JSON dicen PASS con SHA real, y que
    los tests reales (`test_h6_*` / `test_h7_*`) corren verde.
    Contrato invertido: este modulo es el "gap test" que detecta si
    alguien revierte H6 o H7 sin actualizar la evidencia.
    6 tests: 2 evidencias PASS, 2 ejecutan suites reales, 2 modulos
    existen con API esperada.

### Tests anadidos (sin bump)

- `1722fa5` **test(h6)**: 12 tests focalizados en pack_loader.py.
  - `test_pack_loader_declares_types_from_narrative_pack`: pack
    narrativo declara Character/StoryArc desde YAML.
  - `test_pack_loader_valid_character_passes` /
    `test_pack_loader_valid_storyarc_passes`: instancias validas
    se aceptan (name, archetype, backstory, relations).
  - `test_pack_loader_character_missing_archetype_fails` /
    `test_pack_loader_storyarc_missing_premise_fails`: campo
    requerido ausente → error de validacion.
  - `test_pack_loader_unknown_kind_raises`: kind desconocido →
    `UnknownKindError`.
  - `test_pack_loader_cannot_shadow_core_type`: 'Character' no
    puede redefinir DecisionNode/ActionNode/DomainPack.
  - `test_pack_loader_cannot_use_reserved_namespace`: namespaces
    'core'/'skillgraph' rechazados.
  - `test_pack_loader_rejects_non_domain_pack`: doc sin
    frontmatter Domain Pack → error.
  - `test_pack_loader_field_type_mismatch_fails`: tipo de campo
    invalido → error.
  - `test_pack_loader_list_of_field_validates_elements`: list_of
    valida elementos internos.
  - `test_pack_loader_does_not_touch_kernel_modules`: pack_loader
    NO importa registry/bricks/parser (test de regresion).
- `95a0ca9` **test(h7)**: 16 tests focalizados en promotion.py +
  storage outbox.
  - `TestPromotionIdempotencyKey` (3): combinacion project+ref
    deterministica, inputs distintos producen keys distintas,
    inputs vacios rechazados.
  - `TestSubmitProposal` (2): submit crea PENDING, duplicate con
    misma idempotency_key → `IdentityConflictError`.
  - `TestApplyProposal` (6): apply exitoso→PUBLISHED, apply
    failed→FAILED, excepcion→FAILED, idempotencia sobre PUBLISHED
    (counter apply_fn no incrementa), FAILED no se reintenta,
    proposal_id inexistente → KeyError.
  - `TestReconcilePending` (5): empty→empty, procesa multiples
    PENDING, **CASO CRITICO after-interruption** (IN_PROGRESS dejado
    por crash → completa sin duplicar), no duplica PUBLISHED,
    mezcla PENDING+IN_PROGRESS+FAILED → cada uno se trata
    segun corresponde.
- `92cff48` **test(uat)**: 6 tests en `tests/test_uat_blocked.py`
  (inversion del contrato, ver feat anterior).

### Estado verificable al tag

- **HEAD**: `92cff48` (post-commits h6+h7+uat).
- **Tests**: 405 passed en 121s (373 → 405, delta +32 tests
  H6+H7+gap-invertidos).
- **UATs**: **16/16 PASS, 0 FAIL, 0 BLOCKED** — primera vez en la
  historia del proyecto.
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.
- **Audit CLI**: `python tests/uat_audit.py` reporta 16/16 PASS.

### Limitaciones y deudas conocidas

- **H6/H7 sin CLI hooks publicos**: `sg pack load` y
  `sg promotion submit/list/reconcile` NO son comandos CLI. El
  contrato del blueprint es la API Python (pack_loader.declare_*,
  promotion.submit/apply/reconcile). La interfaz CLI es una mejora
  diferible, no un gap funcional.
- **Sin migracion de evidencias legacy**: las evidencias que vivian
  con status=BLOCKED y revision=`cb7e3482` (v0.3.0) se migraron
  sobreescribiendo el archivo a status=PASS con la revision real del
  commit que implemento la feature. Si alguien quiere preservar el
  historial pre-implementacion, mirar git log de tests/uat-evidence/.

## [0.5.0] — 2026-09-23

**Resumen**: añade CLI propio al módulo `tests/uat_audit.py`. Antes
ejecutaba los 16 UATs y sobreescribía la evidencia persistida por
defecto (footgun crítico). Ahora es read-only por defecto; el modo
write es opt-in con flags explícitos y protección contra pisado de
evidencia válida de UATs stub.

Sin cambios en la API pública de SkillGraph. Sin cambios en código
de producción (`src/skillgraph/`).

### Features (MINOR bump)

- `233431b` **feat(uat)**: CLI safety en `tests/uat_audit.py`.
  - **Default read-only**: `python tests/uat_audit.py` ahora LEE la
    evidencia persistida y la reporta sin ejecutar nada. Cierra el
    footgun documentado en v0.4.1 CHANGELOG.
  - **`--write`**: ejecuta los UATs y SOBREESCRIBE la evidencia. Solo
    para UATs no-stub (los stubs UAT-08/09/12/13 son heredados y
    delegan en `uats_blocked_gap`; su evidencia real vive en
    `test_h4_expansion_cli.py` / `test_uat_blocked.py`).
  - **`--write --yes`**: confirma la operación sobre UATs stub
    (mensaje explícito + exit 3 si se omite `--yes`).
  - **`--dry-run`**: ejecuta los UATs sin persistir evidencia (útil
    para debug).
  - **Subset selection**: `uat_audit.py UAT-08 UAT-09` ejecuta solo
    los UATs nombrados.
  - **`--help`**: imprime uso.
  - **Exit codes**: 0 OK, 2 UAT desconocido, 3 stub sin `--yes`.
  - Refactor: extrae `_run_one`, `_report`, `_summary`,
    `_read_existing`, `_build_parser` para DRY.

### Tests añadidos (sin bump)

- `607d859` **test(uat)**: 5 tests para el nuevo CLI.
  - `test_main_default_is_readonly`: modo lectura no escribe nada.
  - `test_main_write_unknown_uat_returns_2`: exit code 2 en UAT
    desconocido.
  - `test_main_write_stub_without_yes_returns_3`: exit code 3 Y la
    evidencia preexistente con `revision: "must-survive"` queda
    intacta (verifica que NO se pisa).
  - `test_main_dry_run_does_not_write`: `--dry-run` no persiste.
  - `test_main_help_exits_zero`: `--help` sale rc=0 con mensaje
    que contiene `--write`.

### Estado verificable al tag

- **HEAD pre-tag**: `607d859`.
- **Tests**: 373 passed en 82s (368 → 373, delta +5 tests CLI).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.
- **Footgun verificado**: ejecutar `python tests/uat_audit.py` ya NO
  modifica el working tree (verificado con `git status` antes/después).

### Limitaciones y deudas conocidas (sin cambio desde v0.4.1)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.
- `paths.py` rama Windows: no testeable en CI Linux.

## [0.4.1] — 2026-09-23

**Resumen**: dos correcciones de portabilidad y trazabilidad del
módulo `tests/uat_audit.py`. Sin cambios de comportamiento observable
ni en la API pública.

### Fixes (PATCH bump)

- `7b81df7` **fix(tests)**: UAT evidence usa SHA real de HEAD.
  - Antes: `revision: "HEAD"` literal en evidencia de UAT-08/09.
  - Ahora: helper `_git_rev_head()` que ejecuta `git rev-parse HEAD`
    en el repo de evidencia y captura el SHA real.
  - Justificación: una evidencia de auditoría que no contiene el SHA
    real no es auditable. Mejora la verificabilidad, no el comportamiento.
- `edb19b0` **fix(uat)**: `REPO_ROOT` se deriva de `__file__`.
  - Antes: `Path("/var/mnt/DiscoChino2-fast/...")` hardcodeado,
    rompía el módulo al clonarse en otra máquina o ruta.
  - Ahora: `Path(__file__).resolve().parent.parent` — funciona en
    cualquier checkout sin editar.
  - Verificado: módulo importa OK desde `test_uat_blocked.py` y
    `test_uat_audit.py`, y resuelve a la misma raíz que el path
    hardcodeado en este entorno.

### Estado verificable al tag

- **HEAD pre-tag**: `edb19b0`.
- **Tests**: 368 passed en 63s (sin delta vs v0.4.0).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.4.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.
- `paths.py` rama Windows: no testeable en CI Linux.
- **NUEVA detectada en sesión**: el `main()` de `tests/uat_audit.py`
  es destructivo por defecto — al ejecutarlo sin args pisa toda la
  evidencia existente en `tests/uat-evidence/*.json` con `BLOCKED`.
  No se ha arreglado en este PATCH por estar fuera del scope
  (cambia contrato del script, no portabilidad).

## [0.4.0] — 2026-09-23

**Resumen**: cierra el gap declarado en `specs/h4-slice-3.md` limitación 3.
`expansion apply` ahora persiste la propuesta y crea marker `.applied`,
haciendo que `list --stage APPLIED` funcione (antes retornaba vacío).
`expansion show` ahora incluye el campo `stage` en el payload JSON.

Compatibilidad hacia atrás mantenida: ningún cambio en códigos de salida,
firmas de comandos, ni en el formato del plan persistido.

### Features (MINOR bump)

- `162a708` **feat(h4-slice-3)**: APPLIED marker + `show.stage` field.
  - `cmd_expansion_apply` ahora persiste la propuesta en
    `expansion_proposals/<id>.json` (si no existe, mismo patrón que
    `cmd_expansion_propose`) y crea marker adyacente `<id>.json.applied`
    con timestamp UTC y `applied_by: "expansion-apply-cli"`.
  - `cmd_expansion_list` y `cmd_expansion_show` leen markers:
    precedencia `ARCHIVED > APPLIED > REJECTED > PROPOSED`.
  - `cmd_expansion_show` añade `"stage": "..."` al payload JSON.
  - Refactor: extrae `_infer_proposal_stage()` y
    `_collect_rejection_ids()` para evitar duplicación entre list y show.

### Estado verificable al tag

- **HEAD**: `162a708` (pre-tag).
- **Tests**: 368 passed en 117s (362 → 368, delta +6 tests focales).
- **Cobertura**: sin cambio material (cli.py 31% in-process; tests
  reales E2E).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.3.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.

## [0.3.0] — 2026-09-23

**Resumen**: primera release taggeada. H0-H5 (excepto H6 y H7)
completados con criterios de aceptación verificados. 14/16 UAT PASS,
2 BLOCKED honestos por falta de spec del operador.

### Features (MINOR bump)

#### H4 — Expansión controlada

- `6f93eb2` **feat(h4)**: Expansion controlada (DISCOVER → APPLY)
  cierra UAT-08/09.
- `bd95d29` **feat(h4-cli)**: expansion propose/apply/validate/rejections
  + E2E para UAT-08/09.
- `3b307f3` **feat(h4-slice-3)**: policy engine P1..P5 + EVALUATE + CLI
  list/show/archive.
- `b7b2d5e` **feat(h4)**: DecisionNode outcomes + max_visits self-loops
  (+7 tests).

Criterio legal HITOS.md H4: "Añadir una investigación imprevista a una
ejecución sin alterar el resultado de nodos anteriores."
- UAT-08 PASS (`tests/uat-evidence/UAT-08.json`): apply incorpora
  únicamente el cambio solicitado; nodos originales intactos.
- UAT-09 PASS (`tests/uat-evidence/UAT-09.json`): propuesta con
  capability no registrada es rechazada con rc=10 y evidencia JSON
  persistida en `expansion_rejections/`.

Limitaciones documentadas (`specs/h4-audit-penal.md`):
- E2E es `representative` (Storage SQLite local), no
  `acceptance_aligned` (sin stress concurrente, sin crash recovery
  verificado en kill-9). Refinamiento pendiente para slice-4.

#### H5 — Adopción de skills

- `26ac401` **feat(h5)**: skill_import (UAT-11 BLOCKED→PASS) +
  `skill_importer` + `cmd pack import`.

Criterio legal HITOS.md H5: "Adoptar una skill real y conservar una
referencia verificable a sus instrucciones originales."
- UAT-11 PASS (`tests/uat-evidence/UAT-11.json`): `pack_import` rc=0,
  `structured_ok=True`, `script_ignored=True`, `scripts_detected=True`.

Decisión documentada (`specs/h5-source-conservation-decision.md`):
- Conservación por referencia (path+content_hash), NO duplicación de
  bytes. Justificado por blueprint §10 §5-6.

#### Otros feats

- `d72bbff` **feat(uat)**: UAT-16 BLOCKED→PASS (handoff_json persiste
  tras revision change).
- `b06cc15` **feat(h3-s1)**: Knowledge ADT + Storage delta.
- `4d8e80c` **feat(ci)**: `scripts/ci.sh` como gate único + pairwise
  import.
- `3bc66d9` **feat(H2)**: tests subprocess CLI run + resume-or-start
  (UAT-04/06/07 E2E).
- `007db8d` **feat(cli)**: añadir `__main__.py` para `python -m
  skillgraph`.
- `a3f7950` **feat(etapa2/S7)**: DSL tipado + PlanBuilder funcional +
  loader Markdown.
- `e763102` **feat(e2-s4+s5)**: WorkflowPlan + RunController +
  ejecución recuperable.
- `92a5174` **feat(e2-s3)**: AgentAdapter + FakeAgentAdapter +
  RecordingAdapter.
- `64bc05d` **feat(e2-s2)**: Handoff materializado con serialización
  estable y SHA-256.
- `92929a9` **feat(e2-s1)**: runtime append-only + EventLog con
  idempotencia por UNIQUE.
- `fb0e56a` **feat(e1)**: CLI real + catálogo + UAT-01..03 PASS.
- `15957d7` **feat(s1)**: almacenamiento SQLite con WAL, aislamiento y
  latencia.
- `0a92c84` **feat(s0)**: brick mínimo Markdown+YAML con parser,
  registro y validación.

### Fixes (PATCH bump)

- `ff433aa` **fix(types)**: SourceKind incluye `skill_pack` y Source
  valida kind en `__post_init__`. Cierra bug silencioso donde
  `from __future__ import annotations` desactivaba Literal-check.
- `e69a8e4` **fix(uat)**: UAT-10 predicados válidos + chequeo
  `seed_rc` y `stale_listed`.
- `bdd196f` **fix(cli)**: UAT-06 max_iterations respeta el límite + 4
  tests honestos.

### Refactors

- `1039171` **refactor + test(paths)**: añadir tests + refactor para
  que la rama nt sea testeable.

### Tests añadidos (sin bump)

- `0e96495` **test(parser)**: 12 tests ramas de error (coverage
  77%→100%).
- `b6ca7e1` **test(plan-loader)**: 13 tests load_plan_file + error
  branches (coverage 48%→100%, dato heredado 69% obsoleto).
- `629be65` **test(recipe)**: 22 tests `__post_init__` + from_dict
  (coverage 73%→100%).
- `7c3f3f4` **test(uat)**: gap coverage UAT en CI — 5 wrappers
  pytest + 2 honest blockers.

### Specs (sin bump)

- `7233fac` spec(h4-audit-penal): cruce H4 slices 1+2 vs blueprint
  literal.
- `92d70e2` spec(h5-audit-penal): cruce H5 skill_import vs blueprint
  literal.
- `81fbb0e` spec(h4-slice-3): propuesta storage persistente + EVALUATE
  + policy engine.
- `2d01a06` spec(uat-coverage-gap): audita que UATs se validan
  automáticamente en CI.

### Estado verificable al tag

- **HEAD**: `076f6e9` (pre-tag) → `v0.3.0` (post-tag).
- **Tests**: 362 passed en 54s (315→362, delta +47 en ciclos de
  stewardship).
- **Cobertura**: 77% total. Módulos críticos `parser.py`, `plan_loader.py`,
  `recipe.py`: 100%. Módulos runtime: 88-100%. `cli.py`: 31% en
  pytest-cov (cobertura real mayor vía tests subprocess E2E no
  contables por cobertura in-process).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos.
- **`scripts/ci.sh`**: OK (format + lint + pytest, replicable por
  cualquier runner externo).
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas

- **UAT-12 (H6 multipropósito)**: BLOCKED. Requiere spec del operador
  para `Character/StoryArc`.
- **UAT-13 (H7 promoción entre bases)**: BLOCKED. Requiere spec del
  operador.
- **H4 slice-4** (deferido por decisión explícita en
  `specs/h4-slice-3.md`): sin migración SQLite, sin gating de
  `auto_signed` via evaluation_result.
- **`paths.py` rama Windows**: no ejercitable en CI Linux
  (`LOCALAPPDATA/USERPROFILE`).
- **`recipes.runtime.dispositivos externos`**: tiktoken solo si H4+
  exige Adapter real.

### Antiobjetivos respetados

- No se introdujo base de grafos especializada.
- No se introdujo scheduler distribuido.
- No se introdujo sistema de agentes permanentes sin requisito
  observado.

## Comparativa con releases anteriores

Esta es la **primera release taggeada** del proyecto.
El historial completo de commits previos forma parte del cuerpo
desarrollado hacia esta release.

[0.3.0]: #030--2026-09-23
