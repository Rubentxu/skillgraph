# B34 — Superficie de consulta

> Medición hecha **antes** de escribir una línea, sobre el árbol real.
> Script: `/tmp/b34_preflight.py`.

## Las seis consultas: cinco ya existían

| pregunta | ¿existe la consulta? |
|---|---|
| what | SI — `list_claims_for_subject` |
| changed | SI — `claims_at_revision` (B29), `claims_desde_commit` (B32) |
| conflicts | SI — `conflicts_for` (B27) + `resolver` (B28) |
| evidence | SI — `get_evidences_for_claim` |
| impact | SI en `Storage`, **NO en el Protocol** — `list_claims_by_object_entity` (B25) |
| why | NO — pero es composición de tres lecturas que ya existen |

Y además:

```
sg.knowledge.query   CONSULTAS = {"claims", "resource"}   -> de las seis, NINGUNA
MCP                  0 ficheros, 0 menciones en src/
CLI `knowledge`      stale, invalidate, refresh, compile, trace, resolve
```

**La lectura que define el bloque:** cinco de las seis consultas ya
existían y la sexta era una composición de lecturas. **B34 no es un bloque
de consultas: es un bloque de superficie.** Lo que no existía era un modelo
único que las nombrara.

## La consulta inalcanzable

`list_claims_by_object_entity` la implementó B25 y la puso en `Storage`,
pero **no la declaró en el `Protocol` `KnowledgeRepository`** — que es el
que consume la capability de B30. Medido: 0 en el puerto, 1 en
`knowledge_claims.py`.

O sea: la consulta existía y era **inalcanzable desde la capa que la
necesitaba**, sin romper la inversión de dependencias de `AGENTS.md` 4.3.

**Y el nombre del parámetro es `object_entity_id`, no `entity_id`.**
Declararlo de otra forma habría creado un Protocol que `Storage` cumple
«a ojo» y que nadie puede comprobar: `isinstance` por `Protocol` no mira
las firmas, luego el error habría salido en runtime, en la primera llamada,
con un `TypeError` que no señala el puerto.

### Una profecía de B25 que resultó equivocada

El docstring de `list_claims_by_object_entity` dice que es «la primera mitad
de `changed` en B34». **No lo es**: es la **arista inversa**, y es `impact`.
`changed` es temporal —una REVISIÓN o un COMMIT— y no tiene nada que ver con
la dirección de la arista. Confundir las dos cosas es el mismo error que B29
cometió con los dos relojes y que B32 cobró caro. Queda escrito en el puerto,
junto al método.

## El gate del roadmap, y por qué aquí sí sirve

El gate dice: «las mismas query models alimentan CLI y MCP/agent handoff;
ninguna superficie reconstruye autoridad o retrieval por su cuenta».

Es bueno, a diferencia del de B33. Pero **MCP no existe** — 0 ficheros, 0
menciones—, luego la mitad «MCP/agent handoff» se cumple por el lado que sí
existe: la **capability**, que es el transporte real hacia un agente. Se
declara en vez de fingir que hay un servidor MCP.

## Lo que entra

`src/skillgraph/knowledge/superficie.py`: `PREGUNTA` (`Literal` de seis),
`CONSULTAS` derivado, `Consulta`, `Procedencia`, `Respuesta` y
`SuperficieConocimiento` con **un** método, `responder`.

La superficie se cablea en las dos superficies que existen:

- la CLI, seis subcomandos generados por un bucle sobre un catálogo
  declarado UNA vez (`_PREGUNTAS_SUPERFICIE` en `parser.py`),
- `sg.knowledge.query`, que pasa de 2 consultas a **8** y **no implementa
  ninguna** de las seis: construye la `Consulta` y pregunta.

## Los dos defectos que solo se ven EJECUTANDO

Los dos salieron al correr la CLI de verdad, no al leer el código.

**1. `impact` imprimía `imports_module = ''`.** El render usaba
`object_literal`, y en un claim cuyo objeto es una ENTIDAD ese campo vale
`None`. La primera corrección buscó `object_entity` —que es lo que lleva el
ADT `Claim`— y siguió imprimiendo `''`: lo que devuelve el puerto es
`StoredClaim`, y ese campo se llama `object_entity_id` con el criterio de XOR
del repo (`""` = literal, un id = entidad). Y el código **no decía nada**
porque `getattr` con default devuelve `None` en vez de fallar.

**2. `conflicts` sin `--intent` no decía nada.** Devolvía el `conflicto` pero
no las afirmaciones, y el render solo imprimía `claims` y la resolución: una
línea de cabecera y nada debajo. Eso no es «no se contradice» — es
«contradicte esto» sin decir qué.

