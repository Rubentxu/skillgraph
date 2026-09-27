"""Tests para los 3 metodos nuevos de Storage que cierran los 4 sitios SQL
directos en ContextController (H9-Coverage-11, ADR-0014).

Siguen el patron de test_h9_storage_*.py:
- contrato observable (input/output);
- aislamiento por tenant+project donde aplique;
- tests de no-regresion por introspeccion.

Cobertura objetivo: cada metodo >= 4 tests.
"""

from __future__ import annotations

import json
import re

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.graph import Claim, Entity, Evidence, Source
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers: sembrar via APIs publicas de Storage (FK-aware).
# ---------------------------------------------------------------------------


def _seed_source(
    storage: Storage,
    *,
    source_id: str,
    tenant_id: str,
    project_id: str,
) -> None:
    src = Source(
        source_id=source_id,
        kind="local_file",  # type: ignore[arg-type]
        content_hash="h" + source_id,
        locator={"path": f"/tmp/{source_id}"},
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-09-24T00:00:00Z",
        freshness="fresh",  # type: ignore[arg-type]
    )
    storage.register_source(tenant_id=tenant_id, project_id=project_id, source=src)


def _seed_entity(
    storage: Storage,
    *,
    entity_id: str,
    tenant_id: str,
    project_id: str,
    kind: str = "function",
) -> None:
    ent = Entity(entity_id=entity_id, kind=kind, stable_key=entity_id)
    storage.upsert_entity(tenant_id=tenant_id, project_id=project_id, entity=ent)


