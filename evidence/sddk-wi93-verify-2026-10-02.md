# WI-93 — El contrato de cobertura que el repo declara en dos sitios, y no exigía ninguno

- **Ciclo**: `p-b7740b96d79ec013/wi-93-coverage-contract-enforcement`
- **Fecha**: 2026-10-02
- **Suite**: 2529 passed (2499 antes; +30)

## Los dos contratos

El repositorio declara dos cosas distintas sobre cobertura, y ninguna se
comprobaba en la CI canónica (`.pipeline.kts`, 5 stages: `discover-repo`,
`sync-deps`, `unit-tests`, `lint`, `evidence`):

| # | Dónde | Qué declara | ¿Quién lo comprueba? |
|---|---|---|---|
| 1 | `pyproject.toml` `[tool.coverage.report]` | `fail_under = 80` (global) | `coverage report`, **si alguien ejecuta el script a mano** |
| 2 | `AGENTS.md §6.3` | suelos **por módulo**: core ≥90 %, CLI ≥70 %, `paths.py` ≥60 % | **nadie**: `coverage report` sólo admite un umbral global |

El segundo contrato **no lo podía expresar ninguna herramienta** que hubiera en
el repo. Es una cifra que se declara y no se verifica.

## La premisa heredada, medida

`scripts/coverage.sh` lleva en su cabecera:

> *NO usar esto como gate de CI: `.pipeline.kts` corre pytest sin coverage
> a propósito (la instrumentación de subproceso **multiplica** el tiempo de
> suite). Es una herramienta de medición, invocada a mano.*

Es una **decisión documentada**, no un descuido. Pero su motivo es una
afirmación sin medir, y este bloque la somete a prueba:

| | Wall clock | Fuente |
|---|---|---|
| `pytest` a pelo (lo que hacía la CI) | **~110 s** | journal run `84dd0239`: 107,70 s de pytest |
| `scripts/coverage.sh` completa | **203 s** | medido dos veces: 200,77 s y 201,77 s de pytest |
| **Delta** | **+93 s** (~1,85× el stage) | |

**No multiplica: cuesta un minuto y medio más.** La premisa era una hipótesis
sin dato y el dato la desmiente.

> Una segunda medición de la receta dio 408 s de wall clock, pero ese comando
> incluía además mi `coverage report` y mi checker, y corrió junto a un
> `pipelinek validate` (compilación Kotlin). El número honesto de la receta son
> los ~203 s. Reportar los 408 s como coste de la receta habría sido una
> medición equivocada con formato de dato.

## El hueco real que encontró el checker

Al poder mirar por módulo apareció algo que el umbral global no podía ver:
`runtime/http_adapter.py` medía **88,04 %**, por debajo del 90 % que le
corresponde por ser un módulo del core.

Sus 19 sentencias sin cubrir no eran código inalcanzable:

| Línea | Qué es |
|---|---|
| 93, 97, 131 | guardas de `__post_init__` y de `_config_from_env` |
| 304, 460 | `_build_strategy` y `_default_model` con proveedor no soportado |
| 191, 194, 212, 215, 218 | respuestas Anthropic/OpenAI malformadas |
| 239 | el LLM devuelve JSON válido que no es un dict |
| 159 | la rama `- included:` del prompt |
| 424 | «defensive: should not reach here» — **inalcanzable por construcción** |
| 442, 449 | failpoint 429 y el `httpx.Timeout` que construye el cliente por defecto |

El módulo ya traía failpoints y un `client` inyectable **precisamente** para
probarlas sin red. Los tests de red existentes usan `respx` con cliente
inyectado, y por eso la rama de producción que construye su propio
`httpx.Timeout` no la tocaba nadie.

`tests/test_wi93_http_adapter_gaps.py` (30 tests) la cubre:

| | Antes | Después |
|---|---|---|
| `http_adapter.py` | 88,04 % | **99 %** (sólo queda la 424) |
| `runtime/` agregado | 95,11 % | **97,98 %** |
| global | 94,75 % | **95,22 %** |
| `cli/` agregado | 86,91 % | 86,91 % |
| `paths.py` | 80,85 % | 80,85 % |

