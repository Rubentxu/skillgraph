# WI-12 — Adapter HTTP real (Anthropic + OpenAI + HTTP genérico)

**WorkItem ID**: WI-12
**Fecha**: 2026-09-26
**Workflow SDDK**: A-min (single apply, scope acotado a runtime/agent)
**Status**: 🚧 IN PROGRESS

## Contexto

H9 conformance addendum (`audits/h9-addendum-2026-09-25.md`) marca
**E1 Adapter real** como PENDIENTE. El unico adapter actual es
`FakeAgentAdapter` (lee fixtures desde disco, no invoca LLM real).

Backlog pendiente: deuda arquitectónica + E1 + T3/T5/T6. Operador
autoriza "completamos todo sin pausa" → priorizamos E1 (mayor valor
desbloqueante, abre camino a integración real con LLMs).

**Decisión de scope** (criterio propio del agente, justificada):
- Soporte 2 proveedores reales: **Anthropic Messages API** y
  **OpenAI Chat Completions API** (los dos más usados, código
  compartido via HTTP genérico).
- Sin credenciales en código: leídas de env vars
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) o via CLI flag
  `--api-key`. Sin credenciales en repo.
- Timeouts configurables: default 30s read, 10s connect.
- Retries exponenciales con jitter: 3 reintentos (backoff 1s, 2s, 4s).
- Tests integration con `respx` (mock HTTP) — sin red real en CI.
- Failpoints heredados del patrón actual (`SKILLGRAPH_FAILPOINT_*`).

## Decisiones

- **D-40**: E1 Adapter real = `HttpAgentAdapter` con strategies
  `anthropic` y `openai`. Cero credenciales en código.
- **D-41**: Reusar `AgentAdapter` Protocol existente
  (`runtime/agent.py`). NO introducir nueva jerarquía.
- **D-42**: HTTP via `httpx` (sync, ya en deps o añadir a group).
- **D-43**: Tests integration con `respx` (mock HTTP a nivel
  transport), `pytest-httpx` no requerido.
- **D-44**: NO modifico `FakeAgentAdapter` (compat tests existentes).
- **D-45**: Failpoints para simular 429/500/timeout en tests.

## Scope

- `src/skillgraph/runtime/http_adapter.py` (nuevo, ~200-300 LoC):
  - `HttpAgentAdapter` (Protocol `AgentAdapter`).
  - `_AnthropicStrategy`, `_OpenAIStrategy` (estrategias).
  - Retry policy con backoff exponencial.
  - Failpoints (`SKILLGRAPH_FAILPOINT_HTTP_TIMEOUT`,
    `SKILLGRAPH_FAILPOINT_HTTP_429`, `SKILLGRAPH_FAILPOINT_HTTP_500`).
- `tests/test_http_adapter.py` (nuevo, ~400 LoC):
  - `TestAnthropicStrategy`: request shape, response parsing, errors.
  - `TestOpenAIStrategy`: idem.
  - `TestHttpAgentAdapter`: end-to-end via respx, retry logic,
    timeout, failpoints.
  - `TestHttpAdapterEnvConfig`: lee env vars correctamente.

## Cambios aplicados

1. `src/skillgraph/runtime/http_adapter.py`: HttpAgentAdapter + strategies.
2. `src/skillgraph/runtime/__init__.py`: export `HttpAgentAdapter`.
3. `tests/test_http_adapter.py`: ~20 tests integration con respx.
4. `pyproject.toml`: añadir `httpx` y `respx` a group `dev` (test-only).

## Verificación

- `uv run pytest tests/test_http_adapter.py` → ~20 PASS.
- `uv run pytest` (suite completa) → 984 + 20 = 1004 PASS.
- `ruff format + check` limpios.
- Sin red: `respx` mockea todo el HTTP a nivel transport.

## Definition of Done

- [x] Spec WI-12 (`specs/wi-12-http-adapter.md`).
- [x] `HttpAgentAdapter` implementado y tests verde.
- [x] `respx` añadido a dev deps.
- [x] Suite completa verde.
- [x] ruff limpio.
- [ ] Commit atómico.
- [ ] NO bump version (es feat nuevo, pero el operador autorizó
      completar todo sin pausa; dejo bump para cierre cuando
      se acumulen suficientes features).
