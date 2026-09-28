"""ContextRecipe: versionable recipes for compiling handoffs.

Doc externo:
  specs/h3-slice-5.md (sub-spec firmado en el H3).
  external/blueprint-v1/docs/06-recipes-handoffs.md.

Una `ContextRecipe` define QUE conocimiento se incluye en el handoff
para un nodo:

- `obligatory`: selectores que DEBEN resolverse (fallo => error).
- `optional`: selectores que se incluyen si caben en el budget.
- `relation_selectors`: formas de expansion transitiva.
- `freshness_policy`: "strict" o "best_effort" (D4 cerrada por defecto).
- `token_budget`: limite aproximado en caracteres (D4 cerrada por defecto).
- `overflow_strategy`: "drop_optional", "fail", "truncate_finding".

Slice 5 carga la receta desde un dict (D2='no brick'); el slice
posterior podria anadir un brick kind 'ContextRecipe'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from skillgraph.core.errors import ValidationError

FreshnessPolicy = Literal["strict", "best_effort"]
OverflowStrategy = Literal["drop_optional", "fail", "truncate_finding"]


def _coerce_int(raw: dict[str, object], *, field: str, default: int) -> int:
    """Smart coercion de escalar entero desde el dict crudo.

    `bool` se rechaza explicitamente: en Python `isinstance(True, int)`
    es True, asi que `int(True)` seria 1 y un `token_budget=True` o una
    `revision=True` pasarian en silencio con valores absurdos. Es el
    mismo patron de fallo que metadata.max_visits (fix 21087d1).

    Las demas coercions observadas se preservan (deterministas y fijadas
    por test): `int('8000')` se acepta y `int(2.9)` trunca a 2.
    """
    if field not in raw:
        return default
    value = raw[field]
    if isinstance(value, bool):
        raise ValidationError(f"recipe.{field} debe ser int, no bool: {value!r}")
    return int(value)


def _parse_selector_item(item: object, where: str, i: int) -> ObligatorySelector:
    """Parsea un elemento {kind, value, label} con tipos estrictos.

    `where` e `i` solo aparecen en los mensajes de error: apuntan al
    elemento exacto que falla dentro de la receta.
    """
    if not isinstance(item, dict):
        raise ValidationError(f"recipe.{where}[{i}] debe ser dict")
    kind = item.get("kind")
    value = item.get("value")
    label = item.get("label", "")
    if not isinstance(kind, str):
        raise ValidationError(f"recipe.{where}[{i}].kind debe ser str")
    if not isinstance(value, str):
        raise ValidationError(f"recipe.{where}[{i}].value debe ser str")
    if not isinstance(label, str):
        raise ValidationError(f"recipe.{where}[{i}].label debe ser str")
    # El smart constructor de ObligatorySelector valida el Literal.
    return ObligatorySelector(kind=kind, value=value, label=label)


def _parse_selectors(items: object, where: str) -> tuple[ObligatorySelector, ...]:
    """Parsea una lista de selectores; `where` nombra el campo en errores."""
    if not isinstance(items, list):
        raise ValidationError(f"recipe.{where} debe ser list, recibio {type(items).__name__}")
    return tuple(_parse_selector_item(it, where, i) for i, it in enumerate(items))


@dataclass(frozen=True, slots=True)
class ObligatorySelector:
    """Selector por entity_id, predicate, o source_id.

    `kind` indica qué campo usar:
      - "entity": match por entity_id exacto.
      - "predicate": match por predicate.
      - "source": match por source_id exacto.
    """

    kind: Literal["entity", "predicate", "source"]
    value: str
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind not in {"entity", "predicate", "source"}:
            raise ValidationError(f"selector.kind invalido: {self.kind!r}")
        if not self.value:
            raise ValidationError("selector.value vacio")


@dataclass(frozen=True, slots=True)
class ContextRecipe:
    """Receta de contexto: selectores, freshness, budget, overflow.

    ADT inmutable (frozen+slots). Se carga desde un dict via `from_dict`.
    """

    recipe_ref: str
    obligatory: tuple[ObligatorySelector, ...] = field(default_factory=tuple)
    optional: tuple[ObligatorySelector, ...] = field(default_factory=tuple)
    relation_selectors: tuple[str, ...] = field(default_factory=tuple)
    freshness_policy: FreshnessPolicy = "best_effort"
    token_budget: int = 8000
    overflow_strategy: OverflowStrategy = "drop_optional"
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.recipe_ref:
            raise ValidationError("recipe_ref vacio")
        if self.freshness_policy not in {"strict", "best_effort"}:
            raise ValidationError(f"freshness_policy invalida: {self.freshness_policy!r}")
        if self.token_budget <= 0:
            raise ValidationError(f"token_budget debe ser positivo: {self.token_budget}")
        if self.overflow_strategy not in {
            "drop_optional",
            "fail",
            "truncate_finding",
        }:
            raise ValidationError(f"overflow_strategy invalido: {self.overflow_strategy!r}")
        if self.revision < 1:
            raise ValidationError(f"revision invalida: {self.revision}")

    @classmethod
    def from_dict(
        cls,
        *,
        recipe_ref: str,
        raw: dict[str, object],
    ) -> ContextRecipe:
        """Carga una receta desde un dict (D2 cerrada como no-brick).

        Esquema esperado:
          obligatory: list[{kind: entity|predicate|source, value: str}]
          optional:   list (mismo shape)
          relation_selectors: list[str]
          freshness_policy: "strict" | "best_effort"
          token_budget: int
          overflow_strategy: "drop_optional" | "fail" | "truncate_finding"
          revision: int

        El orden de validacion es contrato observable: relation_selectors
        se comprueba antes que los selectors, y obligatory antes que
        optional. Ver tests/test_wi53_recipe_contracts.py.
        """
        if not isinstance(raw, dict):
            raise ValidationError("recipe raw debe ser dict")

        rel_raw = raw.get("relation_selectors", [])
        if not isinstance(rel_raw, list) or not all(isinstance(x, str) for x in rel_raw):
            raise ValidationError("recipe.relation_selectors debe ser list[str]")

        obligatory = _parse_selectors(raw.get("obligatory", []), "obligatory")
        optional = _parse_selectors(raw.get("optional", []), "optional")

        return cls(
            recipe_ref=recipe_ref,
            obligatory=obligatory,
            optional=optional,
            relation_selectors=tuple(rel_raw),
            freshness_policy=raw.get("freshness_policy", "best_effort"),  # type: ignore[arg-type]
            token_budget=_coerce_int(raw, field="token_budget", default=8000),
            overflow_strategy=raw.get("overflow_strategy", "drop_optional"),  # type: ignore[arg-type]
            revision=_coerce_int(raw, field="revision", default=1),
        )


__all__ = [
    "ContextRecipe",
    "FreshnessPolicy",
    "ObligatorySelector",
    "OverflowStrategy",
]
