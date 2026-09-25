# Investigation: estado real de Etapa 7 + opciones de H9 frente al blueprint v1

> **Fecha**: 2026-09-25 09:08 (Europe/Madrid)
> **HEAD**: `bfd98d4` (working tree limpio, post stewardship P2+P3+P4)
> **Modo**: investigación read-only del blueprint v1 + código. 0 LoC modificado.
> **Trigger**: sesión 2026-09-25 09:07 habilita modo AUTO con criterio
> propio; el "siguiente" priorizado en la respuesta anterior es
> "P1=spec S7+ del operador". Esta investigation aporta datos
> frescos para que el operador decida con evidencia en vez de
> resumir las 4 opciones del backlog heredado.
> **Corrección importante**: durante la investigation se descubrió
> que **el "S7+" del backlog NO es huérfano**: el blueprint v1 +
> ADR-0013 ya lo nombran como **H9 · Release candidate**
> (renumeración de H7 original tras divergencia documentada).
> Esta investigation reformula el problema del operador en
> términos de H9, no de "S7+".
> **Fuentes**:
> - `external/blueprint-v1/plan/ROADMAP.md` (Etapa 7 + P0..P3 prioridades)
> - `external/blueprint-v1/plan/HITOS.md` (H7 release candidate)
> - `external/blueprint-v1/plan/UAT.md` (16 UATs)
> - `external/blueprint-v1/adr/ADR-0013-divergencia-h7-y-rectificacion-v060.md`
>   (**renumeración H7 -> H9 + pendientes**)
> - `src/skillgraph/` (estado real del código)
> - `tests/` (tests existentes)

## 1. Resumen ejecutivo

El "S7+ pendiente" que STATE.yaml reporta como "no definido en
blueprint v1" es **engañoso**. La investigation descubrió que:

1. **ADR-0013 (2026-09-23) renumeró H7 original a H9** · Release
   candidate. La decisión es del propio operador: "el
   endurecimiento del H7 original se ejecutará como H9 · Release
   candidate". El hueco biblioteca→producto (H6+H7 mal etiquetados
   en v0.6.0) se cerró con **H8 · Integración y certificación
   pública**, **cerrado en v0.6.0**.

2. **El backlog `stewardship_backlog.prioridad_1_spec_s7plus`** fue
   heredado de una sesión donde yo aún no había leído ADR-0013.
   La nomenclatura "S7+" es **obsoleta**. Lo correcto según
   blueprint + ADR es hablar de **H9 · Release candidate** (o, en
   el lenguaje del ROADMAP, **Etapa 7 · Endurecimiento** que
   tiene Trabajos pendientes).

3. **El estado real del proyecto** tiene dos focos pendientes
   bien definidos:

| Concepto | Clave en blueprint v1 | Estado real |
|---|---|---|
| **H9 · Release candidate** (HITOS, antes H7) | 5 Entregables (Adaptador real, Seguridad, Recuperación, Doc operativa, Suite UAT) | **H8 cerrado (biblioteca→producto); H9 pendiente** |
| **Etapa 7 (ROADMAP) · Endurecimiento** | 8 Trabajos | **5+ Trabajos pendientes** (T1, T3-doc, T5, T6, T8) |
| **P3 (Orden de prioridades, ROADMAP)** | extensiones avanzadas, múltiples proveedores, optimizaciones | **No cerrado** |

