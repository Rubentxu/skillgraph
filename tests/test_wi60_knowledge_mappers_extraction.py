"""Red de contrato WI-60 fase 1: mappers de fila a `knowledge_mappers`.

Primera fase de ADR-0020: los 7 mappers puros fila->DTO salen a
`platform.knowledge_mappers` y `knowledge_repository` conserva
re-imports, de modo que los shims de `storage.py` (import diferido del
corte 5 de ADR-0016) y los metodos de la clase no se editan.
"""

from __future__ import annotations

import skillgraph.platform.knowledge_mappers as mappers
from skillgraph.platform import knowledge_repository


class TestMappersIdentity:
    """`knowledge_repository.row_to_X` DEBE ser el mapper real de
    `knowledge_mappers` (los shims de storage.py dependen de ese
    simbolo exportado)."""

    def test_row_to_source_identity(self) -> None:
        assert knowledge_repository.row_to_source is mappers.row_to_source

    def test_row_to_evidence_identity(self) -> None:
        assert knowledge_repository.row_to_evidence is mappers.row_to_evidence

    def test_row_to_stored_claim_identity(self) -> None:
        assert knowledge_repository.row_to_stored_claim is mappers.row_to_stored_claim

    def test_row_to_stored_evidence_identity(self) -> None:
        assert knowledge_repository.row_to_stored_evidence is mappers.row_to_stored_evidence

    def test_row_to_claim_identity(self) -> None:
        assert knowledge_repository.row_to_claim is mappers.row_to_claim

    def test_row_to_resource_identity(self) -> None:
        assert knowledge_repository.row_to_resource is mappers.row_to_resource

    def test_row_to_relation_identity(self) -> None:
        assert knowledge_repository.row_to_relation is mappers.row_to_relation


class TestRepositoryUntouched:
    """La clase no se movio en fase 1 y runner de duplicados, nada."""

    def test_repo_class_stays_in_knowledge_repository(self) -> None:
        assert (
            knowledge_repository.SqliteKnowledgeRepository.__module__
            == "skillgraph.platform.knowledge_repository"
        )

    def test_knowledge_repository_does_not_redefine_mappers(self) -> None:
        import inspect

        source = inspect.getsource(knowledge_repository)
        assert "def row_to_source" not in source
        assert "def row_to_relation" not in source

    # WI-81: este fichero tenia tambien
    # `test_storage_shim_import_keeps_working`, que afirmaba que el shim
    # `storage._row_to_source` resolvia contra `knowledge_repository`.
    # Ese shim era uno de los 7 alias de WI-56 sin callers, asi que se
    # elimino con el resto. El invariante que queda vivo no es "el shim
    # funciona" sino "nadie lo usa": lo vigila
    # `tests/test_wi81_dead_aliases.py`.
