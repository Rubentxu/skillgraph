"""``SqliteOutcomeTraceRepository``: trazas de resultado y sus enlaces.

R1 partio `knowledge_repository.py` —que estaba en **895 LoC**, por encima
del umbral de 800— **por responsabilidad, no por tamaño**.

# POR QUE ESTE GRUPO Y NO OTRO

Un `OutcomeTrace` son **1+N sentencias en una transaccion**: una fila de
`outcome_traces` mas un enlace por cada `claim_refs` y `evidence_refs`, y el
metodo lo dice en su docstring —*«un fallo a mitad de las 1+N sentencias no
deje un `outcome_traces` orphan»*. Esa es una unidad transaccional con su
propio invariante, y un invariante con su propio fichero se lee sin tener que
saber que mas hay alrededor.

Se extrajo **verbatim**: el cuerpo no se reescribio ni se «mejoro». Un
refactor que reescribe el SQL mientras mueve el codigo produce dos cambios a
la vez, y cuando algo falla no se sabe cual de los dos fue.

# LO QUE ESTE COMPONENTE NO HACE

No decide nada. No conoce el grafo, ni las ventanas de vigencia, ni el
presupuesto de contexto. Solo escribe y enlaza filas, y deja que el dominio
opine sobre ellas.
"""

from __future__ import annotations

import sqlite3

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.graph import OutcomeTrace
from skillgraph.platform.storage import Storage


class SqliteOutcomeTraceRepository:
    """Trazas y enlaces. Sin estado propio: comparte la conexión."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._storage._conn

    def record_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace: OutcomeTrace,
    ) -> None:
        """Registra un OutcomeTrace y sus enlaces (claim/evidence en orden).

        Idempotente por `trace_id` y por `(trace_id, link_kind, link_id)`.

        Usa `_atomic()` (BEGIN/COMMIT/ROLLBACK explicitos) en vez de
        `_tx()` para garantizar que un fallo a mitad de las 1+N
        sentencias no deje un `outcome_traces` orphan (sin sus
        `outcome_trace_links`). H9-LIMITACION-7 V4.
        """
        with self._storage._atomic() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO outcome_traces
                    (trace_id, tenant_id, project_id, kind, name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    tenant_id,
                    project_id,
                    trace.kind,
                    trace.name,
                    trace.created_at,
                ),
            )
            # Enlazar claims y evidences preservando orden via `position`.
            for position, claim_id in enumerate(trace.claim_refs):
                cur.execute(
                    """
                    INSERT OR REPLACE INTO outcome_trace_links
                        (trace_id, link_kind, link_id, position)
                    VALUES (?, 'claim', ?, ?)
                    """,
                    (trace.trace_id, claim_id, position),
                )
            for position, evidence_id in enumerate(trace.evidence_refs):
                cur.execute(
                    """
                    INSERT OR REPLACE INTO outcome_trace_links
                        (trace_id, link_kind, link_id, position)
                    VALUES (?, 'evidence', ?, ?)
                    """,
                    (trace.trace_id, evidence_id, position),
                )

    def link_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace_id: str,
        link_kind: str,
        link_id: str,
        position: int,
    ) -> None:
        """Adjunta un enlace adicional a un trace. `link_kind` ∈
        {'claim', 'evidence', 'relation'}."""
        if link_kind not in {"claim", "evidence", "relation"}:
            raise ValidationError(
                f"link_kind invalido: {link_kind!r} (esperado claim/evidence/relation)"
            )
        with self._storage._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO outcome_trace_links
                    (trace_id, link_kind, link_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (trace_id, link_kind, link_id, position),
            )


__all__ = ["SqliteOutcomeTraceRepository"]
