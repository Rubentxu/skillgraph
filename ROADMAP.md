# ROADMAP — la autoridad única del futuro de SkillGraph

> **Este fichero es la única autoridad del roadmap de SkillGraph.**
> Si algún otro documento dice qué hay que hacer después y se contradice
> con éste, este gana, y el otro es un bug.

Detalle de por qué existe, y de lo que se midió para escribirlo:
`evidence/sddk-b0-2026-10-03.md`.

---

## La regla de este roadmap

Cada bloque tiene **objetivo cerrado**, **valor observable** y **gate fuerte
al final**. Un bloque no se cierra por haber trabajado en él, ni por haber
abierto el número de guards que le corresponden.

La diferencia con lo anterior no es de orden, es de criterio: la serie
WI-91…WI-115 fue **una campaña abierta** —cada workitem nacía de «qué
declara el repo que nada comprueba»— y podía producir trabajo
indefinidamente. B0 y B1 la cierran: B0 la convierte en *un* dato, y B1 la
convierte en un inventario finito. A partir de B2 se vuelve a capturar
capacidad de producto.

**Ningún bloque tiene que emitir una versión.** `scripts/derive_semver.py`
sigue mandando. Se publica cuando el cambio lo justifique, no porque el
bloque se cerrara.

---

## Dónde está el proyecto

> Bloque vivo: **B9** — Gate de 1.0
> Versión activa `0.28.0.dev0` · último tag `v0.28.0` · 3176 tests · 16/16 UAT

Esa línea es la respuesta a *«¿dónde está el proyecto y qué toca después?»*
y la produce `scripts/project_truth.py`, que la imprime en JSON. Ningún otro
script la reconstruye.

## Baseline

`v0.22.5` + WI-115 · 2838 tests declarados · 16/16 UAT · blueprint v1
terminado. Lo que heredamos bien y lo que no, está medido en la evidencia de
B0 y resumido en `docs/history/truth-drift-2026-10-03.md`.

---

## El mapa

| Bloque | Objetivo | Resultado |
|---|---|---|
| **B0** | Restaurar una única verdad del proyecto | Roadmap/estado/docs/código sincronizados |
| **B1** | Cerrar definitivamente stewardship | Contratos importantes comprobables, deuda conocida acotada |
| **B2** | Certificar runtime real | Proveedor real, concurrencia real, crashes reales, recovery real |
| **B3** | Consolidar arquitectura extensible | Core estable + ports/capabilities + controllers |
| **B4** | Ontología + recursos CRD-like | Extensión sin modificar core |
| **B5** | Graph Diff Gate + gobierno de evolución | Cambios de grafo explícitos, comparables y autorizables |
| **B6** | Agent-first determinista | Agente propone; herramientas deterministas observan y persisten |
| **B7** | UX operacional | TUI/GUI de grafos, timeline, evidence y decisiones |
| **B8** | Ecosistema y distribución | Packs, SDK, instalación, upgrades y compatibilidad |
| **B9** | Certificación 1.0 | Release reproducible y production-ready local-first |

El orden es **B0 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9**. B0 y B1
antes de tocar funcionalidad nueva, porque hacerlo sobre verdades que se
contradicen produce trabajo que nadie puede verificar.

---

## B0 — Convergencia de verdad

**Objetivo cerrado.** El repositorio tiene cinco afirmaciones sobre sí mismo
—versión, release, número de tests, workitem vivo y roadmap— y se
contradicen entre sí. Que dejen de contradecirse, y que no vuelvan a
contradecirse en silencio.

**Medido antes de arreglar nada** (`.pipelinek/b0_measure.py`):

```
version activa (__init__.py) : 0.22.5.dev0
release declarada (STATE)    : 0.22.5
tag real (git describe)      : 0.22.5
workitem (STATE)             : WI-96     <- vive 19 workitems atras
workitem (CURRENT)           : WI-115
tests declarados (STATE)     : 2838
tests colectados (arbol)     : 2844      <- el guard de WI-115 esta EN ROJO
```

