# verification-report — B4

Ciclo `p-b7740b96d79ec013/b4` · transición `phase.verify.complete`.

## Veredicto por requisito

| | Requisito | Cómo se midió | Resultado |
|---|---|---|---|
| R1 | `ResourceStatus` y `Condition` existen, son inmutables y `Condition.type` es un `Literal` cerrado | construcción + attempted de reasignación | **CUMPLE** |
| R2 | La mitad observada es alcanzable: existe un `UPDATE` de `status_json` y se lee de vuelta | ejecución real contra `Storage` en `tmp_path` | **CUMPLE** |
| R3 | Sin status, la lectura devuelve `None`, no un status vacío | ejecución real: fila recién insertada | **CUMPLE** |
| R4 | Escribir status sube `resource_version` y **no** `generation` | dos escrituras seguidas, ambas columnas leídas | **CUMPLE** |
| R5 | `Brick` no gana el campo `status` | AST sobre `src/` | **CUMPLE** |

## El criterio de aceptación, y quién lo decía

El roadmap pedía que la mitad observada de un recurso dejara de ser
inalcanzable. **Antes de escribir nada**, con
`scripts/measure_b4_observed_state.py`:

```
1 INSERT y 0 UPDATE en la tabla `resources`
0 ocurrencias de `conditions` en todo `src/`
`generation` declarada y nunca escrita
ejecución real: status_json='{}' generation=1 resource_version=1
```

**Ahora**, el mismo instrumento:

```
scripts/measure_b4_observed_state.py -> 0
```

Y el test que lo ejecuta está en la suite: si el hueco volviera, el
propio test se pondría rojo con el veredicto del instrumento.

## La invariante, medida y no declarada

`generation` es lo que el **spec** declara; `resource_version` es lo que
el **almacenamiento** lleva.

| | antes de escribir status | después de escribir status |
|---|---|---|
| `generation` | 1 | **1** |
| `resource_version` | 1 | **2** |

Que `generation` no se mueva **no es un descuido**: es lo que sostiene la
separación. La sonda M3 la quita del `UPDATE` y lo que se midió al
cazarla es lo importante — el sistema sigue funcionando **exactamente
igual**. Nada falla, nada se rompe, y la separación desired/observed se
vuelve decorativa sin que nadie lo note. Por eso tiene guard propio.

`observed_generation` se **lee de la fila**. Si se declarara, mentiría en
cuanto el spec cambiara por debajo, y sin ningún error: sería el status
más fiable del mundo y el menos cierto.

## Mutaciones

`scripts/mutate_b4_observed_state.py` — **8/8 cazadas, 0 sondas
inválidas**, árbol restaurado byte a byte verificado por `git diff`.

| | Sonda | Qué mide |
|---|---|---|
| M1 | el status se escribe pero vacío | el fallo silencioso de la columna `NOT NULL` |
| M2 | el status declara su propia generación | el campo que miente sin fallar |
| M3 | escribir status sube `generation` | **la invariante R4** |
| M4 | escribir status no sube `resource_version` | dos escrituras indistinguibles |
| M5 | se puede repetir un `type` de condición | `Ready=True` y `Ready=False` a la vez |
| M6 | `to_dict` pierde un campo | round-trip: la fila guarda menos de lo que el status dice |
| M7 | las condiciones dejan de ser tupla | una `list` que entra por la frontera |
| M8 | `Brick` gana el campo `status` | **R5** |

**M6 se sustituyó, y el motivo importa más que la sonda.** La primera
M6 quitaba `sort_keys=True` y **no fue cazada**: el orden de las claves
lo fija el literal de `to_dict`, luego dos escrituras del mismo objeto
dan el mismo texto con o sin él. La propiedad que la sonda quería
medir era **vacua**. No era una sonda mala — era una propiedad que se
cumple por construcción, y un guard que mide eso no mide nada.

## Certificación

| Corrida | Resultado |
|---|---|
| 1 (pre-`tests.total`) | 2991 passed, 3 skipped, **2 failed** |
| 2 (post-release commit) | 2992 passed, 3 skipped, **1 failed** |
| 3 (final) | **2993 passed, 3 skipped, 0 failed** |

2993 + 3 = **2996**, que es lo que dice `tests.total`. La cifra se
escribió **después** del run, como manda la regla.

### Los 2 fallos de la primera corrida

Los dos eran `tests.total` desactualizado y su gemelo de convergencia
de B0, **diciendo lo mismo**. Es la primera vez que el guard de WI-115
muerde en esta sesión, y caza porque el recuento viene del árbol
(`pytest --collect-only`) y no de una copia escrita en el propio test.

