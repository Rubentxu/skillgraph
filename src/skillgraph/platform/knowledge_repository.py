"""SqliteKnowledgeRepository: componente WI-56 corte 3.

Implementacion real del cluster knowledge del ``Storage`` god-module
(ADR-0016, strangler). Extraido verbatim de ``platform/storage.py``
en WI-56: el SQL y el orden de columnas no cambian; solo cambia el
dueno del codigo. El schema y la migracion siguen en ``Storage``.

Mapea metodos 1:1 con los delegados del facade ``Storage``; los
callers no se tocan (I1). Los mappers ``row_to_*`` viven aqui (renombrados
sin guion bajo); ``storage.py`` conserva aliases privados de
compatibilidad hasta el corte 5. El contexto de transaccion
``_atomic`` sigue siendo del ``Storage`` dueno (corte 4 lo decidira).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from skillgraph.core.errors import IdentityConflictError, ValidationError
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)

# WI-60 (ADR-0020 fase 1): mappers reubicados; re-export para la clase,
# los shims de storage.py y cualquier consumidor del simbolo.
from skillgraph.platform.knowledge_mappers import (
    row_to_claim,
    row_to_evidence,
    row_to_relation,
    row_to_resource,
    row_to_source,
    row_to_stored_claim,
    row_to_stored_evidence,
)
from skillgraph.platform.ports import (
    StoredClaim,
    StoredEvidence,
    StoredRelation,
    StoredResource,
)
from skillgraph.platform.storage import Storage, _uid
from skillgraph.resources.bricks import Brick


class SqliteKnowledgeRepository:
    """Implementacion real de ``KnowledgeRepository`` sobre la conexion
    de ``Storage``. No duena el schema ni la migracion; solo habla SQL
    del cluster knowledge con la misma forma que ``Storage`` tenia."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        """Conexion compartida con el ``Storage`` dueno del schema."""
        return self._storage._conn  # composicion interna acordada en ADR-0016

    def upsert_resource(self, brick: Brick) -> str:
        """Registra un brick. Lanza `IdentityConflictError` si cambia
        `spec` bajo la misma identidad (versión bumped +409 conflict).
        """

        uid = _uid(brick)
        spec_json = json.dumps(brick.spec, sort_keys=True)
        with self._storage._tx() as cur:
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

    def get_resource(self, uid: str) -> StoredResource | None:
        """Devuelve el DTO de un Resource por uid.

        WI-32.5: devuelve ``StoredResource`` (frozen + slots) en vez
        de ``dict``, manteniendo la frontera de persistencia.
        """
        row = self._conn.execute("SELECT * FROM resources WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None
        return _row_to_resource(row)

    def list_resources(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str | None = None,
    ) -> list[StoredResource]:
        """Lista Resources por (tenant, project) con filtro opcional de kind.

        WI-32.5: devuelve ``list[StoredResource]`` en vez de
        ``list[dict]``.
        """
        sql = "SELECT * FROM resources WHERE tenant_id = ? AND project_id = ?"
        params: tuple[Any, ...] = (tenant_id, project_id)
        if kind is not None:
            sql += " AND api_version || '/' || kind = ? OR kind = ?"
            params = (tenant_id, project_id, kind, kind)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_resource(r) for r in rows]

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
        import uuid

        properties = properties or {}
        props_json = json.dumps(properties, sort_keys=True)
        rid = str(uuid.uuid4())
        with self._storage._tx() as cur:
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

    def dependencies_of(self, uid: str) -> list[StoredRelation]:
        """Aristas salientes: 'qué necesita este recurso' (target).

        WI-32.5: devuelve ``list[StoredRelation]`` en vez de
        ``list[dict]``.
        """
        rows = self._conn.execute("SELECT * FROM relations WHERE source_uid = ?", (uid,)).fetchall()
        return [_row_to_relation(r) for r in rows]

    def dependents_of(self, uid: str) -> list[StoredRelation]:
        """Aristas entrantes: 'qué recursos apuntan a este' (source).

        WI-32.5: devuelve ``list[StoredRelation]`` en vez de
        ``list[dict]``.
        """
        rows = self._conn.execute("SELECT * FROM relations WHERE target_uid = ?", (uid,)).fetchall()
        return [_row_to_relation(r) for r in rows]

    def register_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source: Source,
    ) -> None:
        """Registra una Source. Idempotente por `source_id` (PK)."""

        locator_json = json.dumps(source.locator, sort_keys=True)
        wts_json = (
            json.dumps(source.working_tree_status, sort_keys=True)
            if source.working_tree_status is not None
            else None
        )
        with self._storage._tx() as cur:
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

        row = self._conn.execute(
            "SELECT * FROM sources WHERE source_id = ? AND tenant_id = ? AND project_id = ?",
            (source_id, tenant_id, project_id),
        ).fetchone()
        if row is None:
            return None
        return _row_to_source(row, json)

    def list_sources(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[Source, ...]:
        """Sources del tenant/project (read-only, orden determinista por source_id).

        WI-03: migra el escape hatch ``storage._conn.execute('SELECT source_id
        FROM sources ...')`` que hacia ``receipts.list_applicable_receipts``.
        Devuelve tupla inmutable (regla AGENTS §1.1).
        """

        rows = self._conn.execute(
            "SELECT * FROM sources WHERE tenant_id = ? AND project_id = ? ORDER BY source_id",
            (tenant_id, project_id),
        ).fetchall()
        return tuple(_row_to_source(row, json) for row in rows)

    def update_source_freshness(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        freshness: str,
    ) -> None:
        """Cambia `freshness` de una Source (e.g. fresh -> stale)."""
        with self._storage._tx() as cur:
            cur.execute(
                "UPDATE sources SET freshness = ? WHERE source_id = ? AND tenant_id = ? AND project_id = ?",
                (freshness, source_id, tenant_id, project_id),
            )

    def source_exists_anywhere(self, *, source_id: str) -> bool:
        """True si el ``source_id`` existe en cualquier tenant/project.

        WI-02b: distingue typo de source vs pertenencia a otro proyecto
        (regla de leakage cross-tenant ADR-0015).
        """
        row = self._conn.execute(
            "SELECT 1 FROM sources WHERE source_id = ? LIMIT 1",
            (source_id,),
        ).fetchone()
        return row is not None

    def upsert_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        entity: Entity,
    ) -> None:
        """Inserta o reemplaza una Entity. UNIQUE(kind, stable_key) por tenant/project."""
        with self._storage._tx() as cur:
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

    def find_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        kind: str,
        stable_key: str,
    ) -> Entity | None:
        """Busca una Entity por (kind, stable_key). None si no existe.

        WI-02b: nuevo metodo del ``KnowledgeRepository`` Protocol que
        elimina el acceso directo a ``storage._conn`` que hacia
        ``KnowledgeController.find_entity``.
        """
        row = self._conn.execute(
            """
            SELECT * FROM entities
            WHERE tenant_id = ? AND project_id = ?
              AND kind = ? AND stable_key = ?
            """,
            (tenant_id, project_id, kind, stable_key),
        ).fetchone()
        if row is None:
            return None
        return Entity(
            entity_id=row["entity_id"],
            kind=row["kind"],
            stable_key=row["stable_key"],
        )

    def record_evidence(
        self,
        *,
        tenant_id: str,
        project_id: str,
        evidence: Evidence,
    ) -> None:
        """Registra una Evidence (FK a sources). Inmutable: re-registrar con
        mismo `evidence_id` es no-op (INSERT OR IGNORE)."""

        content_json = (
            json.dumps(evidence.content, sort_keys=True)
            if not isinstance(evidence.content, str)
            else json.dumps(evidence.content)
        )
        with self._storage._tx() as cur:
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

    def record_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim: Claim,
    ) -> str:
        """Registra una Claim. Devuelve su claim_id. Idempotente por
        (subject, predicate, source, checked_at_revision).

        Usa `_atomic()` (BEGIN/COMMIT/ROLLBACK explicitos) en vez de
        `_tx()` para garantizar que un fallo a mitad de las 1+N
        sentencias no deje un `claims` orphan (sin sus
        `claim_evidence` completos). H9-LIMITACION-7 V6.
        """

        obj_json = json.dumps(claim.object_literal, sort_keys=True)
        with self._storage._atomic() as cur:
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

    def list_claims_for_subject(
        self,
        *,
        tenant_id: str,
        project_id: str,
        subject_entity_id: str,
    ) -> list[Claim]:
        """Lista Claims cuyo ``subject_entity_id`` coincide, con evidence_ids pre-cargados.

        WI-02b: sustituye el patron N+1 que hacia antes ``KnowledgeController.
        list_claims_for_subject`` con dos queries separadas (claims +
        claim_evidence dentro de un bucle por row). Aqui se hace una sola
        query con LEFT JOIN para que el adapter SQLite sea responsable de
        la atomicidad del join, no el caller.
        """

        rows = self._conn.execute(
            """
            SELECT c.claim_id, c.subject_entity_id, c.predicate,
                   c.object_literal_json, c.source_id,
                   c.extraction_method, c.extractor_version,
                   c.checked_at_revision, c.stale,
                   GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ?
              AND c.subject_entity_id = ?
            GROUP BY c.claim_id
            ORDER BY c.checked_at_revision DESC
            """,
            (tenant_id, project_id, subject_entity_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_csv = row["evidence_ids_csv"] or ""
            ev_ids = tuple(ev_csv.split(",")) if ev_csv else ()
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=json.loads(row["object_literal_json"]),
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                )
            )
        return out

    def list_claims_for_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
    ) -> list[Claim]:

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

    def list_claims_using_evidence(self, *, evidence_id: str) -> tuple[str, ...]:
        """Tupla de claim_ids que referencian la evidence."""
        rows = self._conn.execute(
            "SELECT claim_id FROM claim_evidence WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchall()
        return tuple(r["claim_id"] for r in rows)

    def mark_claims_stale(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_ids: tuple[str, ...],
    ) -> None:
        """Bulk UPDATE: marca stale=1 en una sola transaccion."""
        if not claim_ids:
            return
        placeholders = ",".join("?" * len(claim_ids))
        with self._storage._tx() as cur:
            cur.execute(
                f"""
                UPDATE claims
                SET stale = 1
                WHERE tenant_id = ? AND project_id = ?
                  AND claim_id IN ({placeholders})
                """,
                (tenant_id, project_id, *claim_ids),
            )

    def reactivate_claims_with_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_id: str,
        new_revision: str,
    ) -> tuple[str, ...]:
        """Bulk UPDATE ... RETURNING: reactiva claims con la nueva revision."""
        with self._storage._tx() as cur:
            cur.execute(
                """
                UPDATE claims
                SET stale = 0
                WHERE tenant_id = ? AND project_id = ?
                  AND source_id = ? AND checked_at_revision = ?
                  AND stale = 1
                RETURNING claim_id
                """,
                (tenant_id, project_id, source_id, new_revision),
            )
            rows = cur.fetchall()
        return tuple(r["claim_id"] for r in rows)

    def list_stale_claims(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[Any, ...]:
        """Lista Claims stale con LEFT JOIN pre-cargado (sin N+1)."""
        import json as _json

        rows = self._conn.execute(
            """
            SELECT c.claim_id, c.subject_entity_id, c.predicate,
                   c.object_literal_json, c.source_id,
                   c.extraction_method, c.extractor_version,
                   c.checked_at_revision, c.stale,
                   GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ? AND c.stale = 1
            GROUP BY c.claim_id
            ORDER BY c.checked_at_revision DESC
            """,
            (tenant_id, project_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_csv = row["evidence_ids_csv"] or ""
            ev_ids = tuple(ev_csv.split(",")) if ev_csv else ()
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=_json.loads(row["object_literal_json"]),
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                )
            )
        return tuple(out)

    def list_claims_by_predicate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        predicate: str,
    ) -> tuple[StoredClaim, ...]:
        """Devuelve todos los Claims con `predicate == value` para el
        (tenant, project) dado.

        El adapter deserializa JSON y carga los evidence ids asociados.
        """

        rows = self._conn.execute(
            """
            SELECT c.*, GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ? AND c.predicate = ?
            GROUP BY c.claim_id
            """,
            (tenant_id, project_id, predicate),
        ).fetchall()
        return tuple(_row_to_stored_claim(row, json) for row in rows)

    def list_evidences_for_source(
        self,
        *,
        source_id: str,
    ) -> tuple[StoredEvidence, ...]:
        """Devuelve todas las Evidences asociadas a `source_id`.

        NO filtra por tenant+project: la fuente ya garantiza aislamiento
        (source_id es unico en el sistema via PK + FK en claims).
        El adapter deserializa `content_json` antes de devolver el DTO.
        """

        rows = self._conn.execute(
            "SELECT * FROM evidences WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        return tuple(_row_to_stored_evidence(row, json) for row in rows)

    def list_resource_refs_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        kind: str,
    ) -> tuple[str, ...]:
        """Devuelve los `resource_ref` unicos del run dado, filtrados por
        prefijo `claim:` o `evidence:`.

        Reemplaza los 2 sitios `_conn.execute` casi-identicos del
        OutcomeTracer (lineas 402-410 y 413-421 de context_controller.py).
        El parametro `kind` valida contra `Literal["claim", "evidence"]`
        en runtime; cualquier otro valor lanza `ValidationError`.
        """
        # Validacion atomica: kind debe ser uno de los prefijos validos.
        # Esto blinda un error silencioso si el caller pasa un kind
        # arbitrario (la query usaria `LIKE '%:%'` y devolveria TODOS
        # los refs, no los filtrados por tipo).
        if kind not in ("claim", "evidence"):
            from skillgraph.core.errors import ValidationError

            raise ValidationError(f"kind debe ser 'claim' o 'evidence', recibio {kind!r}")
        rows = self._conn.execute(
            "SELECT DISTINCT resource_ref FROM runtime_events "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ? "
            "  AND resource_ref LIKE ? "
            "ORDER BY resource_ref",
            (tenant_id, project_id, run_id, f"{kind}:%"),
        ).fetchall()
        return tuple(row["resource_ref"] for row in rows)

    def attach_evidence_to_claim(
        self,
        *,
        tenant_id: str,
        project_id: str,
        claim_id: str,
        evidence_id: str,
    ) -> None:
        """Adjunta una Evidence a un Claim (N:M). Idempotente (PK compuesta)."""
        with self._storage._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
                (claim_id, evidence_id),
            )

    def record_finding(
        self,
        *,
        tenant_id: str,
        project_id: str,
        finding: Finding,
    ) -> None:
        """Registra un Finding. Idempotente por `finding_id` (PK)."""

        ev_json = json.dumps(list(finding.evidence_ids), sort_keys=True)
        with self._storage._tx() as cur:
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

    def record_trace(
        self,
        *,
        tenant_id: str,
        project_id: str,
        trace: OutcomeTrace,
    ) -> None:
        """Registra un OutcomeTrace y sus enlaces (claim/evidence en orden).

        Idempotente por `trace_id` y por `(trace_id, link_kind, link_id)`.

        Usa `_atomic()` (BEGIN/COMMIT/ROLLBACK explicitos) en vez de
        `_tx()` para garantizar que un fallo a mitad de las 1+N
        sentencias no deje un `outcome_traces` orphan (sin sus
        `outcome_trace_links`). H9-LIMITACION-7 V4.
        """
        with self._storage._atomic() as cur:
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
        with self._storage._tx() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO outcome_trace_links
                    (trace_id, link_kind, link_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (trace_id, link_kind, link_id, position),
            )


# Los cuerpos extraidos verbatim llaman a los mappers por su nombre
# privado historico; estos aliases de modulo mantienen ese nombre
# apuntando a las definiciones publicas de arriba (corte 5 unificara).
_row_to_source = row_to_source
_row_to_evidence = row_to_evidence
_row_to_stored_evidence = row_to_stored_evidence
_row_to_claim = row_to_claim
_row_to_stored_claim = row_to_stored_claim
_row_to_resource = row_to_resource
_row_to_relation = row_to_relation
