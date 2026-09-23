"""Tipos base de recursos (bricks).

Etapa 0 / S0: dataclasses inmutables con identidad declarativa.
Se mantiene un solo punto de validación para evitar duplicación
entre el parser y el registro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ResourceIdentity:
    """Identidad declarativa de un brick.

    Coincide con la fórmula del blueprint (doc 03 §3):
        tenant + project + namespace + kind + name.
    """

    tenant_id: str
    project_id: str
    namespace: str
    kind: str
    name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "namespace": self.namespace,
            "kind": self.kind,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class Brick:
    """Recurso declarativo mínimo.

    El campo `spec` se conserva como `dict[str, Any]` para mantener
    neutrality de dominio: la validación tipada se delega al registro
    de tipos (cada kind declara su esquema).
    """

    identity: ResourceIdentity
    api_version: str
    kind: str
    spec: dict[str, Any] = field(default_factory=dict)
    # El cuerpo Markdown se conserva íntegro aunque no participe en la
    # validación estructural: el blueprint (doc 04 §1) exige que el
    # Markdown NO pueda aumentar permisos ni alterar contratos.
    markdown_body: str = ""

    @property
    def uid_components(self) -> dict[str, str]:
        return self.identity.as_dict()
