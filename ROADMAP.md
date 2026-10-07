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

> Bloque vivo: **B38** — El gate mas cercano al push dice `SUCCESS` cuando no ha corrido nada · (B37 cerrado y certificado en `evidence/b37-smoke-subset-2026-10-07.md`: `4118 passed, 3 skipped, 0 failed, 904,48 s`, y `4118 + 3 = 4121` = `tests.total`; suelos rc=0, `project_truth` rc=0, ratchet 5/5 a cero, sondas B37 6/6, B36 5/5 y B35 8/8. B37 cerro el silencio del pre-commit: el `OK` final era el MISMO en los tres caminos y **803 de 1163 commits — el 69 % — pasaron por ahi sin ejecutar un test**; el bloque 4 declara ahora siempre que ha pasado, pegado al `OK`, y cinco tests EJECUTAN el hook y miran lo que imprime, porque un guard por busqueda de cadena aprueba el defecto entero. **B38 abre con lo que B37 dejo escrito sin medir**: su subtitulo era «lo que el hook de pre-push no llega a medir». MEDIDO con `scripts/measure_b38_pre_push.py`: con `HOOK_SKIP_PUSH_TESTS=1` la ultima linea del pre-push es `OK: la receta canonica dio SUCCESS sobre <sha>`, con la receta sin ejecutar, y el guard que ya existe sobre ese bypass solo exige `returncode == 0` y que el stub no saliera en la salida.)
> Versión activa `0.42.2.dev0` · último tag `v0.42.2` · 4121 tests · 16/16 UAT

Esa línea es la respuesta a *«¿dónde está el proyecto y qué toca después?»*.

**CORRECCIÓN DE B23, Y LO QUE AFIRMABA ESTA PÁGINA ERA FALSO.** Decía que
«la produce `scripts/project_truth.py`». No la producía nadie: la escribía a
mano, nadie la leía, y por eso se quedó dos releases atrás (`v0.32.7`) con el
instrumento diciendo `coherente: true`. MEDIDO: el release `9961843` no tocó
este fichero.

Ahora la relación es al revés: `scripts/project_truth.py` **contrasta** esta
ventana contra la verdad —versión, tag y cifra— y sale con `rc=1` si no
cuadra. No la regenera, y es deliberado: el instrumento tiene cero escrituras,
y un instrumento que escribe el fichero de autoridad sería un problema nuevo y
peor que el que arregla. Mantenerla sigue siendo de quien la escribe; lo que
cambia es que **el desfase ya no puede pasar inadvertido**.

