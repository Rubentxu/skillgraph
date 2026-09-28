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

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)
from skillgraph.platform.ports import (
    StoredBudget,
    StoredClaim,
    StoredEvent,
    StoredEvidence,
    StoredNodeExecution,
    StoredPromotion,
    StoredRelation,
    StoredResource,
    StoredRun,
)
from skillgraph.platform.uow import SqliteUnitOfWork
from skillgraph.resources.bricks import Brick

if TYPE_CHECKING:
    from skillgraph.platform.event_store import SqliteEventStore
    from skillgraph.platform.knowledge_repository import SqliteKnowledgeRepository
    from skillgraph.platform.policy_store import SqlitePolicyStore
    from skillgraph.platform.promotion_repository import SqlitePromotionRepository
    from skillgraph.platform.run_repository import SqliteRunRepository
    from skillgraph.runtime.engine import RuntimeEvent

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


def _uid(brick: Brick) -> str:
    """UID determinista por (tenant, project, apiVersion, kind, namespace, name).

    El blueprint (doc 03 §3) deja la elección al núcleo. Aquí usamos un
    UID estable pero NO un hash criptográfico: las revisiones usan un
    contador (resource_version) y la identidad de los `Brick` ya viene
    garantizada por la UNIQUE constraint de la tabla.
    """
    i = brick.identity
    return f"{i.tenant_id}/{i.project_id}/{brick.api_version}/{brick.kind}/{i.namespace}/{i.name}"


