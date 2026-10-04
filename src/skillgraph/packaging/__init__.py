"""El contrato de paquete de B8, y la pregunta de si encaja aqui.

Se reexporta la superficie publica para que quien use el contrato no
tenga que saber en que modulo vive cada cosa —igual que `presentation`
en B7— y para que anadir un simbolo al contrato sea un cambio visible en
un solo sitio.
"""

from __future__ import annotations

from skillgraph.packaging.manifest import (
    ISOLATION_LEVELS,
    PACK_KINDS,
    CapabilityRequirement,
    IncompatiblePackError,
    IsolationLevel,
    PackKind,
    PackManifest,
    Requires,
    es_compatible,
    exigir_compatible,
    parse_manifest,
)
from skillgraph.packaging.registry import (
    ESTADO_INSTALADO,
    ESTADO_RETIRADO,
    FilaDePack,
    RegistroDePacks,
    actualizar,
    instalar,
    manifiesto_de,
    motivos_de_incompatibilidad,
    retirar,
)

__all__ = (
    "ESTADO_INSTALADO",
    "ESTADO_RETIRADO",
    "ISOLATION_LEVELS",
    "PACK_KINDS",
    "CapabilityRequirement",
    "FilaDePack",
    "IncompatiblePackError",
    "IsolationLevel",
    "PackKind",
    "PackManifest",
    "RegistroDePacks",
    "Requires",
    "actualizar",
    "es_compatible",
    "exigir_compatible",
    "instalar",
    "manifiesto_de",
    "motivos_de_incompatibilidad",
    "parse_manifest",
    "retirar",
)
