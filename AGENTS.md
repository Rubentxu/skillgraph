# AGENTS.md — Convenciones para agentes y humanos en SkillGraph

> Este archivo define reglas de **estilo, arquitectura y diseño**
> que TODO agente (humano o LLM) debe respetar al añadir o modificar
> código en este repositorio. Las reglas son obligatorias: no son
> sugerencias.

---

## 0. Identidad del proyecto

- **Qué es**: plataforma Python local-first para convertir skills de
  agente en workflows declarativos.
- **Source of truth**: `external/blueprint-v1/` (12 docs + 12 ADR +
  plan completo). NO contradecir el blueprint sin abrir una ADR.
- **Runtime objetivo**: Python ≥ 3.11 (en este repo: 3.13.15).
- **Toolchain**: `mise` + `uv`. NO pip, NO asdf, NO setup.py.
- **Estado del proyecto**: ver `CURRENT.md` y `STATE.yaml`.

---

## 1. Programación funcional: invariantes obligatorias

### 1.1 Inmutabilidad por defecto

Toda estructura de datos del núcleo debe ser **inmutable**.

- Dataclasses: `frozen=True, slots=True`.
- Colecciones: `tuple` (no `list`), `frozenset` (no `set`),
  `MappingProxyType` si hay que envolver un dict externo.
- Builders / constructores: devuelven **nuevas** instancias; nunca
  mutan `self`. Ver `skillgraph.dsl.PlanBuilder` como referencia.

Excepción documentada: cuando una pieza es **específicamente un
acumulador interno** (e.g. un builder mientras se compone), debe
declararlo en su docstring y exponer solo operaciones que devuelven
un builder nuevo. La regla `RUF005` está activada en ruff para
forzar `(*xs, x)` en vez de `xs + (x,)`.

### 1.2 Errores tipados, no strings

- Toda validación lanza `ValidationError`, `ParseError`,
  `IdentityConflictError`, `NotFoundError`, `IdempotencyError` o
  una subclase tipada de `SkillGraphError`.
- **Prohibido** `raise ValueError(...)` o `raise Exception(...)` en
  código de dominio. Los `Exception` genéricos SOLO en `except`
  como último recurso (e.g. para envolver fallos del Adapter).
- Cada excepción lleva un `code` estable (`sg_*`) usado por la CLI
  para traducir a exit codes.

**Cómo se comprueba (WI-109).** Las tres viñetas anteriores eran
declaración sin instrumento, y la medición encontró que la tercera
era falsa: el `code` se imprimía pero no traducía, y `main()` hacía
`except SkillGraphError -> EXIT_DOMAIN` para todo.

| propiedad | quién la mide | dónde |
|---|---|---|
| el `code` es la clave con la que se traduce a exit code | `exit_para(exc)` en `src/skillgraph/cli/exit_codes.py` | puro sobre `exc.code`; el módulo no importa nada (ADR-0016) |
| `main()` cablea la traducción y no colapsa a 10 | `tests/test_wi109_code_to_exit.py::test_main_usa_la_traduccion_y_no_el_catch_all_a_pelo` | por AST: un `return EXIT_DOMAIN` a pelo no cabe |
| cada error declara su `code` y no hay colisiones | `test_cada_error_de_dominio_declara_su_propio_code`, `test_ningun_code_comparte_clase` | por import real, sobre el `code` efectivo |
| la entrada de usuario malformada no sale como `Traceback` | `test_recipe_json_malformada_no_escapa_como_traceback` | `subprocess`, con proyecto en `tmp_path` |
| ningún `json.loads` de la CLI queda sin `try` | `test_todo_parseo_de_entrada_de_usuario_esta_protegido` | por AST sobre `src/skillgraph/cli/` |

Dos propiedades que la regla daba por ciertas y que la medición
desmentía, ahora vigiladas porque no se dan por solas:

- **Un `code` compartido rompe la traducción.** Si dos errores
  comparten `code`, no pueden salir con exit codes distintos, y el
  `code` deja de ser clave. Por eso toda clase de §1.2 declara el
  suyo; antes tres compartían `sg_error` y dos
  `sg_invalid_expansion`.
- **La traducción es una tabla, no un `except` por comando.** Añadir
  un `code` con exit code propio es un cambio de contrato externo
  (release MINOR). La tabla vive en `exit_codes.py` porque
  `parser.py` la consume sin arrastrar `Storage`: una traducción en
  `runner.py` sería inalcanzable desde ahí y devolvería a la colisión
  con el 2 de `argparse` que ADR-0016 resolvió.

**Lo que NO se comprueba, y sigue siendo deuda.** La prohibición
*literal* de `raise ValueError`/`raise Exception` se cumple hoy (`grep`
sobre `src/` → 0) y no tiene guard: no hay nada que vigilar mientras
sea cierto. Lo que el dominio lanza de verdad son otros builtins —
`TypeError` ×6, `KeyError` ×5, `RuntimeError` ×2,
`NotImplementedError` ×1, medido por AST— casi todos en invariantes
internas de adaptadores (`unwrap()`, `dto.py`) y no en el camino de
error que ve el usuario. Convertirlos es otro workitem; aquí sólo se
registra, porque un guard que declara exceptions en una lista es la
misma lista un nivel más abajo.

### 1.3 Sin I/O oculto

- Las funciones puras (e.g. `Handoff.context_hash`,
  `WorkflowPlan.successors`) no leen disco, red ni reloj.
- El reloj se inyecta (default factory con `datetime.now(UTC)`)
  y se puede mockear.
- Las dependencias externas (Storage, Adapter) se inyectan por
  constructor — no se importan módulos que abran conexiones al
  cargar el paquete.

### 1.4 Sin estado global mutable

- **Prohibido** `lru_cache` con argumentos mutables, singletons
  implícitos, variables de módulo que cambian en runtime.
- Si hace falta caché: una clase explícita con TTL/invalidación,
  detrás de una interfaz.
- El reloj global solo en `datetime.now(UTC)`, nunca `time.time()`
  directo (dificulta tests).

### 1.5 Funciones pequeñas y componibles

- Una función hace **una** cosa. Si el nombre contiene "y" o
  describe dos verbos, partir.
- Tamaño máximo recomendado: ~40 líneas (excluyendo docstring y
  type hints). Más allá: factorizar.
- Efectos secundarios al **final** y explícitos (orden:
  validar → calcular → persistir → emitir).

---

## 2. ADT (Algebraic Data Types): modelado de dominios cerrados

### 2.1 Tipos suma con `Literal`

Para dominios cerrados (estados, kinds, eventos), usar
`Literal["a", "b", "c"]` en vez de `str`:

```python
from typing import Literal

NodeKind = Literal["DecisionNode", "ActionNode"]
RunState = Literal["CREATED", "ACTIVE", "WAITING", "COMPLETED", "FAILED", "CANCELLED"]
EventKind = Literal["RunCreated", "NodeScheduled", ...]  # runtime.py
```

Anadir un valor nuevo es un cambio de **contrato** del blueprint;
no se hace por “feature creep”. Si necesitas un valor nuevo, abre
una ADR primero.

### 2.2 NewType para dominios abiertos pero restringidos

Para strings que vienen de fuera (CLI, Markdown, YAML) y que
tienen semántica propia, usar `NewType`:

```python
from typing import NewType

NodeName = NewType("NodeName", str)
OutcomeLabel = NewType("OutcomeLabel", str)
RevisionNumber = NewType("RevisionNumber", int)
```

Un `NewType` desaparece en runtime (cero coste) pero hace que el
type-checker rechace `plan.successors(outcome, ...)` por confusión
de etiquetas.

### 2.3 Smart constructors

Para cada `NewType`,提供一个 un **smart constructor** que valide:

```python
def node_name(s: str) -> NodeName:
    """Smart constructor: valida y devuelve `NodeName` tipado."""
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", s):
        raise ValidationError(f"NodeName invalido: {s!r}")
    return NodeName(s)
```

Reglas:

- Si una función devuelve un `NewType`, su nombre empieza con el
  tipo en snake_case (`node_name`, `outcome`, `revision`).
- Validación **atómica** en `__post_init__` (no `validate()` que
  pueda olvidarse de llamarse): ver `HandoffIdentity` y compañía.

### 2.4 ADT cerradas también en constantes

Cuando un `Literal` se usa para validaciones runtime
(`if kind not in {...}`), el conjunto canónico vive como constante
exportada con tipo `Final[frozenset[str]]`:

```python
NODE_KINDS: Final[frozenset[str]] = frozenset({"DecisionNode", "ActionNode"})
```

---

## 3. Mini-DSL: cuando una API fluent es la opción correcta

### 3.1 Cuándo añadir un DSL

Un mini-DSL se justifica solo cuando:

1. El **mismo concepto** (plan, política, receta) se declara en
   tres frentes: Markdown+YAML para el usuario, Python para tests,
   y un subconjunto desde la CLI.
2. El tipo Python es **compuesto** (no basta una sola función).
3. La forma declarativa es **más legible** que un dict literal.

NO añadir DSLs para:
- Una función con 2 parámetros (un dict basta).
- Una transformación con 1 punto de uso.
- Lógica con efectos (un DSL puro sin I/O está bien; uno con I/O, no).

### 3.2 Reglas de un DSL en SkillGraph

Si creas un DSL (ver `skillgraph.dsl.PlanBuilder` como referencia):

1. **Tipos nominales primero**: cada "palabra" del DSL tiene un
   `NewType` (NodeName, OutcomeLabel, ...).
2. **Constructores validadores**: cada NewType tiene un smart
   constructor que lanza `ValidationError` o `ParseError`.
3. **Inmutabilidad**: cada método del builder devuelve un builder
   **nuevo** (`__slots__`, sin setters).
4. **Sin I/O**: el DSL no toca disco, red ni reloj. La capa I/O
   (loader) es otra.
5. **Concordancia con el loader**: el DSL y el loader deben
   producir la **misma estructura** desde entradas equivalentes.
   Cubrir con un test (`test_dsl_matches_loader`).
