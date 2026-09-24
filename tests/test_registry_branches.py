"""Cobertura de ramas de validación del registro (cierra deuda H0).

El primer pase del spike S0 cubría el camino feliz y dos errores
explícitos. Estos tests cierran las ramas restantes que la
Estrategia de Tests (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md
§1 + §8) exige antes de declarar el hito completo.
"""

from __future__ import annotations

import pytest

from skillgraph import (
    Brick,
    BrickRegistry,
    BrickType,
    ResourceIdentity,
    UnknownKindError,
    ValidationError,
)

pytestmark = pytest.mark.spike


def _identity(name: str = "x") -> ResourceIdentity:
    return ResourceIdentity(
        tenant_id="t",
        project_id="p",
        namespace="software",
        kind="K",
        name=name,
    )


def _no_op(spec: dict) -> None:
    return None


class TestRegistryDecisionBranches:
    def test_decision_with_empty_outcomes_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_decision

        spec = {"ctx_recipe_ref": "x", "outcomes": []}
        with pytest.raises(ValidationError, match="outcomes"):
            _validate_decision(spec)

    def test_decision_with_non_list_outcomes_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_decision

        spec = {"ctx_recipe_ref": "x", "outcomes": "no-lista"}
        with pytest.raises(ValidationError, match="outcomes"):
            _validate_decision(spec)

    def test_decision_outcome_not_mapping_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_decision

        spec = {
            "ctx_recipe_ref": "x",
            "outcomes": ["no-mapping"],
        }
        with pytest.raises(ValidationError, match="outcomes\\[0\\]"):
            _validate_decision(spec)

    def test_decision_outcome_name_not_string_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_decision

        spec = {
            "ctx_recipe_ref": "x",
            "outcomes": [{"name": 42}],
        }
        with pytest.raises(ValidationError, match="name"):
            _validate_decision(spec)

    def test_decision_ctx_recipe_ref_not_string_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_decision

        spec = {"ctx_recipe_ref": 99, "outcomes": [{"name": "OK"}]}
        with pytest.raises(ValidationError, match="ctx_recipe_ref"):
            _validate_decision(spec)


class TestRegistryActionBranches:
    def test_action_with_empty_transitions_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_action

        spec = {"inputs": [], "transitions": {}}
        with pytest.raises(ValidationError, match="transitions"):
            _validate_action(spec)

    def test_action_with_non_dict_transitions_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_action

        spec = {"inputs": [], "transitions": []}
        with pytest.raises(ValidationError, match="transitions"):
            _validate_action(spec)

    def test_action_with_non_list_inputs_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_action

        spec = {"inputs": "no-lista", "transitions": {"X": "y"}}
        with pytest.raises(ValidationError, match="inputs"):
            _validate_action(spec)


class TestRegistryDomainPackBranches:
    def test_domain_pack_capabilities_not_list_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_domain_pack

        spec = {"version": "1.0.0", "capabilities": "no-lista"}
        with pytest.raises(ValidationError, match="capabilities"):
            _validate_domain_pack(spec)

    def test_domain_pack_version_not_string_rejected(self) -> None:
        from skillgraph.resources.registry import _validate_domain_pack

        spec = {"version": 1.0}
        with pytest.raises(ValidationError, match="version"):
            _validate_domain_pack(spec)


class TestRegistryApiVersionConsistency:
    def test_brick_with_mismatched_apiversion_rejected(self) -> None:
        """Si el brick declara apiVersion distinto del BrickType registrado,
        JS es rechazado aunque el kind sea conocido."""
        reg = BrickRegistry()
        reg.declare(
            BrickType(
                api_version="x/v1",
                kind="K",
                validate_spec=_no_op,
            )
        )
        bad = Brick(
            identity=_identity(),
            api_version="x/v2",  # distinto del declarado
            kind="K",
            spec={},
        )
        with pytest.raises(UnknownKindError, match="apiVersion"):
            reg.validate(bad)

    def test_brick_with_unknown_kind_at_validate_raises(self) -> None:
        reg = BrickRegistry()
        bad = Brick(
            identity=_identity(),
            api_version="n/v1",
            kind="Ghost",
            spec={},
        )
        with pytest.raises(UnknownKindError):
            reg.validate(bad)


class TestStorageRelationProperties:
    """Cierra la rama 'properties no vacias' de add_relation."""

    def test_add_relation_with_properties(self, tmp_data_root) -> None:
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_data_root / "p.sqlite")
        try:
            a = Brick(
                identity=ResourceIdentity(
                    tenant_id="t",
                    project_id="p",
                    namespace="software",
                    kind="ActionNode",
                    name="a",
                ),
                api_version="sg/v1",
                kind="ActionNode",
                spec={"inputs": [], "transitions": {"X": "y"}},
            )
            b = Brick(
                identity=ResourceIdentity(
                    tenant_id="t",
                    project_id="p",
                    namespace="software",
                    kind="ActionNode",
                    name="b",
                ),
                api_version="sg/v1",
                kind="ActionNode",
                spec={"inputs": [], "transitions": {"X": "y"}},
            )
            uid_a = s.upsert_resource(a)
            uid_b = s.upsert_resource(b)
            s.add_relation(
                tenant_id="t",
                project_id="p",
                source_uid=uid_a,
                target_uid=uid_b,
                kind="DEPENDS_ON",
                properties={"weight": 0.7, "note": "test"},
            )
            deps = s.dependencies_of(uid_a)
            assert len(deps) == 1
            import json as _json

            props = _json.loads(deps[0]["properties_json"])
            assert props == {"weight": 0.7, "note": "test"}
        finally:
            s.close()
