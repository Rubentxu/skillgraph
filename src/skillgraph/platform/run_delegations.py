"""Mixin de delegaciones de `Storage` hacia el componente run delegation.

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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skillgraph.platform.ports import (
        StoredEvent,
        StoredNodeExecution,
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
