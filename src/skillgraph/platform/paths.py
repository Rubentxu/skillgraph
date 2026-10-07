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
from typing import Final

ENV_DATA_ROOT = "SKILLGRAPH_DATA_ROOT"
DEFAULT_TENANT = "default"


def default_data_root() -> Path:
    """Raíz por defecto multiplataforma.

    En ``nt`` (Windows): ``%LOCALAPPDATA%`` si existe, si no ``%USERPROFILE%``.
    En ``posix``: ``$XDG_DATA_HOME`` si existe, si no ``~/.local/share``.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base is None:
            # Fallback: expanduser('~') en 'nt' usa %USERPROFILE%, en
            # sistemas sin esa variable, expande vacio. Forzamos un
            # string no vacio para evitar paths raros.
            base = os.path.expanduser("~") or os.getcwd()
    else:
        base = os.environ.get("XDG_DATA_HOME")
        if base is None:
            base = str(Path("~/.local/share").expanduser())
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


#: La regla que `is_safe_name` aplica, escrita UNA vez.
#:
#: MEDIDO por que hace falta: el mensaje de `sg project create` decía
#: «Use solo [a-z0-9-_]», y `is_safe_name` ACEPTA mayusculas. El conjunto que
#: el mensaje anunciaba era estrictamente mas pequeño que el que la funcion
#: aplicaba, y la contradiccion vivia en la unica linea que ve un operador
#: con un nombre invalido.
#:
#: No basta con corregir el texto: un texto corregido a mano vuelve a
#: separarse de la funcion en cuanto cualquiera de las dos cambia. La regla
#: vive aqui y el CLI la imprime, de modo que hay UNA verdad y el guard
#: mide que las dos digan lo mismo.
REGLAS_DE_NOMBRE_SEGURO: Final[str] = (
    "caracteres alfanumericos ASCII ([A-Za-z0-9-_]), de 1 a 64 caracteres"
)


def is_safe_name(name: str) -> bool:
    """Slug de proyecto: alfanumericos ASCII y `-`/`_`, de 1 a 64.

    Defensa contra inyecciones via nombres maliciosos (RF-11). El nombre
    va a una RUTA (`tenants/<t>/projects/<nombre>/`), luego no es un dato
    con formato sino una porcion de camino.

    El conjunto de lo permitido esta escrito en `REGLAS_DE_NOMBRE_SEGURO`,
    que es lo que el CLI imprime al rechazar un nombre. Si cambias una de
    las dos, el guard `test_wi116_nombre_de_proyecto.py` se pone rojo.
    """
    if not name or len(name) > 64:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in name)


def agents_root(data_root: Path) -> Path:
    """Raíz de fixtures de agentes (estructura: <tenant>/<project>/<node>.json).

    Vive fuera de los proyectos para que el usuario pueda mantener
    fixtures compartidas entre proyectos. Por defecto cuelga de
    la raíz de datos como subdirectorio `agents/`.
    """
    return data_root / "agents"
