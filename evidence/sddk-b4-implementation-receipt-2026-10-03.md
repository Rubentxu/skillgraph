# implementation-receipt — B4

Ciclo `p-b7740b96d79ec013/b4` · transición `phase.build.complete` ·
requisito `implementation-receipt`.

## Qué entrega

La mitad **observada** de la separación CRD-like. B3 dejó alcanzable la
mitad *declarada*; esta es la otra, y estaba en el mismo estado: escrita
en el esquema, inalcanzable en ejecución.

## Lo que estaba medido antes de escribir una línea

Con `scripts/measure_b4_observed_state.py`, versionado en `scripts/` y no
en `.pipelinek/` (backlog `bl-bl-01M41DFZEZ0003882TZNP7NPM0`):

```
1 INSERT y 0 UPDATE en la tabla `resources`
0 ocurrencias de `conditions` en todo `src/`
`generation` declarada y nunca escrita
ejecución real: status_json='{}' generation=1 resource_version=1
```

`status_json` está declarada `NOT NULL DEFAULT '{}'` y nadie la
actualizaba. Cada recurso nacía sin observar y moría sin observar, y el
`NOT NULL` lo hacía **parecer** un estado. Es el hueco con el que abrió
B3, un nivel más abajo.

## Commits

| | |
|---|---|
| Antes | `8e8e112` |
| Después | `7eeb026` |
| Commits | **4** |
| Ficheros | 16 modificados, 2075 inserciones, 17 borrados |
| Etiqueta | `v0.24.0` → `7c62326cc0b9a9f4b6e1cf1f79e17b711bc2b7f2` (anotada) |
| Remoto | **sin push** — 5 commits sin publicar |

```
b9a7ac9  feat(resources): la mitad observada de un recurso deja de ser inalcanzable
ad0f037  docs(b4): la exploracion, la spec y el diseno del bloque, con sus gates
7c62326  build(release): v0.24.0
7eeb026  chore(release): mantenimiento post-tag de v0.24.0
```

## Lo entregado

- `ResourceStatus` y `Condition` (`resources/status.py`), `frozen` y con
  `slots`. `Condition.type` es un `Literal` cerrado y **repetir un type
  es error**: `Ready=True` y `Ready=False` a la vez no son un status,
  son un status que ya no sabe qué observa.
- `Storage.update_resource_status` — el primer `UPDATE` de la tabla
  `resources`, alcanzable desde `src/` por la delegación de
  `KnowledgeDelegations`, que es lo que lo hace público.
- `Storage.get_resource_status` — lee, y devuelve `None` cuando no hay
  status. Ausencia y vacío son cosas distintas, y confundirlas hace que
  un recurso sin observar parezca observado.

## La invariante, y por qué tiene guard propio

`generation` es lo que el **spec** declara. `resource_version` es lo que
el **almacenamiento** lleva. Escribir el status sube el segundo y **no**
el primero.

Lo importante no es la invariante: es lo que se midió al cazar la sonda
M3, que la quita del `UPDATE`. **El sistema sigue funcionando
exactamente igual.** Nada falla, nada se rompe y la separación
desired/observed se vuelve decorativa. Es el defecto que no se nota, y
por eso tiene guard propio en vez de confiar en que alguien lo note.

`observed_generation` se **lee de la fila**, no se declara: declarado
mentiría en cuanto el spec cambiara por debajo, y sin ningún error — sería
el status más fiable del mundo y el menos cierto.

## Lo que NO se hizo, y por qué está en un guard

`status` **no vive en `Brick`**, y R5 lo fija por AST, porque *«Brick no
gana status»* no se deduce de un valor sino de la forma. Si el tipo
declarado llevara el estado, un pack declararía el estado de su propio
recurso y la mitad observada dejaría de estar observada: no habría forma
de distinguir `observed` de `human-asserted`. La separación es de
**tipo**, no de convención — y una convención es lo que el próximo
fichero salta por encima.

