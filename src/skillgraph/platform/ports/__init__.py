"""Puertos de persistencia: DTOs y Protocols (WI-69).

WI-69. Desdoblamiento de `ports/__init__.py` (927 LoC) en `dto`
(tipos almacenados) y `repositories` (Protocols), con `__init__`
como indice de re-export.

Por que: el audit marca >800 LoC por fichero y este lo supera por
ANCHURA (14 tipos), no por profundidad: la clase mayor es
`KnowledgeRepository` con 179 LoC. La razon de cambio que si
justificaba el corte es la separacion entre lo que se persiste y
los contratos que lo consumen, con dependencia unidireccional
(los Protocols importan los DTO, nunca al reves).

`from skillgraph.platform.ports import <cualquiera>` sigue
funcionando: `__init__` reexporta los catorce y los declara en
`__all__`. Red: `tests/test_wi69_ports_split.py`.
"""

from __future__ import annotations

from skillgraph.platform.ports.dto import (
    StoredBudget,
    StoredClaim,
    StoredEvent,
    StoredEvidence,
    StoredNodeExecution,
    StoredPromotion,
    StoredRelation,
    StoredResource,
    StoredRun,
)
from skillgraph.platform.ports.repositories import (
    EventStore,
    KnowledgeRepository,
    PolicyStore,
    PromotionRepository,
    RunRepository,
)

__all__ = [
    "EventStore",
    "KnowledgeRepository",
    "PolicyStore",
    "PromotionRepository",
    "RunRepository",
    "StoredBudget",
    "StoredClaim",
    "StoredEvent",
    "StoredEvidence",
    "StoredNodeExecution",
    "StoredPromotion",
    "StoredRelation",
    "StoredResource",
    "StoredRun",
]
