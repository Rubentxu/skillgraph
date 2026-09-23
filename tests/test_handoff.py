"""Tests del Handoff materializado (Etapa 2 / S2).

Cobertura:
- Validacion en construccion (4 sub-datos + expected_result).
- Serializacion estable (mismo contenido -> mismo JSON canonico).
- context_hash SHA-256 determinista.
- Distinto contenido -> distinto hash (incluso con reordenado de
  tuplas y dict budget).
"""

from __future__ import annotations

import pytest

from skillgraph.errors import ValidationError
from skillgraph.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)


def _identity(**overrides: object) -> HandoffIdentity:
    base = dict(
        tenant_id="t",
        project_id="p",
        run_id="r-1",
        node_execution_id="ne-1",
        attempt=1,
    )
    base.update(overrides)
    return HandoffIdentity(**base)  # type: ignore[arg-type]


def _behavior(**overrides: object) -> HandoffBehavior:
    base = dict(
        definition_kind="ActionNode",
        definition_name="act",
        definition_namespace="shared",
        definition_revision=1,
        api_version="skillgraph.dev/v1alpha1",
    )
    base.update(overrides)
    return HandoffBehavior(**base)  # type: ignore[arg-type]


def _knowledge(**overrides: object) -> HandoffKnowledge:
    base: dict[str, object] = dict(recipe_ref="rcp-1")
    base.update(overrides)
    return HandoffKnowledge(**base)  # type: ignore[arg-type]


def _execution(**overrides: object) -> HandoffExecution:
    base: dict[str, object] = dict(
        workspace_ref="ws:.",
        source_revision="abc123",
        budget={"max_nodes": 10},
    )
    base.update(overrides)
    return HandoffExecution(**base)  # type: ignore[arg-type]


def _handoff(**overrides: object) -> Handoff:
    base: dict[str, object] = dict(
        identity=_identity(),
        behavior=_behavior(),
        knowledge=_knowledge(),
        execution=_execution(),
        expected_result="text",
    )
    base.update(overrides)
    return Handoff(**base)  # type: ignore[arg-type]


class TestHandoffValidation:
    def test_minimal_handoff_is_valid(self) -> None:
        h = _handoff()
        assert isinstance(h.context_hash, str)
        assert len(h.context_hash) == 64

    @pytest.mark.parametrize(
        "field, kwargs, needle",
        [
            ("identity.tenant_id", dict(tenant_id=""), "tenant_id"),
            ("identity.project_id", dict(project_id=""), "project_id"),
            ("identity.run_id", dict(run_id=""), "run_id"),
            ("identity.node_execution_id", dict(node_execution_id=""), "node_execution_id"),
            ("identity.attempt", dict(attempt=0), "attempt"),
            ("behavior.definition_kind", dict(definition_kind="Unknown"), "definition_kind"),
            ("behavior.definition_name", dict(definition_name=""), "definition_name"),
            ("behavior.definition_revision", dict(definition_revision=0), "revision"),
            ("behavior.api_version", dict(api_version=""), "api_version"),
            ("knowledge.recipe_ref", dict(recipe_ref=""), "recipe_ref"),
            ("execution.workspace_ref", dict(workspace_ref=""), "workspace_ref"),
            ("execution.source_revision", dict(source_revision=""), "source_revision"),
            ("expected_result", dict(expected_result=""), "expected_result"),
        ],
    )
    def test_invalid_field_rejected(
        self, field: str, kwargs: dict[str, object], needle: str
    ) -> None:
        if "." in field:
            section, prop = field.split(".", 1)
            if section == "identity":
                with pytest.raises(ValidationError, match=needle):
                    _identity(**{prop: kwargs[prop]})  # type: ignore[arg-type]
            elif section == "behavior":
                with pytest.raises(ValidationError, match=needle):
                    _behavior(**{prop: kwargs[prop]})  # type: ignore[arg-type]
            elif section == "knowledge":
                with pytest.raises(ValidationError, match=needle):
                    _knowledge(**{prop: kwargs[prop]})  # type: ignore[arg-type]
            elif section == "execution":
                with pytest.raises(ValidationError, match=needle):
                    _execution(**{prop: kwargs[prop]})  # type: ignore[arg-type]
        else:
            with pytest.raises(ValidationError, match=needle):
                _handoff(**{field: kwargs[field]})  # type: ignore[arg-type]


class TestHandoffSerialization:
    def test_to_dict_is_deterministic_for_same_input(self) -> None:
        h1 = _handoff()
        h2 = _handoff()
        assert h1.to_dict() == h2.to_dict()

    def test_context_hash_is_deterministic(self) -> None:
        h1 = _handoff()
        h2 = _handoff()
        assert h1.context_hash == h2.context_hash

    def test_capabilities_sorted_in_serialization(self) -> None:
        h1 = _handoff(capabilities=("c2", "c1", "c3"))
        h2 = _handoff(capabilities=("c1", "c2", "c3"))
        assert h1.to_dict() == h2.to_dict()
        assert h1.context_hash == h2.context_hash

    def test_budget_sorted_in_serialization(self) -> None:
        h1 = _execution(budget={"a": 1, "b": 2})
        h2 = _execution(budget={"b": 2, "a": 1})
        h_a = _handoff(execution=h1)
        h_b = _handoff(execution=h2)
        assert h_a.context_hash == h_b.context_hash

    def test_different_revision_changes_hash(self) -> None:
        h1 = _handoff(behavior=_behavior(definition_revision=1))
        h2 = _handoff(behavior=_behavior(definition_revision=2))
        assert h1.context_hash != h2.context_hash

    def test_different_attempt_changes_hash(self) -> None:
        h1 = _handoff(identity=_identity(attempt=1))
        h2 = _handoff(identity=_identity(attempt=2))
        assert h1.context_hash != h2.context_hash

    def test_different_knowledge_included_changes_hash(self) -> None:
        h1 = _handoff(
            knowledge=_knowledge(
                included=(("Action", "shared", "alpha"),),
            )
        )
        h2 = _handoff(
            knowledge=_knowledge(
                included=(("Action", "shared", "beta"),),
            )
        )
        assert h1.context_hash != h2.context_hash

    def test_different_capabilities_changes_hash(self) -> None:
        h1 = _handoff(capabilities=("read",))
        h2 = _handoff(capabilities=("write",))
        assert h1.context_hash != h2.context_hash

    def test_hash_format_is_hex_sha256(self) -> None:
        h = _handoff()
        h.context_hash  # noqa: B018
        assert all(c in "0123456789abcdef" for c in h.context_hash)
        assert len(h.context_hash) == 64
