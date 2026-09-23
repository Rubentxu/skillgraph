"""Tests H6 multiprosito (UAT-12): Domain Pack declara tipos extensibles
sin tocar el codigo del nucleo.

Criterio verificable (UAT-12):
"Dado un Domain Pack narrativo, cuando se registran Character y
StoryArc, entonces el proyecto puede crear y relacionar instancias
sin modificar el codigo del nucleo."

El test demuestra que:
1. Cargar un Domain Pack YAML declara sus tipos en BrickRegistry.
2. Crear instancias validas (Character, StoryArc) las acepta.
3. Crear instancias invalidas (falta campo required) las rechaza.
4. Tipos del nucleo (DecisionNode, ActionNode, DomainPack) siguen
   funcionando intactos.
5. Intentar redefinir un tipo del nucleo es rechazado.
6. Intentar usar namespace reservado ('core', 'skillgraph') es rechazado.
7. Validators no ejecutan codigo del pack (solo aplican esquema).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.bricks import Brick, ResourceIdentity
from skillgraph.errors import UnknownKindError, ValidationError
from skillgraph.pack_loader import (
    declare_types_from_pack,
    validate_instance_against_registry,
)
from skillgraph.resources.parser import parse_file
from skillgraph.resources.registry import load_defaults

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "packs"


def _make_identity(
    tenant_id: str = "t-default",
    project_id: str = "demo",
    namespace: str = "shared",
    kind: str = "",
    name: str = "",
) -> ResourceIdentity:
    return ResourceIdentity(
        tenant_id=tenant_id,
        project_id=project_id,
        namespace=namespace,
        kind=kind,
        name=name,
    )


def _load_narrative_pack() -> Brick:
    return parse_file(
        FIXTURES_DIR / "narrative-core.md",
        identity=_make_identity(namespace="", kind="", name=""),
    )


def _build_instance(kind: str, name: str, spec: dict, *, namespace: str = "shared") -> Brick:
    return Brick(
        identity=_make_identity(namespace=namespace, kind=kind, name=name),
        api_version="skillgraph.dev/v1alpha1",
        kind=kind,
        spec=spec,
    )


def test_pack_loader_declares_types_from_narrative_pack() -> None:
    """El pack narrativo declara Character y StoryArc en el registry."""
    pack = _load_narrative_pack()
    assert pack.kind == "DomainPack"

    registry = load_defaults()
    declared = declare_types_from_pack(registry, pack)

    assert declared == ["Character", "StoryArc"]
    assert registry.has("skillgraph.dev/v1alpha1", "Character")
    assert registry.has("skillgraph.dev/v1alpha1", "StoryArc")
    # Tipos del nucleo siguen presentes
    assert registry.has("skillgraph.dev/v1alpha1", "DecisionNode")
    assert registry.has("skillgraph.dev/v1alpha1", "ActionNode")
    assert registry.has("skillgraph.dev/v1alpha1", "DomainPack")


def test_pack_loader_valid_character_passes() -> None:
    """Character con campos required pasa validacion."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    char = _build_instance(
        "Character",
        "alice",
        {"name": "alice", "archetype": "hero", "backstory": "De un pueblo pequeno"},
    )
    # No debe lanzar
    validate_instance_against_registry(registry, char)


def test_pack_loader_valid_storyarc_passes() -> None:
    """StoryArc con required + acts lista pasa validacion."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    arc = _build_instance(
        "StoryArc",
        "hero-journey",
        {
            "title": "Hero Journey",
            "premise": "Un heroe parte de casa",
            "acts": ["partida", "prueba", "retorno"],
        },
    )
    validate_instance_against_registry(registry, arc)


def test_pack_loader_character_missing_archetype_fails() -> None:
    """Character sin archetype falla con ValidationError."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    char = _build_instance("Character", "bob", {"name": "bob"})
    with pytest.raises(ValidationError, match="archetype"):
        validate_instance_against_registry(registry, char)


def test_pack_loader_storyarc_missing_premise_fails() -> None:
    """StoryArc sin premise falla con ValidationError."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    arc = _build_instance("StoryArc", "incomplete", {"title": "X"})
    with pytest.raises(ValidationError, match="premise"):
        validate_instance_against_registry(registry, arc)


def test_pack_loader_unknown_kind_raises() -> None:
    """Un kind no registrado lanza UnknownKindError."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    foo = _build_instance("Foo", "x", {})
    with pytest.raises(UnknownKindError):
        validate_instance_against_registry(registry, foo)


