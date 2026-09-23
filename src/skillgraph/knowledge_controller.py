"""KnowledgeController: API de alto nivel para el subsistema de conocimiento.

Doc externo:
  specs/h3-slice-2.md (sub-spec firmado en el H3).
  external/blueprint-v1/docs/08-conocimiento-y-contexto.md.
  external/blueprint-v1/adr/ADR-0011-controladores.md.

Este modulo introduce la clase `KnowledgeController` que envuelve los
metodos de `Storage` introducidos en Slice 1. Encapsula:

- Validacion previa (los ADT frozen ya validan en `__post_init__`).
- Generacion automatica de IDs reproducibles via UUIDv5.
- Aislamiento por `(tenant_id, project_id)` inyectado en `__init__`.
- Conversion de errores de Storage a errores de dominio:
  - FK violation -> UnknownEntityError / UnknownSourceError.
  - "not found" en lookup -> UnknownSourceError / UnknownClaimError.

Lo que NO hace este slice:
- Invalidacion transitiva (slice 4).
- Git fingerprinting (slice 3).
- ContextRecipe / Handoff (slice 5).
"""

from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass

from skillgraph.errors import (
    NotFoundError,
    StaleKnowledgeWarning,
    UnknownClaimError,
    UnknownEntityError,
    UnknownSourceError,
)
from skillgraph.knowledge import (
    Claim,
    ClaimID,
    Entity,
    EntityID,
    Evidence,
    EvidenceID,
    Finding,
    FindingID,
    OutcomeTrace,
    Source,
    SourceID,
    TraceID,
)
from skillgraph.storage import Storage

# Namespace estable para UUIDv5: cualquier texto puede ser, pero usamos
# un UUID fijo (no aleatorio por proceso) para que el mismo contenido
# siempre genere el mismo ID. Esto da idempotencia por contenido sin
# necesidad de UNIQUE adicionales en Storage.
NAMESPACE_KNOWLEDGE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def make_claim_id(
    *,
    subject_entity_id: EntityID,
    predicate: str,
    source_id: SourceID,
    checked_at_revision: str,
) -> ClaimID:
    """Genera un ClaimID determinista via UUIDv5 sobre la tupla natural."""
    seed = f"{subject_entity_id}|{predicate}|{source_id}|{checked_at_revision}"
    return ClaimID(f"claim-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")


def make_evidence_id(*, source_id: SourceID, content_repr: str) -> EvidenceID:
    """Genera un EvidenceID determinista via UUIDv5."""
    seed = f"{source_id}|{content_repr}"
    return EvidenceID(f"ev-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")


def make_finding_id(
    *,
    entity_id: EntityID,
    rule_ref: str,
    rule_version: str,
) -> FindingID:
    """Genera un FindingID determinista via UUIDv5."""
    seed = f"{entity_id}|{rule_ref}|{rule_version}"
    return FindingID(f"fnd-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")


