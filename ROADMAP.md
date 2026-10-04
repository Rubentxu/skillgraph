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

> Bloque vivo: **B12** — Upgrade entre releases
> Versión activa `0.30.0.dev0` · último tag `v0.30.0` · 3254 tests · 16/16 UAT

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
