"""H9-Coverage-10: cobertura `skillgraph.resources.bricks` (91% -> 100%).

Modulo pequeno: solo `ResourceIdentity.as_dict()` no se invoca directamente
en la suite existente (se usa via `Brick.uid_components` -> delega ->
pero coverage reporta `as_dict` linea 29 como miss).

Tests:
- `ResourceIdentity.as_dict()` retorna dict con todos los campos.
- `Brick.uid_components` delega correctamente.

Spec: specs/h9-coverage-bricks.md.
"""

from __future__ import annotations

from skillgraph.resources.bricks import Brick, ResourceIdentity


def test_resource_identity_as_dict_has_all_fields() -> None:
    """ResourceIdentity.as_dict() retorna los 5 campos del blueprint."""
    ident = ResourceIdentity(
        tenant_id="t",
        project_id="p",
        namespace="shared",
        kind="ActionNode",
        name="a1",
    )
    d = ident.as_dict()
    assert d == {
        "tenant_id": "t",
        "project_id": "p",
        "namespace": "shared",
        "kind": "ActionNode",
        "name": "a1",
    }


def test_brick_uid_components_delegates_to_identity() -> None:
    """Brick.uid_components es una vista sobre identity.as_dict()."""
    ident = ResourceIdentity(
        tenant_id="t2",
        project_id="p2",
        namespace="ns",
        kind="DecisionNode",
        name="d1",
    )
    brick = Brick(identity=ident, api_version="v1", kind="DecisionNode")
    assert brick.uid_components == ident.as_dict()
    assert brick.uid_components["kind"] == "DecisionNode"
