"""Tests del spike S1: SQLite + aislamiento + frontera/dependencias.

Doc de cobertura (external/blueprint-v1/plan/SPIKES.md, S1):
- Crear recursos, relaciones y dependencias.
- Consultas de frontera, dependencias inversas y aislamiento.
- Medir latencia sobre un conjunto representativo.

Reglas (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Fixtures sin credenciales, red ni proveedor LLM.
- Aislamiento: cada test abre su propio `tmp_path`.
- Negative-space testing: sin filtración entre proyectos.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from skillgraph import Brick, ResourceIdentity, parse_file
from skillgraph.core.errors import IdentityConflictError
from skillgraph.platform.storage import Storage

pytestmark = pytest.mark.spike


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _brick_from(
    fixture_path: Path, *, project_id: str = "p-s1", kind: str = "DecisionNode"
) -> Brick:
    return parse_file(
        fixture_path,
        identity=ResourceIdentity(
            tenant_id="tenant-test",
            project_id=project_id,
            namespace="software",
            kind=kind,
            name="any",
        ),
    )


def _uid_for(b: Brick) -> str:
    i = b.identity
    return f"{i.tenant_id}/{i.project_id}/{b.api_version}/{b.kind}/{i.namespace}/{i.name}"


# ---------------------------------------------------------------------------
# Aislamiento y round-trip
# ---------------------------------------------------------------------------


class TestStorageRoundTrip:
    def test_upsert_and_get_resource_round_trip(
        self, tmp_data_root: Path, fixtures_dir: Path
    ) -> None:
        s = Storage(tmp_data_root / "p.sqlite")
        try:
            brick = _brick_from(fixtures_dir / "s0" / "decision-valid.md")
            uid = s.upsert_resource(brick)
            got = s.get_resource(uid)
            assert got is not None
            assert got["kind"] == "DecisionNode"
            assert json.loads(got["spec_json"])["ctx_recipe_ref"] == ("software.implementation")
        finally:
            s.close()

    def test_upsert_idempotent_when_spec_matches(
        self, tmp_data_root: Path, fixtures_dir: Path
    ) -> None:
        s = Storage(tmp_data_root / "p.sqlite")
        try:
            brick = _brick_from(fixtures_dir / "s0" / "decision-valid.md")
            uid1 = s.upsert_resource(brick)
            uid2 = s.upsert_resource(brick)
            assert uid1 == uid2
        finally:
            s.close()

    def test_upsert_rejects_conflicting_spec(self, tmp_data_root: Path, fixtures_dir: Path) -> None:
        s = Storage(tmp_data_root / "p.sqlite")
        try:
            brick1 = _brick_from(fixtures_dir / "s0" / "decision-valid.md")
            s.upsert_resource(brick1)
            tampered = Brick(
                identity=brick1.identity,
                api_version=brick1.api_version,
                kind=brick1.kind,
                spec={"ctx_recipe_ref": "otra.receta", "outcomes": []},
                markdown_body=brick1.markdown_body,
            )
            with pytest.raises(IdentityConflictError):
                s.upsert_resource(tampered)
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Aislamiento entre proyectos (negative-space)
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_resources_do_not_leak_across_projects(
        self, tmp_data_root: Path, fixtures_dir: Path
    ) -> None:
        sa = Storage(tmp_data_root / "alpha.sqlite")
        sb = Storage(tmp_data_root / "beta.sqlite")
        try:
            a = _brick_from(fixtures_dir / "s0" / "decision-valid.md", project_id="alpha")
            b = _brick_from(fixtures_dir / "s0" / "decision-valid.md", project_id="beta")
            uid_a = sa.upsert_resource(a)
            uid_b = sb.upsert_resource(b)
            assert uid_a != uid_b
            assert sa.get_resource(uid_a) is not None
            assert sa.get_resource(uid_b) is None
            assert sb.get_resource(uid_b) is not None
            assert sb.get_resource(uid_a) is None
        finally:
            sa.close()
            sb.close()

    def test_list_resources_filters_by_project(
        self, tmp_data_root: Path, fixtures_dir: Path
    ) -> None:
        sa = Storage(tmp_data_root / "alpha.sqlite")
        sb = Storage(tmp_data_root / "beta.sqlite")
        try:
            sa.upsert_resource(
                _brick_from(fixtures_dir / "s0" / "decision-valid.md", project_id="alpha")
            )
            sb.upsert_resource(
                _brick_from(fixtures_dir / "s0" / "decision-valid.md", project_id="beta")
            )
            assert len(sa.list_resources(tenant_id="tenant-test", project_id="alpha")) == 1
            assert len(sa.list_resources(tenant_id="tenant-test", project_id="beta")) == 0
        finally:
            sa.close()
            sb.close()


# ---------------------------------------------------------------------------
# Relaciones: frontera + dependencias inversas
# ---------------------------------------------------------------------------


class TestRelations:
    def test_add_relation_and_query_frontier_and_inverse(
        self, tmp_data_root: Path, fixtures_dir: Path
    ) -> None:
        s = Storage(tmp_data_root / "p.sqlite")
        try:
            a = _brick_from(fixtures_dir / "s0" / "decision-valid.md")
            b = _brick_from(fixtures_dir / "s0" / "action-valid.md", kind="ActionNode")
            uid_a = s.upsert_resource(a)
            uid_b = s.upsert_resource(b)
            s.add_relation(
                tenant_id="tenant-test",
                project_id="p-s1",
                source_uid=uid_a,
                target_uid=uid_b,
                kind="DEPENDS_ON",
            )
            assert len(s.dependencies_of(uid_a)) == 1
            assert len(s.dependents_of(uid_b)) == 1
            s.add_relation(
                tenant_id="tenant-test",
                project_id="p-s1",
                source_uid=uid_a,
                target_uid=uid_b,
                kind="DEPENDS_ON",
            )
            assert len(s.dependencies_of(uid_a)) == 1
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Latencia sobre fixture representativa (1000 recursos)
# ---------------------------------------------------------------------------


class TestPerformance:
    """Criterio de salida del spike S1: latencia < 50 ms en queries
    de frontera y dependencias inversas sobre 1000 recursos.
    """

    @staticmethod
    def _brick_for(i: int) -> Brick:
        return Brick(
            identity=ResourceIdentity(
                tenant_id="tenant-test",
                project_id="p-perf",
                namespace="software",
                kind="DecisionNode",
                name=f"node-{i:04d}",
            ),
            api_version="skillgraph.dev/v1alpha1",
            kind="DecisionNode",
            spec={
                "ctx_recipe_ref": f"software.impl-{i:04d}",
                "outcomes": [{"name": "OK", "next": "x"}],
            },
        )

    def test_frontier_query_under_50ms_over_1k_resources(self, tmp_data_root: Path) -> None:
        s = Storage(tmp_data_root / "perf.sqlite")
        try:
            bricks: list[Brick] = [self._brick_for(i) for i in range(1000)]
            t0 = time.perf_counter()
            for b in bricks:
                s.upsert_resource(b)
            t_insert = time.perf_counter() - t0

            uids = [_uid_for(b) for b in bricks]
            for i in range(999):
                s.add_relation(
                    tenant_id="tenant-test",
                    project_id="p-perf",
                    source_uid=uids[i],
                    target_uid=uids[i + 1],
                    kind="DEPENDS_ON",
                )

            t0 = time.perf_counter()
            for _ in range(100):
                s.dependencies_of(uids[500])
            t_query = (time.perf_counter() - t0) / 100

            t0 = time.perf_counter()
            for _ in range(100):
                s.dependents_of(uids[500])
            t_inverse = (time.perf_counter() - t0) / 100

            assert t_query < 0.050, f"frontera tardó {t_query * 1000:.1f} ms"
            assert t_inverse < 0.050, f"inversa tardó {t_inverse * 1000:.1f} ms"
            print(
                f"\nS1 perf: insert 1k={t_insert * 1000:.0f}ms, "
                f"frontier={t_query * 1000:.2f}ms, inverse={t_inverse * 1000:.2f}ms"
            )
        finally:
            s.close()
