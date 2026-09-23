"""Almacenamiento SQLite para SkillGraph (Etapa 0/1 / spike S1).

Decisiones de diseño (external/blueprint-v1/docs/09-persistencia.md):
- Bases separadas por tenant/proyecto; aquí usamos una sola base SQLite
  por proyecto, indexada por tenant_id/project_id en cada tabla para
  reforzar el aislamiento en queries.
- WAL activado para lectores concurrentes.
- Interfaz `Storage` no expone SQL directo: futuras migraciones (S2)
  no deberían tocar el código de controladores.

Auditoría de duplicación:
- Esta clase NO reemplaza al parser ni al registro. Toma `Brick` ya
  validado (doc 03 + doc 04) y lo persiste.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from skillgraph.bricks import Brick
from skillgraph.errors import IdentityConflictError, ValidationError

SCHEMA_VERSION = 1


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS resources (
    uid TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    api_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    namespace TEXT NOT NULL,
    name TEXT NOT NULL,
    resource_version INTEGER NOT NULL DEFAULT 1,
    generation INTEGER NOT NULL DEFAULT 1,
    spec_json TEXT NOT NULL,
    status_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tenant_id, project_id, api_version, kind, namespace, name)
);

CREATE INDEX IF NOT EXISTS resources_by_kind
    ON resources(tenant_id, project_id, api_version, kind);
CREATE INDEX IF NOT EXISTS resources_by_name
    ON resources(tenant_id, project_id, namespace, name);

CREATE TABLE IF NOT EXISTS relations (
    uid TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_uid TEXT NOT NULL,
    target_uid TEXT NOT NULL,
    kind TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (source_uid) REFERENCES resources(uid) ON DELETE CASCADE,
    FOREIGN KEY (target_uid) REFERENCES resources(uid) ON DELETE CASCADE,
    UNIQUE (source_uid, target_uid, kind)
);

CREATE INDEX IF NOT EXISTS relations_by_source
    ON relations(tenant_id, project_id, source_uid, kind);
CREATE INDEX IF NOT EXISTS relations_by_target
    ON relations(tenant_id, project_id, target_uid, kind);

CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    resource_uid TEXT NOT NULL,
    phase TEXT NOT NULL,
    result_ref TEXT
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    state TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    current_node TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS workflow_runs_by_state
    ON workflow_runs(tenant_id, project_id, state);

CREATE TABLE IF NOT EXISTS node_executions (
    node_execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL,
    outcome TEXT,
    context_hash TEXT,
    handoff_json TEXT,
    result_json TEXT,
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS node_executions_by_run
    ON node_executions(tenant_id, project_id, run_id, node_name);
CREATE INDEX IF NOT EXISTS node_executions_by_state
    ON node_executions(tenant_id, project_id, state);

CREATE TABLE IF NOT EXISTS runtime_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    run_id TEXT,
    resource_ref TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_run
    ON runtime_events(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS events_by_resource
    ON runtime_events(tenant_id, project_id, resource_ref);
"""


def _uid(brick: Brick) -> str:
    """UID determinista por (tenant, project, apiVersion, kind, namespace, name).

    El blueprint (doc 03 §3) deja la elección al núcleo. Aquí usamos un
    UID estable pero NO un hash criptográfico: las revisiones usan un
    contador (resource_version) y la identidad de los `Brick` ya viene
    garantizada por la UNIQUE constraint de la tabla.
    """
    i = brick.identity
    return f"{i.tenant_id}/{i.project_id}/{brick.api_version}/{brick.kind}/{i.namespace}/{i.name}"


class Storage:
    """Interfaz de almacenamiento para un proyecto.

    Diseñada para fallar rápido en errores de identidad y validación,
    sin exponer SQL a los controladores.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # `check_same_thread=False` permite reuso desde threads de pytest
        # (los tests no usan threads todavía, pero la propiedad
        # es útil cuando entremos a Etapa 2).
        self._conn = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    # ----- ciclo de vida -----

    def _migrate(self) -> None:
        with self._tx() as cur:
            cur.executescript(_SCHEMA_SQL)
            row = cur.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO schema_version(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        # Aislamiento "deferred" por defecto de sqlite3; el commit ocurre
        # al salir del bloque sin error. Si algo lanza, sqlite3 hace rollback.
        with self._conn:
            yield self._conn.cursor()

    # ----- recursos -----

    def upsert_resource(self, brick: Brick) -> str:
        """Registra un brick. Lanza `IdentityConflictError` si cambia
        `spec` bajo la misma identidad (versión bumped +409 conflict).
        """
        import json

        uid = _uid(brick)
        spec_json = json.dumps(brick.spec, sort_keys=True)
        with self._tx() as cur:
            existing = cur.execute(
                "SELECT spec_json FROM resources WHERE uid = ?", (uid,)
            ).fetchone()
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO resources
                        (uid, tenant_id, project_id, api_version, kind,
                         namespace, name, spec_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        brick.identity.tenant_id,
                        brick.identity.project_id,
                        brick.api_version,
                        brick.kind,
                        brick.identity.namespace,
                        brick.identity.name,
                        spec_json,
                    ),
                )
            else:
                if existing["spec_json"] != spec_json:
                    raise IdentityConflictError(f"Identidad ya registrada con spec distinto: {uid}")
                # Si el spec coincide, upsert idempotente (no incrementa rev).
        return uid

    def get_resource(self, uid: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM resources WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_resources(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM resources WHERE tenant_id = ? AND project_id = ?"
        params: tuple[Any, ...] = (tenant_id, project_id)
        if kind is not None:
            sql += " AND api_version || '/' || kind = ? OR kind = ?"
            params = (tenant_id, project_id, kind, kind)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ----- relaciones -----

    def add_relation(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_uid: str,
        target_uid: str,
        kind: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Crea una relación REQUIRES/DEPENDS_ON/etc. idempotente."""
        import json
        import uuid

        properties = properties or {}
        props_json = json.dumps(properties, sort_keys=True)
        rid = str(uuid.uuid4())
        with self._tx() as cur:
            existing = cur.execute(
                """
                SELECT uid FROM relations
                WHERE tenant_id = ? AND project_id = ?
                  AND source_uid = ? AND target_uid = ? AND kind = ?
                """,
                (tenant_id, project_id, source_uid, target_uid, kind),
            ).fetchone()
            if existing is not None:
                return existing["uid"]
            cur.execute(
                """
                INSERT INTO relations
                    (uid, tenant_id, project_id, source_uid,
                     target_uid, kind, properties_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    tenant_id,
                    project_id,
                    source_uid,
                    target_uid,
                    kind,
                    props_json,
                ),
            )
        return rid

    def dependencies_of(self, uid: str) -> list[dict[str, Any]]:
        """Aristas salientes: 'qué necesita este recurso' (target)."""
        rows = self._conn.execute("SELECT * FROM relations WHERE source_uid = ?", (uid,)).fetchall()
        return [dict(r) for r in rows]

    def dependents_of(self, uid: str) -> list[dict[str, Any]]:
        """Aristas entrantes: 'qué recursos apuntan a este' (source)."""
        rows = self._conn.execute("SELECT * FROM relations WHERE target_uid = ?", (uid,)).fetchall()
        return [dict(r) for r in rows]


def open_project_storage(path: str | Path) -> Storage:
    """Ayuda para abrir el almacenamiento de un proyecto.

    Cualquier error de validación aquí es bug: este helper no debería
    recibir paths fuera de los directorios gestionados por la CLI.
    """
    if not str(path).endswith(".sqlite"):
        raise ValidationError(f"Path de proyecto debe terminar en .sqlite: {path}")
    return Storage(path)
