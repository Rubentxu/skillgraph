"""Mixin de delegaciones de `Storage` hacia el componente policy delegation.

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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skillgraph.platform.ports import (
        StoredBudget,
    )


class PolicyDelegations:
    """Reenvia al componente ``policy_store()`` (SqlitePolicyStore).

    4 metodos, 45 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

    def get_policy(
        self,
        *,
        tenant_id: str,
    ) -> str | None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.get_policy``."""
        return self.policy_store().get_policy(tenant_id=tenant_id)

    def upsert_policy(
        self,
        *,
        tenant_id: str,
        policy: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.upsert_policy``."""
        return self.policy_store().upsert_policy(tenant_id=tenant_id, policy=policy)

    def upsert_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        max_visits: int | None,
        max_runtime_seconds: int | None,
        max_events: int | None,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.upsert_budget``."""
        return self.policy_store().upsert_budget(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            max_visits=max_visits,
            max_runtime_seconds=max_runtime_seconds,
            max_events=max_events,
        )

    def get_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredBudget | None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.get_budget``."""
        return self.policy_store().get_budget(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )
