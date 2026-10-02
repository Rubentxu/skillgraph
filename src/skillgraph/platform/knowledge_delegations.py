"""Mixin de delegaciones de `Storage` hacia el componente knowledge delegation.

WI-68. Desdoblamiento de `storage_delegations.py` (915 LoC) en un
modulo por componente, mismo criterio que ADR-0022 fase 1 (los
cinco mixin convivian en un solo fichero) y que ADR-0024 para
`RunController`.

Por que: el audit marca >800 LoC por fichero, y este lo supera
por CONCENTRACION DE CLASES, no de responsabilidad. Ninguna
clase pasa de 366 LoC y ningun metodo de 27: el problema era
que cinco razones de cambio distintas comparten fichero.

Cuerpos verbatim. `Storage` los hereda igual; solo cambia donde
viven. Red: `tests/test_wi68_storage_delegations_split.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)
from skillgraph.resources.bricks import Brick

if TYPE_CHECKING:
    from skillgraph.platform.ports import (
        StoredClaim,
        StoredEvidence,
        StoredRelation,
        StoredResource,
    )


class KnowledgeDelegations:
    """Reenvia al componente ``knowledge_repository()`` (SqliteKnowledgeRepository).

    31 metodos, 329 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

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
