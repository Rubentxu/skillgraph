# WI-87 — Verificación: el vocabulario de estados tiene una sola fuente

- **Ciclo**: `p-b7740b96d79ec013/wi-87-single-source-state-vocabulary`
- **ADR**: ADR-0015
- **Commit**: `d47b7af`
- **Fecha**: 2026-10-02

## Qué se midió antes de decidir

La decisión (d) de `next_workitem` decía, textualmente, que `PROMOTION_STATUSES` y
`NON_TERMINAL_RUN_STATES` estaban "DEFINIDOS en `storage.py` (no son re-exports)" y que
era "la única deuda de arquitectura que queda sin medir". La premisa era correcta pero
incompleta, y lo que se encontró al medir la superó:

| Hecho | Valor medido |
|---|---|
| `core/runtime_types.py:142` | `TERMINAL_RUN_STATES` — **ya existía** en la capa de dominio |
| `core/runtime_types.py:177` | `is_terminal_run_state()` — **ya existía** |
| `platform/storage.py:123` | `NON_TERMINAL_RUN_STATES` — el **complemento**, escrito a mano |
| `platform/schema.py:262` | `CHECK (status IN (...))` — 4 estados, escritos a mano |
| `platform/storage.py:117` | `PROMOTION_STATUSES` — los mismos 4, escritos a mano |
| Relación entre el CHECK y la constante | **ninguna** |
| Test que la declaraba cubrir | `tests/test_h9_storage_promo_list.py:114-116` |

La capa de dominio ya tenía la mitad del vocabulario y su helper. La fachada
reimplementaba el complemento sin ninguna relación verificada.

## El test que afirmaba lo que no hacía

```python
def test_valid_statuses_constant_matches_schema(self) -> None:
    """PROMOTION_STATUSES cubre exactamente el CHECK constraint del schema."""
    assert frozenset({"PENDING", "IN_PROGRESS", "PUBLISHED", "FAILED"}) == PROMOTION_STATUSES
```

No lee `schema.py`. Compara la constante contra un literal repetido en el propio test.
Seguiría en verde con el `CHECK` cambiado, que es exactamente lo que su nombre y su
docstring declaran proteger.

## Por qué un test de igualdad no bastaba

Comprobado directamente antes de tocar nada:

```
CHECK del DDL : ['FAILED', 'IN_PROGRESS', 'PENDING', 'PUBLISHED']
constante     : ['FAILED', 'IN_PROGRESS', 'PENDING', 'PUBLISHED']
coinciden hoy : True
```

Y el DDL sí llevaba el vocabulario escrito a mano (1 literal con `IN_PROGRESS`). Un test
de igualdad habría sido verde desde el primer día. La red lleva **dos** comprobaciones
que no se sustituyen: la igualdad (el invariante) y una que lee el AST de `schema.py` y
falla si el DDL vuelve a escribirse a mano (la derivación).

## El fallo que esto habilitaba

UAT-06 exige que un run interrumpido por un crash se reanude. `find_active_run()` decide
qué es reanudable con `NON_TERMINAL_RUN_STATES`. Si se añadía un estado a `RunState` sin
tocar `storage.py`, el estado nuevo no aparecía en el conjunto, la consulta
`WHERE state IN (...)` no lo encontraba, y el CLI creaba **un segundo run** para el mismo
trabajo lógico. Sin log, sin error, sin test rojo.

Es la misma clase que QW-E (donde la validación rechazaba `skill_pack`), pero con
consecuencia peor: allí se rechazaba un valor, aquí se duplica trabajo.

## Cambios

- `PromotionStatus` Literal nueva en `core/runtime_types.py`.
- `NON_TERMINAL_RUN_STATES` derivado: `frozenset(get_args(RunState)) - TERMINAL_RUN_STATES`.
- `PROMOTION_STATUSES` derivado: `frozenset(get_args(PromotionStatus))`.
- `platform/schema.py` genera el `CHECK` desde ese conjunto (`SCHEMA_SQL` pasa a f-string;
  los dos `DEFAULT '{}'` se escapan a `'{{}}'`).