## Verificación

| | |
|---|---|
| Tests nuevos | **19** en `tests/test_b4_observed_state.py` |
| Mutaciones | **8/8 cazadas**, 0 sondas inválidas |
| Restauración | byte a byte, verificada por `git diff` |
| Certificación | 2992 passed, 3 skipped declarados |
| `ruff check` / `format` | limpios |

Uno de los 19 tests ejecuta el instrumento que abrió el bloque y exige
que ya no reporte el hueco: si el hueco vuelve, el test se pone rojo con
el veredicto del propio instrumento.

### Las dos sondas que hubo que cambiar

- **M6** quitaba `sort_keys=True` y **no fue cazada**. El orden de las
  claves lo fija el literal de `to_dict`, luego dos escrituras del mismo
  objeto dan el mismo texto con o sin él: la propiedad que la sonda
  quería medir era **vacua**. No era una sonda mala, era una propiedad
  que se cumple por construcción. Sustituida por un round-trip, que sí
  carga con algo.
- La instrumentación de este bloque no se versionó en `.pipelinek/` sino
  en `scripts/`, porque las mediciones de este repo no son recuperables
  y ya están registradas como deuda.

## Lo que la certificación destapó, y no era de B4

`tests.total` iba en 2974 y el árbol colectaba 2996. Lo cazaron **dos
guardas independientes** —el de WI-115 y el de convergencia de B0—,
diciendo lo mismo. La cifra va después del run, como manda la regla.

El `+22` está desglosado por diff de identificadores contra un worktree
en el commit que escribió el 2974, y **3 de los 22 no son de B4**: son
casos nuevos de `test_wi47_broad_except_guard.py`, que parametriza sobre
la lista de módulos y generó tres al aparecer `resources/status.py`. Un
guard que deriva sus casos del árbol se entera solo de que añadiste un
módulo. Antes de atribuir la diferencia a B3 se comprobó que su 2974
era veraz: 2974 colectados.

## Orden imposible, y es la segunda vez en una sola release

Dos commits llevan `HOOK_SKIP_TESTS=1`, y la razón es la misma clase en
los dos, no pereza:

- El commit de release exige que la etiqueta exista **antes** de
  declararla (AGENTS §12), y dos guardas exigen que `release.tag` sea la
  última etiqueta de git.
- El commit post-tag no puede pasar porque el hook corre la suite
  **antes** de que el commit exista: HEAD sigue siendo el commit
  etiquetado, luego `test_version_matches_git_tag` cae en su rama de
  «HEAD en la etiqueta» y ve `0.24.0.dev0` donde exige `0.24.0`.

La regla es correcta y el orden es imposible: el hook evalúa el estado
**previo** al commit contra una regla que solo es cierta **posterior** a
él. La compensación es la suite completa ejecutada después de cada uno,
que es lo que hay al final de este receipt.

## Lo que queda sin cerrar

- **Sin push.** 5 commits sin publicar, más los de B3 ya publicados.
- **Un test intermitente de B2**, no de B4:
  `test_b2_real_concurrency.py::TestLectoresConcurrentes::test_leer_mientras_ocho_escriben_no_rompe_nada`
  falló una vez de cuatro corridas completas de suite, con
  `sqlite3.OperationalError: database is locked` en la construcción del
  `Storage`. Aislado: 10/10 verde. Bajo 6 corridas en paralelo: 6/6
  verde. El diagnóstico está medido y **no** está en este bloque; ver
  `STATE.yaml`, `current_workitem`.
- **Ciclo `b4-cierre`**: se creó por error al no encontrar `b4` (que sí
  existía, pero `sddk cycle status` sin `--cycle` no lo ve porque no hay
  lease). Queda **abierto, vacío, en `explore`, con 0 artefactos**.
  `sddk cycle supersede` exige aprobación de una autoridad humana y no
  se fuerza. No se ha inventado una transición para cerrarlo.
