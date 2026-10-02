"""SqlitePromotionRepository: cluster promotions de WI-56 (ADR-0016).

Outbox de promocion entre proyectos (H7): tablas `promotion_outbox`.
Quinto corte del estrangulamiento del god-module `storage.py`.

Los contextos transaccionales ``_tx`` se resuelven via el ``Storage``
dueno del schema (resolucion tardia: preserva el monkeypatching de
H9/H10 sobre Storage).
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from skillgraph.core.errors import IdentityConflictError, ValidationError
from skillgraph.platform.ports import StoredPromotion
from skillgraph.platform.row_mappers import _row_to_stored_promotion
from skillgraph.platform.storage import PROMOTION_STATUSES, Storage

if TYPE_CHECKING:
    pass


class SqlitePromotionRepository:
    """Componente del cluster promotions; comparte conexion con Storage."""

    __slots__ = ("_storage",)

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        """Conexion compartida con el ``Storage`` dueno del schema."""
        return self._storage._conn  # composicion interna acordada en ADR-0016

    def register_promotion(
        self,
        *,
        proposal_id: str,
        idempotency_key: str,
        tenant_id: str,
        source_project: str,
        target_catalog: str,
        knowledge_ref: str,
        payload: dict[str, Any],
    ) -> None:
        """Inserta una propuesta de promocion en el outbox (status=PENDING).

        Si `idempotency_key` ya existe, lanza `IdentityConflictError`
        (la promocion ya fue registrada; no se duplica).
        """
        import json as _json

        with self._storage._tx() as cur:
            existing = cur.execute(
                "SELECT proposal_id FROM promotion_outbox WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                raise IdentityConflictError(
                    f"Promocion duplicada: idempotency_key={idempotency_key!r} "
                    f"ya registrada como proposal_id={existing['proposal_id']!r}"
                )
            cur.execute(
                """
                INSERT INTO promotion_outbox
                    (proposal_id, idempotency_key, tenant_id, source_project,
                     target_catalog, knowledge_ref, payload_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    proposal_id,
                    idempotency_key,
                    tenant_id,
                    source_project,
                    target_catalog,
                    knowledge_ref,
                    _json.dumps(payload, sort_keys=True),
                ),
            )

    def get_promotion(self, proposal_id: str) -> StoredPromotion | None:
        """Devuelve la propuesta por id, o None si no existe.

        WI-38 (R1 strict): devuelve ``StoredPromotion`` (frozen + slots)
        en vez de ``dict[str, Any]``. El campo ``payload`` se deserializa
        en el DTO (no raw json).
        """
        row = self._conn.execute(
            "SELECT * FROM promotion_outbox WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_stored_promotion(row)

    def list_pending_promotions(self) -> list[StoredPromotion]:
        """Lista propuestas con status IN ('PENDING', 'IN_PROGRESS') para reconciliacion.

        Equivalente a ``list_promotions(status="PENDING")`` mas los registros
        ``IN_PROGRESS`` (los dejados por un crash previo). Conservado para
        compatibilidad con callers existentes.

        WI-38 (R1 strict): devuelve ``list[StoredPromotion]`` (frozen + slots).
        """
        rows = self._conn.execute(
            """
            SELECT * FROM promotion_outbox
            WHERE status IN ('PENDING', 'IN_PROGRESS')
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [_row_to_stored_promotion(r) for r in rows]

    def list_promotions(
        self,
        status: str | None = None,
    ) -> list[StoredPromotion]:
        """Lista propuestas del outbox, opcionalmente filtradas por ``status``.

        - ``status=None`` -> todas las propuestas, ordenadas por ``created_at`` ASC.
        - ``status='PENDING'`` -> solo PENDING; equivalente a la rama
          ``list_promotions(status='PENDING')`` (sin IN_PROGRESS).
        - Cualquier otro status valido (``IN_PROGRESS``, ``PUBLISHED``,
          ``FAILED``) filtra exactamente por ese valor.

        Lanza ``ValidationError`` si ``status`` no esta en
        ``PROMOTION_STATUSES``. No expone SQL al caller.

        WI-38 (R1 strict): devuelve ``list[StoredPromotion]``.
        """
        if status is not None and status not in PROMOTION_STATUSES:
            raise ValidationError(
                f"status de promocion invalido: {status!r}; validos={sorted(PROMOTION_STATUSES)}"
            )

        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM promotion_outbox ORDER BY created_at ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM promotion_outbox WHERE status = ? ORDER BY created_at ASC",
                (status,),
            ).fetchall()
        return [_row_to_stored_promotion(r) for r in rows]

    def mark_promotion_in_progress(self, proposal_id: str) -> bool:
        """Pasa de PENDING a IN_PROGRESS. Devuelve True si transiciono."""
        cur = self._conn.execute(
            """
            UPDATE promotion_outbox
            SET status = 'IN_PROGRESS', attempts = attempts + 1,
                updated_at = datetime('now')
            WHERE proposal_id = ? AND status = 'PENDING'
            """,
            (proposal_id,),
        )
        return cur.rowcount > 0

    def mark_promotion_published(self, proposal_id: str) -> bool:
        """Pasa de IN_PROGRESS a PUBLISHED. Devuelve True si transiciono."""
        cur = self._conn.execute(
            """
            UPDATE promotion_outbox
            SET status = 'PUBLISHED', updated_at = datetime('now'),
                published_at = datetime('now')
            WHERE proposal_id = ? AND status = 'IN_PROGRESS'
            """,
            (proposal_id,),
        )
        return cur.rowcount > 0

    def mark_promotion_failed(self, proposal_id: str) -> bool:
        """Marca FAILED para inspeccion manual."""
        cur = self._conn.execute(
            """
            UPDATE promotion_outbox
            SET status = 'FAILED', updated_at = datetime('now')
            WHERE proposal_id = ? AND status IN ('PENDING', 'IN_PROGRESS')
            """,
            (proposal_id,),
        )
        return cur.rowcount > 0