Había además **dos** ventanas contradictorias —`3444 tests` y `3431 tests`— y
el instrumenta no cruzaba ninguna. Ahora tampoco se permite que el fichero se
contradiga a sí mismo.

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
| **B17** | El ciclo de vida de los packs se decidía contando nombres | La propiedad se decide ejecutando el ciclo, que el instrumento ya hacía y nadie cableó |
| **B18** | La frontera del núcleo no miraba la mitad de la superficie | Los relativos se resuelven, la estándar se deriva del intérprete, y la evidencia describe el recorrido |
| **B19** | «NO es reproducible» y «no he podido medirlo» son la misma frase | La entrada del paquete se mide antes de acusar, y el veredicto no culpa al proyecto de haber medido dos entradas distintas |
| **B20** | El gate se contradecía a sí mismo | El conjunto de recursos se deriva del árbol, y un docstring que documenta la frontera no es una dependencia |
| **B21** | Una certificación en rojo no puede decir QUÉ falló | Lo que pytest dice de sus fallos aparece después de la última tabla, y un guard no usa como reloj un estado que mueve su propio contenedor |
| **B22** | La suite no puede cambiar el árbol por debajo de un instrumento, y un predicado reventado no borra el informe | Escribir y cambiar se separan, toda excepción va declarada, y cada predicado da su veredicto aunque lance |
| **B23** | El instrumento que responde «¿dónde está el proyecto?» no lo decía | La raíz es un parámetro, la ventana del ROADMAP se contrasta, y el bloque se cruza con STATE y CURRENT |
| **B24** | La ruta de certificación nunca se ejecutaba, y sus instrucciones apuntaban a un fichero que no existe | Las ocho fronteras se ejecutan contra el adapter de verdad, sin credencial ni dinero, y una instrucción que apunta a un path inexistente se mide como lo que es |
| **B25** | Un hecho entre dos entidades no se puede expresar: `Claim.object_literal` solo admite literales, y los predicados son un conjunto cerrado | `object` pasa a ser literal **o** `EntityRef`, y un pack añade un predicado sin tocar el núcleo |
| **B26** | Una herramienta externa no tiene forma de aportar conocimiento sin escribir en el store | `Observation Envelope` versionado, normalizers puros e ingesta idempotente |
| **B27** | Dos claims incompatibles se pisan y no hay forma de saberlo | conflict sets consultables y estables, sin overwrite |
| **B28** | Resolver un conflicto es un ranking global, y la respuesta correcta depende de para qué se pregunta | `AuthorityProfile` por `QueryIntent`, no un ranking único |
| **B29** | No se puede preguntar qué se sabía en una revisión, ni cómo fue reemplazado | ventanas de vigencia, supersession y query por revisión |
| **B30** | Traer el contexto es traerlo todo, o traerlo truncado sin decir qué se cayó | **cerrado en v0.40.0** — `PresupuestoAplicado` declara lo omitido con su tamaño, `HandoffKnowledge.omitidos` lo carga y lo firma, y `should_skip_adapter` ya no declara completo un slice truncado. La mitad `why`/`impact` queda para el siguiente corte |
| **B31** | ~~No hay análisis estructural real: `line_count = 137` es todo lo que se sabe del código~~ | **cerrado** — `sg.code.analysis` convierte el contenido de un fichero en el `ObservationEnvelope` de B26, y `normalizar` lo convierte en `Claim`s. **La premisa de la fila era FALSA y se midió antes de escribir nada**: el análisis existía (`file_signature.py`, 431 líneas puras y deterministas) y lo que faltaba era el último paso — se persistía como `Evidence` kind=`file_signature`, nunca como `Claim`. El hueco real lo abrió `ADR-0035`: **el objeto no formaba parte de la identidad del claim** (`7 observaciones -> 7 claims -> 5 filas`), y se midió que **`make_claim_id` tenía que cambiar junto** o el fallo se mudaba de capa. Cinco de los siete predicadores salen del extractor; los otros dos se declaran inalcanzables en vez de inventarse. **NO arregla la frontera**: `NUCLEO` no incluye `knowledge/` (medido: el guard da VERDE con `import cognicode`), porque añadir un paquete cambia *qué se considera núcleo*, que es decisión de B3 |
| **B32** | No se puede responder cuándo cambió una relación ni por qué | **cerrado** — `GitHistory` (puerto) y `DulwichGitHistory` dan la ascendencia real con `es_ancestro(a,b) -> bool` y **no** `ordena()`, porque el grafo de commits es parcial y un número mentiría la mitad de las veces; `claims_desde_commit` responde el DESDE QUÉ, con migración `0006` y el índice parcial `idx_sources_commit`. **NO cierra el POR QUÉ**, que es de B33/B34 y tiene un guard que ata que no exista |
| **B33** | La telemetría y la intención/documentación se contradicen y una pisa a la otra | **cerrado** — `telemetry.query.v1` (la vertical que faltaba) con `ADR-0034`: `SourceKind` 5→6 con `runtime_observation`, `Source` +2 columnas, migración `0007` e índice parcial `idx_sources_ventana` — **solo en la migración**, porque en el DDL una base vieja revienta antes de migrar. `ObservationEnvelope` +3 campos con default, así que un envelope de B26 sigue produciéndose igual |
| **B34** | No hay forma de preguntar al sistema por lo que sabe | **cerrado** — `SuperficieConocimiento` con las seis como `Literal` cerrado y **un** método `responder`; seis subcomandos de CLI generados de un catálogo declarado una vez; `sg.knowledge.query` de 2 a 8 consultas, que **no implementa ninguna** de las seis: construye la `Consulta` y pregunta. `list_claims_by_object_entity` al Protocol. **Al certificar salió que el puente no se ejecutaba nunca**: 55 tests atacaban `responder` y la CLI, y `invoke` con una de las seis nunca se llamó — el suelo de §6.3 lo delató, y las líneas sin cubrir eran la entrega del bloque |
| **B35** | ~~De la capability al store hay tres pasos que no existen~~ | **cerrado en v0.42.0** — el par canónico `envelope_a_payload`/`envelope_de_payload` en `observation.py` (**una** definición en `src/`, dos envolturas eliminadas), `knowledge/assembly.py::registro_de_conocimiento` como valor y no singleton, y la puerta `sg knowledge ingest-code`. **MEDIDO AL CERTIFICAR, Y NO SALIA EN EL ALCANCE:** el floors dio `observation_ingestion.py` al **84 %**, seis puntos bajo su suelo, y **lo había producido este mismo bloque**: al meter el objeto en el `UNIQUE` (`ADR-0035`), `normalizar` deriva el `claim_id` de la misma tupla, luego el `UNIQUE` no puede rechazar nada y la rama que recogía el aviso quedó **inalcanzable**. Se borró la rama en vez de bajar el suelo (fabricar un test exigía monkeypatchear `normalizar`, que es poner un peine en la cobertura) y el módulo subió a **100 %**. Cayó también el `if ingesta.conflictos:` de la CLI y dos aserciones que se volvieron **decoradas**, sustituidas por guardes AST. **La detección NO se pierde:** `conflicts_for` sigue viendo la auto-contradicción de una misma fuente y B28 la resuelve por intención |
| **B37** | El bypass que queda, y lo que el hook de pre-push no llega a medir | **cerrado** — `evidence/b37-smoke-subset-2026-10-07.md`. MEDIDO con `scripts/measure_b37_smoke_subset.py`, cuatro rondas sobre los 1163 commits: **803 de 1163 — el 69 % — pasaron por el hook sin ejecutar un test** (551 no stagean `.py`; 252 stagean solo codigo y `pytest -q src/...` colecta cero con rc=5; 264 stagean un test y el hook no lo dice). **Lo que no se arregla, y el propio hook lo declara:** el smoke es un FILTRO, no una certificacion. **Lo que si estaba roto era el SILENCIO:** el `OK` final era el mismo en los tres caminos, luego 803 commits pudieron parecer verdes sin que quedara escrito que no se habia medido. El bloque 4 del hook declara ahora SIEMPRE que ha pasado, en los tres caminos, y pegado al `OK`. Cinco tests que EJECUTAN el hook real en un repo de pruebas y miran lo que imprime — un guard por busqueda de cadena aprueba el defecto entero, que es literalmente donde estaba — y el quinto mira el ORDEN, que es lo que impide declarar la nota dos lineas mas abajo y dejar el `OK` igual de indistinguible. Sondas 6/6. Recibo: 4118 passed, 3 skipped, 0 failed, 904,48 s, 4118+3 = 4121 = `tests.total`, cuatro rondas sobre los 1163 commits del repo. El smoke es `pytest -q $STAGED_PY` (`scripts/hooks/pre-commit:113`), luego corre **un subconjunto del arbol**, y MEDIDO: **551 commits no llegan a lanzar pytest** (no stagean `.py`), **252 stagean solo codigo de produccion** y el smoke colecta cero y sale con el 5 que el hook trata como «nada que ejecutar», y **264 stagean un unico fichero de test** y corren ese y nada mas sin decir que no han corrido los demas. **803 de 1163 commits — el 69 % — pasaron por el hook sin ejecutar un solo test.** Y 3 stagearon el guard de WI-116 tocando codigo, que es de donde salio el bypass de B36. **Lo que no se arregla aqui:** el smoke es un FILTRO rapido y asi lo declara su propio docstring; lo que se declara es la MEDIDA, que 252 commits pueden parecer verdes sin que nada se haya medido |El orden es **B0 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9**. B0 y B1
| **B38** | El gate mas cercano al push dice `SUCCESS` cuando no ha corrido nada, y el guard que existe sobre el bypass no mira lo que imprime | **abierto y medido** con `scripts/measure_b38_pre_push.py`, cinco rondas. MEDIDO: con `HOOK_SKIP_PUSH_TESTS=1` sobre un repo git de verdad, la **ULTIMA LINEA** del hook es `[pre-push] OK: la receta canonica dio SUCCESS sobre 9114cb0`, con la receta sin ejecutar. Y `TestPrePushHookDelega::test_el_bypass_salta_la_verificacion_de_verdad` exige solo `returncode == 0` y que el stub no apareciera en la salida: un hook que MIENTE con la palabra SUCCESS lo aprueba con los ojos cerrados. Es el defecto de B37 con una palabra mas fuerte: alli el `OK` era neutro, aqui el `SUCCESS` afirma una ejecucion que no ocurrio |
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


