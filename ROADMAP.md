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

> Bloque vivo: **B16** — Dos propiedades del gate daban PASS sin nada que comparar
> Versión activa `0.32.1.dev0` · último tag `v0.32.1` · 3301 tests · 16/16 UAT

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
| **B10** | Superficies públicas certificadas | Superficie declarada, versionada y sin moverse: núcleo y CLI |
| **B11** | Ciclo de vida de packs | `install`/`update`/`remove`/`list` sobre el contrato de B8 |
| **B12** | Upgrade entre releases | La versión del esquema es un hecho consultable, y subir una base vieja tiene nombre |
| **B13** | El modelo de amenaza que se sostiene | Cada «cerrado» del STRIDE nombra su prueba, y hay una fuga cross-tenant que se arregla |
| **B14** | La autoridad de coherencia se puede engañar | El estado tiene una sola lectura, y una clave repetida ya no pasa por alto |
| **B15** | Un predicado que se declara leyendo código no sabe cuándo deja de medir | El gate dice de qué tipo es la evidencia de sus veinte propiedades, y la reproducibilidad se comprueba en vez de afirmarse |
| **B16** | Dos propiedades del gate daban PASS sin nada que comparar | El vacío no sale verde, el núcleo no puede depender de un recurso, y ocho procesos que abren la misma base no se matan entre ellos |

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

**Medido** con `scripts/measure_b9_gate_1_0.py`, que deriva las veinte del
propio roadmap y ejecuta un predicado por cada una: **13 PASS · 6 OPEN ·
1 NO_MEASURABLE**, `listo_para_1_0: false`. Dos de las seis `OPEN` eran
`resource/controller API estable` y `CLI estable`, y las dos abiertas por
falta de certificación, no de código. Las cierra **B10**.

---

## B10 — Superficies públicas certificadas

**Las dos propiedades que B9 dejó abiertas, y el motivo por el que estaban
abiertas.** `skillgraph.core` no declaraba `__all__` — un paquete sin
superficie declarada no tiene nada que pueda decir que es estable— y no
existía el snapshot de la CLI: once comandos de primer nivel podían
cambiar sin que nada lo notara.

**Lo importante no es lo que hace, es lo que se le opone.** Las dos se
cerraban en veinte segundos: se escribía un `__all__` y se hacía `touch`
sobre el fichero de la declaración. Los predicados de B9 comprobaban la
**existencia** del fichero, y un `is_file()` es lo más fácil de falsificar
que hay. Un `touch` les daba `PASS` a los dos, con el gate de 1.0
exactamente igual de lejos.

Por eso el guard **ejecuta** la comparación en vez de mirar el fichero, y
las dos superficies se **generan desde el árbol** con `--actualizar`.

**Cerrado:**

1. `src/skillgraph/core/__init__.py` declara `__all__` con los **60
   símbolos** de los tres módulos del núcleo, **derivados** de sus `__all__`
   y no escritos a mano, y los reexporta **por identidad**
   (`core.ValidationError is core.errors.ValidationError`): si el núcleo
   recreara la clase, el `except` que escribe un consumidor y el que lanza
   el núcleo serían dos clases distintas.
2. `scripts/check_public_surfaces.py` — cuatro contratos, capa pura
   (`evaluar_*`, sin disco ni imports) sobre capa de efecto (`medir`).
   `--actualizar` genera; sin él, compara y sale 1 nombrando los
   incumplimientos.
3. `surfaces/core-surface.json` y `surfaces/cli-surface.json`, **generados**.
   Viven fuera de `docs/` porque `docs/*` está en `.gitignore` salvo tres
   carve-outs, y un snapshot que no viaja no declara nada — el defecto que
   B8 midió con el hijo de concurrencia. El guard lo comprueba contra
   `git ls-files`, por fichero.
4. Los dos predicadores de B9 **ejecutan** el guard y deciden por su código
   de salida. Verificado en las cuatro direcciones: snapshot vacío → `OPEN`
   en las dos · comando quitado del snapshot → `OPEN` · superficie real
   movida → `OPEN` · estado de verdad → `PASS` en las dos.
5. `public-surfaces` como etapa de la receta canónica. Lo decidió el propio
   guard WI-98, que exige que todo checker del repo lo invoque.

**Defecto del propio guard, medido al escribirlo.** La primera versión
comparaba los comandos de la CLI en **una sola dirección**
(`reales - declarados`): añadir un comando *inventado* al snapshot pasaba
en verde. Un guard que solo sabe detectar que el árbol creció no vigila la
declaración, y la declaración es lo que dice «esto es lo que hay».