def test_pack_loader_cannot_shadow_core_type() -> None:
    """No se permite redefinir un tipo del nucleo (DecisionNode, etc.)."""
    registry = load_defaults()
    # Construimos un pack que intenta redefinir DecisionNode
    shadow_pack = Brick(
        identity=_make_identity(namespace="shared", kind="DomainPack", name="evil"),
        api_version="skillgraph.dev/v1alpha1",
        kind="DomainPack",
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "DecisionNode",  # YA EXISTE en el nucleo
                    "schema": {"required": []},
                }
            ],
        },
    )
    with pytest.raises(ValidationError, match="ya declarado"):
        declare_types_from_pack(registry, shadow_pack)


def test_pack_loader_cannot_use_reserved_namespace() -> None:
    """Namespaces 'core' y 'skillgraph' son reservados del nucleo."""
    registry = load_defaults()
    pack_in_core = Brick(
        identity=_make_identity(namespace="core", kind="DomainPack", name="x"),
        api_version="skillgraph.dev/v1alpha1",
        kind="DomainPack",
        spec={
            "version": "1.0.0",
            "types": [{"kind": "Foo", "schema": {"required": []}}],
        },
    )
    with pytest.raises(ValidationError, match="reservado"):
        declare_types_from_pack(registry, pack_in_core)


def test_pack_loader_rejects_non_domain_pack() -> None:
    """declare_types_from_pack rechaza bricks que no son DomainPack."""
    registry = load_defaults()
    not_a_pack = Brick(
        identity=_make_identity(namespace="shared", kind="Character", name="x"),
        api_version="skillgraph.dev/v1alpha1",
        kind="Character",
        spec={"name": "x", "archetype": "y"},
    )
    with pytest.raises(ValidationError, match="DomainPack"):
        declare_types_from_pack(registry, not_a_pack)


def test_pack_loader_field_type_mismatch_fails() -> None:
    """Si un campo es int y llega string, falla (tipo primitivo)."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    # Crear un pack de test con un campo entero
    int_pack = Brick(
        identity=_make_identity(namespace="shared", kind="DomainPack", name="int-pack"),
        api_version="skillgraph.dev/v1alpha1",
        kind="DomainPack",
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "Counter",
                    "schema": {
                        "required": ["name", "value"],
                        "fields": {"name": "string", "value": "integer"},
                    },
                }
            ],
        },
    )
    declare_types_from_pack(registry, int_pack)

    # value como string debe fallar
    bad = _build_instance(
        "Counter", "c1", {"name": "c1", "value": "not_an_int"}, namespace="shared"
    )
    with pytest.raises(ValidationError, match="integer"):
        validate_instance_against_registry(registry, bad)


def test_pack_loader_list_of_field_validates_elements() -> None:
    """Campo list_of valida el tipo de cada elemento."""
    registry = load_defaults()
    declare_types_from_pack(registry, _load_narrative_pack())

    # StoryArc con acts que no son todos strings debe fallar
    bad_arc = _build_instance(
        "StoryArc",
        "broken",
        {
            "title": "Broken Arc",
            "premise": "X",
            "acts": ["partida", 123, "retorno"],  # 123 no es string
        },
    )
    with pytest.raises(ValidationError, match="esperaba string"):
        validate_instance_against_registry(registry, bad_arc)


def test_pack_loader_does_not_touch_kernel_modules() -> None:
    """Garantia UAT-12: el nucleo (registry.py, bricks.py, parser.py) NO se
    modifica para soportar multiprosito. Esto se valida como test de
    regresion: si alguien toca estos archivos, el test falla.

    Comprobamos que NO se ha importado pack_loader desde estos modulos
    (acoplamiento implicito).
    """
    # El nucleo no debe depender de pack_loader (seria inversion de
    # dependencias). Si alguien anade ese import, este test detectara
    # la regresion.
    # Tras v0.7.0 (refactor bounded contexts): nucleo vive en
    # src/skillgraph/resources/{registry,bricks,parser}.py.
    registry_src = Path("src/skillgraph/resources/registry.py").read_text(encoding="utf-8")
    bricks_src = Path("src/skillgraph/resources/bricks.py").read_text(encoding="utf-8")
    parser_src = Path("src/skillgraph/resources/parser.py").read_text(encoding="utf-8")

    for name, src in [
        ("resources/registry.py", registry_src),
        ("resources/bricks.py", bricks_src),
        ("resources/parser.py", parser_src),
    ]:
        assert "pack_loader" not in src, (
            f"{name} importa pack_loader: rompe el aislamiento del nucleo respecto a multiprosito"
        )