def _seed_claim(
    storage: Storage,
    *,
    tenant_id: str,
    project_id: str,
    claim_id: str,
    predicate: str,
    source_id: str,
    object_literal: object = "v",
) -> None:
    """Sembra entity + source + claim en orden (FK)."""
    _seed_entity(
        storage,
        entity_id="ent-" + claim_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    _seed_source(
        storage,
        source_id=source_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    claim = Claim(
        claim_id=claim_id,
        subject_entity_id="ent-" + claim_id,
        predicate=predicate,  # type: ignore[arg-type]
        object_literal=object_literal,
        source_id=source_id,
        evidence_ids=(),
        extraction_method="static_analysis",
        extractor_version="skillgraph/0.1.0",
        checked_at_revision="rev-1",
        stale=False,
    )
    storage.record_claim(tenant_id=tenant_id, project_id=project_id, claim=claim)


def _seed_evidence(
    storage: Storage,
    *,
    evidence_id: str,
    tenant_id: str,
    project_id: str,
    source_id: str,
    content: object = "evidence-body",
) -> None:
    _seed_source(
        storage,
        source_id=source_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    ev = Evidence(
        evidence_id=evidence_id,
        kind="test_evidence",
        content=content,
        source_id=source_id,
        observed_at="2026-09-24T00:00:00Z",
    )
    storage.record_evidence(tenant_id=tenant_id, project_id=project_id, evidence=ev)


def _seed_runtime_event(
    storage: Storage,
    *,
    event_id: str,
    tenant_id: str,
    project_id: str,
    run_id: str,
    resource_ref: str,
) -> None:
    storage.record_event(
        tenant_id=tenant_id,
        project_id=project_id,
        event_id=event_id,
        event_kind="NodeScheduled",
        run_id=run_id,
        resource_ref=resource_ref,
        payload={"seed": True},
    )


# ---------------------------------------------------------------------------
# Test 1: list_claims_by_predicate
# ---------------------------------------------------------------------------


class TestListClaimsByPredicate:
    """Cierra el sitio SQL de context_controller.py linea 297-303."""

    def test_returns_matching_claims_as_tuple_of_dicts(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_claim(
            storage,
            tenant_id="t1",
            project_id="p1",
            claim_id="c1",
            predicate="line_count",
            source_id="src-1",
        )
        _seed_claim(
            storage,
            tenant_id="t1",
            project_id="p1",
            claim_id="c2",
            predicate="line_count",
            source_id="src-2",
        )
        _seed_claim(
            storage,
            tenant_id="t1",
            project_id="p1",
            claim_id="c3",
            predicate="function_count",
            source_id="src-1",
        )

        result = storage.list_claims_by_predicate(
            tenant_id="t1", project_id="p1", predicate="line_count"
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        claim_ids = {row["claim_id"] for row in result}
        assert claim_ids == {"c1", "c2"}

    def test_isolation_by_tenant_and_project(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_claim(
            storage,
            tenant_id="t1",
            project_id="p1",
            claim_id="c1",
            predicate="line_count",
            source_id="src-1",
        )
        _seed_claim(
            storage,
            tenant_id="t2",
            project_id="p2",
            claim_id="c2",
            predicate="line_count",
            source_id="src-1",
        )

        result = storage.list_claims_by_predicate(
            tenant_id="t1", project_id="p1", predicate="line_count"
        )

        assert len(result) == 1
        assert result[0]["claim_id"] == "c1"
        assert result[0]["tenant_id"] == "t1"
        assert result[0]["project_id"] == "p1"

    def test_no_matches_returns_empty_tuple(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_claim(
            storage,
            tenant_id="t1",
            project_id="p1",
            claim_id="c1",
            predicate="line_count",
            source_id="src-1",
        )

        result = storage.list_claims_by_predicate(
            tenant_id="t1", project_id="p1", predicate="spec_revision"
        )

        assert result == ()

    def test_dict_has_expected_columns(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_claim(
            storage,
            tenant_id="t1",
            project_id="p1",
            claim_id="c1",
            predicate="line_count",
            source_id="src-1",
            object_literal={"k": "v"},
        )

        result = storage.list_claims_by_predicate(
            tenant_id="t1", project_id="p1", predicate="line_count"
        )

        assert len(result) == 1
        row = result[0]
        assert row["claim_id"] == "c1"
        assert row["predicate"] == "line_count"
        assert row["source_id"] == "src-1"
        assert row["stale"] == 0
        # object_literal_json es la columna real; el caller deserializa.
        assert json.loads(row["object_literal_json"]) == {"k": "v"}


# ---------------------------------------------------------------------------
# Test 2: list_evidences_for_source
# ---------------------------------------------------------------------------


class TestListEvidencesForSource:
    """Cierra el sitio SQL de context_controller.py linea 346-349."""

    def test_returns_evidences_for_source(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_evidence(
            storage,
            evidence_id="e1",
            tenant_id="t1",
            project_id="p1",
            source_id="src-1",
        )
        _seed_evidence(
            storage,
            evidence_id="e2",
            tenant_id="t1",
            project_id="p1",
            source_id="src-1",
        )
        _seed_evidence(
            storage,
            evidence_id="e3",
            tenant_id="t1",
            project_id="p1",
            source_id="src-2",
        )

        result = storage.list_evidences_for_source(source_id="src-1")

        assert isinstance(result, tuple)
        assert len(result) == 2
        evid_ids = {row["evidence_id"] for row in result}
        assert evid_ids == {"e1", "e2"}

    def test_unknown_source_returns_empty_tuple(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")

        result = storage.list_evidences_for_source(source_id="src-ghost")

        assert result == ()

    def test_dict_has_expected_columns(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_evidence(
            storage,
            evidence_id="e1",
            tenant_id="t1",
            project_id="p1",
            source_id="src-1",
            content={"observation": "x"},
        )

        result = storage.list_evidences_for_source(source_id="src-1")

        assert len(result) == 1
        row = result[0]
        assert row["evidence_id"] == "e1"
        assert row["source_id"] == "src-1"
        assert row["kind"] == "test_evidence"
        # content_json es la columna; el caller deserializa.
        assert json.loads(row["content_json"]) == {"observation": "x"}


# ---------------------------------------------------------------------------
# Test 3: list_resource_refs_for_run
# ---------------------------------------------------------------------------


class TestListResourceRefsForRun:
    """Cierra los sitios SQL de context_controller.py lineas 402-410 y
    413-421 (unificados en un solo metodo parametrizado por kind)."""

    def test_kind_claim_returns_claim_refs(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_runtime_event(
            storage,
            event_id="e1",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-1",
        )
        _seed_runtime_event(
            storage,
            event_id="e2",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-2",
        )
        _seed_runtime_event(
            storage,
            event_id="e3",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="evidence:e-1",
        )

        result = storage.list_resource_refs_for_run(
            tenant_id="t1", project_id="p1", run_id="r1", kind="claim"
        )

        assert isinstance(result, tuple)
        assert result == ("claim:c-1", "claim:c-2")

    def test_kind_evidence_returns_evidence_refs(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_runtime_event(
            storage,
            event_id="e1",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-1",
        )
        _seed_runtime_event(
            storage,
            event_id="e2",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="evidence:e-1",
        )

        result = storage.list_resource_refs_for_run(
            tenant_id="t1", project_id="p1", run_id="r1", kind="evidence"
        )

        assert result == ("evidence:e-1",)

    def test_distinct_and_ordered(self, tmp_path: pytest.TempPathFactory) -> None:
        """Refs duplicadas -> DISTINCT; orden por resource_ref ASC."""
        storage = Storage(tmp_path / "test.sqlite")
        # Mismo resource_ref en 2 eventos -> DISTINCT colapsa.
        _seed_runtime_event(
            storage,
            event_id="e1",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-1",
        )
        _seed_runtime_event(
            storage,
            event_id="e2",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-1",
        )
        _seed_runtime_event(
            storage,
            event_id="e3",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-2",
        )

        result = storage.list_resource_refs_for_run(
            tenant_id="t1", project_id="p1", run_id="r1", kind="claim"
        )

        assert result == ("claim:c-1", "claim:c-2")

    def test_isolation_by_run_id(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")
        _seed_runtime_event(
            storage,
            event_id="e1",
            tenant_id="t1",
            project_id="p1",
            run_id="r1",
            resource_ref="claim:c-1",
        )
        _seed_runtime_event(
            storage,
            event_id="e2",
            tenant_id="t1",
            project_id="p1",
            run_id="r2",
            resource_ref="claim:c-2",
        )

        result = storage.list_resource_refs_for_run(
            tenant_id="t1", project_id="p1", run_id="r1", kind="claim"
        )

        assert result == ("claim:c-1",)

    def test_no_events_returns_empty_tuple(self, tmp_path: pytest.TempPathFactory) -> None:
        storage = Storage(tmp_path / "test.sqlite")

        result = storage.list_resource_refs_for_run(
            tenant_id="t1", project_id="p1", run_id="r-ghost", kind="claim"
        )

        assert result == ()

    def test_invalid_kind_raises_validation(self, tmp_path: pytest.TempPathFactory) -> None:
        """Defensa: kind fuera de Literal['claim','evidence']."""
        storage = Storage(tmp_path / "test.sqlite")

        with pytest.raises(ValidationError):
            storage.list_resource_refs_for_run(
                tenant_id="t1",
                project_id="p1",
                run_id="r1",
                kind="handoff",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Test 4: no-regresion por introspeccion en context_controller
# ---------------------------------------------------------------------------


class TestContextControllerNoSqlDirect:
    """Verifica que context_controller.py NO contiene `_conn.execute` ni
    `cursor.execute` despues del refactor (cierre del H9-Coverage-11).

    Esto blinda una regresion tipica: alguien "deshace" la delegacion
    volviendo a abrir _conn directamente.
    """

    def test_context_controller_has_no_direct_conn_execute(self) -> None:
        import inspect

        from skillgraph.knowledge.context_controller import (
            ContextController,
            OutcomeTracer,
        )

        src_controller = inspect.getsource(ContextController)
        src_tracer = inspect.getsource(OutcomeTracer)
        combined = src_controller + "\n" + src_tracer

        # El patron `_conn.execute(` indica SQL directo (rompe la regla
        # "Storage encapsula SQL" introducida en H9-BSlice3).
        assert not re.search(r"_conn\.execute\s*\(", combined), (
            "context_controller.py todavia tiene `_conn.execute(` directo. "
            "Repositorio debe delegar en self.storage.<metodo>(...)."
        )
        assert not re.search(r"cursor\.execute\s*\(", combined), (
            "context_controller.py todavia usa `cursor.execute(`. "
            "Debe delegar en self.storage.<metodo>(...)."
        )

    def test_context_controller_uses_storage_public_api(self) -> None:
        """Verifica que el codigo llama a los 3 metodos nuevos de Storage."""
        import inspect

        from skillgraph.knowledge.context_controller import (
            ContextController,
            OutcomeTracer,
        )

        src_controller = inspect.getsource(ContextController)
        src_tracer = inspect.getsource(OutcomeTracer)
        combined = src_controller + "\n" + src_tracer

        assert "list_claims_by_predicate" in combined
        assert "list_evidences_for_source" in combined
        assert "list_resource_refs_for_run" in combined
