"""Red de contrato WI-61 fase 2 (ADR-0020): cluster CLAIMS como componente real.

Los 9 metodos de claims salen de `SqliteKnowledgeRepository` a
`SqliteClaimRepository` (platform/knowledge_claims.py), componente con
conexion compartida via `_storage`. La fachada conserva las firmas y
delega: los metodos de fachada DEJAN de definir el cuerpo (delegacion,
no copia), y los shims de storage.py siguen resolviendo.
"""

from __future__ import annotations

import inspect

import skillgraph.platform.knowledge_claims as claims_mod
from skillgraph.platform import knowledge_repository
from skillgraph.platform.knowledge_claims import SqliteClaimRepository
from skillgraph.platform.knowledge_mappers import row_to_claim, row_to_stored_claim
from skillgraph.platform.storage import Storage


class TestClaimsComponentIdentity:
    """El componente es real y usa los mappers de knowledge_mappers."""

    def test_component_lives_in_knowledge_claims(self) -> None:
        assert SqliteClaimRepository.__module__ == "skillgraph.platform.knowledge_claims"

    def test_component_uses_canonical_mappers(self) -> None:
        source = inspect.getsource(claims_mod)
        assert "row_to_claim" in source
        assert "row_to_stored_claim" in source


CLAIM_METHODS = (
    "record_claim",
    "get_claim",
    "list_claims_for_subject",
    "list_claims_for_source",
    "list_claims_using_evidence",
    "mark_claims_stale",
    "reactivate_claims_with_revision",
    "list_stale_claims",
    "list_claims_by_predicate",
)


class TestFacadeDelegates:
    """La fachada conserva las firmas y delega (cuerpo minimo, sin SQL)."""

    def test_all_claim_methods_exist_in_facade(self) -> None:
        for name in CLAIM_METHODS:
            assert hasattr(knowledge_repository.SqliteKnowledgeRepository, name), name

    def test_facade_signatures_match_component(self) -> None:
        for name in CLAIM_METHODS:
            facade = inspect.signature(
                getattr(knowledge_repository.SqliteKnowledgeRepository, name)
            )
            component = inspect.signature(getattr(SqliteClaimRepository, name))
            assert str(facade) == str(component), name

    def test_facade_bodies_do_not_contain_sql(self) -> None:
        """Delegacion, no copia: los cuerpos de fachada no llevan SQL."""
        for name in CLAIM_METHODS:
            fn = getattr(knowledge_repository.SqliteKnowledgeRepository, name)
            source = inspect.getsource(fn)
            assert "SELECT" not in source and "INSERT" not in source, name


class TestBehavioralWiring:
    """La delegacion funciona de verdad (no solo en la firma)."""

    def test_get_claim_via_facade_reaches_component(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        storage = Storage(str(tmp_path / "k.sqlite"))
        repo = knowledge_repository.SqliteKnowledgeRepository(storage)
        component = SqliteClaimRepository(storage)
        # El componente y la fachada comparten el mismo storage subyacente.
        assert repo._storage is storage
        assert component._storage is storage
        # Sin claims, ambos caminos devuelven lo mismo (None en get_claim);
        # la firma es keyword-only (marcador *), como el original.
        assert repo.get_claim(
            tenant_id="t", project_id="p", claim_id="nope"
        ) == component.get_claim(tenant_id="t", project_id="p", claim_id="nope")

    def test_mappers_are_the_canonical_ones(self) -> None:
        """El modulo importa los mappers como alias privados (contrato de
        los cuerpos movidos)."""
        assert claims_mod._row_to_claim is row_to_claim
        assert claims_mod._row_to_stored_claim is row_to_stored_claim
