"""Tests del spike S0: brick mínimo Markdown+YAML.

Doc de cobertura del spike (external/blueprint-v1/plan/SPIKES.md, S0):
- DecisionNode, ActionNode y DomainPack mínimo.
- Validación de esquema, resolución de referencias y rechazo de inválidos.

Reglas de la estrategia (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Sin credenciales, red ni proveedor LLM.
- Cada test usa fixtures reales en tests/fixtures/s0/.
- Aislamiento: la identidad que se pasa al parser es siempre local al test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph import (
    BrickRegistry,
    ParseError,
    ResourceIdentity,
    UnknownKindError,
    ValidationError,
    load_defaults,
    parse_file,
    parse_markdown,
)

pytestmark = pytest.mark.spike


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identity() -> ResourceIdentity:
    return ResourceIdentity(
        tenant_id="tenant-test",
        project_id="project-s001",
        namespace="software",
        kind="DecisionNode",
        name="any",
    )


# ---------------------------------------------------------------------------
# Parser: el contrato declarativo se respeta o se rechaza con ParseError
# ---------------------------------------------------------------------------


class TestParserShape:
    def test_decision_valid_returns_brick_with_all_components(self, fixtures_dir: Path) -> None:
        brick = parse_file(
            fixtures_dir / "s0" / "decision-valid.md",
            identity=_identity(),
        )
        assert brick.api_version == "skillgraph.dev/v1alpha1"
        assert brick.kind == "DecisionNode"
        assert brick.spec["ctx_recipe_ref"] == "software.implementation"
        assert len(brick.spec["outcomes"]) == 3
        assert "Seleccionar implementación" in brick.markdown_body

    def test_action_valid_parses_with_transitions(self, fixtures_dir: Path) -> None:
        brick = parse_file(
            fixtures_dir / "s0" / "action-valid.md",
            identity=ResourceIdentity(
                tenant_id="t",
                project_id="p",
                namespace="software",
                kind="ActionNode",
                name="any",
            ),
        )
        assert brick.kind == "ActionNode"
        assert "SUCCEEDED" in brick.spec["transitions"]
        assert "FAILED" in brick.spec["transitions"]

    def test_domain_pack_valid_parses_with_capabilities(self, fixtures_dir: Path) -> None:
        brick = parse_file(
            fixtures_dir / "s0" / "domain-pack-valid.md",
            identity=ResourceIdentity(
                tenant_id="t",
                project_id="p",
                namespace="shared",
                kind="DomainPack",
                name="any",
            ),
        )
        assert brick.kind == "DomainPack"
        assert brick.spec["version"] == "1.0.0"
        assert brick.spec["capabilities"][0]["name"] == "review-story"

    @pytest.mark.parametrize(
        "fixture_name, expected_substring",
        [
            ("no-front-matter.md", "front matter"),
            ("decision-missing-name.md", "metadata.name"),
        ],
    )
    def test_invalid_front_matter_rejected_with_parse_error(
        self, fixtures_dir: Path, fixture_name: str, expected_substring: str
    ) -> None:
        with pytest.raises(ParseError, match=expected_substring):
            parse_file(
                fixtures_dir / "s0" / fixture_name,
                identity=_identity(),
            )


# ---------------------------------------------------------------------------
# Registro: la validación tipada rechaza lo que el parser no puede
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_load_defaults_has_three_brick_types(self) -> None:
        reg = load_defaults()
        assert reg.has("skillgraph.dev/v1alpha1", "DecisionNode")
        assert reg.has("skillgraph.dev/v1alpha1", "ActionNode")
        assert reg.has("skillgraph.dev/v1alpha1", "DomainPack")

    def test_validate_decision_missing_outcomes_raises(self, fixtures_dir: Path) -> None:
        brick = parse_file(
            fixtures_dir / "s0" / "decision-missing-outcomes.md",
            identity=_identity(),
        )
        reg = load_defaults()
        with pytest.raises(ValidationError, match="outcomes"):
            reg.validate(brick)

    def test_validate_unknown_kind_raises(self, fixtures_dir: Path) -> None:
        brick = parse_file(
            fixtures_dir / "s0" / "unknown-kind.md",
            identity=ResourceIdentity(
                tenant_id="t",
                project_id="p",
                namespace="software",
                kind="MysteriousKind",
                name="unknown-kind",
            ),
        )
        reg = load_defaults()
        with pytest.raises(UnknownKindError):
            reg.validate(brick)

    def test_registry_declare_twice_raises(self) -> None:
        from skillgraph import BrickType

        reg = BrickRegistry()

        def _no_op(spec: dict) -> None:
            return None

        reg.declare(
            BrickType(
                api_version="x/v1",
                kind="K",
                validate_spec=_no_op,
            )
        )
        with pytest.raises(ValidationError, match="ya declarado"):
            reg.declare(
                BrickType(
                    api_version="x/v1",
                    kind="K",
                    validate_spec=_no_op,
                )
            )


# ---------------------------------------------------------------------------
# API estable: el paquete expone lo que dice su __all__
# ---------------------------------------------------------------------------


def test_parse_markdown_returns_brick_for_inline_text() -> None:
    text = (
        "---\n"
        "apiVersion: skillgraph.dev/v1alpha1\n"
        "kind: DomainPack\n"
        "metadata:\n"
        "  name: inline\n"
        "  namespace: shared\n"
        "spec:\n"
        "  version: 0.1.0\n"
        "---\n"
        "# inline\n"
    )
    brick = parse_markdown(
        text,
        source="inline.md",
        identity=ResourceIdentity(
            tenant_id="t",
            project_id="p",
            namespace="shared",
            kind="DomainPack",
            name="inline",
        ),
    )
    assert brick.kind == "DomainPack"
    assert brick.spec["version"] == "0.1.0"