**Trabajo.**

1. Este `ROADMAP.md` como autoridad única, con el bloque vivo en formato
   legible por máquina.
2. `docs/blueprint/plan/ROADMAP.md` pasa a **histórico**: era el roadmap del
   blueprint v1, no el del proyecto vivo. Se queda donde está y lo dice en
   su primera línea, en vez de mudarse: mudarlo rompe las citas de la
   evidencia vieja, y esa evidencia es provenance.
3. `scripts/project_truth.py`: **una** respuesta machine-readable a *«¿dónde
   está el proyecto y qué toca después?»*. Todo lo demás la consume; nadie
   la reconstruye.
4. `tests/test_b0_truth_convergence.py`: falla si `CURRENT`, `STATE`,
   versión, release, tests o roadmap se contradicen.
5. README: badge de tests, nombre de la CLI (`sg` no es la de este repo), y
   referencias al roadmap.

**Gate B0.** Existe una única respuesta machine-readable a la pregunta, y un
test pone rojo el repositorio si las cinco verdades se contradicen de nuevo.
Sin contrasaltos: si el lector no puede leer una verdad, es un fallo, no un
verde.

---

## B1 — Cierre de stewardship

**Objetivo cerrado.** Terminar la campaña «qué declara el repositorio que
nadie comprueba» con criterio de terminación, no por volumen.

**Inventario sistemático.** Derivar del árbol y de `AGENTS.md` los contratos
de estas categorías, y para cada declaración:

```
DECLARED
   ↓
MEASURABLE?
   ↓
already guarded?
   ↓
mutation/counterexample
   ↓
FIX / REMOVE CLAIM / ACCEPT DEBT
```

Categorías: inmutabilidad · fronteras de adapters · errores dominio ↔
infraestructura · transacciones · recovery · replay/idempotencia · tiempo ·
paths · tenant/project isolation · versionado · serialización · event
ordering · storage boundaries · capabilities · redaction · authorization ·
pack loading · subprocess boundaries.

**Problemas expresos.** Cerrar el acceso SQL directo desde CLI para
`promotion list`. Revisar las dataclasses `frozen` que aún contienen
colecciones mutables y clasificar cuáles son peligrosas. Eliminar
documentación obsoleta de compatibilidad. Revisar excepciones permitidas de
`datetime`, filesystem y SQLite. Comprobar que la separación de bounded
contexts no sea sólo física. Revisar `Storage` como facade: no volver a una
mega-clase, sí verificar que las délégaciones tienen límites coherentes.

**RESULTADO, medido el 2026-10-03** (`.pipelinek/b1_inventory.py` +
`.pipelinek/b1_verdict.py`): 17 contratos inventariados sobre 17 categorías,
1122 sitios medidos, **14 `GUARDED` · 2 `DEUDA` con motivo escrito · 1
`NO-APLICA` demostrado · 0 deuda crítica · 0 citas rotas**. Detalle y los
seis instrumentos que hubo que arreglar:
`evidence/sddk-b1-inventory-2026-10-03.md`.

**El problema expreso que B1 nombra —el SQL directo de `promotion list`— ya
estaba cerrado.** `cli/commands/promotion.py:358` llama a la API pública
`storage.list_promotions()`; lo que quedaba era el README afirmándolo
abierto, y el propio módulo lleva un comentario que dice lo contrario. El
trabajo real de B1 fue encontrar cuatro **medidores rotos** que daban
«cero» o «875» sobre contratos que sí existen — el detalle está en la
evidencia—.

**Stop condition.** B1 termina cuando todo contrato importante está
`guarded`, o explícitamente no garantizado, o es deuda justificada; y quedan
**0 propiedades críticas declaradas pero invisibles**. No se sigue abriendo
workitem para subir el número de guards.

---

## B2 — Runtime real, no representativo

**Objetivo cerrado.** Atravesar la frontera que el propio repositorio admite:
hoy hay escenarios *representativos*, no *aceptados*.

