"""Tests que validan el cumplimiento de AGENTS.md §1.2 (errores tipados).

AGENTS §1.2 exige: "Toda validacion lanza ValidationError, ParseError,
IdentityConflictError, NotFoundError, IdempotencyError o una subclase
tipada de SkillGraphError. Prohibido raise ValueError(...) en codigo
de dominio."

Estos tests verifican que los __post_init__ de los dataclasses de
knowledge/ lanzan ValidationError (no ValueError) cuando los argumentos
son invalidos.

Origen: investigacion retrospectiva del ciclo STEWARDSHIP-DT-FILE-SCOPE-VALIDATION
descubrio que file_signature.py tenia 8 raises de ValueError, file_handoff.py
3 y git_source.py 1, todos en __post_init__ de dataclasses de dominio.

Workflow SDDK: ciclo de cumplimiento normativo (regla existente, no diseno).
"""

from __future__ import annotations

import re

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.file_handoff import ScopeAwareRecipe
from skillgraph.knowledge.file_signature import (
    FileSignature,
    SignatureProcedencia,
    SignatureVigencia,
)

# ----- SignatureProcedencia -----------------------------------------------


class TestSignatureProcedenciaValidationErrors:
    """file_signature.py line 49-53."""

    def test_empty_extraction_method_raises_validation_error(self) -> None:
        with pytest.raises(
            ValidationError,
            match=re.escape("extraction_method no puede estar vacio"),
        ):
            SignatureProcedencia(extraction_method="", extractor_version="v1")

    def test_empty_extractor_version_raises_validation_error(self) -> None:
        with pytest.raises(
            ValidationError,
            match=re.escape("extractor_version no puede estar vacia"),
        ):
            SignatureProcedencia(extraction_method="regex_def", extractor_version="")


# ----- SignatureVigencia --------------------------------------------------


class TestSignatureVigenciaValidationErrors:
    """file_signature.py line 71-86."""

    def test_invalid_state_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="state invalido"):
            SignatureVigencia(state="nonsense", fresh=False, stale=True)  # type: ignore[arg-type]

    def test_inconsistent_fresh_raises_validation_error(self) -> None:
        # state=complete pero fresh=False: incoherente
        with pytest.raises(ValidationError, match="inconsistente con state"):
            SignatureVigencia(state="complete", fresh=False, stale=False)

    def test_inconsistent_stale_raises_validation_error(self) -> None:
        # state=complete pero stale=True: incoherente
        with pytest.raises(ValidationError, match="inconsistente con state"):
            SignatureVigencia(state="complete", fresh=True, stale=True)


# ----- FileSignature ------------------------------------------------------


class TestFileSignatureValidationErrors:
    """file_signature.py line 113-119."""

    def test_empty_foco_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match=re.escape("foco no puede estar vacio")):
            FileSignature(
                foco="",
                contrato="module",
                cobertura=10,
                procedencia=_valid_procedencia(),
                vigencia=_valid_vigencia(),
            )

    def test_empty_contrato_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match=re.escape("contrato no puede estar vacio")):
            FileSignature(
                foco="Foo",
                contrato="",
                cobertura=10,
                procedencia=_valid_procedencia(),
                vigencia=_valid_vigencia(),
            )

    def test_negative_cobertura_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match=re.escape("cobertura debe ser >= 0")):
            FileSignature(
                foco="Foo",
                contrato="module",
                cobertura=-1,
                procedencia=_valid_procedencia(),
                vigencia=_valid_vigencia(),
            )


# ----- file_handoff.py: ScopeAwareRecipe ----------------------------------


class TestScopeAwareRecipeValidationErrors:
    """file_handoff.py line 105-111."""

    def test_empty_recipe_ref_via_base_raises_validation_error(self) -> None:
        # Para llegar al __post_init__ de ScopeAwareRecipe con recipe_ref vacio,
        # hay que saltar la validacion de ContextRecipe. Usamos object.__setattr__
        # (ContextRecipe es frozen=True, slots=True: truco con _bypass_).
        base = ContextRecipe(recipe_ref="src/recipe.md")
        # Truco: forzar recipe_ref='' saltando la validacion de ContextRecipe.
        # Esto NO es uso normal pero sirve para testear la validacion de
        # ScopeAwareRecipe de forma aislada.
        object.__setattr__(base, "recipe_ref", "")
        with pytest.raises(
            ValidationError,
            match=re.escape("base_recipe.recipe_ref vacio"),
        ):
            ScopeAwareRecipe(
                base_recipe=base,
                scope_queries=("dummy",),
                member_source_ids=("src/a.py",),
            )

    def test_empty_scope_queries_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match=re.escape("scope_queries vacio")):
            ScopeAwareRecipe(
                base_recipe=ContextRecipe(recipe_ref="src/recipe.md"),
                scope_queries=(),
                member_source_ids=("src/a.py",),
            )

    def test_empty_member_source_ids_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match=re.escape("member_source_ids vacio")):
            ScopeAwareRecipe(
                base_recipe=ContextRecipe(recipe_ref="src/recipe.md"),
                scope_queries=("dummy",),
                member_source_ids=(),
            )


# ----- git_source.py ------------------------------------------------------


class TestGitSourceValidationErrors:
    """git_source.py line 140."""

    def test_from_commit_non_commit_sha_raises_validation_error(self) -> None:
        # Necesita un repo git con un Blob (no commit) en el object store
        import tempfile
        from pathlib import Path

        from dulwich.objects import Blob
        from dulwich.repo import Repo

        from skillgraph.knowledge.git_source import GitSource

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            root.mkdir()
            repo = Repo.init(str(root))
            blob = Blob.from_string(b"not a commit")
            repo.object_store.add_object(blob)
            with pytest.raises(ValidationError, match="no apunta a un commit"):
                GitSource.from_commit(repo_root=root, commit_sha=blob.id.decode("ascii"))


# ----- helpers ------------------------------------------------------------


def _valid_procedencia() -> SignatureProcedencia:
    return SignatureProcedencia(extraction_method="regex_def", extractor_version="v1")


def _valid_vigencia() -> SignatureVigencia:
    return SignatureVigencia(state="complete", fresh=True, stale=False)
