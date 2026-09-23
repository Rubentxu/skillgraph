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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC
from pathlib import Path
from typing import Any

from skillgraph.core.errors import IdentityConflictError, NotFoundError, ValidationError
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)
from skillgraph.resources.bricks import Brick

SCHEMA_VERSION = 1


# Estados validos del outbox de promocion (CHECK constraint de la tabla).
# Exportado como frozenset para que Storage.list_promotions() valide
# inputs sin acoplarse a la implementacion del schema.
PROMOTION_STATUSES: frozenset[str] = frozenset({"PENDING", "IN_PROGRESS", "PUBLISHED", "FAILED"})

# Estados no terminales de workflow_runs (CREATED/ACTIVE/WAITING).
# Un run en cualquiera de estos estados se considera "vivo": si el proceso
# muere, un nuevo `sg run` debe reanudar el mismo run_id en lugar de
# crear uno nuevo (cumple UAT-06).
NON_TERMINAL_RUN_STATES: frozenset[str] = frozenset({"CREATED", "ACTIVE", "WAITING"})


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

-- ============================================================
-- H3 Slice 1: tablas del subsistema de conocimiento
-- ============================================================
-- 7 tablas nuevas (sources, entities, evidences, claims,
-- claim_evidence, findings, outcome_traces, outcome_trace_links).
-- NO se modifican tablas existentes: el bloque CREATE TABLE
-- IF NOT EXISTS es idempotente y los ALTER no son necesarios.

CREATE TABLE IF NOT EXISTS sources (
    source_id        TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    locator_json     TEXT NOT NULL,
    git_commit_sha   TEXT,
    git_tree_sha     TEXT,
    working_tree_status_json TEXT,
    checked_at       TEXT NOT NULL,
    freshness        TEXT NOT NULL DEFAULT 'fresh'
);
CREATE INDEX IF NOT EXISTS idx_sources_project
    ON sources(tenant_id, project_id);

CREATE TABLE IF NOT EXISTS entities (
    entity_id        TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    stable_key       TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, kind, stable_key)
);

