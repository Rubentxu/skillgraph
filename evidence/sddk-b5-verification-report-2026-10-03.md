# verification-report — B5

Ciclo `p-b7740b96d79ec013/b5` · transición `phase.verify.complete`.

## Veredicto por requisito

| | Requisito | Cómo se midió | Resultado |
|---|---|---|---|
| R1 | el diff se **calcula**, no se lee | misma propuesta, dos planes → diffs distintos | **CUMPLE** |
| R2 | el cambio se nombra por su efecto semántico | `ChangeSubject` contra el vocabulario del roadmap | **CUMPLE** |
| R3 | las 7 preguntas del roadmap tienen respuesta | un campo por pregunta, por introspección del tipo real | **CUMPLE** |
| R4 | el parche está tipado | AST: `operations` declara `PatchOp`, y la unión cuadra con las clases del árbol | **CUMPLE** |
| R5 | el diff es **derivado** | propuesta que miente → discrepancia; propuesta coherente → ninguna | **CUMPLE** |
| R6 | el diff es una **etapa** del gate | `apply_expansion` rechaza el diff de otro plan, de otra revisión y de contenido falseado | **CUMPLE** |

## El criterio de aceptación, y quién lo decía

> Que toda evolución estructural significativa tenga una representación
> comparable, y que el diff sea **semántico**.

**Antes de escribir nada**, `scripts/measure_b5_graph_diff.py`: **6 de 6
preguntas abiertas**, y la que lo resumía era

```
GraphExpansionProposal.operations: tuple[object, ...]
```

**Ahora**, el mismo instrumento: **0 de 5 en alcance** (P6 sigue
registrada fuera de alcance) y salida **0**.

Y el test que lo ejecuta está en la suite: si el hueco volviera, se
pondría rojo con el veredicto del propio instrumento.

## R5, el guard que más importa

`GraphDiff` lleva dos conjuntos de capacidades y no es redundancia:

- `required_capabilities` — lo que las operaciones **producen**.
- `declared_capabilities` — lo que la propuesta **dice**.

| | declarado | derivado | coherente |
|---|---|---|---|
| propuesta que miente | `('sg.declarada',)` | `('sg.real',)` | **no** |
| propuesta coherente | `('sg.real',)` | `('sg.real',)` | **sí** |

La segunda fila es el contrasalto: un guard que siempre pita no mide.

## Mutaciones

`scripts/mutate_b5_graph_diff.py` — **8/8 cazadas, 0 sondas inválidas**,
árbol restaurado byte a byte verificado por `git diff`.

### Las tres que encontraron agujeros reales

No fueron sondas malas. Fue la red la que estaba incompleta, y eso es
lo que un harness de mutación sirve para.

- **M5 no fue cazada dos veces.** La primera quitaba el `sorted()` de
  `to_dict` y **no podía fallar**: el constructor ya entregaba tuplas
  ordenadas, luego la propiedad era **vacua**. La segunda lo quitaba del
  constructor y tampoco — y ese es el hallazgo: la garantía está puesta
  **dos veces**, luego no se rompe quitando una. Es la misma clase que la
  M6 de B4, **segunda vez en dos bloques consecutivos**.
- **M7** puso `reversible=True` fijo y nadie la cazó porque **ningún
  test** afirmaba que la séptima pregunta dependiera del plan de
  rollback.
- **M8** puso `esperado = diff`, con lo que la comparación se vuelve
  `diff != diff`. **No la cazó nadie** porque la huella salta *antes* y
  los tres tests de R6 usaban un diff bien calculado: la capa de
  recálculo **no se ejecutaba nunca**. Un guard que solo se ejercita por
  el camino bueno no sabe si el malo está cerrado.

**Y un error propio del harness, de la misma clase que caza:** la sonda
de dos sitios se aplicaba a medias porque el bucle usaba la primera
sustitución y descartaba la segunda. Una sonda aplicada a medias se
contaría como victoria. Ahora se comprueba que **ambos** sitios quedan
mutados antes de contar.

## El instrumento, y las tres veces que mintió

Un medidor que miente es peor que no tener medidor.

1. **P1 y P5 daban «cerrado»** porque `ChangedFile` casa con *«change»* —
   y es un cambio de **fichero de git**, con `path` y `old_blob_sha`.
   Afirmaba que el diff contestaba las siete preguntas sin mirar un campo.
2. **P3 devolvía lista vacía** por una ruta mal escrita
   (`src/skillgraph/skillgraph/governance/…`). No era una medida: era un
   cero impreso. Ahora **falla ruidosamente** si la derivación no
   encuentra funciones, y deriva 19.
3. **P4 buscaba el vocabulario en el nombre de la clase**, cuando vive
   en la enumeración, y `X: TypeAlias = Literal[…]` lo pone en el
   **valor**, no en la anotación.

**Y se comprobó que sabe volverse verde:** con un `GraphDiff` real
inyectado, P1/P4/P5 se cierran y P2/P3/P6 siguen abiertos.

## La extracción, decidida con una medición

| | `graph_expansion.py` |
|---|---|
| antes de B5 | 787 LoC (98 % del presupuesto) |
| al integrar el diff | **901** — el guard de god file lo puso rojo |
| tras mover `record_rejection` | **785** |

`record_rejection` —persistir un rechazo es escribir un registro de
auditoría, no expandir un grafo— se mudó a `expansion_audit.py` y **se
reexporta**: mover el código no rompe la ruta de importación.

La salida no fue recortar prosa. La razón por la que la prosa era larga
es que el razonamiento no cabía allí.

## Certificación

| Corrida | Resultado |
|---|---|
| 1 | 3025 passed, 3 skipped, **2 failed** |
| 2 | 3026 passed, 3 skipped, **1 failed** |
| 3 (árbol quieto) | **3027 passed, 3 skipped, 0 failed** |

- La **1** fallaba por `tests.total` desactualizado y su gemelo de
  convergencia de B0, diciendo lo mismo. Cifra correcta: **3030**, escrita
  **después** del run. El `+34` está desglosado: **28** de B5 y **6** de
  `test_wi47_broad_except_guard.py`, que **parametriza sobre la lista de
  módulos** y generó tres casos por cada módulo nuevo. Segunda vez en dos
  bloques que ocurre.
- La **2** fallaba por el release en vuelo: la suite corrió mientras se
  escribían los campos de versión. No es un defecto, es una carrera.
- La **3**, sobre árbol quieto, es la que certifica.

## Deuda registrada, no abierta

1. **Las cuatro vistas** (P6 del medidor). Siguen abiertas y **no bajan
   el veredicto**: son deuda, no un olvido. Construirlas sin el diff
   sería construirlas sin criterio.
2. **El diff sigue siendo opcional.** El roadmap lo pide para *«todo
   cambio estructural importante»* y el default `None` deja pasar las
   propuestas pequeñas. Cerrarlo exige saber qué es «importante»
   medido sobre propuestas reales, no decidido de antemano.
3. **`tests.total` de B3** declaraba 18 donde el árbol tiene 12. No se
   corrige sin medir B3.

## Lo que este informe NO puede firmar

`phase.verify.complete` exige cuatro gates. `tests-pass` y
`policy-compliant` se evaluan con digest real de su propia salida. Los
dos de deuda **no se pueden evaluar**:

```
$ sddk debt report /tmp/b5_debt.json
error: debt detection is not implemented in this build, so there is no
report to read and no gate to evaluate.
```

Es un bloqueo **externo**, del framework, documentado desde el
2026-09-29. Los gates quedan registrados como **failed**, no como passed
ni waived: pasarlos en verde sería exactamente el defecto que la
herramienta describe.

Por eso el ciclo queda en `verify`, como quedó `b4`, y no en `CLOSED`: el
trabajo está entregado, certificado y etiquetado, y el estado dice
exactamente por qué no puede seguir.
