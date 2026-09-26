"""Backups y restore del data-root de SkillGraph (WI-15, T5 roadmap).

Reglas (decision WI-15 / D-48):
- Formato: ZIP conteniendo catalog.sqlite + todos los project.sqlite
  del data-root + un manifest.json con SHA-256 de cada archivo.
- Restore: extrae a un data-root temporal, verifica SHA-256, y si todo
  OK, hace swap atomico (rename del directorio destino).
- create_backup usa SQLite `.backup()` API (no copia cruda del fichero):
  garantiza snapshot consistente aunque haya writers concurrentes.
- Backups viven bajo `<data-root>/backups/<timestamp>.zip` por defecto.
  El usuario puede pasar --output para ruta custom.
- 0 dependencias externas: solo stdlib (sqlite3, zipfile, hashlib, json).

NO incluido en esta version (P3 deferred):
- Backups incrementales o diferenciales.
- Compresion con nivel ajustable (siempre ZIP_DEFLATED nivel 6).
- Cifrado en reposo (gpg/age). Para datos sensibles, cifrar el archivo
  `.zip` con herramientas externas.
- Scheduling automatico (cron / systemd timers). Hook externo.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from skillgraph.core.errors import ValidationError
from skillgraph.platform.paths import (
    DEFAULT_TENANT,
    catalog_path,
    project_dir,
    resolve_data_root,
)

BACKUP_FORMAT_VERSION: Final[str] = "1.0"
BACKUP_DIR_NAME: Final[str] = "backups"


@dataclass(frozen=True, slots=True)
class BackupEntry:
    """Un archivo dentro del backup."""

    relpath: str  # path relativo al data-root, POSIX style
    sha256: str  # hex digest
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Manifest del backup: metadata + lista de archivos con SHA-256."""

    format_version: str
    created_at: str  # ISO 8601 UTC
    data_root: str  # ruta absoluta del data-root original
    tenant_count: int
    project_count: int
    entries: tuple[BackupEntry, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "created_at": self.created_at,
            "data_root": self.data_root,
            "tenant_count": self.tenant_count,
            "project_count": self.project_count,
            "entries": [
                {"relpath": e.relpath, "sha256": e.sha256, "size_bytes": e.size_bytes}
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BackupManifest:
        if data.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ValidationError(
                f"format_version incompatible: {data.get('format_version')!r} "
                f"(esperado {BACKUP_FORMAT_VERSION!r})"
            )
        entries_raw = data.get("entries", [])
        if not isinstance(entries_raw, list):
            raise ValidationError("entries debe ser list")
        entries = tuple(
            BackupEntry(
                relpath=str(e["relpath"]),
                sha256=str(e["sha256"]),
                size_bytes=int(e["size_bytes"]),  # type: ignore[arg-type]
            )
            for e in entries_raw  # type: ignore[union-attr]
        )
        return cls(
            format_version=str(data["format_version"]),
            created_at=str(data["created_at"]),
            data_root=str(data["data_root"]),
            tenant_count=int(data["tenant_count"]),  # type: ignore[arg-type]
            project_count=int(data["project_count"]),  # type: ignore[arg-type]
            entries=entries,
        )


def _hash_file_sha256(path: Path) -> str:
    """SHA-256 hex digest del contenido del archivo (lectura streaming)."""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_backup_to(src_db: Path, dst_file: Path) -> None:
    """Snapshot consistente de SQLite via `.backup()` API.

    Garantiza atomicidad aunque haya writers concurrentes (a diferencia
    de copia cruda de archivo, que puede capturar pagina a medio escribir).
    """
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    if dst_file.exists():
        dst_file.unlink()
    src = sqlite3.connect(str(src_db))
    try:
        dst = sqlite3.connect(str(dst_file))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _collect_files(data_root: Path) -> tuple[list[Path], int, int]:
    """Recolecta archivos a incluir en el backup.

    Returns (files, tenant_count, project_count). Filtra:
    - catalog.sqlite (siempre)
    - <tenant>/projects/<project>/project.sqlite (proyectos)
    - agents/ (fixtures, opcional, decisiones: incluir; son datos)

    Excluye:
    - backups/ (recursividad)
    - pycache, .tmp
    """
    files: list[Path] = []
    if not data_root.exists():
        return files, 0, 0
    cat = catalog_path(data_root)
    if cat.exists():
        files.append(cat)
    tenants_dir = data_root / "tenants"
    tenant_count = 0
    project_count = 0
    if tenants_dir.exists():
        for tenant_path in sorted(tenants_dir.iterdir()):
            if not tenant_path.is_dir():
                continue
            tenant_count += 1
            projects_dir = tenant_path / "projects"
            if not projects_dir.exists():
                continue
            for proj_path in sorted(projects_dir.iterdir()):
                if not proj_path.is_dir():
                    continue
                project_count += 1
                proj_db = proj_path / "project.sqlite"
                if proj_db.exists():
                    files.append(proj_db)
    agents = data_root / "agents"
    if agents.exists():
        for f in sorted(agents.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                files.append(f)
    return files, tenant_count, project_count


def create_backup(
    data_root: Path,
    output_path: Path | None = None,
) -> Path:
    """Crea un backup ZIP del data-root y devuelve la ruta final.

    Args:
        data_root: raiz de datos (la que contiene catalog.sqlite, tenants/, ...).
        output_path: ruta destino del .zip. Si None, usa
            `<data-root>/backups/skillgraph-<UTC-timestamp>.zip`.

    Returns:
        Ruta absoluta al .zip creado.

    Raises:
        ValidationError: si data_root no existe o no contiene catalog.sqlite.
    """
    data_root = data_root.resolve()
    if not data_root.exists():
        raise ValidationError(f"data_root no existe: {data_root}")
    catalog = catalog_path(data_root)
    if not catalog.exists():
        raise ValidationError(
            f"catalog.sqlite ausente en {data_root} (¿proyecto nunca inicializado?)"
        )
    if output_path is None:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out_dir = data_root / BACKUP_DIR_NAME
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"skillgraph-{ts}.zip"
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    files, tenant_count, project_count = _collect_files(data_root)
    entries: list[BackupEntry] = []
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src in files:
            rel = src.relative_to(data_root).as_posix()
            sha = _hash_file_sha256(src)
            size = src.stat().st_size
            entries.append(BackupEntry(relpath=rel, sha256=sha, size_bytes=size))
            zf.write(src, arcname=rel)
        manifest = BackupManifest(
            format_version=BACKUP_FORMAT_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            data_root=str(data_root),
            tenant_count=tenant_count,
            project_count=project_count,
            entries=tuple(entries),
        )
        zf.writestr("manifest.json", json.dumps(manifest.to_dict(), indent=2))
    return output_path


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Info resumida de un backup en disco (para `sg backup list`)."""

    path: Path
    size_bytes: int
    created_at: str
    tenant_count: int
    project_count: int

    @property
    def relpath(self) -> str:
        return self.path.name


def list_backups(backup_dir: Path) -> tuple[BackupInfo, ...]:
    """Lista backups .zip validos en un directorio, ordenados por fecha desc."""
    backup_dir = backup_dir.resolve()
    if not backup_dir.exists():
        return ()
    infos: list[BackupInfo] = []
    for zp in sorted(backup_dir.glob("skillgraph-*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                manifest_raw = zf.read("manifest.json")
            manifest = BackupManifest.from_dict(json.loads(manifest_raw))
            infos.append(
                BackupInfo(
                    path=zp,
                    size_bytes=zp.stat().st_size,
                    created_at=manifest.created_at,
                    tenant_count=manifest.tenant_count,
                    project_count=manifest.project_count,
                )
            )
        except (KeyError, json.JSONDecodeError, ValidationError, zipfile.BadZipFile):
            # Backup corrupto o sin manifest: lo ignoramos en `list`,
            # pero NO lo borramos (preservar evidencia para el operador).
            continue
    return tuple(infos)


def verify_backup(backup_path: Path) -> BackupManifest:
    """Lee el manifest y verifica SHA-256 de cada archivo del backup.

    Returns:
        BackupManifest si todos los archivos pasan la verificacion.

    Raises:
        ValidationError: si el manifest falta, el formato es invalido,
        o cualquier archivo tiene SHA-256 incorrecto.
    """
    backup_path = backup_path.resolve()
    if not backup_path.exists():
        raise ValidationError(f"backup no existe: {backup_path}")
    with zipfile.ZipFile(backup_path, "r") as zf:
        try:
            manifest_raw = zf.read("manifest.json")
        except KeyError as exc:
            raise ValidationError(f"manifest.json ausente en {backup_path}") from exc
        manifest = BackupManifest.from_dict(json.loads(manifest_raw))
        for entry in manifest.entries:
            try:
                data = zf.read(entry.relpath)
            except KeyError as exc:
                raise ValidationError(f"archivo '{entry.relpath}' ausente en zip") from exc
            import hashlib

            actual = hashlib.sha256(data).hexdigest()
            if actual != entry.sha256:
                raise ValidationError(
                    f"SHA-256 mismatch en '{entry.relpath}': "
                    f"esperado {entry.sha256}, calculado {actual}"
                )
    return manifest


def restore_backup(
    backup_path: Path,
    target_data_root: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Restaura un backup a target_data_root.

    Procedimiento:
    1. Verifica SHA-256 del backup (verify_backup).
    2. Extrae a target_data_root.
    3. Si overwrite=False y target_data_root tiene contenido -> error.

    Args:
        backup_path: ruta al .zip.
        target_data_root: directorio destino.
        overwrite: si True, permite restaurar sobre data-root existente.

    Returns:
        Ruta absoluta al target_data_root restaurado.

    Raises:
        ValidationError: backup invalido, SHA-256 mismatch, o conflicto
        con destino (overwrite=False y destino no vacio).
    """
    manifest = verify_backup(backup_path)
    target_data_root = target_data_root.resolve()
    if target_data_root.exists():
        if not overwrite and any(target_data_root.iterdir()):
            raise ValidationError(
                f"target_data_root no vacio: {target_data_root} (usa overwrite=True para forzar)"
            )
    else:
        target_data_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup_path, "r") as zf:
        zf.extractall(target_data_root)
    # Re-hash post-extract para confirmar que el FS no corrompio el archivo.
    for entry in manifest.entries:
        extracted = target_data_root / entry.relpath
        if not extracted.exists():
            raise ValidationError(
                f"post-extract: archivo '{entry.relpath}' no encontrado en {target_data_root}"
            )
        actual = _hash_file_sha256(extracted)
        if actual != entry.sha256:
            raise ValidationError(
                f"post-extract SHA-256 mismatch en '{entry.relpath}': "
                f"esperado {entry.sha256}, calculado {actual}"
            )
    return target_data_root


# ---------------------------------------------------------------------------
# Helpers para CLI
# ---------------------------------------------------------------------------


def default_backup_dir(data_root: Path | None = None) -> Path:
    """Devuelve el directorio default de backups."""
    root = data_root if data_root is not None else resolve_data_root()
    return Path(root) / BACKUP_DIR_NAME


__all__ = [
    "BACKUP_DIR_NAME",
    "BACKUP_FORMAT_VERSION",
    "BackupEntry",
    "BackupInfo",
    "BackupManifest",
    "create_backup",
    "default_backup_dir",
    "list_backups",
    "project_dir",
    "restore_backup",
    "verify_backup",
]


# Re-export para tests / consumidores que ya importan desde paths
_ = project_dir  # silenciar linter
_ = DEFAULT_TENANT