**MEDIDO, 15 PASS · 4 OPEN · 1 NO_MEASURABLE.** Durante el bloque, y con el
`tests.total` todavía sin actualizar, la cuenta intermedia fue 14/5: el
`OPEN` que sobraba era `roadmap/state/docs coherentes`, que es precisamente
el `tests.total` (estado 3176, árbol 3195). Puesta la cifra con el run
ejecutado, esa propiedad vuelve a `PASS` y quedan cuatro.

Las cuatro `OPEN` que quedan **no dependen de certificación**: piden código
que todavía no existe (`pack/controller lifecycle` —`sg pack` expone
`import` y `load`, no `install`/`update`/`remove`— y `upgrade desde
releases soportadas`), o dependen de algo externo (`runtime real
certificado`, que necesita `SG_UAT_REAL_PROVIDER=1` y una credencial), o de
una decisión de redacción (`security/threat model actualizado`: el ADR-0015
se aprobó describiendo un proyecto de 830 tests y 17 releases, y el árbol de
hoy colecta 3195).

---

## B11 — Ciclo de vida de packs

**La primera de las `OPEN` que piden código, no certificación.** El
predicador del gate decía, textual: `sg pack` expone `['import', 'load']` y
no `['install', 'update', 'remove']`. B8 entregó el **contrato**; faltaba la
mitad: saber **qué hay instalado**.

**Medido antes de escribir nada** (`scripts/measure_b11_pack_lifecycle.py`):
**5 de 5 preguntas abiertas**. El instrumento **ejecuta** la CLI en un
proyecto de verdad en vez de mirar nombres — un predicado que comprueba tres
nombres fijos dice «cumple» el día que alguien escriba los tres en el parser
sin que exista el ciclo entero. Al final: **5 PASS**.

**Cerrado:**

1. `skillgraph.packaging.registry` — el registro, con `instalar`, `actualizar`
   y `retirar` como funciones **puras** sobre un valor inmutable.
2. `sg pack install|update|remove|list`. `install` **rechaza** un pack
   incompatible nombrando la cláusula que falló; `update` exige que la
   versión **suba**, y la compara **por número** (`0.10.0` > `0.9.0` como
   número y `<` como texto); `remove` de lo que no está lo dice con la lista
   de lo que sí; `list` responde versión y aislamiento.
3. La tabla `installed_packs` y su repositorio, con el patrón lazy+cacheado
   de ADR-0016/WI-56.

**Un defecto de producción, y es el que hacía el `update` imposible.**
MEDIDO: `upsert_resource` **rechaza** cambiar el `spec` bajo la misma
identidad con `IdentityConflictError` —deliberado, es lo que hace un recurso
inmutable—, y un update de pack es por definición un `spec` distinto bajo la
misma identidad. No es un bug heredado: es que **una instalación no es un
recurso**. El recurso es el *contenido* del pack; la instalación es el *hecho*
de que ese pack esté vivo en este proyecto, y ese hecho tiene su propio ciclo.

**`retirar` no borra: marca.** Un `DELETE` perdería la única respuesta que
existe a «¿este proyecto ha tenido alguna vez este pack?», porque el único
sitio donde vive la respuesta es la fila que se borra. Marcar es el `DELETE`
más su historia.

**Y un hallazgo sobre un filtro que no filtra.** `list_resources` construye
su filtro de `kind` como `AND api_version || '/' || kind = ? OR kind = ?`,
**sin paréntesis**, luego el `OR` se come el `AND` que lo precede. Delegar el
aislamiento en ese filtro habría costado una fuga entre tenants; por eso se
comprueba fila a fila, y hay dos guards que lo verifican en las dos
direcciones.

**Harness 6/6 con 6 causas distintas**, y **tres de sus fallos fueron del
harness, no del código**: `MUTABLES` no incluía el repositorio, así que esa
sonda mutó el fichero y no lo restauró — y el harness reportó «árbol
restaurado» porque **la suite seguía verde**, que es el fallo de B9 repetido
con otro disfraz. Por eso el veredicto final mira ahora las dos cosas: que
la suite pase *y* que `git status` de los mutables esté limpio. Además, la
sonda que apuntaba al filtro de estado del SQL —**redundante**, porque
`RegistroDePacks.instalados` vuelve a filtrar— no tenía nada que un test
pudiera ver, y dos expectativas estaban mal escritas, una nombrando la clase
equivocada.

**Un hueco de cobertura real**, que la sonda de compatibilidad destapó: el
recorrido de la CLI instalaba packs *compatibles*, luego el camino que ve el
operador no estaba cubierto para el caso que duele. Dos tests lo cubren.

Fuera de alcance y registrado: la instalación **no declara los tipos** del
pack —de eso se encarga `sg pack load`, que ya existe—. Uno administra la
*instalación* y el otro el *contenido*, porque dos comandos que hacen lo
mismo con nombres distintos son la trampa de «conectar no es contener».

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

---

## B12 — Upgrade entre releases

