"""Materializacion inmutable del Handoff (Etapa 2 / S2).

Doc externo:
  external/blueprint-v1/docs/07-contexto-y-handoff.md

El Handoff es lo que el agente VE en su adapter. Es la unica forma
que tiene el agente de consumir el estado del run: por tanto:

- Es INMUTABLE (dataclass frozen, slots=True).
- Es SERIALIZABLE a JSON estable (campos ordenados).
- Tiene un `context_hash` SHA-256 que el Core firma (los
  adapters NO calculan hash; reciben el handoff firmado).
- Su identidad incluye revision de definicion y de fuente,
  no solo nombre (UAT-16: estado historico preservado).

Regla de oro: dos handoffs con la misma identidad + comportamiento +
conocimiento + capacidades producen el MISMO `context_hash`. Esto
permite deduplicar en `HandoffStore` y reproducir ejecuciones.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from skillgraph.errors import ValidationError
from skillgraph.runtime_types import NODE_KINDS, NodeKind


@dataclass(frozen=True, slots=True)
class HandoffIdentity:
    """Quien ejecuta y bajo que intento."""

    tenant_id: str
    project_id: str
    run_id: str
    node_execution_id: str
    attempt: int

    def __post_init__(self) -> None:
        from skillgraph.errors import ValidationError

        if not self.tenant_id:
            raise ValidationError("tenant_id vacio")
        if not self.project_id:
            raise ValidationError("project_id vacio")
        if not self.run_id:
            raise ValidationError("run_id vacio")
        if not self.node_execution_id:
            raise ValidationError("node_execution_id vacio")
        if self.attempt < 1:
            raise ValidationError("attempt debe ser >= 1")

    def validate(self) -> None:
        # Mantener firma historica; la logica vive en __post_init__.
        return


@dataclass(frozen=True, slots=True)
class HandoffBehavior:
    """Que brick se ejecuta y bajo que revision."""

    definition_kind: NodeKind
    definition_name: str
    definition_namespace: str
    definition_revision: int
    api_version: str

    def __post_init__(self) -> None:
        if self.definition_kind not in NODE_KINDS:
            raise ValidationError(f"definition_kind invalido: {self.definition_kind!r}")
        if not self.definition_name:
            raise ValidationError("definition_name vacio")
        if not self.definition_namespace:
            raise ValidationError("definition_namespace vacio")
        if self.definition_revision < 1:
            raise ValidationError("definition_revision debe ser >= 1")
        if not self.api_version:
            raise ValidationError("api_version vacio")

    def validate(self) -> None:
        return


@dataclass(frozen=True, slots=True)
class HandoffKnowledge:
    """Lo que el agente puede ver: contexto resuelto de la receta."""

    recipe_ref: str
    included: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    """(resource_kind, resource_namespace, resource_name) de cada item."""

    def __post_init__(self) -> None:
        from skillgraph.errors import ValidationError

        if not self.recipe_ref:
            raise ValidationError("recipe_ref vacio")

    def validate(self) -> None:
        return


@dataclass(frozen=True, slots=True)
class HandoffExecution:
    """Donde corre y con que limites."""

    workspace_ref: str
    source_revision: str
    budget: dict[str, int]

    def __post_init__(self) -> None:
        from skillgraph.errors import ValidationError

        if not self.workspace_ref:
            raise ValidationError("workspace_ref vacio")
        if not self.source_revision:
            raise ValidationError("source_revision vacio")
        if not isinstance(self.budget, dict):
            raise ValidationError("budget debe ser dict")

    def validate(self) -> None:
        return


@dataclass(frozen=True, slots=True)
class Handoff:
    """Snapshot inmutable del estado relevante para UN nodo."""

    identity: HandoffIdentity
    behavior: HandoffBehavior
    knowledge: HandoffKnowledge
    execution: HandoffExecution
    expected_result: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.identity.validate()
        self.behavior.validate()
        self.knowledge.validate()
        self.execution.validate()
        if not self.expected_result:
            from skillgraph.errors import ValidationError

            raise ValidationError("expected_result vacio")

    def to_dict(self) -> dict[str, Any]:
        """Serializacion estable: orden total, sin orden de insercion."""

        def _k(v: Any) -> Any:
            if isinstance(v, tuple):
                return [_k(x) for x in v]
            return v

        return {
            "identity": {
                "tenant_id": self.identity.tenant_id,
                "project_id": self.identity.project_id,
                "run_id": self.identity.run_id,
                "node_execution_id": self.identity.node_execution_id,
                "attempt": self.identity.attempt,
            },
            "behavior": {
                "definition_kind": self.behavior.definition_kind,
                "definition_name": self.behavior.definition_name,
                "definition_namespace": self.behavior.definition_namespace,
                "definition_revision": self.behavior.definition_revision,
                "api_version": self.behavior.api_version,
            },
            "knowledge": {
                "recipe_ref": self.knowledge.recipe_ref,
                "included": [_k(list(item)) for item in self.knowledge.included],
            },
            "execution": {
                "workspace_ref": self.execution.workspace_ref,
                "source_revision": self.execution.source_revision,
                "budget": dict(sorted(self.execution.budget.items())),
            },
            "expected_result": self.expected_result,
            "capabilities": sorted(self.capabilities),
        }

    @property
    def context_hash(self) -> str:
        """SHA-256 hex sobre la serializacion estable."""
        body = json.dumps(self.to_dict(), sort_keys=False)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
