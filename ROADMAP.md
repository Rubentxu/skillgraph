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

> Bloque vivo: **B0** — Convergencia de verdad
> Versión activa `0.22.5.dev0` · último tag `v0.22.5` · 2844 tests · 16/16 UAT

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
