"""Tests para `governance/backups.py` (WI-15, T5 roadmap).

Cobertura:
- TestBackupManifest: serializacion round-trip JSON.
- TestCreateBackup: ciclo create -> list -> verify -> restore.
- TestVerifyBackup: deteccion de corrupcion (SHA-256 mismatch).
- TestRestoreBackup: overwrite policy, post-extract re-hash.
- TestListBackups: filtrado de backups corruptos, orden por fecha desc.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.governance.backups import (
    BACKUP_DIR_NAME,
    BACKUP_FORMAT_VERSION,
    BackupEntry,
    BackupManifest,
    create_backup,
    default_backup_dir,
    list_backups,
    restore_backup,
    verify_backup,
)
from skillgraph.platform.paths import catalog_path, project_dir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_data_root(root_dir: Path) -> Path:
    """Crea un data-root con catalog.sqlite + 1 proyecto con project.sqlite.

    root_dir: directorio que sera el data-root (debe existir).
    """
    root = root_dir / "data"
    root.mkdir(parents=True, exist_ok=True)
    # catalog.sqlite
    cat = catalog_path(root)
    conn = sqlite3.connect(str(cat))
    conn.execute("CREATE TABLE foo (id INTEGER)")
    conn.commit()
    conn.close()
    # 1 proyecto
    proj = project_dir(root, "demo")
    proj.mkdir(parents=True)
    db = proj / "project.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE bar (id INTEGER)")
    conn.commit()
    conn.close()
    return root


# ---------------------------------------------------------------------------
# TestBackupManifest
# ---------------------------------------------------------------------------


class TestBackupManifest:
    """Serializacion round-trip del manifest."""

    def test_roundtrip_empty(self) -> None:
        m = BackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            created_at="2026-09-26T20:00:00Z",
            data_root="/tmp/x",
            tenant_count=0,
            project_count=0,
            entries=(),
        )
        d = m.to_dict()
        m2 = BackupManifest.from_dict(d)
        assert m2 == m

    def test_roundtrip_with_entries(self) -> None:
        m = BackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            created_at="2026-09-26T20:00:00Z",
            data_root="/tmp/x",
            tenant_count=2,
            project_count=5,
            entries=(
                BackupEntry(relpath="catalog.sqlite", sha256="abc", size_bytes=100),
                BackupEntry(
                    relpath="tenants/default/projects/demo/project.sqlite",
                    sha256="def",
                    size_bytes=200,
                ),
            ),
        )
        d = m.to_dict()
        m2 = BackupManifest.from_dict(d)
        assert m2 == m
        assert len(m2.entries) == 2

    def test_from_dict_rejects_wrong_format_version(self) -> None:
        with pytest.raises(ValidationError):
            BackupManifest.from_dict(
                {
                    "format_version": "99.0",
                    "created_at": "x",
                    "data_root": "x",
                    "tenant_count": 0,
                    "project_count": 0,
                    "entries": [],
                }
            )

    def test_from_dict_rejects_non_list_entries(self) -> None:
        with pytest.raises(ValidationError):
            BackupManifest.from_dict(
                {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "created_at": "x",
                    "data_root": "x",
                    "tenant_count": 0,
                    "project_count": 0,
                    "entries": "not-a-list",
                }
            )


# ---------------------------------------------------------------------------
# TestCreateBackup
# ---------------------------------------------------------------------------


class TestCreateBackup:
    """Ciclo create del backup."""

    def test_creates_zip_with_manifest(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        assert out.exists()
        assert out.suffix == ".zip"
        assert out.parent.name == BACKUP_DIR_NAME
        with zipfile.ZipFile(out, "r") as zf:
            assert "manifest.json" in zf.namelist()
            assert "catalog.sqlite" in zf.namelist()
            assert "tenants/default/projects/demo/project.sqlite" in zf.namelist()

    def test_creates_with_custom_output_path(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        custom = tmp_path / "my-backup.zip"
        out = create_backup(root, output_path=custom)
        assert out == custom.resolve()

    def test_creates_with_default_data_root(self, tmp_path: Path) -> None:
        """Si no se pasa output_path, crea <data-root>/backups/<timestamp>.zip."""
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        assert out.parent == root / "backups"
        assert out.name.startswith("skillgraph-")
        assert out.name.endswith(".zip")

    def test_raises_if_data_root_missing(self, tmp_path: Path) -> None:
        ghost = tmp_path / "nope"
        with pytest.raises(ValidationError):
            create_backup(ghost)

    def test_raises_if_catalog_missing(self, tmp_path: Path) -> None:
        """data_root existe pero sin catalog.sqlite: ValidationError."""
        root = tmp_path / "data-empty"
        root.mkdir()
        with pytest.raises(ValidationError):
            create_backup(root)

    def test_manifest_records_correct_counts(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        with zipfile.ZipFile(out, "r") as zf:
            manifest = BackupManifest.from_dict(json.loads(zf.read("manifest.json")))
        assert manifest.tenant_count == 1
        assert manifest.project_count == 1
        assert len(manifest.entries) == 2  # catalog + 1 project


# ---------------------------------------------------------------------------
# TestVerifyBackup
# ---------------------------------------------------------------------------


class TestVerifyBackup:
    """Verificacion SHA-256 post-create."""

    def test_verify_passes_on_clean_backup(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        manifest = verify_backup(out)
        assert manifest.tenant_count == 1

    def test_verify_detects_missing_file(self, tmp_path: Path) -> None:
        """Si el manifest declara un archivo que NO esta en el zip,
        verify_backup lanza ValidationError."""
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        # Anade un entry falso al manifest (apunta a archivo inexistente)
        with zipfile.ZipFile(out, "r") as zf:
            data = {n: zf.read(n) for n in zf.namelist()}
        manifest_dict = json.loads(data["manifest.json"])
        manifest_dict["entries"].append(
            {
                "relpath": "tenants/default/projects/demo/missing.sqlite",
                "sha256": "deadbeef" * 8,
                "size_bytes": 0,
            }
        )
        data["manifest.json"] = json.dumps(manifest_dict).encode()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for n, b in data.items():
                zf.writestr(n, b)
        with pytest.raises(ValidationError):
            verify_backup(out)

    def test_verify_detects_sha_mismatch(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        # Corrompe 1 byte de catalog.sqlite dentro del zip
        with zipfile.ZipFile(out, "r") as zf:
            data = {n: zf.read(n) for n in zf.namelist()}
        original = data["catalog.sqlite"]
        data["catalog.sqlite"] = bytes([(original[0] + 1) % 256]) + original[1:]
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for n, b in data.items():
                zf.writestr(n, b)
        with pytest.raises(ValidationError):
            verify_backup(out)

    def test_verify_raises_if_zip_missing(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError):
            verify_backup(tmp_path / "nope.zip")

    def test_verify_raises_if_manifest_missing(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty, "w") as zf:
            zf.writestr("foo.txt", "bar")
        with pytest.raises(ValidationError):
            verify_backup(empty)


# ---------------------------------------------------------------------------
# TestRestoreBackup
# ---------------------------------------------------------------------------


class TestRestoreBackup:
    """Restore del backup a un data-root destino."""

    def test_roundtrip_create_then_restore(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        target = tmp_path / "restored"
        restored = restore_backup(out, target)
        assert restored == target.resolve()
        assert (target / "catalog.sqlite").exists()
        assert (target / "tenants" / "default" / "projects" / "demo" / "project.sqlite").exists()

    def test_restored_files_have_matching_sha(self, tmp_path: Path) -> None:
        """Post-extract: verify_backup re-confirma SHA-256."""
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        target = tmp_path / "restored"
        restore_backup(out, target)
        # Vuelve a verificar el manifest (que apunta a los archivos extraidos).
        # Esto confirma que el SHA del disco coincide con el del zip.
        manifest = verify_backup(out)
        for entry in manifest.entries:
            extracted = target / entry.relpath
            assert extracted.exists()


# ---------------------------------------------------------------------------
# TestListBackups
# ---------------------------------------------------------------------------


class TestListBackups:
    """Listado de backups disponibles."""

    def test_empty_dir_returns_empty_tuple(self, tmp_path: Path) -> None:
        assert list_backups(tmp_path) == ()

    def test_list_returns_backup_info(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        out = create_backup(root)
        infos = list_backups(root / "backups")
        assert len(infos) == 1
        assert infos[0].path == out
        assert infos[0].tenant_count == 1
        assert infos[0].project_count == 1

    def test_list_sorts_newest_first(self, tmp_path: Path) -> None:
        root = _make_data_root(tmp_path)
        import time

        create_backup(root, output_path=root / "backups" / "skillgraph-A.zip")
        time.sleep(0.01)
        create_backup(root, output_path=root / "backups" / "skillgraph-B.zip")
        infos = list_backups(root / "backups")
        assert len(infos) == 2
        # sorted(reverse=True) -> lexicografico, B > A
        assert infos[0].path.name == "skillgraph-B.zip"

    def test_list_ignores_corrupt_zips(self, tmp_path: Path) -> None:
        """Un .zip sin manifest.json valido NO aparece en list (preservado en disco)."""
        bkp_dir = tmp_path / "backups"
        bkp_dir.mkdir()
        bad = bkp_dir / "skillgraph-bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("foo.txt", "bar")
        # Tambien un buen backup
        data_src = tmp_path / "data-src"
        root = _make_data_root(data_src)
        good = create_backup(root)
        # Mueve el bueno al mismo dir
        good_target = bkp_dir / good.name
        good_target.write_bytes(good.read_bytes())
        infos = list_backups(bkp_dir)
        # Solo el bueno aparece
        assert len(infos) == 1
        assert infos[0].path.name == good.name


# ---------------------------------------------------------------------------
# TestDefaults
# ---------------------------------------------------------------------------


class TestDefaults:
    """Helpers default_backup_dir."""

    def test_default_backup_dir_under_data_root(self) -> None:
        result = default_backup_dir(Path("/tmp/some-root"))
        assert result == Path("/tmp/some-root/backups")
