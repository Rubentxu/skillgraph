"""Mixin de delegaciones de `Storage` hacia el componente promotion delegation.

WI-68. Desdoblamiento de `storage_delegations.py` (915 LoC) en un
modulo por componente, mismo criterio que ADR-0022 fase 1 (los
cinco mixin convivian en un solo fichero) y que ADR-0024 para
`RunController`.

Por que: el audit marca >800 LoC por fichero, y este lo supera
por CONCENTRACION DE CLASES, no de responsabilidad. Ninguna
clase pasa de 366 LoC y ningun metodo de 27: el problema era
que cinco razones de cambio distintas comparten fichero.

Cuerpos verbatim. `Storage` los hereda igual; solo cambia donde
viven. Red: `tests/test_wi68_storage_delegations_split.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class PromotionDelegations:
    """Reenvia al componente ``promotion_repository()`` (SqlitePromotionRepository).

    7 metodos, 66 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

    def register_promotion(
        self,
        *,
        proposal_id: Any,
        idempotency_key: Any,
        tenant_id: Any,
        source_project: Any,
        target_catalog: Any,
        knowledge_ref: Any,
        payload: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().register_promotion(
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            source_project=source_project,
            target_catalog=target_catalog,
            knowledge_ref=knowledge_ref,
            payload=payload,
        )

    def get_promotion(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().get_promotion(
            proposal_id,
        )

    def list_pending_promotions(
        self,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().list_pending_promotions()

    def list_promotions(
        self,
        status: Any = None,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().list_promotions(
            status,
        )

    def mark_promotion_in_progress(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().mark_promotion_in_progress(
            proposal_id,
        )

    def mark_promotion_published(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().mark_promotion_published(
            proposal_id,
        )

    def mark_promotion_failed(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().mark_promotion_failed(
            proposal_id,
        )
