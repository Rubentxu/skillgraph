"""H9-Coverage-5: cobertura de las ramas no ejercitadas de
`skillgraph.resources.catalog` (88% -> >=95%).

Las ramas cubiertas aqui son:
- register_project: duplicado -> IdentityConflictError
- list_projects: tenant con proyectos + tenant vacio
- open_catalog: path sin extension .sqlite -> ValidationError

Sin modificacion de produccion. Spec: specs/h9-coverage-catalog.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.core.errors import IdentityConflictError, ValidationError
from skillgraph.resources.catalog import Catalog, open_catalog

# ---------------------------------------------------------------------------
# register_project: duplicado
# ---------------------------------------------------------------------------


def test_register_project_duplicate_raises_identity_conflict(tmp_path: Path) -> None:
    """Registrar el mismo (tenant_id, name) dos veces -> IdentityConflictError.

    Cubre linea 76 (rama `existing is not None`).
    """
    catalog = Catalog(tmp_path / "catalog.sqlite")
    try:
        catalog.register_project(
            tenant_id="t-1",
            name="alpha",
            db_path=tmp_path / "alpha.sqlite",
        )
        with pytest.raises(IdentityConflictError, match=r"Proyecto ya existe"):
            catalog.register_project(
                tenant_id="t-1",
                name="alpha",
                db_path=tmp_path / "alpha_other.sqlite",
            )
    finally:
        catalog.close()


# ---------------------------------------------------------------------------
# list_projects: con resultados
# ---------------------------------------------------------------------------


def test_list_projects_returns_all_in_name_order(tmp_path: Path) -> None:
    """`list_projects` devuelve proyectos ordenados por nombre.

    Cubre lineas 96-100 (rama verdadera con resultados).
    """
    catalog = Catalog(tmp_path / "catalog.sqlite")
    try:
        # Insertar en orden NO alfabetico para verificar el ORDER BY.
        catalog.register_project(
            tenant_id="t-1",
            name="zebra",
            db_path=tmp_path / "zebra.sqlite",
        )
        catalog.register_project(
            tenant_id="t-1",
            name="alpha",
            db_path=tmp_path / "alpha.sqlite",
        )
        catalog.register_project(
            tenant_id="t-1",
            name="middle",
            db_path=tmp_path / "middle.sqlite",
        )

        projects = catalog.list_projects(tenant_id="t-1")

        assert [p["name"] for p in projects] == ["alpha", "middle", "zebra"]
        # db_path se preserva verbatim
        assert projects[0]["db_path"] == str(tmp_path / "alpha.sqlite")
        # tenant_id consistente
        assert all(p["tenant_id"] == "t-1" for p in projects)
    finally:
        catalog.close()


# ---------------------------------------------------------------------------
# list_projects: tenant sin proyectos
# ---------------------------------------------------------------------------


def test_list_projects_for_unknown_tenant_returns_empty(tmp_path: Path) -> None:
    """`list_projects` con tenant sin proyectos devuelve `[]`."""
    catalog = Catalog(tmp_path / "catalog.sqlite")
    try:
        # Tenant sin proyectos registrados.
        projects = catalog.list_projects(tenant_id="t-void")
        assert projects == []
    finally:
        catalog.close()


# ---------------------------------------------------------------------------
# open_catalog: path sin extension .sqlite
# ---------------------------------------------------------------------------


def test_open_catalog_rejects_non_sqlite_path(tmp_path: Path) -> None:
    """`open_catalog` con path que NO termina en `.sqlite` -> ValidationError.

    Cubre linea 105.
    """
    bad_path = tmp_path / "catalog.db"  # extension incorrecta
    with pytest.raises(ValidationError, match=r"debe terminar en \.sqlite"):
        open_catalog(bad_path)