**La segunda de las `OPEN` que piden código.** El predicado del gate decía,
textual: *«no existe ninguna función de upgrade o de migración de datos entre
releases: no hay de dónde subir una base creada por una versión anterior»*. La
medición dijo que el problema era más profundo que «falta la función».

**Medido antes de escribir nada** (`/tmp/b12_measure.py`, y después
`scripts/measure_b12_schema_upgrade.py`): **0 de 5 preguntas en PASS**.

| hecho | dónde | por qué importa |
|---|---|---|
| `SCHEMA_VERSION = 1` | `platform/schema.py` | sin moverse en 73 releases |
| `INSERT OR IGNORE INTO schema_version` | `platform/storage.py` | se escribe y **nadie lo lee** en `platform/` |
| base sin `schema_version` | se abre igual | el código la recrea: la reparación es invisible |
| `_anade_column_claims_assertion_origin` | `platform/storage.py` | una función escrita a mano **para una tabla** |

El dato que resume el bloque: **borrar la tabla `schema_version` entera de una
base y abrirla no daba ningún error.** Una versión que se regenera cuando
falta es un `DEFAULT`, no un hecho.

**Cerrado:**

1. `platform/migrations.py` — cada migración tiene un identificador **estable**
   y es idempotente por precondición.
2. `SCHEMA_VERSION = version_declarada()` = `len(MIGRACIONES)`. **Derivada**:
   no hay número que mantener en dos sitios, y un guard por AST lo vigila.
3. La migración de `claims.assertion_origin` deja de ser un método privado del
   facade y pasa a ser la primera del libro. El método **se borra**, y hay un
   test que lo comprueba.
4. `Storage.version_esquema()` y `Storage.migraciones_aplicadas()`: «¿qué
   versión tiene este proyecto?» se responde por el **dato** de la base.
5. `SchemaTooNewError`: una base **más nueva** que el código falla en vez de
   abrirse en silencio.

**La decisión de diseño, que es lo que más se discutirá:** el libro
**registra, no gobierna**. `sincroniza` ejecuta *todas* las migraciones y anota
las que faltaban. Podría haber guardado ejecutando solo las pendientes, y sería
más eficiente. Se eligió lo contrario por el caso que de verdad duele: una base
restaurada de una copia parcial tiene el libro atrasado **y** el esquema con una
columna que falta a la vez, y un libro que gobierna se creería que está bien y
no repararía nada. El límite de la decisión está escrito en el código.

**Regresión que el bloque introdujo y corrigió, medida:** la primera versión
hacía `DELETE FROM schema_version` + `INSERT` siempre. Antes era
`INSERT OR IGNORE`, que tras la primera apertura no escribe nada, luego abrir
una base era una *lectura*. Con el `DELETE` incondicional, ocho procesos
concurrentes se repartían mal el turno de escritura: *«se esperaban 8 autores
distintos y hay 7»*. El contrasalto que lo vigila mide `total_changes`, que es
determinista; contar ejecuciones verdes de un test de concurrencia sería una
tirada, no una prueba.

**Un predicado del gate que mentía en la dirección contraria.**
«upgrade desde releases soportadas» buscaba `def upgrade` con un regex. La
capacidad se llama `sincroniza`, así que B12 habría entregado la capacidad y el
gate habría seguido diciendo `OPEN`: un falso **negativo**, la misma clase que el
falso positivo de B9 con el signo cambiado. Ahora el predicador **ejecuta** el
medidor y decide por su código de salida, y se verificó en las dos direcciones
—con la capacidad entera da `PASS`, con el libro roto da `OPEN 3/5`—.

**Harness:** 5/5 sondas cazadas, 5 causas distintas. Una de ellas, **M4, nació
rota**: su texto ancla apuntaba a una línea que `ruff format` había movido. Es
el error 32 de WI-113 repetido, y se detectó porque el harness reporta
`[SIN SONDA]` en vez de contarla como verde.

**Resultado:** gate de 1.0 en **17 PASS / 2 OPEN / 1 NO_MEASURABLE**.

---

## B13 — El modelo de amenaza que se sostiene

**La tercera y última de las `OPEN` que no dependen de credencial ni de
persona.** El veredicto del gate de 1.0 decía, textual: *«el ADR se aprobó
describiendo un proyecto de 830 tests y 17 releases; el modelo de amenaza
describe un producto que ya no es este»*. Se podía leer como «actualiza las
cifras». **La medición dijo que las cifras son lo de menos.**

**Medido antes de escribir una línea** (`/tmp/b13_measure.py`): **0 de 5
preguntas en PASS**. Y la primera no es documental: se inserta un `DomainPack`
del tenant T1 en una base real, se pide desde T2, y **la fila de T1 vuelve**.
Medido: *T2 recibió `[dp-de-t1]`*. No es un análisis del SQL: es una fila que
cruzó.

