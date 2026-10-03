# design — B5, Graph Diff Gate

Ciclo `p-b7740b96d79ec013/b5` · fase `design`.

## La decisión que el bloque entero sostiene

**`GraphDiff` lleva DOS conjuntos de capacidades, y no es redundancia.**

- `required_capabilities` — lo que las operaciones del parche
  **producen**, derivado del plan.
- `declared_capabilities` — lo que la propuesta **dice**, copiado de
  `capabilities_needed`.

Que discrepen no es un defecto del diff: es **el resultado**. Un diff que
devolviera la declaración sería un eco con mejor tipografía, y un gate que
comprueba ecos no mira nada. La sonda M1 sustituye el derivado por el
declarado y la red lo cazó.

Es el mismo criterio con el que B4 decidió que `status` **no** vive en
`Brick`: si el portador de la verdad lo declara, la mitad observada deja
de estar observada. Aquí el portador es la propuesta, y la mitad
verificada es su parche.

## La segunda decisión, y la que salió de una medición

**`base_fingerprint`: SHA-256 de una serialización estable del plan.**

No estaba en el diseño. La primera versión llevaba solo `base_revision`,
y se rompió de una forma que solo se ve ejecutando: **con el parche
vacío el diff sale vacío sea cual sea el grafo**, luego un diff
calculado sobre otro plan pasaba por suyo siempre que coincidiera la
revisión. Y dos estados pueden compartir revisión.

Sin la huella, *conectar ≠ contenido* (WI-102) se queda en buena
intención. La huella es lo que ata el diff a su estado.

**La serialización ordena antes de serializar.** Un `WorkflowPlan` es un
valor y dos planes con el mismo contenido pueden traer los nodos en otro
orden; sin ordenar, la huella dependería del orden de construcción. Es el
error de B3 (`tuple(set)`, ocho órdenes en ocho corridas) aplicado a algo
de lo que ahora depende un gate.

## La tercera: R6 en tres capas, y por qué el diff es opcional

`apply_expansion` acepta el diff y lo rechaza si no es de esa
aplicación, comprobando **revisión, huella y recálculo**.

La tercera capa parece redundante con las dos primeras, y no lo es: las
dos primeras la pasan un `GraphDiff` **construido a mano** con la
revisión y la huella correctas y el contenido falseado. Sin el recálculo,
basta con construir un diff plausible. La sonda M8 lo expone — y no la
cazó nadie hasta que se añadió un test que falsea el contenido con
revisión y huella correctas.

**El default es `None`, y no un diff sintético.** Romper las llamadas
existentes no es una opción; un diff inventado sería **peor** que
ninguno, porque diría que se ha comprobado algo que no se ha comprobado.
Lo que no se permite es que un diff *equivocado* pase.

## La cuarta: la extracción, decidida con una medición

Al integrar el diff, `graph_expansion.py` pasó de 787 a **901** LoC y
el guard de god file lo puso rojo.

La salida **no** fue recortar prosa. La razón por la que la prosa era
larga es que el razonamiento no cabía allí, y por eso vive en
`graph_diff.py` y en `expansion_audit.py`.

`record_rejection` —persistir un rechazo es escribir un registro de
auditoría, no expandir un grafo— se mudó a `governance/expansion_audit.py`
y **se reexporta** desde `graph_expansion`, para que mover el código no
rompa la ruta de importación de quien lo importaba. Queda en 785.

Es la misma lección que ADR-0022 y WI-68: *el problema no era
concentración de responsabilidad sino de fichero*.

## Lo que NO se decide aquí

**Las cuatro vistas.** Son cuatro proyecciones tipadas sobre recursos y
relaciones comunes. Construirlas sin el diff sería construirlas sin
criterio, y este bloque ya midió que el diff es la única forma de
saber si una proyección miente. Quedan registradas y **visibles** en el
medidor.

**Que el diff sea obligatorio para toda propuesta.** El roadmap lo pide
para *«todo cambio estructural importante»*, y hoy el default `None`
deja pasar las pequeñas. Cerrar eso es trabajo con su propia
exploración: requiere saber qué es «importante» medido sobre propuestas
reales, no decidido de antemano.

## Los contrasaltos, y por qué están

Un guard que solo se ejercita por el camino bueno no sabe si el malo
está cerrado. Los que importan:

- El **medidor** recibe un `GraphDiff` de verdad y debe cerrarse. Un
  instrumento que solo sabe decir «abierto» no es un instrumento.
- El **test de R6** usa un diff bien calculado *y* uno con revisión y
  huella correctas pero contenido falseado.
- **`es_coherente()`** distingue el caso bueno del malo: una propuesta
  coherente no produce discrepancia. Un guard que siempre pita no mide.
- **R2** mide el `Literal` cerrado contra el vocabulario del roadmap, no
  contra una copia escrita en el test.
