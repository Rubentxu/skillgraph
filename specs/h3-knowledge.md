# Spec H3 — Conocimiento incremental y contexto verificable

> Estado: **BORRADOR**, pendiente de firma antes de implementar.
> Hito: H3 (Etapa 3) — cierra `external/blueprint-v1/plan/ROADMAP.md` Etapa 3.
> Gate de H3 (literal): "modificar una fuente, detectar qué afirmaciones
> requieren revisión y reconstruir el contexto".
> UAT canónico (literal): "un agente simulado puede completar su trabajo
> sin historial conversacional".

## 1. Principio rector

El **conocimiento** (Claims, Evidence, OutcomeTrace) está separado del
**contexto** (ContextRecipe, Handoff). El primero es la fuente de verdad
sobre el proyecto; el segundo es una vista materializada e inmutable
que un nodo recibe.

Las afirmaciones observan dependencia: si cambia la fuente, hay un
conjunto calculado de Claims que quedan `stale` (no necesariamente
inválidos, pero que requieren verificación).

## 2. Entregables concretos

### 2.1. Modelo de conocimiento (KnowledgeController)

**Source** — referencia a un origen externo o interno:
- Identidad lógica (`source_id`).
- Tipo: `git_commit` | `local_file` | `external_doc` | `git_tree`.
- Para `git_*`: commit SHA + ruta + blob SHA + worktree ref.
- Hash de contenido (independiente del commit SHA, ver ADR-0007).
- Fecha/Revisión de comprobación.
- Estado de vigencia (`fresh` | `stale` | `archived`).

**Entity** — sujeto del conocimiento: archivo, símbolo, contrato,
regla, etc. Identidad estable (`entity_id`) que NO cambia con la revisión.

**Relation** — arista tipada entre entities (`REQUIRES`, `DEPENDS_ON`,
`IMPLEMENTS`, etc.). Mismas propiedades que Storage actual + `properties`
JSON serializadas.

**Claim** — afirmación verificable:
- `subject_entity_id` (la entity sobre la que se afirma).
- `predicate` (string normalizado).
- `object_literal` (el valor afirmado).
- `source_id` (de dónde se extrajo).
- `evidence_ids` (las evidencias que la sustentan).
- `extraction_method` (`static_analysis` | `git_log` | `manual` | …).
- `extractor_version` (versión del analizador).
- `checked_at_revision` (revisión/fecha de la última verificación).
- `stale` (bool; calculado por el grafo de dependencias).

**Evidence** — observación atómica:
- `kind` (`metric` | `snippet` | `log_line` | `commit_message`).
- `content` (texto o JSON estructurado).
- `source_id`.
- `observed_at` (timestamp o commit).

**Finding** — resultado de aplicar una regla:
- `entity_id`, `observation`, `rule_ref`, `rule_version`,
  `evidence_ids`, `result` (`pass`|`fail`|`inconclusive`),
  `valid_until_revision`.

**OutcomeTrace** — recorrido transversal:
- `trace_id`, `name`, `kind` (`SoftwareExecutionSlice` | otro).
- Lista ordenada de `claim_ids` + `evidence_ids` + `relation_ids`.
- NO duplica el contenido de cada elemento (ver §9 del blueprint).

### 2.2. ContextRecipe y ContextController

**ContextRecipe** (recurso brick, kind nuevo `ContextRecipe`):
- Metadata (`name`, `namespace`, `revision`).
- `obligatory`: lista de selectores (entity|relation|finding) que
  SIEMPRE deben estar en el handoff.
- `optional`: selectores que pueden incluirse bajo presupuesto.
- `relation_selectors`: tipo de relaciones a expandir (transitivo 1..N).
- `freshness_policy`: `strict` (receta rechaza si stale) | `best_effort`.
- `token_budget`: entero (presupuesto aproximado, NO autoritativo).
- `overflow_strategy`: `drop_optional` | `fail` | `truncate_finding`.
- `isolation_policy`: `project` | `tenant` | `global`.

**ContextController**:
- `compile_handoff(node_definition, recipe_ref) -> Handoff`:
  ejecuta el proceso §5 de `07-contexto-y-handoff.md` literal.
- Resuelve contrato → ámbito → conocimiento obligatorio →
  relaciones → vigencia → selección → materialización →
  validación de presupuesto → persistencia → entrega.
- Lanza `MissingObligatoryKnowledgeError` si falta algo obligatorio.
- Lanza `StaleKnowledgeError` si `freshness_policy=strict` y hay stale.
- Idempotente: misma receta + mismas revisiones → mismo `context_hash`.

### 2.3. KnowledgeController

- `register_source(source) -> source_id` — alta idempotente.
- `record_claim(claim) -> claim_id` — alta idempotente por
  (subject, predicate, source, checked_at_revision).
- `invalidate_from_source(source_id) -> list[claim_id]` —
  marca stale y propaga por relaciones transitivamente.
- `query_relevant_obligatory(recipe) -> list[Claim|Evidence]`.
- `traverse_dependencies(claim_id, max_hops) -> list[Claim]`.

### 2.4. Git fingerprinting