**La causa, y por qué nadie la vio.** `platform/knowledge_repository.py:211`
armaba el filtro sin paréntesis. En SQL `AND` liga más fuerte que `OR`, luego
la segunda mitad del `OR` se come el `tenant_id` **y** el `project_id`, y
devuelve cualquier fila de cualquier tenant con ese `kind`. Y **era alcanzable**:
`cli/support.py:299` llama `list_resources(..., kind="DomainPack")`.

**B11 encontró este defecto y no lo arregló**, porque esquivarlo era la
decisión correcta para su bloque: necesitaba aislamiento fila a fila, y por eso
lo comprobó así. Lo que falló es que la puerta se quedó abierta y el ADR-0015,
que en S1 decía *«las queries filtran por tenant_id, project_id en todos los
paths verificados»*, la declaraba **CERRADA**.

> Un modelo de amenaza que llama `OK` a una fuga que existe no es un modelo
> caducado: es un modelo que dice lo contrario de la verdad.

**Cerrado:**

1. **La fuga, arreglada** — dos paréntesis, con el porqué escrito en el propio
   método y no en un comentario que alguien puede borrar.
2. **Un guard general sobre el SQL que sale al motor**, derivado por
   `set_trace_callback`: exige que ninguna lectura tenga un `OR` sin agrupar y
   que toda lectura mencione `tenant_id`. La primera versión recorría
   literales y daba verde **con la fuga presente**, porque `WHERE` y `OR` están
   en literales distintos: el guard medía el texto, no la consulta.
3. **Un contrasalto de cobertura derivado del árbol**: solo 4 superficies
   combinan `tenant_id` con un filtro `kind`, y son la única vía por la que un
   `AND` se vuelve opcional. Una superficie nueva que admita esa combinación
   tiene que entrar en la lista, y el guard obliga.
4. **S9 y S10 en el ADR**, con su amenaza y sus gaps: los packs instalables
   admiten contenido de fuera del proyecto, y es una frontera de confianza que
   el modelo no mencionaba.
5. **Una sección `Superficies` con una fila por cada uno de los 10 paquetes**,
   cada una nombrando el fichero de test que la sostiene.

**Dónde se mira, verificado por AST:**

- `tests/test_b13_threat_model.py::TestLaFugaCrossTenant` — dos tenants de verdad; la fuga se **ejecuta**, no se razona
- `test_b13_threat_model.py:198::test_toda_superficie_con_filtro_de_kind_esta_cubierta` — contrasalto de cobertura, derivado del árbol
- `test_b13_threat_model.py:214::test_ninguna_lectura_ejecuta_un_where_con_or_suelto` — el guard mira la consulta ensamblada
- `test_b13_threat_model.py:290::test_todo_paquete_del_arbol_tiene_fila_en_el_adr` — un paquete nuevo rompe hasta que alguien decida
- `test_b13_threat_model.py:386::test_cada_superficie_nombra_una_evidencia_que_existe` — cada «OK» dice de qué depende
- `test_b13_threat_model.py:421::test_el_adapter_no_puede_estar_fuera_de_alcance_y_cerrado` — contradicción 1
- `test_b13_threat_model.py:432::test_la_seccion_de_alcance_no_excluye_lo_que_esta_implementado` — contrasalto por su otra vía
- `test_b13_threat_model.py:452::test_el_adr_no_puede_decir_que_no_toca_codigo_mientras_lo_toca` — contradicción 3, la que no se contradice consigo misma
- `measure_b9_gate_1_0.py:614::_security_threat_model_actualizado` — el gate corre el guard y decide por su rc
- `mutate_b13_threat_model.py:94::_sin_trabajo_sin_commitar` — «restaurar» y «borrar» son la misma operación sin commit debajo
- `mutate_b13_threat_model.py:129::_colectados` — el harness rechaza arrancar si un diagnóstico no existe

**Los cuatro commits de B13**, por si alguien quiere leerlos en orden:

```
da1c18f  fix(platform)      la fuga, el guard que la ejecuta y el ADR que la declaraba cerrada
c516ecc  chore(gate)        el predicado ejecuta el guard; el harness se comprueba a sí mismo
dcf1f58  fix(security)      la tercera contradicción, y el guard que caza su propia corrección
<docs>    docs(state)       este bloque, con sus cifras medidas
```

**El predicado del gate, reescrito.** La vigencia del modelo se medía
**comparando un número de tests**. Un número es una foto que caduca con cada
commit sin que nadie toque el análisis, y un gate que se pone rojo por causas
ajenas al objeto que vigila enseña a ignorarlo. Ahora el predicado **ejecuta**
`tests/test_b13_threat_model.py` y decide por su resultado, verificado **en las
dos direcciones y con causas distintas**: quitar la fila de `packaging` de la
tabla da `OPEN` con 1 fallo; reabrir la fuga da `OPEN` con 3 fallos.