6. **Errores tipados**: nunca `ValueError`, nunca `assert`.
7. **Docstring con ejemplo**: el `__init__` del builder debe
   incluir un ejemplo en formato doctest que se pueda ejecutar.

### 3.3 DSL declarativo existente

- **`skillgraph.dsl`** (Etapa 2 / S7): DSL para `WorkflowPlan`.
  Define `NodeName`, `OutcomeLabel`, `RevisionNumber`,
  `NodeKind` y `PlanBuilder` (fluent, inmutable).
- **`skillgraph.plan_loader`**: carga el mismo `WorkflowPlan` desde
  Markdown + YAML. La equivalencia se valida en
  `tests/test_dsl.py::TestDslMatchesLoader`.

---

## 4. Tipado estricto

### 4.1 Python tipado, sin `Any` innecesario

- **Todas** las funciones públicas declaran anotaciones de tipo
  en parámetros y retorno. Las privadas también, salvo cuando el
  cuerpo es trivial (`def _key(self): return self._x`).
- `from __future__ import annotations` en todos los `.py`.
- `Any` solo en:
  - Serialización (JSON/YAML).
  - Adaptadores externos (LLM, HTTP) donde el contrato es opaco.
- Prohibido `cast` salvo para narrowing de uniones que el checker
  no entiende (e.g. `cast(NodeKind, kind)` tras validar que está
  en el Literal). Si lo usas, comenta por qué.

### 4.2 Uniones explícitas

Si algo puede ser dos tipos, declararlo:

```python
def _parse_node(data: Any) -> WorkflowNode: ...  # I/O: Any permitido
def successors(self, node: NodeName, outcome: OutcomeLabel) -> NodeName | None: ...
```

Prohibido `Optional[T]` (preferir `T | None`, idiomático en 3.10+).
Prohibido `Union[A, B]` cuando `A | B` es la forma actual.

### 4.3 Protocol para dependencias inyectables

Las dependencias del core (Storage, Adapter, EventLog) son
`Protocol`s o clases abstractas. El RunController **depende del
protocolo, no de la implementación**:

```python
class AgentAdapter(Protocol):
    def invoke(self, handoff: Handoff) -> AgentResult: ...
```

### 4.4 Cobertura mínima de tipos

- Toda función pública con retorno no-`None`: el test debe
  comprobar el tipo del retorno o usar aserciones claras.
- `Sequence[X]` o `tuple[X, ...]`, nunca `list[X]`, cuando la
  colección es inmutable.
- `Mapping[K, V]` cuando la colección es solo de lectura.

---

## 5. Reglas de estilo (ruff)

Configuración en `pyproject.toml`. Reglas activas relevantes:

- `E/F/I/B/UP/SIM/RUF` — lo básico.
- `RUF005` — `(*xs, x)` en vez de `xs + (x,)` (forzar estilo
  unpacking inmutable).
- `B008` — `default_factory` no debe llamar funciones con
 副作用 en dataclass defaults.
- Formato: `ruff format` con defaults (88 cols).

---

## 6. Reglas de testing (vinculadas a las de AUTO)

### 6.1 TDD rojo → verde → refactor

- Antes de implementar, escribe el test (puede ser uno solo que
  ejercite el contrato mínimo).
- Ciclo: ejecutar tests → ver rojo → mínimo código → verde →
  refactorizar → verde.
- No avaces al siguiente test hasta que el actual esté verde.

### 6.2 Marcadores pytest

- `pytest.mark.etapa1`, `pytest.mark.etapa2`, ... para agrupar
  verticales.
- `pytest.mark.parametrize` cuando hay variaciones del mismo
  contrato.
- NO usar `pytest.skip` para esconder fallos: o arreglas el test
  o lo borras.

**Un `skip` por falta de artefacto es el mismo defecto, con otra forma.**

**Cómo se comprueba (WI-108).** La regla se mide en dos sitios distintos,
porque son dos propiedades distintas y el CI solo puede ver una:

| propiedad | quién la mide | dónde |
|---|---|---|
| un run con `skipped`/`xfailed` es un incumplimiento | `sg_pipeline_tests_skipped` | etapa `evidence` de `.pipeline.kts`, vía `scripts/check_pipeline_receipt.py` |
| todo skip del repo está declarado, y todo declarado existe | `tests/test_wi108_zero_skips.py` | pytest, sobre el **AST** de `tests/**/*.py` |

La lista de skips **legítimos** es `SKIPS_PLATAFORMA` en
`scripts/check_pipeline_receipt.py`, y se vigila en las dos direcciones: un
skip de plataforma que se borre deja la declaración sin suelo, y un skip
nuevo que nadie declare es un incumplimiento. La lista no es «los skips que
hay», es «los skips cuya ausencia sería un defecto».

El guard mira el **AST**, no el texto. La propiedad es «este código *llama*
a `pytest.skip`», y un docstring que lo menciona es indistinguible de una
llamada si buscas la cadena. La primera versión de ese guard buscaba con
regex y se puso roja por la documentación del propio test que lo llevaba.

Medido el 2026-10-03, antes del arreglo: un run cuyo resumen era
`2715 passed, 3 skipped` daba **cero problemas** y el guard imprimía
«OK: el run cumple los criterios que declara AGENTS.md». El criterio 2 —el
que existe para separar un run real de un veredicto cacheado— aceptaba el
resumen con skips sin pestañear, porque la pregunta no se había hecho.

**Límite declarado:** un `from pytest import skip` seguido de `skip(...)`
no lo ve el AST, porque el nombre ya no es `pytest.skip`. Es un alias, no
la forma que pytest documenta, y no se cubre. Queda escrito en vez de
descubrirlo.

Un gate que lee un fichero fechado y se salta si no existe no mide la
propiedad que declara: mide si hoy alguien se acordaba de correr algo.
MEDIDO en WI-103, con el gate que vigila que `main` no vuelva a listarse
como hotspot público (`cc>=20`):

| | |
|---|---|
| informes `architecture-debt-*` | **6** en 7 días (falta el `2026-09-30`) |
| hoy | sin informe → gate en `SKIPPED`, **exit 0** |
| informe de hoy generado | 1 passed (`main` no es hotspot hoy) |
| informe de hoy con `main` inyectado | 1 **failed**, exit 1 |

La propiedad era real y el gate mordía cuando el artefacto estaba. El
defecto era **la existencia del artefacto**, y por eso la regla es más
específica que la de arriba:

> **Un gate mide.** Si su propiedad es sobre el código, ejecuta el análisis
> sobre el código. Si su propiedad es sobre un artefacto versionado,
> entonces el artefacto es parte del contrato y su ausencia es un fallo, no
> una excusa para no mirar.

Y el contrasalto, porque es donde estos casos se esconden: **un gate que
solo sabe pasar no está probado.** El arreglo de WI-103 trae un
contraejemplo que construye un árbol con un `main` real de `cc>=20` y exige
que la medición lo vea. Sin ese test, una medición que devolviera siempre
`()` habría pasado todo verde — indistinguible de la que no mide nada.
Mutaciones 5/5, y la M2 es exactamente esa: la medición que no mide nada.

### 6.3 Cobertura mínima

El suelo lo hereda el **paquete**, y el paquete no se declara: lo hereda
todo módulo que cuelgue de un subdirectorio de `src/skillgraph/`.

- Todo módulo de cualquier paquete: **≥ 90 %**.
- `cli/`: **≥ 70 %** (lo que falta son ramas de error que ya cubre
  integración).
- `src/skillgraph/platform/paths.py`: **≥ 60 %** (la rama de Windows no se
  ejecuta en CI).

`src/skillgraph/__init__.py` y `__main__.py` no cuelgan de un
subdirectorio y están en `omit` de `pyproject.toml`: §6.3 no los gobierna.
Un paquete que necesite un suelo distinto del 90 % se declara en
`SUELOS_ESPECIALES`, y un módulo suelto en `EXCEPCIONES`, dentro de
`scripts/check_coverage_floors.py`.

Esta sección **no enumera módulos**, y es a propósito. La versión anterior
los enumeraba —`errors, bricks, parser, registry, storage, runtime,
handoff, agent, workflow, runcontroller`— y esa enumeración era una fuente
de verdad más: `runtime` no es un módulo sino un paquete, y nueve de los
diez vivían fuera de `core/`. Medido y cerrado en WI-107; el guard que lo
impide es `tests/test_wi107_coverage_package_symmetry.py`.

### 6.4 Tests de extremo a extremo

Para cada `UAT-*` del blueprint:

- Un test Python que ejercita la lógica de negocio.
- Un test CLI (`subprocess`) que verifica el contrato externo:
  exit code + salida + side effects en disco.
- Sin mocks para Storage/SQLite; usa `:memory:` o `tmp_path`.

---

## 7. Reglas de Git

- Commits pequeños y atómicos: un vertical slice por commit.
- Mensaje: `tipo(scope): descripción corta`, 72 cols en el
  subject, body justificado si hay decisiones o bugs no obvios.