## Por qué este módulo y no otro

AGENTS §6.3 nombra `runtime` entre los módulos del core pero no enumera cada
fichero. Elegí la lectura **estricta**: todo módulo de `runtime/` hereda el
90 %. Es la lectura que hace útil el contrato, y la que encontró el hueco.
Queda escrito como decisión, no presentado como cita literal de §6.3.

Consecuencia de esa lectura: el checker **exige que todo módulo de `runtime/`
con código tenga suelo declarado**, para que añadir uno nuevo no pase
desapercibido. Un guard que sólo vigila la lista que él mismo mantiene no
vigila nada.

## Dos decisiones de diseño del checker

**Agrega recuentos, no porcentajes.** Con `branch = true`, coverage combina
sentencias y ramas y una rama parcial cuenta como media. Promediar porcentajes
da más de lo que hay: un paquete al 95 % de media puede esconder un módulo al
60 %.

**Un suelo sobre un módulo fantasma es un fallo.** Si la ruta no aparece en el
informe, el checker aborta en vez de medir en silencio. Un módulo vacío
(0 sentencias, 0 ramas — los `__init__.py` de reexport) queda excluido:
exigirle un suelo es exigir medir un fichero vacío, y además revienta con
división por cero.

## Mutaciones del checker

| # | Mutación | Resultado |
|---|---|---|
| M1 | subir un suelo por encima de la cobertura real (`http_adapter` a 99,9) | **cazada** |
| M2 | apuntar un suelo a un módulo que no existe | **cazada** |
| M3 | borrar el suelo de un módulo de `runtime/` **que tiene código** | **cazada** |
| M4 | control final: el estado real vuelve a verde y el fichero queda byte-idéntico | **OK** |

`cazadas=3  no-cazadas=0`

M1 es la que importa: si el checker no midiera, subir el suelo no lo notaría, y
un gate que no puede fallar es una decoración.

## Conocimiento negativo

- **La cobertura agregada puede tapar un módulo débil.** `runtime/` estaba al
  95,11 % — muy por encima de 90 — y contenía un módulo al 88 %. «El paquete
  llega al 90 %» y «cada módulo llega al 90 %» son contratos distintos, y sólo
  el segundo encuentra el hueco. Declarar un suelo agregado es elegir que un
  módulo débil sea aceptable.
- **La instrumentación de subproceso no es un lujo: es lo que hace verdadera la
  medición.** Sin el hook `.pth`, el CLI que la suite lanza por subproceso mide
  65,86 % en vez de 94 %. Instrumentar cuesta +93 s; no instrumentar produce un
  número que parece un incumplimiento y es ceguera del instrumento.
- **Un `if pipeline | tail; then` mide el `tail`, no el pipeline.** Leí `rc=0`
  de un comando cuyo script estaba reportando cinco incumplimientos: el `rc` era
  el de `tail`. Misma familia que medir `/usr/bin/sg` en WI-88 o que medir
  `wc -c` sobre una línea con `—` en WI-91: **medir la cosa equivocada produce
  un número que parece confirmar cualquier premisa.**
- **Un guard que sólo vigila lo que él mismo mantiene no vigila nada.** La
  primera versión comprobaba los módulos de la lista `SUELOS` y nada más:
  añadir un módulo nuevo a `runtime/` sin suelo pasaba desapercibido. Lo vio la
  mutación M3 y se cerró exigiendo suelo para todo módulo de `runtime/` con
  código.
- **La cobertura es una techo, no una puerta.** Subir un módulo del 88 al 99 %
  no demuestra que el adaptador funcione contra Anthropic: demuestra que
  rechaza bien lo que no debe aceptar. Son cosas distintas y el bloque no las
  confunde.

## Lo que sigue sin probarse

Este bloque **no** prueba que Anthropic ni OpenAI respondan. Eso requiere
credenciales que este entorno no tiene, y el registro de conformidad de H9 lo
declara explícitamente como hueco abierto. Lo que sí queda probado es que el
adaptador **rechaza** bien lo que no debería aceptar, que es la mitad del
contrato que es local.