@dataclass(frozen=True, slots=True)
class KnowledgeController:
    """API de alto nivel para Source/Entity/Claim/Evidence/Finding/OutcomeTrace.

    Recibe `storage`, `tenant_id`, `project_id` por inyeccion. Esto permite:
    - Mockear Storage en tests sin SQLite.
    - Reutilizar el mismo controller con distintos `(tenant, project)`.
    - Testeo determinista con fixtures inyectados.
    """

    storage: Storage
    tenant_id: str
    project_id: str

    # ----- Sources -----

    def register_source(self, *, source: Source) -> SourceID:
        """Registra una Source. Emite `StaleKnowledgeWarning` si la source
        ya existe con `freshness != 'fresh'` (re-registro de source stale)."""
        existing = self.storage.get_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=source.source_id,
        )
        if existing is not None and existing.freshness != "fresh":
            warnings.warn(
                f"re-registrando source stale: {source.source_id!r}",
                StaleKnowledgeWarning,
                stacklevel=2,
            )
        self.storage.register_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source=source,
        )
        return source.source_id

    def get_source(self, *, source_id: SourceID) -> Source:
        """Recupera una Source. `UnknownSourceError` si no existe."""
        result = self.storage.get_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=source_id,
        )
        if result is None:
            raise UnknownSourceError(f"Source no encontrada: {source_id!r}")
        return result

    def mark_source_stale(self, *, source_id: SourceID) -> None:
        """Marca una Source como stale. Lanza UnknownSourceError si no existe."""
        existing = self.get_source(source_id=source_id)
        self.storage.update_source_freshness(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=existing.source_id,
            freshness="stale",
        )

    def mark_source_fresh(self, *, source_id: SourceID) -> None:
        """Marca una Source como fresh."""
        existing = self.get_source(source_id=source_id)
        self.storage.update_source_freshness(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=existing.source_id,
            freshness="fresh",
        )

    # ----- Entities -----

    def upsert_entity(self, *, entity: Entity) -> EntityID:
        """Inserta o reemplaza una Entity. Devuelve su entity_id."""
        self.storage.upsert_entity(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            entity=entity,
        )
        return entity.entity_id

    def get_entity(self, *, entity_id: EntityID) -> Entity:
        """Recupera una Entity. UnknownEntityError si no existe."""
        result = self.storage.get_entity(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            entity_id=entity_id,
        )
        if result is None:
            raise UnknownEntityError(f"Entity no encontrada: {entity_id!r}")
        return result

    def find_entity(self, *, kind: str, stable_key: str) -> Entity | None:
        """Busca una Entity por (kind, stable_key). None si no existe.

        Implementacion: query directa sobre `entities` (UNIQUE(kind,
        stable_key) por tenant/project garantiza unicidad).
        """

        row = self.storage._conn.execute(
            """
            SELECT * FROM entities
            WHERE tenant_id = ? AND project_id = ?
              AND kind = ? AND stable_key = ?
            """,
            (self.tenant_id, self.project_id, kind, stable_key),
        ).fetchone()
        if row is None:
            return None
        return Entity(
            entity_id=row["entity_id"],
            kind=row["kind"],
            stable_key=row["stable_key"],
        )

    # ----- Evidences -----

    def record_evidence(self, *, evidence: Evidence) -> EvidenceID:
        """Registra una Evidence. Convierte FK violation en UnknownSourceError."""
        try:
            self.storage.record_evidence(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                evidence=evidence,
            )
        except Exception as exc:
            msg = str(exc)
            if "FOREIGN KEY" in msg:
                raise UnknownSourceError(f"Source no existe: {evidence.source_id!r}") from exc
            raise
        return evidence.evidence_id

    def get_evidences_for_claim(self, *, claim_id: ClaimID) -> tuple[Evidence, ...]:
        """Devuelve las Evidences asociadas a un Claim."""
        return self.storage.get_evidences_for_claim(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            claim_id=claim_id,
        )

    # ----- Claims -----

    def record_claim(self, *, claim: Claim) -> ClaimID:
        """Registra un Claim. Convierte FK violation en UnknownEntityError.

        Si el ADT tiene `claim_id=""` (vacio), genera uno determinista
        via UUIDv5 sobre (subject, predicate, source, revision).
        """
        # Si el caller paso claim_id vacio, generamos uno.
        claim_to_record = claim
        if not claim.claim_id:
            generated = make_claim_id(
                subject_entity_id=claim.subject_entity_id,
                predicate=claim.predicate,
                source_id=claim.source_id,
                checked_at_revision=claim.checked_at_revision,
            )
            claim_to_record = Claim(
                claim_id=generated,
                subject_entity_id=claim.subject_entity_id,
                predicate=claim.predicate,
                object_literal=claim.object_literal,
                source_id=claim.source_id,
                evidence_ids=claim.evidence_ids,
                extraction_method=claim.extraction_method,
                extractor_version=claim.extractor_version,
                checked_at_revision=claim.checked_at_revision,
                stale=claim.stale,
            )
        try:
            self.storage.record_claim(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                claim=claim_to_record,
            )
        except Exception as exc:
            # SQLite emite "FOREIGN KEY constraint failed" sin nombrar la tabla.
            # Distinguimos por el orden de chequeo: SQLite evalua FKs por orden
            # de insercion, asi que si subject_entity_id no existe, falla antes
            # que source_id. Hacemos lookup para saber cual.
            msg = str(exc)
            if "FOREIGN KEY" in msg:
                if (
                    self.storage.get_entity(
                        tenant_id=self.tenant_id,
                        project_id=self.project_id,
                        entity_id=claim.subject_entity_id,
                    )
                    is None
                ):
                    raise UnknownEntityError(
                        f"Entity no existe: {claim.subject_entity_id!r}"
                    ) from exc
                raise UnknownSourceError(f"Source no existe: {claim.source_id!r}") from exc
            raise
        return claim_to_record.claim_id

    def get_claim(self, *, claim_id: ClaimID) -> Claim:
        """Recupera un Claim. UnknownClaimError si no existe."""
        result = self.storage.get_claim(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            claim_id=claim_id,
        )
        if result is None:
            raise UnknownClaimError(f"Claim no encontrado: {claim_id!r}")
        return result

    def list_claims_for_source(self, *, source_id: SourceID) -> list[Claim]:
        """Lista Claims asociados a una Source."""
        return self.storage.list_claims_for_source(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            source_id=source_id,
        )

    def list_claims_for_subject(self, *, subject_entity_id: EntityID) -> list[Claim]:
        """Lista Claims cuyo subject_entity_id coincide."""
        import json

        rows = self.storage._conn.execute(
            """
            SELECT * FROM claims
            WHERE tenant_id = ? AND project_id = ? AND subject_entity_id = ?
            ORDER BY checked_at_revision DESC
            """,
            (self.tenant_id, self.project_id, subject_entity_id),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            ev_rows = self.storage._conn.execute(
                "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
                (row["claim_id"],),
            ).fetchall()
            out.append(
                Claim(
                    claim_id=row["claim_id"],
                    subject_entity_id=row["subject_entity_id"],
                    predicate=row["predicate"],
                    object_literal=json.loads(row["object_literal_json"]),
                    source_id=row["source_id"],
                    evidence_ids=tuple(r["evidence_id"] for r in ev_rows),
                    extraction_method=row["extraction_method"],
                    extractor_version=row["extractor_version"],
                    checked_at_revision=row["checked_at_revision"],
                    stale=bool(row["stale"]),
                )
            )
        return out

    # ----- Findings -----

    def record_finding(self, *, finding: Finding) -> FindingID:
        """Registra un Finding. Si `finding_id=""`, genera uno via UUIDv5."""
        f = finding
        if not finding.finding_id:
            generated = make_finding_id(
                entity_id=finding.entity_id,
                rule_ref=finding.rule_ref,
                rule_version=finding.rule_version,
            )
            f = Finding(
                finding_id=generated,
                entity_id=finding.entity_id,
                observation=finding.observation,
                rule_ref=finding.rule_ref,
                rule_version=finding.rule_version,
                evidence_ids=finding.evidence_ids,
                result=finding.result,
                valid_until_revision=finding.valid_until_revision,
            )
        self.storage.record_finding(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            finding=f,
        )
        return f.finding_id

    # ----- Outcome traces -----

    def record_trace(self, *, trace: OutcomeTrace) -> TraceID:
        """Registra un OutcomeTrace y sus enlaces preservando orden."""
        self.storage.record_trace(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            trace=trace,
        )
        return trace.trace_id

    def link_trace(
        self,
        *,
        trace_id: TraceID,
        link_kind: str,
        link_id: str,
        position: int,
    ) -> None:
        """Adjunta un enlace adicional a un trace."""
        self.storage.link_trace(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            trace_id=trace_id,
            link_kind=link_kind,
            link_id=link_id,
            position=position,
        )

    # ----- Invalidation (delegates to knowledge_invalidator) -----
    # Import lazy aqui para evitar ciclos y para que el invalidator se
    # pueda importar standalone en tests.

    def invalidate_from_source(
        self,
        *,
        source_id: SourceID,
        max_hops: int = 2,
    ) -> list[ClaimID]:
        """Marca stale las Claims que dependen del source (transitivo).

        Wrapper de `knowledge_invalidator.invalidate_from_source`.
        """
        from skillgraph.knowledge_invalidator import invalidate_from_source as _inv

        return _inv(
            self,
            source_id=source_id,
            max_hops=max_hops,
        )

    def refresh_source(
        self,
        *,
        source_id: SourceID,
        new_revision: str,
    ) -> list[ClaimID]:
        """Re-valida Claims contra nueva revision (las reactiva)."""
        from skillgraph.knowledge_invalidator import refresh_source as _ref

        return _ref(
            self,
            source_id=source_id,
            new_revision=new_revision,
        )

    def list_stale_claims(self) -> list[Claim]:
        """Lista todas las Claims stale del proyecto actual."""
        from skillgraph.knowledge_invalidator import list_stale_claims as _ls

        return list(_ls(self))


__all__ = [
    "NAMESPACE_KNOWLEDGE",
    "KnowledgeController",
    "NotFoundError",  # re-export para tests
    "make_claim_id",
    "make_evidence_id",
    "make_finding_id",
]