## Una anotación que era MENTIRA con tipos

`Respuesta.claims` quedó anotada `tuple[Claim, ...]`. Lo que llega del puerto
es `StoredClaim`, que tiene `object_entity_id: str` y **no** tiene
`object_entity`. El puerto declara `Any` —a propósito, porque no debe
conocer el ADT de arriba—, luego el type-checker no lo cazaba: el error
habría salido en runtime, en la primera línea que leyera un campo. Ahora es
`tuple[Any, ...]` con el motivo escrito.

## Las sondas: 8/8, y dos estuvieran en verde

`scripts/mutate_b34_superficie.py`, con baseline verificado antes.

| sonda | qué rompe |
|---|---|
| M1 | la CLI vuelve a hablar con el repositorio |
| M2 | la capability toma la autoridad por su cuenta |
| M3 | `impact` deja de ser la arista inversa |
| M4 | `what` pasa a resolver |
| M5 | `conflicts` resuelve sin `--intent` |
| M6 | `Procedencia` crece con un campo de causalidad |
| M7 | `--commit` se acepta en cualquier pregunta |
| M8 | el render deja de pintar la entidad |

### El guard de B34 daba VERDE con el retrieval movido

**El hallazgo del bloque, y el más importante.** La primera versión de
`test_la_cli_no_llama_al_retrieval` medía `LOS_SEIS` —los seis handlers
`cmd_knowledge_*`, que son **una línea cada uno**: un
`return _responder_y_salir(args, "what")`.

MEDIDO: sustituyendo la superficie por una llamada directa al repositorio
**dentro de `_responder_y_salir`**, el guard daba **VERDE**.

Es el error del guard de B15 y del de WI-92, por tercera vez en este repo:
**un guard que mide la ENVOLTURA y no el CAMINO sigue en verde mientras el
camino esté roto.** Seis funciones que solo delegan no son seis funciones
auditables; el retrieval ocurre más abajo. El guard ahora mide los **tres
helpers** además de los seis handlers, y la sonda M1 cae.

### Y el alias

M2 estuvo mal diseñada dos veces y dio INOCUA ambas: hardcodar una pregunta
no cambia el número de métodos `_responde_*`, así que no había forma de que
cayera. La tercera versión hace que la capability **tome la autoridad por su
cuenta**, y lo hace con `from ... import resolver as _r` a propósito.

MEDIDO: con el guard como estaba —que solo miraba `ast.Attribute` y luego
`ast.Name`— esa sonda **pasaba**, porque en el árbol el nombre es `_r` y no
`resolver`. Es el mismo agujero que WI-108 declara para
`from pytest import skip`.

Aquí **sí se pudo cerrar**, y es lo único que este bloque hace mejor que sus
predecesores: el guard mira también las **importaciones**, así que el alias
deja de servir. Si el módulo importa `resolver`, está tomando la autoridad
por su cuenta diga luego cómo la llame.

## La deuda que este bloque deja CON NOMBRE

`sg knowledge resolve` (B28) y `sg knowledge conflicts --at-revision <intent>`
(B34) son **la misma pregunta**. Los dos existen.

Se declara en vez de esconderse porque unificar tiene un coste medido:
`cmd_knowledge_resolve` resuelve **TODOS** los conflictos del sujeto, uno por
uno, con su propio render y sus tests de B28. Unificarlos es un cambio de
contrato de la CLI que merece su bloque, no un arrastre dentro de este.

`TestElSolapeConResolveDeB28` ata que la situación siga siendo la declarada:
el día que se unifiquen, el test se pone rojo y obliga a reescribir el motivo
—que es lo que se quiere: que la deuda no se vuelva invisible porque nadie
volvió a mirar.

## Cobertura

`superficie.py` y el bloque de CLI de `knowledge.py` entran nuevos. Hay que
medirlos, no suponerlos: el suelo es el del paquete —90 %— y el de `cli/` es
70 %.

---

# LO QUE SALIÓ AL CERTIFICAR

Y no es un ajuste de cifras: son **dos cosas que el bloque affirmaba y que
no eran verdad todavía**.

## 1. La superficie de la CLI se había movido y el snapshot no lo sabía

Los dos guards de B10 se pusieron rojos, que es exactamente su trabajo:

```
[cli_subcomando_movido]  `sg knowledge` expone 12 subcomandos y el snapshot declara 6
[cli_runner_all_movido]  runner.__all__ cambio: 6 símbolos (45 reales frente a 39)
```