- `GitSource.from_commit(repo_root, sha, pathspec) -> Source`:
  captura commit SHA + paths + blob SHAs + working tree status.
- `GitSource.refresh() -> None`: detecta cambios (blob SHA).
- Diferencia **explícita** entre commit SHA y blob SHA
  (ver §5 del blueprint, §3 de ADR-0007).

### 2.5. OutcomeTrace software

- `SoftwareExecutionSlice` (subtipo de `OutcomeTrace`):
  un slice de ejecución sobre el grafo de conocimiento.
- `OutcomeTracer.from_run(run_id, knowledge) -> OutcomeTrace`:
  extrae los claims/evidencias que el run tocó.

## 3. Schema SQLite (delta sobre storage.py)

Tablas nuevas, todas con `tenant_id + project_id` para aislamiento:

```sql
sources(
  source_id, kind, content_hash, locator_json,
  git_commit_sha, git_tree_sha, working_tree_status,
  checked_at, freshness_state
)
entities(
  entity_id, kind, stable_key, project_id
)
claims(
  claim_id, subject_entity_id, predicate, object_literal,
  source_id, extraction_method, extractor_version,
  checked_at_revision, stale, created_at
)
evidences(
  evidence_id, kind, content_json, source_id, observed_at
)
claim_evidence(
  claim_id, evidence_id  -- N:M
)
findings(
  finding_id, entity_id, observation, rule_ref, rule_version,
  evidence_ids_json, result, valid_until_revision
)
outcome_traces(
  trace_id, kind, name, project_id, created_at
)
outcome_trace_links(
  trace_id, link_kind, link_id  -- 'claim'|'evidence'|'relation'
)
```

Índices:
- `(tenant_id, project_id, source_id)` (todas).
- `(subject_entity_id, predicate)` en claims (búsqueda por sujeto).
- `stale=1` parcial en claims (invalidación rápida).

`Storage._migrate()` aplica `CREATE TABLE IF NOT EXISTS` para cada tabla
sin tocar las existentes (idempotente).

## 4. Algoritmo de invalidación (literal del §8 del blueprint)

```text
detect_source_change(source_id)
  -> locate_direct_claims(source_id)
  -> traverse_relevant_dependencies(transitively, max_hops)
  -> mark_affected_claims_stale(claim_ids)
  -> identify_active_consumers(claim_ids)
  -> schedule_required_refresh()
  -> verify_new_claims()        -- cuando el refresco se ejecuta
  -> publish_new_revisions()    -- emite event de KnowledgeUpdated
```

No regenera todo el grafo. La invalidación es inmediata; la
actualización bajo demanda. Sigue ADR-0001 (Python core) y
ADR-0007 (provenance).

## 5. UAT canónico (H3)

1. Crear proyecto + DomainPack de software.
2. Registrar Source = `git_commit` del proyecto.
3. Extraer Claims automáticos: `entity=archivo.py`,
   `predicate=line_count`, `value=42`.
4. Modificar el archivo en un commit posterior.
5. `KnowledgeController.invalidate_from_source(source_id)`.
6. Verificar:
   - Claim aparece como `stale=1`.
   - Consumers activos son identificados (otros Claims que dependen).
   - `ContextController.compile_handoff` con `freshness_policy=strict`
     lanza `StaleKnowledgeError`.
   - Con `best_effort`, compila handoff con `stale=true` flag en claims.
7. `refresh()` re-extrae Claims actualizados.
8. `OutcomeTracer.from_run(run_id, knowledge)` produce un trace que
   referencia las Claims/Evidences que el run tocó.
9. **Sin historial conversacional**: el test sube el handoff
   serializado, lo abre en un proceso nuevo, ejecuta un FakeAdapter,
   y el resultado es el mismo que en el proceso original.

## 6. Slices de implementación (propuesta 5)

Cada slice entrega una pieza vertical observable. Cierran
**decremento de funcionalidad** si fallan, no incremento.

### Slice 1 — Knowledge ADT + Storage delta

- `src/skillgraph/knowledge.py`: dataclasses frozen para
  `Source`/`Entity`/`Claim`/`Evidence`/`Relation`/`Finding`/`OutcomeTrace`.
- `runtime_types.py` extendido: `SourceKind`, `FreshnessState`,
  `ClaimPredicate` (Literal inicial), `FindingResult` literals.
- `Storage._migrate()` añade las 7 tablas nuevas.
- `Storage` métodos: `register_source`, `get_source`,
  `record_claim`, `get_claim`, `list_stale_claims`,
  `attach_evidence`, `get_evidences_for_claim`,
  `record_finding`, `record_trace`, `link_trace`.
- Tests: `tests/test_knowledge_storage.py` (15 tests, schema,
  idempotencia de upsert, UNIQUE constraints).

### Slice 2 — KnowledgeController (sin invalidación transitiva)

- `src/skillgraph/knowledge_controller.py`:
  `register_source`, `record_claim`, `query_relevant_obligatory`,
  `traverse_dependencies(max_hops=1)`.
- Tests: `tests/test_knowledge_controller.py` (12 tests, sin git todavía).

### Slice 3 — Git fingerprinting