**Lo que el ADR se decía a sí mismo, y ya no dice.** Marcaba el adapter real
HTTP/LLM como «E1, sin implementar, fuera de alcance» y a la vez le dedicaba
una sección S8 entera, marcándolo CERRADO. La contradicción está resuelta y
escrita con sus dos mitades.

**Harness:** `scripts/mutate_b13_threat_model.py`, 6 sondas, cada una con su
conjunto de tests diagnósticos. **Dos nacieron rotas** y las cazó el propio
harness antes de contar: M5 declaraba sus dos diagnósticos con el nombre de la
clase mal escrito, y el harness lo reportaba `[CAZADA]` igual porque
`caidos & esperados` no está vacío mientras caiga *uno* de los dos; M4 usaba
`## Superficies` como ancla y aparece dos veces, como encabezado y dentro de
una mención en prosa, así que `replace(..., 1)` se comía la prosa. El harness
rechaza arrancar si un diagnóstico no existe o si un ancla no es única.

Una tercera sonda, M6, deshace una contradicción que se encontró **al releer
el ADR con la corrección ya escrita**: sus consecuencias decían que el ADR «no
introduce cambios de código», y el bloque que lo revisaba había arreglado una
fuga. El guard de esa frase llegó a cazar la redacción de su propia
corrección, que citaba la afirmación falsa para explicarla.

**Resultado: 6/6 sondas cazadas, 6 causas distintas.** Suite certificada
**3268 passed, 3 skipped, 0 failed**, `tests.total` 3271.

**Un rojo que no se ha explicado, y no se maquilla.** Una corrida del hook de
pre-commit sobre este árbol dio `3 failed, 3264 passed`. Cinco corridas
completas posteriores sobre el **mismo árbol** —incluida una con el índice
sucio, que es el estado en que estaba el hook— dieron `0 failed` cada una.
No se reproduce y **la causa no está identificada**. Se deja escrito porque
un verde posterior no borra un rojo anterior.

**Resultado:** gate de 1.0 en **18 PASS / 1 OPEN / 1 NO_MEASURABLE**. Lo que
queda `OPEN` es el runtime real certificado, que necesita
`SG_UAT_REAL_PROVIDER=1` y una credencial real: no se resuelve desde el
repositorio.

---

## B14 — La autoridad de coherencia se puede engañar, y se engañó

**No es un bloque hacia 1.0. Es el bloque que hace que el verificador del que
dependen todos los demás pueda ser creído.**

`scripts/project_truth.py` es la respuesta a *«¿dónde está el proyecto?»*. B0 la
creó, y desde entonces B0..B13 se apoyan en su veredicto de `coherente`. Un
verificador que dice «coherente» cuando no lo está es **peor que no tener
verificador**, porque las dos mitades de la propiedad se apoyan en él.

**No es una hipótesis: es un caso que ya pasó en B13.** Al cerrar B13 se añadió
una segunda clave `current_workitem` en `STATE.yaml`, y el resultado medido fue:

```
yaml.safe_load          -> B13_cerrado   (última clave)
regex de project_truth  -> B13           (primera coincidencia)
project_truth           -> coherente: true, contradicciones: []
```

Seis ficheros de test leen `STATE.yaml` con `yaml.safe_load`;
`project_truth.py` **no importaba `yaml` en absoluto** y lo leía entero con
regex. Dos lectores del mismo fichero discrepando en silencio.

**Medido antes de escribir nada** (`scripts/measure_b14_truth_single_reader.py`,
mutaciones **en sitio** con restauración verificada por sha256): **7 de 8**. La
que no era la de la clave duplicada. **Al cerrar: 8 de 8**, y el instrumento
tiene su propia contramutación —`--autocomprobacion`, **3 de 3**— porque un
8/8 que no puede ponerse en rojo no es un 8/8.

**La primera versión del instrumento dio 7 de 8 en una copia temporal, y era
mentira:** la copia no colecta tests, `project_truth` no puede leer el recuento
real, y todo devolvía `rc=2` — incluidas las siete que el script contaba como
buenas. Un instrumento que se pasa a sí mismo porque el entorno no puede correr
es la forma exacta del falso verde que este repositorio lleva catorce bloques
cazando. Se rehízo sobre el árbol real, y por eso el número de partida es 7.

**Cerrado:**

1. `STATE.yaml` se lee **una vez** con `yaml.safe_load`, en vez de con tres
   regex que cada una puede encontrar otra cosa. Markdown y Python siguen con
   regex: no son YAML.
2. Un loader que **rechaza claves duplicadas en el punto de lectura**, no
   después con un guard: un guard que busca «¿hay dos claves iguales?» sería un
   segundo lector, que es el problema.
3. Comprobación de **tipo** en los tres campos. Con YAML, un `total: 'muchos'`
   llegaba al verificador sin que nadie lo mirara.