- `platform/storage.py` pierde ambas constantes. `promotion_repository` y
  `run_repository` las importan de la hoja `core.runtime_types`.
- Docstring de `_find_active_run_id` corregido: apuntaba a
  `Storage.NON_TERMINAL_RUN_STATES`, que nunca existió como atributo.

`SCHEMA_VERSION` sigue en 1: el conjunto de valores aceptados no cambia, no hay migración.

## Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | DDL con el vocabulario escrito a mano | **cazada** |
| M2 | DDL acepta un estado fuera del dominio | **cazada** |
| M3 | DDL pierde un estado del dominio | **cazada** |
| M4 | `NON_TERMINAL_RUN_STATES` escrito a mano (mismo valor) | imposible por construcción |
| M5 | con M4, añadir `PAUSED` a `RunState` | **cazada** — la partición exhaustiva detecta el olvido |
| M6 | la partición deja de ser disyunta | imposible por construcción |

`cazadas=4  imposibles-por-construccion=2  no-cazadas=0`

M4 y M6 no son agujeros: son la demostración de que la derivación hace el fallo
imposible. M4 produce el mismo valor, así que la igualdad no puede verlo; M5 prueba que
la red de seguridad sí lo detecta en cuanto el valor de `RunState` cambia. M6 es
imposible porque al derivar por complemento, añadir un estado terminal lo resta del no
terminal automáticamente, y ambas invariantes se mantienen por definición.

Anotar M4 y M6 como "no cazadas" habría sido afirmar que hay un agujero donde no lo hay.
El script distingue las tres categorías por eso.

## Conocimiento negativo

- **Una primera versión de la red afirmaba algo falso.** Decía que "un estado
  desconocido cuenta como no terminal", en un docstring de un helper y en un test. Es
  falso: `RunState` es una ADT cerrada y un valor que no está en el Literal no pertenece
  al vocabulario en ninguno de los dos sentidos. Se corrigió la afirmación, no el
  criterio. El intento de probar la polaridad con `PAUSED` fue lo que lo reveló: `PAUSED`
  no puede estar en el complemento de un conjunto del que no forma parte.
- **`is_non_terminal_run_state()` se retiró**: se añadió con la misma lógica y tenía
  **cero** consumidores. WI-81 borró alias muertos y WI-86 la capa de re-export muerta;
  introducir un tercer muerto contradice las dos.
- **El primer script de mutaciones nunca corría los tests.** `mutate` capturaba la salida
  de la *mutación* en vez de la de pytest, así que todo se|reportaba "no cazado" — un
  informe que afirmaba una medición inexistente.
- **El control de restauración usaba `git diff --quiet` contra HEAD**, con el árbol
  justru sin commitear: siempre fallaba. Un control que siempre falla no es un control.
  Ahora compara contra el backup con `cmp`.
- **`test_wi82_evidence_write_idempotence.py:179` limita su `git status --porcelain` a
  `-- tests/uat-evidence/`**, así que no podía ver que `audits/` sigue ensuciando el
  árbol. Es una instancia distinta de la misma clase que WI-82, no un descuido de aquel
  arreglo. Registrado como seguimiento; no se corrige aquí por ser de otra superficie.
  El informe regenerado se commitea en este bloque porque es una medición real del árbol
  (20779 → 20829 LoC) y revertirlo dejaba el informe versionado mintiendo.

## Resultados

- Tests afectados: **37** en los tres ficheros del WI, **144** con la suite de storage y
  sus contratos, **423** en la selección amplia de promoción / storage / estados.
- Suite completa: **2430 passed in 106.01s** (lo reportó el pre-commit al commitear).
- `ruff check src tests`: limpio. `ruff format --check`: limpio.
- Tests nuevos: 14. `2416 + 14 = 2430`.