El `+22` está desglosado por **diff de identificadores** contra un
worktree en el commit que escribió el 2974, y **3 de los 22 no son de
B4**: son casos nuevos de `test_wi47_broad_except_guard.py`, que
parametriza sobre la lista de módulos y generó tres al aparecer
`resources/status.py`. Antes de atribuir la diferencia a B3 se comprobó
que su 2974 era **veraz**: 2974 colectados.

## Deuda registrada, no abierta

### 1. Un test intermitente de B2 — severidad media, prioridad baja

`tests/test_b2_real_concurrency.py::TestLectoresConcurrentes::test_leer_mientras_ocho_escriben_no_rompe_nada`
falló **1 de 3** corridas completas de suite, con
`sqlite3.OperationalError: database is locked` en la construcción del
`Storage`.

Medido, no supuesto:

- aislado: **10/10 verde**;
- con 6 copias en paralelo (carga): **6/6 verde**;
- en el worktree del commit previo a B4: **5/5 verde**;
- B4 no toca la apertura de conexión, el `journal_mode`, el
  `busy_timeout` ni el harness de concurrencia.

**Diagnóstico del reintento, medido por separado.** El patrón actual es
`try: PRAGMA journal_mode = WAL / except: PRAGMA journal_mode = WAL`, y
el comentario del propio código afirma —correctamente— que *«la
solución no es esperar más: es no preguntar»*. **La implementación hace
lo contrario: pregunta otra vez.** Reproducido 3/3 de forma
determinista:

```
patrón actual (sin backoff) : FALLA (database is locked) tras 10.01 s
tras soltar el lock          : ok en el intento 1, 0.00 s
```

Los 10.01 s son 2 × 5 s de `busy_timeout`: los dos intentos se quedan
sin ventana, no porque el segundo sea instantáneo sino porque ambos
esperan lo mismo. Y la alternativa que propone el comentario **tampoco
funciona**, medido: *leer* `PRAGMA journal_mode` también se bloquea
(5.005 s), porque la lectura toma lock compartido detrás del exclusivo.

**Por qué no se arregla en B4.** Es superficie de B2, no de B4, y el
arreglo necesita un número de intentos y un presupuesto de espera que
elegir *midiendo* la contención real — que es un workitem con su propia
exploración, no un apéndice de un bloque que ya está entregado y
etiquetado. Queda aquí con el diagnóstico ejecutado, que es lo que
permite empezarlo sin volver a investigar.

**Severidad: media.** No corrompe datos: el proceso muere antes de
escribir y su salida no es cero, luego el padre lo ve. Pero entrena a
leer *«a veces pasa»* como ruido, y este repositorio ya escribió que un
defecto intermitente en un guard es peor que no tener guard.

### 2. `tests.total` de B3 declaraba 18 tests donde el árbol tiene 12

Registrado, **no corregido**: arreglarlo es medir B3, y un bloque que
corrige la contabilidad de otro sin medirlo es el bloque que inventa
cifras. Severidad baja, prioridad baja.

### 3. La política de `.pipelinek/`

Sin tocar. La instrumentación de B4 va en `scripts/` a propósito.

## Lo que este informe NO puede firmar

`phase.verify.complete` exige cuatro gates, y **dos de ellos no se
pueden evaluar** en este build:

```
$ sddk debt report /tmp/b4_debt.json
error: debt detection is not implemented in this build, so there is no
report to read and no gate to evaluate.
...
Until detection exists, the gates debt-severity-assigned and
debt-priority-assigned cannot pass, and the verify phase is blocked by
that fact rather than by a measurement that never happened.
```

Es un bloqueo **externo** —del framework SDDK, no de este repositorio—
y ya estaba documentado el 2026-09-29 en
`evidence/blocker-B4-debt-report-context.md`, cuando la herramienta
producía verde falso; ahora se niega, que es mejor pero igual de
bloqueante.

`debt-severity-assigned` y `debt-priority-assigned` quedan **sin
evaluar**, y no se falsean. La deuda de la sección anterior está
escrita aquí con su severidad y su prioridad, que es lo que esos gates
pedirían hacer, pero la firma es del gate y no de este documento.

Por eso el ciclo queda en `verify` con `block-condition-met` evaluado y
registrado, y no en `CLOSED`: el trabajo está entregado, certificado y
etiquetado, y el estado dice exactamente por qué no se puede seguir.
