# WI-86 — correccion: WI-65 ya estaba entregado; y la capa de re-export de `platform.storage`

- **Ciclo SDDK:** `p-b7740b96d79ec013` (cierre de estado) + work item WI-86
- **Fecha:** 2026-10-02
- **BASE:** `d01e96f` (post-release `v0.16.12.dev0`)
- **Tipo:** `refactor` (sin bump) + `docs` (correccion de registro)

## Parte 1 — Correccion de un registro mio que era falso

En el cierre del bloque anterior escribi, en `STATE.yaml.next_workitem` y
en el mensaje al operador, que **`WI-65-fase-1` era el siguiente bloque
sustantivo**. **Es falso.** WI-65 ya estaba entregado, y el error fue
mío por no verificar antes de registrar.

### La cronologia, medida

| Momento | Hecho | Commit |
|---|---|---|
| 2026-10-02 08:09:42Z | se abre el ciclo `wi65-storage-facade-decomposition` | — |
| 2026-10-02 10:10:37 | se commitea su informe de exploracion | `c471264` |
| **2026-10-02 11:03:14** | **WI-68 desdobla `storage_delegations` en 5 modulos** | `405f49e` |
| **2026-10-02 11:31:53** | **se publica `v0.16.10`, que entrega el bloque WI-65..WI-71** | `2ee6d77` |

`git merge-base --is-ancestor c471264 2ee6d77` → **si**: el informe se
commiteo 81 minutos antes de la release que lo implemento.

### El informe no estaba equivocado, estaba vencido

El informe de exploracion **acierta en todo lo que predice**: «las 65
delegaciones se agrupan en 5 mixins perfectamente disjuntos (31/19/7/4/4)».
Medido hoy:

```
src/skillgraph/platform/storage.py          613 LoC   (informe: 1807)
metodos de Storage                           15       (informe:  80)
knowledge_delegations.py   31 metodos  405 LoC
run_delegations.py         19 metodos  321 LoC
promotion_delegations.py    7 metodos  103 LoC
event_store_delegations.py  4 metodos   89 LoC
policy_delegations.py       4 metodos   81 LoC
```

Y `class Storage(RunDelegations, KnowledgeDelegations,
PromotionDelegations, EventStoreDelegations, PolicyDelegations)` — los
cinco, exactamente como estaba previsto. El plan se ejecuto **verbatim**.

Lo que fallo fue mio: lei el informe como si describiera el presente, sin
contrastarlo con el arbol. Es exactamente el modo de fallo que el objetivo
prohibe («no confies en estados documentales; el codigo es la evidencia»),
y lo cometi en la frase que mas pesaba: la que designaba el siguiente
trabajo.

### Decision sobre el ciclo

`wi65-storage-facade-decomposition` se cierra con `goal-replaced`: su
objetivo **fue entregado**, pero por otro bloque (WI-65..WI-71, v0.16.10),
no por el ciclo que lo proceso. Quedaba `OPEN` desde hace horas con un
artefacto de gran calidad que ya no describia nada.

Con el ciclo `wi-65-subprocess-coverage-file` (cerrado en el bloque
anterior por `goal-replaced` con la misma forma) el proyecto queda con
**27 ciclos CLOSED y 0 abiertos**.

## Parte 2 — WI-86: la capa de re-export de `platform.storage`

Decision (a) de `STATE.yaml.next_workitem`, que llevaba dos bloques
abierta con «requiere ADR NUEVO». Resuelta por medicion.

### Lo medido

Los 7 simbolos que `storage.py` importa y reexporta
(`MAPPER_NAMES`, `_row_to_stored_event`, `_row_to_stored_promotion`,
`_row_to_stored_budget`, `_row_to_run`, `_row_to_node_execution`, `_uid`)
aparecen **exactamente dos veces** cada uno en el fichero: una en el
`import` (lineas 61-68) y otra en `__all__` (lineas 90, 111-116).

**Ninguno se usa en una sola linea de codigo dentro de `storage.py`.**
La capa entera existe para servir a hermanos.

Sus consumidores reales son **cinco**, no los dos que nombra el comentario
del propio bloque de re-export:

| Consumidor | Importa desde `platform.storage` |
|---|---|
| `event_store.py:24` | `_SCHEMA_SQL`, `Storage`, `_row_to_stored_event` |
| `policy_store.py:18` | `Storage`, `_row_to_stored_budget` |
| `knowledge_repository.py` | `_uid` |
| `promotion_repository.py:18-22` | `PROMOTION_STATUSES`, `Storage`, `_row_to_stored_promotion` |
| `run_repository.py:32-38` | `NON_TERMINAL_RUN_STATES`, `Storage`, `_row_to_run`, `_row_to_node_execution`, `_row_to_stored_event` |

Y `row_mappers.py` es una **hoja**: importa `sqlite3`, `typing` y
`skillgraph.platform.ports` (los DTO). No depende de nada que dependa de
el. No hay ciclo que justifique el rodeo.

`MAPPER_NAMES` no lo consume **nadie** a traves del facade: los dos unicos
usos (`tests/test_wi65_storage_schema_mappers.py` y
`tests/test_wi81_dead_aliases.py`) lo importan ya directamente de
`row_mappers`.

### El defecto

Es el mismo patron que WI-81, una generacion mas abajo. Un modulo
declara en `__all__` unos simbolos que no usa, para que `ruff` no los
borre por F401, y con eso **anuncia** una superficie que no sostiene. El
comentario del bloque lo dice sin notar la contradiccion: los
exporta «porque `event_store` y `policy_store` los importan desde ahi»,
cuando en realidad los importan **cinco** modulos, y ninguno de los cinco
tiene una razon para no ir a la hoja.

La consecuencia no es academica: quien lea `storage.__all__` concluira que
`platform.storage` es la direccion canonica de los mappers, cuando la
direccion canonica es `row_mappers` (lo que ya hace `MAPPER_NAMES`
cuando se importa de ahi). Es el mismo «dato plausible y falso» que el
proyecto rechaza en `knowledge/git_source.py:365`.

### El arreglo

Migracion, no borrado: cada consumidor pasa a importar de `row_mappers`, y
`storage.py` retira el bloque de re-export y las 7 entradas de `__all__`.
Cero cambios de comportamiento: es cambiar de donde se resuelve **el
mismo objeto**, y la red lo comprueba por **identidad**, no por igualdad.

`PROMOTION_STATUSES` y `NON_TERMINAL_RUN_STATES` **no se tocan**: estan
definidos en `storage.py` (lineas 123 y 129), no son re-exports. Que los
consuman los componentes es una pregunta de propiedad de dominio distinta
—describe una regla de `runs` o de `promotions` y vive en el facade— y esa si
es un cambio de arquitectura que merece ADR. Se registra como decision
abierta, no se ejecuta aqui.

## Conocimiento negativo

- `MAPPER_NAMES` se conserva en `row_mappers`: es la guarda de recuento
  que usan `test_wi81_dead_aliases` y `test_wi65_storage_schema_mappers`.
  Lo que cae es su re-export por el facade, que no tiene consumidor.
- No se puede saber si el re-export de `platform.storage` promete algo a
  un consumidor **fuera** del repo. Medido: cero en el repo. Se documenta
  como cambio de contrato en CHANGELOG y aqui, que es donde puede
  sobrevivir (`external/` esta en `.gitignore`).
- El informe de exploracion de un ciclo puede ser **excelente y aun asi
  estar vencido**. La calidad del analisis no dice nada sobre si su
  premisa sigue en pie; hay que medir el estado actual contra ella.
