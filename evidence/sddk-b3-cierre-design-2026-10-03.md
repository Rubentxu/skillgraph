# Diseño — B3-cierre: adapter real y controller kernel

Ciclo `p-b7740b96d79ec013/b3` · fase `design`. Encadena con
`evidence/sddk-b3-cierre-spec-2026-10-03.md`, que dice **qué**; esto dice
**dónde va cada cosa y qué línea no se cruza**.

---

## 1. Una observación sobre la herramienta, antes que el diseño

`sddk architecture graph` no puede leer nada en este repo:

```
architecture: cannot read declaration
`/…/skillgraph/.sddk/architecture/contracts.yaml`: No such file or directory
```

**Este proyecto no declara un conjunto de contratos arquitectónicos para
SDDK.** Su arquitectura la hace cumplir con guardas propias, por AST, desde
WI-69. No es un defecto: es que la herramienta espera un fichero que este
repo nunca ha tenido, y el receipt de conformidad de `sddk architecture`
**no puede ser la evidencia** de este gate. Se usa en su lugar la medición
que sí existe y es del repo: la dirección de los imports, medida sobre el
árbol real.

Se declara aquí porque un gate que se pasa con una evidencia que no es del
repo que se está certificando sería exactamente el defecto que B3 ya corrigió
dos veces: un instrumento que dice medir algo y mide otra cosa.

## 2. Los dos módulos, y por qué en ese sitio

```
skillgraph/
├── platform/ports/capabilities.py     <- YA EXISTE. El contrato. No se toca.
│      contiene: Capability, CapabilitySpec, CapabilityRequest,
│               CapabilityResult, CapabilityRegistry, CapabilityNotFound
│
├── knowledge/knowledge_query.py       <- NUEVO. R1. El adapter real.
│      depende de: platform/ports/capabilities  (el CONTRATO)
│                   platform/ports/repositories  (el PORT, no la impl)
│
└── runtime/capability_controller.py   <- NUEVO. R2. El kernel.
       depende de: platform/ports/capabilities  (el CONTRATO)
```

### 2.1 El adapter va en `knowledge/`, no en un `adapters/` nuevo

Es la capability **de la capa de conocimiento**, y la capa de conocimiento ya
existe y ya tiene su contexto acotado. Crear `platform/adapters/` sería un
paquete nuevo cuya única razón de existir sería una clase, y pondría
adapters de producción al lado de los contratos que los describen: el
contrato y su implementación en el mismo sitio es el camino corto a que un
adapter se parezca a un puerto.

Además, `knowledge/context_controller.py` **ya** importa de
`platform/`, luego la dirección `knowledge → platform.ports` está probada en
el repo y no es una regla nueva.

### 2.1-bis Una hipótesis mía que la medición desmontó

Escribí este documento con la intención de justificar la elección de
paquetes diciendo que *«platform es la capa inferior»*. **Medido sobre el
árbol real, es falso:**

```
ficheros analizados: 80
inversiones platform->(knowledge|runtime|governance|cli): 10
  platform/event_store.py          -> skillgraph.runtime.engine
  platform/knowledge_claims.py      -> skillgraph.knowledge.graph
  platform/knowledge_delegations.py -> skillgraph.knowledge.graph
  platform/knowledge_mappers.py     -> skillgraph.knowledge.graph
  platform/knowledge_repository.py  -> skillgraph.knowledge.graph
  platform/run_delegations.py      -> skillgraph.runtime.engine
  platform/run_repository.py        -> skillgraph.runtime.engine
  platform/run_repository.py        -> skillgraph.runtime.runcontroller
  platform/storage.py               -> skillgraph.knowledge.graph
  platform/storage.py               -> skillgraph.runtime.engine
```

**Este repo no está estratificado.** `platform` depende de `runtime` y de
`knowledge` en diez sitios, y no son un defecto: son la razón por la que
`Storage` puede hablar con el motor.