CREATE TABLE IF NOT EXISTS evidences (
    evidence_id      TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    content_json     TEXT NOT NULL,
    source_id        TEXT NOT NULL REFERENCES sources(source_id),
    observed_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id              TEXT PRIMARY KEY,
    tenant_id             TEXT NOT NULL,
    project_id            TEXT NOT NULL,
    subject_entity_id     TEXT NOT NULL REFERENCES entities(entity_id),
    predicate             TEXT NOT NULL,
    object_literal_json   TEXT NOT NULL,
    source_id             TEXT NOT NULL REFERENCES sources(source_id),
    extraction_method     TEXT NOT NULL,
    extractor_version     TEXT NOT NULL,
    checked_at_revision   TEXT NOT NULL,
    stale                 INTEGER NOT NULL DEFAULT 0,
    UNIQUE (subject_entity_id, predicate, source_id, checked_at_revision)
);
CREATE INDEX IF NOT EXISTS idx_claims_subject
    ON claims(subject_entity_id, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_stale
    ON claims(stale) WHERE stale = 1;

CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id      TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_id   TEXT NOT NULL REFERENCES evidences(evidence_id),
    PRIMARY KEY (claim_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id          TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    entity_id           TEXT NOT NULL REFERENCES entities(entity_id),
    observation         TEXT NOT NULL,
    rule_ref            TEXT NOT NULL,
    rule_version        TEXT NOT NULL,
    evidence_ids_json   TEXT NOT NULL,
    result              TEXT NOT NULL,
    valid_until_revision TEXT
);

CREATE TABLE IF NOT EXISTS outcome_traces (
    trace_id      TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    project_id    TEXT NOT NULL,
    kind          TEXT NOT NULL,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcome_trace_links (
    trace_id      TEXT NOT NULL REFERENCES outcome_traces(trace_id),
    link_kind     TEXT NOT NULL CHECK (link_kind IN ('claim','evidence','relation')),
    link_id       TEXT NOT NULL,
    position      INTEGER NOT NULL,
    PRIMARY KEY (trace_id, link_kind, link_id)
);

-- ============================================================
-- H7 release candidate (UAT-13): outbox de promocion entre bases.
-- Tabla nueva; no se modifica ninguna tabla existente.
-- ============================================================
-- Una propuesta de promocion es un mensaje de outbox persistente
-- que se aplica idempotentemente del lado destino. Si el proceso
-- se interrumpe entre el INSERT origen y el apply destino, la
-- reconciliacion (status=PENDING) lo completa sin duplicar
-- (idempotency_key = source_project + knowledge_ref).

CREATE TABLE IF NOT EXISTS promotion_outbox (
    proposal_id     TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    tenant_id       TEXT NOT NULL,
    source_project  TEXT NOT NULL,
    target_catalog  TEXT NOT NULL,
    knowledge_ref   TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'IN_PROGRESS', 'PUBLISHED', 'FAILED')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    published_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_promotion_outbox_status
    ON promotion_outbox(status);
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

    # ----- H3 Slice 1: conocimiento (sources, entities, claims, etc.) -----
    #
    # Estas APIs NO son CRUD plano: devuelven los ADT de `skillgraph.knowledge`
    # cuando es posible, y dejan la logica de negocio (invalidacion
    # transitiva, hashing, glosario) al KnowledgeController que se introduce
    # en Slice 2.

    # ---- Sources

    def register_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source: Source,
    ) -> None:
        """Registra una Source. Idempotente por `source_id` (PK)."""
        import json

        locator_json = json.dumps(source.locator, sort_keys=True)
        wts_json = (
            json.dumps(source.working_tree_status, sort_keys=True)
            if source.working_tree_status is not None
            else None
        )
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO sources
                    (source_id, tenant_id, project_id, kind, content_hash,
                     locator_json, git_commit_sha, git_tree_sha,
                     working_tree_status_json, checked_at, freshness)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.source_id,
                    tenant_id,
                    project_id,
                    source.kind,
                    source.content_hash,
                    locator_json,
                    source.git_commit_sha,
                    source.git_tree_sha,
                    wts_json,
                    source.checked_at,
                    source.freshness,
                ),
            )

    def get_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
    ) -> Source | None:
        """Recupera una Source por ID; `None` si no existe."""
        import json

        row = self._conn.execute(
            "SELECT * FROM sources WHERE source_id = ? AND tenant_id = ? AND project_id = ?",
            (source_id, tenant_id, project_id),
        ).fetchone()
        if row is None:
            return None
        return _row_to_source(row, json)

    def update_source_freshness(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        freshness: str,
    ) -> None:
        """Cambia `freshness` de una Source (e.g. fresh -> stale)."""
        with self._tx() as cur:
            cur.execute(
                "UPDATE sources SET freshness = ? WHERE source_id = ? AND tenant_id = ? AND project_id = ?",
                (freshness, source_id, tenant_id, project_id),
            )

    # ---- Entities

    def upsert_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        entity: Entity,
    ) -> None:
        """Inserta o reemplaza una Entity. UNIQUE(kind, stable_key) por tenant/project."""
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO entities
                    (entity_id, tenant_id, project_id, kind, stable_key)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entity.entity_id,
                    tenant_id,
                    project_id,
                    entity.kind,
                    entity.stable_key,
                ),
            )

    def get_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        entity_id: str,
    ) -> Entity | None:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE entity_id = ? AND tenant_id = ? AND project_id = ?",
            (entity_id, tenant_id, project_id),
        ).fetchone()
        if row is None:
            return None
        return Entity(
            entity_id=row["entity_id"],
            kind=row["kind"],
            stable_key=row["stable_key"],
        )

    # ---- Evidences

    def record_evidence(
        self,
        *,
        tenant_id: str,
        project_id: str,
        evidence: Evidence,
    ) -> None:
        """Registra una Evidence (FK a sources). Inmutable: re-registrar con
        mismo `evidence_id` es no-op (INSERT OR IGNORE)."""
        import json

        content_json = (
            json.dumps(evidence.content, sort_keys=True)
            if not isinstance(evidence.content, str)
            else json.dumps(evidence.content)
        )
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO evidences (evidence_id, tenant_id, project_id, kind, content_json, source_id, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence.evidence_id,
                    tenant_id,
                    project_id,
                    evidence.kind,
                    content_json,
                    evidence.source_id,
                    evidence.observed_at,
                ),
            )

    def get_evidences_for_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
    ) -> tuple[Evidence, ...]:
        """Devuelve las Evidences asociadas a un Claim (N:M via claim_evidence)."""
        import json

        rows = self._conn.execute(
            """
            SELECT e.*
            FROM evidences e
            JOIN claim_evidence ce ON ce.evidence_id = e.evidence_id
            JOIN claims c ON c.claim_id = ce.claim_id
            WHERE c.claim_id = ? AND c.tenant_id = ? AND c.project_id = ?
            """,
            (claim_id, tenant_id, project_id),
        ).fetchall()
        return tuple(_row_to_evidence(r, json) for r in rows)

    # ---- Claims

    def record_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim: Claim,
    ) -> str:
        """Registra una Claim. Devuelve su claim_id. Idempotente por
        (subject, predicate, source, checked_at_revision)."""
        import json

        obj_json = json.dumps(claim.object_literal, sort_keys=True)
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR IGNORE INTO claims
                    (claim_id, tenant_id, project_id, subject_entity_id,
                     predicate, object_literal_json, source_id,
                     extraction_method, extractor_version,
                     checked_at_revision, stale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    tenant_id,
                    project_id,
                    claim.subject_entity_id,
                    claim.predicate,
                    obj_json,
                    claim.source_id,
                    claim.extraction_method,
                    claim.extractor_version,
                    claim.checked_at_revision,
                    int(claim.stale),
                ),
            )
            # Attach evidence links (idempotente).
            for evidence_id in claim.evidence_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
                    (claim.claim_id, evidence_id),
                )
        return claim.claim_id

    def get_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
    ) -> Claim | None:
        import json

        row = self._conn.execute(
            "SELECT * FROM claims WHERE claim_id = ? AND tenant_id = ? AND project_id = ?",
            (claim_id, tenant_id, project_id),
        ).fetchone()
        if row is None:
            return None
        # Recoger evidence_ids del join.
        ev_rows = self._conn.execute(
            "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
        return _row_to_claim(row, [r["evidence_id"] for r in ev_rows], json)

    def list_claims_for_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
    ) -> list[Claim]:
        import json

        rows = self._conn.execute(
            "SELECT * FROM claims WHERE source_id = ? AND tenant_id = ? AND project_id = ?",
            (source_id, tenant_id, project_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_rows = self._conn.execute(
                "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
                (row["claim_id"],),
            ).fetchall()
            out.append(_row_to_claim(row, [r["evidence_id"] for r in ev_rows], json))
        return out

    def attach_evidence_to_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
        evidence_id: str,
    ) -> None:
        """Adjunta una Evidence a un Claim (N:M). Idempotente (PK compuesta)."""
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
                (claim_id, evidence_id),
            )

    # ---- Findings

    def record_finding(
        self,
        *,
        tenant_id: str,
        project_id: str,
        finding: Finding,
    ) -> None:
        """Registra un Finding. Idempotente por `finding_id` (PK)."""
        import json

        ev_json = json.dumps(list(finding.evidence_ids), sort_keys=True)
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO findings
                    (finding_id, tenant_id, project_id, entity_id,
                     observation, rule_ref, rule_version,
                     evidence_ids_json, result, valid_until_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    tenant_id,
                    project_id,
                    finding.entity_id,
                    finding.observation,
                    finding.rule_ref,
                    finding.rule_version,
                    ev_json,
                    finding.result,
                    finding.valid_until_revision,
                ),
            )

    # ---- Outcome traces

    def record_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace: OutcomeTrace,
    ) -> None:
        """Registra un OutcomeTrace y sus enlaces (claim/evidence en orden).

        Idempotente por `trace_id` y por `(trace_id, link_kind, link_id)`."""
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO outcome_traces
                    (trace_id, tenant_id, project_id, kind, name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    tenant_id,
                    project_id,
                    trace.kind,
                    trace.name,
                    trace.created_at,
                ),
            )
            # Enlazar claims y evidences preservando orden via `position`.
            for position, claim_id in enumerate(trace.claim_refs):
                cur.execute(
                    """
                    INSERT OR REPLACE INTO outcome_trace_links
                        (trace_id, link_kind, link_id, position)
                    VALUES (?, 'claim', ?, ?)
                    """,
                    (trace.trace_id, claim_id, position),
                )
            for position, evidence_id in enumerate(trace.evidence_refs):
                cur.execute(
                    """
                    INSERT OR REPLACE INTO outcome_trace_links
                        (trace_id, link_kind, link_id, position)
                    VALUES (?, 'evidence', ?, ?)
                    """,
                    (trace.trace_id, evidence_id, position),
                )

    def link_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace_id: str,
        link_kind: str,
        link_id: str,
        position: int,
    ) -> None:
        """Adjunta un enlace adicional a un trace. `link_kind` ∈
        {'claim', 'evidence', 'relation'}."""
        if link_kind not in {"claim", "evidence", "relation"}:
            raise ValidationError(
                f"link_kind invalido: {link_kind!r} (esperado claim/evidence/relation)"
            )
        with self._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO outcome_trace_links
                    (trace_id, link_kind, link_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (trace_id, link_kind, link_id, position),
            )

    # ----- Events (H3 Slice 4) -----

    def record_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_id: str,
        event_kind: str,
        resource_ref: str,
        payload: Mapping[str, Any],
        run_id: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Registra un evento en `runtime_events`. Devuelve su sequence.

        `payload` se serializa como JSON. `timestamp` por defecto = now UTC.
        """
        import json as _json
        from datetime import datetime

        ts = timestamp or datetime.now(UTC).replace(microsecond=0).isoformat()
        with self._tx() as cur:
            cur.execute(
                """
                INSERT INTO runtime_events
                    (event_id, tenant_id, project_id, event_kind, run_id,
                     resource_ref, causation_id, correlation_id,
                     payload_json, timestamp, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    project_id,
                    event_kind,
                    run_id,
                    resource_ref,
                    causation_id,
                    correlation_id,
                    _json.dumps(dict(payload), ensure_ascii=False),
                    ts,
                    1,
                ),
            )
            return cur.lastrowid or 0

    def list_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
        resource_ref: str | None = None,
        event_kind: str | None = None,
    ) -> list[sqlite3.Row]:
        """Lista eventos filtrados por (tenant, project) + resource_ref/kind."""
        q = "SELECT * FROM runtime_events WHERE tenant_id = ? AND project_id = ?"
        params: list[Any] = [tenant_id, project_id]
        if resource_ref is not None:
            q += " AND resource_ref = ?"
            params.append(resource_ref)
        if event_kind is not None:
            q += " AND event_kind = ?"
            params.append(event_kind)
        q += " ORDER BY sequence ASC"
        return self._conn.execute(q, params).fetchall()

    # ----- H7 promocion entre bases (UAT-13) -----

    def register_promotion(
        self,
        *,
        proposal_id: str,
        idempotency_key: str,
        tenant_id: str,
        source_project: str,
        target_catalog: str,
        knowledge_ref: str,
        payload: dict[str, Any],
    ) -> None:
        """Inserta una propuesta de promocion en el outbox (status=PENDING).

        Si `idempotency_key` ya existe, lanza `IdentityConflictError`
        (la promocion ya fue registrada; no se duplica).
        """
        import json as _json

        with self._tx() as cur:
            existing = cur.execute(
                "SELECT proposal_id FROM promotion_outbox WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                raise IdentityConflictError(
                    f"Promocion duplicada: idempotency_key={idempotency_key!r} "
                    f"ya registrada como proposal_id={existing['proposal_id']!r}"
                )
            cur.execute(
                """
                INSERT INTO promotion_outbox
                    (proposal_id, idempotency_key, tenant_id, source_project,
                     target_catalog, knowledge_ref, payload_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    proposal_id,
                    idempotency_key,
                    tenant_id,
                    source_project,
                    target_catalog,
                    knowledge_ref,
                    _json.dumps(payload, sort_keys=True),
                ),
            )

    def get_promotion(self, proposal_id: str) -> dict[str, Any] | None:
        """Devuelve la propuesta por id, o None si no existe."""
        import json as _json

        row = self._conn.execute(
            "SELECT * FROM promotion_outbox WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["payload"] = _json.loads(d.pop("payload_json"))
        return d

    def list_pending_promotions(self) -> list[dict[str, Any]]:
        """Lista propuestas con status IN ('PENDING', 'IN_PROGRESS') para reconciliacion.

        Equivalente a ``list_promotions(status="PENDING")`` mas los registros
        ``IN_PROGRESS`` (los dejados por un crash previo). Conservado para
        compatibilidad con callers existentes.
        """
        import json as _json  # local import por consistencia con resto del modulo

        rows = self._conn.execute(
            """
            SELECT * FROM promotion_outbox
            WHERE status IN ('PENDING', 'IN_PROGRESS')
            ORDER BY created_at ASC
            """
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["payload"] = _json.loads(d.pop("payload_json"))
            result.append(d)
        return result

    def find_active_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> str | None:
        """Devuelve el run_id del Run mas reciente en estado no terminal
        para (tenant, project), o ``None`` si no hay ninguno.

        No terminal = ``CREATED``, ``ACTIVE`` o ``WAITING`` (ver
        ``NON_TERMINAL_RUN_STATES``). ``COMPLETED``, ``FAILED`` y
        ``CANCELLED`` se consideran terminales: el siguiente ``sg run``
        debe crear un Run nuevo.

        Cumple UAT-06: tras un crash con un Run ACTIVE, el CLI lo
        encuentra y lo reanuda en lugar de crear otro.
        """
        # Construir placeholders de tamaño dinamico (NO expone SQL al caller,
        # solo la consulta SQL).
        placeholders = ",".join("?" * len(NON_TERMINAL_RUN_STATES))
        params: list[Any] = [*NON_TERMINAL_RUN_STATES, tenant_id, project_id]
        row = self._conn.execute(
            f"""
            SELECT run_id FROM workflow_runs
            WHERE state IN ({placeholders})
              AND tenant_id = ? AND project_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row is None:
            return None
        return row["run_id"]

    # ----- lecturas del ciclo de vida de un Run (H9-BSlice3-S1) -----

    def load_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Carga la fila de `workflow_runs` para (tenant, project, run).

        Lanza ``NotFoundError`` si no existe. Sustituye a la lectura
        directa sobre ``self._conn.execute(...)`` que realizaba
        ``RunController._load_run``. Es una lectura pura: no participa
        en transacciones compartidas con ``EventLog.append``.

        No expone SQL al caller; la conversión de Row a dict es interna.
        """
        row = self._conn.execute(
            """
            SELECT * FROM workflow_runs
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
            """,
            (tenant_id, project_id, run_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"run no encontrado: {run_id}")
        return dict(row)

    def list_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
    ) -> list[dict[str, Any]]:
        """Lista NodeExecutions de un (run, node_name) ordenadas por
        ``started_at ASC``.

        Sustituye a la lectura directa que realizaba
        ``RunController._node_executions_for``. Lectura pura:
        orden estable, sin filtrado por estado (la query del
        RunController original tampoco filtraba).
        """
        rows = self._conn.execute(
            """
            SELECT * FROM node_executions
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
              AND node_name = ?
            ORDER BY started_at ASC
            """,
            (tenant_id, project_id, run_id, node_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_executed_node_names(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> tuple[str, ...]:
        """Devuelve los `node_name` DISTINCT con ``state='SUCCEEDED'``
        para un run, ordenados alfabéticamente.

        Sustituye a la lectura directa que realizaba
        ``RunController._executed_node_names``. Lectura pura: el orden
        alfabético hace el resultado determinista y testeable sin
        depender del orden de inserción.
        """
        rows = self._conn.execute(
            """
            SELECT DISTINCT node_name FROM node_executions
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
              AND state = 'SUCCEEDED'
            ORDER BY node_name ASC
            """,
            (tenant_id, project_id, run_id),
        ).fetchall()
        return tuple(r["node_name"] for r in rows)

    def recover_interrupted_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> int:
        """Transiciona TODOS los NodeExecution en ``RUNNING`` sin
        ``finished_at`` a ``READY`` para un run.

        Sustituye a ``RunController._recover_interrupted``: el original
        abría una transacción por cada fila (bucle ``for r in rows: with
        self._conn: ...``). Esta versión abre UNA sola transacción para
        todas las filas. Es una escritura atómica en sí misma: si algo
        falla dentro de la operación, ninguna fila queda a medias.

        Esta operación NO emite eventos. S4 del plan H9-BSlice3.

        Devuelve el número de filas recuperadas (0 si no había ninguna).
        """
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'READY', finished_at = datetime('now')
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                  AND state = 'RUNNING' AND finished_at IS NULL
                """,
                (tenant_id, project_id, run_id),
            )
            return cur.rowcount

    def transition_run_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        """Transiciona el ``state`` y/o ``current_node`` de un Run.

        UPDATE no-op si el run no existe. Sustituye a
        ``RunController._set_run_state``.

        No emite eventos. Si la operación debe ir coordinada con
        ``EventLog.append`` (lo más habitual), el llamador hace el
        append DESPUES. Esto preserva el contrato actual: la
        atomicidad entre state y eventos sigue siendo responsabilidad
        del orquestador (RunController), no de Storage. Ver decisión
        arquitectónica del 2026-09-23 18:24.

        ``state`` debe ser uno de los literales ``RunState``; validación
        tipica la hace el type checker, no este método (Storage expone
        ``str`` para no acoplarse a tipos del runtime).
        """
        with self._conn:
            self._conn.execute(
                """
                UPDATE workflow_runs
                SET state = ?, current_node = ?,
                    updated_at = datetime('now')
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                """,
                (state, current_node, tenant_id, project_id, run_id),
            )

    def start_node_execution(
        self,
        *,
        node_execution_id: str,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
        context_hash: str,
        handoff_json: str,
    ) -> None:
        """Inserta un NodeExecution en estado ``RUNNING``.

        Sustituye a la parte INSERT del RunController._execute_one.
        El ``node_execution_id`` lo genera el llamador (ver
        ``new_node_execution_id``); el state queda fijado a
        ``RUNNING`` y ``started_at`` se materializa en SQL con
        ``datetime('now')``.

        No emite eventos. La coordinación con
        ``EventLog.append(events.node_started(...))`` sigue siendo
        del llamador (RunController._execute_one).
        """
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO node_executions
                    (node_execution_id, run_id, tenant_id, project_id,
                     node_name, attempt, state, context_hash, handoff_json,
                     started_at)
                VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, datetime('now'))
                """,
                (
                    node_execution_id,
                    run_id,
                    tenant_id,
                    project_id,
                    node_name,
                    attempt,
                    context_hash,
                    handoff_json,
                ),
            )

    def complete_node_execution(
        self,
        *,
        node_execution_id: str,
        outcome: str,
        result_json: str,
    ) -> None:
        """Transiciona un NodeExecution a ``SUCCEEDED`` con outcome y
        result_json ya serializado.

        Sustituye a la parte UPDATE SUCCEEDED del RunController._execute_one.

        No emite eventos. La coordinacion con
        ``EventLog.append(events.node_completed(...))`` y
        ``EventLog.append(events.evidence_produced(...))`` sigue siendo
        del llamador.

        ``result_json`` debe llegar ya como string (la API no serializa;
        es responsabilidad del llamador que ``result`` sea JSON-able).
        """
        with self._conn:
            self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'SUCCEEDED', outcome = ?, result_json = ?,
                    finished_at = datetime('now')
                WHERE node_execution_id = ?
                """,
                (outcome, result_json, node_execution_id),
            )

    def mark_node_failed(
        self,
        *,
        node_execution_id: str,
        error: str,
    ) -> None:
        """Transiciona un NodeExecution a ``FAILED`` con un mensaje de
        error legible (sin stack).

        Sustituye a ``RunController._mark_node_failed``.

        No emite eventos. La coordinacion con
        ``EventLog.append(events.node_failed(...))`` sigue siendo del
        llamador.
        """
        with self._conn:
            self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'FAILED', error = ?, finished_at = datetime('now')
                WHERE node_execution_id = ?
                """,
                (error, node_execution_id),
            )

    def list_promotions(
        self,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista propuestas del outbox, opcionalmente filtradas por ``status``.

        - ``status=None`` -> todas las propuestas, ordenadas por ``created_at`` ASC.
        - ``status='PENDING'`` -> solo PENDING; equivalente a la rama
          ``list_promotions(status='PENDING')`` (sin IN_PROGRESS).
        - Cualquier otro status valido (``IN_PROGRESS``, ``PUBLISHED``,
          ``FAILED``) filtra exactamente por ese valor.

        Lanza ``ValidationError`` si ``status`` no esta en
        ``PROMOTION_STATUSES``. No expone SQL al caller.
        """
        import json as _json  # local import por consistencia con resto del modulo

        if status is not None and status not in PROMOTION_STATUSES:
            raise ValidationError(
                f"status de promocion invalido: {status!r}; validos={sorted(PROMOTION_STATUSES)}"
            )

        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM promotion_outbox ORDER BY created_at ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM promotion_outbox WHERE status = ? ORDER BY created_at ASC",
                (status,),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["payload"] = _json.loads(d.pop("payload_json"))
            result.append(d)
        return result

    def mark_promotion_in_progress(self, proposal_id: str) -> bool:
        """Pasa de PENDING a IN_PROGRESS. Devuelve True si transiciono."""
        cur = self._conn.execute(
            """
            UPDATE promotion_outbox
            SET status = 'IN_PROGRESS', attempts = attempts + 1,
                updated_at = datetime('now')
            WHERE proposal_id = ? AND status = 'PENDING'
            """,
            (proposal_id,),
        )
        return cur.rowcount > 0

    def mark_promotion_published(self, proposal_id: str) -> bool:
        """Pasa de IN_PROGRESS a PUBLISHED. Devuelve True si transiciono."""
        cur = self._conn.execute(
            """
            UPDATE promotion_outbox
            SET status = 'PUBLISHED', updated_at = datetime('now'),
                published_at = datetime('now')
            WHERE proposal_id = ? AND status = 'IN_PROGRESS'
            """,
            (proposal_id,),
        )
        return cur.rowcount > 0

    def mark_promotion_failed(self, proposal_id: str) -> bool:
        """Marca FAILED para inspeccion manual."""
        cur = self._conn.execute(
            """
            UPDATE promotion_outbox
            SET status = 'FAILED', updated_at = datetime('now')
            WHERE proposal_id = ? AND status IN ('PENDING', 'IN_PROGRESS')
            """,
            (proposal_id,),
        )
        return cur.rowcount > 0


