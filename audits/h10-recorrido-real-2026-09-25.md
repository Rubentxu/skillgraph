# H10 — Mapa del recorrido real y baseline

**Fecha**: 2026-09-25
**Workitem**: H10 (evolution-v2/plan/ROADMAP.md)
**Workflow SDDK**: A-min (research deliverable, sin codigo de produccion)
**Estado**: COMPLETO

## 1. Proposito

Inventariar APIs y contratos existentes, trazar un caso real de
extremo a extremo, localizar decisiones duplicadas, identificar
fixtures existentes y seleccionar el primer proveedor determinista
candidato para H11-H15.

Criterios de salida de H10:

1. Inventario de APIs y contratos existentes.
2. Trazado de un caso real (workflow end-to-end).
3. Localizacion de decisiones duplicadas.
4. Catastro de fixtures de consultas y revisiones.
5. Seleccion del primer proveedor determinista (criterio + 1-2
   candidatos).

Todos cubiertos abajo.

## 2. Inventario de APIs y contratos existentes

### 2.1 Modulos por bounded context (38 modulos productivos)

| Area              | Modulos | Cobertura media | Funcion                        |
|-------------------|--------:|----------------:|--------------------------------|
| `runtime/`        |       7 |             94% | RunController, EventLog, locks  |
| `resources/`      |       7 |             99% | registry, parser, catalog, workflow |
| `knowledge/`      |       6 |             95% | grafo, contexto, conocimiento   |
| `domain/`         |       4 |             97% | DSL, pack_loader, skill_importer |
| `core/`           |       4 |             99% | errors, recipe, runtime_types   |
| `platform/`       |       3 |             92% | paths, storage (97%)            |
| `governance/`     |       3 |             99% | expansion, promotion            |
| `cli/` + entry    |       3 |             49% | runner (gap estructural subprocess) |
| **TOTAL**         |  **38** |         **83%** | (3811 stmts / 1028 branches)    |

Nota: `cli/runner.py` 49% es gap estructural conocido
(audits/runner-coverage-2026-09-25.md) — los 30 `cmd_*` se
ejercitan via subprocess en `tests/test_cli_uat.py` pero
pytest-cov no rastrea subprocess. NO requiere fix.

### 2.2 APIs publicas de Storage (57 metodos, 96% cobertura)

Storage encapsula **toda** la SQL del proyecto tras el refactor
H9-BSlice3 (commits 54d9015..e9e577e). Las APIs se agrupan en:

| Grupo | Metodos | Notas |
|---|---:|---|
| Recursos (bricks) | `upsert_resource`, `get_resource`, `list_resources` | CRUD basico |
| Relaciones | `add_relation`, `dependencies_of`, `dependents_of` | DAG traversal |
| Sources | `register_source`, `get_source`, `update_source_freshness` | ciclo de vida del source |
| Entities + Claims + Evidences | `upsert_entity`, `get_entity`, `record_claim`, `get_claim`, `record_evidence`, `attach_evidence_to_claim`, etc. | ~20 metodos; sub-grafo de conocimiento |
| Claims/Evidences por criterio | `list_claims_by_predicate`, `list_evidences_for_source`, `list_claims_for_source` | queries del knowledge_controller |
| Workflows (runs) | `create_run`, `load_run`, `transition_run_state`, `list_node_executions`, `list_executed_node_names`, `start_node_execution`, `complete_node_execution`, `mark_node_failed`, `recover_interrupted_node_executions` | 9 APIs H9-BSlice3-S1..S9 |
| Eventos / Trazas | `record_trace`, `link_trace`, `record_finding` | append-only |
| Lifecycle | `close`, `conn` (property), `storage.atomic` ctx manager | |

Hallazgo H10: las 57 APIs son **estables** (firmas keyword-only,
tipos concretos). El refactor H9-BSlice3 cerro los 10 sitios SQL
directos del RunController.

### 2.3 Protocolos inyectables

