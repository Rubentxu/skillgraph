"""Tests H7 promocion entre bases (UAT-13): reconciliacion idempotente
tras interrupcion.

Criterio verificable (UAT-13):
"Dada una propuesta de promocion persistida en un proyecto, cuando se
interrumpe el proceso durante su publicacion, entonces la reconciliacion
permite completarla sin duplicar la capacidad compartida."

El test demuestra:
1. Submit crea propuesta en outbox con status PENDING.
2. Apply exitoso transiciona a PUBLISHED.
3. Apply fallido transiciona a FAILED.
4. Apply duplicado (segundo intento sobre PUBLISHED) es idempotente:
   NO se vuelve a aplicar apply_fn (counter no incrementa).
5. Submit duplicado (mismo idempotency_key) lanza IdentityConflictError.
6. Reconciliacion tras interrupcion completa propuestas PENDING.
7. Reconciliacion completa propuestas IN_PROGRESS dejadas por crash.
"""

from __future__ import annotations

import pytest

from skillgraph.errors import IdentityConflictError, ValidationError
from skillgraph.promotion import (
    _compute_idempotency_key,
    apply_proposal,
    reconcile_pending,
    submit_proposal,
)
from skillgraph.storage import Storage


@pytest.fixture
def storage(tmp_path):
    """Storage SQLite temporal, autocerrado al final del test."""
    db = Storage(tmp_path / "test.db")
    yield db
    db.close()


class TestPromotionIdempotencyKey:
    def test_compute_idempotency_key_combines_project_and_ref(self) -> None:
        """La key es estable: misma (project, ref) -> misma key."""
        k1 = _compute_idempotency_key("proj-a", "claim-123")
        k2 = _compute_idempotency_key("proj-a", "claim-123")
        assert k1 == k2
        assert "proj-a" in k1
        assert "claim-123" in k1

    def test_compute_idempotency_key_different_inputs(self) -> None:
        """Keys distintas para inputs distintos."""
        assert _compute_idempotency_key("proj-a", "x") != _compute_idempotency_key("proj-b", "x")
        assert _compute_idempotency_key("proj-a", "x") != _compute_idempotency_key("proj-a", "y")

    def test_compute_idempotency_key_rejects_empty(self) -> None:
        """Campos vacios lanzan ValidationError."""
        with pytest.raises(ValidationError):
            _compute_idempotency_key("", "x")
        with pytest.raises(ValidationError):
            _compute_idempotency_key("p", "")


class TestSubmitProposal:
    def test_submit_creates_pending_proposal(self, storage: Storage) -> None:
        """Submit inserta propuesta con status=PENDING."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={"claim": "data"},
        )
        p = storage.get_promotion("prop-1")
        assert p is not None
        assert p["status"] == "PENDING"
        assert p["source_project"] == "proj-a"
        assert p["knowledge_ref"] == "claim-100"
        assert p["payload"] == {"claim": "data"}

    def test_submit_duplicate_raises_conflict(self, storage: Storage) -> None:
        """Mismo idempotency_key no se puede insertar dos veces."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={},
        )
        with pytest.raises(IdentityConflictError, match="duplicada"):
            submit_proposal(
                storage,
                proposal_id="prop-2",
                tenant_id="t1",
                source_project="proj-a",
                target_catalog="catalog-shared",
                knowledge_ref="claim-100",  # mismo knowledge_ref
                payload={},
            )


