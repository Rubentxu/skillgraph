"""Resolución de rutas de datos de SkillGraph (Etapa 1).

Reglas (external/blueprint-v1/docs/09-persistencia.md §3 y RF-11):
- Datos fuera de los proyectos fuente del usuario.
- Raíz configurable por env var o `--data-root`.
- Defaults: `~/.local/share/skillgraph` en Linux/Mac,
  `%LOCALAPPDATA%\\skillgraph` en Windows.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_DATA_ROOT = "SKILLGRAPH_DATA_ROOT"
DEFAULT_TENANT = "default"


def default_data_root() -> Path:
    """Raíz por defecto multiplataforma."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "skillgraph"


def resolve_data_root(explicit: Path | None = None) -> Path:
    """Resuelve la raíz de datos con precedencia:
    1) argumento explícito
    2) variable de entorno SKILLGRAPH_DATA_ROOT
    3) default multiplataforma
    """
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = os.environ.get(ENV_DATA_ROOT)
    if env:
        return Path(env).expanduser().resolve()
    return default_data_root().resolve()


def catalog_path(data_root: Path) -> Path:
    """Path del catálogo local (identidad de tenants/proyectos)."""
    return data_root / "catalog.sqlite"


def tenant_dir(data_root: Path, tenant: str = DEFAULT_TENANT) -> Path:
    return data_root / "tenants" / tenant


def project_dir(data_root: Path, project: str, tenant: str = DEFAULT_TENANT) -> Path:
    return tenant_dir(data_root, tenant) / "projects" / project


def project_db_path(data_root: Path, project: str, tenant: str = DEFAULT_TENANT) -> Path:
    return project_dir(data_root, project, tenant) / "project.sqlite"


def is_safe_name(name: str) -> bool:
    """Slug de proyecto: solo [a-z0-9-_], longitud razonable.

    Defensa contra inyecciones via nombres maliciosos (RF-11).
    """
    if not name or len(name) > 64:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in name)
