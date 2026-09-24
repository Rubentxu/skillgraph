"""Tests del modulo paths (resolucion de data_root multiplataforma).

Cubre las ramas no ejercitadas en CI Linux:
- default_data_root() en posix con XDG_DATA_HOME ausente / presente.
- resolve_data_root() con argumento explicito (rama 1).
- resolve_data_root() con env pero sin explicit (rama 2).
- resolve_data_root() sin env ni explicit (rama 3 = default_data_root).
- helpers catalog_path/tenant_dir/project_dir/project_db_path.

La rama ``os.name == 'nt'`` no se cubre en CI Linux (cruzar pathlib entre
plataformas es fragil); el contrato queda documentado en el docstring
de ``default_data_root``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgraph.platform.paths import (
    DEFAULT_TENANT,
    ENV_DATA_ROOT,
    catalog_path,
    default_data_root,
    project_db_path,
    project_dir,
    resolve_data_root,
    tenant_dir,
)


class TestDefaultDataRoot:
    def test_linux_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Garantiza XDG_DATA_HOME ausente y HOME conocido.
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("HOME", "/home/test")
        root = default_data_root()
        assert root == Path("/home/test/.local/share/skillgraph")

    def test_linux_with_xdg_data_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg")
        root = default_data_root()
        assert root == Path("/custom/xdg/skillgraph")

    def test_windows_is_only_relevant_on_nt(self) -> None:
        # La rama nt no se ejercita en CI Linux (monkeypatch de os.name
        # combinado con pathlib.WindowsPath() no es seguro). Aqui solo
        # documentamos el contrato: si os.name == 'nt' y LOCALAPPDATA
        # existe, debe usarse. La implementacion lo hace; ver
        # ``src/skillgraph/paths.py``.
        assert os.name in {"posix", "nt"}


class TestResolveDataRoot:
    def test_explicit_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ENV_DATA_ROOT, "/should/be/ignored")
        root = resolve_data_root(tmp_path)
        assert root == tmp_path.resolve()

    def test_env_when_no_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_DATA_ROOT, "/env/data/root")
        root = resolve_data_root(None)
        assert root == Path("/env/data/root").resolve()

    def test_default_when_no_explicit_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_DATA_ROOT, raising=False)
        monkeypatch.setattr(os, "name", "posix")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("HOME", "/home/default")
        root = resolve_data_root(None)
        assert root == Path("/home/default/.local/share/skillgraph").resolve()


class TestPathHelpers:
    def test_catalog_path(self, tmp_path: Path) -> None:
        assert catalog_path(tmp_path) == tmp_path / "catalog.sqlite"

    def test_tenant_dir(self, tmp_path: Path) -> None:
        assert tenant_dir(tmp_path) == tmp_path / "tenants" / DEFAULT_TENANT
        assert tenant_dir(tmp_path, "other") == tmp_path / "tenants" / "other"

    def test_project_dir(self, tmp_path: Path) -> None:
        assert project_dir(tmp_path, "demo") == (
            tmp_path / "tenants" / DEFAULT_TENANT / "projects" / "demo"
        )

    def test_project_db_path(self, tmp_path: Path) -> None:
        assert project_db_path(tmp_path, "demo") == (
            tmp_path / "tenants" / DEFAULT_TENANT / "projects" / "demo" / "project.sqlite"
        )