## B25..B34 — La serie epistemológica

**Objetivo cerrado.** Diez bloques que convierten el grafo de conocimiento de
«un almacen de claims» en «algo que se puede preguntar». B0..B24 construyeron
un motor que sabe **ejecutar** un workflow y **certificar** que lo ejecuta; esta
serie le da un tercer eje: **qué se sabe**, **quién lo afirma** y **cuándo dejó
de ser cierto**.

No es una ampliación de B24 ni continúa su serie: es una línea distinta, con su
propio vocabulario, y arranca con **ningún bloque empezado**.

### Lo que hay hoy, medido

**B25 parte de un defecto real y presente en el código.** `Claim` declara

    object_literal: Any  # int | str | bool; depende del predicate

(`src/skillgraph/knowledge/graph.py:189`). El `object` de un claim es
**siempre un literal**: no hay forma de decir «A usa B» sin escribir el nombre
de B dentro de un string. Y los predicados son un `Final[frozenset[str]]` de
**siete** literales escrito en el núcleo
(`src/skillgraph/core/runtime_types.py:241`), validado en `__post_init__`: un
pack no puede añadir ni el objeto ni el predicado sin tocar el core. Las dos
mitades de la fila de B25 en el mapa están medidas, no temidas.

**Y el primer predicado de esa lista es `line_count`**, que es la prueba de que
la fila de B31 no es una hipótesis: B31 dice «no hay análisis estructural real:
`line_count = 137` es todo lo que se sabe del código», y ese `line_count` es el
primer elemento de un conjunto de siete valores que alguien decidió de
antemano. Un conjunto de siete no crece solo.

**B31 no tiene que inventar su frontera: ya está instrumentada.**
`TestElNucleoNoImportaAdapters` (`tests/test_b3_capability_kernel.py:539`) rastrea
los paquetes `("runtime", "core", "resources")` y falla si alguno conoce un
producto externo, con un contrasalto declarado aparte (`NUCLEO_MINIMO`) para que
reducir el rastreo no lo vacíe en verde. `knowledge/knowledge_query.py:17` ya
nombra `CodeAnalysis`, `TelemetryQuery` y `SecretAccess` como capabilities y no
como imports. La frontera de diseño que esta serie atraviesa ya tiene dueño.

**Lo que NO existe todavía, medido:** `EntityRef`, `Observation Envelope`,
`AuthorityProfile`, `ContextSlice`, supersession y conflict sets **no aparecen en
`src/`**. Cero de los diez bloques tiene código.

### Estado

**B25, B26, B27, B28 y B29 cerrados** (`v0.35.0`, `v0.36.0`, `v0.37.0`, `v0.38.0`
y pendiente de release). Los otros cinco siguen en el mapa como fila, sin sección,
guard, harness ni criterio de aceptación escrito.

**Y LA FILA DE B27 DECIA UNA COSA QUE MEDIDA RESULTO SER FALSA**, lo cual importa
mas que el resultado. Decía: *«Dos claims incompatibles se pisan y no hay forma
de saberlo»*. MEDIDO antes de escribir nada, con
`scripts/measure_b27_conflictos.py`:

    P1  dos fuentes, hechos opuestos  -> 2 filas, COEXISTEN
    P2  misma fuente, hechos opuestos -> 1 fila, SE PISA

El overwrite **no** depende de que dos herramientas discrepen: depende de la
MISMA fuente con la MISMA revisión, porque el `UNIQUE` de `claims` es
`(subject_entity_id, predicate, source_id, checked_at_revision)` y lleva
`source_id` dentro. Dos herramientas distintas ya coexistían de sobra.

Lo que sí era cierto era la otra mitad —«y no hay forma de saberlo»— y esa mitad
es la que B27 arregla: `conflicts_for` por la fachada, y `record_claim` que
devuelve si hubo conflicto y **qué se solapa** en vez de devolver siempre el
`claim_id` como si hubiera escrito.

**LO QUE B26 DEJO ABIERTO PARA B27, DICHO EN SU PROPIO RECIBO.** La ingesta de
un envelope **no borra historia**: si una herramienta cambia lo que dice sin
cambiar de versión, quedan **dos** afirmaciones, y las dos son válidas porque
las dos tienen fuente. Eso es exactamente el caso del enunciado de B27 —«dos
claims incompatibles se pisan y no hay forma de saberlo»— y B26 lo hace
**consultable** antes de que exista forma de resolverlo: el `claim_id` es
determinista sobre `(subject, predicate, source, revision)`, así que las dos
filas coexisten y se pueden leer, en vez de pisarse.

El orden que queda es el del bundle, con una dependencia que sí es dura:
**B28 no es ejecutable sin B27**, porque no se puede resolver un conflicto por
intención de consulta si antes no hay conflicto que consultar. El resto del
orden puede reordenarlo un gate. **Esa dependencia está ya satisfecha**: B28
está cerrado y es lo que convierte los conflict sets de B27 en respuestas.

---

## B28 — La autoridad se decide por intención

**Objetivo cerrado.** Un conflicto deja de ser una lista de afirmaciones que se
oponen y pasa a ser **una respuesta a una pregunta**, con la explicación de por
qué una gana y la otra pierde.

### Lo que se midió antes de escribir nada

`scripts/measure_b28_autoridad.py` → **5/5 ABIERTAS**. Y la primera sorpresa
está en el enunciado:

**La fila acusa a un «ranking global», y MEDIDO no hay ranking: no hay nada.**
B27 dejó los conflictos consultables y ordenados; lo único que faltaba era
decidir. La acusación sigue siendo útil, pero como **tentación medida**:

```
AssertionOrigin = observed | derived-deterministically
                | agent-inferred | human-asserted
```

Esos cuatro valores ya están en `core/runtime_types.py`, y su docstring dice
en sus propias palabras que **no son un ranking** —son «quién afirma». Los
datos para ordenar están a mano, y el orden depende de la pregunta:

```
¿qué devolvió producción?        observed > derived-deterministically
¿qué dependencia está permitida?  human-asserted > derived-deterministically
```

Por eso la propiedad que se mide **no es «se elige alguien»** sino **«el mismo
conflicto, con dos intenciones, elige afirmaciones DISTINTAS»**. Un resolver con
ranking fijo pasaría cualquier prueba que comprobara que hay ganador.