La consecuencia es directa sobre lo que este bloque **no** va a hacer: **no
se escribe un guard de «platform no importa a runtime»**. Sería una regla
nueva que el repo no tiene, que el árbol viola hoy, y que un test así
—rojo desde el primer día, y sin relationship con el gate de B3— se
presentaría como si midiera la arquitectura cuando mediría una regla
inventada.

Lo que sí es invariante, y lo que sí se mide, está en §4: el contrato de
capability no nombra capabilities concretas. Esa es la frontera del
roadmap, y la que ya vigila `TestElNucleoNoImportaAdapters`.

### 2.2 El kernel va en `runtime/`, y NO en `core/`

Decisión forzada por el propio docstring de `core/__init__.py`:

> *«Pure types and errors that have no dependency on infrastructure,
> storage, runtime, or any other bounded context.»*

El kernel consume `platform.ports.capabilities`, que es **otro contexto
acotado**. Ponerlo en `core/` sería violar la regla que el propio paquete
declara sobre sí mismo, y ningún test lo habría cazado: el guard de imports
vigila quién importa a quién entre paquetes, no qué se puede meter dentro de
`core/`.

`runtime/` es donde vive el resto de la orquestación (`engine.py`,
`runcontroller.py`) y ya importa `platform.ports`. El kernel va con su
familia.

## 3. Las formas de datos

Tres, y ninguna es nueva en su categoría:

| Tipo | Dónde | Regla |
|---|---|---|
| `KnowledgeQueryCapability` | `knowledge/knowledge_query.py` | clase con `spec` e `invoke`. Inyecta el `Protocol` `KnowledgeRepository` por constructor. |
| `CapabilityController` | `runtime/capability_controller.py` | clase con `registry` inyectado. Sin singletons. |
| `CapabilityOutcome` | `runtime/capability_controller.py` | `frozen=True, slots=True`. Une el `CapabilityResult` con el `type_name` pedido. |

`CapabilityOutcome` existe, y no es un `CapabilityResult` con otro nombre,
por una razón concreta: **el `type_name` pedido y el `spec` del adapter que
respondió son dos cosas distintas**, y un despliegue podría resolver un
pedido con una versión distinta. Guardar solo el resultado pierde el
pedido; guardar solo el pedido pierde quién respondió. Sin el par, no se
puede responder «este nodo pidió `X` y alguien entregó `Y`».

## 4. La línea que no se cruza

> **Ningún módulo del núcleo nombra una capability concreta.**

Vigila: `runtime/`, `core/`, `resources/`. El kernel recibe **nombres**,
los resuelve contra el registro inyectado y devuelve resultados. Si mañana
aparece `sg.knowledge.query`, el kernel no cambia; si aparece
`sg.telemetry.query`, tampoco. Esa es la propiedad que el gate del roadmap
compra, y por eso se mide por AST sobre el árbol y no por un test de
comportamiento: un test de comportamiento pasa igual aunque el kernel tenga
un `if tipo == "sg.knowledge.query"` en el cuerpo, porque el resultado es el
mismo.

`AGENTS.md 1.1` aplica a las tres: `frozen=True, slots=True`, colecciones en
tupla, y builders que devuelven instancias nuevas.

## 5. Lo que el kernel NO hace, aunque el nombre lo sugiera

- **No emite eventos.** La procedencia se persiste desde `699e67d`, en el
  motor, que es quien sabe qué adapter invocó. Si el kernel emitiera, habría
  dos sitios que affirmar quién produjo algo, y el segundo sería peor.
- **No muta el grafo.** Un controller *observa y propone* — así lo dice el
  roadmap de B4. Este devuelve; escribir es trabajo de quien lo invoca.
- **No decide política.** Dice qué falta (`missing_from`) y ejecuta lo que
  hay. La decisión de si eso es admisible es de otro bloque.

## 6. Cómo se ve el fallo

`CapabilityNotFound`, tipado, con `code`, traducible a exit code por el
mecanismo de WI-109. El mensaje lista **todas** las que faltan y todas las
que hay, porque el caso real es el typo y se ve en la línea de error.

Un `None` o una lista vacía convertirían un fallo del despliegue en un
resultado vacío que tres capas más abajo alguien interpretará como «no hay
nada que leer».