- Tipos: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`,
  `perf`, `ci`.
- NO `git push --force` sobre main.
- NO merges con `--no-ff` decorativos; el historial es lineal.

---

## 8. Decisiones de arquitectura (resumen, no exhaustivo)

- **Storage**: SQLite por proyecto, WAL, FK on, migración
  idempotente. Cero ORM; SQL directo con índices por
  `(tenant_id, project_id, ...)`.
- **Eventos**: append-only en `runtime_events` con `UNIQUE(event_id)`.
  Idempotencia por constraint, no por código.
- **Handoff**: inmutable + SHA-256 sobre serialización estable
  (capacidades y budget ordenados). El Adapter recibe el hash
  firmado; nunca lo recalcula.

### Cómo se comprueba (WI-111)

Las tres mitades de esa viñeta se sostendrán por separado, porque
antes de WI-111 **ninguna** se sostenía. `frozen=True` congela el
*enlace* del atributo, no su *valor*: con `budget: dict[str, int]`
la estructura era mutable por dentro.

| propiedad | quién la mide | cómo |
|---|---|---|
| `budget` no es un dict mutable | `TestElBudgetNoEsUnDictMutable` | `MappingProxyType` sobre una **copia**; escribir lanza `TypeError` |
| el llamante no puede alterar el handoff a posteriori | `test_el_valor_recibido_no_se_aliasa_al_llamante` | mutar el dict externo no toca el handoff |
| el hash lo calcula el Core **una vez**, al firmarlo | `test_el_hash_no_se_calcula_una_segunda_vez` | contador de llamadas a `context_hash`, por origen |
| la fila y los eventos no describen handoffs distintos | `TestElHashNoSeRecalculaDespuesDelInvoke` | **se ejecuta un nodo y se lee de disco** |

**El guard no lee el código: ejecuta un nodo.** Un guard que comprobara
`frozen=True` por AST mediría la *regla*, no el *defecto*: el
defecto estaba en la distancia entre el instante en que el Core firma
el hash y el instante en que el Adapter recibe el handoff, y esa
distancia no se ve en el texto. Se mide leyendo `node_executions` y
`runtime_events` después de un `reconcile_run` de verdad.

Medido antes de arreglar nada:

```
fila node_executions.context_hash : 0063e7dfd167afc6...
evento NodeCompleted               : 951a2d3a16cf7ea8...
evento EvidenceProduced            : 951a2d3a16cf7ea8...
hash que el Adapter vio AL ENTRAR  : 0063e7dfd167afc6...
budget en handoff_json persistido  : {'max_nodes': 1}
```

La fila describe el handoff de **antes** y los eventos el de
**después**, para la misma `node_execution`. El `handoff_json`
persistido no tiene la clave que el Adapter inyecto: la fila precede
al Adapter, y por eso es la firma.

**Dos cosas que el guard tiene que evitar, y las dos costaron una
mutacion cada una:**

- **No comparar con `==` para exigir un tipo.** Un
  `MappingProxyType` **es igual** a un `dict`: un test que miraba el
  valor pasaba con el mapping vivo devuelto. Lo que discrimina es el
  tipo, y sobre todo que `json.dumps` lo acepte.
- **No contar llamadas sin distinguir el origen.** La lectura que hace
  el propio Adapter no es una recalculación del motor. Se cuenta por
  origen, o el test exige 1 y obtiene 2 por una razón que no es la
  que vigila.

Mutaciones: **5/5** cazadas, con sonda por mutación
(`.pipelinek/wi111_mutate.py`). M5 se reescribió dos veces: la
primera quitaba el `sorted()`, que resultó **inocua** — quitar el
orden no rompe la copia— y la sonda apuntaba a un test que comparaba
dos handoffs distintos en vez de re-leer el que mutó, un test que no
podía fallar nunca.

- **Adapter**: `Protocol` para invertir dependencia; `FakeAgentAdapter`
  lee fixtures desde disco. **No** se ejecuta código Python del
  Domain Pack al importar (UAT-14).
- **RunController**: una pasada por `reconcile_run` (un nodo).
  El CLI scheduler llama de nuevo para avanzar.
- **Rust**: NO en el bootstrap. 5 puntos de entrada documentados en
  `CURRENT.md` con trigger GO medible.

---

## 9. Cómo añadir código nuevo (checklist)

Antes de abrir un PR (o commit, si AUTO):

1. [ ] He leído el doc del blueprint relevante.
2. [ ] He definido los tipos (`Literal` o `NewType`) primero.
3. [ ] He escrito un smart constructor para cada `NewType`.
4. [ ] He escrito tests rojos antes de implementar (TDD).
5. [ ] Las estructuras son `frozen=True, slots=True` (si son
   dataclasses) o tuplas inmutables.
6. [ ] Las funciones de dominio lanzan `SkillGraphError` o
   subclase; nunca `ValueError`.
7. [ ] El builder/DSL (si aplica) devuelve instancias nuevas;
   nunca muta.
8. [ ] He actualizado `CURRENT.md`, `STATE.yaml` y
   `SESSION-JOURNAL.md` con el nuevo workitem.
9. [ ] He corrido `mise exec -- uv run pytest` y `ruff check src tests`
   y todo está verde.
10. [ ] Si toqué `pyproject.toml`, `src/skillgraph/__init__.py` o
    cualquier cosa que entre en el paquete, he corrido
    `mise exec -- uv run python scripts/check_package_build.py`
    y el contrato de empaquetado está verde (§12).
11. [ ] El commit message describe el "por qué", no el "qué".

---

## 10. Excepciones y overrides

Cualquier desviación de estas reglas requiere:

1. Comentario en el código explicando el motivo.
2. Entrada en `SESSION-JOURNAL.md` con la fecha y la justificación.
3. Si es material (afecta contratos o arquitectura), abrir una ADR
   en `external/blueprint-v1/adr/` o proponer una nueva.

Sin un override documentado, el linter o el revisor puede pedir
reversión sin más discusión.

---

## 11. Inspiración funcional al estilo Haskell

Esta sección **traduce** principios que damos por sentados en
Haskell / Elm / Rust al dialecto Python. No es Haskell con otra
sintaxis: es "lo mejor de Haskell que Python puede sostener sin
romper el ecosistema".

> Haskell se suele leer como "**lo que es, no lo que hace**".
> Un `WorkflowPlan` no se construye paso a paso: se **describe**.
> Un estado no cambia: **se transforma**. Un error no se lanza
> con un mensaje: **se modela**.

### 11.1 Pureza por defecto (purity)

Inspirado en IO de Haskell: separa el cálculo puro del efecto.

```haskell
-- Haskell
executeNode :: Node -> Handoff -> Either AppError AgentResult
```

```python
# Python en SkillGraph
def plan_handoff(node: WorkflowNode, ctx: NodeContext) -> Handoff:
    """Funcion pura: no toca Storage ni Adapter. Produce un Handoff."""
```

Reglas:

- **Pureza estructural**: una función no debe leer disco, red ni
  reloj, NI recibir objetos que lo hagan (Storage, Adapter).
- Si una función necesita un efecto, que sea **un argumento explícito**
  (inyección de dependencia) o un `Protocol` con una sola operación.
- Una función pura debe ser **total**: mismo input → mismo output,
  sin excepciones para datos válidos. Las excepciones son para
  entradas inválidas (verificables).

### 11.2 Transparencia referencial (referential transparency)

Inspirado en `Data.Function.&`: el resultado de evaluar una expresión
puede substituirse por su valor sin cambiar el programa.

```python
# BIEN: el resultado es substituido sin cambiar el comportamiento
hash_a = handoff_a.context_hash
hash_b = handoff_b.context_hash
if hash_a == hash_b:
    ...

# MAL: el resultado depende de estado oculto (orden de lectura, reloj)
if Path(file).stat().st_mtime > some_timestamp:
    ...
```

Reglas:

- Las funciones puras pueden **componerse**: `f(g(x))` debe ser
  equivalente a `let y = g(x) in f(y)`.
- **Prohibido** capturar `self.method` indirectamente cuando el
  método tiene efectos (e.g. `def compute(self): return self._conn.execute(...)`).
  Convertirlo en función pura o pasar la dependencia explícita.

### 11.3 Composición con `pipe` / `compose`

Inspirado en `Data.Function.(.)` y `Control.Pipeline`:

```haskell
-- Haskell
process = validate >> compile >> execute
```

En Python lo escribimos con generadores o con `functools.reduce`:

```python
from functools import reduce


def pipeline(value, *funcs):
    return reduce(lambda v, f: f(v), funcs, value)


# Uso:
plan = pipeline(raw_dict, parse_frontmatter, validate_plan, freeze)
```

Reglas:

- Para `n > 3` pasos, **componer** con un pipeline es preferible a
  anidar llamadas. Mejor legibilidad, mejor testeo.
- Cada paso del pipeline debe ser **puro** (11.1).

### 11.4 Pattern matching como dispatch (sum types)

Inspirado en `case ... of` y `Either a b`:

```haskell
case outcome of
  "ok" -> proceed
  "no"  -> branch
  _     -> default
```

En Python lo hacemos con `match/case` (3.10+), **pero** con ADT
cerradas, no con `Any`:

```python
match outcome:
    case "ok":
        ...
    case "no":
        ...
    case _:
        raise OutcomeInvalidError(outcome)
```

Reglas:

- Preferir `match/case` con `Literal` cuando el dominio es cerrado.
- Si la rama `_` es reachable, falta una validación en el sum type
  (volver a 2.1).
- **Prohibido** `match obj.attr` con strings arbitrarios: el `match`
  pierde la potencia del type checker.

### 11.5 `Maybe` / `Optional` como semántica, no como sintaxis

Inspirado en `Maybe a = Just a | Nothing`:

```haskell
-- Haskell
findNode :: WorkflowPlan -> NodeName -> Maybe WorkflowNode
```

En Python: `WorkflowNode | None` con un protocolo claro.

Reglas:

- **Nunca** usar `None` como centinela de "no encontrado" sin
  documentar. La firma `def find(...) -> T | None` lo dice.
- Para errores recuperables (e.g. "nodo terminal sin sucesor"),
  preferir `T | None` en vez de una excepción. Las excepciones son
  para **irrecuperable** o **invariante violada**.
- Para errores tipados (reutilizables), usar `Result`-style:

  ```python
  @dataclass(frozen=True, slots=True)
  class Result(Generic[T, E]):
      value: T | None
      error: E | None

      @property
      def is_ok(self) -> bool:
          return self.error is None
  ```

  O más simple: una tupla `(T | None, str | None)` con un
  protocolo que documente el contrato. **No** acumular flags.

### 11.6 Composición de errores con ADT jerárquica

Inspirado en `ExceptT m a` y `Data.Validation`:

```haskell
-- Haskell
data AppError
  = NotFound Text
  | ParseFailed Text
  | ValidationFailed [ValidationError]
```

En SkillGraph, esto YA está modelado con jerarquía de excepciones:

```python
class SkillGraphError(Exception): ...  # raiz


class ValidationError(SkillGraphError): ...  # subtipo


class ParseError(SkillGraphError): ...