### Lo que entra

`QueryIntent` (los siete valores del «ADT inicial» de 05-SPEC §3, con smart
constructor), `AuthorityProfile`, `MotivoDescarte`, `Descartada` y
`Resolution`, con `resolver()` **puro**: sin disco, sin reloj y sin `Storage`.
Y **`sg knowledge resolve`**, porque una capacidad que no se puede preguntar es
el mismo defecto que B6 midió en `extraction_method` — un eje al que no
escribe nadie en `src/`.

### El guard del agente es un campo, no una posición en la lista

La spec (§7) dice que `agent-inferred` «no puede por defecto cerrar conflicto».
La lectura tentadora es ponerlo el último de la preferencia. **Eso sería un
guard roto**, por una razón concreta: se rompe **reordenando una lista**, que
es el cambio más barato que puede hacer quien no sabe lo que hace, y solo en el
perfil equivocado.

Aquí es un campo explícito (`permitir_inferencia_de_agente`, default `False`),
y está medido: un perfil que pone al agente **el primero** lo sigue dejando
perder. El opt-in existe y es auditable, pero lo concede quien escribe la
política, no el módulo.

### La contrasalto encontró un fallo del INSTRUMENTO, y por eso los perfiles nombran los cuatro orígenes

La primera versión de P4 usaba el perfil por defecto de `actual_behavior`,
donde `human-asserted` está por encima de `agent-inferred`. Ahí el agente
perdía **por rango** aunque el guard estuviera borrado, luego la pregunta
contestaba «no» por una razón que **no era la que vigilaba** — y la sonda M2
(flag del agente a `True`) **no fue cazada**.

Un origen **no listado** valía por una prohibición silenciosa. Los siete
perfiles por defecto nombran ahora los **cuatro**, de modo que P4 —que es el
guard del bloque— no pueda pasar aunque el guard se borrara. Y poner al
agente el último **no es lo que lo prohíbe**: lo prohíbe el flag, y sigue
valiendo aunque el orden cambiara.

**Instrumento:** 5/5 → **0/5**. **Contrasalto:** **5/5 sondas cazadas**,
`rc=0` al restaurar. Las anclas son **regex**, no texto literal, porque
`ruff format` desancló las cinco de una pasada — y el guard de sintaxis las
clasificó `ROTA` en vez de fingir que las cazó, que es lo que tiene que hacer.

### Lo que este bloque NO hace

1. **No borra.** Resolver para una intención no elimina afirmaciones: las dos
   siguen consultables. Lo que las borra es **B29**, con ventanas de vigencia.
2. **No persiste** la resolución, y **no carga perfiles de YAML**. Que quien
   llama pueda traer el suyo es el punto de extensión, y una carga declarativa
   es trabajo futuro — declararla como hecho sería documentar un hueco.
3. **No elige entre perfiles.** `resolver` recibe una intención; quién usa qué
   política es de quien pregunta, y es la misma línea que dice que no hay un
   ranking global.

### Una discrepancia de la spec, resuelta y said

`05-SPEC` no es coherente consigo misma: **§3** lista `intended_behavior` y
**§2 ejemplo B** usa `queryIntent: intended_architecture`. Se sigue §3 por dos
razones: es la lista normativa y explícitamente cerrada, y `AGENTS.md` §2.1
exige ADR para crecer un `Literal` — y el ADR que cubre esto (ADR-0028) no lo
pide. Crecerlo sería inventar un valor donde más se lee como verdad.

---

## B29 — Un cambio en el tiempo deja de leerse como una contradicción

**Objetivo cerrado.** Dos afirmaciones de la misma fuente que fueron ciertas en
instantes distintos dejan de contradecirse, y se puede preguntar qué se sabía
en una revisión dada.

### Lo que se midió antes de escribir nada

`scripts/measure_b29_vigencia.py` → **5/5 ABIERTAS**. Y la fila exagera en su
primera mitad: **decía que no se puede preguntar qué se sabía en una revisión, y
eso es falso** — `checked_at_revision` está en cada claim desde antes de esta
serie. Lo que no había era la **consulta**.

La mitad grave es otra, y es la que duele:

```
filas en claims:   c-A "psycopg" @revA    c-B "sqlite3" @revB
conflicts_for  ->  1 conflicto: [c-A, c-B]
resolver       ->  gana NADIE
```

**El sistema responde «nadie gana» a algo que tiene respuesta definitiva en cada
instante.** En `revA` era `psycopg`; en `revB` es `sqlite3`. Las dos
afirmaciones están, con su revisión, y no sabe. La causa es precisa:
`conflicts_for` compara valores **sin mirar el tiempo**, luego un hecho que
**cambió** se lee igual que uno que se **contradice**.

### El orden: por qué nace `revision_registro`

Las revisiones reales son SHAs, y compararlos **es lexicográfico y arbitrario**
(`rev10 < rev9`). Se introduce `revision_registro(seq, revision)`, donde `seq`
es **el orden en que ESTE store aprendió de esas revisiones**. No es ascendencia
de git — eso es `GitHistory`, que es B32 — y el nombre lo declara para que nadie
lo lea como más de lo que es.

### La ventana es `[desde, hasta)`, y el gate lo dice

No es una elección de gusto. El gate de `06-SPEC` §9, escrito por el bloque:

```
commit A: A -> calls B        commit B: A -> calls C
at(A) -> calls B             at(B)  -> calls C
```

En `revB` la respuesta es `calls C`, y **no las dos**. Con el extremo superior
inclusivo, `at(B)` devolvería las dos — media mitad de un conflicto. La primera
versión del bloque hizo la ventana cerrada por los dos lados, y por eso
`claims_at_revision(revB)` daba `['c-A', 'c-B']`.

### La asimetría de los `NULL`, interpretada en un solo sitio

| columna | `NULL` significa |
|---|---|
| `valid_from_revision` | «desde `checked_at_revision`» |
| `valid_until_revision` | «todavía vigente» |

`valid_from` en `NULL` es «desde que lo vimos», no «desde el principio de todo»,
que solo es cierto para el primer hecho de una cadena. Y `valid_until` en
`NULL` es «todavía vigente», que es lo que hace que un hecho sin reemplazo siga
compitiendo en HEAD.

`valid_from_revision` se escribe **tal cual lo declara el llamante**. Rellenarlo
con `checked_at_revision` rompía la ida y vuelta `get_claim(...) == Claim(...)`,
que es un contrato de B25: el store estaba guardando un campo que nadie había
declarado.

