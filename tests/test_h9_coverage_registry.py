"""H9-Coverage-6: cobertura de las ramas no ejercitadas de
`skillgraph.resources.registry` (93% -> >=95%).

Las ramas cubiertas aqui son:
- _validate_decision: outcomes[i]['name'] no-string -> ValidationError
- _validate_action: transitions con clave no-string -> ValidationError
- _validate_domain_pack: capabilities no-lista -> ValidationError

Sin modificacion de produccion. Spec: specs/h9-coverage-registry.md.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.resources.bricks import Brick, ResourceIdentity
from skillgraph.resources.registry import load_defaults


def _identity(*, kind: str = "X", name: str = "x") -> ResourceIdentity:
    return ResourceIdentity(
        tenant_id="t-1",
        project_id="demo",
        namespace="shared",
        kind=kind,
        name=name,
    )


# NOTA: la rama `brick_type.api_version != brick.api_version` en
# `validate()` es logica muerta por construccion (ver spec). No se cubre.


# ---------------------------------------------------------------------------
# _validate_decision: outcomes[i]['name'] no-string
# ---------------------------------------------------------------------------


def test_validate_decision_outcome_name_not_string_raises() -> None:
    """outcomes con name no-string (p.ej. int) -> ValidationError.

    Cubre linea 108->105 (rama verdadera del check `isinstance(outcome['name'], str)`).
    """
    reg = load_defaults()
    brick = Brick(
        identity=_identity(kind="DecisionNode", name="d1"),
        api_version="skillgraph.dev/v1alpha1",
        kind="DecisionNode",
        spec={
            "ctx_recipe_ref": "r1",
            "outcomes": [{"name": 123}],  # type: ignore[list-item]
        },
    )
    with pytest.raises(ValidationError, match=r"outcomes\[0\]\.name debe ser string"):
        reg.validate(brick)


# ---------------------------------------------------------------------------
# _validate_action: transitions con clave no-string
# ---------------------------------------------------------------------------


def test_validate_action_transition_key_not_string_raises() -> None:
    """transitions con clave entera -> ValidationError 'claves deben ser string'.

    Cubre linea 122 (rama verdadera del check `isinstance(state, str)`).
    """
    reg = load_defaults()
    brick = Brick(
        identity=_identity(kind="ActionNode", name="a1"),
        api_version="skillgraph.dev/v1alpha1",
        kind="ActionNode",
        spec={
            "inputs": [],
            "transitions": {42: "next"},  # type: ignore[dict-item]
        },
    )
    with pytest.raises(ValidationError, match=r"claves deben ser string"):
        reg.validate(brick)


# ---------------------------------------------------------------------------
# _validate_domain_pack: capabilities no-lista
# ---------------------------------------------------------------------------


def test_validate_domain_pack_capabilities_not_list_raises() -> None:
    """capabilities no-lista (string) -> ValidationError 'debe ser lista'.

    Cubre linea 130->exit (rama verdadera del check `isinstance(capabilities, list)`).
    """
    reg = load_defaults()
    brick = Brick(
        identity=_identity(kind="DomainPack", name="d1"),
        api_version="skillgraph.dev/v1alpha1",
        kind="DomainPack",
        spec={
            "version": "1.0.0",
            "capabilities": "not-a-list",  # type: ignore[dict-item]
        },
    )
    with pytest.raises(ValidationError, match=r"capabilities debe ser lista"):
        reg.validate(brick)
