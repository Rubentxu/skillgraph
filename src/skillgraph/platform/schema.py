"""DDL del esquema SQLite de SkillGraph (WI-65, fase 2).

`SCHEMA_SQL` son 248 LoC de DDL. No es comportamiento: es una
constante, y por tanto no comparte razon de cambio con los metodos del
facade `Storage`. Vive aqui para que `storage.py` quede por debajo del
umbral de 800 LoC del audit.

`storage.py` lo re-exporta como `_SCHEMA_SQL` porque `event_store.py` lo importa desde ahi
(ADR-0016 corte 4). NO mover sin migrar ese import.

El DDL **no** se toca: no hay cambio de schema en esta fase. Lo que
ADR-0016 exige que se quede en `Storage` son los atomicos
(`_tx`, `_atomic`, `_insert_event_in_tx`, `_atomic_state_and_event`),
que no viven aqui.
"""

from __future__ import annotations

__all__ = ["SCHEMA_SQL", "SCHEMA_VERSION"]

SCHEMA_VERSION = 1

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS run_budgets (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    max_visits INTEGER,
    max_runtime_seconds INTEGER,
    max_events INTEGER,
    inserted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tenant_policies (
    tenant_id TEXT PRIMARY KEY,
    redaction_policy TEXT NOT NULL DEFAULT 'metadata',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

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
