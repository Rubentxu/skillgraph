"""Tests focalizados de las validaciones de ContextRecipe y ObligatorySelector.

Cubre las 13 missing lines + 13 branches parciales que pytest-cov
reporta como uncovered en `src/skillgraph/recipe.py`:

- ObligatorySelector.__post_init__: kind invalido (no en Literal),
  value vacio.
- ContextRecipe.__post_init__: recipe_ref vacio, freshness_policy
  invalido, token_budget <= 0, overflow_strategy invalido,
  revision < 1.
- ContextRecipe.from_dict: raw no-dict, obligatory/optional no-list,
  selector no-dict, kind/value/label no-str, relation_selectors
  no-list-of-str.

NO duplica lo que ya cubren tests/test_context_controller.py
(construccion y uso de ContextRecipe en handoff compilation).

Ver specs/h4-slice-3.md (stewardship de cobertura).
"""

from __future__ import annotations

import pytest

from skillgraph import ValidationError
from skillgraph.recipe import ContextRecipe, ObligatorySelector

# ---------------------------------------------------------------------------
# T1: ObligatorySelector.__post_init__ validation
# ---------------------------------------------------------------------------


def test_obligatory_selector_rejects_unknown_kind() -> None:
    """`kind` debe ser 'entity', 'predicate', o 'source'."""
    with pytest.raises(ValidationError, match=r"selector.kind invalido"):
        ObligatorySelector(kind="unknown", value="x")


def test_obligatory_selector_rejects_empty_value() -> None:
    """`value` no puede ser string vacio."""
    with pytest.raises(ValidationError, match=r"selector.value vacio"):
        ObligatorySelector(kind="entity", value="")


def test_obligatory_selector_accepts_valid_label_default() -> None:
    """label es opcional (default ''), se acepta sin pasarlo."""
    s = ObligatorySelector(kind="predicate", value="references")
    assert s.label == ""


# ---------------------------------------------------------------------------
# T2: ContextRecipe.__post_init__ validation
# ---------------------------------------------------------------------------


def test_context_recipe_rejects_empty_recipe_ref() -> None:
    """recipe_ref no puede ser vacio."""
    with pytest.raises(ValidationError, match="recipe_ref vacio"):
        ContextRecipe(recipe_ref="")


def test_context_recipe_rejects_invalid_freshness_policy() -> None:
    """freshness_policy fuera de Literal['strict','best_effort']."""
    with pytest.raises(ValidationError, match="freshness_policy invalida"):
        ContextRecipe(recipe_ref="r", freshness_policy="maybe")  # type: ignore[arg-type]


def test_context_recipe_rejects_non_positive_token_budget() -> None:
    """token_budget debe ser positivo."""
    with pytest.raises(ValidationError, match="token_budget debe ser positivo"):
        ContextRecipe(recipe_ref="r", token_budget=0)


def test_context_recipe_rejects_negative_token_budget() -> None:
    """token_budget negativo tambien es invalido."""
    with pytest.raises(ValidationError, match="token_budget debe ser positivo"):
        ContextRecipe(recipe_ref="r", token_budget=-1)


def test_context_recipe_rejects_invalid_overflow_strategy() -> None:
    """overflow_strategy fuera de Literal['drop_optional','fail','truncate_finding']."""
    with pytest.raises(ValidationError, match="overflow_strategy invalido"):
        ContextRecipe(recipe_ref="r", overflow_strategy="random")  # type: ignore[arg-type]


def test_context_recipe_rejects_revision_less_than_one() -> None:
    """revision debe ser >= 1."""
    with pytest.raises(ValidationError, match="revision invalida"):
        ContextRecipe(recipe_ref="r", revision=0)


def test_context_recipe_accepts_defaults() -> None:
    """Defaults razonables se aceptan sin especificar campos opcionales."""
    r = ContextRecipe(recipe_ref="ns.recipe")
    assert r.freshness_policy == "best_effort"
    assert r.token_budget == 8000
    assert r.overflow_strategy == "drop_optional"
    assert r.revision == 1


# ---------------------------------------------------------------------------
# T3: ContextRecipe.from_dict validation
# ---------------------------------------------------------------------------


def test_from_dict_rejects_non_dict_raw() -> None:
    """`raw` debe ser un dict."""
    with pytest.raises(ValidationError, match="recipe raw debe ser dict"):
        ContextRecipe.from_dict(recipe_ref="r", raw="not-a-dict")  # type: ignore[arg-type]


