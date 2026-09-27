"""Tests para HttpAgentAdapter (E1 Adapter real — WI-12).

Usa ``respx`` para mockear HTTP a nivel de transport — sin red real.

Cubre:
- AnthropicStrategy: shape de request, parseo de response.
- OpenAIStrategy: idem.
- HttpAgentAdapter: end-to-end, retry logic, timeout, failpoints.
- http_adapter_from_env: lee env vars correctamente.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from skillgraph.core.errors import (
    NotFoundError,
    OutcomeInvalidError,
    ValidationError,
)
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)
from skillgraph.runtime.http_adapter import (
    _ANTHROPIC_URL,
    _OPENAI_URL,
    HttpAgentAdapter,
    http_adapter_from_env,
)

# --- Helpers ----------------------------------------------------------


def _handoff() -> Handoff:
    """Handoff minimo valido para tests."""
    return Handoff(
        identity=HandoffIdentity(
            tenant_id="t-1",
            project_id="p-1",
            run_id="r-1",
            node_execution_id="ne-1",
            attempt=1,
        ),
        behavior=HandoffBehavior(
            definition_kind="ActionNode",
            definition_name="n-1",
            definition_namespace="ns",
            definition_revision=1,
            api_version="v1",
        ),
        knowledge=HandoffKnowledge(recipe_ref="r-1"),
        execution=HandoffExecution(
            workspace_ref="/tmp",
            source_revision="abc",
            budget={"tokens": 1024},
        ),
        expected_result="outcome",
        capabilities=("c-1",),
    )


def _anthropic_response(outcome: str = "ok", result: dict | None = None) -> dict:
    return {
        "id": "msg_01",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": json.dumps({"outcome": outcome, "result": result or {}}),
            }
        ],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }


def _openai_response(outcome: str = "ok", result: dict | None = None) -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"outcome": outcome, "result": result or {}}),
                },
                "finish_reason": "stop",
            }
        ],
        "model": "gpt-4o-mini",
    }


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0))


# --- TestAnthropicStrategy --------------------------------------------


class TestAnthropicStrategy:
    """WI-12: Anthropic strategy request shape + response parsing."""

    def test_request_shape_contains_required_fields(self) -> None:
        from skillgraph.runtime.http_adapter import _AnthropicStrategy, _ProviderConfig

        cfg = _ProviderConfig(provider="anthropic", api_key="test-key", model="claude-sonnet-4-6")
        strat = _AnthropicStrategy(cfg)
        url, body, headers = strat.build_request("hello world")

        assert url == _ANTHROPIC_URL
        assert body["model"] == "claude-sonnet-4-6"
        assert body["max_tokens"] == 1024
        assert body["messages"] == [{"role": "user", "content": "hello world"}]
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

    def test_response_parsing_valid_json(self) -> None:
        from skillgraph.runtime.http_adapter import _AnthropicStrategy, _ProviderConfig

        strat = _AnthropicStrategy(
            _ProviderConfig(provider="anthropic", api_key="k", model="claude-sonnet-4-6")
        )
        result = strat.parse_response(_anthropic_response("ok", {"score": 0.9}))
        assert isinstance(result, AgentResult)
        assert result.outcome == "ok"
        assert result.result == {"score": 0.9}

    def test_response_parsing_with_markdown_fences(self) -> None:
        from skillgraph.runtime.http_adapter import _AnthropicStrategy, _ProviderConfig

        body = {
            "content": [
                {
                    "type": "text",
                    "text": "```json\n"
                    + json.dumps({"outcome": "ok", "result": {"x": 1}})
                    + "\n```",
                }
            ]
        }
        strat = _AnthropicStrategy(_ProviderConfig(provider="anthropic", api_key="k", model="m"))
        result = strat.parse_response(body)
        assert result.outcome == "ok"
        assert result.result == {"x": 1}

    def test_response_parsing_invalid_json_raises(self) -> None:
        from skillgraph.runtime.http_adapter import _AnthropicStrategy, _ProviderConfig

        body = {"content": [{"type": "text", "text": "not json"}]}
        strat = _AnthropicStrategy(_ProviderConfig(provider="anthropic", api_key="k", model="m"))
        with pytest.raises(OutcomeInvalidError, match="JSON invalido"):
            strat.parse_response(body)

    def test_response_parsing_empty_content_raises(self) -> None:
        from skillgraph.runtime.http_adapter import _AnthropicStrategy, _ProviderConfig

        strat = _AnthropicStrategy(_ProviderConfig(provider="anthropic", api_key="k", model="m"))
        with pytest.raises(OutcomeInvalidError):
            strat.parse_response({"content": []})


# --- TestOpenAIStrategy -----------------------------------------------


class TestOpenAIStrategy:
    """WI-12: OpenAI strategy request shape + response parsing."""

    def test_request_shape_contains_required_fields(self) -> None:
        from skillgraph.runtime.http_adapter import _OpenAIStrategy, _ProviderConfig

        cfg = _ProviderConfig(provider="openai", api_key="sk-test", model="gpt-4o-mini")
        strat = _OpenAIStrategy(cfg)
        url, body, headers = strat.build_request("hello")

        assert url == _OPENAI_URL
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert headers["authorization"] == "Bearer sk-test"
        assert headers["content-type"] == "application/json"

    def test_response_parsing_valid_json(self) -> None:
        from skillgraph.runtime.http_adapter import _OpenAIStrategy, _ProviderConfig

        strat = _OpenAIStrategy(_ProviderConfig(provider="openai", api_key="k", model="m"))
        result = strat.parse_response(_openai_response("done", {"answer": 42}))
        assert result.outcome == "done"
        assert result.result == {"answer": 42}

    def test_response_parsing_empty_choices_raises(self) -> None:
        from skillgraph.runtime.http_adapter import _OpenAIStrategy, _ProviderConfig

        strat = _OpenAIStrategy(_ProviderConfig(provider="openai", api_key="k", model="m"))
        with pytest.raises(OutcomeInvalidError):
            strat.parse_response({"choices": []})


# --- TestHttpAgentAdapter ---------------------------------------------


class TestHttpAgentAdapter:
    """WI-12: HttpAgentAdapter end-to-end via respx."""

    def test_validation_empty_api_key(self) -> None:
        with pytest.raises(ValidationError, match="api_key requerida"):
            HttpAgentAdapter(provider="anthropic", api_key="")

    def test_validation_unknown_provider(self) -> None:
        with pytest.raises(ValidationError, match="provider invalido"):
            HttpAgentAdapter(provider="unknown_llm", api_key="k")  # type: ignore[arg-type]

    def test_default_model_anthropic(self) -> None:
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k")
        assert adapter.model == "claude-sonnet-4-6"

    def test_default_model_openai(self) -> None:
        adapter = HttpAgentAdapter(provider="openai", api_key="k")
        assert adapter.model == "gpt-4o-mini"

    def test_default_model_anthropic_not_deprecated(self) -> None:
        """QW-A: el default Anthropic NO debe ser un modelo retirado por
        el proveedor. ``claude-3-5-sonnet-20241022`` fue retirado por
        Anthropic el 2025-10-28. Si este test falla, hay que migrar
        el default de ``_default_model()`` al modelo actual.
        """
        from skillgraph.runtime.http_adapter import _default_model

        # Lista negra explicita de modelos retirados conocidos. Cualquier
        # match debe bloquearse. Si Anthropic retira mas modelos, an
        # adirlos aqui.
        known_retired = {
            "claude-3-5-sonnet-20241022",  # Anthropic shutdown 2025-10-28
            "claude-3-5-sonnet-20240620",  # shutdown 2025-08-13
            "claude-3-opus-20240229",  # shutdown 2025-07-21
        }
        current = _default_model("anthropic")
        assert current not in known_retired, (
            f"Default Anthropic {current!r} es un modelo retirado. Migrar a un modelo actual."
        )

    @respx.mock
    def test_anthropic_end_to_end_success(self, client: httpx.Client) -> None:
        respx.post(_ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, json=_anthropic_response("ok", {"v": 1}))
        )
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client)
        result = adapter.invoke(_handoff())
        assert result.outcome == "ok"
        assert result.result == {"v": 1}
        assert respx.calls.call_count == 1

    @respx.mock
    def test_openai_end_to_end_success(self, client: httpx.Client) -> None:
        respx.post(_OPENAI_URL).mock(
            return_value=httpx.Response(200, json=_openai_response("done", {"v": 2}))
        )
        adapter = HttpAgentAdapter(provider="openai", api_key="k", client=client)
        result = adapter.invoke(_handoff())
        assert result.outcome == "done"
        assert result.result == {"v": 2}

    @respx.mock
    def test_retry_on_429(self, client: httpx.Client) -> None:
        """429 dispara retry; 200 al segundo intento -> exito."""
        route = respx.post(_ANTHROPIC_URL).mock(
            side_effect=[
                httpx.Response(429, text="rate limited"),
                httpx.Response(200, json=_anthropic_response("ok")),
            ]
        )
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client, max_retries=3)
        result = adapter.invoke(_handoff())
        assert result.outcome == "ok"
        assert route.call_count == 2

    @respx.mock
    def test_retry_on_500(self, client: httpx.Client) -> None:
        """500 dispara retry; 200 al tercer intento -> exito."""
        route = respx.post(_ANTHROPIC_URL).mock(
            side_effect=[
                httpx.Response(500, text="server error"),
                httpx.Response(500, text="server error"),
                httpx.Response(200, json=_anthropic_response("ok")),
            ]
        )
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client, max_retries=3)
        result = adapter.invoke(_handoff())
        assert result.outcome == "ok"
        assert route.call_count == 3

    @respx.mock
    def test_retry_exhausted_raises(self, client: httpx.Client) -> None:
        """429 persistente hasta max_retries -> NotFoundError."""
        respx.post(_ANTHROPIC_URL).mock(return_value=httpx.Response(429, text="limit"))
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client, max_retries=2)
        with pytest.raises(NotFoundError, match="HTTP 429"):
            adapter.invoke(_handoff())

    @respx.mock
    def test_4xx_no_retry(self, client: httpx.Client) -> None:
        """400 (client error) NO dispara retry -> ValidationError inmediato."""
        route = respx.post(_ANTHROPIC_URL).mock(
            return_value=httpx.Response(400, text="bad request")
        )
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client, max_retries=3)
        with pytest.raises(ValidationError, match="HTTP 400"):
            adapter.invoke(_handoff())
        assert route.call_count == 1

    @respx.mock
    def test_failpoint_timeout(self, client: httpx.Client, monkeypatch) -> None:
        """SKILLGRAPH_FAILPOINT_HTTP_TIMEOUT -> NotFoundError tras retries."""
        monkeypatch.setenv("SKILLGRAPH_FAILPOINT_HTTP_TIMEOUT", "1")
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client, max_retries=1)
        with pytest.raises(NotFoundError, match="HTTP timeout"):
            adapter.invoke(_handoff())

    @respx.mock
    def test_failpoint_500(self, client: httpx.Client, monkeypatch) -> None:
        """SKILLGRAPH_FAILPOINT_HTTP_500 -> 500 -> retry path."""
        monkeypatch.setenv("SKILLGRAPH_FAILPOINT_HTTP_500", "1")
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k", client=client, max_retries=1)
        with pytest.raises(NotFoundError, match="HTTP 500"):
            adapter.invoke(_handoff())

    def test_invoke_rejects_non_handoff(self) -> None:
        adapter = HttpAgentAdapter(provider="anthropic", api_key="k")
        with pytest.raises(ValidationError, match="handoff debe ser Handoff"):
            adapter.invoke("not a handoff")  # type: ignore[arg-type]


# --- TestHttpAdapterEnvConfig -----------------------------------------


class TestHttpAdapterEnvConfig:
    """WI-12: http_adapter_from_env lee env vars correctamente."""

    def test_anthropic_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        adapter = http_adapter_from_env("anthropic")
        assert adapter.provider == "anthropic"
        assert adapter.api_key == "sk-ant-test"
        assert adapter.model == "claude-sonnet-4-6"

    def test_anthropic_model_override(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus-20240229")
        adapter = http_adapter_from_env("anthropic")
        assert adapter.model == "claude-3-opus-20240229"

    def test_openai_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        adapter = http_adapter_from_env("openai")
        assert adapter.provider == "openai"
        assert adapter.api_key == "sk-openai-test"
        assert adapter.model == "gpt-4o-mini"

    def test_missing_api_key_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValidationError, match="api_key requerida"):
            http_adapter_from_env("anthropic")
