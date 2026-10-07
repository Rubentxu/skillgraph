"""``SqliteSourceRepository``: fuentes de conocimiento y entidades.

SEGUNDO CORTE DE R1. `knowledge_repository.py` seguia por encima del umbral
de 800 LoC despues de sacar las trazas, y aqui estan **las ocho
responsabilidades** que quedan con un limite claro.

# POR QUE `sources` Y `entities` EN UN SOLO COMPONENTE

Las dos son la capa de **identidad**: quien afirma y **sobre qué**. Y estan
unidas por una FK (`entities.source_id` → `sources.source_id`) y por una
politica comun —la frescura de la fuente decide si lo que afirma sobre ella
esta stale—. Partirlas en dos ficheros pondria esa politica partida en dos
sitios que pueden apartarse, que es la clase de defecto que B14 ya midio
cuando dos mitigaciones_.

El corte es **verbatim**: el cuerpo se movio sin reescribirlo. Un refactor
que reescribe el SQL mientras lo mueve son dos cambios a la vez, y cuando
algo falla no se sabe cual.

# LO QUE NO ENTRA

    claims    -> SqliteClaimRepository (B25-B29)
    conflicts -> SqliteConflictRepository (B27-B28)
    traces    -> SqliteOutcomeTraceRepository (este bloque)
    resources -> la fachada, que es donde ya vivian
"""

from __future__ import annotations

import json
import sqlite3

from skillgraph.knowledge.graph import Entity, Source
from skillgraph.platform.knowledge_mappers import row_to_source
from skillgraph.platform.storage import Storage


class SqliteSourceRepository:
    """Fuentes y entidades. Sin estado propio: comparte la conexión."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._storage._conn

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
        return row_to_source(row, json)

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
        return tuple(row_to_source(row, json) for row in rows)

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


__all__ = ["SqliteSourceRepository"]