**Proveedor real.** `HttpAgentAdapter` contra al menos un proveedor real, sin
mocks, recorriendo el ciclo entero:

```
workflow → ContextRecipe → handoff → adapter real → AgentResult
        → transición → persistencia → recuperación
```

Credenciales **fuera del repo**; la UAT es **opt-in**.

**Crash real.** Dejar de depender de failpoints. Pruebas en subproceso que
maten el proceso durante creación de run, persistencia de resultado,
`GraphExpansion`, promotion, checkpoint y reconciliación. Después: *restart →
reconcile → exactamente-una-vez*.

**Concurrencia real.** Procesos separados, SQLite real, locks reales: `run/run`,
`promotion/promotion`, `reconcile/reconcile`, `read/write`, `cancel/commit`.
No threads dentro del mismo intérprete.

**RESULTADO, medido el 2026-10-03** (`.pipelinek/b2_crash_child.py`,
`.pipelinek/b2_concurrency_child.py`): **crash real CERTIFICADO** y
**concurrencia real CERTIFICADA — con tres defectos de producción
encontrados por el camino**. Detalle completo en
`evidence/sddk-b2-2026-10-03.md`.

Lo medido ANTES: **cero `SIGKILL` en todo `tests/`** y cero ficheros SQLite
escritos por dos programas a la vez. Toda la superficie de crash eran
failpoints —que lanzan y Python cierra ordenadamente— y toda la de
concurrencia, threads —que el GIL serializa—.

**Crash real** (`SIGKILL` desde dentro del proceso, comprobado sobre el
disco): escribir sin commit → **0 filas** · transacción abierta con dos
filas → **0 filas** · commit y muerte inmediata → **1 fila**.
`integrity_check ok` en los tres. La que importa es la segunda: un
failpoint que hace rollback deja la base tan limpia como un commit, así
que solo apagando el proceso se ve que lo no confirmado desaparece
**entero**. 10 tests, mutaciones 4/4 con 0 sondas inválidas.

**Concurrencia real** (8 procesos, 10 escrituras cada uno, `Storage`
real): **80 de 80 escrituras, cero perdidas**, con tres defectos
arreglados en `platform/storage.py`, **ninguno en el runtime**:

1. `PRAGMA journal_mode = WAL` sin `busy_timeout` mataba procesos al
   construirse — **70 de 80 eventos, diez escrituras perdidas sin dejar
   rastro**.
2. `_migrate` era un *check-then-act* (`SELECT` y, si vacío, `INSERT`) y
   ocho procesos abriendo una base nueva se volcaban en
   `UNIQUE(schema_version.version)`. Resuelto con `INSERT OR IGNORE` y
   borrando el `SELECT`: la constraint resuelve la carrera, que es lo que
   manda `AGENTS.md §8`.
3. El `busy_timeout` no cubría el bloqueo **dentro** de la conversión del
   journal. Resuelto con un reintento acotado que, si falla, deja subir la
   excepción — nunca `except: pass`, que dejaría la base en `delete` sin
   que nadie lo supiera.

**Proveedor real: NO CERTIFICADO, y se dice.** La UAT existe, es opt-in y
está construida (`tests/test_uat_real_provider.py`), pero **no se ejecutó**:
requiere credenciales que este entorno no tiene. Declararlo es el mismo
trabajo que WI-91 hizo con el addendum de H9 — sustituir una afirmación
falsa por otra que nadie ha medido sería el mismo defecto al revés—.

**Lo que el gate de B2 NO puede marcarse todavía.** El bloque pide cinco
pares de concurrencia —`run/run`, `promotion/promotion`, `reconcile/
reconcile`, `read/write`, `cancel/commit`— y aquí se cubren
**escritura/escritura** y **lectura/escritura** a nivel de `Storage`. Los
pares a nivel de *run* y *promotion* necesitan el harness de la CLI y
quedan pendientes. La frase del H7 **todavía no puede marcarse como
probada literalmente**: dos de sus tres patas están, la tercera no.