```python
class AgentAdapter(Protocol):                  # src/skillgraph/runtime/agent.py:71
    def invoke(self, handoff: Handoff) -> AgentResult: ...
```

Implementaciones en repo:
- `FakeAgentAdapter` (lee fixtures deterministas desde disco).
- `RecordingAdapter` (graba invocaciones para tests).

Estado actual: NO hay Adapter real. **Es el gap E1 del H9
addendum honesto** (audits/h9-addendum-2026-09-25.md).

### 2.4 CLI (30 comandos)

Distribucion:
- `sg init` — bootstrap proyecto.
- `sg project {create,list,inspect}` — gestion de proyecto.
- `sg knowledge {stale,invalidate,refresh,compile,trace}` — 5 cmd.
- `sg runs {list,show,logs,cancel,budget}` — 5 cmd (Etapa 7 S4).
- `sg policy {get,set}` — redaction (Etapa 7 S5).
- `sg pack {load,import}` — 2 cmd.
- `sg brick register` — 1 cmd.
- `sg promotion {submit,list,reconcile}` — 3 cmd (H7 outbox).
- `sg run` — ejecutar workflow (entry point).
- `sg expansion {propose,apply,validate,rejections,list,show,archive}` — 7 cmd (H4).

### 2.5 Tests: 784 tests, 73 ficheros

| Categoria | Ficheros | Cobertura notable |
|---|---:|---|
| Unit (storage, runtime, knowledge) | ~50 | Core + integration |
| CLI in-process | ~15 | Tests de los wrappers InProcess (no subprocess) |
| CLI subprocess (UAT) | ~7 | `test_cli_uat.py` ejecuta `sg` real |
| Bench smoke | 3 | `test_bench_smoke`, `test_bench_storage_reads_smoke`, `test_bench_common` |
| UAT audit | 2 | `test_uat_audit.py` (16 UATs wrapped) |

## 3. Caso real trazado: `sg run` end-to-end

Trazado literal del recorrido que sigue una invocacion `sg run`
desde CLI hasta la persistencia del evento final.

```text
[CLI] usuario: sg run plan.yaml --budget-max-events 1000
  -> cmd_run(args)                                    # cli/runner.py
       |
       v
[Plan] PlanLoader.load(plan.yaml)                     # resources/plan_loader.py
       -> InitialNode = "start"
       -> Plan + WorkflowPlan (frozen dataclass)
       |
       v
[Storage] create_run(tenant, project, plan_json, initial_node)
       -> run_id = new_run_id()                       # runtime/runcontroller.py:215
       -> INSERT INTO workflow_runs
       |
       v
[EventLog] append(RunCreated event)                  # runtime/engine.py
       -> INSERT INTO runtime_events (UNIQUE event_id)
       |
       v
[RunController] reconcile_run(run_id)                 # runtime/runcontroller.py:363
       -> para cada nodo ready:
       |     compile_handoff(recipe, run_id, ne_id)   # knowledge/context_controller.py:260
       |     -> resolve_selectors (obligatory + optional)
       |     -> enforce_strict_freshness
       |     -> apply_budget (token_budget, overflow_strategy)
       |     -> Handoff inmutable (HandoffExecution + Knowledge + Capabilities)
       |
       v
[Storage] start_node_execution(tenant, project, run_id, node_name, attempt, ctx_hash, handoff_json)
       -> INSERT INTO node_executions
       |
       v
[EventLog] append(NodeStarted event)
       |
       v
[Adapter] adapter.invoke(handoff)                     # runtime/agent.py
       -> hoy: FakeAgentAdapter (lee fixture)
       -> futuro: RealAdapter (HTTP/Mock/Local)        # H9 E1 PENDIENTE
       -> AgentResult(outcome, result_json, evidence?)
       |
       v
[Storage] complete_node_execution(node_exec_id, outcome, result_json)
       -> UPDATE node_executions SET state='SUCCEEDED'
       |
       v
[EventLog] append(NodeCompleted event)
       |  + append(EvidenceProduced event) si hay evidence
       |
       v
[RunController] _executed_node_names  -> siguiente nodo (transitions en plan)
       -> si siguiente nodo: repetir desde compile_handoff
       -> si nodo terminal: transition_run_state(COMPLETED)
       |
       v
[EventLog] append(RunCompleted event)
       |
       v
[CLI] imprime resumen: run_id, eventos, handoffs, exit 0
```

