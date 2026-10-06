"""Componente CLAIMS del knowledge (WI-61, ADR-0020 fase 2).

Los 9 metodos de claims salen de `SqliteKnowledgeRepository` verbatim:
mismo contrato, misma conexion compartida via `_storage`. La fachada
delega en este componente; los mappers viven en
`knowledge_mappers.py` (fase 1).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from skillgraph.core.errors import InvalidEntityIDError
from skillgraph.knowledge.graph import Claim
from skillgraph.platform.knowledge_mappers import (
    objeto_del_claim,
    row_to_claim as _row_to_claim,
    row_to_stored_claim as _row_to_stored_claim,
)
from skillgraph.platform.storage import Storage, StoredClaim


class SqliteClaimRepository:
    """Claims del grafo de conocimiento (clusters CLAIMS de la clase
    original). Comparte `_storage` con la fachada; `_conn` se deriva
    igual que en `SqliteKnowledgeRepository`.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._storage._conn

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

        **B25: UN objeto o el otro, nunca los dos.** La columna nueva
        `object_entity_id` lleva `''` cuando el objeto es un literal, y el
        literal lleva `''` cuando el objeto es una entidad. Es el mismo XOR que
        sostiene `Claim.__post_init__` y el CHECK de la tabla; los tres dicen la
        misma pregunta a proposito, porque si uno se apartara los otros dos
        darian verde sobre filas que la base rechazaria.

        **`json.dumps` NUNCA produce `''`**, luego el marcador no puede
        confundirse con un literal: `json.dumps("")` es `'""'`, con comillas.
        """
        if claim.object_entity is not None:
            self._exige_que_exista_la_entidad(
                tenant_id=tenant_id, project_id=project_id, entity_id=claim.object_entity.entity_id
            )
            obj_json = ""
            ref = claim.object_entity.entity_id
        else:
            obj_json = json.dumps(claim.object_literal, sort_keys=True)
            ref = ""

        with self._storage._atomic() as cur:
            cur.execute(
                """
                INSERT OR IGNORE INTO claims
                    (claim_id, tenant_id, project_id, subject_entity_id,
                     predicate, object_literal_json, source_id,
                     assertion_origin,
                     extraction_method, extractor_version,
                     checked_at_revision, stale, object_entity_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    tenant_id,
                    project_id,
                    claim.subject_entity_id,
                    claim.predicate,
                    obj_json,
                    claim.source_id,
                    claim.assertion_origin,
                    claim.extraction_method,
                    claim.extractor_version,
                    claim.checked_at_revision,
                    int(claim.stale),
                    ref,
                ),
            )
            # Attach evidence links (idempotente).
            for evidence_id in claim.evidence_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?)",
                    (claim.claim_id, evidence_id),
                )
        return claim.claim_id

    def _exige_que_exista_la_entidad(
        self, *, tenant_id: str, project_id: str, entity_id: str
    ) -> None:
        """B25: la referencia tiene que apuntar a algo que exista.

        **POR QUE ESTA COMPROBACION EN LUGAR DE UNA CLAVE FORANEA.** MEDIDO con
        `PRAGMA foreign_keys = ON`, que es como abre `storage.py`: declarar
        `REFERENCES entities(entity_id)` en la columna nueva rechaza TODOS los
        claims literales, porque el marcador `''` no es una entidad. La columna
        no puede llevar la FK, y la garantia se recupera aqui.

        Lo que eso cuesta, dicho: una escritura que no pase por
        `record_claim` no tiene la garantia. Se acepta porque la alternativa
        —una columna nullable con `NULL` de ausencia— obliga a quitar el
        `NOT NULL` de `object_literal_json`, y SQLite no puede: habria que
        reconstruir la tabla entera.
        """
        fila = self._conn.execute(
            "SELECT 1 FROM entities WHERE entity_id = ? AND tenant_id = ? AND project_id = ?",
            (entity_id, tenant_id, project_id),
        ).fetchone()
        if fila is None:
            raise InvalidEntityIDError(
                f"la entidad {entity_id!r} no existe en ({tenant_id}, {project_id}); "
                "un claim no puede apuntar a una entidad que no esta"
            )

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
                   c.assertion_origin, c.extraction_method, c.extractor_version,
                   c.checked_at_revision, c.stale, c.object_entity_id,
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
            object_literal, object_entity = objeto_del_claim(row, json)
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=object_literal,
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    assertion_origin=row["assertion_origin"],
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                    object_entity=object_entity,
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
        rows = self._conn.execute(
            """
            SELECT c.claim_id, c.subject_entity_id, c.predicate,
                   c.object_literal_json, c.source_id,
                   c.assertion_origin, c.extraction_method, c.extractor_version,
                   c.checked_at_revision, c.stale, c.object_entity_id,
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
            object_literal, object_entity = objeto_del_claim(row, json)
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=object_literal,
                    source_id=row["source_id"],
                    evidence_ids=ev_ids,
                    assertion_origin=row["assertion_origin"],
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                    object_entity=object_entity,
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

    def list_claims_by_object_entity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        object_entity_id: str,
    ) -> tuple[StoredClaim, ...]:
        """B25: los claims cuyo OBJETO es esa entidad. La pregunta «¿qué
        afirma sobre X que sea otra cosa?».

        **POR QUE ESTA CONSULTA ES PARTE DEL BLOQUE Y NO UNA EXTRA.** Sin ella
        la referencia a entidad se guardaría y no se podría preguntar por ella:
        sería un dato que se escribe y nunca se lee, que es peor que no
        tenerlo —porque el que lo escribió creería que sí. Es la consulta que
        B27 necesita para encontrar dos claims incompatibles que apuntan a la
        misma entidad, y la primera mitad de `changed` en B34.

        Usa `idx_claims_object_entity`, que es un indice PARCIAL sobre las
        filas con referencia: los claims literales, que son la mayoria, no
        ocupan sitio en el.

        La forma de devolver (`StoredClaim`, no `Claim`) es la de
        `list_claims_by_predicate` y la de `list_stale_claims`; se copia la
        que ya existe en el sitio, no la que seria mas comoda aqui.
        """
        rows = self._conn.execute(
            """
            SELECT c.*, GROUP_CONCAT(ce.evidence_id) AS evidence_ids_csv
            FROM claims c
            LEFT JOIN claim_evidence ce ON ce.claim_id = c.claim_id
            WHERE c.tenant_id = ? AND c.project_id = ?
              AND c.object_entity_id = ? AND c.object_entity_id <> ''
            GROUP BY c.claim_id
            ORDER BY c.checked_at_revision DESC
            """,
            (tenant_id, project_id, object_entity_id),
        ).fetchall()
        return tuple(_row_to_stored_claim(row, json) for row in rows)
