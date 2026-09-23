"""Catálogo local: identidad de tenants y proyectos.

Decisión: una sola tabla `projects` con UNIQUE(tenant_id, name).
No usamos FOREIGN KEY para no atar la tabla al esquema de proyecto;
el catálogo sobrevive incluso si un proyecto está corrupto.

No confundir con la base `project.sqlite` del proyecto: el catálogo
solo guarda identidad y ruta, no recursos.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skillgraph.errors import IdentityConflictError, ValidationError

SCHEMA_VERSION = 1


_CATALOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS projects (
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    db_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, name)
);
CREATE INDEX IF NOT EXISTS projects_by_tenant ON projects(tenant_id);
"""


class Catalog:
    """Catálogo local de proyectos (un archivo por data root)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        with self._tx() as cur:
            cur.executescript(_CATALOG_SCHEMA)
            row = cur.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        with self._conn:
            yield self._conn.cursor()

    def register_project(self, *, tenant_id: str, name: str, db_path: Path) -> None:
        """Registra un proyecto. Lanza `IdentityConflictError` si ya existe."""
        existing = self._conn.execute(
            "SELECT 1 FROM projects WHERE tenant_id = ? AND name = ?",
            (tenant_id, name),
        ).fetchone()
        if existing is not None:
            raise IdentityConflictError(f"Proyecto ya existe: tenant={tenant_id!r} name={name!r}")
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO projects(tenant_id, name, db_path, created_at) VALUES (?, ?, ?, ?)",
                (
                    tenant_id,
                    name,
                    str(db_path),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_project(self, *, tenant_id: str, name: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE tenant_id = ? AND name = ?",
            (tenant_id, name),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_projects(self, *, tenant_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM projects WHERE tenant_id = ? ORDER BY name",
            (tenant_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def open_catalog(path: str | Path) -> Catalog:
    if not str(path).endswith(".sqlite"):
        raise ValidationError(f"Path de catálogo debe terminar en .sqlite: {path}")
    return Catalog(path)