**Gate B2.** La frase original del H7 —*«escenario real completo con
trazabilidad, aislamiento y recuperación»*— se marca **probada literalmente**,
no «capacidad existente con dobles».

---

## B3 — Core extensible de verdad

**Objetivo cerrado.** Congelar el núcleo que ya funciona y establecer la
frontera de la siguiente generación. **No** construir todavía la ontología.

```
                SkillGraph Core
                     │
          ┌──────────┼───────────┐
          ▼          ▼           ▼
        Ports    Capabilities  Events
          ▲          ▲           ▲
          └────── Controllers ───┘
```

El core provee: resource lifecycle, graph lifecycle, run lifecycle, capability
resolution, policy decision, event/evidence y reconciliation. **No**
implementaciones concretas de herramientas externas.

`KnowledgeQuery`, `CodeAnalysis`, `TelemetryQuery`, `ArtifactRead`,
`AgentExecution`, `SecretAccess` y `ExternalCommand` son **capabilities**,
no imports de CogniCode, Chronos ni ningún producto concreto. Los adapters
las suministran. Así SkillGraph no reconstruye CogniCode, Chronos o secretless.

**Gate B3.** Se puede añadir una capability (tipo, contrato, adapter,
controller opcional, policy, tests) **sin modificar** `RunController`, el
storage base ni el motor del workflow.

---

## B4 — Ontología y recursos CRD-like

**Objetivo cerrado.** Extensión sin modificar el core. No copiar Kubernetes
literalmente, sí su separación: *desired state / observed state / controller /
reconcile / status / conditions*.

```yaml
apiVersion: skillgraph.io/v1
kind: Investigation
metadata:
  name: inspect-storage-boundary
spec: {...}
status:
  phase: Running
  conditions: [...]
```

Los Domain Packs aportan nuevos `kind`, schemas, relaciones y controllers. El
núcleo sigue sin conocer `Character`, `StoryArc`, `SecurityReview` ni
`ReleaseCandidate`.

Los controllers **observan y proponen**; nunca mutan arbitrariamente:

```
observe → derive desired transition → proposal → policy
        → Graph Diff Gate → apply
```

Eso casa con el `GraphExpansion` que ya existe. No se reemplaza: **se
generaliza**.

---

## B5 — Graph Diff Gate

**Objetivo cerrado.** Que toda evolución estructural significativa tenga una
representación comparable, y que el diff sea **semántico**.

```
CURRENT GRAPH ──proposal──▶ CANDIDATE GRAPH ──▶ GRAPH DIFF
```

`+ node` · `- node` · `~ relation` · `~ capability` · `~ policy` · `~ budget` ·
`~ priority` · `~ evidence requirement`. No un diff de YAML.

**Cuatro vistas del mismo sistema** —no cuatro bases de datos, sino cuatro
proyecciones tipadas sobre recursos y relaciones comunes:

```
Execution Graph        Knowledge Graph
Decision/Evidence Graph    Capability/Control Graph
```

El diff responde: ¿qué cambia? ¿por qué? ¿qué evidencia lo justifica? ¿qué
coste añade? ¿qué capacidades exige? ¿qué nodos invalida? ¿es reversible? Y
permite reasignar `attention`, `effort`, `budget`, `spikes` y `priority` sin
convertirlos en lógica hardcodeada del runtime.

**Gate B5.** Ningún cambio estructural importante ocurre sin
`Proposal → Diff → Policy → Decision → Evidence → Apply`.

---

## B6 — Agent-first pero menos dependiente del agente

**Objetivo cerrado.** El agente **no** puebla conocimiento directamente, salvo
en bootstrapping o cuando no hay otra fuente. La dirección es:

```
agente detecta necesidad → solicita capability → herramienta determinista
observa → normalizador produce hechos/evidencias → SkillGraph persiste
relaciones → agente interpreta
```

