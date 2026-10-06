"""B27 — Los conflictos son CONSULTABLES y ESTABLES.

**QUE HACE ESTE COMPONENTE Y POR QUE NO ESTA EN `knowledge_claims.py`.** El
conflicto no es un claim: es una RELACION entre claims, y la consulta la hace
sobre filas de las que ninguna otra capa es duena. Vive aparte porque tiene su
contrato —inmutable y ordenado— y porque su error es propio.

# LA MEDIDA QUE DIO NOMBRE AL BLOQUE

`scripts/measure_b27_conflictos.py` → **3/5 ABIERTAS**, y las dos cerradas lo
son **a favor de un enunciado exagerado**:

    P1  CERRADA  dos fuentes que dicen cosas distintas -> 2 filas, COEXISTEN
    P2  CERRADA  misma fuente, hechos opuestos       -> 1 fila, SE PISA
    P3  ABIERTA  nadie dice que dos afirmaciones se contradigan
    P4  ABIERTA  el overwrite no avisa a quien escribe

La fila del roadmap dice que «dos claims incompatibles se pisan», y eso solo es
cierto con la **misma** fuente y la **misma** revision: el `UNIQUE` de `claims`
es `(subject_entity_id, predicate, source_id, checked_at_revision)` y lleva
`source_id` dentro, luego dos herramientas distintas ya coexistian de sobra.

Lo que faltaba era la mitad que si es cierta del enunciado —«y no hay forma de
saberlo»— y esa mitad es este fichero.

# DOS COSAS QUE ESTE COMPONENTE NO HACE, Y SON EL LIMITE DEL BLOQUE

1. **NO RESUELVE.** Ordena afirmaciones contradictorias, no dice cual tiene
   razon. Eso es B28, y es por intencion de consulta: la respuesta correcta a
   «¿cual creo?» depende de para que se pregunta.
2. **NO BORRA.** Un conflicto no es un error a limpar: son dos afirmaciones
   que ambas tienen fuente. Lo que las resolvera son las ventanas de vigencia
   de B29.

Borrarlas aqui seria decidir con una regla que no tiene en cuenta al que
pregunta, y quien decidiria seria este componente, que no lo sabe.
"""

from __future__ import annotations

import json
import sqlite3

from skillgraph.knowledge.graph import Conflicto
from skillgraph.platform.knowledge_mappers import row_to_claim as _row_to_claim
from skillgraph.platform.storage import Storage

__all__ = ["SqliteConflictRepository"]


def _valor_de(row: sqlite3.Row) -> tuple[str, ...]:
    """La «forma» del objeto de un claim, como tupla comparable.

    **POR QUE UNA TUPLA Y NO EL JSON TAL CUAL.** Dos literales son distintos si
    su valor lo es, y `json.dumps(..., sort_keys=True)` ya normaliza el orden de
    las claves, luego el string sirve. Pero un objeto que es una **referencia a
    entidad** no vive en `object_literal_json`: vive en `object_entity_id`, y en
    ese caso la columna del literal es el marcador `''`.

    Sin esta normalizacion, dos claims que dicen «A usa B» y «A usa C» tendrian
    los dos `''` en el literal, **serian iguales**, y el conflicto no se
    detectaria. Es el caso que B25 abrio y el que un `SELECT` ingenuo no ve.
    """
    ref = row["object_entity_id"]
    return ("entity", ref) if ref else ("literal", row["object_literal_json"])


class SqliteConflictRepository:
    """Conflictos entre afirmaciones. Comparte `_storage` con la fachada."""

    __slots__ = ("_storage",)

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._storage._conn

    def conflicts_for(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
    ) -> tuple[Conflicto, ...]:
        """Los conflictos de un sujeto, **ordenados de forma estable**.

        Args:
            tenant_id: tenant de la consulta.
            project_id: proyecto. **Filtra**: dos proyectos no se contradicen
                entre si, y meterlos seria ruido con apariencia de señal.
            subject_entity_id: el sujeto cuyas afirmaciones se comparan.

        Returns:
            Una tupla de `Conflicto`, **vacia si no hay ninguno**. Una sola
            afirmacion NO es conflicto: no se contradice nadie, y llamarle
            conflicto seria el equivalente de B25 — un sistema que confunde
            «coexisten» con «se oponen».
        """
        rows = self._conn.execute(
            """
            SELECT * FROM claims
            WHERE subject_entity_id = ? AND tenant_id = ? AND project_id = ?
            ORDER BY predicate ASC, claim_id ASC
            """,
            (subject_entity_id, tenant_id, project_id),
        ).fetchall()
        if not rows:
            return ()

        por_predicado: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            por_predicado.setdefault(row["predicate"], []).append(row)

        conflictos: list[Conflicto] = []
        for predicado in sorted(por_predicado):
            grupo = por_predicado[predicado]
            if _tiene_valores_distintos(grupo):
                conflictos.append(
                    Conflicto(
                        subject_entity_id=subject_entity_id,
                        predicate=predicado,
                        afirmaciones=tuple(
                            _row_to_claim(r, [], json)
                            for r in sorted(grupo, key=lambda r: r["claim_id"])
                        ),
                    )
                )
        return tuple(conflictos)


def _tiene_valores_distintos(grupo: list[sqlite3.Row]) -> bool:
    """¿Este grupo de afirmaciones se contradice entre si?

    **EL CONTRA SALTO VIVE AQUI, Y ES LO QUE IMPIDE QUE B27 SEA RUIDO.** Un
    grupo es conflicto cuando hay **DOS VALORES DISTINTOS**, no cuando tiene
    varias filas: tres fuentes que dicen todas `true` NO se contradicen, y
    llamarlas conflicto haria que `conflicts_for` devolviera casi todo.

    Y el detalle que hace que dos referencias a entidad distintas SI se detecten
    como conflicto: la comparacion es sobre `_valor_de`, no sobre
    `object_literal_json` a secas.
    """
    return len({_valor_de(r) for r in grupo}) > 1