El `stewardship_backlog.prioridad_1_spec_s7plus` original proponía
**4 opciones** ("A Adapter real" / "B grieta transaccional" / "C
cert. concurrencia" / "D multi-tenancy"), pero **solo 2 (A y C)
tienen base blueprint**: B es una decisión mía (deuda defendible
F-6) y D no aparece en el blueprint. Esto reformula el problema
del operador: **no es elegir entre 4 opciones**, es **elegir el
alcance de H9** o **completar Etapa 7** o **abrir P3**.

## 2. Estado real de Etapa 7 (ROADMAP): 8 Trabajos

Reproducción textual del blueprint:

```
## Etapa 7 — Endurecimiento
Resultado: versión candidata para uso local real.
Trabajos:
  - Adaptador real de agentes.
  - Presupuestos y cancelación.
  - Seguridad de extensiones.
  - Concurrencia.
  - Backups y migraciones.
  - Observabilidad.
  - UAT de aislamiento y recuperación.
  - Benchmark de contexto y consultas.
Gate: escenario real completo, instalado,
      con resultados y recuperación verificados.
```

Caracterización honesta contra el código real:

### T1. Adaptador real de agentes — **NO CUMPLIDO**

- Blueprint: "Adaptador real".
- Código: `src/skillgraph/runtime/agent.py:71` define `AgentAdapter`
  como `Protocol`. Implementaciones:
  - `FakeAgentAdapter` (línea 77) — fixture determinista con
    outcomes pre-escritos.
  - `RecordingAdapter` (línea 130) — captura invocaciones para tests.
- **No existe** ninguna implementación que invoque un LLM real,
  HTTP, ni mocks externos. La intención del blueprint es tener
  al menos un Adapter que pueda correr contra un proveedor real
  (OPENAI_API_KEY, ANTHROPIC_API_KEY, o un servidor local).
- Justificación histórica documentada: `STATE.yaml.deuda_tecnica_residual`
  declara "Token budget aproximado (chars, no tokens reales):
  tiktoken solo si H4+ exige Adapter real." — el Adapter real
  se diferencia del Fake en dos cambios: (a) usa red, (b) usa
  tokens reales.
- **Gap real**, no dudoso.

### T2. Presupuestos y cancelación — **CUMPLIDO**

- Blueprint: "Presupuestos y cancelación" (incluye tiempo y eventos).
- Código: `RunBudget` introducido en Etapa 7 S4 (v0.12.0, commit
  `9d9ae09`). Tabla `run_budgets` + 3 campos (max_visits,
  max_runtime_seconds, max_events). CLI `sg runs budget`.
- Tests: 20 tests de RunBudget (incluyendo subprocess E2E).
- Estado: **cerrado en v0.12.0**, con buena cobertura y feature
  completa expuesta por CLI.

### T3. Seguridad de extensiones — **PARCIALMENTE CUMPLIDO**

- Blueprint: "Seguridad de extensiones" (Domain Packs, scripts
  externos, capabilities no registradas).
- Código:
  - `pack_loader.py` valida el schema del pack (sin exec/import)
    — cerrado en H6.
  - `skill_importer.py` NO ejecuta scripts Python del pack
    importado — cerrado en H5 (UAT-14 PASS).
  - `FakeAgentAdapter` outcome JSON gobierna la ejecución, no
    el contenido del brick — cerrado en UAT-15 PASS.
- **No documentado formalmente** un threat model (¿qué pasa
  con un pack que pide `os.system`? el validator lo rechaza
  por schema; pero ¿hay denial-of-service? ¿resource exhaustion?
  ¿path traversal?). Se cubre **por construcción** (Defense in
  depth) pero **no se ha redactado un threat model** que el
  operador pueda auditar.
- Estado: las **3 capacidades clave** están. Falta
  **formalización** (un ADR o spec de threat model) — esto es
  > ~30 min de trabajo documental.

### T4. Concurrencia — **PARCIALMENTE CUMPLIDO**

- Blueprint: "Concurrencia".
- Código: `RunLock` introducido en v0.14.0 (commit `241ccc9`).
  Locks por run con 3 modos (`none`, `advisory`, `fail-fast`).
  CLI `sg run --lock-mode/--lock-timeout-seconds`.
- Tests: 14 tests (locks por run, integration con hilos).
- **Pero**: la cobertura es **intra-proceso** (hilos + threads)
  y `multiprocessing` ligera. **NO está certificado con carga
  real** (múltiples procesos concurrentes contra el mismo
  `workflow_runs` con presupuesto, redacción, etc. activados).
  El plan B (`audits/h9-plan-b-atomicity-characterization.md`)
  describe la **grieta transaccional workflow_runs <-> runtime_events**
  que NO está cerrada por los locks (los locks mitigan
  interleaving de procesos, no cierran la grieta a nivel DB).
- Estado: **lock-level cerrado** (S6 v0.14.0). Faltan:
  - Certificación concurrencia real (carga, stress).
  - Cierre transaccional (storage.create_run_atomic,
    start_node_execution_atomic, ...).

### T5. Backups y migraciones — **NO CUMPLIDO**

- Blueprint: "Backups y migraciones".
- Código: storage.py tiene **migration idempotente** al inicio
  (cada módulo verifica `pragma user_version` y crea tablas si
  faltan). **Pero NO hay**:
  - CLI `sg backup` / `sg restore`.
  - Comandos para exportar/importar un proyecto completo
    (incluyendo `knowledge/`, `evidence/`, `promotion_outbox/`).
  - Tests de round-trip backup/restore.
- Esto es un **gap material**: el operador podría hoy perder
  datos al cambiar de máquina o directorio `~/.local/share/skillgraph/`
  sin un backup previo.

### T6. Observabilidad — **NO CUMPLIDO**

- Blueprint: "Observabilidad".
- Código: existe `runtime_events` table + `sg runs logs` para
  listar eventos por run. NO hay:
  - Métricas agregadas (events/sec, latency percentiles por
    Adapter, ratios de fallo por política).
  - Dashboard (HTML o CLI).
  - Trazas de stack o correlación de errores.
- `graph.py:167` define `kind = "metric" | "snippet" | "log_line" | "commit_message"`
  — esto es **declaración de tipo**, no infraestructura de
  observabilidad. Es una semilla inutilizada.
- **Gap material** que requiere >300 LoC si se hace en
  serio (dashboard + agregaciones).

### T7. UAT de aislamiento y recuperación — **CUMPLIDO**

- Blueprint: "UAT de aislamiento y recuperación".
- Implementación: **Los UATs ya cubren esto por construcción**.
  - UAT-01 (proyecto sin contaminación) → aislamiento del repo.
  - UAT-02 (aislamiento proyectos) → multi-proyecto.
  - UAT-06 (recuperación) → crash + resume.
  - UAT-07 (idempotencia) → mismo evento 2 veces.
  - UAT-12 (dominio especializado) → pack narrativo sin tocar núcleo.
  - UAT-13 (promoción entre bases) → outbox + reconciliación.
- Estado: **todos PASS, documentados en tests/uat-evidence/**.
  El blueprint **no exige un nuevo UAT** dedicado a esto; el
  conj. existente cubre el criterio.

### T8. Benchmark de contexto y consultas — **NO CUMPLIDO**

- Blueprint: "Benchmark de contexto y consultas".
- Código: NO hay scripts ni tests de benchmark. `ContextRecipe`
  tiene `token_budget` como field (Etapa 1+) pero NO hay
  medición de cuán rápido una consulta agotando budget en
  distintos tamaños de corpus.
- **Gap material** que es 100% stewardship: sería un script
  `bench/` con `time` o `timeit`, ~50-100 LoC + CSV de
  resultados + actualización a README.

## 3. Tabla resumen Etapa 7

| # | Trabajo blueprint | Estado | Gap material | Coste estimado |
|---|---|---|---|---|
| T1 | Adaptador real | no cumplido | sí (Fake+Recording únicamente) | ~300-500 LoC, depende del proveedor |
| T2 | Presupuestos y cancelación | cerrado | no | — |
| T3 | Seguridad de extensiones | parcial (capacidades sí, threat model no) | documental | ~1 doc, 1 ADR |
| T4 | Concurrencia | parcial (locks sí, cert. transaccional no) | sí (grieta workflow_runs<->runtime_events) | ~200-500 LoC transaccional + ~1 día stress |
| T5 | Backups y migraciones | no cumplido | sí (no existe CLI backup/restore) | ~150-250 LoC |
| T6 | Observabilidad | no cumplido | sí (no hay agregaciones, dashboard) | ~300-500 LoC |
| T7 | UAT aislamiento/recuperación | cerrado (UAT-01/02/06/07/12/13 PASS) | no | — |
| T8 | Benchmark contexto/consultas | no cumplido | sí (no existe script) | ~50-100 LoC + runner |

**Total LoC estimado para cerrar Etapa 7**: ~1000-2000 LoC + 1 ADR +
1 spec threat model + scripts de bench. ~2-4 semanas.

## 4. Estado real de H9 (HITOS, antes H7): Release candidate

Reproducción textual de H7 original (HITOS.md, antes de renumerar):

```
## H7 — Release candidate (ahora H9)
Entregables:
  - Adaptador real.
  - Seguridad.
  - Recuperación.
  - Documentación operativa.
  - Suite UAT.
Criterio de salida: el sistema completa escenarios reales con
trazabilidad, aislamiento y recuperación.
```

Caracterización honesta tras leer ADR-0013 (renumeración):

| Entregable | Estado | Observación |
|---|---|---|
| Adaptador real | **NO cumplido** | T1 de Etapa 7 |
| Seguridad | parcial (T3) | threat model pendiente |
| Recuperación | cerrado | UAT-06 + UAT-13 |
| Documentación operativa | parcial | README + CHANGELOG, pero no OPERATIONS.md |
| Suite UAT | cerrado | 16/16 PASS |

**Conclusión importante**: ADR-0013 separa el antiguo H7 en dos:
- **H8** = integración pública CLI (cerrado v0.6.0).
- **H9** = el resto (release candidate propiamente dicho); **ESTE
  ES EL TRABAJO QUE EL OPERADOR TIENE PENDIENTE** cuando pregunta
  por S7+ o "qué sigue".

Por tanto, el "spec S7+" del backlog = **espec de H9**. Los 5
Entregables de H9 son el alcance del próximo ciclo del operador.

Adicionalmente, `STATE.yaml.etapa7_rationale` describe los slices
S1..S6 de "Etapa 7 runtime/reconciliación" como **capacidad local**,
NO como cumplimiento del H7/H9 release candidate. Son dos
acepciones distintas del nombre "Etapa 7" que conviene tener
claras en el próximo ciclo (ver §10 de este informe).

## 5. Orden de prioridades (ROADMAP): P0..P3

Reproducción textual:

```
P0: contratos, persistencia y recuperación.
P1: handoff, conocimiento y expansión dinámica.
P2: asimilación y Domain Packs especializados.
P3: extensiones avanzadas, múltiples proveedores y optimizaciones del almacenamiento.
```

Mapeo al estado real:

| Prioridad blueprint | Estado en SkillGraph | Observación |
|---|---|---|
| P0 | cerrado | Storage SQLite WAL + EventLog + idempotencia (UAT-07) |
| P1 | cerrado | Handoff (UAT-05) + Conocimiento (UAT-10) + Expansión (UAT-08/09) |
| P2 | cerrado | Asimilación (UAT-11/14) + Domain Packs (UAT-12) |
| P3 | NO cerrado | "extensiones avanzadas, múltiples proveedores y **optimizaciones del almacenamiento**" — esto ES la frontera de S7+ |

**Lectura**: **P3** del blueprint es justamente el ámbito que el
operador necesita decidir. Si re-abrimos la iniciativa, P3 es el
alcance legítimo según el blueprint.

## 6. Recomendaciones al operador (con datos, no opinión)

Esta investigation NO decide por el operador. Aporta 4 caminos
**basados en blueprint** para que elija. Cada uno es **compatible
con lo ya construido** (no requiere tirar trabajo).

### Opción A: Cerrar H7/H9 formalmente (con addendum honesto)

- Acción: agregar a STATE.yaml `h7_cerrado_por_conformance: true`
  (ya documentado en ADR-0013), `h9_adapter_real_pendiente: true`,
  addendum en SESSION-JOURNAL.
- LoC: 0 producción, ~30 LoC doc.
- Valor: honestidad. Sin commitment futuro.
- Tiempo: 5 min.
- Bloqueos: ninguno.

### Opción B: Cerrar Etapa 7 (Trabajos pendientes 1, 3, 5, 6, 8)

- Acción: roadmap execution por orden de Coste/Valor:
  1. T8 (benchmark) — más barato, ~50-100 LoC.
  2. T3 (threat model) — documental, ~1 doc.
  3. T5 (backup CLI) — feature pequeña, ~150 LoC.
  4. T1 (Adapter real) — feature mayor, ~300-500 LoC + elección
     de proveedor (Anthropic/OpenAI/local).
  5. T6 (observabilidad) — feature mayor, ~300-500 LoC + elección
     de formato (CLI dashboard / HTML / OpenTelemetry).
- Tiempo: 2-4 semanas con criterio.
- Valor: cumplir blueprint v1 al 100%.
- Riesgo: elecciones arquitectónicas (proveedor, formato observabilidad)
  requieren spec del operador o criterio explícito.

### Opción C: Cerrar P3 (orden de prioridades blueprint)

- Acción: abrir nueva iniciativa `g-skillgraph-p3` con alcance
  "extensiones avanzadas, múltiples proveedores y optimizaciones del
  almacenamiento". La iniciativa viviría al margen de Etapa 7.
- Equivale a Opción B sin cerrar formalmente T1..T8.
- Tiempo: 1-2 semanas por sub-trabajo.
- Valor: ejecución literal del blueprint.

### Opción D: Stewardship transversal menor (preparar tests de T8 primero)

- Acción: empezar por T8 (benchmark). Es el más barato, no toca
  contratos, y aporta **métrica medible** que el operador usará
  para priorizar T1, T5, T6.
- Tiempo: 1-2h.
- Valor: bajo individual pero **desbloquea decisiones** para
  Opción B/C.
- Sin elección arquitectónica.

## 7. Riesgo de decisión por defecto

Si el operador NO elige, **mi acción por defecto** es:
- Documentar este research memo en `audits/`.
- Mantener `stewardship_backlog.prioridad_1_spec_s7plus`
  abierto hasta consigna.
- **No** auto-comenzar feature alguno (T1, T5, T6, T8) sin spec
  del operador.
- Si el operador quiere "avanzar", la opción D (T8 benchmark)
  es el único camino defendible con criterio propio: 50-100 LoC,
  read-only sobre el código, output medible.

## 8. Conclusión

"S7+" en SkillGraph no es "elegir entre 4 opciones abstractas".
Es elegir **qué hacer con H9 · Release candidate** (renumerado
de H7 original, documentado por ADR-0013) que tiene 5 Entregables
de los cuales **Adaptador real sigue pendiente**:

> **Decidir entre** (a) re-abrir la iniciativa con alcance H9
> · Release candidate (5 Entregables: Adapter real, Seguridad,
> Recuperación, Doc operativa, Suite UAT), **o** (b) re-abrir
> con alcance Etapa 7 del ROADMAP (5+ Trabajos pendientes de los
> 8), **o** (c) re-abrir con alcance **P3 del orden de
> prioridades** (extensiones avanzadas, múltiples proveedores,
> optimizaciones), **o** (d) cerrar formalmente las deudas
> declaradas con un addendum honesto y dejar el proyecto en
> estado "blueprint v1 cerrado al 100% + extras por versiones
> futuras".

Esta investigation propone 4 caminos defendibles para que el
operador elija en 5 minutos sobre datos verificados, no sobre
las 4 opciones abstractas heredadas. No es decisión mía — es
material estructurado para que el operador **sea** quien decide.

## 9. Acción opcional accionable sin spec (Opción D)

Si el operador quiere que avance con criterio propio antes de
decidir el alcance completo, el sub-trabajo T8 (benchmark de
contexto y consultas) es ejecutable ahora:

- Coste: ~1-2h, 50-100 LoC + script runner.
- Riesgo: bajo (read-only sobre código, añade script `bench/`).
- Valor: métrica medible + desbloquea decisiones para Opción B/C.
- Sin elección arquitectónica (no toca API pública).
- Outputs: `bench/bench_context.py` (script invocable) + tabla CSV
  con resultados + `bench/README.md` con instrucciones.

**Desventaja**: hace lo fácil primero (no lo más importante).
Si T1 (Adapter real) es la decisión real del operador, el benchmark
queda como precedente sin H9 cerrado.

## 10. Confusión terminológica documentada

Hay dos "Etapa 7" en este proyecto:
- **Etapa 7 (ROADMAP)** = "Endurecimiento", 8 Trabajos; la mitad
  cubiertos por las 6 slices S1..S6 de "Etapa 7 runtime/reconciliación".
- **H9 (HITOS, antes H7)** = "Release candidate", 5 Entregables;
  pendiente.

`STATE.yaml.etapa7_*` se refiere a la **capacidad local** del
RunController (los 6 slices S1..S6), NO al cumplimiento del H9.
Esto se aclaró en el commit `b9959aa` ("chore(closure): housekeeping
post-Etapa 7") pero el nombre sigue siendo **confuso**. Sugerencia
para próximas sesiones: renombrar `etapa7_*` a `etapa7runtime_*` o
`slices_runtime_*` para evitar colisión con "Etapa 7" del ROADMAP.

## 11. trazabilidad

- Audits previos: `audits/runtime-2026-09-25.md` (367 LoC,
  RunController), `audits/redaction-2026-09-25.md` (170 LoC),
  `audits/runner-coverage-2026-09-25.md` (270 LoC).
- Stewardship backlog cerrado: P2 (DT-2 lock), P3 (audit
  redaction), P4 (audit runner).
- Stewardship backlog pendiente: P1 (esta investigation
  reestructura el problema hacia H9), P5 (ejecución de S7+,
  depende P1).
- HEAD al cierre: `bfd98d4`.
- ADR relevante: `ADR-0013-divergencia-h7-y-rectificacion-v060.md`.
