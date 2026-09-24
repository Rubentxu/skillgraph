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
RunState = Literal["CREATED", "ACTIVE", "WAITING",
                   "COMPLETED", "FAILED", "CANCELLED"]
EventKind = Literal["RunCreated", "NodeScheduled", ...]   # runtime.py
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
def _parse_node(data: Any) -> WorkflowNode: ...   # I/O: Any permitido
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

### 6.3 Cobertura mínima

- Módulos del core (errors, bricks, parser, registry, storage,
  runtime, handoff, agent, workflow, runcontroller): ≥ 90%.
- CLI: ≥ 70% (lo que falta son ramas de error que ya cubre
  integración).
- `paths.py`: ≥ 60% (la rama de Windows no se ejecuta en CI).

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
10. [ ] El commit message describe el "por qué", no el "qué".

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
if hash_a == hash_b: ...

# MAL: el resultado depende de estado oculto (orden de lectura, reloj)
if Path(file).stat().st_mtime > some_timestamp: ...
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
    case "ok": ...
    case "no": ...
    case _: raise OutcomeInvalidError(outcome)
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
      def is_ok(self) -> bool: return self.error is None
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
class SkillGraphError(Exception): ...           # raiz
class ValidationError(SkillGraphError): ...     # subtipo
class ParseError(SkillGraphError): ...
class UnknownKindError(ValidationError): ...    # sub-subtipo
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
new_builder = old_builder.starts_at(name)   # copy-on-write manual
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

`pipelinek` v0.39.0 — instalable desde `pipelinek-0.39.0.zip` (build local:
`v2/pipeline-application/build/install/pipelinek/bin/pipelinek`). Comando
canónico desde la raíz del proyecto:

```bash
pipelinek run --db .pipelinek/db.sqlite \
              --control-root .pipelinek/control \
              .pipeline.kts
```

### Criterios de éxito (todos deben cumplirse)

1. `Pipeline finished with SUCCESS` en la línea final del run.
2. Journal SQLite presente en `.pipelinek/db.sqlite` con eventos tipados
   (`CompilationStarted`, `RunStarted`, `StageStarted`, `StepStarted`,
   `EchoOutputCaptured` o equivalente, `StageFinished/success`,
   `RunFinished/success`).
3. Control root presente en `.pipelinek/control/{last-run, retry-control,
   wait-until-control, workspace/<stage-name>}`.
4. Cero `StepFailed` ni `RunFinished/failure` en el journal del último run.
5. SHA-256 del `.pipeline.kts` registrado en la sesión y comparable con
   `git log -- .pipeline.kts` para detectar drift no intencional.

### Comando de validación rápida

```bash
test -f .pipeline.kts && \
  pipelinek validate .pipeline.kts && \
  echo "pipelinek CI local: configuración válida"
```

### Extensión del script

Cualquier stage nuevo debe:

* Declarar su propósito en el `echo` inicial del stage.
* Usar **rutas absolutas** dentro de los `sh(...)` (el motor v0.39.0 no
  resuelve el cwd del script).
* Producir efectos secundarios solo a través de los directorios
  `.pipelinek/` y `evidence/` (no contaminar el árbol del proyecto).
* Mantener `discover-repo` como primer stage para que un run nuevo
  siempre documente el estado del repositorio.

### Compatibilidad con otros runners

`pipelinek` es la fuente de verdad local. GitHub Actions, GitLab CI,
Jenkins o cualquier otro runner remoto **debe** invocar el mismo
`.pipeline.kts` desde el mismo checkout. Si un runner remoto produce
PASS y `pipelinek` local produce FAIL, prevalece `pipelinek` local hasta
que la divergencia se investigue y documente en este mismo archivo.

### Excepciones documentadas

Ninguna hasta la fecha. Toda excepción requiere entrada en
`SESSION-JOURNAL.md` y aprobación explícita del maintainer del proyecto.

---