def test_from_dict_rejects_non_list_obligatory() -> None:
    """`obligatory` debe ser list."""
    with pytest.raises(ValidationError, match=r"recipe\.obligatory debe ser list"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"obligatory": "not-a-list"},
        )


def test_from_dict_rejects_non_list_optional() -> None:
    """`optional` debe ser list."""
    with pytest.raises(ValidationError, match=r"recipe\.optional debe ser list"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"optional": 42},
        )


def test_from_dict_rejects_non_dict_selector_item() -> None:
    """Cada item dentro de obligatory/optional debe ser dict."""
    with pytest.raises(ValidationError, match=r"recipe\.obligatory\[0\] debe ser dict"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"obligatory": ["not-a-dict"]},
        )


def test_from_dict_rejects_non_str_kind_in_selector() -> None:
    """selector.kind debe ser string."""
    with pytest.raises(ValidationError, match=r"recipe\.obligatory\[0\]\.kind debe ser str"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"obligatory": [{"kind": 42, "value": "x"}]},
        )


def test_from_dict_rejects_non_str_value_in_selector() -> None:
    """selector.value debe ser string."""
    with pytest.raises(ValidationError, match=r"recipe\.obligatory\[0\]\.value debe ser str"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"obligatory": [{"kind": "entity", "value": 42}]},
        )


def test_from_dict_rejects_non_str_label_in_selector() -> None:
    """selector.label debe ser string (si se pasa)."""
    with pytest.raises(ValidationError, match=r"recipe\.optional\[0\]\.label debe ser str"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={
                "obligatory": [],
                "optional": [{"kind": "source", "value": "x", "label": 99}],
            },
        )


def test_from_dict_rejects_non_list_relation_selectors() -> None:
    """relation_selectors debe ser list."""
    with pytest.raises(ValidationError, match=r"recipe.relation_selectors debe ser list"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"relation_selectors": "not-a-list"},
        )


def test_from_dict_rejects_non_str_items_in_relation_selectors() -> None:
    """Todos los items de relation_selectors deben ser str."""
    with pytest.raises(ValidationError, match=r"recipe.relation_selectors debe ser list"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"relation_selectors": ["valid", 42, "also-valid"]},
        )


# ---------------------------------------------------------------------------
# T4: from_dict happy path
# ---------------------------------------------------------------------------


def test_from_dict_loads_minimal_recipe_with_defaults() -> None:
    """Sin campos opcionales, defaults se aplican correctamente."""
    r = ContextRecipe.from_dict(recipe_ref="ns.basic", raw={})
    assert r.recipe_ref == "ns.basic"
    assert r.obligatory == ()
    assert r.optional == ()
    assert r.relation_selectors == ()
    assert r.freshness_policy == "best_effort"
    assert r.token_budget == 8000
    assert r.overflow_strategy == "drop_optional"
    assert r.revision == 1


def test_from_dict_loads_full_recipe_with_all_fields() -> None:
    """Todos los campos del dict se parsean correctamente."""
    raw = {
        "obligatory": [
            {"kind": "entity", "value": "ent-1", "label": "primary"},
            {"kind": "predicate", "value": "references"},
        ],
        "optional": [
            {"kind": "source", "value": "src-1"},
        ],
        "relation_selectors": ["rel-a", "rel-b"],
        "freshness_policy": "strict",
        "token_budget": 4000,
        "overflow_strategy": "fail",
        "revision": 3,
    }
    r = ContextRecipe.from_dict(recipe_ref="ns.full", raw=raw)
    assert len(r.obligatory) == 2
    assert r.obligatory[0].label == "primary"
    assert len(r.optional) == 1
    assert r.relation_selectors == ("rel-a", "rel-b")
    assert r.freshness_policy == "strict"
    assert r.token_budget == 4000
    assert r.overflow_strategy == "fail"
    assert r.revision == 3


def test_from_dict_validates_selector_kind_through_obligatory_selector() -> None:
    """Un selector con kind invalido se rechaza via ObligatorySelector.__post_init__."""
    with pytest.raises(ValidationError, match=r"selector.kind invalido"):
        ContextRecipe.from_dict(
            recipe_ref="r",
            raw={"obligatory": [{"kind": "invalid-kind", "value": "x"}]},
        )
