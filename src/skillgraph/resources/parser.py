"""Parser Markdown+YAML para bricks.

Reglas (doc 04 §1):
- YAML = estructura interpretable.
- Markdown = directivas semánticas.
- El cuerpo Markdown NO puede alterar el contrato estructural.

El parser es deliberadamente pequeño: separa el front matter, normaliza
el dict y construye un `Brick`. La validación tipada vive en
`skillgraph.registry`, no aquí, para evitar duplicación.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from skillgraph.core.errors import ParseError
from skillgraph.resources.bricks import Brick, ResourceIdentity

# Delimitadores YAML de front matter. Coinciden con la convención
# habitual en herramientas de agent para Markdown+YAML.
_FM_OPEN = re.compile(r"^---\s*$", re.MULTILINE)
_FM_PAIR = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


def _split_front_matter(text: str) -> tuple[str, str]:
    """Devuelve (front_matter_yaml, body_markdown).

    Si no hay front matter se lanza `ParseError` con causa tipada.
    """
    m = _FM_PAIR.match(text)
    if m is None:
        raise ParseError("Falta el front matter YAML (delimitadores '---')")
    front = m.group(1)
    body = text[m.end() :].lstrip("\n")
    return front, body


def _parse_yaml(front: str, *, source: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(front)
    except yaml.YAMLError as exc:
        raise ParseError(f"YAML inválido en {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError(f"YAML en {source} debe ser un mapping en el nivel superior")
    return data


def _require_str(
    data: dict[str, Any],
    key: str,
    *,
    source: str,
) -> str:
    """Lee `data[key]` y exige string no vacio. Lanza ParseError tipado."""
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ParseError(f"{source}: {key} ausente o no es string")
    return value


def _require_dict(
    data: dict[str, Any],
    key: str,
    *,
    source: str,
) -> dict[str, Any]:
    """Lee `data[key]` y exige mapping (o {} si falta). Lanza ParseError."""
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ParseError(f"{source}: {key} debe ser un mapping")
    return value


def _metadata_name(metadata: dict[str, Any], *, source: str) -> str:
    name = metadata.get("name")
    if not isinstance(name, str) or not name:
        raise ParseError(f"{source}: metadata.name ausente o no es string")
    return name


def _metadata_namespace(metadata: dict[str, Any], *, source: str) -> str:
    namespace = metadata.get("namespace", "")
    if not isinstance(namespace, str):
        raise ParseError(f"{source}: metadata.namespace debe ser string")
    return namespace


def parse_markdown(
    text: str,
    *,
    source: str,
    identity: ResourceIdentity,
) -> Brick:
    """Parsea un texto Markdown+YAML a `Brick`.

    No realiza validación tipada del `spec`; eso es responsabilidad del
    registro de tipos. Aquí solo se impone la **forma declarativa**
    común del blueprint (doc 03 §3).

    La identidad del brick se construye desde el front matter
    (`metadata.namespace`, `metadata.name`) combinada con el `tenant_id`
    y `project_id` del caller. El caller NO controla el namespace/name
    del brick resultante: eso sería una escalada de capacidades.
    """
    if not isinstance(text, str):
        raise ParseError(f"Entrada de {source} debe ser texto")

    front, body = _split_front_matter(text)
    data = _parse_yaml(front, source=source)

    api_version = _require_str(data, "apiVersion", source=source)
    kind = _require_str(data, "kind", source=source)
    metadata = _require_dict(data, "metadata", source=source)
    spec = _require_dict(data, "spec", source=source)

    name = _metadata_name(metadata, source=source)
    namespace = _metadata_namespace(metadata, source=source)

    brick_identity = ResourceIdentity(
        tenant_id=identity.tenant_id,
        project_id=identity.project_id,
        namespace=namespace,
        kind=kind,
        name=name,
    )

    return Brick(
        identity=brick_identity,
        api_version=api_version,
        kind=kind,
        spec=spec,
        markdown_body=body,
    )


def parse_file(
    path: str | Path,
    *,
    identity: ResourceIdentity,
) -> Brick:
    p = Path(path)
    return parse_markdown(p.read_text(encoding="utf-8"), source=str(p), identity=identity)