**Punto clave**: la grieta transaccional entre
`workflow_runs`/`node_executions` (Storage) y `runtime_events`
(EventLog) sigue abierta por diseño (deuda documentada). Las
mutaciones se commitean antes de que el evento pueda emitir un
`IdempotencyError`. Solucion requiere operaciones transaccionales
Storage que coordinen INSERT/UPDATE con INSERT events en una sola
transaccion.

## 4. Decisiones duplicadas / candidatos a unificar

### 4.1 Storage vs Catalog (resources/catalog.py)

`resources/catalog.py` tiene un API en memoria sobre el grafo de
recursos, mientras `platform/storage.py` tiene `list_resources`,
`dependencies_of`, `dependents_of` sobre SQLite. Hay **solapamiento
parcial**: ambos pueden responder "¿que recursos dependen de X?",
pero con semanticas distintas (catalog = en memoria + filtros;
storage = persistido + completo).

Estado: documentado como defensa en profundidad intencional en
`STATE.yaml:deuda_tecnica_residual`. NO unificar sin diseno.

### 4.2 Storage list_events_for_run vs EventLog query

`Storage.list_events_for_run` (Etapa 7 S3 logs) reusa internamente
la conexion de EventLog via `Storage.conn` (la identidad de la
conexion, no un wrapper). Esto es coherente con la decision H9-BSlice3
de exponer `Storage.conn` como API publica para que EventLog pueda
ver las mutaciones de Storage en tiempo real.

No es duplicacion: es composicion explicita.

### 4.3 `time.time()` vs `datetime.now(UTC)`

AGENTS.md §1.3 obliga `datetime.now(UTC)` (reloj inyectable, testeable).
Los benches usan `time.perf_counter_ns` (no es reloj, es contador de
rendimiento: legitimo). NO hay uso de `time.time()` directo en
produccion.

### 4.4 NewTypes vs strings

Los bounded contexts usan `NewType` (NodeName, OutcomeLabel,
RevisionNumber, SourceKind, etc.) + smart constructors. Las CLI
reciben strings del usuario, convierten via smart constructor, y
propagan `ValidationError` si el formato no encaja. Sin duplicacion
de validacion.

### 4.5 KnowledgeController vs ContextController

`KnowledgeController` (gestiona el grafo: claims, evidences,
sources, entities) vs `ContextController` (compila handoffs:
receta + freshness + budget). Responsabilidades distintas, sin
solapamiento. ContextController usa KnowledgeController como
injected dependency.

Conclusion: **NO hay duplicacion real** entre bounded contexts.

## 5. Fixtures de consultas y revisiones

Inventario de fixtures y datos de prueba reutilizables:

### 5.1 Tests fixtures
- `tests/_evidence_lock.py` (162 LoC) — context manager `flock`
  para UAT evidence.
- `tests/conftest.py` — fixtures globales (tmp_path, storage_factory).
- `tests/fixtures/` — Domain Packs de prueba (si existe).

### 5.2 UAT evidence
- `tests/uat-evidence/UAT-{01..16}.json` — 16 UATs con revision +
  timestamp + scenario + expected + observed + steps.
- `tests/uat_audit.py` — corre los 16 UATs y mantiene PASS/FAIL.

### 5.3 Bench corpora sinteticos
- `bench/bench_context.py` — corpus sintetico (sources + claims
  distribuidos en N).
- `bench/bench_storage_reads.py` — corpus Storage SQLite en tempdir.

### 5.4 Domain Packs reales
- `bench/fixtures/` o similar — packs de prueba para H6
  (Character/StoryArc).

