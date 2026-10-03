"""E1 Adapter real — HttpAgentAdapter con strategies Anthropic + OpenAI.

Cubre el derivado E1 del H9 addendum: adapter que invoca LLMs reales
via HTTP en lugar de leer fixtures desde disco.

Workflow SDDK: A-min (single apply, scope acotado a runtime/agent).

Pre-condiciones:
- AgentAdapter Protocol existe en skillgraph.runtime.agent.
- FakeAgentAdapter para tests deterministas.
- Handoff serializado de forma estable (context_hash) — el Adapter
  recibe el Handoff completo, lo proyecta a prompt del proveedor,
  y mapea respuesta a AgentResult.

Decisiones:
- Soporte 2 proveedores: Anthropic Messages API + OpenAI Chat Completions.
- Sin credenciales en código: leídas de env vars o via constructor.
- Timeouts configurables (default 30s read, 10s connect).
- Retries exponenciales con jitter (3 reintentos max).
- Tests integration con `respx` (mock HTTP transport-level).
- Failpoints para simular 429/500/timeout en tests deterministas.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

from skillgraph.core.errors import (
    NotFoundError,
    OutcomeInvalidError,
    ValidationError,
)
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.handoff import Handoff

# --- Failpoints (test-only, pero disponibles en produccion) ----------

_FAILPOINT_TIMEOUT = "SKILLGRAPH_FAILPOINT_HTTP_TIMEOUT"
_FAILPOINT_429 = "SKILLGRAPH_FAILPOINT_HTTP_429"
_FAILPOINT_500 = "SKILLGRAPH_FAILPOINT_HTTP_500"


class RetryableHttpStatus(Exception):
    """Status HTTP que merece retry (429 / 5xx). Senal interna del adapter."""

    code: str = "sg_http_retryable"


# Sentinel privado: marca que `_dispatch_response` debe atrapar el status
# para que el caller (invoke) aplique la politica de retry. No es una
# `SkillGraphError` porque el usuario nunca la ve cruda.


def _failpoint_active(name: str) -> bool:
    """Lee una variable de entorno como failpoint.

    Si la variable es "1" o "true" (case-insensitive), el failpoint
    esta activo. Usado por tests para simular condiciones adversas
    sin red real.
    """
    val = os.environ.get(name, "").strip().lower()
    return val in ("1", "true", "yes")


# --- Strategies -------------------------------------------------------

Provider = Literal["anthropic", "openai"]

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


@dataclass(frozen=True, slots=True)
class _ProviderConfig:
    """Configuracion inmutable de un proveedor."""

    provider: Provider
    api_key: str
    model: str
    base_url: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider not in ("anthropic", "openai"):
            raise ValidationError(f"provider invalido: {self.provider!r}")
        if not self.api_key:
            raise ValidationError(f"api_key requerida para provider={self.provider!r}")
        if not self.model:
            raise ValidationError(f"model requerido para provider={self.provider!r}")


def _config_from_env(provider: Provider, *, model: str | None = None) -> _ProviderConfig:
    """Lee configuracion del proveedor desde variables de entorno.

    Anthropic: ``ANTHROPIC_API_KEY`` (+ ``ANTHROPIC_MODEL`` opcional).
    OpenAI: ``OPENAI_API_KEY`` (+ ``OPENAI_MODEL`` opcional).
    Modelos default: ``claude-sonnet-4-6`` (Anthropic; sustituye al
    ``claude-3-5-sonnet-20241022`` retirado por Anthropic el 2025-10-28),
    ``gpt-4o-mini`` (OpenAI).
    """
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        # claude-3-5-sonnet-20241022 fue retirado por Anthropic el
        # 2025-10-28. Migramos al modelo estable actual. Si necesitas
        # un modelo especifico, sobreescribe via ANTHROPIC_MODEL o
        # el parametro ``model=``.
        default_model = "claude-sonnet-4-6"
        env_model = os.environ.get("ANTHROPIC_MODEL")
        return _ProviderConfig(
            provider="anthropic",
            api_key=api_key,
            model=model or env_model or default_model,
        )
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        default_model = "gpt-4o-mini"
        env_model = os.environ.get("OPENAI_MODEL")
        return _ProviderConfig(
            provider="openai",
            api_key=api_key,
            model=model or env_model or default_model,
        )
    raise ValidationError(f"provider desconocido: {provider!r}")


def _build_prompt(handoff: Handoff) -> str:
    """Proyecta un Handoff a un prompt textual.

    Serializacion estable (mismo input -> mismo output) para que el
    Adapter pueda deduplicar via el context_hash del Handoff.
    """
    parts: list[str] = []
    parts.append(f"# Handoff {handoff.identity.node_execution_id}")
    parts.append("")
    parts.append("## Identity")
    parts.append(f"- tenant: {handoff.identity.tenant_id}")
    parts.append(f"- project: {handoff.identity.project_id}")
    parts.append(f"- run: {handoff.identity.run_id}")
    parts.append(f"- attempt: {handoff.identity.attempt}")
    parts.append("")
    parts.append("## Behavior")
    parts.append(
        f"- {handoff.behavior.definition_kind}: "
        f"{handoff.behavior.definition_namespace}/{handoff.behavior.definition_name}"
        f"@v{handoff.behavior.definition_revision}"
    )
    parts.append("")
    parts.append("## Knowledge")
    parts.append(f"- recipe_ref: {handoff.knowledge.recipe_ref}")
    if handoff.knowledge.included:
        parts.append("- included:")
        for item in handoff.knowledge.included:
            parts.append(f"  - {item}")
    parts.append("")
    parts.append("## Execution")
    parts.append(f"- workspace: {handoff.execution.workspace_ref}")
    parts.append(f"- budget: {handoff.execution.budget}")
    parts.append("")
    parts.append("## Capabilities")
    # ── DEUDA CONOCIDA, DECIDIDA, MEDIDA. NO ES UN OLVIDO. ──
    #
    # `handoff.capabilities` puede contener `'stale'`, que NO es una
    # capability: es un valor de `FreshnessState`
    # (`core/runtime_types.py::FreshnessState`), o sea un estado de
    # frescura. Medido con Storage real y una Claim real
    # (`.pipelinek/b3_stale_measure.py`):
    #
    #     best_effort -> capabilities=('stale',)
    #     strict      -> StaleKnowledgeError (no hay handoff)
    #
    # O sea que este prompt puede emitir, literalmente:
    #
    #     ## Capabilities
    #     - stale
    #
    # que le dice al modelo que TIENE una capacidad llamada `stale`.
    # Eso es una afirmacion falsa en el prompt, y es lo que B3 vino a
    # arreglar en `graph_expansion`; aqui sigue en pie.
    #
    # LA DECISION (2026-10-03): se deja como esta. Sacarlo de
    # `capabilities` cambia `context_hash` de todo handoff que hoy lo
    # lleva, y el hash firmado es ruptura de datos, materia de B8. La
    # deuda queda escrita, no cerrada: es el mismo veredicto que B1 dio
    # a sus dos deudas, con el motivo por escrito.
    #
    # LO QUE NO SE AFIRMA: que el modelo lo interprete mal. Eso haria
    # falta un proveedor real, y B2 dejo escrito que la UAT con
    # proveedor NO se certifico. Lo que se afirma es lo comprobable: la
    # palabra llega, y llega bajo este encabezado.
    #
    # Si algun dia se mueve, el guard que lo vigila es
    # `tests/test_b3_capability_kernel.py::TestLaSenalDeFrescuraPorEl
    # CaminoQueSiLlega`, y su fallo dice que es un cambio de contrato.
    for cap in handoff.capabilities:
        parts.append(f"- {cap}")
    parts.append("")
    parts.append("## Task")
    parts.append("Produce a JSON object with `outcome` (string) and `result` (object).")
    parts.append("Respond ONLY with the JSON, no prose.")
    return "\n".join(parts)


def _parse_anthropic_response(body: dict[str, Any]) -> AgentResult:
    """Parsea la respuesta de Anthropic Messages API.

    Formato esperado:
        {
          "content": [{"type": "text", "text": "<json-as-string>"}],
          ...
        }
    """
    content = body.get("content")
    if not isinstance(content, list) or not content:
        raise OutcomeInvalidError(f"respuesta Anthropic sin content[] valido: {body!r}")
    first = content[0]
    if not isinstance(first, dict):
        raise OutcomeInvalidError(f"respuesta Anthropic content[0] no es dict: {first!r}")
    text = first.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise OutcomeInvalidError(f"respuesta Anthropic text vacio: {text!r}")
    return _parse_llm_text_as_agent_result(text, provider="anthropic")


def _parse_openai_response(body: dict[str, Any]) -> AgentResult:
    """Parsea la respuesta de OpenAI Chat Completions API.

    Formato esperado:
        {
          "choices": [{"message": {"content": "<json-as-string>"}, ...}],
          ...
        }
    """
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OutcomeInvalidError(f"respuesta OpenAI sin choices[] valido: {body!r}")
    first = choices[0]
    if not isinstance(first, dict):
        raise OutcomeInvalidError(f"respuesta OpenAI choices[0] no es dict: {first!r}")
    message = first.get("message", {})
    if not isinstance(message, dict):
        raise OutcomeInvalidError(f"respuesta OpenAI message no es dict: {message!r}")
    text = message.get("content", "")
    if not isinstance(text, str) or not text.strip():
        raise OutcomeInvalidError(f"respuesta OpenAI content vacio: {text!r}")
    return _parse_llm_text_as_agent_result(text, provider="openai")


def _parse_llm_text_as_agent_result(text: str, *, provider: Provider) -> AgentResult:
    """Parsea el texto del LLM como AgentResult.

    Acepta JSON puro o JSON envuelto en markdown fences (```json ... ```).
    Si el JSON es invalido, lanza OutcomeInvalidError.
    """
    cleaned = text.strip()
    # Strip markdown fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Drop first line (```json) and last line (```)
        cleaned = "\n".join(lines[1:-1]).strip() if len(lines) >= 3 else cleaned
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise OutcomeInvalidError(f"LLM ({provider}) devolvio JSON invalido: {cleaned!r}") from exc
    if not isinstance(payload, dict):
        raise OutcomeInvalidError(f"LLM ({provider}) JSON no es dict: {type(payload).__name__}")
    return AgentResult.from_fixture(payload)


class _Strategy(Protocol):
    """Contrato de estrategia por proveedor."""

    def build_request(self, prompt: str) -> tuple[str, dict[str, Any], dict[str, str]]:
        """Devuelve (url, json_body, headers) listos para httpx.post."""
        ...

    def parse_response(self, body: dict[str, Any]) -> AgentResult:
        """Parsea el body JSON de la respuesta."""
        ...


@dataclass(frozen=True, slots=True)
class _AnthropicStrategy:
    config: _ProviderConfig

    def build_request(self, prompt: str) -> tuple[str, dict[str, Any], dict[str, str]]:
        url = self.config.base_url or _ANTHROPIC_URL
        body = {
            "model": self.config.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        headers.update(self.config.extra_headers)
        return url, body, headers

    def parse_response(self, body: dict[str, Any]) -> AgentResult:
        return _parse_anthropic_response(body)


@dataclass(frozen=True, slots=True)
class _OpenAIStrategy:
    config: _ProviderConfig

    def build_request(self, prompt: str) -> tuple[str, dict[str, Any], dict[str, str]]:
        url = self.config.base_url or _OPENAI_URL
        body = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "authorization": f"Bearer {self.config.api_key}",
            "content-type": "application/json",
        }
        headers.update(self.config.extra_headers)
        return url, body, headers

    def parse_response(self, body: dict[str, Any]) -> AgentResult:
        return _parse_openai_response(body)


def _build_strategy(config: _ProviderConfig) -> _Strategy:
    if config.provider == "anthropic":
        return _AnthropicStrategy(config)
    if config.provider == "openai":
        return _OpenAIStrategy(config)
    raise ValidationError(f"provider no soportado: {config.provider!r}")


# --- Retry policy -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class _RetryPolicy:
    max_retries: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 8.0

    def sleep_seconds(self, attempt: int) -> float:
        """Backoff exponencial con jitter.

        ``attempt`` es 0-indexed: 0 -> primer reintento, etc.
        """
        exp = min(self.base_delay_s * (2**attempt), self.max_delay_s)
        jitter = random.uniform(0, 0.25 * exp)
        return exp + jitter


# --- Adapter ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpAgentAdapter:
    """Adapter HTTP real para Anthropic + OpenAI.

    Implementa el Protocol ``AgentAdapter`` de
    ``skillgraph.runtime.agent``. Reusar el Protocol existente
    (D-41) garantiza compatibilidad con RunController sin
    cambios adicionales.

    Las credenciales NUNCA se hardcodean: se leen de env vars
    (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``) o se pasan via
    constructor. Los tests usan ``respx`` para mockear HTTP a
    nivel de transport, sin red real.
    """

    provider: Provider
    api_key: str = field(repr=False)
    model: str = ""
    base_url: str = ""
    timeout_s: float = 30.0
    connect_timeout_s: float = 10.0
    max_retries: int = 3
    client: httpx.Client | None = None  # for tests (respx)
    _strategy: _Strategy | None = field(default=None, init=False, repr=False)
    _retry: _RetryPolicy | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.provider not in ("anthropic", "openai"):
            raise ValidationError(f"provider invalido: {self.provider!r}")
        if not self.api_key:
            raise ValidationError("api_key requerida (no se aceptan credenciales vacias)")
        model = self.model or _default_model(self.provider)
        config = _ProviderConfig(
            provider=self.provider,
            api_key=self.api_key,
            model=model,
            base_url=self.base_url,
        )
        # frozen dataclass: use object.__setattr__ for computed fields
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "_strategy", _build_strategy(config))
        object.__setattr__(
            self,
            "_retry",
            _RetryPolicy(max_retries=self.max_retries),
        )

    def __repr__(self) -> str:
        # api_key esta marcado repr=False, asi que el dataclass auto-generado
        # ya lo omite. Pero el cliente httpx en `client=None` puede contener
        # credenciales en headers por defecto; usamos repr explicito que solo
        # muestra lo seguro (provider, model, timeouts).
        return (
            f"HttpAgentAdapter(provider={self.provider!r}, "
            f"model={self.model!r}, timeout_s={self.timeout_s}, "
            f"max_retries={self.max_retries})"
        )

    def invoke(self, handoff: Handoff) -> AgentResult:
        """Invoca el LLM y devuelve el resultado mapeado.

        Side effects:
        - 0..N HTTP POSTs al endpoint del proveedor (con retries).
        - Posible lectura de failpoints del entorno.
        """
        assert self._strategy is not None  # post_init guarantees
        assert self._retry is not None

        if not isinstance(handoff, Handoff):
            raise ValidationError(f"handoff debe ser Handoff, recibio {type(handoff).__name__}")

        prompt = _build_prompt(handoff)
        url, body, headers = self._strategy.build_request(prompt)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._post_with_failpoints(url, body, headers)
                return self._dispatch_response(response)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self._retry.sleep_seconds(attempt))
                    continue
                raise NotFoundError(
                    f"HTTP timeout/network tras {attempt + 1} intentos: {exc}"
                ) from exc
            except RetryableHttpStatus as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self._retry.sleep_seconds(attempt))
                    continue
                raise NotFoundError(str(exc)) from exc

        # Defensive: should not reach here, but if retries exhausted without raise
        raise NotFoundError(f"retries exhausted: {last_exc}")

    def _dispatch_response(self, response: httpx.Response) -> AgentResult:
        """Decide la accion segun status_code. Lanza `RetryableHttpStatus` para 429/5xx."""
        if response.status_code == 200:
            return self._strategy.parse_response(response.json())  # type: ignore[union-attr]
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableHttpStatus(f"HTTP {response.status_code}: {response.text[:200]}")
        # Other 4xx: client error, no retry
        raise ValidationError(f"HTTP {response.status_code}: {response.text[:200]}")

    def _post_with_failpoints(
        self, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        """POST con failpoints para tests deterministas."""
        if _failpoint_active(_FAILPOINT_TIMEOUT):
            raise httpx.TimeoutException("failpoint: SKILLGRAPH_FAILPOINT_HTTP_TIMEOUT")
        if _failpoint_active(_FAILPOINT_429):
            return httpx.Response(429, text="rate limited (failpoint)")
        if _failpoint_active(_FAILPOINT_500):
            return httpx.Response(500, text="server error (failpoint)")

        if self.client is not None:
            return self.client.post(url, json=body, headers=headers)

        timeout = httpx.Timeout(self.timeout_s, connect=self.connect_timeout_s)
        with httpx.Client(timeout=timeout) as client:
            return client.post(url, json=body, headers=headers)


def _default_model(provider: Provider) -> str:
    if provider == "anthropic":
        # claude-3-5-sonnet-20241022 fue retirado el 2025-10-28.
        return "claude-sonnet-4-6"
    if provider == "openai":
        return "gpt-4o-mini"
    raise ValidationError(f"provider sin modelo default: {provider!r}")


def http_adapter_from_env(provider: Provider, *, model: str | None = None) -> HttpAgentAdapter:
    """Fabrica un HttpAgentAdapter desde variables de entorno.

    Conveniencia para CLI/scripts. Lanza ValidationError si las
    credenciales no estan en el entorno (no se aceptan defaults).
    """
    config = _config_from_env(provider, model=model)
    return HttpAgentAdapter(
        provider=config.provider,
        api_key=config.api_key,
        model=config.model,
    )


__all__ = [
    "HttpAgentAdapter",
    "Provider",
    "http_adapter_from_env",
]
