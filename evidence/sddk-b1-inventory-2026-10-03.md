# Evidencia B1 — Cierre de stewardship (2026-10-03)

Bloque B1 del mapa que vive en [`ROADMAP.md`](../../ROADMAP.md).
Instrumentos: `.pipelinek/b1_inventory.py` (medición, solo lectura) y
`.pipelinek/b1_verdict.py` (veredicto por contrato, solo lectura).

---

## 1. Qué es B1 y por qué es una campaña **finita**

La serie WI-91..WI-115 se abrió con una pregunta: *«¿qué declara el
repositorio que nadie comprueba?»*. Esa pregunta admite un workitem por
contrato, para siempre, y por eso B0 la cerró y B1 la convierte en un
inventario con **criterio de terminación**.

La finititud no está en la pregunta —sigue abierta—, está en exigir que
cada declaración caiga en uno de estos tres, y solo tres:

```
DECLARED
   ↓
MEASURABLE?      ── no ──▶ NO-GUARANTEED
   ↓ sí
GUARDED?         ── no ──▶ DEUDA (con el motivo POR ESCRITO)
   ↓ sí
ACCEPTED
```

**Y una regla que el inventario se aplica a sí mismo:** un contrato que se
sostiene hoy y que nadie puede romper **no se instrumenta**. Vigilar una
verdad imposible de violar es la peor versión de un guard: da cobertura
aparente y no mide nada. Es lo que WI-114 escribió al elegir sus cuatro
candidatos, y es la razón de que el inventario distinga `GUARDED` de
«no aplica».

## 2. Stop condition, y si se cumple

> B1 termina cuando todo contrato importante está `guarded`, o
> explícitamente no garantizado, o es deuda justificada; y quedan **0
> propiedades críticas declaradas pero invisibles**.

| veredicto | n | |
|---|---|---|
| `GUARDED` | 14 | hay guard, y se verificó que puede fallar |
| `DEUDA` | 2 | real, sin guard, **con el motivo escrito** |
| `NO-APLICA-O-INSTRUMENTO-ROTO` | 1 | la categoría no aplica, y se demuestra por qué |
| **total** | **17** | |

**Deuda crítica (sin guard y no declarada N/A): 0.** El stop condition se
cumple en su parte medible.

## 3. Las dos deudas, y por qué se aceptan

**inmutabilidad — 23 dataclasses frozen con campos `dict`/`list`/`set`.**
WI-113 los midió uno a uno y no encontró ni un sitio que los mute. Son
deuda de **estilo**, no defecto de comportamiento: arreglarlos sería
tocar código correcto sin prueba de que está mal. Se acepta y se
**escribe**, que es lo que la hace distinta de una deuda olvidada.

**capabilities — 32 Protocols en `platform/ports`.** No es una deuda de
B1: es que el concepto de *capability* que pide B3 todavía no existe como
tal, y lo que hay son puertos de persistencia. Se acepta **como base de
B3**, no como riesgo abierto.

## 4. La categoría que no aplica, y cómo se demuestra

**subprocess boundaries — 0 sitios.** Cero en el núcleo, y con grep sobre
`src/` no hay `subprocess`, `Popen` ni `os.system` fuera de comentarios.

Cero no es «cumplido». Se declara `NO-APLICA-O-INSTRUMENTO-ROTO` y la
razón es concreta: **la frontera de subprocess la usan los tests, no el
código de producción** (UAT-13 mata el proceso desde fuera). Es un hecho
sobre el diseño, no una ausencia de vigilancia.

## 5. Los cuatro instrumentos que hubo que arreglar

Todos los hallazgos del bloque salió de medidores **rotos**, y cada uno es una
variante del mismo error.

| # | qué pasaba | por qué no lo detectaba nadie |
|---|---|---|
| 1 | El predicado de `inmutabilidad` miraba `decorator.args[0].value is True` — el primer argumento **posicional** | El repo escribe `@dataclass(frozen=True, slots=True)`, con `frozen` como **palabra clave**. `args` vacío ⇒ cero dataclasses frozen en un repo que tiene 23. |
| 2 | `capabilities` buscaba `port` | Casa dentro de «comportamiento» y «export»: **875** falsos positivos. Un predicado demasiado ancho no es menos roto que uno demasiado estrecho. |
| 3 | `subprocess` buscaba `Popen(` | El repo no lo usa; era la categoría la que no aplicaba, no el predicado. |
| 4 | `paths` buscaba `project_root` | Se llama `project_dir`. |

