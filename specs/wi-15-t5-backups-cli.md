# WI-15: T5 Backups CLI (sg backup create|list|restore)

## Objetivo

Implementar el feature T5 del roadmap: backups del data-root local
con verificación criptográfica, formato portable y restore a un
directorio destino. Cumple la promesa del blueprint
`Backups y migraciones` (ROADMAP §3).

## Decision previa (D-48)

- **Formato**: ZIP contenedor de catalog.sqlite + todos los
  project.sqlite + un `manifest.json` con SHA-256 de cada archivo.
- **Atomicidad SQLite**: usar la API `Connection.backup()` (no copia
  cruda del archivo). Garantiza snapshot consistente aunque haya
  writers concurrentes en el proyecto origen.
- **Restore seguro**: `verify_backup` (SHA-256 de cada archivo en
  el zip) + re-hash post-extract para confirmar que el FS no
  corrompio el archivo. Falla atomica ante cualquier mismatch.
- **CLI minima viable**: `sg backup create|list|restore` con
  sub-comandos argparse. NO incluyo scheduling automatico (P3 deferred).
- **0 dependencias externas**: solo stdlib (sqlite3, zipfile,
  hashlib, json, pathlib). Sin boto3, sin cryptography.
- **Cifrado en reposo NO incluido** (P3 deferred): si el operador
  quiere cifrar el `.zip`, usa gpg/age externamente.

## Cambios

### `src/skillgraph/governance/backups.py` (nuevo, ~395 LoC)

API publica:

- `create_backup(data_root, output_path=None) -> Path`
- `list_backups(backup_dir) -> tuple[BackupInfo, ...]`
- `verify_backup(backup_path) -> BackupManifest`
- `restore_backup(backup_path, target_data_root, *, overwrite=False) -> Path`
- `default_backup_dir(data_root=None) -> Path`

Tipos:
- `BackupEntry` (dataclass frozen/slots): relpath + sha256 + size_bytes.
- `BackupManifest`: format_version + created_at + data_root +
  tenant_count + project_count + entries.
- `BackupInfo`: path + size_bytes + created_at + tenant_count + project_count.

Constantes:
- `BACKUP_FORMAT_VERSION = "1.0"`
- `BACKUP_DIR_NAME = "backups"`

### `src/skillgraph/cli/runner.py`

- Sub-parser `backup` con 3 sub-comandos:
  - `sg backup create` (sin args adicionales).
  - `sg backup list [--dir <path>]`.
  - `sg backup restore <backup> <target> [--overwrite]`.
- Dispatcher `cmd_backup` + helpers `cmd_backup_{create,list,restore}`.

### `tests/test_backups.py` (nuevo, 22 tests, 6 clases)

- `TestBackupManifest`: round-trip JSON, formato invalido.
- `TestCreateBackup`: ZIP con manifest, custom output_path, default
  data-root, errores (data_root ausente, catalog ausente), counts.
- `TestVerifyBackup`: SHA-256 OK, manifest faltante, archivo faltante
  en zip, SHA mismatch, zip inexistente.
- `TestRestoreBackup`: roundtrip create->restore, post-extract re-hash.
- `TestListBackups`: dir vacio, orden desc, filtrado de corruptos.
- `TestDefaults`: helper `default_backup_dir`.

## Compatibilidad

- **Backward-compatible 100%**: agrega 1 sub-comando (`backup`) sin
  modificar los existentes.
- **0 cambios en API publica** del resto del proyecto.

## Evidencia

- `uv run pytest tests/test_backups.py` -> 22/22 PASS
- `uv run pytest` (suite completa) -> **1044/1044 PASS** en 180.48s
  (era 1022, +22 tests nuevos)
- `uv run ruff check src tests` -> All checks passed
- `sg backup --help` muestra los 3 sub-comandos correctamente

## Pendiente tras WI-15

- **WI-16 (T6 Observabilidad runbook)**: docs + sinks.
- **WI-17+ (deuda arquitectónica)**: H-01..H-10.
- Bump `0.14.6.dev0 → 0.14.7` con WI-12/13/14/15/16 acumulados
  (FEAT x3 + DOC x1 + CLI x1 suficiente para MINOR bump).
- Push a origin (regla WI-01).
