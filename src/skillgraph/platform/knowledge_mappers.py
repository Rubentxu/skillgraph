"""Mappers fila-SQLite -> DTO del knowledge (WI-60, ADR-0020 fase 1).

Extraidos verbatim de `knowledge_repository.py`: funciones puras de
traduccion, sin SQL y sin conexion. `knowledge_repository` re-exporta
los simbolos para los shims de `storage.py` (ADR-0016 corte 5).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skillgraph.knowledge.graph import Claim, EntityID, EntityRef, Evidence, Source
from skillgraph.platform.storage import StoredClaim, StoredEvidence, StoredRelation, StoredResource


def row_to_source(row: sqlite3.Row, json: Any) -> Source:
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


def row_to_evidence(row: sqlite3.Row, json: Any) -> Evidence:
    content: Any = json.loads(row["content_json"])
    return Evidence(
        evidence_id=row["evidence_id"],
        kind=row["kind"],
        content=content,
        source_id=row["source_id"],
        observed_at=row["observed_at"],
    )


def row_to_stored_evidence(row: sqlite3.Row, json: Any) -> StoredEvidence:
    """Convierte una fila de ``evidences`` al DTO de ports."""
    try:
        content = json.loads(row["content_json"])
    except json.JSONDecodeError:
        content = row["content_json"]
    return StoredEvidence(
        evidence_id=row["evidence_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        kind=row["kind"],
        content=content,
        source_id=row["source_id"],
        observed_at=row["observed_at"],
    )


def objeto_del_claim(row: sqlite3.Row, json: Any) -> tuple[object, EntityRef | None]:
    """B25: el objeto de un claim, en sus dos formas y sin adivinar.

    **POR QUE NO SE ADIVINA MIRANDO EL JSON.** Una implementacion que metiera la
    referencia dentro de `object_literal_json` con una etiqueta tendria que
    distinguir al leer entre «un dict que es una referencia» y «un dict que un
    usuario escribió y se parece a una referencia» — y no hay forma de
    distinguirlos. Por eso la referencia tiene columna propia, y por eso aquí la
    pregunta es «¿qué dice la columna?», no «¿qué forma tiene esto?».

    La columna `object_entity_id` es `NOT NULL`, luego llega SIEMPRE: `''` es el
    marcador de ausencia y no lo produce nunca `json.dumps`. Se mira el
    conjunto de columnas porque una consulta que no la selecciona —`SELECT *` de
    una base pre-B25, o una consulta explicita de las anteriores a este
    bloque— no es una fila sin referencia: es una fila de un esquema anterior.

    **`# noqa: SIM118` NO ES COSMETICO, ES LO CONTRARIO DE LO QUE PARECE.**
    ruff pide cambiar `x in row.keys()` por `x in row`. MEDIDO en SQLite:

        'a' in r        -> False      # con la columna 'a' presente y valiendo 1
        'a' in r.keys() -> True

    `sqlite3.Row` **no implementa `__contains__`**, luego `in` cae al iterable
    de la fila y compara contra los VALORES. Aplicar el autofix de ruff habria
    hecho que toda fila con referencia se leyera como si no tuviera columna, y
    el round-trip devolveria `None` sin que ningun test lo notara: se busco un
    predicado que no existe, nunca se comparo un valor con un nombre.
    """
    # ruff no puede saber que `row` es un sqlite3.Row y no un dict.
    if "object_entity_id" not in row.keys():  # noqa: SIM118
        # Esquema anterior a B25: toda fila es literal. No es un caso teorico;
        # lo produce abrir una base con una version vieja que no ha migrado.
        return (json.loads(row["object_literal_json"]), None)

    ref = row["object_entity_id"]
    if ref:
        return (None, EntityRef(EntityID(ref)))
    return (json.loads(row["object_literal_json"]), None)


def row_to_claim(row: sqlite3.Row, evidence_ids: list[str], json: Any) -> Claim:
    object_literal, object_entity = objeto_del_claim(row, json)
    return Claim(
        claim_id=row["claim_id"],
        subject_entity_id=row["subject_entity_id"],
        predicate=row["predicate"],
        object_literal=object_literal,
        source_id=row["source_id"],
        evidence_ids=tuple(evidence_ids),
        assertion_origin=row["assertion_origin"],
        extraction_method=row["extraction_method"],
        extractor_version=row["extractor_version"],
        checked_at_revision=row["checked_at_revision"],
        stale=bool(row["stale"]),
        object_entity=object_entity,
    )


def row_to_stored_claim(row: sqlite3.Row, json: Any) -> StoredClaim:
    """Convierte una fila de ``claims`` al DTO de ports."""
    evidence_csv = row["evidence_ids_csv"] or ""
    evidence_ids = tuple(evidence_csv.split(",")) if evidence_csv else ()
    try:
        object_literal = json.loads(row["object_literal_json"])
    except json.JSONDecodeError:
        object_literal = row["object_literal_json"]
    return StoredClaim(
        claim_id=row["claim_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        subject_entity_id=row["subject_entity_id"],
        predicate=row["predicate"],
        object_literal=object_literal,
        source_id=row["source_id"],
        evidence_ids=evidence_ids,
        assertion_origin=row["assertion_origin"],
        extraction_method=row["extraction_method"],
        extractor_version=row["extractor_version"],
        checked_at_revision=row["checked_at_revision"],
        stale=bool(row["stale"]),
        object_entity_id=(row["object_entity_id"] if "object_entity_id" in row.keys() else ""),  # noqa: SIM118
    )


def row_to_resource(row: sqlite3.Row) -> StoredResource:
    """Convierte una fila de ``resources`` al DTO ``StoredResource``.

    WI-32.5: sustituye ``dict(row)`` por una traduccion tipada. El
    adapter expone ``StoredResource`` (frozen + slots) en vez de
    ``dict``, manteniendo la frontera de persistencia.
    """
    return StoredResource(
        uid=row["uid"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        api_version=row["api_version"],
        kind=row["kind"],
        namespace=row["namespace"],
        name=row["name"],
        resource_version=row["resource_version"],
        generation=row["generation"],
        spec_json=row["spec_json"],
        status_json=row["status_json"],
        created_at=row["created_at"],
    )


def row_to_relation(row: sqlite3.Row) -> StoredRelation:
    """Convierte una fila de ``relations`` al DTO ``StoredRelation``.

    WI-32.5: sustituye ``dict(row)`` por traduccion tipada.
    ``StoredRelation`` es frozen + slots y refleja 1:1 la tabla.
    """
    return StoredRelation(
        uid=row["uid"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        source_uid=row["source_uid"],
        target_uid=row["target_uid"],
        kind=row["kind"],
        properties_json=row["properties_json"],
    )