**Tres cosas que el bloque encontró en sí mismo, y que importan más que el
arreglo:**

- **El mecanismo central no lanzaba nunca.** `_construye` hacía
  `construct_mapping(...)` y luego miraba `Mapping.items()`; y
  `construct_mapping` ya devuelve un dict donde la clave repetida se colapsó.
  El bucle veía **una** clave, no dos. Medido: con dos `current_workitem`,
  `_estado()` leía `B99_inventado` sin protestar. Para cuando existe el dict, la
  información de que había dos declaraciones ya no está.
- **El test de la clave duplicada daba verde aceptando el defecto.** Sin el
  constructor, YAML toma la última y el verificador dice *«STATE declara
  B99_inventado, CURRENT declara B13»*: **elige una de las dos y la publica
  como la verdad**. El veredicto sí cambia, luego un test de «cambia el
  veredicto» pasa. Ahora el contrato es «el estado es ilegible», y hay un
  contrasalto que comprueba que **no se publica ninguno de los dos valores**.
- **La medición usaba el mismo predicado débil**, y por eso daba 8/8 con el
  mecanismo central roto. Endurecida a exigir `ilegible` nombrando la clave.

> Los tres son de la misma clase que el falso verde que B13 cerró en el gate de
> 1.0: **un guard que pasa por una causa ajena al objeto que vigila**. Y los
> tres los manifestó el harness o la sonda manual, no una lectura del código.

**Y lo que el bloque encontró al CERTIFICAR, que es más de lo mismo.** Los
cinco siguientes son el mismo defecto con distinto disfraz —**un predicado que
se puede satisfacer por una causa que no es la que dice medir**— y los cinco
los manifestó el harness o la sonda, ninguno una lectura del código:

- **Dos guards de los tests estaban atados a `current_workitem: B13` escrito a
  mano.** Al mover el bloque vivo a B14 los dos dejaron de mutar nada: un
  `.replace()` vuelto no-op, y un conjunto prohibido `{"B13", "B99_inventado"}`
  que ya no contenía el valor que un verificador roto publicaría. Un contrasalto
  que se desactiva al cambiar el calendario ya no es un contrasalto.
- **La medición tenía tres mutaciones no-op, por el mismo motivo y en el mismo
  fichero.** Imprimía **5 de 8 diciendo que el arreglo recién hecho no
  funcionaba**; lo que estaba roto era el instrumento. Ahora deriva los valores
  del fichero y **aborta** si la sustitución no aplicó.
- **Tres de sus ocho preguntas pedían «no es coherente».** Lo cumple un módulo
  roto igual que un módulo que dejó de mirar, y se comprobó: una sustitución mal
  escrita dejaba el YAML inválido, rc=2, y la pregunta contaba eso como PASS.
- **`RAIZ` era una ruta absoluta de esta máquina.** El instrumento mutaba
  ficheros de un árbol que podía no ser el suyo.
- **La sonda M1 del harness no medía el guard que decía vigilar.** Referenciaba
  `_TAG_STATE`, que este mismo bloque borró: el módulo reventaba con `NameError`
  y caían los diez tests, ninguno el diagnosticado. El harness la declaró
  INVÁLIDA —que es lo que distingue a una sonda que mide de una que rompe— y
  ahora reinsta un reader funcional.

**Y un defecto de verdad, no de instrumento.** Al endurecer la pregunta que
detecta una versión incoherente apareció esto: con `__init__.py` mutilado, pytest
no termina la colecta, imprime «2867 tests collected, 27 errors» y sale con
rc=2. Ese número es real —son los tests que llegó a ver— pero no es **el**
recuento, y `tests_colectados()` lo publicaba con su nombre: *«tests: STATE
declara 3284, el arbol colecta 2867»*. Sin 417 tests y sin decir por qué. Ahora
se niega a leer el número. El fallo va en la dirección **segura** —dice que no
cuadra cuando sí cuadra—, así que no es el defecto que B14 persigue; se arregla
porque la autoridad de coherencia hablando de un número que no contó es del
mismo género que ella hablando de una coherencia que no midió.

**Y una lección que casi se lleva el verificador por delante.** La primera
ejecución de `--autocomprobacion` reventó a mitad —restauraba dos veces, y la
segunda ya no encontraba la copia— y **dejó `project_truth.py` sin el
constructor**, con el repo entero en `coherente: false` y sin que nadie lo
dijera. La red que verifica por sha256 no cubría el fichero que el instrumento
más deforma. `scripts/project_truth.py` entra ahora en `MUTABLES`: una red que
no cubre lo que deforma no es una red.

