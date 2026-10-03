# B4 — Diseño: la mitad observada, y por qué no vive en `Brick`

Ciclo `p-b7740b96d79ec013/b4` · fase `design`. Encadena con la exploración
(`sddk-b4-2026-10-03.md`) y la especificación (`sddk-b4-spec-2026-10-03.md`).

---

## 1. Una decisión que parece de estilo y es de contrato

La forma obvia de «darle status a un recurso» es añadirle el campo a `Brick`:

```python
Brick(identity=..., api_version=..., kind=..., spec={...}, status={...})
```

**Eso destruye la separación que B4 pide, y por eso no se hace.**

`Brick` es lo **declarado**: lo que alguien escribe y pide que exista. Si
`Brick` lleva `status`, entonces un pack puede **declarar** el estado de su
propio recurso, y la mitad observada deja de estar observada. Pasa a ser una
declaración más, escrita por la misma parte que pide.

Eso es exactamente la distinción que B6 quiere poder hacer entre
`observed`, `derived`, `agent-inferred` y `human-asserted`. Si `status` cabe
en el mismo tipo que `spec`, el sistema **no puede** decir cuál es cuál, y
no por falta de un campo sino porque la forma del dato lo borra antes de
llegar a la base.

De ahí dos tipos, y la separación es **de tipo, no de convención**:

```
Brick            lo declarado    spec, markdown_body
ResourceStatus   lo observado    phase, conditions, observed_generation
```

## 2. Dónde vive cada cosa, y por qué no en `platform/`

`ResourceStatus` y `Condition` van en `resources/`, junto a `Brick` y
`ResourceIdentity`. Son **tipos de dominio**, no DTOs ni puertos:

- `platform/ports/dto.py` expone `status_json` como **texto crudo**, y eso es
  deliberado: *«preservando la frontera de persistencia»*. Convertirlo en
  tipo en la capa de persistencia sería deshacer una decisión ya tomada y
  medida.
- `platform/` es infraestructura. Un `phase` y sus condiciones son del
  dominio, y un Domain Pack los va a declarar sin conocer `platform/`.

## 3. La serialización estable, y por qué no es opcional

El status se persiste como JSON en `status_json`, y se serializa con
`sort_keys=True`.

Es el mismo motivo por el que el hash del handoff ordena capacidades y
budget (`AGENTS.md 8`): **dos statuses con las mismas condiciones tienen que
darse el mismo texto**. Sin eso no se pueden comparar dos status, ni
detectar que uno no ha cambiado, ni deduplicar escrituras. Un JSON con
claves en el orden del `dict` de Python convierte una comparación en una
casualidad.

## 4. La invariante, y por qué es la parte que se rompe sola

> Un cambio de `status` no cambia `generation`. Un cambio de `spec` sí.

Kubernetes lo define así y no es arbitrario: `generation` identifica **la
versión del spec**; `resourceVersion` es el reloj de **cualquier** escritura.
La asimetría es lo que permite responder *«el status que ves es de la
generación 3 y el spec ya va por la 4»*.

`ResourceStatus` lleva por eso `observed_generation`: **no** el número que
el status dice de sí mismo, sino el que el que escribe **lee de la fila** en
el momento de escribir. Si el que escribe lo declarara, el campo mentiría en
cuanto el spec cambiara por debajo.

**Y esta invariante se puede romper sin que nada falle.** Basta con que un
`UPDATE` de status suba también `generation`: el sistema sigue
funcionando, los tests siguen verdes si no hay uno que lo mire, y el daño es
que el status deja de poder situarse en el spec que observó. Por eso el
guard mira **antes y después**, no el valor final.

## 5. `conditions`, y por qué un `type` no puede repetirse

`Condition.status` es `Literal["True", "False", "Unknown"]`, no `bool`.

`Unknown` no es `False`. Un operador mirando un recurso necesita distinguir
tres cosas: *esto está bien*, *esto está mal*, y *esto no se ha intentado
todavía*. Con `bool`, la tercera se representa como `False` y se lee como un
fallo, y un recurso recién creado parece roto.

Y **un `type` no puede repetirse** dentro de un status. `Ready=True` y
`Ready=False` a la vez no significan «dos estados»: significan que el que
escribe el status no sabe cuál está observing. Se valida al construir, con
`ValidationError`, y no al persistir: un status mal formado es un error de
quien lo construye, y se le dice a quien lo construye.

## 6. Lo que este diseño NO incluye, y por qué

- **No cambia `GraphExpansion`.** El roadmap dice *«no se reemplaza: se
  generaliza»*. Su mitad propuesta —`propose`, `Authorization`,
  `InvalidProposal`, `ExpansionResult`— está escrita y funciona. Lo que
  aporta este bloque es el otro extremo del bucle: algo **observable** de
  lo que la propuesta puede derivar.
- **No implementa el bucle completo** `observe → apply`. Lo que se entrega es
  la mitad que faltaba y que está medida; cerrar el bucle es el siguiente
  vertical y el gate de diff es B5.
- **No cambia `Handoff.capabilities`** ni su hash firmado. Ruptura de datos,
  B8.
- **No toca `generation` al escribir spec**, porque **no existe** un camino
  de escritura de `spec`: `upsert_resource` con el mismo `spec` es
  idempotente y con `spec` distinto lanza `IdentityConflictError`. O sea:
  el `INSERT` con `IdentityConflictError` **es** el guard de que el spec no
  cambia bajo un uid, y el incremento de `generation` pertenece al día en que exista
  un `patch` de spec. Se dice aquí para que no se lea como un olvido: es
  que la otra mitad del par todavía no tiene por dónde empezar.

## 7. La medición que abre el bloque, y su contra

`scripts/measure_b4_observed_state.py` justifica el bloque. Después del
arreglo **tiene que dejar de dar `INALCANZABLE`**, o la evidencia que
justifica el trabajo estaría caducada mientras el trabajo sigue en el árbol.

Eso es un contrasalto con una forma nueva: no es «el guard no mide nada», es
**«el guard midió bien y por eso ahora dice que el hueco está cerrado»**.
Un guard que solo sabe decir «el hueco sigue ahí» no distingue «no he
arreglado nada» de «lo he arreglado», y ese es el mismo error con la
espejo puesta: el primer gate de B3 medía una propiedad que un singleton
cumplía mejor que un valor.