- `src/skillgraph/git_source.py`: `GitSource.from_commit`,
  `GitSource.refresh`, `detect_changes(since_sha)`.
- Dependencia: `pygit2` o `dulwich` (a decidir en spec);
  sin networking, solo acceso al repo local.
- Tests: `tests/test_git_source.py` (8 tests, repo temporal en tmp).

### Slice 4 — Invalidación transitiva + event

- `KnowledgeController.invalidate_from_source(source_id)`:
  implementa el algoritmo literal del §4.
- Emite `KnowledgeInvalidated` event al EventLog (reusa el sistema
  de la Etapa 2; tipo de evento nuevo en `runtime_types.py`).
- Tests: `tests/test_knowledge_invalidation.py` (10 tests, ciclo
  modify → invalidate → check stale → refresh).

### Slice 5 — ContextRecipe + ContextController + OutcomeTracer

- Kind nuevo `ContextRecipe` en registry.
- `src/skillgraph/context_controller.py`: `compile_handoff`,
  serialización, hash determinista.
- `OutcomeTracer.from_run(run_id)`.
- Tests: `tests/test_context_controller.py` (12 tests, UAT canónico
  completo §5 in-process).
- Tests E2E subprocess: añadir a `tests/test_cli_branches.py`
  comando nuevo `knowledge` (subcomando opcional; ver §10).

## 7. Out of scope explícito

- **NO** se añade base de grafos especializada (mantener SQLite
  per-proyecto; tabla `claims` indexada).
- **NO** se introduce scheduler distribuido ni sistema de agentes
  permanentes (antiobjetivos del roadmap §Final).
- **NO** se añaden Domain Packs especializados (eso es H5).
- **NO** se modifica el núcleo de H2 (RunController, Handoff,
  FakeAdapter) — solo consume Handoff como dato.

## 8. Riesgos y decisiones pendientes

### Decisión D1 — Librería Git

- Opción A: `pygit2` (binding libgit2, robusto pero binario).
- Opción B: `dulwich` (pure Python, más portable).
- Recomendación: **B (`dulwich`)**. SkillGraph es local-first;
  evitar binarios C reduce la superficie de instalación.
- Pendiente: spike de 1h para confirmar que cubre `blob`,
  `commit`, `tree` y `status` que necesitamos.

### Decisión D2 — ContextRecipe como brick

- Ser brick (kind `ContextRecipe`) permite versionado,
  revisión declarativa, asimilación por Domain Pack.
- Costo: añadir validate_spec al registry.
- Recomendación: **SÍ como brick**.

### Decisión D3 — Sincronización de invalidación

- ¿El event `KnowledgeInvalidated` dispara reconciliación de
  RunController? Sí, pero solo para runs ACTIVE. Para runs
  terminales, el handoff es inmutable y NO se invalida
  retroactivamente (inmutabilidad del handoff).
- Pendiente: cómo manejar runs ACTIVE cuyo handoff referenciaba
  Claims ahora stale. **Decisión**: el run continúa hasta su
  próximo reconcile_run; el CLI avisa con warning; el run solo
  falla si la siguiente operación requiere `freshness_policy=strict`.

### Decisión D4 — Token budget real

- El blueprint menciona "presupuesto de tokens" pero NO define
  unidades ni forma de medir. SkillGraph H3 implementa el
  campo como `int` con semántica de "caracteres aproximados",
  NO como tokens de modelo. Esto es deliberadamente subóptimo
  pero suficiente para el gate UAT.
- Pendiente: revisar cuando se integre un Adapter LLM real.

## 9. Criterios de aceptación del spec

El spec se considera **firmado** cuando:

1. D1 está decidida (elegir `dulwich` o `pygit2`).
2. D2 está aprobada (sí/no como brick).
3. D3 está aprobada (sincronización de invalidación).
4. D4 está aprobada (semántica del token budget).
5. Las 5 slices de §6 tienen criterios de aceptación por slice
   (commits separados, tests verde por slice, no por hito completo).

Tras la firma, el spec se commitea en `specs/h3-knowledge.md`
con estado `STATUS: SIGNED`.

## 10. Comando CLI (futuro, no implementa en este spec)

`skillgraph knowledge` subcomandos (post-H3 inmediato):
- `knowledge extract --project P --source S` — extrae Claims.
- `knowledge stale --project P` — lista Claims stale.
- `knowledge invalidate --project P --source S` — fuerza invalidación.
- `knowledge trace --project P --run-id R` — muestra OutcomeTrace.

## 11. Referencias

- `external/blueprint-v1/06-controladores.md` §2 (controllers)
- `external/blueprint-v1/07-contexto-y-handoff.md` (completo)
- `external/blueprint-v1/08-conocimiento.md` (completo)
- `external/blueprint-v1/adr/ADR-0006-handoff-contexto.md`
- `external/blueprint-v1/adr/ADR-0007-conocimiento-verificable.md`
- `external/blueprint-v1/adr/ADR-0011-controladores.md`
- `external/blueprint-v1/plan/HITOS.md` H3
- `external/blueprint-v1/plan/ROADMAP.md` Etapa 3
- `external/blueprint-v1/plan/UAT.md` (acceptance matrix)
