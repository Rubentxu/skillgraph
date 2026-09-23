"""H9-Coverage-2: cobertura de las ramas no ejercitadas de
`skillgraph.domain.pack_loader` (78% -> >=95%).

Las ramas cubiertas aqui son:
- _make_schema_validator: list_of, number, boolean, refs, dict-no-soportado,
  schema-tipo-invalido.
- declare_types_from_pack: types no-lista, entry no-dict, kind vacio,
  schema no-dict.

Sin modificacion de produccion. Spec: specs/h9-coverage-pack-loader.md.
"""

from __future__ import annotations

import pytest

from skillgraph.bricks import Brick, ResourceIdentity
from skillgraph.errors import ValidationError
from skillgraph.pack_loader import (
    declare_types_from_pack,
    validate_instance_against_registry,
)
from skillgraph.resources.registry import load_defaults


def _identity(
    *,
    namespace: str = "shared",
    kind: str = "",
    name: str = "",
) -> ResourceIdentity:
    return ResourceIdentity(
        tenant_id="t-default",
        project_id="demo",
        namespace=namespace,
        kind=kind,
        name=name,
    )


def _domain_pack(
    *,
    spec: dict,
    name: str = "test-pack",
) -> Brick:
    return Brick(
        identity=_identity(namespace="shared", kind="DomainPack", name=name),
        api_version="skillgraph.dev/v1alpha1",
        kind="DomainPack",
        spec=spec,
    )


def _instance(
    *,
    kind: str,
    name: str,
    spec: dict,
    namespace: str = "shared",
) -> Brick:
    return Brick(
        identity=_identity(namespace=namespace, kind=kind, name=name),
        api_version="skillgraph.dev/v1alpha1",
        kind=kind,
        spec=spec,
    )


# ---------------------------------------------------------------------------
# _make_schema_validator: ramas de validacion de campos
# ---------------------------------------------------------------------------


def test_schema_refs_field_is_passthrough() -> None:
    """Campo con `{refs: [...]}` se acepta sin validar FK (responsabilidad del motor).

    Cubre lineas 93-97 (rama `elif "refs" in field_schema`).
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "LinkedNode",
                    "schema": {
                        "required": ["name", "link"],
                        "fields": {"name": "string", "link": {"refs": ["Other"]}},
                    },
                }
            ],
        }
    )
    declare_types_from_pack(registry, pack)

    # La instancia pasa la validacion del pack aunque "Other" no exista en el
    # registry: la FK NO se valida en el pack_loader (es trabajo del motor).
    inst = _instance(kind="LinkedNode", name="n1", spec={"name": "n1", "link": "Other"})
    validate_instance_against_registry(registry, inst)


def test_schema_list_of_with_non_list_value_raises() -> None:
    """`fields: {tags: {list_of: string}}` + value no-lista -> ValidationError.

    Cubre linea 82.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "Tagged",
                    "schema": {
                        "required": ["name", "tags"],
                        "fields": {"name": "string", "tags": {"list_of": "string"}},
                    },
                }
            ],
        }
    )
    declare_types_from_pack(registry, pack)

    inst = _instance(
        kind="Tagged",
        name="t1",
        spec={"name": "t1", "tags": "not-a-list"},  # type: ignore[list-item]
    )
    with pytest.raises(ValidationError, match=r"esperaba lista"):
        validate_instance_against_registry(registry, inst)


def test_schema_number_mismatch_raises() -> None:
    """`fields: {ratio: "number"}` + value no numerico -> ValidationError.

    Cubre linea 70.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "Ratio",
                    "schema": {
                        "required": ["name", "ratio"],
                        "fields": {"name": "string", "ratio": "number"},
                    },
                }
            ],
        }
    )
    declare_types_from_pack(registry, pack)

    inst = _instance(
        kind="Ratio",
        name="r1",
        spec={"name": "r1", "ratio": "1.5"},  # type: ignore[dict-item]
    )
    with pytest.raises(ValidationError, match=r"number"):
        validate_instance_against_registry(registry, inst)


def test_schema_boolean_mismatch_raises() -> None:
    """`fields: {active: "boolean"}` + value no-bool -> ValidationError.

    Cubre linea 74.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "Switch",
                    "schema": {
                        "required": ["name", "active"],
                        "fields": {"name": "string", "active": "boolean"},
                    },
                }
            ],
        }
    )
    declare_types_from_pack(registry, pack)

    inst = _instance(
        kind="Switch",
        name="s1",
        spec={"name": "s1", "active": 1},  # type: ignore[dict-item]
    )
    with pytest.raises(ValidationError, match=r"boolean"):
        validate_instance_against_registry(registry, inst)


def test_schema_unsupported_dict_field_raises() -> None:
    """`fields: {weird: {unknown_key: 1}}` -> ValidationError 'no soportado'.

    Cubre lineas 98-101.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "Weird",
                    "schema": {
                        "required": ["name", "weird"],
                        "fields": {
                            "name": "string",
                            "weird": {"unknown_key": 1},
                        },
                    },
                }
            ],
        }
    )
    declare_types_from_pack(registry, pack)

    inst = _instance(
        kind="Weird",
        name="w1",
        spec={"name": "w1", "weird": {"unknown_key": 1}},
    )
    with pytest.raises(ValidationError, match=r"no soportado"):
        validate_instance_against_registry(registry, inst)


def test_schema_invalid_field_type_raises() -> None:
    """`fields: {weird: 42}` (int, no str ni dict) -> ValidationError 'invalido'.

    Cubre lineas 102-106.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [
                {
                    "kind": "InvalidSchema",
                    "schema": {
                        "required": ["name", "weird"],
                        "fields": {"name": "string", "weird": 42},
                    },
                }
            ],
        }
    )
    declare_types_from_pack(registry, pack)

    inst = _instance(
        kind="InvalidSchema",
        name="i1",
        spec={"name": "i1", "weird": 42},
    )
    with pytest.raises(ValidationError, match=r"invalido"):
        validate_instance_against_registry(registry, inst)


# ---------------------------------------------------------------------------
# declare_types_from_pack: ramas de validacion de tipos
# ---------------------------------------------------------------------------


def test_declare_types_pack_with_non_list_types_raises() -> None:
    """`pack.spec.types = "nope"` (no lista) -> ValidationError.

    Cubre linea 140.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": "not-a-list",  # type: ignore[dict-item]
        }
    )
    with pytest.raises(ValidationError, match=r"spec\.types debe ser lista"):
        declare_types_from_pack(registry, pack)


def test_declare_types_pack_with_non_dict_entry_raises() -> None:
    """`pack.spec.types = ["nope"]` (entry no-dict) -> ValidationError.

    Cubre linea 147.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": ["not-a-dict"],
        }
    )
    with pytest.raises(ValidationError, match=r"esperaba mapping"):
        declare_types_from_pack(registry, pack)


def test_declare_types_pack_with_empty_kind_raises() -> None:
    """`pack.spec.types = [{}]` (kind vacio) -> ValidationError.

    Cubre linea 153.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [{}],
        }
    )
    with pytest.raises(ValidationError, match=r"kind"):
        declare_types_from_pack(registry, pack)


def test_declare_types_pack_with_non_dict_schema_raises() -> None:
    """`entry.schema` no es dict -> ValidationError.

    Cubre linea 158.
    """
    registry = load_defaults()
    pack = _domain_pack(
        spec={
            "version": "1.0.0",
            "types": [{"kind": "X", "schema": "not-a-dict"}],
        }
    )
    with pytest.raises(ValidationError, match=r"schema"):
        declare_types_from_pack(registry, pack)
