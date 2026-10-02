"""Delegaciones del facade `Storage` por componente (WI-65, corte 1).

Extraccion estranguladora de los 65 metodos de `Storage` que solo
reenvian a un componente ya extraido en WI-56 (ADR-0016). El cuerpo de
cada metodo se mueve **verbatim**: no hay logica nueva, ni rama nueva,
ni ruta de error nueva. La unica diferencia es que ahora viven en un
mixin por componente y `Storage` los hereda.

Por que mixin y no `__getattr__` dinamico: `__getattr__` rompe el
tipado estatico que AGENTS.md 4.1 exige explicito, mientras que el
mixin conserva las anotaciones reales de cada metodo, mantiene
`Storage` como la misma clase con los mismos metodos publicos y
obliga a cero ediciones en los callers.

Invariante de estos mixin: delegan y nada mas. Ningun metodo toca
`self._conn`, `_tx()` ni `_atomic()`; el SQL vivo se queda en
`Storage`. Cada mixin reenvia a un unico accessor, lo que hace la
extraccion mecanica y la red `test_wi65_storage_facade_delegations`
puede exigirlo.

Medicion (AST, reproducible): 65 metodos, 759 LoC, 42% de los 1807
LoC de `storage.py`. Detalle: `evidence/wi65-storage-facade-exploration.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
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
        StoredBudget,
        StoredClaim,
        StoredEvent,
        StoredEvidence,
        StoredNodeExecution,
        StoredRelation,
        StoredResource,
        StoredRun,
    )
    from skillgraph.runtime.engine import RuntimeEvent


class RunDelegations:
    """Reenvia al componente ``run_repository()`` (SqliteRunRepository).

    19 metodos, 267 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

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


class PromotionDelegations:
    """Reenvia al componente ``promotion_repository()`` (SqlitePromotionRepository).

    7 metodos, 66 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

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


class EventStoreDelegations:
    """Reenvia al componente ``event_store()`` (SqliteEventStore).

    4 metodos, 52 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

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


class PolicyDelegations:
    """Reenvia al componente ``policy_store()`` (SqlitePolicyStore).

    4 metodos, 45 LoC movidos de `Storage`.
    Cuerpos verbatim: ver `storage.py` @ WI-65.
    """

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