class UnknownKindError(ValidationError): ...  # sub-subtipo
```

Reglas:

- Para añadir un error, decidir primero **dónde vive** en el árbol.
  `sg_*` code en cada nivel.
- **Prohibido** `except SkillGraphError` para "tragarse" errores
  sin re-lanzar o registrar.

### 11.7 Kleisli / composición de funciones con efecto

Inspirado en Kleisli category (`a -> m b`):

```haskell
-- Haskell
parsePlan :: String -> Either AppError WorkflowPlan
validatePlan :: WorkflowPlan -> Either AppError WorkflowPlan
persistPlan :: WorkflowPlan -> IO AppError
```

En Python con `Result`:

```python
def parse(text: str) -> Result[WorkflowPlan, ParseError]: ...
def validate(plan: WorkflowPlan) -> Result[WorkflowPlan, ValidationError]: ...


plan = parse(text).bind(validate)
```

Reglas:

- Cuando una transformación puede fallar Y su salida alimenta a otra
  transformación, modelar con `Result` (11.5) y **componer**.
- **Prohibido** encadenar 4 `try/except` en cascada: refactorizar a
  un `Result` o a una mónada específica.

### 11.8 Funciones de orden superior (HOF)

Inspirado en `map`, `foldl`, `filter`:

```haskell
-- Haskell
map node_name (planNodes plan)
```

En Python:

```python
# BIEN: composicion declarativa
node_names = tuple(n.name for n in plan.nodes)

# MEJOR con HOF:
from functools import reduce


def compose2(f, g):
    return lambda x: f(g(x))


# La regla es: si usas un patron `for` que solo acumula,
# sustituir por comprehension, reduce, o itertools.
```

Reglas:

- **Prohibido** un `for` que solo acumula en una lista cuando hay
  una comprehension que dice lo mismo.
- **Prohibido** un `for` que solo cuenta cuando `sum(1 for ...)` o
  `len([...])` lo dice.

### 11.9 Inmutabilidad por construcción (structural sharing)

Inspirado en Data.Sequence / Data.Vector de Haskell: cada `(*xs, x)`
comparte estructura con `xs`. Python no lo hace automáticamente,
pero **el patrón sí** y el GC ayuda.

```python
# BIEN: el builder nuevo comparte _initial con el viejo si no cambia
new_builder = old_builder.starts_at(name)  # copy-on-write manual
```

Reglas:

- **Nunca** `xs.append(x)` en código de dominio. Siempre `(*xs, x)`.
- Si necesitas "modificar" un objeto, devuelve uno **nuevo** con
  los campos cambiados. El viejo sigue siendo válido.

### 11.10 Currificación parcial (partial application)

Inspirado en la currificación automática de Haskell:

```haskell
-- Haskell
add :: Int -> Int -> Int
add 1 2  -- = 3
let addOne = add 1
addOne 2  -- = 3
```

En Python con `functools.partial`:

```python
from functools import partial


def make_event(kind: str, tenant: str, project: str, payload: dict) -> RuntimeEvent: ...


make_node_event = partial(make_event, kind="NodeScheduled")
```

Reglas:

- Si una función **siempre** toma los mismos 2-3 argumentos en
  un sitio, factorizar con `partial` o un closure.
- **Prohibido** pasar `tenant_id, project_id, run_id` 14 veces en
  el mismo método: crear un `RunContext` (dataclass frozen) que los
  agrupe y se inyecte.

### 11.11 Funciones sobre tipos: typeclasses / Protocol

Inspirado en `class Functor f where fmap`:

```python
class Mappable(Protocol[T]):
    def map(self, f: Callable[[T], T]) -> "Mappable[T]": ...
```

Reglas:

- Las dependencias inyectables son **Protocols**, no clases
  abstractas con `abc.ABC` (a menos que haya estado compartido).
- `Storage`, `Adapter`, `EventLog`, `RunRepository`: todos
  Protocol o dataclass final.

### 11.12 Pruebas como propiedades (QuickCheck-style)

Inspirado en QuickCheck de Haskell:

```haskell
prop_roundTrip :: WorkflowPlan -> Bool
prop_roundTrip p = fromJSON (toJSON p) == Right p
```

En Python con `hypothesis`:

```python
from hypothesis import given, strategies as st


@given(st.integers(min_value=1))
def test_revision_never_negative(n: int) -> None:
    rev = _make_revision(n)
    assert rev >= 1
```

Reglas:

- Para cada invariante "todo X tiene propiedad P", escribir un
  property test (no solo ejemplos).
- **Si añades Hypothesis**, declaralo en `pyproject.toml` y úsalo
  solo donde aporte (parsers, validadores). Para el resto, tests
  deterministas son más rápidos y reproducibles.

### 11.13 Lo que NO importamos de Haskell

- **Lazy evaluation**: Python es estricto. No simular con generadores
  donde no aporta legibilidad.
- **Type classes con dispatch dinámico**: usar `singledispatch` o
  un dict de estrategias solo si el beneficio es claro.
- **Do-notation / comprehensions de mónadas**: `bind`/`fmap` ya
  son explícitos. No esconder el efecto.
- **Cero mutabilidad absoluta**: `__post_init__` es válido para
  invariantes. Lo inmutable es **el dato publicado**, no el
  proceso de construcción.

### 11.14 Anti-patrones que detectaremos en revisión

Si tu código cae aquí, el revisor (humano o LLM) puede pedir
reversión sin más discusión:

1. `def f(...) -> ...` que lee `self.something` con side-effects
   cuando existe una firma pura equivalente.
2. `match/case` sobre strings que **no** son `Literal`.
3. `for` que solo acumula cuando hay comprehension.
4. `try/except Exception` sin re-raise ni registro.
5. `cast(...)` en código de negocio (no en adaptadores).
6. `@lru_cache` sobre funciones con argumentos mutables.
7. Importar un módulo solo para "pillar su variable global".
8. `Optional[T]` en vez de `T | None`.
9. `from typing import List, Dict, Tuple` en vez de `list, dict, tuple`.
10. `pass` en un `except` sin comentario explicando por qué.

### 11.15 Referencia mental

| Haskell / Elm         | SkillGraph                                  |
|-----------------------|---------------------------------------------|
| `data X = A \| B`     | `X = Literal["A", "B"]`                     |
| `newtype X = X T`    | `X = NewType("X", T)`                       |
| `Maybe a`             | `T \| None`                                 |
| `Either a b`          | `Result[T, E]` o jerarquía de excepciones   |
| `>>>` / `.&.`         | `reduce(lambda v, f: f(v), funcs, v)`       |
| `fmap`                | comprehension / `map(f, xs)`                |
| `case ... of`         | `match/case` con `Literal`                  |
| `pure`                | función pura sin argumentos de efecto       |
| `>>=`                 | `result.bind(next)`                         |
| ADT recursiva         | dataclass con `tuple` de la misma ADT       |
| `Data.Map.Strict`     | `Mapping[K, V]` (read-only) o `dict`         |

Si dudas, pregúntate: **"¿cómo escribiría esto en Haskell sin
`unsafePerformIO`?"**. Si la respuesta es "no puedo" o requiere
una mónada específica, **entonces tu función no es pura y debe
declarar sus efectos**.

---

## CI Local Obligatorio — pipelinek

**Este proyecto adopta `pipelinek` como mecanismo canónico de CI local.**

Toda verificación de estado del repositorio debe ejecutarse a través del script
versionado en `.pipeline.kts`, ubicado en la raíz del proyecto. Ningún agente,
sesión humana o pipeline externo puede declarar el repositorio en estado
"verificado" sin haber ejecutado ese script y observado un `Pipeline finished
with SUCCESS` terminal.

### Binario

`pipelinek` v0.39.0. La versión se fija en `mise.toml` con el id de
backend completo (`"github:Rubentxu/pipeline-kotlin" = "0.39.0"`); no
confíes en el `pipelinek` que aparezca en el `PATH`, porque `asdf`
expone un shim con la MISMA ruta de nombre y otra versión. Resuelve con
`mise which pipelinek` antes de ejecutar.

Comando canónico desde la raíz del proyecto:

```bash
mise exec -- pipelinek run --rerun \
              --db .pipelinek/db.sqlite \
              --control-root .pipelinek/control \
              .pipeline.kts
