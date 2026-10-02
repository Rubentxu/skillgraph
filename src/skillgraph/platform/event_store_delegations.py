"""Mixin de delegaciones de `Storage` hacia el componente event store delegation.

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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skillgraph.platform.ports import (
        StoredEvent,
    )


class EventStoreDelegations:
    """Reenvia al componente ``event_store()`` (SqliteEventStore).

    4 metodos, 52 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

    def record_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_id: str,
        event_kind: str,
        resource_ref: str,
        payload: Mapping[str, Any],
        run_id: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Delegado WI-56: ver ``SqliteEventStore.record_event``."""
        return self.event_store().record_event(
            tenant_id=tenant_id,
            project_id=project_id,
            event_id=event_id,
            event_kind=event_kind,
            resource_ref=resource_ref,
            payload=payload,
            run_id=run_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

    def list_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
        resource_ref: str | None = None,
        event_kind: str | None = None,
    ) -> list[StoredEvent]:
        """Delegado WI-56: ver ``SqliteEventStore.list_events``."""
        return self.event_store().list_events(
            tenant_id=tenant_id,
            project_id=project_id,
            resource_ref=resource_ref,
            event_kind=event_kind,
        )

    def ensure_schema(self) -> None:
        """Delegado WI-56: ver ``SqliteEventStore.ensure_schema``."""
        return self.event_store().ensure_schema()

    def fetch_event_raw(
        self,
        *,
        event_id: str,
    ) -> StoredEvent | None:
        """Delegado WI-56: ver ``SqliteEventStore.fetch_event_raw``."""
        return self.event_store().fetch_event_raw(event_id=event_id)
