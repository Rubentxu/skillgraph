# Spec H3 — Conocimiento incremental y contexto verificable

> Estado: **DISEÑO COMPLETO**, pendiente de firma (D2, D3, D4).
> D1 cerrada con spike (dulwich, commit `0e94e16`).
> Sub-specs diseñados: slices 1-5 (commits `13c1942`, este commit,
> y siguientes).
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

## 6. Slices de implementación (5 slices, todos con sub-spec)

Cada slice entrega una pieza vertical observable. Cierran
**decremento de funcionalidad** si fallan, no incremento.

**Sub-specs detallados** (en `specs/`):
- Slice 1 → `specs/h3-slice-1.md` (457 líneas, 17 tests, ADT + Storage).
- Slice 2 → `specs/h3-slice-2.md` (KnowledgeController, 14 tests).
- Slice 3 → `specs/h3-slice-3.md` (Git fingerprinting con dulwich, 8 tests).
- Slice 4 → `specs/h3-slice-4.md` (Invalidación transitiva + event, 10 tests).
- Slice 5 → `specs/h3-slice-5.md` (ContextController + OutcomeTracer, 15 tests).

Cada sub-spec incluye: ADT, schema, API pública, errores nuevos,
lista de tests con criterios, riesgos identificados, y commit
previsto. **Total previsto tras firma**: 161 → 225 tests.

### Slice 1 — Knowledge ADT + Storage delta

Ver `specs/h3-slice-1.md` para detalle completo. 17 tests propuestos.

### Slice 2 — KnowledgeController (sin invalidación transitiva)

Ver `specs/h3-slice-2.md`. 14 tests propuestos, dependencias de
Storage (Slice 1), no toca Git. UUIDv5 para IDs derivados.

### Slice 3 — Git fingerprinting

Ver `specs/h3-slice-3.md`. 8 tests con repo temporal, `dulwich`
como dep opcional (`pip install skillgraph[git]`).

### Slice 4 — Invalidación transitiva + event

Ver `specs/h3-slice-4.md`. 10 tests, algoritmo del blueprint §8
implementado literalmente. Emite `KnowledgeInvalidated` al EventLog.

### Slice 5 — ContextRecipe + ContextController + OutcomeTracer

Ver `specs/h3-slice-5.md`. 15 tests (12 unit + 3 E2E subprocess),
cierra el gate H3. ContextRecipe como brick (D2 cerrado=brick).

## 7. Out of scope explícito

- **NO** se añade base de grafos especializada (mantener SQLite
  per-proyecto; tabla `claims` indexada).
- **NO** se introduce scheduler distribuido ni sistema de agentes
  permanentes (antiobjetivos del roadmap §Final).
- **NO** se añaden Domain Packs especializados (eso es H5).
- **NO** se modifica el núcleo de H2 (RunController, Handoff,
  FakeAdapter) — solo consume Handoff como dato.

## 8. Riesgos y decisiones pendientes

### Decisión D1 — Librería Git ✅ (cerrada 2026-09-23)

**Decisión: `dulwich`**.

Evidencia del spike (probe en `/tmp/sg-git-spike`):

| Métrica | dulwich | pygit2 |
|---|---|---|
| Tiempo de import | **5.76 ms** | 103.45 ms (~18× más) |
| Binarios nativos | ninguno (pure Python) | `pygit2.libs/` = 14 MB (libgit2 C) |
| Wheel instalado | 7 MB | 17 MB total |
| API HEAD/Tree/Blob | `Repo.head()` + `repo[head]` + `tree.items()` | `repo.head.target` + `repo[tree]` |
| API status | `porcelain.status(repo)` con `.staged`/`.unstaged`/`.untracked` separados | `repo.status()` dict {filename: flags} |
| Cross-check SHAs | ✅ HEAD/tree/blob SHA coinciden con pygit2 | ✅ |

**Motivos para `dulwich`:**
- SkillGraph es **local-first**: al no usar networking ni push/pull,
  pygit2 no aporta ventajas de rendimiento.
- Pure Python reduce la superficie de instalación: `uv pip install dulwich`
  no requiere compilador C ni dependencias de sistema.
- API más limpia para nuestro caso: separar staged/unstaged/untracked
  es exactamente el modelo conceptual del blueprint §5 (índice + working tree).
- Wheel 2.5× menor: relevante para `mise` install limpio.

**Trade-offs aceptados:**
- pygit2 es ~2× más rápido en operaciones masivas (clones, fetch).
  SkillGraph H3 NO clona repos remotos: solo lee `.git/` local. No aplica.
- pygit2 soporta más features de libgit2 (worktrees múltiples, submodules).
  SkillGraph H3 NO usa submodules; worktrees múltiples están fuera de scope.
  Si H4+ los necesita, se reconsidera.

**Pendiente operativo:** ~~spike de 1h para confirmar `dulwich` cubre también
`git_log`.~~ **CERRADO 2026-09-23**: `dulwich.repo.Repo.get_walker(paths=[...])`
cubre `git_log -- <path>` exactamente como necesitamos para
`OutcomeTracer.from_run`. Filtros por pathspec funcionan. D1 cerrada
por completo con evidencia reproducible.

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

1. D1 está decidida (✅ cerrada 2026-09-23: `dulwich`, commit `0e94e16`).
2. D2 está aprobada (sí/no como brick).
3. D3 está aprobada (sincronización de invalidación).
4. D4 está aprobada (semántica del token budget).
5. Las 5 slices de §6 tienen sub-specs detallados con criterios
   de aceptación por slice (commits separados, tests verde por
   slice, no por hito completo). ✅ (slice-1 a slice-5 commiteados).

Tras la firma, el spec se commitea con estado `STATUS: SIGNED`.

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