```

> **`--rerun` no es opcional.** El motor cachea el resultado por
> `cacheKey` de compilación del script. Sin `--rerun`, un run cuyo
> script no ha cambiado **reutiliza el veredicto previo y termina en
> `Pipeline finished with SUCCESS` sin ejecutar un solo step**: cero
> `StepStarted`, cero `EchoOutputCaptured`, stages completados en
> milisegundos. Medido el 2026-10-02: run canónico de 72 ms con 5/5
> stages "success" y ninguna línea de pytest en el journal. Es el modo
> de fallo "SUCCESS cacheado" que esta misma sección ya describía.

### En un clon nuevo (WI-99)

El comando canónico tiene **dos precondiciones** que no se ven leyendo esta
sección, y ambas se descubrieron midiendo en un clon recién hecho. Sin ellas,
el comando de arriba no ejecuta nada y devuelve un error que no menciona
esta sección:

```bash
mise trust                       # sin esto: "Trust them with `mise trust`"
mkdir -p .pipelinek              # sin esto: java.sql.SQLException (abajo)
```

`mise` no ejecuta las herramientas de un checkout en el que no confía. Y
`pipelinek` **abre el fichero SQLite, no el directorio que lo contiene**:

```
java.sql.SQLException: path to '.pipelinek/db.sqlite':
'/ruta/al/clon/.pipelinek' does not exist
```

Por eso `.pipelinek/.gitkeep` está **versionado**: el directorio tiene que
existir en un clon nuevo para que el comando documentado sea ejecutable tal
cual. Los artefactos que viven dentro (journal, control root, logs) siguen
sin versionarse; sólo existe el directorio. Es el mismo criterio que
WI-98 aplicó a las rutas de `.pipeline.kts`, y por el mismo motivo: una
regla que no se puede cumplir fuera de esta máquina no es un contrato, es
una costumbre.

`scripts/ci.sh` (modo por defecto) hace las dos cosas por ti y delega en el
comando canónico. `bash scripts/ci.sh --quick` es un modo de iteración que
corre `pytest` a pelo: más rápido, y por eso **no certifica**.

### Criterios de éxito (todos deben cumplirse)

1. `Pipeline finished with SUCCESS` en la línea final del run.
2. **El run ejecutó pasos de verdad**: el journal contiene al menos un
   `StepStarted` y un `EchoOutputCaptured` cuyo contenido incluya la
   línea de resumen de pytest (`N passed in Xs`). Este criterio es el
   que separa una verificación real de un veredicto cacheado; el
   criterio 1 por sí solo lo satisfacen runs que no ejecutan nada.
3. Journal SQLite presente en `.pipelinek/db.sqlite` con eventos tipados
   (`CompilationStarted`, `RunStarted`, `StageStarted`, `StepStarted`,
   `EchoOutputCaptured` o equivalente, `StageFinished/success`,
   `RunFinished/success`).
4. Control root presente en `.pipelinek/control/{last-run, retry-control,
   wait-until-control, workspace/<stage-name>}`.
5. Cero `StepFailed` ni `RunFinished/failure` **en los eventos de la
   ejecución actual** (filtrar por `occurred_at` de este run: el
   `run_id` se reutiliza entre replays y arrastra `StepFailed`
   históricos).
6. SHA-256 del `.pipeline.kts` registrado en la sesión y comparable con
   `git log -- .pipeline.kts` para detectar drift no intencional.

**Desde WI-105 los criterios 1 a 5 los comprueba una herramienta**, y el 6
sigue siendo del agente a propósito:

```bash
mise exec -- uv run python scripts/check_pipeline_receipt.py                    # último run
mise exec -- uv run python scripts/check_pipeline_receipt.py --run-id 4f407df9  # uno concreto
```

Es la etapa `evidence` de `.pipeline.kts`, que antes hacía tres `test -d`
que **no podían fallar** porque sus operandos los crea el motor antes de
la etapa. El **criterio 6 no se automatiza**: es el SHA-256 «registrado en
la sesión», y una sesión es del agente, no del repo. Declararlo comprobado
sería la misma mentira que el script viene a arreglar.

Dos detalles que no son obvios, los dos MEDIDOS:

- **Sin `--rerun` los criterios 1 y 2 no distinguen nada.** Un
  veredicto cacheado y una verificación real dicen los dos
  `Pipeline finished with SUCCESS`; el criterio 2 es el que los separa.
- **La receta verifica el run ANTERIOR.** Cuando la etapa corre, el run en
  curso todavía no tiene `RunFinished`, así que «el `RunFinished` más
  reciente» es el run anterior. El huevo y la gallina es real, y lo
  resuelve el propio motor sin trucos.

Y una consecuencia de lo anterior que **no** es evidente, y que salió
medida en WI-109 con seis runs y se **resolvió en WI-110**:

> **La etapa `evidence` se verifica a sí misma.** Exige que el run medido
> termine en `success`; un run sólo termina en `success` si **todas** sus
> etapas pasaron; y `evidence` es una de esas etapas. Sin exculpación,
> un fallo cualquiera —incluido uno ya corregido— dejaba la cadena
> envenenada para siempre.

Medido: `8d6a9594` fue el último run con las 8 etapas en `success`, y los
cinco siguientes tuvieron las **siete etapas de código** en `success` y
ninguno se recuperó. Un fallo ya corregido no devuelve la cadena a
verde, porque el fallo dejó de estar en el código pero seguía en el
veredicto.

**Cómo se exculpa, y por qué es mínima** (WI-110):

- La exculpación vive en `scripts/check_pipeline_receipt.py::evaluar()`,
  **no** en la etapa. Por eso `.pipeline.kts` no cambia, su SHA-256 sigue
  siendo `7541ced5…`, y las certificaciones de WI-101 a WI-109 siguen
  valiendo: cada run se certifica con el verificador de su momento.
- Requiere **las tres** condiciones: un solo `StepFailed`, su **nombre**
  conocido, y que el nombre empiece por `evidence`. Con dos pasos
  rotos, sin nombre, o con cualquier otra etapa, se rechaza igual.
- El **nombre** es el cambio de fondo. Antes `step_failed` era un
  contador, y un contador no sabe quién falló: por eso no había base
  para exculpar. `InformeRun.paso_fallido` lo lleva desde el journal.
- **El veredicto del run nunca se exculpa.** Un run abortado sin un solo
  `StepFailed` se rechaza igual, y eso lo fija
  `test_un_run_abortado_sigue_sin_pasar`.

Lo que **no** arregla: un run con las siete etapas de código verdes y
`evidence` en rojo sigue terminando en `FAILURE` por construcción, porque
la etapa que lo evalúa es una de las ocho. Lo que cambia es que **el
siguiente run ya no hereda el fallo**: el primer run verde tras el
arreglo llega uno después, no en el mismo.

**Las tres consecuencias que dejó la medición de WI-109 y WI-110**, porque
son las que hacen perder una tarde a quien no las sepa:

- **El veredicto de un run no describe su propio código.** Hay que leer
  las ETAPAS. Cinco runs seguidos con las siete etapas verdes y
  `FAILURE`.
- **Para certificar hay que leer por `run_id` Y por `occurred_at`.** El
  `run_id` se reutiliza entre replays, y «el más reciente por `sequence`»
  puede ser un run de ayer: en WI-109 eso dio un `OK, 8/8 etapas` sobre
  un run del día anterior.
- **Si un run sale en `FAILURE`, hay que mirar si falló `evidence` antes
  que suspectar del código.** Desde WI-110 el caso es distinguible: el
  mensaje nombra el último paso que falló.

Guard: `tests/test_wi110_evidence_recoverable.py`, con **más** tests para
la mitad peligrosa —la que perdona de más— que para la que arregla: seis
etapas distintas que tienen que seguir sin pasar, dos pasos rotos que no
se exculpan, y un `StepFailed` sin nombre que se rechaza.

### Comando de validación rápida

```bash
test -f .pipeline.kts && \
  pipelinek validate .pipeline.kts && \
  echo "pipelinek CI local: configuración válida"
