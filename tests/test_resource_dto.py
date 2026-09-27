"""Tests for WI-32.5 resources DTOs.

Verifica ``StoredResource`` y ``StoredRelation`` (relaciones entre
recursos): dataclasses frozen + slots con campos 1:1 contra
``resources`` y ``relations``.

Admission gate de WI-32.5 (R1 del audit externo).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from skillgraph.platform.ports import StoredRelation, StoredResource


def test_stored_resource_is_frozen_dataclass() -> None:
    assert is_dataclass(StoredResource)
    r = StoredResource(
        uid="r1",
        tenant_id="t1",
        project_id="p1",
        api_version="v1",
        kind="Skill",
        namespace="ns",
        name="my-skill",
        resource_version=1,
        generation=1,
        spec_json="{}",
        status_json="{}",
        created_at="2026-01-01 00:00:00",
    )
    with pytest.raises(FrozenInstanceError):
        r.kind = "Policy"  # type: ignore[misc]


def test_stored_resource_field_count_matches_schema() -> None:
    f = {fld.name for fld in fields(StoredResource)}
    assert f == {
        "uid",
        "tenant_id",
        "project_id",
        "api_version",
        "kind",
        "namespace",
        "name",
        "resource_version",
        "generation",
        "spec_json",
        "status_json",
        "created_at",
    }


def test_stored_resource_to_dict_roundtrip() -> None:
    r = StoredResource(
        uid="r1",
        tenant_id="t1",
        project_id="p1",
        api_version="v1",
        kind="Skill",
        namespace="ns",
        name="my-skill",
        resource_version=3,
        generation=2,
        spec_json='{"x":1}',
        status_json='{"ready":true}',
        created_at="2026-01-01 00:00:00",
    )
    d = r.to_dict()
    assert d["uid"] == "r1"
    assert d["resource_version"] == 3
    assert d["generation"] == 2
    assert d["spec_json"] == '{"x":1}'
    assert d["status_json"] == '{"ready":true}'


def test_stored_relation_is_frozen_dataclass() -> None:
    assert is_dataclass(StoredRelation)
    rel = StoredRelation(
        uid="rel1",
        tenant_id="t1",
        project_id="p1",
        source_uid="a",
        target_uid="b",
        kind="DEPENDS_ON",
        properties_json='{"v":1}',
    )
    with pytest.raises(FrozenInstanceError):
        rel.kind = "OTHER"  # type: ignore[misc]


def test_stored_relation_field_count() -> None:
    f = {fld.name for fld in fields(StoredRelation)}
    assert f == {
        "uid",
        "tenant_id",
        "project_id",
        "source_uid",
        "target_uid",
        "kind",
        "properties_json",
    }


def test_stored_relation_to_dict_roundtrip() -> None:
    rel = StoredRelation(
        uid="rel1",
        tenant_id="t1",
        project_id="p1",
        source_uid="a",
        target_uid="b",
        kind="DEPENDS_ON",
        properties_json=None,
    )
    d = rel.to_dict()
    assert d["source_uid"] == "a"
    assert d["target_uid"] == "b"
    assert d["kind"] == "DEPENDS_ON"
    assert d["properties_json"] is None
