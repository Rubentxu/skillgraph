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

## [Unreleased — evolution-v2 (H0..H15)] — 2026-09-25

**Resumen**: roadmap `external/evolution-v2/plan/ROADMAP.md` cerrado al 100%. 5 nuevos modulos, 58 tests UAT-EVO nuevos (suite 830/830 PASS). NO bump de release: los workitems añaden superficie de conocimiento/governance sin capacidad observable nueva a nivel de API CLI (no hay comandos ni flags nuevos).

### Added (evolution-v2)

- **H0–H1 (foundation)**: cobertura del recorrido real y caracterización de gates (audits/h10-recorrido-real-2026-09-25.md).
- **H11 — Conocimiento tipado reutilizable** (`skillgraph.knowledge.file_signature`): `FileSignature`, `SignatureProcedencia`, `SignatureVigencia`, `ExtractionState`. Pure extractor regex_def. Persistencia via `Evidence(kind='file_signature')` reusando tabla existente.
- **H12 — Scopes y consultas composables** (`skillgraph.knowledge.file_scope`): `FileScope` Literal, `ScopeQuery`, `ScopeResolution`, `AggregatedSignatures`, `aggregate_signatures()` puro. Aislamiento E2E-08 estricto.
- **H13 — Handoff experto desde consultas** (`skillgraph.knowledge.file_handoff`): `ScopeAwareRecipe` (composicion sobre `ContextRecipe`), `CoverageManifest`, `HandoffBlockedError`, `compile_handoff_from_scopes()`. Manifest como representación canónica; handoff compila OK con `obligatory=()`.
- **H14 — Evidencia operativa temporal** (`skillgraph.governance.receipts`): `ValidationReceipt` (frozen, verdict Literal), `is_receipt_applicable()` puro, `record_validation_receipt()`, `list_applicable_receipts()`. Persistencia via `Evidence(kind='validation_receipt')`.
- **H15 — Evaluación y automejora acotada** (`skillgraph.governance.improvement`): `ImprovementCandidate` + `ImprovementKind` Literal cerrada, `detect_redundant_extraction()`, `localize_omission()`, `compare_recipes()`, `promote_candidate()` exige `human_approved=True` (UAT-EVO-18 sin autocertificacion, `SelfCertificationBlockedError` tipado), `rollback_candidate()` con `RollbackPolicy` Literal.

### Notes

- Persistencia H11–H15: ninguna tabla nueva. Todos los nuevos tipos se almacenan via `Evidence(kind=...)` reusando la tabla `evidence` existente (regla AGENTS §1.5).
- ADT cerradas: `ExtractionState`, `FileScope`, `ImprovementKind`, `RollbackPolicy`, `ReceiptVerdict` via `Literal[...]` (regla AGENTS §2.1).
- Errores tipados: `HandoffBlockedError`, `SelfCertificationBlockedError` (subclases de `SkillGraphError`, regla AGENTS §1.2).
- Tests UAT-EVO: 4 + 12 + 8 + 8 + 9 + 9 = 50 nuevos (H0–H1 + H11–H15).

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

## [0.8.1] — 2026-09-24 (PATCH, refactor)

**Tag**: `v0.8.1` (`ab7b5171aec5524320c67e44ad511ae78b70a7d1`).

