"""DDL del esquema SQLite de SkillGraph (WI-65, fase 2).

`SCHEMA_SQL` son 248 LoC de DDL. No es comportamiento: es una
constante, y por tanto no comparte razon de cambio con los metodos del
facade `Storage`. Vive aqui para que `storage.py` quede por debajo del
umbral de 800 LoC del audit.

`storage.py` lo re-exporta como `_SCHEMA_SQL` porque `event_store.py` lo importa desde ahi
(ADR-0016 corte 4). NO mover sin migrar ese import.

El DDL no cambia de forma: ADR-0016 exige que se queden en `Storage` los
atomicos (`_tx`, `_atomic`, `_insert_event_in_tx`,
`_atomic_state_and_event`), que no viven aqui.

ADR-0015: el unico punto del DDL que **expresa vocabulario de dominio** es
el `CHECK` de `promotion_outbox.status`, y se genera desde
`core.runtime_types.PROMOTION_STATUSES` en vez de escribirse a mano. El
conjunto de valores aceptados es identico, asi que ese cambio NODLE NECESITA
migracion, y el numero se mantiene con `SCHEMA_VERSION` DERIVADO de
`MIGRACIONES`.

B12: `SCHEMA_VERSION` era `1` escrito a mano y no se movia desde WI-65. MEDIDO
en `.pipelinek/b12_preflight.md` §6: se escribia con `INSERT OR IGNORE` y no
se leia en ningun sitio de `platform/`, y borrar la tabla entera de una base
hacia que el codigo la recreara en silencio —una version que se regenera
cuando falta es un DEFAULT, no un hecho—. Ahora sale de
`platform.migrations.version_declarada()`, que es `len(MIGRACIONES)`, y por
eso no se puede olvidar subirlo: no hay ningun numero que mantener.

Consecuencia practica del ADR-0015, intacta: la base de datos y el validador
de entrada no pueden divergir porque salen de la misma expresion.
"""

from __future__ import annotations

from skillgraph.core.runtime_types import PROMOTION_STATUSES
from skillgraph.platform.migrations import MIGRACIONES, version_declarada

__all__ = ["MIGRACIONES", "SCHEMA_SQL", "SCHEMA_VERSION"]

#: Derivada, no literal. El guard de B12 lo comprueba por AST precisamente
#: porque leer `SCHEMA_VERSION == 2` no diria nada: solo `len(MIGRACIONES)`
#: garantiza que la version y la lista no se puedan separar.
SCHEMA_VERSION: int = version_declarada()

#: El `CHECK` de promocion, generado desde la ADT de dominio. `sorted`
#: porque un frozenset no tiene orden estable entre procesos y el DDL debe
#: ser reproducible byte a byte.
_PROMOTION_STATUS_SQL = ", ".join(f"'{status}'" for status in sorted(PROMOTION_STATUSES))

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- B12: el libro de migraciones. UNA fila por migracion aplicada, con su
-- identificable estable. `schema_version` responde «que version tiene este
-- proyecto»; esta tabla responde «que se le hizo a esta base», que es la
-- pregunta que hace falta cuando algo va mal y la version sola no basta.
-- B29: EL ORDEN DE LAS REVISIONES.
--
-- Una ventana de vigencia es un intervalo, y un intervalo necesita un orden.
-- Las revisiones de verdad son SHAs de commit, y comparar dos SHAs es
-- LEXICOGRAFICO: un orden total y ARBITRARIO. Una ventana sobre un orden
-- inventado no es una ventana.
--
-- `seq` es EL ORDEN EN QUE ESTE STORE APRENDIO DE ESAS REVISIONES. No es
-- ascendencia de git —eso es la capability `GitHistory`, que es B32—, ni es
-- orden lexicografico, y no pretende serlo. Es el unico orden que este store
-- puede defender sin conocer la topologia del repositorio.
--
-- Y esto es lo que separa los DOS EJES de 06-SPEC §1 de forma real:
-- `checked_at_revision` es knowledge time, y `seq` es valid time. Confundirlos
-- no era una falta de estilo: era no tener un eje con el que comparar.
--
-- `revision` es UNIQUE porque dos filas con la misma revision y distinto
-- `seq` harian la ventana arbitraria, y la consulta por revisionaria.
CREATE TABLE IF NOT EXISTS revision_registro (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    revision TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
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
    status_json TEXT NOT NULL DEFAULT '{{}}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tenant_id, project_id, api_version, kind, namespace, name)
);

CREATE INDEX IF NOT EXISTS resources_by_kind
    ON resources(tenant_id, project_id, api_version, kind);
CREATE INDEX IF NOT EXISTS resources_by_name
    ON resources(tenant_id, project_id, namespace, name);