> **Con la deformación puesta, la sonda 3 deja ver el defecto central de B14 a
> la vista:**
>
> ```
> "coherente": true,  "contradicciones": [],
> "workitem_current": "B14",  "workitem_state": "B99"
> ```
>
> El verificador publicando como coherente un estado en el que `STATE` y
> `CURRENT` dicen cosas distintas. Eso, y no el arreglo del loader, es lo que
> B14 existía para cerrar.

**Dónde se mira, verificado por AST:**

- `project_truth.py:120::_SinClavesDuplicadas` — el loader que no elige
- `project_truth.py:124::_construye` — recorre `node.value`, no el dict
- `test_b14_truth_single_reader.py::TestUnaClaveDuplicadaNoPasaPorAlto` — el contrato
- `mutate_b14_truth_single_reader.py:77::_sin_trabajo_sin_commitar` — «restaurar» y «borrar» son lo mismo
- `test_b14_truth_single_reader.py::TestUnRecuentoQueNoSeTerminoNoSePublica` — un número de una colecta a medias no se publica
- `measure_b14_truth_single_reader.py::Arbol` — restaura el verificador también, y lo comprueba

**Harness:** **6 sondas, 6/6 cazadas, 6 causas distintas.** M1–M6, con M1
reforzada dos veces: la primera versión solo **definía** un regex del estado sin
usarlo —desactivaba el módulo sin cambiar lo que el código hace—, y la segunda
lo replaceaba por una referencia a una constante que B14 había borrado, con lo
que el módulo reventaba entero. Una sonda que rompe el módulo no prueba el
guard que dice vigilar. M6 cubre el recuento de una colecta interrumpida.

**Autocomprobación del instrumento:** 3 sondas sobre los tres mecanismos que B14
toca. Dos de ellas nacieron **declarando más preguntas de las que rompen** y la
autocomprobación las marcó `[SIN CAZAR]`: eran expectativas, no propiedades.

**Lo que este bloque NO abre.** El PRE-FLIGHT anotó «los otros consumidores con
regex que quedan en el repo». **Medido: no quedan.** `project_truth.py` era el
único consumidor de producción, y los seis de test ya usaban el parser. Era
deuda sin verificar, y sin verificar no era deuda.

**Resultado:** gate de 1.0 **sin cambios**, 18 PASS / 1 OPEN / 1 NO_MEASURABLE, y
`coherente: true` con `tests.total` cuadrando contra el árbol.


## B16 — Dos propiedades del gate daban PASS sin nada que comparar

**Es la primera de las siete que B15 dejó nombradas**, y no era una mejora de
forma: dos de ellas **daban verde sin mirar nada**.

Medido antes de escribir una línea, sobre copias del árbol con el repo real
intacto:

```
MEDIDO A · se renombra la constante a _CAPABILITY_VERSION en todo src/
  veredicto : PASS
  evidencia : CAPABILITY_VERSION se declara en un solo sitio: []

MEDIDO B · core/ importa DomainPack de verdad
  veredicto : PASS
  evidencia : core/ no nombra ningun tipo de recurso: se anaden sin tocarlo
```

La primera es **un PASS cuya evidencia dice una lista vacía**. La segunda es **la
fuga de B13 con el signo cambiado**: allí el guard leía literales en vez de la
consulta ensamblada y daba verde con la fuga presente; aquí leía cadenas en vez
de los imports y daba verde con la dependencia presente. Y lo declarado era una
frontera arquitectónica —el núcleo no depende de los recursos— que nada
vigilaba.

**Lo que encontró al medir, y que no era de B16.** `concurrencia real
certificada` pasó de PASS a OPEN y no era ruido del medidor: cuatro corridas
rojas de veinte, y un hijo muerto de treinta con
`sqlite3.IntegrityError: UNIQUE constraint failed: schema_version.version`. Ocho
procesos abren la misma base nueva, los ocho leen que hay que subir, y el
segundo `INSERT` se lleva un UNIQUE sobre la PRIMARY KEY y muere antes de
escribir un solo evento. El `timeout` que arregló el `PRAGMA journal_mode` en B2
no lo puede arreglar, porque no es un candado esperando: es un `SELECT` seguido
de un `INSERT`, y entre los dos cabe otro proceso. La respuesta era la que ya
estaba en el mismo archivo, quince líneas más arriba, en las migraciones:
`INSERT OR IGNORE`.

**Y lo que no se pudo hacer, medido y escrito en el código.** La carrera **no es
reproducible de forma determinista**, y el test que afirmaba reproducirla se
retiró en vez de quedarse mintiendo. Un guard que solo sabe dar verde fabrica
confianza justo donde no la hay.

## B15 — Un predicado que se declara leyendo código no sabe cuándo deja de medir

**No es un bloque hacia 1.0 todavía: es un bloque sobre cómo el gate sabe lo que
sabe.** Las dos propiedades que quedan abiertas siguen sin abrirse —una
credencial y una persona—, y esto no las toca.

