# exploration-report — B5, Graph Diff Gate

Ciclo `p-b7740b96d79ec013/b5` · fase `explore` · requisito
`exploration-report`.

## La pregunta del roadmap

> Que toda evolución estructural significativa tenga una representación
> comparable, y que el diff sea **semántico**. No un diff de YAML.
>
> Gate B5. Ningún cambio estructural importante ocurre sin
> `Proposal → Diff → Policy → Decision → Evidence → Apply`.

## Lo que había, medido

Con `scripts/measure_b5_graph_diff.py` —versionado en `scripts/` y no en
`.pipelinek/`— la medición dio **6 de 6 preguntas abiertas**:

| | Pregunta | Respuesta del árbol |
|---|---|---|
| P1 | ¿tipo que represente un cambio comparable? | `NINGUNO` |
| P2 | ¿el parche está tipado? | `tuple[object, ...]` |
| P3 | ¿el paso `Diff` entre propuesta y política? | 19 funciones en `graph_expansion.py`, **0** de diff |
| P4 | ¿el cambio se nombra por su efecto semántico? | `NINGUNO` |
| P5 | ¿responde a las 7 preguntas del roadmap? | **0 de 7** |
| P6 | ¿las cuatro proyecciones tipadas? | **0 de 4** |

## El instrumento se corrigió tres veces antes de servir

Un medidor que miente es peor que no tener medidor, y este mentía:

1. **P1 y P5 daban «cerrado»** porque `ChangedFile` casa con *«change»* en
   el nombre — y `ChangedFile` es un cambio de **fichero de git**, con
   `path` y `old_blob_sha`, que no tiene nada que ver con un grafo. La
   primera versión afirmaba que el diff contestaba las siete preguntas sin
   mirar un solo campo.
2. **P3 devolvía lista vacía** porque construía la ruta
   `src/skillgraph/skillgraph/governance/…`. El `if ruta.exists()` se
   tragaba el fallo y se leía como *«no hay ninguna función de diff»*. No
   era una medida: era una ruta mal escrita imprimiendo un cero. Ahora
   **falla ruidosamente** si la derivación no encuentra funciones en un
   fichero que se sabe que las tiene, y deriva 19.
3. **P4 buscaba el vocabulario del roadmap en el NOMBRE de la clase.**
   No puede encontrarlo, porque el significado no está en el nombre: está
   en la enumeración que el campo declara. Y `X: TypeAlias = Literal[…]`
   pone el `Literal` en el **valor**, no en la anotación, luego había que
   recorrer los dos.

**Y se comprobó que sabe volverse verde.** Con un `GraphDiff` real
inyectado, P1, P4 y P5 se cierran y P2, P3 y P6 siguen abiertos: el
medidor discrimina en las dos direcciones, que es lo que lo hace
medidor.

## La forma exacta del hueco

Una línea:

```
GraphExpansionProposal.operations: tuple[object, ...]
```

Un saco de operaciones sin tipar. Las tres clases ya existían —
`AddNode`, `AddTransition`, `RemoveTransition`— y el comentario del
propio código decía *«PatchOp es ADT cerrado»* **desde antes de que
existiera un `PatchOp` que cerrara nada**. Sin él, nada que quisiera
preguntarle al parche qué invalida tiene por dónde mirar: `object`
admite cualquier valor, luego no restringe nada.

Y sin representación del cambio, la secuencia del gate es
`Proposal → Policy → Decision → Evidence → Apply`. **No hay etapa
`Diff`.** No es un detalle de la política: no está.

## La precondición que B3 dejó satisfecha

B3 dejó escrito que *«por qué B5 importa aquí: el Graph Diff Gate se
apoya en `GraphExpansion`. Con I4 rechazando toda propuesta con
dependencia nueva, B5 nacía con el gate cerrado — no por decisión, sino
porque el invariante no tenía fuente»*.

B3 arregló I4 partiéndolo en dos vistas —`capabilities` y `references`—
con dos fuentes distintas. **La precondición de B5 está satisfecha y
verificada.** Ese era el riesgo que B3 registries, y no se materializó.

## Qué queda fuera, y por qué

**Las cuatro vistas (P6).** El roadmap las presenta como el marco sobre
el que el diff es semántico *«sobre el mismo sistema»*, y ninguna existe.
Es trabajo de su propio: cuatro proyecciones tipadas sobre recursos y
relaciones comunes, que construidas sin tener antes un diff contra el que
comprobarlas serían construidas sin criterio. Se registra como hueco
abierto, y el medidor lo sigue diciendo —`P6` no se apaga, y **no baja el
veredicto** porque es deuda, no un olvido.

## El riesgo que el bloque asume

Que un diff semántico es **más restrictivo** que un diff textual, y que
una propuesta que hoy se aceptaría podría no tener diff. Es el coste
correcto: el gate dice *«ningún cambio estructural importante ocurre sin
diff»*, y un diff que acepta cualquier cosa no es un diff.
