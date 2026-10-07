"""Puerto de registro de revisiones: el contrato que consume el core.

# POR QUÉ ESTE PUERTO EXISTE

Hasta R0, `knowledge/graph.py` publicaba dos helpers que hablaban SQL:

    def _sigiente_revision(cur: Any, revision: str) -> int: ...
    def seq_de(cur: Any, revision: str | None) -> int | None: ...

Y lo grave no era solo que el dominio hablara SQL: **`platform/` los
importaba** (`knowledge_claims.py`, `knowledge_conflicts.py`), luego la
frontera estaba **invertida**. El dominio servía de utilidad de base de
datos para el adapter.

Aquí va el contrato; la implementación es
`skillgraph.platform.revision_registry.SqliteRevisionRegistry`.

# LA SEMÁNTICA, QUE NO SE INVENTA: ES LA DE B29

`seq` es **el orden en que ESTE store aprendió de las revisiones**. No es
ascendencia de git —comparar SHAs es lexicográfico y arbitrario (`rev10 <
rev9`)—, que es lo que declara la nota de `revision_registro` en
`platform/schema.py`. La ascendencia real es `GitHistory`, que es B32.

# POR QUÉ `registrar` ES IDEMPOTENTE Y POR QUÉ NO PUEDE NO SERLO

Reingerir el mismo envelope (idempotencia de B26) llega aquí con la misma
revisión. Si `registrar` creara una fila nueva cada vez, el `seq` de una
revisión dependería del número de veces que se vio, y dos almacenes con el
mismo conjunto de revisiones darían órdenes distintos —que es exactamente
la propiedad de B27 que este puerto no puede romper por el camino.

Por eso `registrar` es *get-or-create*: devuelve el `seq` existente si lo
hay, y solo asigna uno nuevo la primera vez.

# LO QUE ESTE PUERTO NO HACE

No ordena revisiones entre almacenes distintos, y no sabe si dos SHAs tienen
relación de ancestro. Eso es `GitHistory` (B32). Este puerto solo sabe
contar en qué orden este store las aprendió, que es menos y es exacto.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RevisionRegistry(Protocol):
    """Orden de aprendizaje de revisiones, de un solo almacén.

    Consumido por la capa de conocimiento a través de la comparación de
    ventanas de vigencia (B29). Sin disco, sin red y sin reloj desde el
    punto de vista del que lo usa: quien habla SQLite es la
    implementación.
    """

    def registrar(self, revision: str) -> int:
        """Devuelve el `seq` de `revision`, creándolo la primera vez.

        Idempotente: llamarla dos veces con la misma revisión devuelve el
        mismo `seq` y **no** crea una segunda fila.
        """
        ...

    def seq_de(self, revision: str | None) -> int | None:
        """El `seq` de `revision`, o `None` si este store no la ha visto.

        **Una revisión desconocida NO es un error: es que no hay nada que
        decir de ella.** Y se distingue de «hay claims pero ninguno en esa
        revisión» precisamente porque una revisión desconocida no aparece
        en el registro y por tanto no tiene `seq` con el que comparar.
        """
        ...