### La supersesión cierra ventanas; la cadena encadena una secuencia

Son dos cosas distintas y el bloque las separa. **Se cierran TODAS** las
afirmaciones abiertas de esa fuente que dijeran otro valor — una fuente no
sostiene dos cosas a la vez —, mientras que `supersedes_claim_id` es **singular**
y apunta a la más reciente, porque la cadena de `06-SPEC` §2 es una línea y
recorrerla hacia atrás tiene que tener un único predecesor.

Las tres condiciones que la supersesión **no** puede tocar, y que no estaban
escritas en ninguna parte, salieron de ejecutar la suite de B25–B28 sobre el
bloque ya implementado:

1. **Orden.** La consulta elegía «la vigente más reciente» sin mirar el orden:
   reingerir el mismo envelope cerraba la ventana del propio claim (rompía la
   idempotencia de B26).
2. **Valor.** Tampoco miraba el valor, pese a que el propio comentario del bloque
   decía «y el valor es otro». Reingerir la misma afirmación no es un cambio, y
   sin ese filtro la ventana dependía del orden de ingesta (rompía la propiedad
   de B27 de que el conflict set no dependa del orden).
3. **Alcance.** Cerraba solo la más reciente y dejaba abiertas las anteriores de
   esa fuente: entonces «cuál era la más reciente» dependía de cuál se guardara
   primero.

### Lo que este bloque NO hace

1. **No borra.** El claim viejo se queda, con su ventana cerrada. B27 no borra y
   B29 tampoco: lo que deja de competir no es lo que se elimina.
2. **No añade `GitHistory`** ni inventa el orden entre revisiones de dos
   almacenes distintos. B32 es quien trae la ascendencia real de commits.
3. **No reabre B27.** Misma fuente, misma revisión y otro valor **siguen
   avisando**: eso es una discrepancia de verdad, no un cambio en el tiempo.
4. **No supersede entre fuentes.** `06-SPEC` §2 habla de *source family*, y dos
   fuentes son dos familias: no se sabe cuál cambió de opinión.

### El contrasalto, y las dos sondas que Measure mal

**Instrumento:** 5/5 → **0/5**. **Contrasalto:** **5/5 sondas cazadas**,
`rc=0` al restaurar, y **verificado después de `ruff format`** — que es lo que
desancló las cinco de B28 en una sola pasada.

Dos cosas de este harness que los anteriores no tenían, y las dos salieron de
que la sonda **no era la sonda**:

- **Las sondas de existencia son multi-fichero.** M1 y M2 preguntan si el ADT
  declara la ventana y si la tabla tiene la columna de supersesión. La sonda
  honesta es **renombrar el identificador de punta a punta** —campo, columna,
  `ALTER TABLE`, mapper, `INSERT`— para que el árbol siga cargando y las otras
  cuatro preguntas sigan midiendo. Borrar la columna hace reventar el mapper:
  una sonda «cazada» por un crash, que no es la propiedad rota sino el árbol
  roto. Es el error 32 de B26 y de WI-113, por tercera vez.
- **M3 resultó INOCUA, y el motivo es el hallazgo más útil del bloque.** Apuntaba
  a `knowledge_repository.py`, pero `Storage.claims_at_revision` lo hereda de
  `KnowledgeDelegations`. Lo que se renombró fue el método interno; el público
  quedó intacto y P3 siguió cerrada — la lectura que miente en verde. MEDIDO, no
  supuesto: `getattr(Storage, 'claims_at_revision').__module__`.

Y M4 y M5 tocan el mismo `if` y **no son intercambiables**: M4 rompe la primera
mitad del contrasalto y abre P4; M5 deja HEAD **intacto** y abre P5 y **no** P4.
Un arreglo que comprase «cero conflictos» apagando el detector pasaría P4 en
verde.

### Un test que falló al escribirlo, con razón

`test_una_revision_ANTERIOR_no_supersede_a_una_posterior` afirmaba que en `rc3`
las dos afirmaciones de `false` coexistían. En el orden inverso de ingesta **no
es cierto**: ahí `rc3` ocupa la posición 1 del store y la otra todavía no se ha
aprendido.

No es un defecto. Es la **consecuencia declarada** de que `seq` sea el orden en
que el store aprendió, y fingir que `rc3` es siempre la posición 2 sería
inventarlo. Lo que sí es independiente del orden —y es lo que el test mide ahora—
es cuántas ventanas siguen abiertas al llegar el cambio.

---

### Lo que esta línea NO sustituye

**El gate de 1.0 sigue vivo y sigue siendo B9**, con sus dos propiedades que no
se abren desde el código: runtime real certificado (`OPEN` — una credencial) y
TUI operacional (`NO_MEASURABLE` — una persona). B25..B34 son ortogonales a las
dos y pueden avanzar sin tocarlas; lo que no pueden es declararlas resueltas, y
esta sección no lo hace.

### Procedencia, y lo que de ella llega a todo el mundo

`docs/skillgraph-epistemic-evolution-2026-10-06/` — 18 documentos: baseline,
visión, arquitectura objetivo, siete specs, roadmap, hitos, UAT/AAT, migración,
playbook, riesgos y nueve ADR (`ADR-0025`..`ADR-0033`).

**Esa carpeta no está versionada.** `.gitignore` deja `docs/*` fuera salvo
`docs/blueprint/` y `docs/architecture/`, por la política de WI-99 que separa la
evidencia que los UAT leen del material de trabajo. Consecuencia concreta: **la
tabla del mapa es la copia que llega a todo el mundo**, y quien solo tenga git
tiene el orden y los objetivos, pero no las specs ni los ADR. Es una deuda
conocida y asumida, no un olvido.

**Numeración: dos rebaseos, y el primero estaba mal.** La serie venía como
B22..B31 sobre un árbol donde B21 era el último cerrado. El primer rebaseo la
llevó a **B32..B41** y fue un error: si B22, B23 y B24 están ocupados, el
siguiente libre es **B25**, y B32..B41 dejaba B25..B31 —siete bloques— sin usar
en la autoridad. Segundo rebaseo a **B25..B34**, que es lo que está aquí.

### La frontera que los atraviesa

**El contrato va de SkillGraph a la herramienta, nunca al revés.**

```
              contrato de SkillGraph
                       ▲
                       │
   Adaptador CogniCode ┘
```

