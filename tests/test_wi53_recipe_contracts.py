"""Red de contrato para ContextRecipe.from_dict y ObligatorySelector.

`Recipe.from_dict` estaba al 100% de cobertura de lineas y con cc=11
era el tercer hotspot del ranking medido. La cobertura no fijaba
contrato: estos tests pinan que error gana cuando hay varios fallos,
los bordes de cada regla, y el comportamiento de coercion observado.

Dos trampas bool quedan aqui documentadas como ESTADO OBSERVADO antes
del fix: `token_budget=True` y `revision=True` se aceptan porque
`bool` es subclase de `int`. Es la misma clase de trampa que ya se
corrigio en `metadata.max_visits`.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.core.recipe import ContextRecipe, ObligatorySelector


def _load(raw: dict[str, object]) -> ContextRecipe:
    return ContextRecipe.from_dict(recipe_ref="r-1", raw=raw)


def _sel(kind: str = "entity", value: str = "v", label: str = "") -> dict[str, object]:
    return {"kind": kind, "value": value, "label": label}


# --------------------------------------------------------------------------
# ObligatorySelector (smart constructor)
# --------------------------------------------------------------------------


class TestObligatorySelector:
    def test_selector_valido(self) -> None:
        s = ObligatorySelector(kind="entity", value="e-1", label="L")
        assert s.kind == "entity"
        assert s.label == "L"

    @pytest.mark.parametrize("kind", ["entity", "predicate", "source"])
    def test_kinds_validos(self, kind: str) -> None:
        assert ObligatorySelector(kind=kind, value="v").kind == kind

    def test_kind_invalido_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"selector\.kind invalido"):
            ObligatorySelector(kind="foo", value="v")  # type: ignore[arg-type]

    def test_kind_bool_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"selector\.kind invalido"):
            ObligatorySelector(kind=True, value="v")  # type: ignore[arg-type]

    def test_value_vacio_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"selector\.value vacio"):
            ObligatorySelector(kind="entity", value="")

    def test_label_vacio_es_valido(self) -> None:
        assert ObligatorySelector(kind="entity", value="v").label == ""

    def test_kind_gana_sobre_value_vacio(self) -> None:
        """Orden observable: kind invalido se queja antes de value vacio."""
        with pytest.raises(ValidationError, match=r"selector\.kind invalido"):
            ObligatorySelector(kind="foo", value="")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# ContextRecipe.__post_init__
# --------------------------------------------------------------------------


class TestContextRecipeInvariants:
    def test_receta_por_defecto_valida(self) -> None:
        r = ContextRecipe(recipe_ref="r")
        assert r.freshness_policy == "best_effort"
        assert r.token_budget == 8000
        assert r.overflow_strategy == "drop_optional"
        assert r.revision == 1

    def test_recipe_ref_vacio_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="recipe_ref vacio"):
            ContextRecipe(recipe_ref="")

    @pytest.mark.parametrize("policy", ["strict", "best_effort"])
    def test_freshness_policy_valida(self, policy: str) -> None:
        assert ContextRecipe(recipe_ref="r", freshness_policy=policy).freshness_policy == policy

    def test_freshness_policy_invalida_rechazada(self) -> None:
        with pytest.raises(ValidationError, match="freshness_policy invalida"):
            ContextRecipe(recipe_ref="r", freshness_policy="STRICT")  # type: ignore[arg-type]

    def test_token_budget_cero_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="token_budget debe ser positivo"):
            ContextRecipe(recipe_ref="r", token_budget=0)

    def test_token_budget_negativo_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="token_budget debe ser positivo"):
            ContextRecipe(recipe_ref="r", token_budget=-5)

    @pytest.mark.parametrize("strategy", ["drop_optional", "fail", "truncate_finding"])
    def test_overflow_strategy_valida(self, strategy: str) -> None:
        assert (
            ContextRecipe(recipe_ref="r", overflow_strategy=strategy).overflow_strategy == strategy
        )

    def test_overflow_strategy_invalida_rechazada(self) -> None:
        with pytest.raises(ValidationError, match="overflow_strategy invalido"):
            ContextRecipe(recipe_ref="r", overflow_strategy="DROP")  # type: ignore[arg-type]

    def test_revision_cero_rechazada(self) -> None:
        with pytest.raises(ValidationError, match="revision invalida"):
            ContextRecipe(recipe_ref="r", revision=0)

    def test_recipe_ref_gana_sobre_freshness_invalida(self) -> None:
        """Orden observable del __post_init__."""
        with pytest.raises(ValidationError, match="recipe_ref vacio"):
            ContextRecipe(recipe_ref="", freshness_policy="x")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# from_dict: formas de entrada
# --------------------------------------------------------------------------


class TestFromDictShape:
    def test_raw_no_dict_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="recipe raw debe ser dict"):
            ContextRecipe.from_dict(recipe_ref="r", raw="no")  # type: ignore[arg-type]

    def test_vacio_da_defaults(self) -> None:
        r = _load({})
        assert r.obligatory == ()
        assert r.optional == ()
        assert r.relation_selectors == ()

    def test_claves_desconocidas_ignoradas(self) -> None:
        """Comportamiento observado: forward-compat silenciosa."""
        r = _load({"clave_inventada": 1})
        assert r.recipe_ref == "r-1"

    def test_recipe_ref_viaja(self) -> None:
        assert ContextRecipe.from_dict(recipe_ref="otro", raw={}).recipe_ref == "otro"


class TestFromDictSelectors:
    def test_obligatory_parseado(self) -> None:
        r = _load({"obligatory": [_sel("entity", "e-1", "L"), _sel("predicate", "p")]})
        assert len(r.obligatory) == 2
        assert r.obligatory[0].kind == "entity"
        assert r.obligatory[0].label == "L"

    def test_optional_parseado(self) -> None:
        r = _load({"optional": [_sel("source", "s-1")]})
        assert len(r.optional) == 1
        assert r.optional[0].kind == "source"

    def test_obligatory_no_list_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"recipe\.obligatory debe ser list"):
            _load({"obligatory": "x"})

    def test_selector_no_dict_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"recipe\.obligatory\[0\] debe ser dict"):
            _load({"obligatory": ["x"]})

    def test_indice_en_el_error(self) -> None:
        """El error apunta al elemento exacto que falla."""
        with pytest.raises(ValidationError, match=r"recipe\.optional\[1\]"):
            _load({"optional": [_sel(), "no-dict"]})

    @pytest.mark.parametrize(
        ("field", "bad"),
        [("kind", True), ("value", 1), ("label", 2.5)],
    )
    def test_tipos_de_selector_rechazados(self, field: str, bad: object) -> None:
        item: dict[str, object] = {"kind": "entity", "value": "v"}
        item[field] = bad
        with pytest.raises(ValidationError, match=rf"recipe\.obligatory\[0\]\.{field}"):
            _load({"obligatory": [item]})

    def test_kind_invalido_en_dict_rechazado_por_smart_constructor(self) -> None:
        """El smart constructor de ObligatorySelector valida el Literal."""
        with pytest.raises(ValidationError, match=r"selector\.kind invalido"):
            _load({"obligatory": [_sel("foo")]})

    def test_selector_value_vacio_en_dict_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"selector\.value vacio"):
            _load({"obligatory": [_sel("entity", "")]})


class TestFromDictRelationSelectors:
    def test_relation_selectors_valido(self) -> None:
        r = _load({"relation_selectors": ["a", "b"]})
        assert r.relation_selectors == ("a", "b")

    def test_no_list_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="relation_selectors debe ser list"):
            _load({"relation_selectors": "a"})

    def test_elemento_no_str_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="relation_selectors debe ser list"):
            _load({"relation_selectors": ["a", 1]})

    def test_vacio_valido(self) -> None:
        assert _load({"relation_selectors": []}).relation_selectors == ()


# --------------------------------------------------------------------------
# from_dict: coercions y trampas bool (ESTADO OBSERVADO pre-fix)
# --------------------------------------------------------------------------


class TestFromDictCoercions:
    def test_token_budget_str_se_coacciona(self) -> None:
        """Observado: int('8000') se acepta. Coercion determinista."""
        assert _load({"token_budget": "8000"}).token_budget == 8000

    def test_token_budget_float_se_trunca(self) -> None:
        """Observado: int(2.9) == 2. Truncamiento silencioso."""
        assert _load({"token_budget": 2.9}).token_budget == 2

    def test_revision_str_se_coacciona(self) -> None:
        assert _load({"revision": "3"}).revision == 3

    def test_revision_bool_se_acepta_como_1(self) -> None:
        """TRAMPA bool, estado observado antes del fix.

        `bool` es subclase de `int`: `revision=True` pasa la validacion
        `revision >= 1` porque True == 1.
        """
        assert _load({"revision": True}).revision == 1

    def test_token_budget_bool_se_acepta_como_1(self) -> None:
        """TRAMPA bool, estado observado antes del fix.

        `token_budget=True` produce un presupuesto de 1 caracter en
        silencio. Nadie configura eso a proposito; es el mismo patron de
        fallo que metadata.max_visits (fix 21087d1).
        """
        assert _load({"token_budget": True}).token_budget == 1

    def test_bool_en_selectores_y_relaciones_rechazado(self) -> None:
        """El resto del schema ya rechaza bool: el hueco es solo escalar."""
        with pytest.raises(ValidationError, match="relation_selectors"):
            _load({"relation_selectors": [True]})


class TestFromDictFieldPrecedence:
    """El orden de validacion de from_dict es observable."""

    def test_raw_no_dict_gana_sobre_todo(self) -> None:
        with pytest.raises(ValidationError, match="recipe raw debe ser dict"):
            ContextRecipe.from_dict(recipe_ref="", raw="x")  # type: ignore[arg-type]

    def test_relation_selectors_gana_sobre_obligatory_malformado(self) -> None:
        """relation_selectors se valida antes de parsear selectors."""
        with pytest.raises(ValidationError, match="relation_selectors"):
            _load({"relation_selectors": 1, "obligatory": "tambien-mal"})

    def test_obligatory_gana_sobre_optional(self) -> None:
        with pytest.raises(ValidationError, match=r"recipe\.obligatory"):
            _load({"obligatory": "mal", "optional": "mal"})

    def test_defaults_aplicados_juntos(self) -> None:
        r = _load({"freshness_policy": "strict", "overflow_strategy": "fail"})
        assert r.freshness_policy == "strict"
        assert r.overflow_strategy == "fail"
        assert r.token_budget == 8000  # default intacto