**El primero es el que más importa, y es exactamente el error 32 de
WI-113 por el otro lado.** WI-113 cazó una sonda que apuntaba a un texto
inexistente. Esto es un predicado que busca la convención que el repo
escribe **de otra manera**: devuelve la lista vacía, el inventario dice
«cero», y nadie se entera porque **cero no se ve raro**.

Un predicado que devuelve siempre la lista vacía pasa todos los tests en
verde y no mide nada — el M2 de WI-110. Por eso `b1_inventory` imprime
explícitamente las categorías sin hallazgo y dice que hay que distinguir
«no aplica» de «instrumento roto», en vez de contarlas como cumplidas.

**Dos más, en el veredicto:**

- La detección de **deuda crítica** buscaba las palabras «riesgo» o
  «defecto» en el motivo escrito, y marcó las dos deudas —incluida
  capabilities, cuyo motivo dice que **no** es un defecto—. Un predicado
  que busca en la prosa que se supone que está midiendo confunde su
  propia descripción con su veredicto: WI-106 aplicado a un campo de
  texto. Ahora es **estructural**: crítica = `DEUDA` y sin guard.
- El veredicto citaba `tests/test_wi93_coverage_floors.py`, que **no
  existe** (el suelo lo vigila `scripts/check_coverage_floors.py`), y
  nadie lo notó porque un veredicto se lee, no se ejecuta. Ahora
  `citas_rotas()` lo comprueba, y distingue las citas de código de los
  ficheros de ejemplo citados en prosa.

## 6. Verificación

```
categorias con sitios medidos : 16/17
sitios hallados en total      : 1122
categorias SIN hallazgo       : ['subprocess boundaries']   <- N/A, demostrado
categorias SIN guard          : ninguna
deuda critica                 : 0
citas rotas                   : 0
```

**Contrasaltos ejecutados** (no contados, ejecutados):

| contrasalto | resultado |
|---|---|
| Un guard citado se renombra a un fichero inexistente | `rc=1`, nombra el fichero roto |
| El veredicto, en estado sano | `rc=0` |

El primer intento de la comprobación de citas marcaba **también** un
`tests/test_algo.py` que era un ejemplo dentro de su propio docstring. Es
el caso límite real: un verificador de citas que no distingue un ejemplo
de una referencia obliga a escribir los ejemplos de otra forma. Se
resolvió borrando los docstrings del AST antes de escanear.

## 7. Lo que B1 NO hace, y por qué

- **No arregla las 23 dataclasses.** Lo medido dice que no hay mutación;
  arreglarlas sería tocar código correcto sin prueba de que está mal. Se
  acepta la deuda y se escribe.
- **No toca `promotion list`.** B1 lo nombra como problema expreso, y
  **MEDIDO: ya no existe**. `src/skillgraph/cli/commands/promotion.py:358`
  llama a `storage.list_promotions()`, la API pública. El README
  todavía afirmaba que leía `promotion_outbox` por SQL directo —una
  afirmación vieja que B0 no había tocado porque no estaba en su
  medición—, y el propio módulo lleva un comentario que dice lo
  contrario. **El problema ya estaba cerrado; lo que quedaba era la
  afirmación que decía que no lo estaba.**
- **No abre workitems por cada fila del inventario.** Eso es
  precisamente lo que B1 cierra.

## 8. El punto de partida de B2

B1 deja un dato que es el argumento de B2: la categoría `recovery` sale
`GUARDED` con 17 sitios, y su guard es real. **Lo que no está probado es
el crash real** — hoy la recuperación se ejercita con failpoints
inyectados, no matando el proceso. Por eso B2 no empieza inventing
guards: empieza executando contra un proveedor real, matando procesos de
verdad, y usando procesos separados para la concurrencia.