B31 es donde se paga caro si se invierte: si el modelo epistemológico se
diseñara alrededor de la forma de salida de un analizador concreto, cada
analizador nuevo obligaría a cambiar el núcleo, que es lo que `AGENTS.md` §4.3
prohíbe con `Protocol` y lo que el guard citado arriba ya mide.


## B23 — El instrumento de la verdad puede equivocarse, y se le ve

**Objetivo cerrado.** El instrumento que responde *«¿dónde está el proyecto y
qué toca después?»* era el apoyo de B0 a B22. B23 no lo endureció: lo
**encontró mintiendo**, y en tres dimensiones a la vez.

### Lo que se midió antes de escribir nada

`project_truth.py` no tenía línea de órdenes. `sys.argv` no se leía en ninguna
parte del fichero, y su raíz venía de `Path(__file__)`. Ejecutado, decía:

```
$ project_truth.py --raiz /tmp          rc=0, imprime la verdad del REPO REAL
$ project_truth.py --raiz /no/existe    rc=0, imprime la verdad del REPO REAL
$ cd /otro/arbol && project_truth.py    rc=0, imprime la verdad del REPO REAL
```

No era una ergonomía que faltara. Era un instrumento que **afirmaba haber
medido lo que no medía**, con la autoridad de quien publica la respuesta. Y
un flag que se ignora en silencio no es una opción: es una afirmación falsa
sobre lo que se acaba de contar.

### La ventana del ROADMAP: seis contradicciones y un «coherente»

`ROADMAP.md` declaraba, en su sección «Dónde está el proyecto», que esa línea
«la produce `scripts/project_truth.py`». **No la producía nadie.** La escribía
a mano, nadie la leía, y por eso el release `9961843` —que no tocó el fichero
— la dejó dos versiones atrás:

```
ventanas que publicaba el ROADMAP
  > `0.32.7.dev0` · tag `v0.32.7` · 3444 tests · 16/16 UAT
  > Versión activa `0.32.7.dev0` · último tag `v0.32.7` · 3431 tests · 16/16 UAT

la verdad: 0.33.0.dev0 · v0.33.0 · 3465 tests
veredicto que publicaba el instrumento: coherente = true
```

Seis contradicciones a la vista. Dos líneas, además, que se contradecían
**entre sí** —`3444 tests` y `3431 tests`— mientras el fichero era la
respuesta. Y un tercer hueco de la familia B20-2: el `bloque` se leía y se
publicaba, y no se cruzaba con nadie, de modo que STATE y CURRENT podían
concordar entre sí y el ROADMAP decir `B99` sin que nada lo notara.

### Lo que entra

La raíz pasa a ser **parámetro** en los doce lectores, y las constantes de
módulo desaparecen —su sola presencia es la invitación a leer de la raíz
equivocada—. Un `set_raiz()` global habría sido más corto y sería el estado
global mutable que `AGENTS.md` §1.4 prohíbe.

La ventana se **contrasta**, no se regenera: el instrumento sigue con cero
escrituras, porque uno que escribe el fichero de autoridad sería un problema
nuevo y peor que el que arregla. Las tres reglas nuevas —ventana contra
verdad, ventana contra ventana, bloque contra STATE y CURRENT— nombran
siempre las dos caras, como las que ya había.

Y `test_b14_truth_single_reader.py` **deja de deformar el árbol real**. Estaba
bloqueado por diseño desde B22, y la razón era el instrumento, no el test: sin
una raíz por parámetro, cualquier sandbox daba `ilegible` por el motivo
equivocado. Con la raíz, el sandbox se construye entero —su `.git`, su estado,
su ventana y un test propio— y las tres deformaciones apuntan allí. **MEDIDO**:
sha256 de los cuatro ficheros del árbol real antes y después de la corrida,
idénticos.

### Lo que el harness cazó, y era un hueco de verdad

Seis sondas, seis propiedades, 6/6. La primera corrida dio 5/6, y la sexta no
cayó por una razón que no era del harness: desactivada la comprobación del
código de salida de pytest, el verificador leía el **número parcial** de una
colecta rota y publicaba `coherente: true` con `tests_reales: 2`. Como el
parcial coincidía con el declarado, no había contradicción `tests:` que
emitir, y el guard miraba precisamente eso.

**Una aserción que mira la contradicción no ve la publicación.** Ese hueco
llevaba desde B14: lo peligroso no era que el número se comparara —eso
producía una contradicción visible— sino que coincidiera y no se notara. La
aserción se endurece a lo que la propiedad decía: negarse a publicar el
recuento y decirlo con `ilegible`.

### Lo que este bloque NO cierra, con motivo medido

- **`pipelinek` 0.39.0 no arranca en este entorno** (`INFRASTRUCTURE`, sin
  `wrapper.sh`). Es el binario, no el repo: los contratos de la receta se
  ejecutaron directo y están en verde. Backlog
  `bl-bl-01M3WJ3KCP000387S47TMRXK40`.
- **El instrumento no lo pide ninguna etapa de la receta.** El único
  consumidor en producción es el gate de 1.0, que se ejecuta a mano. En CI la
  red es `test_b0_truth_convergence.py`, que con B23 pasa de estar verde **por
  la razón equivocada** a estar verde **por la correcta**. No se añade etapa:
  el SHA-256 de `.pipeline.kts` es un invariante declarado desde WI-110.

---

## B22 — El árbol de trabajo no puede cambiar bajo los pies de un instrumento

**Objetivo cerrado.** Dos propiedades que solo se pueden violar a la vez, y por
eso nunca se midieron:

1. **Ningún test cambia el contenido de un fichero que git versiona**, salvo
   los que declaran por qué.
2. **Cuando un predicado del gate de 1.0 revienta, el informe conserva los
   veredictos de los otros diecinueve.**

**Medido antes de arreglar nada.** `measure_b9_gate_1_0.py` devolvió «Un
predicado revanto y el informe NO esta completo» y con eso borró los veredictos
de las otras diecinueve propiedades: cero información, no un OPEN. El
predicado que reventó es `_distribution_reproducible`, y revienta porque su
premisa —«nadie toca `src/skillgraph/__init__.py` mientras lo leo»— es falsa.
Que el contenido fuera el inyectado no es una sospecha: el sha256 de
`__version__ = "7.7.7"` es `7da24eaaf72e`, y durante la suite completa ese
fichero tuvo dos contenidos —el real en 195 649 lecturas y ese en 1 214—.

