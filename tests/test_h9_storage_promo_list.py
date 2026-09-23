"""H9 slice B: API publica Storage.list_promotions(status=None).

Cierra la limitacion declarada en CHANGELOG (post-H8) segun la cual
`sg promotion list` realizaba SQL directo sobre `storage._conn`. Este
test cubre la API Storage de bajo nivel; el adaptador CLI tiene su
cobertura en test_h8_public_paths.py (subprocess) y en los tests
in-process del runner cuando se anadan.

Convenciones: mismo patron que test_h7_promocion.py (fixture `storage`
en tmp_path, db SQLite autocerrado). Sin mocks; storage real.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.platform.storage import PROMOTION_STATUSES, Storage


@pytest.fixture
def storage(tmp_path):
    db = Storage(tmp_path / "test.db")
    yield db
    db.close()


def _reg(
    storage: Storage,
    *,
    pid: str,
    key: str,
    claim: str,
) -> None:
    storage.register_promotion(
        proposal_id=pid,
        idempotency_key=key,
        tenant_id="t1",
        source_project="src",
        target_catalog="tgt",
        knowledge_ref=claim,
        payload={"claim": claim},
    )


class TestListPromotionsEmpty:
    def test_empty_outbox_returns_empty_list(self, storage: Storage) -> None:
        """Outbox recien creado: list_promotions() sin filtro => []."""
        assert storage.list_promotions() == []

    def test_empty_outbox_with_status_filter_returns_empty(self, storage: Storage) -> None:
        """Filtro de status sobre outbox vacio => [] (no error)."""
        assert storage.list_promotions(status="PENDING") == []
        assert storage.list_promotions(status="PUBLISHED") == []
        assert storage.list_promotions(status="FAILED") == []
        assert storage.list_promotions(status="IN_PROGRESS") == []


class TestListPromotionsNoFilter:
    def test_returns_all_proposals_in_created_at_asc(self, storage: Storage) -> None:
        """Sin filtro devuelve TODAS las propuestas, orden created_at ASC."""
        _reg(storage, pid="p1", key="k1", claim="c1")
        _reg(storage, pid="p2", key="k2", claim="c2")
        _reg(storage, pid="p3", key="k3", claim="c3")
        rows = storage.list_promotions()
        assert [r["proposal_id"] for r in rows] == ["p1", "p2", "p3"]

    def test_payload_is_deserialized(self, storage: Storage) -> None:
        """El campo `payload` viene como dict (no str JSON)."""
        _reg(storage, pid="p1", key="k1", claim="c1")
        rows = storage.list_promotions()
        assert rows[0]["payload"] == {"claim": "c1"}
        assert isinstance(rows[0]["payload"], dict)


class TestListPromotionsByStatus:
    def test_filter_published(self, storage: Storage) -> None:
        _reg(storage, pid="p1", key="k1", claim="c1")
        _reg(storage, pid="p2", key="k2", claim="c2")
        storage.mark_promotion_in_progress("p1")
        storage.mark_promotion_published("p1")
        rows = storage.list_promotions(status="PUBLISHED")
        assert [r["proposal_id"] for r in rows] == ["p1"]

    def test_filter_pending_excludes_in_progress(self, storage: Storage) -> None:
        """list_promotions(status='PENDING') es estricto: NO incluye IN_PROGRESS.

        Diferencia con list_pending_promotions(), que SI los incluye (compat).
        """
        _reg(storage, pid="p1", key="k1", claim="c1")
        _reg(storage, pid="p2", key="k2", claim="c2")
        storage.mark_promotion_in_progress("p2")  # p2 pasa a IN_PROGRESS
        rows_pending = storage.list_promotions(status="PENDING")
        assert [r["proposal_id"] for r in rows_pending] == ["p1"]
        rows_inprog = storage.list_promotions(status="IN_PROGRESS")
        assert [r["proposal_id"] for r in rows_inprog] == ["p2"]

    def test_filter_failed(self, storage: Storage) -> None:
        _reg(storage, pid="p1", key="k1", claim="c1")
        storage.mark_promotion_failed("p1")
        rows = storage.list_promotions(status="FAILED")
        assert len(rows) == 1
        assert rows[0]["proposal_id"] == "p1"


class TestListPromotionsValidation:
    def test_invalid_status_raises_validation_error(self, storage: Storage) -> None:
        with pytest.raises(ValidationError) as exc_info:
            storage.list_promotions(status="XYZ")
        # Mensaje incluye la lista valida para diagnostic claro.
        assert "XYZ" in str(exc_info.value)
        assert "PENDING" in str(exc_info.value)

    def test_valid_statuses_constant_matches_schema(self) -> None:
        """PROMOTION_STATUSES cubre exactamente el CHECK constraint del schema."""
        assert frozenset({"PENDING", "IN_PROGRESS", "PUBLISHED", "FAILED"}) == PROMOTION_STATUSES


class TestListPendingPromotionsCompat:
    """list_pending_promotions() debe seguir funcionando y devolver PENDING + IN_PROGRESS."""

    def test_includes_pending_and_in_progress(self, storage: Storage) -> None:
        _reg(storage, pid="p1", key="k1", claim="c1")
        _reg(storage, pid="p2", key="k2", claim="c2")
        _reg(storage, pid="p3", key="k3", claim="c3")
        storage.mark_promotion_in_progress("p2")  # IN_PROGRESS
        storage.mark_promotion_in_progress("p3")
        storage.mark_promotion_published("p3")  # PUBLISHED
        rows = storage.list_pending_promotions()
        # p1 PENDING y p2 IN_PROGRESS; p3 ya no.
        ids = {r["proposal_id"] for r in rows}
        assert ids == {"p1", "p2"}