```

### Extensión del script

Cualquier stage nuevo debe:

* Declarar su propósito en el `echo` inicial del stage.
* Pasar por `repo` (ver abajo) en vez de escribir una ruta. **Nunca una
  ruta absoluta a un árbol de trabajo concreto** (WI-98).
* Producir efectos secundarios solo a través de los directorios
  `.pipelinek/` y `evidence/` (no contaminar el árbol del proyecto).
* Mantener `discover-repo` como primer stage para que un run nuevo
  siempre documente el estado del repositorio.

### La raíz se resuelve, no se escribe (WI-98)

`.pipeline.kts` abre con:

```kotlin
val repo = System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")
```

**Por qué no rutas absolutas.** Hasta WI-98 el script llevaba diez
apariciones de `/var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/...`.
Eso arreglaba el síntoma local —el motor no resuelve el cwd, así que
`ls pyproject.toml` corría contra el workspace del motor— y dejaba la
receta **inejecutable en cualquier otra máquina**. Una regla que no se
puede cumplir no es un contrato: es la razón por la que el runner remoto
llevaba su propia receta sin que nadie pareciera incumplir nada.

**Por qué esto sí funciona.** El motor v0.39.0 no define `$REPO_ROOT`, pero
**sí propaga el entorno a los `sh()`**: un `GITHUB_WORKSPACE` exportado llega
intacto al shell. Medido, no supuesto. Y `user.dir` es el repo cuando el
comando canónico se invoca desde su raíz, que es como se documenta.

Dos invariantes de `scripts/check_ci_recipe_parity.py` lo vigilan, y las
dos se pueden comprobar sin heurística:

* el script **resuelve** la raíz (`System.getenv` o `user.dir`);
* el script **no contiene** la raíz de este árbol de trabajo.

Comparar contra la raíz real y no contra un patrón de «parece absoluta»
importa: `/usr/bin/uv` es legítimo y no ata el script a ninguna máquina.

### Una sola receta, también en local (WI-99)

WI-98 lo dejó escrito: la receta canónica tiene que ser **portable**, para
que un runner remoto pueda ejecutarla. WI-99 midió que faltaba la mitad
anterior: que **nadie más la ejecute**.

La receta canónica no es «la receta de este runner», es **la** receta. Un
script local que corre `pytest` por su cuenta produce un veredicto con otro
instrumento, y ese veredicto es el que llega a quien audita. Lo que se
midió:

| quién mide | Stages | contratos exigibles | `cli/commands/runs.py` |
|---|---|---|---|
| `.pipeline.kts` (canónica) | 8/8 | 4/4 | 87,96 % |
| `scripts/ci.sh` (hasta WI-98) | 3 | **0** | 39 % |

Y `scripts/audit_bundle.sh`, que existe **para** dar evidencia reproducible
a una auditoría independiente, llamaba a ese segundo. Es decir: el
instrumento que existe para medir medía con el que no ve.

**La regla.** Un script de `scripts/` que ejecuta `pytest` tiene que estar
conectado a la receta canónica: o es un **fragmento** que ella invoca
(`scripts/coverage.sh`), o **delega** en ella (`scripts/ci.sh`).

Es disyuntiva a propósito. La versión restrictiva —«nadie ejecuta pytest
salvo `.pipeline.kts`»— hace del propio fichero de cobertura una
infracción, y su única salida es una lista de excepciones que el guard
mantiene: un guard que vigila la lista que él mismo mantiene no vigila
nada.

`scripts/check_ci_recipe_parity.py` lo vigila, y lo vigila sobre **órdenes
ejecutadas**, no sobre el texto del fichero:

* los fragmentos se **leen** de `.pipeline.kts`, no de una lista aparte;
* los scripts se **descubren** por extensión dentro de `scripts/`, así que
  un `verify.sh` nuevo entra en el contrato sin tocar el guard;
* se ignoran comentarios y se unen las continuaciones con `\`, porque la
  invocación real está partida en varias líneas.

Medido: seis mutaciones, seis en rojo. Una de ellas restaura el
`scripts/ci.sh` real de antes de WI-99, sacado de git, porque un
contrajemplo inventado prueba que el test está bien, no que el guard
muerda.

*Resuelto en WI-100:* `scripts/hooks/pre-push` ejecutaba la suite completa a
pelo y emitía veredicto con el instrumento ciego — el mismo defecto que este
capítulo describe para `scripts/ci.sh`. Ahora **delega** en `scripts/ci.sh`, y
sus tests ejecutan el hook de verdad contra un repo de prueba en vez de
comprobar que el fichero contiene una cadena.

### El bundle de auditoría tiene que ejecutar (WI-101)

Delego en la receta no basta si el paso que viene después no mide nada.

`scripts/audit_bundle.sh` —el instrumento que existe *para* dar evidencia
reproducible a una auditoría independiente— invocaba
`python -m tests.uat_audit` sin flags. Ese es el modo lectura: **no ejecuta
ningún UAT**, relee los 26 JSON de `tests/uat-evidence/` y los repite. El
`PASS=16` del bundle de WI-99 se escribió mirando ficheros del commit
`0ebbd58`, 111 commits por detrás.

Y lo que hace peor: el modo lectura hacía `return 0` **incondicional**. El
exit code estaba estructuralmente desacoplado del veredicto, así que la
guarda del bundle (`if [ "$UAT_RC" -ne 0 ]`) no podía dispararse nunca.
Medido con el comando exacto del bundle, antes del arreglo:

| evidencia en disco | salida | exit code |
|---|---|---|
| `UAT-01.json` inyectada en `FAIL` | `PASS=15 FAIL=1` | **0** |
| `tests/uat-evidence/` ausente | `PASS=0 FAIL=0` | **0** |

Un bundle con un FAIL a la vista y un bundle sin una sola evidencia eran
indistinguibles de uno sano. Un exit code fijo no es un guard: es un mensaje
con código de salida.

**Las tres reglas que lo cierran.**

1. **El exit code sale de `_verdict`**, compartido por los tres modos, para
   que no puedan divergir entre sí. Lista **blanca** (`PASS`, `BLOCKED`), no
   negra: el conjunto de cosas malas no tiene fin, y con lista negra un
   `status: "passed"` pasaba en silencio.
2. **`--verify` ejecuta, no persiste, y confronta.** Cada veredicto se
   compara con la evidencia persistida. Sin ese contraste la evidencia era la
   única fuente del veredicto, y no se contrastaba con nada: podía afirmar
   `PASS` para un UAT que hoy falla sin que nadie se entere.
3. **El resumen no se traga lo que no conoce.** Antes `PASS=15 FAIL=0` sobre
   16 filas leídas, porque el recuento solo miraba las tres etiquetas
   conocidas. Un total que no suma las filas no es un total.

Verificado después del arreglo, no antes: los 16 UAT se ejecutan y
**convergen** con la evidencia versionada. La evidencia era cierta; lo que
faltaba era comprobarlo. Un guard que declara algo que no mide produce el
mismo resultado que uno roto, y por eso solo se nota al mutarlo: 9/9 en
rojo (`.pipelinek/wi101_mutate.sh`).


### La receta puede perder un contrato y seguir dando verde (WI-102)

C3 lee las etapas del script, y está bien: leer del script es lo que evita un
guard que vigila una lista paralela. Pero comprobaba que la lista fuera
**legible**, y una lista de etapas vacía por legibilidad es tan válida como
una completa.

Medido en WI-102, con el comando canónico de verdad: se borró el bloque
entero de la etapa `coverage-floors` —la que impone los suelos que §6.3
declara exigibles— y el resultado fue

| quién debía enterarse | resultado |
|---|---|
| `scripts/check_ci_recipe_parity.py` | exit **0** — «OK: …» |
| `pytest tests/test_wi98_ci_recipe_parity.py` | **37 passed** |
| la receta, ejecutada de verdad | **`Pipeline finished with SUCCESS`** |

Cero menciones de `coverage-floors` en su salida, y cero de su `VEREDICTO`. Una
receta que ejecuta menos se ejecuta igual de bien, y el instrumento que
certifica los contratos no comprobaba que los contratos estuvieran. C4 exigía
que quien ejecuta `pytest` esté *conectado* a la receta; nadie exigía que la
receta *contenga* los contratos.

**C5. Todo `scripts/check_*.py` lo invoca la receta canónica.**

La forma es deliberadamente **sin lista**: el conjunto sale del repo, no de
una constante. Una lista de contratos obligatorios dentro del guard es la
misma trampa que `DIRECTORIOS_NO_RECETA` en WI-99 — obliga a mantener
enumerado lo que el guard debería comprobar solo. Así un checker nuevo entra
en el contrato el día que se escribe, y borrar una etapa se detecta porque
el checker que invocaba deja de estar invocado.

Cubre también el caso inverso, que hasta WI-102 era invisible: **escribir un
checker y no enchufarlo en la receta**. Es un guard que no guarda nada, con la
misma forma exacta que un guard real.

Lo que no cubre, y se declara en vez de disimularse: el descubrimiento es por
la convención `check_*.py`. Un contrato escrito con otro nombre queda fuera
del invariante, igual que un script sin extensión quedaba fuera de C3 antes
de WI-100.

Medido después del arreglo, con la misma mutación: guard exit **1** con el
nombre del checker huérfano, 3 tests en rojo, y la receta **ella misma**
`Pipeline finished with FAILURE`. Mutaciones 5/5 en rojo
(`.pipelinek/wi102_mutate.sh`), y la quinta vuelve a borrar la etapa de
verdad: un invariante que solo sabe fallar con informes sintéticos no ha
medido nada.

### Una cita tiene que decir a qué apunta (WI-104)

`tests/test_wi92_measured_claims.py` vigila las citas `fichero.py:N` del bloque
vivo de `CURRENT.md`. Hasta WI-104 comprobaba que `N <= total_lineas`: que la
línea **existe**. Eso es resolubilidad, no verdad, y por eso WI-102 pudo
escribir `scripts/check_ci_recipe_parity.py:352` y `:479` —dos líneas de prosa
dentro de un docstring— donde las reales eran `:421` y `:589`, y el guard dio
las cuatro por buenas.

**La cita lleva el símbolo al que apunta:**

```text
ruta/fichero.py:LINEA::simbolo
```

`LINEA::simbolo` no es decoración: es lo que hace la afirmación falsable. Con
sólo el número no hay manera de distinguir «he abierto el fichero» de «he
escrito un número que me sonaba», y por eso el error se cuela sin que nada lo
note. `tests/test_wi92_measured_claims.py::TestLaCitaDeclaraQueSimboloApunta`
comprueba que el símbolo se resuelva en el fichero que la cita nombra —no en
cualquiera del repo— y que `LINEA` caiga dentro de su definición.

Tres reglas que se siguen:

1. **La cita apunta a la definición que contiene la cosa**, no a una línea de
   cuerpo. Todas las citas existentes ya lo hacen.
2. **El ancla es obligatoria.** Opcional sería un chequeo que no se ejecuta:
   es el «conectar ≠ contener» de WI-102 aplicado a las citas.
3. **Las citas de bloques anteriores no se comprueban.** Son la foto de un
   código que ya no existe; corregirlas sería falsificar la historia.
4. **El bloque vivo tampoco narra historia con sintaxis de cita.** Al
   escribir WI-104 se cuenta el fallo Anterior —«escribí la línea 352 en vez
   de la 421»— usando el patrón `fichero.py:352`, y el guard lo leyó como una
   afirmación y lo rechazó. Es lo correcto: un bloque que cuenta un error
   usando el formato del error se contradice a sí mismo. La arqueología va al
   `CHANGELOG.md`; el puntero de hoy cita el código de hoy.

Cuando una cita se queda vieja porque alguien insertó una línea arriba, el
error **dice dónde está el símbolo ahora**. Un verificador que dice «falso» sin
decir «está aquí» deja al que corrige en un callejón sin salida (mutación M5).

### Un criterio declarado que nadie comprueba (WI-105)

`AGENTS.md` enumera **seis** criterios que un run «debe cumplir». Hasta WI-105
**ninguna herramienta comprobaba ninguno**: la etapa `evidence` de la receta
—el único sitio que tocaba `.pipelinek/`— imprimía `present` con tres `test -d`
cuyos operandos crea el motor **antes** de la etapa, así que los tres podían
pasar y ninguno podía fallar. Medido contra el journal real: 15 runs, 3 de ellos
`RunFinished/failure`, y la etapa dice lo mismo en los quince.

Tres reglas que se sacan de ahí:

1. **Un `SUCCESS` que no ejecutó nada no es una verificación.** Los dos dicen
   `Pipeline finished with SUCCESS`. Si una etapa comprueba que el motor terminó
   bien pero no que ejecutó pasos, está midiendo el motor, no el trabajo.
   **Comprobar pasos, no veredictos.**
2. **Lo que un guard no puede medir, se declara que no lo mide.** El criterio 6
   —el SHA-256 «registrado en la sesión»— es del agente, no del repo. Meterlo en
   el script habría sido la misma mentira que el script viene a arreglar.
3. **El huevo y la gallina no es excusa para no comprobar.** La receta no puede
   verificar su propio run, porque cuando la etapa corre el run en curso no
   tiene `RunFinished`. El motor lo resuelve solo: *el `RunFinished` más
   reciente es, durante un run, el run anterior*.

Y un detalle de instrumento que costó una medición entera: **el `payload` del
journal es una lista JSON con un dict dentro, no un objeto.** `json_extract(payload,
'$.outcome')` devuelve `NULL` sobre ese schema. Leerlo por la ruta de objeto da
`None` en los 15 `RunFinished` y convierte el run más sano del repo en
`failure`. Un instrumento que no abre el contenedor no mide lo que cree medir.

### Compatibilidad con otros runners

`pipelinek` es la fuente de verdad local. GitHub Actions, GitLab CI,
Jenkins o cualquier otro runner remoto **debe** invocar el mismo
`.pipeline.kts` desde el mismo checkout. Si un runner remoto produce
PASS y `pipelinek` local produce FAIL, prevalece `pipelinek` local hasta
que la divergencia se investigue y documente en este mismo archivo.

**Desde WI-98 esa regla es exigible, y lo es por stage.**
`scripts/check_ci_recipe_parity.py` (stage `ci-parity`) comprueba, mediante
**C1–C5**, que todo runner remoto invoque `.pipeline.kts` **en un paso que se
ejecuta** —no en un comentario que lo mencione—, que la receta canónica se
pueda ejecutar fuera de esta máquina, que quien ejecuta `pytest` esté
conectado a la receta (C4), y que la receta **contenga** todos los contratos
exigibles de `scripts/` (C5). C4 y C5 son las dos mitades de una misma regla:
conectar sin contener, y contener sin conectar, fallan igual.

Medido cuando se añadió la comprobación:

| receta local | `ci.yml` antes de WI-98 |
|---|---|---|
| stages ejecutados | **8** | **1** (`lint`) |
| contratos exigibles | los 4 | **0** |
| `cli/commands/runs.py` | 87,96 % | **39 %** |
| `cli/support.py` | 85,71 % | **69 %** (suelo: 70 %) |

El remoto podía dar **verde** un paquete que no cumplía el suelo que el
propio `AGENTS.md §6.3` declara, porque no ejecutaba el checker y su
medición no veía lo que el canónico ve. El número se midió con el mismo
instrumento en las dos recetas: comparar el remoto contra un 94 % de otra
base habría sido comparar dos cosas distintas y llamarles divergencia.

### Excepciones documentadas

Ninguna hasta la fecha. Toda excepción requiere entrada en
`SESSION-JOURNAL.md` y aprobación explícita del maintainer del proyecto.

---

## 12. Regla de release

Una única fuente de verdad para la SemVer publicada:

- **Fuente**: `src/skillgraph/__init__.py:__version__`.
- **Back-end**: `[tool.hatch.version] path` en `pyproject.toml`
  apunta a ese fichero. Hatch lo lee en cada build.
- **Etiqueta**: cada tag anotado `v<X>.<Y>.<Z>` debe corresponder
  a un commit cuyo `__version__` (sin sufijo `.devN`) sea
  `<X>.<Y>.<Z>`.
- **Trabajo**: commits posteriores a la etiqueta más reciente
  deben incrementar `.dev0`, `.dev1`, etc. (mismo SemVer base
  hasta la siguiente release).
- **Bumps entre releases**: si se cambia `X.Y.Z` base entre
  dos releases, **la nueva etiqueta debe existir antes** de que
  `__version__` la declare como base.
- **Prohibido** `git tag --force` o `git push --force` sobre
  cualquier etiqueta publicada. La provenance es histórica y no
  se reescribe.

### Derivar la versión

La versión de una release **no se decide a mano**: se deduce de los commits
que hay entre la etiqueta anterior y la nueva.

| Tipo de commit | Bump |
|---|---|
| `feat` | MINOR |
| `fix` | PATCH |
| `feat!` / `fix!` / footer `BREAKING CHANGE` | MAJOR |
| `refactor`, `test`, `docs`, `spec`, `chore`, `style`, `build`, `ci` | **sin bump** (no hay release) |

Escribir `feat!` o añadir el footer `BREAKING CHANGE` en el **cuerpo** cuenta
igual que el `!` en el asunto. Si la regla dice «sin bump», **no se emite
etiqueta**: el trabajo se acumula hasta que haya un `feat` o un `fix`.

Se calcula con `scripts/derive_semver.py`, que imprime para cada etiqueta el
bump real frente al que dicta la regla. Vive en `scripts/` y no en
`.pipelinek/`, porque es una regla del repo y no un paso de esta pipeline.

> Esta tabla estaba antes **solo** en la cabecera de `CHANGELOG.md`, que no
> es el dueño de la gobernanza de releases. Medido el 2026-10-02 (WI-96), con
> 47 etiquetas y 6 bloques de trabajo: la regla no la aplicaba ni la comprobaba
> nadie, y su sitio natural —esta sección, que se titula «Regla de release»—
> no la contenía.

#### El campo que dice por qué se movió la versión (WI-106)

`STATE.yaml` escribe `release.semver_bump`: la **causa** del bump, la
respuesta a «por qué la versión se movió». La tabla de arriba y
`scripts/derive_semver.py` son la respuesta a «qué habría dicho la regla».

Hasta WI-106 nadie comparaba las dos. Medido: con el campo puesto a `MAJOR`
cuando el release había sido `MINOR`, la suite de gobernanza de release daba
**18 passed, exit 0**, y los tres checkers de la receta y el bundle de
auditoría, también `exit 0`.

El **nivel** de la versión sí estaba verificado —
`test_el_conjunto_de_divergencias_no_cambia` vigila que la lista de
divergencias históricas no crezca. Lo que no exigía nadie es que el campo
dijera la verdad.

Regla: **`release.semver_bump` no se escribe, se contrasta.** Si no coincide
con lo que dice `derive_semver.py` para `release.tag`, el campo documenta una
causa que nadie verificó. Dos cosas que hacen que el contraste sirva:

1. **La expectativa sale de la herramienta, no de una constante.** Un guard que
   compara contra su propia copia de la regla no vigila nada: hoy la copia dice
   lo mismo y el día que la regla cambie dirá lo contrario. Por eso
   `test_el_bump_calculado_no_es_una_constante` exige que el cálculo acierte en
   **dos bumps distintos**, cosa que un literal no puede.
2. **El dominio y la existencia se comprueban sobre entradas, no sobre el valor
   de hoy.** Comprobar que `MINOR` es válido no es comprobar que el dominio
   existe. `release.semver_bump: RELLENO` y `release.tag: v9.9.9` tienen que ser
   rechazados.

### Salvedad 0.x: un breaking change no obliga a 1.0.0

El proyecto está en **0.x**, donde SemVer no garantiza estabilidad del API
público. Mientras la versión mayor siga siendo `0`, un `BREAKING CHANGE`
**no** obliga a saltar a `1.0.0`: la etiqueta sigue avanzando por MINOR o
PATCH según el resto de commits del tramo.

Se aplicó **tres veces**, y conviene ser exacto sobre cómo: **ninguna de las
tres usó el marcador de la convención**. No hay `!` en el asunto ni un footer
`BREAKING CHANGE:` — lo que hay es un **anuncio en prosa** dentro del cuerpo
del commit, y una decisión tomada a mano en el commit de release.

| Etiqueta | Qué cambió | Cómo se anunció |
|---|---|---|
| `v0.7.0` | eliminación de 20 shims de retro-compatibilidad y de rutas de import antiguas | viñeta «Esto es BREAKING CHANGE para importadores externos que usaban…» |
| `v0.15.0` | R1+R2 de la frontera de persistencia | «MINOR por 1 BREAKING + 3 feat + 1 fix», en el commit de release |
| `v0.16.2` | — | «BREAKING CHANGE, luego MINOR y MAJOR quedan fuera y corresponde PATCH» |

Que ninguna llevara el marcador es **justo el problema**, no un detalle: sin
`!` ni footer, ninguna herramienta podía verlas. `scripts/derive_semver.py`
las cuenta hoy como breaking en **cero**, y aun así fueron cambios
rompedores. La decisión fue correcta y está documentada; lo que faltó fue el
marcador que la habría hecho citable por una máquina.

Se nombran para que el precedente sea **citable**. Sin nombre, cada
breaking change obliga a volver a medirlo desde cero, y el salto a `1.0.0` es
una decisión de una sola oportunidad: tomarla por sorpresa es peor que
tomarla por criterio.

**Marcar es lo barato**: mientras se este en 0.x, un `BREAKING CHANGE`
marcado no obliga a nada, porque la cláusula de arriba lo exonera. Marcar
cuesta un carácter y compra que la decisión quede visible.

**Salir de 0.x es una decisión explícita**, no un efecto secundario de tener
ya muchas versiones. Cuando se decida, se escribe aquí antes que en el
mensaje de un commit.

### Divergencias medidas que NO se corrigen

`tests/test_wi96_semver_rule.py` deriva el bump de las 47 etiquetas y
compara. Trece no coinciden con la regla, y **ninguna se arregla**: son
etiquetas publicadas y su número es provenance. Se registran como hechos
medidos para que nadie las vuelva a descubrir ni las tome por un olvido.

| Tipo | Etiquetas |
|---|---|
| la regla pide MINOR y se publicó PATCH | `v0.3.0`, `v0.7.1`, `v0.7.2`, `v0.7.3`, `v0.14.1`, `v0.14.7` |
| la regla no pide release y se etiquetó | `v0.8.1`, `v0.14.2`–`v0.14.6`, `v0.14.8`, `v0.16.5`, `v0.16.8` |

Todas son anteriores a `v0.16.3`. Desde `v0.16.3` hasta `v0.16.20` el bump
**se deduce de la regla sin excepción de tipo**, y eso es lo que el guard
exige.

### Release gate

El test `tests/test_release_governance.py` es el **admission
gate de release** y forma parte de la pipeline local canónica
(`pipelinek run`). Tiene tres ramas válidas:

1. HEAD en una etiqueta `v<X>.<Y>.<Z>` y
   `__version__ = <X>.<Y>.<Z>` (release limpia).
2. HEAD posterior a una etiqueta reachable y `__version__` con
   sufijo `.devN` (trabajo entre releases; base puede ser la
   misma o superior).
3. Sin etiqueta reachable y `__version__` con sufijo `.devN`
   (trabajo pre-release inicial).

Y rechaza dos derivas reales:

- `__version__ = X.Y.Z` puro con HEAD no etiquetado.
- `__version__` con sufijo `.devN` apuntando a una base que
  contradice una etiqueta anotada en el mismo commit.

Si el test falla, **la release queda bloqueada** hasta que
`__version__` y la etiqueta vuelvan a coincidir.

### La cadena termina en un artefacto, y el artefacto se comprueba (WI-97)

El gate anterior cierra la cadena `git → __version__`. Faltaba el último
eslabón, que es el que de verdad produce lo que se distribuye:

```
git ──▶ __version__ ──▶ pyproject (hatch) ──▶ wheel / sdist
 ▲         ▲                ▲                     ▲