# --- Helpers de conversion row -> ADT -------------------------------------


def _row_to_source(row: sqlite3.Row, json: Any) -> Source:
    """Convierte una fila de `sources` al ADT `Source`."""
    locator = json.loads(row["locator_json"])
    wts = row["working_tree_status_json"]
    return Source(
        source_id=row["source_id"],
        kind=row["kind"],
        content_hash=row["content_hash"],
        locator=locator,
        git_commit_sha=row["git_commit_sha"],
        git_tree_sha=row["git_tree_sha"],
        working_tree_status=json.loads(wts) if wts else None,
        checked_at=row["checked_at"],
        freshness=row["freshness"],
    )


def _row_to_evidence(row: sqlite3.Row, json: Any) -> Evidence:
    content: Any = json.loads(row["content_json"])
    return Evidence(
        evidence_id=row["evidence_id"],
        kind=row["kind"],
        content=content,
        source_id=row["source_id"],
        observed_at=row["observed_at"],
    )


def _row_to_claim(row: sqlite3.Row, evidence_ids: list[str], json: Any) -> Claim:
    return Claim(
        claim_id=row["claim_id"],
        subject_entity_id=row["subject_entity_id"],
        predicate=row["predicate"],
        object_literal=json.loads(row["object_literal_json"]),
        source_id=row["source_id"],
        evidence_ids=tuple(evidence_ids),
        extraction_method=row["extraction_method"],
        extractor_version=row["extractor_version"],
        checked_at_revision=row["checked_at_revision"],
        stale=bool(row["stale"]),
    )


def open_project_storage(path: str | Path) -> Storage:
    """Ayuda para abrir el almacenamiento de un proyecto.

    Cualquier error de validación aquí es bug: este helper no debería
    recibir paths fuera de los directorios gestionados por la CLI.
    """
    if not str(path).endswith(".sqlite"):
        raise ValidationError(f"Path de proyecto debe terminar en .sqlite: {path}")
    return Storage(path)
