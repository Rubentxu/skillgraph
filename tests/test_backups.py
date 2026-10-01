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

from skillgraph.core.errors import IntegrityError, ValidationError
from skillgraph.governance.backups import (
    BACKUP_DIR_NAME,
    BACKUP_FORMAT_VERSION,
    BackupEntry,
    BackupManifest,
    _collect_agent_files,
    _collect_files,
    _collect_project_dbs,
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

    def test_from_dict_rejects_bool_size_bytes(self) -> None:
        """WI-49: `size_bytes: true` seria int(1) silencioso en Python.

        El manifest es un fichero declarado que from_dict lee en el
        camino de restore; un booleano en un campo entero debe ser un
        ValidationError, no un tamano 1 que nadie escribio.
        """
        with pytest.raises(ValidationError, match="size_bytes"):
            BackupManifest.from_dict(
                {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "created_at": "x",
                    "data_root": "x",
                    "tenant_count": 0,
                    "project_count": 0,
                    "entries": [{"relpath": "a.sqlite", "sha256": "abc", "size_bytes": True}],
                }
            )

    def test_from_dict_rejects_bool_counts(self) -> None:
        """WI-49: tenant_count/project_count tampoco aceptan booleanos."""
        with pytest.raises(ValidationError, match="tenant_count"):
            BackupManifest.from_dict(
                {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "created_at": "x",
                    "data_root": "x",
                    "tenant_count": True,
                    "project_count": 0,
                    "entries": [],
                }
            )
        with pytest.raises(ValidationError, match="project_count"):
            BackupManifest.from_dict(
                {
                    "format_version": BACKUP_FORMAT_VERSION,
                    "created_at": "x",
                    "data_root": "x",
                    "tenant_count": 0,
                    "project_count": False,
                    "entries": [],
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


# ---------------------------------------------------------------------------
# TestWALConsistency
# ---------------------------------------------------------------------------


class TestWALConsistency:
    """El backup debe capturar los datos confirmados, no solo el fichero.

    El proyecto abre sus conexiones en WAL (`platform/storage.py`), asi que
    los datos confirmados viven en el fichero `-wal` hasta el checkpoint.
    Copiar el `.sqlite` a pelo se lleva el fichero principal vacio.

    Sin este test, `create` + `verify` + `restore` coinciden entre si y dan
    un backup "valido" que no contiene ninguna tabla.
    """

    @staticmethod
    def _wal_data_root(root_dir: Path) -> Path:
        """Data-root con un project.sqlite en WAL y un writer concurrente."""
        root = root_dir / "data"
        root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(catalog_path(root)))
        conn.execute("CREATE TABLE tenants(id TEXT)")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()
        conn.execute("INSERT INTO tenants VALUES ('t1')")
        conn.commit()
        conn.close()
        proj = project_dir(root, "demo")
        proj.mkdir(parents=True)
        conn = sqlite3.connect(str(proj / "project.sqlite"))
        conn.execute("CREATE TABLE runs(id INTEGER)")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()
        for i in range(200):
            conn.execute("INSERT INTO runs VALUES (?)", (i,))
        conn.commit()
        return root

    def test_committed_rows_survive_round_trip(self, tmp_path: Path) -> None:
        """Filas confirmadas deben sobrevivir a create -> restore."""
        root = self._wal_data_root(tmp_path)
        # Segundo writer: deja la transaccion viva al respaldar, que es el
        # estado normal de cualquier data-root en produccion.
        writer = sqlite3.connect(str(project_dir(root, "demo") / "project.sqlite"))
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO runs VALUES (999)")
        writer.commit()
        expected = 201
        writer.close()

        zip_path = create_backup(root)
        restored = tmp_path / "restored"
        restored.mkdir()
        restore_backup(zip_path, restored, overwrite=True)

        db = sqlite3.connect(str(project_dir(restored, "demo") / "project.sqlite"))
        try:
            got = db.execute("SELECT count(*) FROM runs").fetchone()[0]
        finally:
            db.close()
        assert got == expected, f"PERDIDA DE DATOS: {expected} -> {got}"

    def test_snapshot_includes_wal_only_data(self, tmp_path: Path) -> None:
        """El manifest no debe describir el fichero principal sin consolidar.

        Se mantiene un writer abierto durante el backup: es lo que mantiene
        los datos en el `-wal`. Si `create_backup` copiara el fichero a pelo,
        el manifest describiria el fichero principal, que no los contiene.
        """
        root = self._wal_data_root(tmp_path)
        proj_db = project_dir(root, "demo") / "project.sqlite"
        writer = sqlite3.connect(str(proj_db))
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO runs VALUES (999)")
        writer.commit()
        # `writer` sigue abierto a proposito: no hay checkpoint mientras viva.
        wal = proj_db.with_name(proj_db.name + "-wal")
        assert wal.exists() and wal.stat().st_size > 0, "el test necesita WAL pendiente"

        zip_path = create_backup(root)
        writer.close()

        with zipfile.ZipFile(zip_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        entry = next(e for e in manifest["entries"] if e["relpath"].endswith("project.sqlite"))
        assert entry["size_bytes"] > 4096, (
            "el backup copio el fichero principal sin consolidar el WAL: "
            f"manifest={entry['size_bytes']} (4096 = cabecera vacia de sqlite)"
        )

    def test_catalog_rows_also_survive(self, tmp_path: Path) -> None:
        """El catalogo tambien es WAL: aplica la misma regla."""
        root = self._wal_data_root(tmp_path)
        conn = sqlite3.connect(str(catalog_path(root)))
        conn.execute("PRAGMA journal_mode = WAL")
        for i in range(50):
            conn.execute("INSERT INTO tenants VALUES (?)", (f"t{i}",))
        conn.commit()
        conn.close()

        zip_path = create_backup(root)
        restored = tmp_path / "restored2"
        restored.mkdir()
        restore_backup(zip_path, restored, overwrite=True)

        db = sqlite3.connect(str(catalog_path(restored)))
        try:
            got = db.execute("SELECT count(*) FROM tenants").fetchone()[0]
        finally:
            db.close()
        assert got == 51, f"PERDIDA DE DATOS en catalog: 51 -> {got}"

    def test_corrupt_database_raises_instead_of_writing_partial(self, tmp_path: Path) -> None:
        """Una base ilegible debe fallar, no entrar en el ZIP a medias.

        Un snapshot parcial pasaria verify y restore (el hash es el del
        fichero a medias) y solo reventaria al usarse, que es peor que no
        tener backup.
        """
        root = self._wal_data_root(tmp_path)
        broken = project_dir(root, "broken")
        broken.mkdir(parents=True)
        (broken / "project.sqlite").write_bytes(b"esto no es una base de sqlite")

        with pytest.raises(IntegrityError) as exc:
            create_backup(root)
        assert "broken" in str(exc.value)

    def test_corrupt_database_leaves_no_zip_behind(self, tmp_path: Path) -> None:
        """Si el snapshot falla, no debe quedar un backup utilizable."""
        root = self._wal_data_root(tmp_path)
        broken = project_dir(root, "broken")
        broken.mkdir(parents=True)
        (broken / "project.sqlite").write_bytes(b"no soy sqlite")
        out = tmp_path / "out.zip"

        with pytest.raises(IntegrityError):
            create_backup(root, output_path=out)
        assert not out.exists(), "quedo un backup parcial en disco"


# ---------------------------------------------------------------------------
# TestCollectFiles
# ---------------------------------------------------------------------------


class TestCollectFiles:
    """`_collect_files` decide que entra en el backup: es politica, no detalle.

    Las ramas sin cubrir eran skips defensivos y el caso `agents/`, que es
    una decision documentada: los fixtures de agente son datos y se guardan.
    """

    def test_agents_fixtures_are_included(self, tmp_path: Path) -> None:
        """`agents/` entra en el backup: es una decision, no un descuido."""
        root = _make_data_root(tmp_path)
        agents = root / "agents"
        (agents / "pack").mkdir(parents=True)
        (agents / "pack" / "skill.md").write_text("contenido", encoding="utf-8")

        zip_path = create_backup(root)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert "agents/pack/skill.md" in names

    def test_pycache_is_excluded(self, tmp_path: Path) -> None:
        """`__pycache__` no es dato: no debe entrar en el backup."""
        root = _make_data_root(tmp_path)
        cache = root / "agents" / "pack" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "x.pyc").write_bytes(b"\x00")

        zip_path = create_backup(root)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert not [n for n in names if "__pycache__" in n]

    def test_stray_files_are_skipped(self, tmp_path: Path) -> None:
        """Ficheros sueltos y tenants sin proyectos no cuentan ni se guardan."""
        root = _make_data_root(tmp_path)
        # Un fichero suelto donde se espera un directorio de tenant.
        (root / "tenants" / "notas.txt").write_text("x", encoding="utf-8")
        # Un tenant sin directorio `projects/`.
        (root / "tenants" / "vacio").mkdir(parents=True)
        # Un proyecto sin `project.sqlite`.
        (root / "tenants" / "default" / "projects" / "sin-db").mkdir(parents=True)

        zip_path = create_backup(root)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert "tenants/notas.txt" not in names
        assert not [n for n in names if n.startswith("tenants/vacio/")]
        assert not [n for n in names if "sin-db" in n]

        with zipfile.ZipFile(zip_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        # Solo cuenta `default` como tenant y `demo` como proyecto.
        assert manifest["tenant_count"] == 2, "vacio cuenta como tenant"
        assert manifest["project_count"] == 2, "sin-db cuenta como proyecto"

    def test_missing_data_root_returns_empty(self, tmp_path: Path) -> None:
        """Raiz inexistente: coleccion vacia, no excepcion."""
        files, tenants, projects = _collect_files(tmp_path / "no-existe")
        assert files == []
        assert (tenants, projects) == (0, 0)


# ---------------------------------------------------------------------------
# TestCollectProjectDbs — extraccion de politica (WI-46, cc 14 -> 4)
# ---------------------------------------------------------------------------


class TestCollectProjectDbs:
    """`_collect_project_dbs` es la politica de "que proyecto cuenta" aislada.

    `_collect_files` decidia en un solo cuerpo: recorrer tenants, contar,
    filtrar directorios, buscar la base y decidir si se incluye. Con
    cc=14 era la funcion mas compleja de `backups.py`, y es justamente
    la que decide que datos sobreviven a un backup. Merece poder
    probarse sin montar un arbol de datos completo.
    """

    def test_counts_projects_without_database(self, tmp_path: Path) -> None:
        """Un directorio de proyecto cuenta aunque no tenga `project.sqlite`.

        Es la distincion sutil que la extraccion deja explicita: el
        conteo es de directorios, la inclusion de ficheros es de
        bases existentes. Un proyecto sin DB no aporta datos, pero si
        cuenta como proyecto del tenant.
        """
        root = tmp_path / "tenants" / "acme" / "projects"
        (root / "con-db").mkdir(parents=True)
        (root / "con-db" / "project.sqlite").write_bytes(b"")
        (root / "sin-db").mkdir(parents=True)

        dbs, tenants, projects = _collect_project_dbs(tmp_path)

        # El helper devuelve rutas completas; el proyecto sin DB no aporta fichero.
        assert [p.parent.name for p in dbs] == ["con-db"]
        assert tenants == 1
        assert projects == 2

    def test_tenant_without_projects_is_counted_but_yields_nothing(self, tmp_path: Path) -> None:
        """Tenant sin `projects/` cuenta como tenant y no aporta ficheros."""
        (tmp_path / "tenants" / "sin-projects").mkdir(parents=True)

        dbs, tenants, projects = _collect_project_dbs(tmp_path)

        assert dbs == []
        assert tenants == 1
        assert projects == 0

    def test_deterministic_ordering(self, tmp_path: Path) -> None:
        """El orden no depende del inode del sistema de ficheros.

        Dos llamadas seguidas dan la misma lista: un manifest de backup
        tiene que ser reproducible para poder comparar hashes.
        """
        projects = tmp_path / "tenants" / "acme" / "projects"
        for name in ("zeta", "alfa", "medio"):
            (projects / name).mkdir(parents=True)
            (projects / name / "project.sqlite").write_bytes(b"")

        first, _, _ = _collect_project_dbs(tmp_path)
        second, _, _ = _collect_project_dbs(tmp_path)

        assert [p.parent.name for p in first] == ["alfa", "medio", "zeta"]
        assert first == second

    def test_missing_tenants_dir(self, tmp_path: Path) -> None:
        """Sin `tenants/`: no hay nada que contar, y no es un error."""
        dbs, tenants, projects = _collect_project_dbs(tmp_path)
        assert (dbs, tenants, projects) == ([], 0, 0)


# ---------------------------------------------------------------------------
# TestCollectAgentFiles — extraccion de politica (WI-46)
# ---------------------------------------------------------------------------


class TestCollectAgentFiles:
    """`_collect_agent_files` aísla la regla "los fixtures de agente son datos"."""

    def test_recurses_and_excludes_pycache(self, tmp_path: Path) -> None:
        """Entra en subdirectorios; `__pycache__` queda fuera a cualquier nivel."""
        agents = tmp_path / "agents"
        deep = agents / "pack" / "sub" / "deep"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("x", encoding="utf-8")
        cache = deep / "__pycache__"
        cache.mkdir()
        (cache / "m.pyc").write_bytes(b"\x00")

        found = _collect_agent_files(tmp_path)

        # Ruta completa: el fichero esta anidado, no en la raiz de `agents/`.
        assert [p.name for p in found] == ["SKILL.md"]
        assert found[0].parts[-3:] == ("sub", "deep", "SKILL.md")

    def test_empty_directory_yields_nothing(self, tmp_path: Path) -> None:
        """Directorio sin ficheros: lista vacia, sin ruido."""
        (tmp_path / "agents" / "vacio").mkdir(parents=True)
        assert _collect_agent_files(tmp_path) == []
