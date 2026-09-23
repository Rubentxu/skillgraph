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
        """
        if not isinstance(raw, dict):
            raise ValidationError("recipe raw debe ser dict")

        def _selectors(items: object, where: str) -> tuple[ObligatorySelector, ...]:
            if not isinstance(items, list):
                raise ValidationError(
                    f"recipe.{where} debe ser list, recibio {type(items).__name__}"
                )
            out: list[ObligatorySelector] = []
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    raise ValidationError(f"recipe.{where}[{i}] debe ser dict")
                kind = it.get("kind")
                value = it.get("value")
                label = it.get("label", "")
                if not isinstance(kind, str):
                    raise ValidationError(f"recipe.{where}[{i}].kind debe ser str")
                if not isinstance(value, str):
                    raise ValidationError(f"recipe.{where}[{i}].value debe ser str")
                if not isinstance(label, str):
                    raise ValidationError(f"recipe.{where}[{i}].label debe ser str")
                out.append(
                    ObligatorySelector(
                        kind=kind,  # type: ignore[arg-type]
                        value=value,
                        label=label,
                    )
                )
            return tuple(out)

        obligatory_raw = raw.get("obligatory", [])
        optional_raw = raw.get("optional", [])
        rel_raw = raw.get("relation_selectors", [])
        if not isinstance(rel_raw, list) or not all(isinstance(x, str) for x in rel_raw):
            raise ValidationError("recipe.relation_selectors debe ser list[str]")

        obligatory = _selectors(obligatory_raw, "obligatory")
        optional = _selectors(optional_raw, "optional")

        return cls(
            recipe_ref=recipe_ref,
            obligatory=obligatory,
            optional=optional,
            relation_selectors=tuple(rel_raw),
            freshness_policy=raw.get("freshness_policy", "best_effort"),  # type: ignore[arg-type]
            token_budget=int(raw.get("token_budget", 8000)),
            overflow_strategy=raw.get("overflow_strategy", "drop_optional"),  # type: ignore[arg-type]
            revision=int(raw.get("revision", 1)),
        )


__all__ = [
    "ContextRecipe",
    "FreshnessPolicy",
    "ObligatorySelector",
    "OverflowStrategy",
]