class TestApplyProposal:
    def test_apply_successful_marks_published(self, storage: Storage) -> None:
        """Apply exitoso transiciona a PUBLISHED."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={"k": "v"},
        )
        applied_count = 0

        def apply_fn(payload):
            nonlocal applied_count
            applied_count += 1
            return True

        status = apply_proposal(storage, "prop-1", apply_fn=apply_fn)
        assert status == "PUBLISHED"
        assert applied_count == 1
        p = storage.get_promotion("prop-1")
        assert p["status"] == "PUBLISHED"
        assert p["published_at"] is not None

    def test_apply_failed_marks_failed(self, storage: Storage) -> None:
        """Apply que devuelve False transiciona a FAILED."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={},
        )

        def apply_fn(payload):
            return False

        status = apply_proposal(storage, "prop-1", apply_fn=apply_fn)
        assert status == "FAILED"
        assert storage.get_promotion("prop-1")["status"] == "FAILED"

    def test_apply_exception_marks_failed(self, storage: Storage) -> None:
        """Excepcion en apply_fn transiciona a FAILED."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={},
        )

        def apply_fn(payload):
            raise RuntimeError("catalog unreachable")

        status = apply_proposal(storage, "prop-1", apply_fn=apply_fn)
        assert status == "FAILED"

    def test_apply_already_published_is_idempotent(self, storage: Storage) -> None:
        """Segundo apply sobre PUBLISHED NO llama apply_fn (idempotencia)."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={},
        )
        applied_count = 0

        def apply_fn(payload):
            nonlocal applied_count
            applied_count += 1
            return True

        apply_proposal(storage, "prop-1", apply_fn=apply_fn)
        assert applied_count == 1

        # Segundo apply: debe ser idempotente, NO incrementar count.
        status = apply_proposal(storage, "prop-1", apply_fn=apply_fn)
        assert status == "PUBLISHED"
        assert applied_count == 1, (
            f"apply_fn fue llamado {applied_count} veces; deberia ser 1 por idempotencia"
        )

    def test_apply_failed_status_not_retried(self, storage: Storage) -> None:
        """Apply sobre FAILED no reintenta automaticamente."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={},
        )
        apply_proposal(storage, "prop-1", apply_fn=lambda p: False)
        assert storage.get_promotion("prop-1")["status"] == "FAILED"

        # Segundo intento: NO debe reintentar (status=FAILED corto-circuita).
        applied_count = 0

        def apply_fn(payload):
            nonlocal applied_count
            applied_count += 1
            return True

        status = apply_proposal(storage, "prop-1", apply_fn=apply_fn)
        assert status == "FAILED"
        assert applied_count == 0

    def test_apply_unknown_proposal_raises(self, storage: Storage) -> None:
        """Apply sobre proposal inexistente lanza ValidationError."""
        with pytest.raises(ValidationError, match="no existe"):
            apply_proposal(storage, "prop-missing", apply_fn=lambda p: True)


class TestReconcilePending:
    def test_reconcile_empty_returns_empty(self, storage: Storage) -> None:
        """Sin propuestas pendientes, reconciliacion devuelve lista vacia."""
        results = reconcile_pending(storage, apply_fn=lambda p: True)
        assert results == []

    def test_reconcile_processes_pending(self, storage: Storage) -> None:
        """Reconciliacion aplica todas las PENDING."""
        for i in range(3):
            submit_proposal(
                storage,
                proposal_id=f"prop-{i}",
                tenant_id="t1",
                source_project="proj-a",
                target_catalog="catalog-shared",
                knowledge_ref=f"claim-{i}",  # keys distintas
                payload={},
            )
        results = reconcile_pending(storage, apply_fn=lambda p: True)
        assert len(results) == 3
        assert all(r["status"] == "PUBLISHED" for r in results)

    def test_reconcile_after_interruption_completes_pending(self, storage: Storage) -> None:
        """CASO CRITICO UAT-13: tras interrupcion, reconciliacion completa
        sin duplicar.

        Simulacion:
        1. Submit prop-1 (PENDING).
        2. Worker A inicia apply: marca IN_PROGRESS pero se interrumpe
           antes de completar (no llega a mark_published).
        3. Reconciliacion: ve IN_PROGRESS, completa -> PUBLISHED.
        4. apply_fn es llamado UNA sola vez (idempotencia).
        """
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={"important": "data"},
        )

        # Simulacion de interrupcion: marcamos IN_PROGRESS manualmente
        # (como si el worker hubiera sido matado despues de este paso).
        assert storage.mark_promotion_in_progress("prop-1") is True
        assert storage.get_promotion("prop-1")["status"] == "IN_PROGRESS"

        # Reconciliacion: debe completar la transicion.
        applied_count = 0

        def apply_fn(payload):
            nonlocal applied_count
            applied_count += 1
            return True

        results = reconcile_pending(storage, apply_fn=apply_fn)
        assert len(results) == 1
        assert results[0]["status"] == "PUBLISHED"
        assert applied_count == 1, f"apply_fn fue llamado {applied_count} veces; deberia ser 1"

        # Estado final
        p = storage.get_promotion("prop-1")
        assert p["status"] == "PUBLISHED"
        assert p["published_at"] is not None

    def test_reconcile_does_not_duplicate_published(self, storage: Storage) -> None:
        """Propuestas ya PUBLISHED NO se vuelven a aplicar."""
        submit_proposal(
            storage,
            proposal_id="prop-1",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-100",
            payload={},
        )
        apply_proposal(storage, "prop-1", apply_fn=lambda p: True)
        # prop-1 ahora es PUBLISHED.

        # Anadimos otra PENDING para que reconciliacion tenga algo que hacer.
        submit_proposal(
            storage,
            proposal_id="prop-2",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-200",
            payload={},
        )

        applied_count = 0

        def apply_fn(payload):
            nonlocal applied_count
            applied_count += 1
            return True

        results = reconcile_pending(storage, apply_fn=apply_fn)
        # Solo prop-2 (PENDING) debe haber sido procesada.
        assert len(results) == 1
        assert results[0]["proposal_id"] == "prop-2"
        assert applied_count == 1

    def test_reconcile_mixed_status_handles_each_correctly(self, storage: Storage) -> None:
        """Mezcla de PENDING, IN_PROGRESS y FAILED se reconcilia correctamente."""
        # PENDING
        submit_proposal(
            storage,
            proposal_id="prop-pending",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-1",
            payload={},
        )
        # IN_PROGRESS (interrumpido)
        submit_proposal(
            storage,
            proposal_id="prop-inprog",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-2",
            payload={},
        )
        storage.mark_promotion_in_progress("prop-inprog")
        # FAILED (no se reintenta)
        submit_proposal(
            storage,
            proposal_id="prop-failed",
            tenant_id="t1",
            source_project="proj-a",
            target_catalog="catalog-shared",
            knowledge_ref="claim-3",
            payload={},
        )
        apply_proposal(storage, "prop-failed", apply_fn=lambda p: False)

        # Reconciliacion
        results = reconcile_pending(storage, apply_fn=lambda p: True)
        # Solo PENDING e IN_PROGRESS aparecen en la lista; FAILED ya estaba.
        prop_ids = {r["proposal_id"] for r in results}
        assert prop_ids == {"prop-pending", "prop-inprog"}
        statuses = {r["proposal_id"]: r["status"] for r in results}
        assert statuses["prop-pending"] == "PUBLISHED"
        assert statuses["prop-inprog"] == "PUBLISHED"

        # prop-failed sigue FAILED (no se reintento).
        assert storage.get_promotion("prop-failed")["status"] == "FAILED"