**Código efectivo**: commit `ab7b517` ("refactor(runtime): helper
_fail_node_with(exc=...) en RunController").

**Resumen**: el método `_execute_one` repite el patrón
`except X as exc: self._mark_node_failed(... error=f"{type(exc).__name__}: {exc}")`
en dos ramas (compilación de handoff y adaptador). Esta versión
centraliza ese formato en un helper privado `_fail_node_with(exc=...)`
que delega en `_mark_node_failed`. La tercera rama (outcome no
declarado) usa una firma distinta (incluye `outcome=`) y se conserva
como llamada directa.

**SemVer**: refactor puro → PATCH (v0.8.1). Sin cambio de
comportamiento observable.

**Resultado**: 652/652 tests PASS; 16/16 UAT PASS, 0 FAIL. Ruff
limpio. Cobertura mantenida.

### Cambios funcionales

Ninguno.

### Refactor (sin bump adicional)

- `RunController._fail_node_with(*, tenant_id, project_id, run_id,
  node_execution_id, node_name, exc)` añadido como helper privado.
- `RunController._execute_one`: 2 ramas `except` pasan a usar
  `_fail_node_with(exc=exc)` en vez de construir el string de error
  y llamar a `_mark_node_failed` directamente. La rama de outcome
  no declarado queda igual.

## [Sin bump] — 2026-09-24 (refactor interno)

**Tag**: ninguno. **Código efectivo**: commit `ea54021`
("refactor(runtime): helpers _transition_run_state_with_event y
_is_budget_exhausted").

**Resumen**: deuda técnica pendiente del refactor previo
(`v0.8.1`). `reconcile_run` tenía 122 LoC y tres ramas con el patrón
`EventBuilder(...).run_completed(...) + transition_run_state_atomically`,
más un bloque de 14 LoC para detectar budget de visitas agotado.
Esta versión extrae dos helpers privados en `RunController`:

- `_transition_run_state_with_event(*, tenant_id, project_id, run_id,
  state, current_node, at=None)`: construye el `RunCompleted` y
  llama a `transition_run_state_atomically` en una sola TX.
  Reemplaza las 3 ramas de terminación del run.
- `_is_budget_exhausted(plan, tenant_id, project_id, run_id,
  prev_current)`: detecta H4 (self-loop + max_visits + ejecuciones
  acumuladas >= max_visits).

**SemVer**: refactor puro (sin cambio de contrato público, sin fix,
sin feat). Regla "`refactor` → sin bump de versión" del CHANGELOG.
No se publica tag.

**Resultado**: 659/659 tests PASS (+4 nuevos sobre el helper).
Ruff limpio. Cobertura `runcontroller.py`: 84% → 95%
(umbral ≥90% AGENTS.md core). `reconcile_run`: 122 → 100 LoC.

### Continuación del refactor (aee5cd5)

Misma rama, sin bump adicional. Extrae dos helpers privados
adicionales en `RunController`:

- `_open_node_execution(*, tenant_id, project_id, run_id, node_name,
  attempt) -> tuple[EventBuilder, str]`: emite `NodeScheduled` y crea
  la `NodeExecution` RUNNING atómica. Devuelve `(events,
  node_execution_id)`.
- `_finalize_node_success(*, events, run_id, node_execution_id,
  result, context_hash)`: emite `NodeCompleted` + `EvidenceProduced`
  y delega el UPDATE a SUCCEEDED atómico.
- `_fail_node_with` ahora retorna `bool` (`False`); permite
  `return self._fail_node_with(...)` sin repetir el literal.

`_execute_one` colapsa 162 → 124 LoC. El orquestador queda como
secuencia explícita: bootstrap → compilar handoff → invocar adapter →
validar outcome → cerrar. Cobertura mantenida 95%.


## [0.9.0] — 2026-09-24 (MINOR, cancel + refactors)

**Tag**: `v0.9.0` (`a4d749e9fefad551e4406aa7305e32aac224df08`).

**Resumen**: S1 del roadmap Etapa 7 (presupuestos y cancelación):
el operador puede detener un Run en curso sin esperar al reconcile
completo. Nueva API `RunController.cancel_run` + nuevo subcomando
CLI `sg runs cancel <project> <run-id>`. Consolidación de los
refactors acumulados sobre `RunController` (helpers privados
para extraer las ramas duplicadas de terminación, transición de
estado y bootstrap/ejecución de nodos).

### Cambios funcionales (MINOR)

- **`RunController.cancel_run(*, tenant_id, project_id, run_id)`**:
  transiciona el Run a `CANCELLED` y emite `RunCompleted` en una
  sola TX (reutiliza `_transition_run_state_with_event`).
  - Run no existe -> `NotFoundError` (delegado en `Storage.load_run`).
  - Run ya terminal -> `ValidationError` (no idempotente).
  - NodeExecutions RUNNING se quedan: la cancelación es a nivel
    de Run, no de nodo. El siguiente `reconcile_run` no las
    re-ejecuta (test `test_reconcile_after_cancel_is_noop`).
- **CLI `sg runs cancel <project> <run-id>`**: subcomando nuevo
  bajo `runs` (paralelo a `run`). Exit code 0 + `state=CANCELLED`
  en stdout. Errores tipados -> `EXIT_DOMAIN` (10).

### Refactors acumulados (sin bump adicional)

Consolidación de la deuda técnica detectada sobre `RunController`
en `v0.8.1`:

- `RunController._transition_run_state_with_event(*, ...)`:
  helper que centraliza las 3 ramas de terminación del Run
  (FAILED por nodo, FAILED por budget exhausted, COMPLETED
  normal, ahora también CANCELLED).
- `RunController._is_budget_exhausted(plan, ...)`:
  detección de H4 (self-loop + max_visits + ejecuciones
  acumuladas >= max_visits).
- `RunController._open_node_execution(*, ...)`:
  bootstrap del nodo: emite `NodeScheduled` y crea la
  NodeExecution RUNNING atómica.
- `RunController._finalize_node_success(*, ...)`:
  cierre exitoso: emite `NodeCompleted` + `EvidenceProduced`
  y delega el UPDATE a SUCCEEDED atómico.
- `RunController._fail_node_with(*, exc=...) -> bool`:
  devuelve `False` para permitir
  `return self._fail_node_with(...)` sin literal.
- `_execute_one`: 162 → 124 LoC.
- `reconcile_run`: 122 → 100 LoC.

### Tests

- 5 tests unitarios `tests/test_runcontroller.py::TestCancelRun`:
  estado persistido, evento emitido, idempotencia, run terminal
  rechazado, reconcile post-cancel no-op, run desconocido.
- 2 tests subprocess `tests/test_cli_runs_cancel.py`:
  cancel vía CLI exit code 0 + persistencia + evento; cancel
  de run inexistente -> exit code != 0.
- 4 tests del helper `_is_budget_exhausted`
  (`tests/test_h4_cycles_and_decision.py::TestIsBudgetExhaustedHelper`).
- UAT-08/09 regenerados sobre `a4d749e`.

### Resultado

- **Batería completa**: 666 passed (de 652 en v0.8.0).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 95% (umbral ≥90% AGENTS.md core).

### SemVer

`feat` (capacidad observable nueva: cancel programático y CLI) →
**MINOR** → `v0.9.0`. Los refactors van consolidados en la
misma release con la regla "`refactor` → sin bump" relajada
porque la `feat` ya justifica MINOR.

## [0.10.0] — 2026-09-24 (MINOR, list + show runs)

**Tag**: `v0.10.0` (`c6963f072d6b6e51ab569e396de688633aed2fb2`).

**Resumen**: S2 del roadmap Etapa 7 (gestion del ciclo de vida de
Runs): complementa el S1 (`v0.9.0`, cancel_run) con inspeccion
read-only. El operador ahora puede listar Runs existentes con
`sg runs list` y ver el snapshot de un Run concreto con
`sg runs show`, sin abrir SQLite directamente.

### Cambios funcionales (MINOR)

- **`Storage.list_runs(*, tenant_id, project_id, state=None, limit=50)`**:
  SELECT con filtro opcional por estado, ordenado por `rowid DESC`
  (mas reciente primero; monotono, independiente de la resolucion
  de 1 segundo de `datetime('now')` en SQLite).
- **`Storage.get_run(*, tenant_id, project_id, run_id)`**:
  fila cruda de un Run; `NotFoundError` si no existe.
- **`RunController.list_runs(...)`**: tupla inmutable de
  `RunSnapshot` ordenados por mas reciente primero. Filtra por
  estado opcional.
- **`RunController.show_run(...)`**: snapshot de un Run por id;
  `NotFoundError` si no existe. Delega en `Storage.get_run`.
- **`RunController._count_events(...)`**: helper privado read-only
  para contar eventos de un Run (usado por list/show).
- **CLI `sg runs list <project> [--state S] [--limit N]`**:
  salida CSV-like con columnas estables (run_id, state,
  current_node, executed, events). '(sin runs)' si vacio.
- **CLI `sg runs show <project> <run-id>`**: salida key=value
  (run_id, state, current_node, executed_nodes, events_emitted).
  Parseable con `awk`/`cut`.
- **`_open_project_storage(args)`**: helper compartido por
  `cmd_runs_list`/`show`/`cancel` (DRY: resolver proyecto +
  abrir Storage en una sola funcion).

### Tests

- 6 tests unitarios `tests/test_runcontroller.py::TestListAndShowRun`:
  vacio, orden, limit, filtro por estado, snapshot, NotFoundError.
- 3 tests subprocess CLI `tests/test_cli_runs_inspect.py`:
  list vacio, list orden, show snapshot.
- Archivo renombrado: `test_cli_runs_cancel.py` ->
  `test_cli_runs_inspect.py` (cubre cancel + list + show).
- UAT-08/09 regenerados sobre `c6963f0`.

### Resultado

- **Bateria completa**: 675 passed (de 666 en v0.9.0, +9 nuevos).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 95% mantenida.

### SemVer

`feat(list_runs) + feat(show_run) + feat(sg runs list) +
feat(sg runs show)` -> **MINOR** -> `v0.10.0`. Consolidacion
inmediata con v0.9.0 porque `list`/`show` son el complemento
natural de `cancel`: sin ellos, el operador no puede saber
que Run cancelar.

## [0.11.0] — 2026-09-24 (MINOR, logs run)

**Tag**: `v0.11.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S3 del roadmap Etapa 7. Cierra el triangulo de
inspeccion read-only de Runs: tras listar (`v0.10.0`) y snapshotear
(`v0.10.0`), el operador puede ahora examinar el timeline completo
de eventos de un Run con `sg runs logs`. Read-only, sin emitir
eventos.

### Cambios funcionales (MINOR)

- **`Storage.list_events_for_run(*, tenant_id, project_id, run_id)`**:
  SELECT ordenado por `sequence ASC` (orden causal) filtrado por
  run_id usando el indice `events_by_run` ya existente. Devuelve
  tupla de tuplas crudas `(sequence, event_id, kind, timestamp,
  payload_json)`; el parsing a `RuntimeEvent` vive en `RunController`
  para mantener Storage libre de tipos del bounded context `runtime`.
- **`RuntimeEventLog`**: nuevo dataclass frozen
  `(sequence: int, event: RuntimeEvent)` que expone `sequence` al
  exterior sin modificar el contrato del evento runtime (sequence
  es meta-informacion de almacenamiento, no del evento en si).
- **`RunController.logs_run(*, tenant_id, project_id, run_id)`**:
  fail-fast con `get_run` (NotFoundError si no existe). Itera
  `_row_to_event_dict` sobre cada row y lo envuelve en
  `RuntimeEventLog(sequence, event)`. No emite eventos.
- **CLI `sg runs logs <project> <run-id> [--limit N]`**: salida
  CSV-like con cabecera (`seq event_kind timestamp payload`) y una
  linea por evento con resumen del payload (primer nivel
  `clave=valor` truncado a 40 chars). '--limit N' corta por cabeza
  despues de cargar todo (util para depurar los primeros N eventos
  de Runs largos). '(sin eventos)' si vacio.
- **`_route_runs`**: nueva rama `logs -> cmd_runs_logs`.
- **Reuso**: `cmd_runs_logs` delega en `_open_project_storage`
  (mismo helper DRY que list/show/cancel).

### Tests

- 3 tests unitarios `tests/test_runcontroller.py::TestLogsRun`:
  NotFoundError, RunCreated presente, RuntimeEventLog expone
  sequence + RuntimeEvent.
- 2 tests subprocess CLI `tests/test_cli_runs_inspect.py`:
  `test_logs_run_via_cli_outputs_event_timeline` (cabecera +
  1 linea RunCreated con payload resumido) y
  `test_logs_run_via_cli_unknown_run_returns_error` (exit 10).
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 680 passed (de 675 en v0.10.0, +5 nuevos:
  3 unit + 2 subprocess).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 96% (sube de 95% a 96%).

### SemVer

`feat(logs_run) + feat(sg runs logs)` -> **MINOR** -> `v0.11.0`.
Consolidacion inmediata con v0.10.0 porque `logs` es el
complemento natural de `list`/`show`: sin timeline, el operador
no puede diagnosticar por que un Run fallo o se cancelo.

## [0.12.0] — 2026-09-24 (MINOR, budgets)

**Tag**: `v0.12.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S4 del roadmap Etapa 7 (presupuestos opt-in por Run).
Cierra el riesgo principal que dejo el H4: un Run con self-loop y
sin limite superior puede iterar eternamente, consumiendo disco y
tiempo de computo sin abortar. Con S4, el operador puede poner
limites explicitos al crear el Run y el controller abortara
automaticamente cuando se alcancen, emitiendo un evento
`BudgetExceeded` que aparece en `sg runs logs`.

### Cambios funcionales (MINOR)

- **`EVENT_KINDS`** (`engine.py`): nuevo valor canonico
  `"BudgetExceeded"` (event_kind del runtime, NO categoria).
- **`EventBuilder.budget_exceeded(*, run_id, kind, limit, observed)`**:
  smart constructor con validacion: `kind` debe estar en
  `{visits, runtime, events}`. Payload: `{kind, limit, observed}`.
- **`RunBudget`** (dataclass frozen en `runcontroller.py`):
  `max_visits`, `max_runtime_seconds`, `max_events` (todos
  `Optional[int]`). Validacion `__post_init__`: no negativos,
  si se da debe ser > 0. `is_active` True si alguno definido.
- **`Storage.run_budgets`**: nueva tabla con PK `run_id` (FK
  logica a `workflow_runs`). Columnas `max_visits`,
  `max_runtime_seconds`, `max_events`, `inserted_at`.
  Migracion idempotente en `_migrate` (CREATE TABLE IF NOT EXISTS).
- **`Storage.upsert_budget(...)`**: INSERT OR REPLACE sobre la PK.
  Idempotente (cumple UAT-07).
- **`Storage.get_budget(...)`**: devuelve fila cruda o `None`
  (no lanza NotFoundError: ausencia = sin limites, compat con
  Runs anteriores a S4).
- **`RunController.create_run(..., budget=None)`**: parametro
  opcional. Si `budget is not None AND budget.is_active`,
  persiste via `upsert_budget`. Budget inactivo (todos None) o
  `None` = no escribe fila = semantica "sin limites" (compat).
- **`RunController._is_budget_exhausted`**: extendido (H4 + S4).
  Chequea 3 limites: (1) H4 original self-loop+max_visits por
  nodo, (2) Run.max_visits global, (3) Run.max_events global.
  Cuando (2) o (3) falla, emite `BudgetExceeded` antes de
  devolver True (asi el timeline del Run muestra POR QUE aborto).
- **`RunController._execute_one`**: invoca el check al inicio;
  si budget agotado, devuelve `False` (FAILED) sin tocar el
  nodo. El caller (`reconcile_run`) cierra el Run en FAILED
  via `_transition_run_state_with_event`.
- **`RunController._count_events`**: refactor menor — ahora
  delega en `Storage.list_events_for_run` (regla "Storage
  encapsula SQL"; antes tocaba `self._storage._conn` directo).
- **CLI `sg run ... --budget-visits N --budget-runtime-seconds N
  --budget-events N`**: parametros nuevos en el subcomando `run`.
  Si se da al menos uno, se construye `RunBudget` y se persiste.
- **CLI `sg runs budget <project> <run-id>`**: subcomando nuevo.
  Muestra el budget activo (key=value parseable) o `(sin budget)`.
  Run desconocido -> exit 10 (EXIT_DOMAIN).

### Tests

- 5 unit `TestRunBudgetDataclass`: defaults, valores positivos,
  negativos, cero, `is_active`.
- 4 unit `TestStorageBudget`: round-trip, nones, ausente, idempotencia.
- 3 unit `TestCreateRunWithBudget`: budget persistido, sin budget,
  budget inactivo.
- 2 unit `TestBudgetEnforcement`: self-loop+max_visits=1 emite
  BudgetExceeded; plan lineal sin budget no se aborta.
- 2 unit `TestBudgetKindValidation`: smart ctor rechaza kind invalido.
- 3 subprocess CLI `TestRunsBudgetCli`: `(sin budget)`,
  key=value, run desconocido -> exit 10.
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 700 passed (de 680 en v0.11.0, +20 nuevos).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 88% (baja de 96% por las
  nuevas lineas de S4 que no todos los tests ejercitan — el
  chequeo de `max_runtime_seconds` queda documentado como
  reservado y sera cubierto en S5 cuando se conecte a un
  reloj inyectable; el de `max_events` ya esta cubierto por
  enforcement del primer test).

### SemVer

`feat(RunBudget) + feat(BudgetExceeded) + feat(upsert_budget) +
feat(get_budget) + feat(sg runs budget) + feat(sg run --budget-*)`
-> **MINOR** -> `v0.12.0`. Consolidacion inmediata con v0.11.0
porque budgets son **complemento directo** del timeline:
`sg runs logs` (v0.11.0) muestra los eventos; sin budgets, no
hay forma de abortar Runs problematicos antes de que el operador
vea el timeline. La regla "evita micro-releases triviales" se
respeta: budgets son 3 `feat` coherentes (modelo, persistencia,
CLI) con enforce end-to-end probado.

## [0.13.0] — 2026-09-24 (MINOR, redaction policies)

**Tag**: `v0.13.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S5 del roadmap Etapa 7 (politicas de redaccion por
tenant). Cierra el vector de exfiltracion que dejo el modelo de
eventos: hasta v0.12.0, cualquier payload de evento (que puede
contener API keys, tokens, paths de workspace) se persistia integro
en `runtime_events.payload_json`. Con S5, el operador configura una
politica por tenant (`none` | `metadata` | `payload` | `full`) y
el `EventLog` redacta automaticamente antes de persistir.

### Cambios funcionales (MINOR)

- **`runtime.redaction`** (modulo nuevo):
  - `RedactionPolicy = Literal["none", "metadata", "payload", "full"]`.
  - `validate_policy(policy)`: smart constructor; `ValidationError`
    si la politica no esta en el conjunto canonico.
  - `redact_payload(payload, policy)`: funcion pura (no I/O,
    no reloj, determinista). Implementa las 4 politicas:
    - `none`: copia superficial (compat con pre-S5).
    - `metadata`: conserva claves, valores -> `[REDACTED]`.
    - `payload`: redaccion recursiva (escalares `[REDACTED]`,
      colecciones conservadas en forma).
    - `full`: devuelve `{}` (descarta todo el payload).
  - `REDACTED_MARKER: Final[str] = "[REDACTED]"`: constante
    publica para UIs que quieran detectar y formatear.
- **`Storage.tenant_policies`**: nueva tabla con PK `tenant_id`.
  Columnas: `redaction_policy TEXT NOT NULL DEFAULT 'none'`,
  `updated_at`.
- **`Storage.get_policy(*, tenant_id)`**: devuelve la politica
  configurada o `None` (sin fila = sin limite = default `none`).
- **`Storage.upsert_policy(*, tenant_id, policy)`**: INSERT OR
  REPLACE idempotente sobre la PK. Storage NO valida la politica;
  la validacion vive en `runtime.redaction` (regla "Storage
  encapsula SQL, no reglas de negocio").
- **`EventLog.__init__(conn, *, policy_resolver=None)`**: nuevo
  parametro opcional. `policy_resolver` es un `Callable[[str],
  str | None]` que, dado un `tenant_id`, devuelve la politica
  efectiva. Sin resolver -> default `none` (compat con pre-S5).
- **`EventLog._resolve_policy(tenant_id)`**: helper privado.
  Sin resolver -> `"none"`. Resolver devuelve None -> `"none"`.
  Resolver devuelve valor -> se aplica tal cual.
- **`EventLog.append`**: si hay policy_resolver configurado,
  el payload se redacta ANTES de serializar a `payload_json`.
  El `RuntimeEvent` original NO se muta (es frozen). Asi `logs_run`
  sigue viendo el evento ORIGINAL; en disco solo aparece la
  version redactada.
- **`RunController.__init__`**: inyecta un policy_resolver que
  delega en `Storage.get_policy` (regla "Storage encapsula SQL").
- **CLI `sg policy get <project>`**: imprime la politica efectiva
  del tenant. Default `none` si no hay fila.
- **CLI `sg policy set <project> --redact-policy X`**: persiste
  la politica. Choices validadas via argparse: `none|metadata|payload|full`.
- **`_route_policy`**: dispatcher para `policy get|set`.

### Politica default

Sin politica configurada para un tenant, el `EventLog` aplica
`"none"` (passthrough). Esto preserva el comportamiento de
v0.12.0 y anteriores: los Runs creados antes de S5 siguen
persistiendo payloads integros. La redaccion es **opt-in** por
tenant. Migrar un tenant a redaccion requiere ejecutar
`sg policy set <project> --redact-policy <X>`.

### Tests

- 14 unit `test_redaction.py`: validate_policy (2) + none (2) +
  metadata (2) + full (2) + payload (3) + pureza (2) + type (1).
- 3 unit `TestStoragePolicyPersistence`: round-trip, ausente,
  idempotencia.
- 4 unit `TestEventLogRedaction`: resolver=metadata redacta,
  default=none passthrough, resolver=payload recursivo,
  resolver=none passthrough.
- 4 subprocess CLI `test_cli_policy.py`: get sin policy,
  set+get round-trip, set invalido -> exit != 0, persistencia SQL.
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 725 passed (de 700 en v0.12.0, +25 nuevos).
- **Ruff**: limpio.
- **Cobertura `redaction.py`**: **100%** (modulo nuevo puro).
- **Cobertura `runcontroller.py`**: 88% (sin cambios: las lineas
  nuevas de S4 siguen sin cubrir `max_runtime_seconds`, que se
  conectara a un reloj inyectable en una iteracion futura).

### SemVer

`feat(redaction) + feat(EventLog.policy_resolver) +
feat(tenant_policies) + feat(sg policy get/set)` -> **MINOR**
-> `v0.13.0`. Consolidacion inmediata con v0.12.0 porque la
redaccion es **complemento directo** del modelo de eventos:
v0.12.0 emita eventos con secretos potenciales; sin S5, esos
secretos iban a disco. La regla "evita micro-releases triviales"
se respeta porque S5 son 4 `feat` coherentes (modelo, persistencia,
integracion EventLog, CLI).

## [0.14.0] — 2026-09-24 (MINOR, locks concurrentes por run)

**Tag**: `v0.14.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S6 del roadmap Etapa 7 (locks concurrentes por run).
Hasta v0.13.0, dos `sg run --concurrency` o dos schedulers
externos apuntando al mismo `<tenant>/<project>/<run-id>` podian
leer/escribir `runtime_events` y `runs` de forma entrelazada,
corrompiendo la transicion de estado. S6 introduce locks de
fichero por run para serializar reconcile_run y create_run
dentro del mismo proceso y entre procesos, con dos politicas:
`advisory` (espera hasta `lock-timeout-seconds`) y `fail-fast`
(eleva `LockUnavailable` con `code=sg_lock_unavailable`).

**Modulos / simbolos nuevos**:

- `skillgraph.runtime.locks` (modulo nuevo):
  - `RunLockKey(tenant_id, project_id, run_id)` con sanitizacion
    de path traversal (caracteres `/\. ` reemplazados por `_`).
  - `RunLockKey.to_filename() -> str` (`<tenant>__<project>__<run-id>.lock`).
  - `LockMode = Literal["none", "advisory", "fail-fast"]`.
  - `LockUnavailable(SkillGraphError)` con `code="sg_lock_unavailable"`.
  - `RunLock(lock_dir: Path, key: RunLockKey).take(mode, timeout_seconds)`
    context manager sobre `fcntl.flock` (LOCK_EX | LOCK_NB en polling
    para advisory; LOCK_EX | LOCK_NB en fail-fast).
  - Limpieza: `LOCK_UN`, `os.close`, `unlink()` con
    `contextlib.suppress(OSError)`.

**RunController**:

- Constructor extendido: `lock_dir: Path | None`,
  `lock_mode: LockMode = "none"`,
  `lock_timeout_seconds: float = 30.0`.
- Helper interno `_locked_run(tenant, project, run_id) -> Iterator`
  que delega en `_noop_lock()` cuando `lock_mode="none"` o
  `lock_dir=None`.
- `create_run(...)` envuelto en `with self._locked_run(...)`.
- `reconcile_run(...)` envuelve el cuerpo en
  `with self._locked_run(...)`; extraido a `_reconcile_run_locked`.

**Tests** (12 nuevos en `tests/test_locks.py`):

- `TestRunLockTakeRelease` (3): acquire + release, no leak, idempotencia.
- `TestRunLockConflict` (2): `fail-fast` eleva `LockUnavailable`;
  `advisory` con timeout corto eleva `LockUnavailable`.
- `TestRunLockReleasesOnException` (2): `try/except` interno libera
  el lock; `with` con excepcion interna libera.
- `TestRunLockKey` (3): filename estable, sanitizacion, sin colisiones.
- `TestRunLockAcrossProcesses` (2): dos procesos via `multiprocessing`
  se serializan en el mismo run.
- `TestRunControllerLockIntegration` (1): dos `RunController`
  reconciliando el mismo Run con `lock_mode="advisory"` se serializan
  y terminan ambos en `COMPLETED`; lock_file no queda tras la ejecucion.
- `TestRunControllerLockFailFast` (1): `fail-fast` eleva
  `LockUnavailable` si otro reconcile_run tiene el lock
  (test debil bajo concurrencia extrema).

Total acumulado: **739 tests verde** (725 + 14 nuevos).
`ruff check src tests`: limpio.

### SemVer

`feat(runtime.locks) + feat(RunController lock_dir/lock_mode/lock_timeout_seconds) +
feat(create_run/reconcile_run lock wrapping)` -> **MINOR**
-> `v0.14.0`. Consolidacion inmediata con v0.13.0 porque los locks
son **complemento directo** del modelo de eventos: v0.13.0 introduce
politicas de redaccion, pero sin S6 dos reconciliaciones concurrentes
pueden intercalar eventos y saltarse la redaccion. La regla
"evita micro-releases triviales" se respeta porque S6 son 3 `feat`
coherentes (locks, integracion RunController, tests de concurrencia).

## [Sin bump] — 2026-09-24 (refactor interno)

**Commit**: `6c8c17f` (sin tag, refactor sin bump).

**Resumen**: Reduccion de tamano de funciones en `knowledge/context_controller.py`
para cumplir AGENTS.md §1.5 (umbral ~40 LoC).

- `ContextController.compile_handoff`: 121 -> 94 LoC. Delegacion en
  3 helpers puros de modulo:
  - `enforce_strict_freshness(items, policy)`
  - `apply_budget(obligatory, optional, *, budget_chars, overflow_strategy)`
  - `build_capabilities(included, policy)`
- `ContextController._resolve_one_selector`: 114 -> 23 LoC. Dispatcher
  que delega en 3 ramas:
  - `_resolve_entity_selector(ctrl, value)` (14 LoC)
  - `_resolve_predicate_selector(ctrl, value)` (16 LoC)
  - `_resolve_source_selector(ctrl, value, label)` (31 LoC)
- Mapeo a `CompiledResource` encapsulado en 3 funciones puras de
  modulo: `claim_to_resource`, `predicate_row_to_resource`,
  `evidence_row_to_resource`.

**Tests**: 15 nuevos en `tests/test_context_controller.py`
(11 helpers + 4 mappers). Total: **754/754 verde**. ruff limpio.

## [Sin bump] — 2026-09-26 (stewardship: defensa operativa)

**Commits**: `4d1e622` + `23e4c94` (fix) + `21bc550` (docs) + tareas mise.

**Resumen**: Ciclo STEWARDSHIP-DT-PRE-PUSH-HOOK. Tercera capa de defensa
operativa (junto a pre-commit y CI remoto): **pre-push** ejecuta la suite
completa de pytest (~190s) antes de aceptar un `git push`.

- Hook POSIX shell en `scripts/hooks/pre-push` (75 LoC, sin
  dependencias externas).
- Dispatcher `run_in_toolchain` que detecta `mise`/`uv`/`pip`/`none` y
  delega en el wrapper nativo.
- Bypass `HOOK_SKIP_PUSH_TESTS=1` para emergencias.
- Patrón `mktemp` + `if !` (workaround al bug `set -e` + `| tail` ya
  documentado en `.pipeline.kts`).
- `trap 'rm -f "$_log"' EXIT` para limpieza de tempfile en
  SIGTERM/SIGINT (anadido en V9d deep audit).
- README documenta la capa defense-in-depth en EN y ES.
- Tareas `mise run test-fast` (abort 1er fallo) y `mise run test-cov`
  (cobertura local) para iteracion RED/GREEN.

**Tests**: 9 nuevos en `TestPrePushHook` + `test_installer_copies_all_hooks`.
Total: **889/889 verde**. ruff limpio. Auditoria completa en
`audits/pre-push-hook-2026-09-26.md` (239 LoC).

**Justificación de "Sin bump"**: es dev-infra puro. No añade API
observables ni cambia comportamiento del producto. Siguiente bump
será solo cuando llegue un `feat` real.

## [Sin bump] — 2026-09-26 (stewardship: cobertura de branches H12)

**Commit**: `tests/test_h12_file_signature_scopes.py` (15 tests nuevos) +
`audits/file-scope-validation-branches-2026-09-26.md`.

**Resumen**: Ciclo STEWARDSHIP-DT-FILE-SCOPE-VALIDATION tras la consigna
"avanza" del operador. Subir la cobertura de `file_scope.py` (H12 Scopes
y consultas composables) sin tocar API ni contratos.

- Clase `TestFileScopeValidation` con 15 tests nuevos cubriendo las 12
  ramas tristes que coverage reportaba como descubiertas:
  - 4 sobre `validate_package_name` / `validate_bounded_context_name`
  - 2 sobre `ScopeQuery.__post_init__`
  - 3 sobre `ScopeResolution.__post_init__`
  - 2 sobre `resolve_directory_scope`
  - 2 sobre `resolve_package_scope`
  - 1 sobre `resolve_bounded_context_scope`
  - 1 sobre `aggregate_signatures` (dedup por foco)
- 0 cambios en `src/skillgraph/`. 0 contratos rotos. 0 regresiones.
- Hallazgo colateral documentado (NO reparado): `SignatureProcedencia.
  __post_init__` levanta `ValueError` en vez de `ValidationError`,
  violando AGENTS §1.2. Fix fuera de scope; registrado como derivado.

**Tests**: 23/23 verde en el archivo. Total proyecto: **904/904 verde**.
ruff limpio.

**Cobertura**: `file_scope.py` 82% → **99%** (+17pp). La única línea
restante (284) es un corner case interno del loop de agregación donde
`signatures_per_source` tiene entries con tuple vacío.

## [Sin bump] — 2026-09-26 (cumplimiento AGENTS §1.2: errores tipados)

**Commit**: `dfd192a` — 16 raises cambiados + 12 tests nuevos + audit.

**Resumen**: Tras la consigna "vamos con lo siguiente", se abordó el
hallazgo colateral de la investigación retrospectiva. La inspección
extendida reveló 16 violaciones de AGENTS §1.2 (errores tipados) en
6 archivos:

```text
src/skillgraph/knowledge/file_signature.py    8 raises ValueError
src/skillgraph/knowledge/file_handoff.py      3 raises ValueError
src/skillgraph/knowledge/git_source.py        1 raise ValueError
src/skillgraph/runtime/locks.py                1 raise ValueError
src/skillgraph/governance/improvement.py       2 raises ValueError
src/skillgraph/governance/receipts.py          1 raise ValueError
```

Todos en `__post_init__` de dataclasses de dominio.

**Cambios**:
- src/: 16 raises cambiados de ValueError → ValidationError
- tests/test_knowledge_validation_errors.py: 12 tests nuevos (12/12 rojo→verde)
- tests/test_h9_coverage_git_source.py:78: migrado a ValidationError
- 0 callers en src/ con `except ValueError` (grep limpio)
- ValidationError hereda de SkillGraphError → Exception (no rompe nada)

**Tests**: 918/918 verde (906 → 918, +12 nuevos). Mutation testing M8
detectada. ruff limpio.

**Verificación final**:
```bash
grep -rn "raise ValueError\|raise Exception" src/skillgraph/ --include="*.py"
  → 0 resultados (100% cumplimiento §1.2)
```

**Auditoría completa** en `audits/knowledge-validation-errors-2026-09-26.md`
(114 LoC).
