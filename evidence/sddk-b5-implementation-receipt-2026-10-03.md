# implementation-receipt — B5

Ciclo `p-b7740b96d79ec013/b5` · transición `phase.build.complete` ·
requisito `implementation-receipt`.

## Qué entrega

La etapa `Diff` de la secuencia del gate
`Proposal → Diff → Policy → Decision → Evidence → Apply`. El roadmap la
pide y no estaba: lo que había era un parche sin comparar.

## Lo que estaba medido antes de escribir una línea

Con `scripts/measure_b5_graph_diff.py`, versionado en `scripts/` y no
en `.pipelinek/` (backlog `bl-bl-01M41DFZEZ0003882TZNP7NPM0`):

```
6 de 6 preguntas abiertas
GraphExpansionProposal.operations: tuple[object, ...]
19 funciones de nivel superior en graph_expansion.py, 0 de diff
```

Un saco de operaciones sin tipar. Las tres clases —`AddNode`,
`AddTransition`, `RemoveTransition`— ya existían, y el comentario del
propio código decía *«PatchOp es ADT cerrado»* desde antes de que
existiera un `PatchOp` que cerrara nada. Sin él, nada que quisiera
preguntarle al parche qué invalida tenía por dónde mirar.

## Commits

| | |
|---|---|
| Antes | `645c3b8` |
| Después | commit de release + post-tag |
| Commits | **3** (`feat`, `build(release)`, `chore(release)`) |
| Etiqueta | `v0.25.0` (anotada), MINOR por `0/1/0/2/0` |

```
e74177a  feat(governance): el diff del grafo deja de ser un parche sin comparar
ecda4b1  build(release): v0.25.0
HEAD     chore(release): mantenimiento post-tag de v0.25.0
```

## Lo entregado

- `governance/graph_diff.py` — `GraphDiff` y `GraphChange`, frozen y
  con `slots`. `ChangeSubject` es un `Literal` **cerrado** sobre las
  siete clases de cambio del roadmap, y los nueve campos responden a
  las siete preguntas que el roadmap le exige a un diff.
- `diff_graph(plan, proposal)` — **calcula** el cambio comparando el
  plan que hay con lo que la propuesta propone.
- `base_fingerprint` — SHA-256 de una serialización estable del plan.
- `apply_expansion(..., diff=...)` — **rechaza** el diff que no sea de
  esa aplicación, en tres capas: revisión, huella y recálculo.
- `operations: tuple[PatchOp, …]`, con `es_patch_op` comprobándolo en
  runtime y no solo en la anotación.
- `governance/expansion_audit.py` — `record_rejection`, mudado y
  reexportado.

## El hallazgo: el diff tiene que poder ver la mentira

`GraphDiff` lleva **dos** conjuntos de capacidades:

- `required_capabilities` — lo que las operaciones **producen**.
- `declared_capabilities` — lo que la propuesta **dice**.

Que discrepen no es un defecto del diff: es el resultado. Un diff que
devolviera la declaración sería un eco con mejor tipografía, y un gate
que comprueba ecos no mira nada.

## Verificación

| | |
|---|---|
| Tests nuevos | **28** en `tests/test_b5_graph_diff.py` |
| Mutaciones | **8/8 cazadas**, 0 sondas inválidas |
| Restauración | byte a byte, verificada por `git diff` |
| `graph_expansion.py` | 787 → 901 (por el diff) → **785** (tras la extracción) |
| Ruff | `check` y `format` limpios |

## Las tres sondas que encontraron agujeros reales

No fueron sondas malas. Fue la red la que estaba incompleta.

- **M5 no fue cazada dos veces.** La primera quitaba el `sorted()` de
  `to_dict` y no podía fallar: el constructor ya entregaba tuplas
  ordenadas, luego la propiedad era **vacua**. La segunda lo quitaba
  del constructor y tampoco — y ese es el hallazgo: la garantía está
  puesta **dos veces**, luego no se rompe quitando una. Es la misma
  clase que la M6 de B4, segunda vez en dos bloques consecutivos.
- **M7** puso `reversible=True` fijo y nadie la cazó porque **ningún
  test** afirmaba que la séptima pregunta dependiera del rollback.
- **M8** puso `esperado = diff`, con lo que la comparación se vuelve
  `diff != diff`. No la cazó nadie porque la huella salta **antes** y
  los tests de R6 usaban un diff bien calculado: la capa de recálculo
  no se ejecutaba nunca. Un guard que solo se ejercita por el camino
  bueno no sabe si el malo está cerrado.

**Y un error propio del harness, de la misma clase que caza:** la sonda
de dos sitios se aplicaba a medias porque el bucle usaba la primera
sustitución y descartaba la segunda. Una sonda aplicada a medias se
contaría como victoria. Ahora se comprueba que **ambos** sitios quedan
mutados antes de contar.

## La extracción se decidió con una medición

Al integrar el diff, `graph_expansion.py` pasó de 787 a **901** LoC y
el guard de god file lo puso rojo. La salida no fue recortar prosa: la
razón por la que la prosa era larga es que el razonamiento no cabía
allí, y por eso vive en `graph_diff.py` y en `expansion_audit.py`.
`record_rejection` —persistir un rechazo es escribir un registro de
auditoría, no expandir un grafo— se mudó y **se reexporta**, para que
mover el código no rompa la ruta de importación.

## Fuera de alcance, y visible

Las **cuatro vistas** del roadmap no existen. El medidor las mantiene
abiertas y **no las baja del veredicto**: son deuda registrada, no un
olvido. Construirlas sin el diff sería construirlas sin criterio.

## Orden imposible, y es la tercera vez en dos releases

1. El commit de release no puede pasar los hooks: la etiqueta tiene que
   existir antes de declararse (`AGENTS §12`) y una etiqueta listada
   tiene que existir en git.
2. El commit post-tag no puede pasar el hook del release governance:
   HEAD sigue *en* la etiqueta y `__version__` ya volvió a `.dev0`.
3. La entrada de `releases:` no se puede escribir en el commit de
   release porque el sha de ese commit no existe todavía. Se escribe en
   el post-tag, **con el sha real**.

Las tres se resuelven igual: **escribir cada campo cuando es cierto, no
antes.** Un `sha: PENDING` habría hecho pasar la forma del documento y
roto la verdad, que es justo lo que `test_sha_field_never_holds_prose`
existe para cazar.