def _row_to_stored_event(row: sqlite3.Row) -> StoredEvent:
    """Mapea ``sqlite3.Row`` de ``runtime_events`` al DTO ``StoredEvent``.

    WI-32.2 (R1 strict, audit 2026-09-27): este helper es la frontera
    entre ``platform/`` y el resto del runtime. El consumidor (EventLog,
    RunController) solo ve ``StoredEvent``; nunca importa ``sqlite3``.

    El campo ``payload`` se deserializa desde ``payload_json`` aqui;
    ``runtime/engine.py`` ya no maneja ``json.loads`` sobre filas.
    """
    import json  # local import por consistencia con resto del modulo

    return StoredEvent(
        sequence=row["sequence"],
        event_id=row["event_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        event_kind=row["event_kind"],
        run_id=row["run_id"],
        resource_ref=row["resource_ref"],
        causation_id=row["causation_id"],
        correlation_id=row["correlation_id"],
        payload=json.loads(row["payload_json"]),
        timestamp=row["timestamp"],
        schema_version=row["schema_version"],
    )


def _row_to_stored_promotion(row: sqlite3.Row) -> StoredPromotion:
    """Mapea ``sqlite3.Row`` de ``promotion_outbox`` al DTO ``StoredPromotion``.

    WI-38 (R1 strict): cierra la fuga de ``dict[str, Any]`` en los
    3 metodos de promotion (``get_promotion``, ``list_pending_promotions``,
    ``list_promotions``). El campo ``payload`` se deserializa aqui.
    """
    import json  # local import por consistencia con resto del modulo

    return StoredPromotion(
        proposal_id=row["proposal_id"],
        idempotency_key=row["idempotency_key"],
        tenant_id=row["tenant_id"],
        source_project=row["source_project"],
        target_catalog=row["target_catalog"],
        knowledge_ref=row["knowledge_ref"],
        payload=json.loads(row["payload_json"]),
        status=row["status"],
        attempts=row["attempts"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
    )


def _row_to_stored_budget(row: sqlite3.Row) -> StoredBudget:
    """Mapea ``sqlite3.Row`` de ``run_budgets`` al DTO ``StoredBudget``.

    WI-38 (R1 strict): sustituye ``dict(row)`` en ``get_budget``.
    """
    return StoredBudget(
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        run_id=row["run_id"],
        max_visits=row["max_visits"],
        max_runtime_seconds=row["max_runtime_seconds"],
        max_events=row["max_events"],
    )


class Storage:
    """Interfaz de almacenamiento para un proyecto.

    Diseñada para fallar rápido en errores de identidad y validación,
    sin exponer SQL a los controladores.

    WI-33: ``Storage`` es ahora un facade delgado sobre
    ``SqliteUnitOfWork``. Los 5 bounded-context adapters (runs,
    events, knowledge, governance, policy) comparten la misma
    ``sqlite3.Connection``. El facade expone cada metodo publico
    como alias directo sobre el adapter correspondiente.
    """

    # Nombres de metodos publicos declarados en los 5 adapters de
    # ``skillgraph.platform.uow``. Documenta la superficie; NO se
    # consume en ninguna parte (``__init__`` no hace bind de metodos:
    # el facade tiene sus propios metodos SQL y los adapters delegan
    # en el, no al reves).
    #
    # WI-45: se corrige el comentario, que afirmaba que estos nombres
    # "se bind-an en __init__". No era cierto, y por eso la lista
    # arrastraba dos nombres que ningun metodo real tiene
    # (``get_redaction_policy`` / ``set_redaction_policy``). La
    # lista ahora nombra lo que el facade implementa de verdad.
    _PUBLIC_METHODS = frozenset(
        {
            # SqliteRunAdapter (RunRepository)
            "list_runs",
            "get_run",
            "load_run",
            "list_node_executions",
            "find_active_run",
            "list_executed_node_names",
            "recover_interrupted_node_executions",
            "transition_run_state",
            "start_node_execution",
            "complete_node_execution",
            "mark_node_failed",
            "create_run",
            "transition_run_state_atomically",
            "start_node_execution_atomically",
            "complete_node_execution_atomically",
            "mark_node_failed_atomically",
            "update_node_execution_handoff",
            # SqliteEventAdapter (EventStore)
            "list_events_for_run",
            "fetch_event_raw",
            "record_event",
            # SqliteKnowledgeAdapter (KnowledgeRepository)
            "get_resource",
            "list_resources",
            "dependencies_of",
            "dependents_of",
            "upsert_resource",
            "add_relation",
            # SqliteGovernanceAdapter (PromotionRepository)
            "get_promotion",
            "list_promotions",
            # SqlitePolicyAdapter (PolicyStore) — los metodos reales
            # del facade; los del adapter se llaman get/set_redaction_policy
            # y delegan aqui.
            "get_policy",
            "upsert_policy",
        }
    )

    @property
    def uow(self) -> SqliteUnitOfWork:
        """Acceso al ``SqliteUnitOfWork`` underlying (WI-33).

        La UoW es estable: la misma instancia para todo el ciclo
        de vida del ``Storage``. Esto permite a tests verificar
        ``storage.uow is storage.uow``.

        Tipo: ``SqliteUnitOfWork``. Esta propiedad es la API
        publica de WI-33: los tests nuevos pueden usar
        ``storage.uow.runs.list_runs(...)`` en vez de la facade
        ``storage.list_runs(...)``.
        """
        return self._uow

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
        # WI-56 cortes 1-2: cache de los componentes reales del
        # cluster runs y del cluster policy/budget (lazy en sus
        # factorias).
        self._run_repository: SqliteRunRepository | None = None
        self._policy_store: SqlitePolicyStore | None = None
        self._knowledge_repository: SqliteKnowledgeRepository | None = None
        self._event_store: SqliteEventStore | None = None
        self._promotion_repository: SqlitePromotionRepository | None = None
        self._migrate()
        # WI-33 (R2 audit externo): el ``SqliteUnitOfWork`` owns la
        # conexion y expone 5 bounded-context adapters que la
        # comparten. ``Storage`` sigue siendo el facade historico,
        # con sus metodos SQL directos. Los adapters son NUEVAS
        # implementaciones que viven en ``platform/uow.py`` y se
        # acceden via ``storage.uow.runs.list_runs(...)``.
        #
        # WI-33 NO reemplaza los metodos del facade. Esto preserva
        # la API actual y evita recursion: el facade tiene sus
        # implementaciones SQL, los adapters tienen las suyas
        # (inicialmente delegando al facade, pero con la UoW como
        # single owner de la conexion).
        from skillgraph.platform.uow import (
            SqliteEventAdapter,
            SqliteGovernanceAdapter,
            SqliteKnowledgeAdapter,
            SqlitePolicyAdapter,
            SqliteRunAdapter,
            SqliteUnitOfWork,
        )

        self._runs_adapter = SqliteRunAdapter(_conn=self._conn, _storage=self)
        self._events_adapter = SqliteEventAdapter(_conn=self._conn, _storage=self)
        self._knowledge_adapter = SqliteKnowledgeAdapter(_conn=self._conn, _storage=self)
        self._governance_adapter = SqliteGovernanceAdapter(_conn=self._conn, _storage=self)
        self._policy_adapter = SqlitePolicyAdapter(_conn=self._conn, _storage=self)
        self._uow = SqliteUnitOfWork(
            runs=self._runs_adapter,
            events=self._events_adapter,
            knowledge=self._knowledge_adapter,
            governance=self._governance_adapter,
            policy=self._policy_adapter,
        )

    def close(self) -> None:
        """Cierra la conexion SQLite. Idempotente: doble close no falla.

        QW-C: permite que ``Storage`` se use como context manager
        (``with Storage(path) as s: ...``) sin generar
        ``ResourceWarning: unclosed database``. ``__exit__`` llama
        a este metodo; tests que ya usan ``storage.close()`` siguen
        funcionando igual.
        """
        # sqlite3.Connection.close() es idempotente en Python >=3.10,
        # pero por seguridad marcamos una bandera para dobles llamadas.
        with suppress(sqlite3.ProgrammingError):
            self._conn.close()

    def __enter__(self) -> Storage:
        """Soporte ``with Storage(path) as s: ...``.

        Devuelve ``self`` para que el cuerpo del ``with`` pueda usar
        el storage directamente.
        """
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Cierra la conexion al salir del ``with``. Ignora la excepcion
        del cuerpo (no la suprime: el caller la ve normalmente).

        Si el cuerpo lanzo una excepcion, sqlite3 cierra la transaccion
        abierta (rollback automatico) y nosotros cerramos la conexion.
        """
        self.close()
        # No devolvemos True: la excepcion (si la hubo) se propaga.

    # ----- factorías de puertos (WI-02a) -------------------------------
    # ``Storage`` implementa los 5 Protocols de persistencia
    # (``RunRepository``, ``EventStore``, ``KnowledgeRepository``,
    # ``PromotionRepository``, ``PolicyStore``) por duck typing
    # estructural: sus métodos públicos coinciden con las firmas
    # declaradas en ``skillgraph.platform.ports``. Estas factorías
    # permiten a los consumidores del core (RunController, EventLog)
    # recibir la abstracción sin acoplarse a la clase concreta
    # ``Storage``. La factoría devuelve ``self`` para preservar el
    # sharing de conexión: cualquier mutación sobre ``Storage``
    # sigue siendo visible de inmediato para los adapters.
    #
    # Cuando se introduzcan ``SqliteRunRepository`` etc. en WI-02b,
    # estas factorías pueden delegar a ellos sin cambiar la firma.

    def run_repository(self) -> SqliteRunRepository:
        """Devuelve el componente REAL del cluster runs (WI-56).

        Una unica instancia por ``Storage`` (cacheada): identidad
        estable entre llamadas, conexion compartida, SQL viviendo en
        ``platform/run_repository.py``. El facade conserva delegados
        con firma explicita por compatibilidad con los call-sites
        existentes (REQ-WI56-1/I1: cero ediciones en callers).
        ``getattr`` (y no acceso directo) porque los dobles de test
        que heredan de ``Storage`` sin pasar por ``__init__``
        (``ConnFaultyStorage``) no tienen el slot.
        """
        if getattr(self, "_run_repository", None) is None:
            from skillgraph.platform.run_repository import SqliteRunRepository

            self._run_repository = SqliteRunRepository(self)
        return self._run_repository

    # ----- delegados del cluster runs (WI-56 corte 1) ---------------
    # El SQL vive en ``SqliteRunRepository``; estos delegados con
    # firma explicita preservan la API del facade (I1: cero
    # ediciones en callers) y mantienen auditable la superficie
    # (el guard WI-45 comprueba keywords contra estas firmas).

    def find_active_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> str | None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.find_active_run``."""
        return self.run_repository().find_active_run(tenant_id=tenant_id, project_id=project_id)

    def list_runs(
        self,
        *,
        tenant_id: str,
        project_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[StoredRun]:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.list_runs``."""
        return self.run_repository().list_runs(
            tenant_id=tenant_id, project_id=project_id, state=state, limit=limit
        )

    def get_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredRun:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.get_run``."""
        return self.run_repository().get_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def list_events_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> list[StoredEvent]:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.list_events_for_run``."""
        return self.run_repository().list_events_for_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def load_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredRun:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.load_run``."""
        return self.run_repository().load_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def list_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
    ) -> list[StoredNodeExecution]:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.list_node_executions``."""
        return self.run_repository().list_node_executions(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id, node_name=node_name
        )

    def list_executed_node_names(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> tuple[str, ...]:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.list_executed_node_names``."""
        return self.run_repository().list_executed_node_names(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def recover_interrupted_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> int:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.recover_interrupted_node_executions``."""
        return self.run_repository().recover_interrupted_node_executions(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def transition_run_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.transition_run_state``."""
        return self.run_repository().transition_run_state(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
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
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.start_node_execution``."""
        return self.run_repository().start_node_execution(
            node_execution_id=node_execution_id,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
            context_hash=context_hash,
            handoff_json=handoff_json,
        )

    def complete_node_execution(
        self,
        *,
        node_execution_id: str,
        outcome: str,
        result_json: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.complete_node_execution``."""
        return self.run_repository().complete_node_execution(
            node_execution_id=node_execution_id, outcome=outcome, result_json=result_json
        )

    def mark_node_failed(
        self,
        *,
        node_execution_id: str,
        error: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.mark_node_failed``."""
        return self.run_repository().mark_node_failed(
            node_execution_id=node_execution_id, error=error
        )

    def start_node_execution_atomically(
        self,
        *,
        event: RuntimeEvent,
        node_execution_id: str,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
        context_hash: str,
        handoff_json: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.start_node_execution_atomically``."""
        return self.run_repository().start_node_execution_atomically(
            event=event,
            node_execution_id=node_execution_id,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
            context_hash=context_hash,
            handoff_json=handoff_json,
        )

    def update_node_execution_handoff(
        self,
        *,
        node_execution_id: str,
        context_hash: str,
        handoff_json: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.update_node_execution_handoff``."""
        return self.run_repository().update_node_execution_handoff(
            node_execution_id=node_execution_id,
            context_hash=context_hash,
            handoff_json=handoff_json,
        )

    def complete_node_execution_atomically(
        self,
        *,
        event_completed: RuntimeEvent,
        event_evidence: RuntimeEvent,
        node_execution_id: str,
        outcome: str,
        result_json: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.complete_node_execution_atomically``."""
        return self.run_repository().complete_node_execution_atomically(
            event_completed=event_completed,
            event_evidence=event_evidence,
            node_execution_id=node_execution_id,
            outcome=outcome,
            result_json=result_json,
        )

    def mark_node_failed_atomically(
        self,
        *,
        event: RuntimeEvent,
        node_execution_id: str,
        error: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.mark_node_failed_atomically``."""
        return self.run_repository().mark_node_failed_atomically(
            event=event, node_execution_id=node_execution_id, error=error
        )

    def create_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan_json: str,
        initial_node: str,
    ) -> str:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.create_run``."""
        return self.run_repository().create_run(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_json=plan_json,
            initial_node=initial_node,
        )

    def create_run_atomically(
        self,
        *,
        event: RuntimeEvent,
        run_id: str,
        tenant_id: str,
        project_id: str,
        plan_json: str,
        initial_node: str,
    ) -> str:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.create_run_atomically``."""
        return self.run_repository().create_run_atomically(
            event=event,
            run_id=run_id,
            tenant_id=tenant_id,
            project_id=project_id,
            plan_json=plan_json,
            initial_node=initial_node,
        )

    def transition_run_state_atomically(
        self,
        *,
        event: RuntimeEvent,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqliteRunRepository.transition_run_state_atomically``."""
        return self.run_repository().transition_run_state_atomically(
            event=event,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            state=state,
            current_node=current_node,
        )

    def promotion_repository(self) -> SqlitePromotionRepository:
        """Devuelve el componente REAL del cluster promotions (WI-56).

        Una unica instancia por ``Storage`` (cacheada): identidad
        estable y conexion compartida. El SQL del outbox de promocion
        (H7) vive en ``platform/promotion_repository.py`` desde el
        corte 5 de WI-56/ADR-0016. Los helpers atomicos de eventos
        permanecen en ``Storage`` (H9/H10). ``getattr`` por los dobles
        de test que heredan sin ``__init__``.
        """
        if getattr(self, "_promotion_repository", None) is None:
            from skillgraph.platform.promotion_repository import (
                SqlitePromotionRepository,
            )

            self._promotion_repository = SqlitePromotionRepository(self)
        return self._promotion_repository

    def event_store(self) -> SqliteEventStore:
        """Devuelve el componente REAL del cluster events (WI-56).

        Antes devolvia ``self`` (structural subtyping con el
        Protocol ``EventStore``); desde el corte 4 de WI-56/ADR-0016
        devuelve la instancia real de ``SqliteEventStore`` (cacheada):
        identidad estable, conexion compartida, SQL viviendo en
        ``platform/event_store.py``. Los helpers atomicos
        ``_insert_event_in_tx`` / ``_atomic_state_and_event`` siguen
        en ``Storage`` (H9/H10). ``getattr`` por los dobles de test
        que heredan sin ``__init__``.
        """
        if getattr(self, "_event_store", None) is None:
            from skillgraph.platform.event_store import SqliteEventStore

            self._event_store = SqliteEventStore(self)
        return self._event_store

    def knowledge_repository(self) -> SqliteKnowledgeRepository:
        """Devuelve el componente REAL del cluster knowledge (WI-56).

        Antes (WI-31) devolvia ``self`` (structural subtyping); desde
        el corte 3 de WI-56/ADR-0016 devuelve la instancia real de
        ``SqliteKnowledgeRepository`` (cacheada): identidad estable,
        conexion compartida, SQL viviendo en
        ``platform/knowledge_repository.py``. El facade conserva
        delegados con firma explicita por compatibilidad con los
        call-sites existentes (REQ-WI56-1/I1: cero ediciones en
        callers). ``getattr`` (y no acceso directo) por los dobles de
        test que heredan sin ``__init__``.
        """
        if getattr(self, "_knowledge_repository", None) is None:
            from skillgraph.platform.knowledge_repository import (
                SqliteKnowledgeRepository,
            )

            self._knowledge_repository = SqliteKnowledgeRepository(self)
        return self._knowledge_repository

    def policy_store(self) -> SqlitePolicyStore:
        """Devuelve el componente REAL del cluster policy/budget (WI-56).

        Una unica instancia por ``Storage`` (cacheada): identidad
        estable, conexion compartida, SQL viviendo en
        ``platform/policy_store.py``. El facade conserva delegados
        con firma explicita (I1: cero ediciones en callers).
        """
        if getattr(self, "_policy_store", None) is None:
            from skillgraph.platform.policy_store import SqlitePolicyStore

            self._policy_store = SqlitePolicyStore(self)
        return self._policy_store

    # ----- delegados policy/budget (WI-56 corte 2) -----------------
    # El SQL vive en ``SqlitePolicyStore``; delegados con firma
    # explicita preservan la API del facade.

    def get_policy(
        self,
        *,
        tenant_id: str,
    ) -> str | None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.get_policy``."""
        return self.policy_store().get_policy(tenant_id=tenant_id)

    def upsert_policy(
        self,
        *,
        tenant_id: str,
        policy: str,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.upsert_policy``."""
        return self.policy_store().upsert_policy(tenant_id=tenant_id, policy=policy)

    def upsert_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        max_visits: int | None,
        max_runtime_seconds: int | None,
        max_events: int | None,
    ) -> None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.upsert_budget``."""
        return self.policy_store().upsert_budget(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            max_visits=max_visits,
            max_runtime_seconds=max_runtime_seconds,
            max_events=max_events,
        )

    def get_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredBudget | None:
        """Delegado WI-56: el SQL vive en ``SqlitePolicyStore.get_budget``."""
        return self.policy_store().get_budget(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

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

    @contextmanager
    def _atomic(self) -> Iterator[sqlite3.Cursor]:
        """Transaccion explicita con BEGIN/COMMIT/ROLLBACK.

        Necesario para operaciones multi-statement en las que un fallo
        a mitad NO deba dejar estado parcial en disco (H9-LIMITACION-7,
        V4 `record_trace`). `isolation_level=None` en `_conn` hace que
        cada `execute()` sea autocommit, por lo que `with self._conn:`
        NO rollbackea de verdad — la salida del bloque solo emite
        COMMIT o ROLLBACK si Python lo solicita explicitamente.

        Este helper:
          1. Emite `BEGIN` (start de transaccion manual).
          2. Yieldea un cursor sobre la conexion transaccional.
          3. Si el bloque retorna sin error: COMMIT explicito.
          4. Si el bloque lanza: ROLLBACK explicito + re-raise.

        Uso:
            with self._atomic() as cur:
                cur.execute(...)  # serollbackea si falla
                cur.execute(...)

        Tests: `tests/test_h9_limitacion_7_slice1.py::TestT17RecordTrace`.
        """
        self._conn.execute("BEGIN")
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.execute("COMMIT")
        except BaseException:
            # ROLLBACK es best-effort: si falla (p.ej. la conexion
            # esta rota), sqlite3 abortara la transaccion de todos
            # modos. Coherente con el patron de `*_atomically`.
            # Se capturan TODAS las excepciones (incluido KeyboardInterrupt)
            # porque el proposito es dejar la transacion consistente
            # antes de propagar: un `except Exception` dejaria el BEGIN
            # abierto si el fallo es una BaseException: un Ctrl-C no
            # debe dejar la transaccion a medias.
            with suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise

    # ----- recursos -----

    # ----- delegados del cluster knowledge (WI-56 corte 3) --------
    # El SQL vive en ``SqliteKnowledgeRepository``; delegados con
    # firma explicita preservan la API del facade (I1: cero
    # ediciones en callers).

    def upsert_resource(
        self,
        brick: Brick,
    ) -> str:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.upsert_resource``."""
        return self.knowledge_repository().upsert_resource(brick)

    def get_resource(
        self,
        uid: str,
    ) -> StoredResource | None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.get_resource``."""
        return self.knowledge_repository().get_resource(uid)

    def list_resources(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str | None = None,
    ) -> list[StoredResource]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_resources``."""
        return self.knowledge_repository().list_resources(
            tenant_id=tenant_id, project_id=project_id, kind=kind
        )

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
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.add_relation``."""
        return self.knowledge_repository().add_relation(
            tenant_id=tenant_id,
            project_id=project_id,
            source_uid=source_uid,
            target_uid=target_uid,
            kind=kind,
            properties=properties,
        )

    def dependencies_of(
        self,
        uid: str,
    ) -> list[StoredRelation]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.dependencies_of``."""
        return self.knowledge_repository().dependencies_of(uid)

    def dependents_of(
        self,
        uid: str,
    ) -> list[StoredRelation]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.dependents_of``."""
        return self.knowledge_repository().dependents_of(uid)

    def register_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source: Source,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.register_source``."""
        return self.knowledge_repository().register_source(
            tenant_id=tenant_id, project_id=project_id, source=source
        )

    def get_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
    ) -> Source | None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.get_source``."""
        return self.knowledge_repository().get_source(
            tenant_id=tenant_id, project_id=project_id, source_id=source_id
        )

    def list_sources(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[Source, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_sources``."""
        return self.knowledge_repository().list_sources(tenant_id=tenant_id, project_id=project_id)

    def update_source_freshness(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        freshness: str,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.update_source_freshness``."""
        return self.knowledge_repository().update_source_freshness(
            tenant_id=tenant_id, project_id=project_id, source_id=source_id, freshness=freshness
        )

    def source_exists_anywhere(
        self,
        *,
        source_id: str,
    ) -> bool:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.source_exists_anywhere``."""
        return self.knowledge_repository().source_exists_anywhere(source_id=source_id)

    def upsert_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        entity: Entity,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.upsert_entity``."""
        return self.knowledge_repository().upsert_entity(
            tenant_id=tenant_id, project_id=project_id, entity=entity
        )

    def get_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        entity_id: str,
    ) -> Entity | None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.get_entity``."""
        return self.knowledge_repository().get_entity(
            tenant_id=tenant_id, project_id=project_id, entity_id=entity_id
        )

    def find_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str,
        stable_key: str,
    ) -> Entity | None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.find_entity``."""
        return self.knowledge_repository().find_entity(
            tenant_id=tenant_id, project_id=project_id, kind=kind, stable_key=stable_key
        )

    def record_evidence(
        self,
        *,
        tenant_id: str,
        project_id: str,
        evidence: Evidence,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.record_evidence``."""
        return self.knowledge_repository().record_evidence(
            tenant_id=tenant_id, project_id=project_id, evidence=evidence
        )

    def get_evidences_for_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
    ) -> tuple[Evidence, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.get_evidences_for_claim``."""
        return self.knowledge_repository().get_evidences_for_claim(
            tenant_id=tenant_id, project_id=project_id, claim_id=claim_id
        )

    def record_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim: Claim,
    ) -> str:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.record_claim``."""
        return self.knowledge_repository().record_claim(
            tenant_id=tenant_id, project_id=project_id, claim=claim
        )

    def get_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
    ) -> Claim | None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.get_claim``."""
        return self.knowledge_repository().get_claim(
            tenant_id=tenant_id, project_id=project_id, claim_id=claim_id
        )

    def list_claims_for_subject(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
    ) -> list[Claim]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_claims_for_subject``."""
        return self.knowledge_repository().list_claims_for_subject(
            tenant_id=tenant_id, project_id=project_id, subject_entity_id=subject_entity_id
        )

    def list_claims_for_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
    ) -> list[Claim]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_claims_for_source``."""
        return self.knowledge_repository().list_claims_for_source(
            tenant_id=tenant_id, project_id=project_id, source_id=source_id
        )

    def list_claims_using_evidence(
        self,
        *,
        evidence_id: str,
    ) -> tuple[str, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_claims_using_evidence``."""
        return self.knowledge_repository().list_claims_using_evidence(evidence_id=evidence_id)

    def mark_claims_stale(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_ids: tuple[str, ...],
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.mark_claims_stale``."""
        return self.knowledge_repository().mark_claims_stale(
            tenant_id=tenant_id, project_id=project_id, claim_ids=claim_ids
        )

    def reactivate_claims_with_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        new_revision: str,
    ) -> tuple[str, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.reactivate_claims_with_revision``."""
        return self.knowledge_repository().reactivate_claims_with_revision(
            tenant_id=tenant_id,
            project_id=project_id,
            source_id=source_id,
            new_revision=new_revision,
        )

    def list_stale_claims(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[Any, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_stale_claims``."""
        return self.knowledge_repository().list_stale_claims(
            tenant_id=tenant_id, project_id=project_id
        )

    def list_claims_by_predicate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        predicate: str,
    ) -> tuple[StoredClaim, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_claims_by_predicate``."""
        return self.knowledge_repository().list_claims_by_predicate(
            tenant_id=tenant_id, project_id=project_id, predicate=predicate
        )

    def list_evidences_for_source(
        self,
        *,
        source_id: str,
    ) -> tuple[StoredEvidence, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_evidences_for_source``."""
        return self.knowledge_repository().list_evidences_for_source(source_id=source_id)

    def list_resource_refs_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        kind: str,
    ) -> tuple[str, ...]:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.list_resource_refs_for_run``."""
        return self.knowledge_repository().list_resource_refs_for_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id, kind=kind
        )

    def attach_evidence_to_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
        evidence_id: str,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.attach_evidence_to_claim``."""
        return self.knowledge_repository().attach_evidence_to_claim(
            tenant_id=tenant_id, project_id=project_id, claim_id=claim_id, evidence_id=evidence_id
        )

    def record_finding(
        self,
        *,
        tenant_id: str,
        project_id: str,
        finding: Finding,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.record_finding``."""
        return self.knowledge_repository().record_finding(
            tenant_id=tenant_id, project_id=project_id, finding=finding
        )

    def record_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace: OutcomeTrace,
    ) -> None:
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.record_trace``."""
        return self.knowledge_repository().record_trace(
            tenant_id=tenant_id, project_id=project_id, trace=trace
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
        """Delegado WI-56: ver ``SqliteKnowledgeRepository.link_trace``."""
        return self.knowledge_repository().link_trace(
            tenant_id=tenant_id,
            project_id=project_id,
            trace_id=trace_id,
            link_kind=link_kind,
            link_id=link_id,
            position=position,
        )

    # ----- relaciones -----

    # ----- H3 Slice 1: conocimiento (sources, entities, claims, etc.) -----
    #
    # Estas APIs NO son CRUD plano: devuelven los ADT de `skillgraph.knowledge`
    # cuando es posible, y dejan la logica de negocio (invalidacion
    # transitiva, hashing, glosario) al KnowledgeController que se introduce
    # en Slice 2.

    # ---- Sources

    # ---- Entities

    # ---- Evidences

    # ---- Claims

    # ---- WI-02b: ports de mantenimiento (invalidation, refresh) ----

    # ---- H9-Coverage-11: lecturas puras para ContextController (ADR-0014)
    #
    # Estas 3 APIs cierran los 4 sitios `_conn.execute` directos que
    # quedaron en ContextController despues del refactor H9-BSlice3.
    # Devuelven tuplas inmutables (no list) para mantener consistencia
    # con la regla "inmutabilidad por defecto" (AGENTS.md §1.1) y para
    # que el caller no pueda mutar el resultado por accidente.

    # ---- Findings

    # ---- Outcome traces

    # ----- Events (H3 Slice 4) -----

    # ----- delegados del cluster events (WI-56 corte 4) ----------
    # El SQL vive en ``SqliteEventStore``; delegados con firma
    # explicita preservan la API del facade (I1: cero ediciones en
    # callers). Los helpers atomicos _insert_event_in_tx y
    # _atomic_state_and_event siguen AQUI (H9/H10 los parchean).

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
        """Delegado WI-56: ver ``SqliteEventStore.record_event``."""
        return self.event_store().record_event(
            tenant_id=tenant_id,
            project_id=project_id,
            event_id=event_id,
            event_kind=event_kind,
            resource_ref=resource_ref,
            payload=payload,
            run_id=run_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            timestamp=timestamp,
        )

    def list_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
        resource_ref: str | None = None,
        event_kind: str | None = None,
    ) -> list[StoredEvent]:
        """Delegado WI-56: ver ``SqliteEventStore.list_events``."""
        return self.event_store().list_events(
            tenant_id=tenant_id,
            project_id=project_id,
            resource_ref=resource_ref,
            event_kind=event_kind,
        )

    def ensure_schema(self) -> None:
        """Delegado WI-56: ver ``SqliteEventStore.ensure_schema``."""
        return self.event_store().ensure_schema()

    def fetch_event_raw(
        self,
        *,
        event_id: str,
    ) -> StoredEvent | None:
        """Delegado WI-56: ver ``SqliteEventStore.fetch_event_raw``."""
        return self.event_store().fetch_event_raw(event_id=event_id)

    # ----- H7 promocion entre bases (UAT-13) -----

    def register_promotion(
        self,
        *,
        proposal_id: Any,
        idempotency_key: Any,
        tenant_id: Any,
        source_project: Any,
        target_catalog: Any,
        knowledge_ref: Any,
        payload: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().register_promotion(
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            source_project=source_project,
            target_catalog=target_catalog,
            knowledge_ref=knowledge_ref,
            payload=payload,
        )

    def get_promotion(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().get_promotion(
            proposal_id,
        )

    def list_pending_promotions(
        self,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().list_pending_promotions()

    # ----- lecturas del ciclo de vida de un Run (H9-BSlice3-S1) -----

    def _insert_event_in_tx(
        self,
        cur: sqlite3.Cursor,
        event: RuntimeEvent,
    ) -> None:
        """Inserta un RuntimeEvent en `runtime_events` usando el cursor
        dado (que pertenece a una transaccion ya abierta por el caller).

        NO llama `cur.connection.commit()` ni `with self._conn:`. El
        caller controla la transaccion.
        """
        import json as _json

        cur.execute(
            """
            INSERT INTO runtime_events
                (event_id, tenant_id, project_id, event_kind, run_id,
                 resource_ref, causation_id, correlation_id,
                 payload_json, timestamp, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.tenant_id,
                event.project_id,
                event.event_kind,
                event.run_id,
                event.resource_ref,
                event.causation_id,
                event.correlation_id,
                _json.dumps(dict(event.payload), ensure_ascii=False),
                event.timestamp,
                event.schema_version,
            ),
        )

    def _atomic_state_and_event(
        self,
        *,
        event: RuntimeEvent,
        exec_sql: tuple[str, tuple[Any, ...]],
    ) -> None:
        """Ejecuta una sentencia de mutacion de estado + el INSERT del
        evento en runtime_events bajo una SOLA transaccion SQLite
        (BEGIN explicito + COMMIT/ROLLBACK).

        Esto es necesario porque `with self._conn:` con
        ``isolation_level=None`` NO rollbackea al fallar dentro del
        cuerpo (cada ``execute`` ejecuta autocommit por sentencia).
        Plan B arranca de esta verididad: ver
        ``docs/architecture/h9-plan-b-atomicity-characterization.md``
        §3 (grieta H9-Plan-B) y §5 (estrategia).

        Re-raise como ``IdempotencyError`` cuando el UNIQUE sobre
        ``runtime_events.event_id`` se viola (UAT-07, replay-safe).
        """
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(exec_sql[0], exec_sql[1])
            self._insert_event_in_tx(self._conn.cursor(), event)
            self._conn.execute("COMMIT")
        except BaseException:
            # El cuerpo de la transaccion puede lanzar CUALQUIER cosa
            # (validacion de dominio, TypeError, ...), no solo errores
            # de sqlite3. Estrechar aqui a `sqlite3.Error` dejaba el
            # BEGIN abierto ante un ValidationError, que es peor que
            # el except ancho que se queria evitar. Lo que si se
            # estrecha es el ROLLBACK, que solo habla de la conexion.
            with suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise

    def list_promotions(
        self,
        status: Any = None,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().list_promotions(
            status,
        )

    def mark_promotion_in_progress(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().mark_promotion_in_progress(
            proposal_id,
        )

    def mark_promotion_published(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().mark_promotion_published(
            proposal_id,
        )

    def mark_promotion_failed(
        self,
        proposal_id: Any,
    ) -> Any:
        """Delegado WI-56: el SQL vive en SqlitePromotionRepository."""
        return self.promotion_repository().mark_promotion_failed(
            proposal_id,
        )


# --- Helpers de conversion row -> ADT -------------------------------------


def _row_to_source(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_source``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_source

    return row_to_source(row, json)


def _row_to_evidence(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_evidence``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_evidence

    return row_to_evidence(row, json)


def _row_to_stored_evidence(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_stored_evidence``. El corte 5
    reubicara los callers."""
    from skillgraph.platform.knowledge_repository import row_to_stored_evidence

    return row_to_stored_evidence(row, json)


def _row_to_claim(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_claim``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_claim

    return row_to_claim(row, [], json)


def _row_to_stored_claim(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_stored_claim``. El corte 5
    reubicara los callers."""
    from skillgraph.platform.knowledge_repository import row_to_stored_claim

    return row_to_stored_claim(row, json)


def _row_to_run(row: sqlite3.Row) -> StoredRun:
    """Convierte una fila de ``workflow_runs`` al DTO ``StoredRun``.

    WI-32.4: sustituye ``dict(row)`` por una traduccion tipada.
    El adapter expone ``StoredRun`` (frozen + slots) en vez de dict
    mutable, evitando que ``sqlite3.Row`` escape del modulo
    ``platform/``.
    """
    return StoredRun(
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        state=row["state"],
        plan_json=row["plan_json"],
        current_node=row["current_node"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_node_execution(row: sqlite3.Row) -> StoredNodeExecution:
    """Convierte una fila de ``node_executions`` al DTO ``StoredNodeExecution``.

    WI-32.4: sustituye ``dict(row)`` por una traduccion tipada.
    ``StoredNodeExecution`` es frozen + slots y refleja 1:1 la tabla.
    """
    return StoredNodeExecution(
        node_execution_id=row["node_execution_id"],
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        node_name=row["node_name"],
        attempt=row["attempt"],
        state=row["state"],
        outcome=row["outcome"],
        context_hash=row["context_hash"],
        handoff_json=row["handoff_json"],
        result_json=row["result_json"],
        error=row["error"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _row_to_resource(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_resource``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_resource

    return row_to_resource(row)


def _row_to_relation(row: sqlite3.Row) -> Any:
    """Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
    ``SqliteKnowledgeRepository.row_to_relation``. El corte 5 reubicara
    los callers."""
    from skillgraph.platform.knowledge_repository import row_to_relation

    return row_to_relation(row)


def open_project_storage(path: str | Path) -> Storage:
    """Ayuda para abrir el almacenamiento de un proyecto.

    Cualquier error de validación aquí es bug: este helper no debería
    recibir paths fuera de los directorios gestionados por la CLI.
    """
    if not str(path).endswith(".sqlite"):
        raise ValidationError(f"Path de proyecto debe terminar en .sqlite: {path}")
    return Storage(path)