**Y el inventario sale de ejecutar, no de leer.** 25 escrituras que cambian
contenido, en tres ficheros de test. El grep encuentra seis: el séptimo —
`test_wi82`, que se llama «does not dirty tracked evidence» y por tanto declara
lo contrario de lo que hace— solo apareció al instrumentar.

**Lo que entra.** El guard vive en `tests/conftest.py` porque la propiedad es
sobre *toda* la corrida, y decide en `tests/test_b22_arbol_real.py`. Separa
**escribir** de **cambiar**: cinco escrituras sobre versionados no cambian
contenido —los `finally` del gate y de B15— y son el mecanismo correcto del
test que deforma y restaura; contarlas obligaría a prohibir restaurar. Toda
infracción ha de estar declarada, y toda declaración ha de seguir en uso.

**Lo que NO entra, con su motivo medido.** `test_b14` sigue deformando el árbol
real. El arreglo no es un test: `project_truth.py` deriva su RAIZ de
`__file__`, y medido que ningún sandbox da una respuesta de verdad — con los
cuatro ficheros que el script lee la colecta sale rc=5 y el verificador
responde `ilegible` por el motivo equivocado; con el árbol entero copiado sale
rc=3 porque la copia no es un repositorio. Las dos salidas piden que el
instrumento acepte su raíz por parámetro, que es la superficie de B0/B14.

**R2.** Cada predicado se ejecuta aislado y su excepción se convierte en su
veredicto, `NO_MEASURABLE` con la clase y el mensaje. `NO_MEASURABLE` y no
`OPEN` porque `OPEN` es una afirmación sobre el **proyecto** y un predicado que
revienta no ha medido nada. `listo_para_1_0` sigue exigiendo las veinte en
`PASS`, así que el 1.0 no se puede declarar: correcto, no un castigo.

**Cuatro defectos propios, que es lo que más costó.** La constante que programa
el guard al final llevaba escrito a mano un nombre de fichero que no era el
suyo: no casaba, no movía nada, y el guard corría **en cabeza** dando verde con
diecinueve infracciones ya registradas. El contrasalto del caso base usó B14
como ejemplo de escritor no declarado y se volvió no-op al registrar su deuda.
El informe del instrumento imprimía con los nombres que deja un `for` normal,
que ligan en el ámbito de la función, y por eso las dieciocho filas graves
salían con el autor del último. Y el harness dio un **4/4 falso**: las cuatro
sondas «cayaban» por un INTERNALERROR del propio hook al colectar, no por su
aserción.

**Harness 4/4** tras endurecerlo: exige que el test nombrado aparezca como
`FAILED` y detecta anclas ambiguas —M2 deformaba la primera de dos apariciones y
no miraba el sitio del guard—.

---

## B20 — El gate se contradecía a sí mismo

**Es el hallazgo más incómodo de la serie, y no es un `PASS` falso ni un
`OPEN` falso.** B16 abrió propiedades que daban verde con el defecto presente;
B18 endureció una que ya era cierta; B19 arregló un veredicto que afirmaba más
de lo que podía sostener. B20 es otra cosa: **el gate se contradice a sí
mismo**.

`ontology extensible` y `core sin dependencias de impl. externa` son dos
propiedades sobre la misma frontera. Con un solo import en `core/`, medido:

```
core/ importa skillgraph.packaging.manifest
  ontology extensible    : PASS   «no nombra ningún tipo de recurso»
  core sin dependencias  : OPEN   «depende de fuera de sí mismo»
```

Sobre la superficie **real** del proyecto, no sobre casos inventados: **7
contradicciones de 9**.

**La razón, y tiene las dos caras.** `_TIPO_DE_RECURSO` era
`^[A-Z][A-Za-z]*Pack$`, un patrón por forma. No veía lo que importa — de los
ocho tipos de recurso que el proyecto declara de verdad veía **cero**, y
`PackManifest` es el tipo central del proyecto — y veía lo que no importa: el
único nombre que contaba era `FilaDePack`, una fila de tabla. Con su import
puesto salía `OPEN` acusando al núcleo.

El comentario del código razonaba correctamente que no escribir una lista de
tipos evita una segunda fuente de verdad. Lo que no ve es que **un patrón por
forma *es* una lista**, más corta y peor: decide cómo se *escribe* un nombre en
vez de a qué conjunto *pertenece*. El endurecimiento de B16 fue sobre el formato
de la mirada, no sobre su alcance.

**Lo que entra.** El conjunto se deriva del árbol; la evidencia dice cuántos
tipos hay y de dónde salen; y los docstrings que nombran un recurso se dicen sin
abrir el veredicto, porque documentar la frontera es lo contrario de depender de
ella.

**El techo, y no se maquilla.** Quedan tres contradicciones y el motivo es uno:
el proyecto llama recurso a tres tipos cuyos paquetes no lo dicen. «Qué es un
recurso» no es un concepto que el código contenga, y declararlo es una decisión
de producto. Este bloque no la toma: la mide y la deja escrita, y el guard
**nombra** el techo en vez de contarlo, porque un techo que no se nombra no se
puede romper —medido, con la implicación invertida la lista queda vacía y cero
caben en tres, y la contrasalto de la contrasalto daba `NO CAYO` sin que nadie
supiera que el guard no tenía con qué enterarse—.

## B19 — «NO es reproducible» y «no he podido medirlo» son la misma frase

**Es el primer bloque de la serie que no es una propiedad falsa.** B16 y B17
abrieron propiedades que daban verde con el defecto presente; B18 endureció una
que ya era cierta. Aquí la propiedad **es cierta** y el defecto está en el verbo
del veredicto.

Nace de un `OPEN` de 1 de 8 que salió al certificar B18, con la evidencia
guardada: *«mismo contenido y distinta fecha dan bytes distintos en 2
artefacto(s)»*. Y la propiedad es cierta al revés, medido: **ocho
construcciones con la condición exacta del predicado dan bytes iguales 8 de 8**,
con y sin tocar la fecha, y dos sdists con la suite completa de pytest en
paralelo tienen contenido idéntico — 397 ficheros, 0 diferencias.

**El defecto, y hay dos causas que piden acciones opuestas.** Si el build es
irreproducible se arregla el **build**; si la entrada cambió entre las dos
mediciones se arregla la **medición**. El predicado no las distinguía y decía
«la distribución NO es reproducible» en los dos casos. Es grave aquí de un modo
que no lo era antes: `distribution reproducible` es la clase de propiedad **más
alta de la serie**, `ejecutada`, y la única que alguien podría citar para decir
que el build del proyecto es irreproducible sin comprobar nada más.