Ejemplo: el LLM necesita el acoplamiento de un módulo → pide `CodeAnalysis` →
un adapter lo calcula → sale **evidencia estructurada** → al Knowledge Graph.
No: *el LLM analiza el código, inventa la estructura y escribe el grafo*.

Los agentes participan más al principio y delegan progresivamente en
herramientas deterministas. SkillGraph evoluciona hacia **orquestador
epistemológico**, no base de recuerdos del LLM.

**Gate B6.** Cada afirmación importante del Knowledge Graph distingue
`observed` · `derived-deterministically` · `agent-inferred` ·
`human-asserted`, y conserva su provenance.

---

## B7 — UX operacional, no chatbot

**Objetivo cerrado.** **Después** de B2..B6, no antes. La CLI sigue siendo
primera clase; TUI primero y GUI después, sobre las mismas APIs y query
models.

Widgets vivos: `Graph` · `Timeline` · `Evidence` · `Decisions` · `Resources` ·
`Diff` · `Runs` · `Policies` · `Capabilities` · `Knowledge`. Cada uno escala de
summary card a panel a full-screen.

La UX que importa no es conversar con SkillGraph, es **entender qué está
haciendo el sistema y gobernarlo**. Un operador abre un run y ve: nodo actual,
handoff, evidence, capabilities, decisions, graph diff, coste/budget y
timeline. Esto convierte SkillGraph de framework en producto operativo.

**Gate B7.** Los diez widgets existen **sobre las mismas APIs y query models**,
y cada uno escala de summary card a panel a full-screen.

**Bloque vivo. Medido antes de escribir nada**
(`scripts/measure_b7_operational_ux.py`): **3 de 3 preguntas abiertas**. Y el
hueco no era que faltara una TUI, sino la pieza de la que la TUI depende: cero
declaraciones de `--format` en siete módulos de comando, y ningún símbolo en
`src/` que expusiera render. La palabra «las mismas» del gate no tenía a qué
referirse.

**CERRADO Y PUBLICADO como `v0.27.0`** (MINOR por `0/1/1/2/0`, derivado con
`scripts/derive_semver.py`, ninguno con marcador de ruptura). Certificación:
**3085 passed, 3 skipped declarados, 0 failed**. `tests.total` 3088, con el
desglose medido. Entrega `0d9d423`, tag `v0.27.0` en `683dbfc`.

**Cerrado:** `src/skillgraph/presentation/` con `TableView` y `DetailView` como
superficie de render, las diez proyecciones puras en `widgets.py`, y
`--format {text,json}` en `runs list` y `runs show` sobre un único `_emit`.

**Abierto, y no baja el veredicto:** que la TUI sea usable de verdad (P4). Depende
de un terminal y de una interacción humana que el CI no tiene. Lo que sí es
comprobable sin humano —la pieza de abajo— es lo que este bloque mide; que la
TUI sea usable se mide cuando haya alguien usándola.

**Estado del ciclo**: `p-b7740b96d79ec013/b7` está en `BLOCKED`, no `CLOSED`.
Los dos gates de deuda no son evaluables en esta build de SDDK —la detección de
deuda no está implementada—, así que `verify` no puede pasar a `release`. El
trabajo **está** entregado, verificado y publicado; lo que no se puede es cerrar
el ciclo. Mismo bloqueo que `b4` y `b5`.

---

## B8 — Ecosistema y distribución

**Objetivo cerrado.** Con core + ontología + controllers estables, un contrato
claro para:

```
Skill Package · Controller Package · Capability Adapter · Domain Pack
Policy Pack · UI Widget
```

**No** plugins arbitrarios cargados dentro del core. Aislamiento progresivo
según riesgo: `declarative → subprocess → sandbox`.

También: `mise` · `asdf` · `uv tool` · PyPI · paquete standalone si compensa ·
upgrade/migración · install/update/remove de packs · matriz de compatibilidad.
Con formato explícito:

