"""Indice de los mixin de delegacion de `Storage` (WI-68).

Cada componente tiene su modulo (`knowledge_delegations`,
`run_delegations`, `promotion_delegations`, `event_store_delegations` y
`policy_delegations`). Este modulo reexporta los cinco para que
`from skillgraph.platform.storage_delegations import Storage` siga
funcionando sin editar a los llamadores.

Los nombres se declaran en `__all__` porque `Storage` los importa
desde aqui: sin eso, ruff los borraria por F401 en cuanto el facade
dejase de referenciarlos.
"""

from __future__ import annotations

from skillgraph.platform.event_store_delegations import EventStoreDelegations
from skillgraph.platform.knowledge_delegations import KnowledgeDelegations
from skillgraph.platform.policy_delegations import PolicyDelegations
from skillgraph.platform.promotion_delegations import PromotionDelegations
from skillgraph.platform.run_delegations import RunDelegations

__all__ = [
    "EventStoreDelegations",
    "KnowledgeDelegations",
    "PolicyDelegations",
    "PromotionDelegations",
    "RunDelegations",
]