**Por qué no se resuelve dentro del artefacto: medido, no se puede.** Con un
fichero ya versionado que cambia entre las dos construcciones, los dos artefactos
son coherentes consigo mismos y aun así se construyeron con entradas
distintas. Hace falta el estado del árbol, y se toma con `_huella_de_entrada`
antes de cada construcción. **El diff es lo que aporta el contenido**: sin él
la huella sería un `git status` que solo ve nombres.

**Lo que ya existía y cubre la mitad, y no se toca.**
`sg_build_sdist_no_versionado` ya rechaza un fichero que git no versiona, con un
mensaje que es exactamente el que haría falta. La hipótesis más obvia era la
buena, y hay un test que lo comprueba: si el arreglo degrada un guard que ya
era correcto, se ha roto uno bueno mientras se arreglaba uno malo.

**La decisión es pura y por eso se prueba en milisegundos.** Medido: dejarla
dentro del predicado hacía que los tests tardaran cero, porque no se puede
deformar la decisión sin deformar también la construcción.

**Tres fallos propios, que importan más que el arreglo.** El test midió el
repositorio equivocado —y **falló**, que es como se pudo ver—. El contrasalto
de la sonda no aislaba el contenido, porque `git status` ya cambia entre «árbol
limpio» y «árbol editado». Y el harness no sabía leer su propia salida: dio
0 de 3 sobre tres sondas que sí habían caído.

## B18 — La frontera del núcleo no miraba la mitad de la superficie

**Es la cuarta de las siete que B15 nombró**, y la que B17 dejó escrita como la
primera que habría que mirar de las que quedan. El predicado es
`core sin dependencias de impl. externa`, y sus tres defectos tienen una raíz: no
sabía qué superficie estaba mirando ni de dónde salía su propia verdad.

Medido antes de escribir una línea, con el repo real intacto:

```
MEDIDO A · se añade a core/ un `from ..platform.storage import Storage` (relativo, nivel 2)
  veredicto : PASS
  evidencia : core/ no depende de fuera de si mismo, MEDIDO sobre ... (5 modulos)
  — byte a byte IDÉNTICA a la del caso limpio

MEDIDO B · se añade a core/ un `import pathlib` (estándar, no estaba en la lista)
  veredicto : OPEN
  evidencia : core/ depende de fuera de si mismo: ['pathlib']
  — un OPEN sobre una frontera que se estaba respetando
```

`_imports_de` exigía `nodo.level == 0`, así que un relativo de nivel 2 —que sale
de `core/` entero— era invisible y su evidencia era idéntica a la del caso
limpio. Y la estándar eran trece renglones escritos a mano sobre 290 que el
intérprete conoce: `pathlib`, `contextlib`, `abc`, `io`, `warnings` y `copy`
faltaban, luego un import legítimo producía un `OPEN` falso. **La lista no tenía
ni un nombre falso: era correcta y estaba vieja**, y una lista vieja no avisa,
simplemente empieza a dar veredictos que nadie revisó.

**Lo que entra.** Los relativos se resuelven a nombre absoluto; `_MODULOS_ESTANDAR`
se deriva de `sys.stdlib_module_names`; y la evidencia dice **cuántos ficheros se
recorrieron** y **de dónde sale la lista** —antes decía «(5 modulos)» sobre un
paquete de cuatro ficheros, contando nombres de import distintos, y no decía
cuántos ficheros había recorrido.

**Lo que no hace, a propósito.** No prohíbe los relativos: que `core/` escriba
`from .errors import ...` es correcto, y obligarle a escribir la forma absoluta
para que un predicado lo vea es cambiar el código para que el guard quede bien.
Lo que faltaba era mirarlos.

**El veredicto hoy.** 17 PASS / 2 OPEN / 1 NO_MEASURABLE, con esta propiedad en
**PASS** y **la clase sin cambios**, que es lo correcto: B18 endurece una
medición que ya era cierta, no una propiedad que fuera falsa.

## B17 — El ciclo de vida de los packs se decidía contando nombres

**Es la tercera de las siete que B15 nombró**, y la más fácil de las que quedan
por una razón que no es de estilo: el instrumento que hace el trabajo ya estaba
escrito y no se estaba usando.

`scripts/measure_b11_pack_lifecycle.py` responde cinco preguntas y **cada una
ejecuta la CLI de verdad** en un proyecto temporal, con su propio código de
salida. El gate no lo llamaba: decía «`sg pack` expone el ciclo completo» y su
único trabajo era mirar si tres cadenas estaban en un `dict` que sale del
parser.

Medido antes de escribir una línea, con la **decisión** de `install` rota en una
copia del árbol —y no `es_compatible`, que es la verdad del dominio:

```
MEDIDO A · install deja de rechazar un pack incompatible
  gate   : PASS    <- leía NOMBRES
  B11 Q1 : PASS    <- leía NOMBRES, y es LITERALMENTE el predicado del gate
  B11 Q2 : OPEN    <- EJECUTABA install con un pack incompatible
```

El ciclo de vida estaba roto y la propiedad que lo declara estaba en verde.

**Y el hallazgo más incómodo no es del gate:** el predicado **era Q1 del propio
instrumento**, y Q1 es la más débil de las cinco. El gate decidía «el ciclo de
vida existe» con la única pregunta que no lo prueba. No se reimplementa el
instrumento, se ejecuta —la forma de B12— y Q1 no se toca: es una condición
necesaria y barata, y lo que no puede hacer es bastar.

**Lo que entra.** El predicado ejecuta el instrumento y decide por su código de
salida; la evidencia pasa a ser el veredicto de las cinco preguntas nombrando
cuál cae; la clase de la propiedad pasa de `derivada` a `ejecutada`. Y una
separación que este bloque se encontró al escribirlo: un instrumento que no
arranca no es un ciclo roto, y decirlo como si lo fuera es afirmar una
ejecución que no ocurrió.

**La sonda que importa.** M6 no deforma el gate: deforma el **instrumento**, y
exige que el gate caiga. Si el único defecto posible fuera «el gate dejó de
mirar», bastaría comprobar que el gate llama al instrumento. M6 cayó, luego la
cadena decisión → instrumento → gate se sostiene entera.

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