```yaml
requires:
  skillgraph: ">=0.30,<1"
  capabilities:
    - code.analysis.v1
```

**Bloque vivo. El enunciado enumera siete frentes y este es el primero.**

Este bloque mide y entrega **el manifiesto**, que es la pieza de la que los
otros seis cuelgan: sin `requires` declarado no hay versión que comparar, sin
un contrato versionado no hay `upgrade`, y sin contrato no hay
`install`/`update`/`remove` que valga como algo más que copiar ficheros.

Medido antes de escribir nada (`scripts/measure_b8_package_contract.py`):
**5 de 5 preguntas abiertas**. No había manifiesto —solo un `Brick` con
`kind="DomainPack"`, que es el contrato de *tipos*, no el de *paquete*.

**Entregado:** `src/skillgraph/packaging/` con `PackManifest`, `Requires`,
`CapabilityRequirement`, los seis tipos en `PACK_KINDS` **derivados por
`get_args`**, los tres niveles de aislamiento **en orden creciente**, y
`es_compatible` / `exigir_compatible` que responden **con motivos y no con un
`bool`**.

La costura ya estaba puesta: B3 dejó `CAPABILITY_VERSION` en el puerto con un
docstring que dice que está ahí «para que `requires.capabilities` de B8 tenga
algo que versionar».

**Abierto, y no baja el veredicto:** que un pack se instale de verdad en una
instalación real (P6). Depende de un registro remoto y de una política de
fijación que el CI no tiene. Lo comprobable sin red es el contrato.

**Siguen abiertos para los siguientes bloques del mismo roadmap:** la
distribución real (`mise`/`asdf`/`uv tool`/PyPI), el `upgrade` sobre este
contrato, el `install`/`update`/`remove` de packs, la matriz de compatibilidad
—que este manifiesto ya puede generar— y el aislamiento *ejecutable*
(`subprocess` y `sandbox` son hoy campos declarados, no mechanisms).

---

## B9 — Gate de 1.0

**Objetivo cerrado.** 1.0 **no** se define por número de funcionalidades, se
define por propiedades. `v1.0.0` solo existe cuando se cumplan **todas**:

```
roadmap/state/docs coherentes          resource/controller API estable
blueprint legacy completamente probado  Graph Diff Gate operativo
runtime real certificado                ontology extensible
crash/recovery real certificado         provenance fuerte
concurrencia real certificada           capabilities deterministas
core sin dependencias de impl. externa  CLI estable
                                          TUI operacional
migrations probadas                     pack/controller lifecycle
backups/restore probados                upgrade desde releases soportadas
security/threat model actualizado       distribution reproducible
UAT agent-first completa
```

Luego un período RC: `1.0.0-rc.1 → bug fixes only → 1.0.0-rc.2 si hace falta
→ certification → 1.0.0`. **Nada de features entre RC y final.**

---

## Documentos que ya NO son autoridad

Esto es lo que B0 arregla, y queda escrito para que nadie los vuelva a leer
como si lo fueran:

| Documento | Qué es | Dónde está la verdad |
|---|---|---|
| `docs/blueprint/plan/ROADMAP.md` | El roadmap del **blueprint v1**, congelado | histórico, para saber de dónde venimos |
| `external/blueprint-v1/` |Canon de producto/arquitectura de la v1 | sigue siendo canon **de la v1** |
| `external/evolution-v2/` | La línea H10..H15, cerrada al 100 % | historia de una línea ya cerrada |
| `CURRENT.md` | La ventana sobre el bloque **actual** | su bloque vivo, contrastado contra los demás |
| `STATE.yaml` | Estado estructurado | contrastado contra el árbol y el roadmap |
| `README.md` | Cómo se usa y en qué punto está | el punto, en `scripts/project_truth.py` |

`CURRENT.md` y `STATE.yaml` no desaparecen: se vuelven **verificables**. Es
la diferencia entre una segunda fuente de verdad y una ventana que se
contrasta con la primera.
