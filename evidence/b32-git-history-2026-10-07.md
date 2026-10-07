# B32 — GitHistory: lo que se pudo responder ANTES de escribir una línea

Fecha: 2026-10-07 · Medición: `.pipelinek/b32_measure.py` (ejecutada sobre una base real)

La fila del roadmap dice: **«No se puede responder cuándo cambió una relación
ni por qué»**. Lo que se midió antes de implementar nada:

```
    ==========================================================================
    
    [esquema] ¿la tabla guarda el SHA y hay indice por el?
      columnas git_* en sources: ['git_commit_sha', 'git_tree_sha']
      indices sobre sources: ['sqlite_autoindex_sources_1', 'idx_sources_project']
    
    [preguntas] sobre una base con un claim de verdad
      claim registrado: c-1
      P1 claim -> source (el commit del que vino): SI (s-1)
      P2 commit -> claims (al reves): SI (['c-1'])
      P3 ascendencia de un commit (padre, y el padre del padre): NO (devuelve None)
      P4 claims que nacieron DESPUES de un commit: NO (devuelve None)
      P5 orden entre dos revisiones-commit: NO (devuelve None)
      P6 por que se afirmo el claim (mas alla del source_id): NO (devuelve None)
    
    [el otro reloj] revision_registro, que NO es git
      revision_registro: [(1, 'abc123'), (2, 'commit-sha-real-1234'), (3, 'otro-commit-9999')]
      el MISMO sha registrado dos veces sigue siendo UN seq: 'abc123' -> seq [1]
      esto es ORDEN DE OBSERVACION local, no ascendencia. Un reloj que
      no puede decir si A es padre de B, solo que A se vio antes que B.
      El nombre del puerto lo declara; por eso B32 necesita OTRO reloj.
    
    [fuera de la base] ¿hay un puerto de ascendencia en el codigo?
      puertos de revision: ['Protocol', 'RevisionRegistry', 'annotations', 'runtime_checkable']
      GitHistory definido: False
      CommitHistory definido: False
      CommitLineage definido: False
    
    [fuera de la base] ¿el nucleo importa git?
      dulwich: disponible (dependencia principal)
    
```

## Lo que se cierra en B32, y lo que NO

| mitad | qué es | quién la responde |
|---|---|---|
| **el CUÁNDO** | ascendencia real de commits | `ports.git_history.GitHistory` |
| **el DESDE QUÉ** | qué afirmaciones salieron de este commit | `claims_desde_commit` |
| **el POR QUÉ** | intención sobre la evidencia | **no** — es de B33/B34 |

La tercera fila es la que hay que leer dos veces: B32 **no cierra** el
«ni por qué». Implementar aquí un `por_que` de un campo sería escribir el
contrato de dos bloques siguientes sin haberlos discutido, y un guard
`test_que_no_existe_por_que` lo ata para que nadie lo escriba de contrabando.

## El dato que salió del propio `grep`

MEDIDO: `git_commit_sha` **no tenía ningún llamador en `src/`**. Nadie había
hecho la pregunta nunca, no desde el producto. No faltaba el índice —no
faltaba la pregunta—. Por eso la fila del roadmap es cierta y el trabajo es
de creación, no de reparación.

## Los dos relojes, que no se mezclan

```
    [el otro reloj] revision_registro, que NO es git
      revision_registro: [(1, 'abc123'), (2, 'commit-sha-real-1234'), (3, 'otro-commit-9999')]
      el MISMO sha registrado dos veces sigue siendo UN seq: 'abc123' -> seq [1]
      esto es ORDEN DE OBSERVACION local, no ascendencia. Un reloj que
      no puede decir si A es padre de B, solo que A se vio antes que B.
```

`RevisionRegistry.seq` es el orden en que **este store** aprendió de las
revisiones; `GitHistory` es la ascendencia real. Un puerto que mezclara los dos
volvería a ser el mapa único que contesta dos preguntas — el defecto que B3
denunció a propósito. `test_ambos_relojes_siguen_siendo_protocolos_distintos` lo vigila.

## Lo que la medición NO puede responder, y se dice

El grafo de commits es PARCIAL: dos commits de ramas distintas no tienen orden
entre ellos. Por eso el contrato ofrece `es_ancestro(a, b) -> bool` y **no**
`ordena(a, b) -> int`, que prometería un número para algo que no tiene
dirección. Y `False` significa «no se puede demostrar», no «es posterior».