**El hallazgo, medido.** El gate de 1.0 declara veinte propiedades. Sus veinte
PASS salían en la misma lista y con la misma tipografía, y **no había manera de
saber cuáles estaban respaldados por algo que se ejecuta y cuáles por una
lectura del árbol**. La diferencia no es estética: es si el veredicto **puede
volverse falso sin que nadie vuelva a mirarlo**.

Medido, y derivado del AST del propio gate:

```
ejecutada  13      derivada  7
```

**Y una propiedad que decia PASS sin comprobar lo que dice comprobar.**
`distribution reproducible` ejecutaba `check_package_build.py`, que construye el
wheel y el sdist, y devolvía PASS con la evidencia entera: *«el wheel y el sdist
se construyen y llevan lo que declaran»*. Eso prueba que **se construyen**.
Reproducible es otra cosa: las mismas entradas, los mismos bytes. Un único build
no puede distinguir «reproducible» de «esta vez salió bien».

Medido antes de arreglar, con una prueba que tiene dientes: se construye, se
espera a que el reloj avance, se toca el mtime de un fuente —contenido
idéntico— y se construye otra vez. Los sha256 coinciden. **La propiedad era
cierta; lo que no existía era nada que pudiera quitársela.**

**Cerrado:**

1. Cada propiedad declara su clase de evidencia, y la clase se **deriva** del
   grafo de llamadas del propio módulo hasta un `subprocess`. No se escribe a
   mano: veinte líneas escritas a mano serían una segunda fuente de verdad que
   divergiría en silencio.
2. Un guard vigila que la clase **siga al código** en las dos direcciones: un
   predicado al que se le añade un subproceso pasa a `ejecutada` solo, y al que
   se le quita el `subprocess` entero pasan las trece a `derivada`.
3. `distribution reproducible` se **ejecuta**: dos construcciones, la fuente
   tocada entre medias, los sha comparados.

**Y el fallo que este bloque encontró en su propia casa, que es lo que le da
sentido.** La primera versión de la derivación devolvió **veinte de veinte
`derivada`**, con la autoridad de un `print` y sin una sola advertencia. Los
predicados se registran en `PREDICADOS` como `_` + slug, la función buscaba el
slug a secas, no lo encontraba, y **devolvía un valor por defecto** en vez de
decir «no lo sé». Seis de esos predicados sí lanzan subproceso.

> Es el mismo hallazgo que B13 cerró en el guard de SQL —que leía literales en vez
> de la consulta ensamblada— y que B14 encontró en los guards atados a un valor
> vivo y en las tres mutaciones no-op de su medidor. **Un guard que se declara
> leyendo el código no sabe cuándo deja de medir.** Y la diferencia con un
> predicar suelto: un guard que miente está instalado y paga el coste a cada
> commit. Una sonda que miente se tira. La deuda que queda aquí es de clase
> distinta: no es que falte un guard, es que no había forma de saber cuándo un
> guard derivado empieza a mentir.

**Y un dato de esta sesión que va en la misma línea, porque se Midió.** Al
buscar un PASS falso —`blueprint legacy completamente probado`, que cuenta
cobertura de UAT con un `re.findall` sobre el texto de los tests— se construyeron
cuatro sondeos para comprobarlo. **Las cuatro fallaron, cada una en una
dirección distinta**: buscando cadenas donde el código usa nombres; buscando el
operador `!=` por su nombre donde el AST tiene un nodo `NotEq`; buscando
`--collect-only` como argumento directo donde está dentro de una lista; y
clasificando «el test razona sobre el UAT» por una aserción que lo nombre,
cuando un test que de verdad prueba UAT-11 lo nombra en el docstring. Cuatro
cifras distintas —0 de 12, 9 de 12, 3 de 12— y ninguna correcta. **El PASS que
se buscaba era cierto**: `tests/uat_audit.py` tiene una función completa por UAT
con directorios temporales, la CLI de verdad y aserciones. El predicado es
débil; la propiedad es cierta. Queda anotado con su debilidad, que es
información, no deuda fingida.

**Dónde se mira, verificado por AST:**

- `measure_b9_gate_1_0.py::_grafo_del_modulo` — la clase sale de aquí
- `measure_b9_gate_1_0.py::_funcion_del_predicado` — una búsqueda que no
  encuentra **levanta**
- `measure_b9_gate_1_0.py::_construye_en` — construye para comparar, no para
  declarar
- `test_b15_evidence_kind.py::TestLaClaseSigueAlCodigo` — el contrasalto en las
  dos direcciones

**Resultado:** gate de 1.0 **sin cambios de veredicto**, 18 PASS / 1 OPEN / 1
NO_MEASURABLE, ahora con la clase de cada una. Harness **6/6 con 6 causas**,
autocomprobación del medidor **13 de 20 clases giran**.