derive_semver.py      el valor lo lee        ESTE NO SE COMPROBABA
                       hatchling de aqui       NUNCA, HASTA WI-97
```

Hasta WI-97 ese último tramo no lo ejecutaba nadie: cero tests
referenciaban `hatchling`, `uv build` o `entry_points`, y ningún stage de
`.pipeline.kts` construía el paquete. Toda la machinery de esta sección
medía un número sobre un artefacto que nadie había visto nacer.

Ahora lo verifica `scripts/check_package_build.py`, stage propio
`package-build`:

| Invariante | Qué impide |
|---|---|
| `sg_build_version_drift` | que el número del artefacto no sea el del código |
| `sg_build_target_no_resoluble` | que un `[project.scripts]` apunte a algo que no existe |
| `sg_build_modulo_faltante` | que el wheel deje de recoger un módulo del paquete |
| `sg_build_py_typed_ausente` | que el paquete declare `py.typed` y no lo lleve |
| `sg_build_sdist_no_versionado` | que el artefacto herede del árbol de trabajo y no del commit |
| `sg_build_sdist_falta` / `..._sin_declarar` | que el `only-include` y el artefacto dejen de corresponderse |

El más importante es `sg_build_sdist_no_versionado`: un artefacto que
hereda de ficheros sin versionar hace que dos árboles con el mismo commit
produzcan dos sdists distintos, y `git` deja de poder decir qué se publicó.

`sg_build_target_no_resoluble` existe por una razón que conviene no
olvidar: comparar «lo declarado» con «lo publicado» es tautología a medias,
porque lo publicado **se deriva** de lo declarado. Un target equivocado sale
idéntico en los dos lados. Solo importar el módulo distingue «declaré algo
que existe» de «declaré algo que no existe y el backend lo copió sin
mirarlo».

### Erratum histórico: `v0.14.0`

La etiqueta `v0.14.0` (HEAD `d50f666`) **NO se reescribe**:
permanece como evidencia histórica de una release publicada con
package metadata defectuosa (`__version__ = "0.7.0.dev0"`). La
release correctiva es `v0.14.1`. SemVer no contempla reescritura
retroactiva de versiones publicadas, y la provenance histórica
debe preservarse como está.


### La lista que se salva cambiando de eje no deja de ser una lista (WI-107)

Novena vía de la serie «qué declara el repo que nada comprueba», y la
tercera vez que la **misma idea** se salva de sí misma cambiando de forma.

`AGENTS.md §6.3` declara suelos de cobertura por módulo. La historia del
guard que los comprueba son tres listas, cada una creyendo que era la
última:

| | La lista | Lo que dejaba fuera |
|---|---|---|
| WI-93 | 21 módulos escritos a mano | todo menos `runtime/` |
| WI-94 | 8 prefijos de paquete escritos a mano | un paquete **nuevo** |
| WI-107 | ninguna | — |

El docstring de WI-94 afirmaba, con toda la razón que da un docstring
recién escrito:

> «Una sola fuente, sin lista que mantener, y por eso no se puede olvidar
> uno.»

Es falso. El suelo pasó a declararse por paquete, y el **conjunto de
paquetes** seguía siendo un diccionario escrito a mano. Medido el
2026-10-03, con un paquete nuevo cuyo módulo nadie importa y que ya está
versionado en git:

```
pytest                    2709 passed in 234.75s
check_coverage_floors.py  exit 0, «todos los suelos se cumplen»
cobertura de oracular.py  0 %  (18 sentencias, 10 ramas, 0 cubiertas)
suelo global              94.85 %   (fail_under = 80)
```

El paquete se midió **dos veces** y la segunda es la que se cita, porque
la primera daba un resultado que no era el que se iba a escribir. Con el
paquete sin versionar, la suite daba `1 failed`:
`sg_build_sdist_no_versionado` (WI-97) lo delata, porque un sdist no
puede llevar lo que git no versiona. Ese guard lo ve, pero por **otra**
propiedad y con **otro** mensaje, y un paquete nuevo se versiona: no es el
contrato de §6.3, es otra puerta que se abre por casualidad. La versión
sin versionar habria producido una afirmación más fuerte y falsa —«el repo
entero es ciego ante un paquete sin suelo»— y esa es la que no se escribe.

**La regla que sale de aquí.** Una lista se puede eliminar, o se puede
declarar y vigilar. Lo que no se puede es creer que al cambiarle el eje
deja de ser una lista:

* Si el dato **se deduce del árbol**, no se escribe. `SUELO_POR_DEFECTO =
  90` alcanza a todo módulo que cuelgue de un subdirectorio de
  `src/skillgraph/`, paquete nuevo incluido. Lo único escrito son las
  **desviaciones**, que son datos: `cli/` al 70 % y `platform/paths.py`
  al 60 %. De ocho entradas quedan dos, y las dos son el contrato diciendo
  algo que el código no puede deducir.
* Si el dato **no se deduce** (un suelo distinto, una excepción), se
  declara, y declararlo incluye vigilar que lo declarado exista. Por eso la
  aserción de WI-94 cambió de objeto en vez de desaparecer: vigilaba que
  los ocho paquetes declarados tuvieran módulos, y con suelo por defecto
  eso es tautológico —los paquetes se derivan del árbol—, mientras que lo
  que sí puede quedarse viejo es la desviación.

Y el guard del documento: `§6.3` **no enumera módulos**. La enumeración
anterior («errors, bricks, parser, registry, storage, runtime, handoff,
agent, workflow, runcontroller») era una fuente de verdad más, y ya estaba
vieja: `runtime` no es un módulo sino un paquete, `runtime.py` no existe, y
nueve de los diez vivían fuera de `core/`.

**La mutación que no cazaba, y por qué el harness cambió.** Primera pasada
del harness: 6/8, con `m2` sobrevivida. Segunda pasada del **mismo**
código: 7/8, con `m2` cazada. Una mutación que a veces sobrevive no es un
guard que no muerde: es un experimento que no sabe qué midió. Con
`PYTHONDONTWRITEBYTECODE=1` y una **sonda por mutación** —una expresión que
tiene que cambiar de valor con el código ya mutado— las tres salidas
quedan separadas y con nombre: *cazada*, *inválida* (la sonda no cambió, la
mutación no degradaba nada) y *el entorno no vio la mutación*. 8/8 en tres
pasadas consecutivas.


### La regla que se escribe con tu letra y no se comprueba con ninguna (WI-108)

Décima vía de la serie «qué declara el repo que nada comprueba», y la más
pequeña en código: una sola prohibition, de siete palabras, con el «por
qué» escrito al lado.

> **NO usar `pytest.skip` para esconder fallos: o arreglas el test o lo
> borras.**
> **Un `skip` por falta de artefacto es el mismo defecto, con otra forma.**

La segunda la escribió WI-103 después de medir un gate que se saltaba por
falta de informe. Y de todo el repo:

```
instrumentos que miran skips (scripts/, src/): 0
etapas de la receta que los miran:               0
```

Medido antes de escribir una línea, con un run sintético cuyo único cambio
es la línea de resumen del journal:

```
run sin skips:   0 problemas []
run con 3 skips: 0 problemas []
veredicto: «OK: el run cumple los criterios que declara AGENTS.md»
```

**El detalle que lo hace grave** no es el regex. Es que el **criterio 2** de
esta misma sección —el que existe para distinguir un run real de un
veredicto cacheado— acepta un resumen con skips: `2715 passed, 3 skipped`
casa con su regex igual que `2718 passed`. No es un bug del regex: es que
la pregunta por los skips **no se había hecho**, así que nadie la
respondió nunca. Una regla y el criterio que la vigila no se contradicen
cuando nunca se cruzan.

**Y la regla la incumplía el autor de la regla.** De los cinco skips que
había, dos son de plataforma (`fcntl` no existe en Windows: no esconden
un fallo, describen una diferencia real entre máquinas) y **tres son de
artefacto** —«sin journal: clon nuevo»—, que es literalmente lo que la
segunda línea prohíbe. Los escribí yo en WI-105, en el guard que construí
precisamente para no esconder nada.

Los tres se fueron, y **no se sustituyeron por nada**, que es la decisión
que hay que defender. Los tres medían el **entorno** —qué pasó en esta
máquina— y no el **entregable** —qué garantiza el guard—. El journal no
está versionado, así que en un clon nuevo se saltaban en silencio y la
suite pasaba en verde con skips. Sus tres propiedades ya tienen sitio: dos
en la etapa `evidence` en cada run, una sintética desde WI-105. La tabla
de dónde vive cada una está en el propio fichero donde estaban.

**El guard que mira el código mira el AST, no el texto.** La primera
versión buscaba `pytest.skip(` con un regex y se puso roja **por su propia
documentación**: un docstring que cita el patrón es indistinguible de una
llamada. Es la regla de la serie —«un guard que busca una cadena busca la
cadena, no la propiedad»— y aparece por segunda vez en dos semanas, en el
mismo repositorio y por el mismo motivo. La propiedad es «este código
*llama* a `pytest.skip`», y eso lo responde el árbol sintáctico.

**Límite declarado:** `from pytest import skip` seguido de `skip(...)` no
lo ve el AST, porque el nombre ya no es `pytest.skip`. Es un alias, no la
forma que pytest documenta, y queda escrito en vez de descubrirse.

**Mutaciones 9/9 en tres pasadas**, con sonda por mutación: el patrón que
WI-107 dejó montado, aplicado desde el principio. Una de las nueve
—cambiar el código del error a uno que nadie espera— no la cazó la
primera sonda porque la sonda medía la forma de retorno de un árbol sin
llamadas, donde esa forma nunca se ejerce: la mutación era inválida, y el
harness lo dijo en vez de acusar al guard.