`sg knowledge` **6 → 12** y `runner.__all__` **39 → 45**. Se regenera desde el
árbol con `check_public_surfaces.py --actualizar`, **como B28**, y no a mano:
ADR-0018 declara esa superficie estable, y un snapshot escrito a mano es
justo la declaración que puede mentir.

## 2. `knowledge_query.py` estaba en 86,21 % — y las líneas sin cubrir eran la entrega de B34

Esto es lo que importa, y no aparece mirando los tests: aparece **midiendo
el suelo del módulo**.

```
src/skillgraph/knowledge/knowledge_query.py   86,21 %   suelo 90 %   BAJO
```

Las líneas sin cubrir eran **162-163 y 184**, y son literalmente esto:

```python
respuesta = self._superficie.responder(self._consulta_b34(request, consulta))
return CapabilityResult(...)
...
return Consulta(pregunta=pregunta(consulta), ...)
```

**La delegación.** El entregable de B34 escrito en el roadmap es «las mismas
query models alimentan CLI y **agent handoff**». Las 55 pruebas atacaban
`responder` directamente y la CLI, y **`invoke` no se llamaba nunca con una de
las seis preguntas**. La mitad del agent handoff del gate era **prosa**.

### Por qué los guards no lo vieron

Porque miden otra cosa, y lo hacen bien:

`TestUnaSolaSuperficieParaTodas` mide que la capability **no reconstruya** el
retrieval. Eso lo cumple un puente que responde siempre `what`.

MEDIDO, con la sonda M10 puesta (`pregunta=pregunta("what")`):

```
TestUnaSolaSuperficieParaTodas              3 passed     <- VERDE
TestLaCapabilityEjecutaLaDelegacion         CAZADA       <- ROJO
```

**Un guard que mide que se DELEGA no mide que se delegue EN LA PREGUNTA
PEDIDA.** Es la tercera vez que sale este defecto en el repo —el guard de
B15, el de WI-92, y el de este propio bloque, que ya lo había detectado en
`_responder_y_salir`— y por eso la clase nueva no es «más cobertura».

### Lo que se añadió

`TestLaCapabilityEjecutaLaDelegacion`, 4 tests:

| | |
|---|---|
| las seis se preguntan por la capability | el bucle sale de `CONSULTAS`, no de una lista escrita aquí |
| el puente es transparente | el payload es **el de `responder`**, comparado contra la respuesta directa |
| lo que no está en el vocabulario no se construye | y el caso sin `kind`, que es distinto del caso con `kind` inválido |
| las dos de B30 NO pasan por la superficie | `claims` y `resource` no deben mezclarse con las seis |

Y las sondas suben de **8 a 10**, porque M9 y M10 **no podían existir antes**:
las ocho anteriores miden la FORMA.

| sonda | rompe | la caza |
|---|---|---|
| M10 | `pregunta=pregunta("what")` — el puente pide siempre lo mismo | `test_las_seis_se_preguntan_por_la_capability` |
| M9 | el puente reescribe el payload en vez de delegar | `test_lo_que_responde_es_lo_que_responde_la_superficie` |

**10/10 cazadas, 0 inválidas, 0 sin sonda.**

`knowledge_query.py`: 86,21 % → **100 %**.

## El recibo

```
pytest              4021 passed, 3 skipped, 0 failed   892,75 s   rc=0
cobertura global    97,11 %   (fail_under 80 %)
floors §6.3         todo modulo cumple su suelo          rc=0
  cli/              93,18 %  (suelo 70 %)   11 modulos
  runtime/          98,41 %  (suelo 90 %)   12 modulos
  superficie.py     100 %
  knowledge_query.py 100 %   <- era 86,21 %
  cli/commands/knowledge.py  93,99 %  (suelo 70 %)
arquitectura        5/5 a cero                             rc=0
project_truth       4024 declarados == 4024 colectados     rc=0
sondas              10/10                                   rc=0
```

4024 = 4021 + 3, y las 4024 se cuentan con `pytest --collect-only` sobre el
árbol real, no contra una copia (WI-115).

## Lo que este bloque deja escrito

Tres cosas que la certificación encontró y que el bloque no declaraba:

1. **El puente era prosa.** Ahora se ejecuta, y dos sondas de comportamiento
   lo vigilan —que es lo que faltaba, porque la forma ya estaba vigilada.
2. **Un guard de forma no sustituye a un test de camino.** El AST mide que
   no llames al retrieval; no mide qué preguntaste. Son dos propiedades y
   este bloque tiene las dos por primera vez.
3. **La cobertura es un guard de camino gratis.** El suelo de §6.3 no es
   burocracia: encontró una ruta muerta de tres líneas que era la entrega
   del bloque.