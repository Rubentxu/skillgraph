"""Tests del AgentAdapter (Etapa 2 / S3).

Cobertura:
- AgentResult valida la estructura minima (outcome, result dict).
- FakeAgentAdapter busca fixtures en orden razonable y NotFoundError
  si no encuentra ninguna.
- FakeAgentAdapter lee JSON y parsea resultado correctamente.
- RecordingAdapter envuelve sin alterar el resultado.
- UAT-14: el Adapter NO se importa/ejecuta automaticamente.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgraph.agent import (
    AgentResult,
    FakeAgentAdapter,
    RecordingAdapter,
)
from skillgraph.errors import NotFoundError, ValidationError
from tests.test_handoff import _handoff


class TestAgentResult:
    def test_minimal_valid_result(self) -> None:
        r = AgentResult.from_fixture({"outcome": "ok", "result": {}})
        assert r.outcome == "ok"
        assert r.result == {}
        assert r.evidence_ref is None

    def test_with_evidence_ref(self) -> None:
        r = AgentResult.from_fixture({"outcome": "ok", "result": {"x": 1}, "evidence_ref": "ev-1"})
        assert r.evidence_ref == "ev-1"

    @pytest.mark.parametrize(
        "payload, needle",
        [
            ({"result": {}}, "outcome"),
            ({"outcome": 1, "result": {}}, "outcome"),
            ({"outcome": "ok"}, "result"),
            ({"outcome": "ok", "result": []}, "result"),
            ({"outcome": "ok", "result": {}, "evidence_ref": 7}, "evidence_ref"),
            ("not a dict", "dict"),
        ],
    )
    def test_invalid_payload_rejected(self, payload: object, needle: str) -> None:
        with pytest.raises(ValidationError, match=needle):
            AgentResult.from_fixture(payload)  # type: ignore[arg-type]


class TestFakeAgentAdapter:
    @pytest.fixture
    def fixtures_root(self, tmp_path: Path) -> Path:
        d = tmp_path / "agents"
        d.mkdir()
        return d

    def test_loads_fixture_by_node_execution_id(self, fixtures_root: Path) -> None:
        target = fixtures_root / "t" / "p" / "ne-1.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"outcome": "selected", "result": {"a": 1}}))
        ad = FakeAgentAdapter(fixtures_root)
        h = _handoff()  # tenant=t, project=p, node_execution_id=ne-1
        r = ad.invoke(h)
        assert r.outcome == "selected"
        assert r.result == {"a": 1}

    def test_loads_fixture_by_definition_name(self, fixtures_root: Path) -> None:
        target = fixtures_root / "t" / "p" / "act.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"outcome": "trans-a", "result": {}}))
        ad = FakeAgentAdapter(fixtures_root)
        h = _handoff()  # definition_name="act"
        r = ad.invoke(h)
        assert r.outcome == "trans-a"

    def test_loads_fixture_by_namespace_and_name(self, fixtures_root: Path) -> None:
        target = fixtures_root / "shared" / "act.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"outcome": "trans-b", "result": {}}))
        ad = FakeAgentAdapter(fixtures_root)
        h = _handoff()
        r = ad.invoke(h)
        assert r.outcome == "trans-b"

    def test_missing_fixture_raises_not_found(self, fixtures_root: Path) -> None:
        ad = FakeAgentAdapter(fixtures_root)
        h = _handoff()
        with pytest.raises(NotFoundError, match="fixture de agente no encontrada"):
            ad.invoke(h)

    def test_invalid_fixture_json_raises_validation(self, fixtures_root: Path) -> None:
        target = fixtures_root / "t" / "p" / "ne-1.json"
        target.parent.mkdir(parents=True)
        target.write_text("{ this is not valid JSON")
        ad = FakeAgentAdapter(fixtures_root)
        h = _handoff()
        with pytest.raises(ValidationError, match="fixture invalida"):
            ad.invoke(h)

    def test_fixture_with_invalid_payload_raises_validation(self, fixtures_root: Path) -> None:
        target = fixtures_root / "t" / "p" / "ne-1.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"outcome": "ok"}))  # falta result
        ad = FakeAgentAdapter(fixtures_root)
        h = _handoff()
        with pytest.raises(ValidationError, match="result"):
            ad.invoke(h)


class TestRecordingAdapter:
    @pytest.fixture
    def fixtures_root(self, tmp_path: Path) -> Path:
        d = tmp_path / "agents"
        d.mkdir()
        return d

    def test_records_each_invocation(self, fixtures_root: Path) -> None:
        target = fixtures_root / "shared" / "act.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"outcome": "ok", "result": {}}))
        fake = FakeAgentAdapter(fixtures_root)
        rec = RecordingAdapter(fake)
        h1 = _handoff()
        h2 = _handoff(
            identity=_handoff().identity.__class__(
                tenant_id="t",
                project_id="p",
                run_id="r-2",
                node_execution_id="ne-2",
                attempt=1,
            )
        )
        rec.invoke(h1)
        rec.invoke(h2)
        assert len(rec) == 2
        assert rec.calls[0].identity.node_execution_id == "ne-1"
        assert rec.calls[1].identity.node_execution_id == "ne-2"

    def test_does_not_alter_result(self, fixtures_root: Path) -> None:
        target = fixtures_root / "shared" / "act.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"outcome": "ok", "result": {"x": 42}}))
        fake = FakeAgentAdapter(fixtures_root)
        rec = RecordingAdapter(fake)
        r = rec.invoke(_handoff())
        assert r.outcome == "ok"
        assert r.result == {"x": 42}
