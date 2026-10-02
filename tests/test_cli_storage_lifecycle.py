"""Regression tests for CLI-owned Storage lifecycles.

The CLI helpers must own the Storage instances they open. Returning a live
connection to handlers without a scope leaks sqlite connections when the CLI
is used in-process, even though subprocess tests pass at process exit.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from skillgraph.cli.commands.knowledge import _open_known_project
from skillgraph.cli.support import _open_project_storage
from skillgraph.platform.paths import DEFAULT_TENANT, catalog_path, project_db_path
from skillgraph.platform.storage import Storage
from skillgraph.resources.catalog import open_catalog


def _args(data_root: Path, project: str = "demo") -> argparse.Namespace:
    return argparse.Namespace(data_root=data_root, project=project)


def _create_project(data_root: Path, project: str = "demo") -> Path:
    db_path = project_db_path(data_root, project, tenant=DEFAULT_TENANT)
    with Storage(db_path):
        pass
    catalog = open_catalog(catalog_path(data_root))
    try:
        catalog.register_project(
            tenant_id=DEFAULT_TENANT,
            name=project,
            db_path=db_path,
        )
    finally:
        catalog.close()
    return db_path


def test_open_project_storage_context_closes_connection(tmp_path: Path) -> None:
    """The runs/policy helper closes its owned Storage at scope exit."""
    data_root = tmp_path / "data"
    db_path = _create_project(data_root)

    with _open_project_storage(_args(data_root)) as (storage, err):
        assert err == 0
        assert storage is not None
        connection = storage._conn

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert db_path.exists()


def test_open_known_project_context_closes_connection(tmp_path: Path) -> None:
    """The knowledge helper closes its owned Storage at scope exit."""
    data_root = tmp_path / "data"
    _create_project(data_root)

    with _open_known_project(_args(data_root), "demo") as (
        tenant_id,
        project_id,
        storage,
    ):
        assert tenant_id == DEFAULT_TENANT
        assert project_id == "demo"
        connection = storage._conn

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