-- B11: el REGISTRO de packs instalados.
--
-- POR QUE ESTA TABLA Y NO LA DE `resources`, y por que no es un detalle:
-- `upsert_resource` RECHAZA cambiar el `spec` bajo la misma identidad con
-- `IdentityConflictError` —es deliberado, es lo que hace que un recurso
-- sea inmutable y que cambiarlo sea un conflicto, no una edicion—. MEDIDO:
-- con el registro encima de `resources`, `sg pack update` era
-- estructuralmente IMPOSIBLE: la version nueva es un spec distinto bajo la
-- misma identidad, luego el storage la rechazaba siempre.
--
-- Una INSTALACION no es un recurso. El recurso es el contenido del pack;
-- la instalacion es el hecho de que ese pack este vivo en este proyecto,
-- y ese hecho tiene su propio ciclo: se instala, se actualiza y se retira.
-- Meterlo en `resources` no era solo comodo, era incorrecto.
--
-- Y `retirar` NO borra: mueve `estado` a `retired`. Ver la cabecera de
-- `skillgraph.packaging.registry`, que explica por que un DELETE perderia
-- la unica respuesta que existe a «¿este proyecto ha tenido este pack?».
CREATE TABLE IF NOT EXISTS installed_packs (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    estado TEXT NOT NULL,
    uid TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tenant_id, project_id, name)
);

CREATE INDEX IF NOT EXISTS installed_packs_by_project
    ON installed_packs(tenant_id, project_id, estado);

CREATE TABLE IF NOT EXISTS relations (
    uid TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_uid TEXT NOT NULL,
    target_uid TEXT NOT NULL,
    kind TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{{}}',
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
    assertion_origin      TEXT NOT NULL DEFAULT 'observed'
        CHECK (assertion_origin IN (
            'observed',
            'derived-deterministically',
            'agent-inferred',
            'human-asserted'
        )),
    extraction_method     TEXT NOT NULL,
    extractor_version     TEXT NOT NULL,
    checked_at_revision   TEXT NOT NULL,
    stale                 INTEGER NOT NULL DEFAULT 0,
    -- B25: el objeto de un claim es UN literal o UNA entidad, nunca los dos y
    -- nunca ninguno. El XOR de abajo es la MISMA pregunta que la de
    -- `Claim.__post_init__`, a proposito: si las dos capas no dijeran lo
    -- mismo, la base rechazaria filas que Python acepta.
    --
    -- `''` es el marcador de ausencia y no colisiona con nada, porque
    -- `json.dumps` NUNCA produce `''`: `json.dumps("")` es `'""'` y
    -- `json.dumps(None)` es `'null'`.
    --
    -- SIN clave foránea a proposito, y medido: con `foreign_keys = ON` (como
    -- abre `storage.py`) declarar `REFERENCES entities(entity_id)` aqui
    -- rechazaria TODOS los claims literales, porque `''` no es una entidad.
    object_entity_id      TEXT NOT NULL DEFAULT ''
        CHECK ((object_literal_json = '') <> (object_entity_id = '')),
    -- B29: VENTANA DE VIGENCIA. `checked_at_revision` de arriba es
    -- KNOWLEDGE time (cuando lo vimos); estas dos son VALID time (cuando era
    -- cierto el hecho), y no son lo mismo. Sin ellas, un hecho que CAMBIO se
    -- lee igual que un hecho que se CONTRADICE. MEDIDO: con dos filas de la
    -- MISMA fuente en revisiones consecutivas, `conflicts_for` devolvia un
    -- conflicto y `resolver` contestaba «gana NADIE» a algo que si tiene
    -- respuesta en cada instante.
    --
    -- Las dos son ANULABLES y sin default a proposito: `NULL` significa
    -- «esta afirmacion no caduca» —que es lo cierto de todo el grafo que ya
    -- existia—, y un default inventado fecharia en el pasado lo que se acaba
    -- de escribir. Un `CHECK` de coherencia vive en `Claim.__post_init__`, no
    -- aqui: SQLite no revalida CHECK sobre filas ya escritas, y una restriccion
    -- blanda hacia atras es exactamente lo que B25 eligio y dijo.
    valid_from_revision  TEXT,
    valid_until_revision TEXT,
    -- B29: la cadena de supersesion. NO es un `REFERENCES`: dos claims que se
    -- superseden pueden provenir de bases migradas antes de que existiera la
    -- columna, y una FK ahi haria fallar escrituras que antes funcionaban.
    -- La integridad la sostiene `record_claim`, que es quien la escribe.
    supersedes_claim_id TEXT,
    UNIQUE (subject_entity_id, predicate, source_id, checked_at_revision)
);
CREATE INDEX IF NOT EXISTS idx_claims_subject
    ON claims(subject_entity_id, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_stale
    ON claims(stale) WHERE stale = 1;
-- B25: `idx_claims_object_entity` NO se crea aqui, y el motivo es concreto.
--
-- Este DDL se ejecuta con `CREATE TABLE IF NOT EXISTS`, luego sobre una base
-- cuya tabla `claims` ya existia **no la reconstruye**: la deja como estaba.
-- Un `CREATE INDEX` sobre una columna que esa tabla vieja no tiene revienta
-- `executescript` entero, y con el revienta el ABRIR la base — que es
-- precisamente lo que deberia arreglar una migracion. MEDIDO: una base con la
-- tabla al esquema anterior no abria, con `no such column: object_entity_id`.
--
-- El indice lo crea la migracion `0003`, que si sabe distinguir «la columna no
-- esta» de «la columna esta y el indice no». Una base nueva lo tiene tambien:
-- `sincroniza` corre TODAS las migraciones en cada apertura, no solo las que
-- faltan.

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
                    CHECK (status IN ({_PROMOTION_STATUS_SQL})),
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    published_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_promotion_outbox_status
    ON promotion_outbox(status);
"""