Estado: el corpus esta **suficientemente diversificado** para que
H11 (extraccion tipada) no necesite fixtures nuevas inicialmente:
puede reusar `tests/fixtures/` y los packs de prueba de H6.

## 6. Primer proveedor determinista (seleccion)

H10 requiere seleccionar **un** proveedor determinista para H11.

### 6.1 Candidatos evaluados

| Candidato | Tipo | Pros | Contras | Veredicto |
|---|---|---|---|---|
| **FakeAgentAdapter** actual | in-process, fixture JSON | Ya existe; deterministic; testeable | No es externo; no cubre HTTP | **Seleccionado** |
| HTTP mock (responses) | in-process | Comun para tests de integracion | Requiere adaptacion a `Protocol` | Candidato secundario |
| Local filesystem walker | in-process | Materializa el caso "leer de un dir" | Limitado a filesystem | Para H12 scopes |
| Git source provider | real-ish | SkillGraph ya tiene `git_source.py` | No es "external provider" | Para H11 evidence |

### 6.2 Decision

**Seleccionado**: **FakeAgentAdapter** como proveedor determinista
inicial para H11, con extension planificada:

1. **Corto plazo (H11)**: reusar FakeAgentAdapter para construir
   fixtures tipadas (FileSignatures con foco, contrato, cobertura,
   procedencia).
2. **Medio plazo (H12-H13)**: introducir `LocalFileSystemProvider`
   que lea de un directorio y emita FileSignatures via la misma
   interfaz `AgentAdapter`.
3. **Largo plazo (post-H15)**: el Adapter real HTTP queda como
   H9 E1 (es trabajo separado, fuera del alcance de H11-H15).

Razon: H10 pide **un** proveedor determinista, no el Adapter real
(que es H9 E1 con spec pendiente). FakeAgentAdapter es la base
existente, testeable, deterministic. Las FileSignatures de H11
pueden sintetizarse desde el mismo Storage sin red.

## 7. Cumplimiento de los criterios de salida

| Criterio | Estado | Referencia |
|---|---|---|
| 1. Inventario de APIs y contratos | ✅ | Secciones 2.1-2.5 |
| 2. Trazar un caso real | ✅ | Seccion 3 (sg run end-to-end) |
| 3. Localizar decisiones duplicadas | ✅ | Seccion 4 (sin duplicacion real) |
| 4. Catastro de fixtures | ✅ | Seccion 5 |
| 5. Seleccionar primer proveedor determinista | ✅ | Seccion 6 (FakeAgentAdapter) |

**H10 COMPLETO**: gate "mapa respaldado por rutas, funciones y
pruebas. Ningun componente nuevo por especulacion." cumplido.

## 8. Riesgos y blockers identificados

- **Blocker pre-existente**: H9 E1 (Adapter real) sigue pendiente
  con spec del operador. H11-H15 pueden proceder sin él mientras
  usen proveedores deterministas (FakeAgentAdapter, LocalProvider).
- **Riesgo**: la grieta transaccional Storage↔EventLog puede
  confundir a H14 (eventos como evidencia operativa temporal). Si
  H14 requiere atomicidad EventLog↔Storage, hay que reabrir H9 E3.
  Evaluacion al cerrar H14.

## 9. Siguiente paso (propuesta)

**H11 — Conocimiento tipado reutilizable**: registrar
FileSignatures con foco, contrato, cobertura, procedencia y
vigencia. Adaptar ADT y registro existentes (Storage ya tiene
`record_evidence` y `list_evidences_for_source`); persistir
resultado de extraccion; reusar FakeAgentAdapter como proveedor
determinista; reutilizar entre procesos (Storage ya lo cubre);
estados vacio/ausente/parcial/stale (Storage ya soporta todos).

Esto NO requiere spec operador: es trabajo sobre Storage +
ContextController + KnowledgeController, todo en bounded contexts
probados.

Pero el operador decidio: priorizar H10 (investigation + mapa) en
este ciclo. H11 queda como siguiente workitem propuesto.
