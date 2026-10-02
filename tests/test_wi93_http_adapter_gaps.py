"""WI-93 — las ramas que dejaban `http_adapter.py` por debajo de su suelo.

Por que este fichero existe
---------------------------
AGENTS.md §6.3 pone un suelo del 90 % a los modulos del core, y
`runtime/http_adapter.py` es un modulo del core. Medido con la receta
correcta (`scripts/coverage.sh`, que ve el subproceso), mide **88.04 %**:
19 sentencias y 15 ramas sin cubrir.

Ninguna de esas ramas es inalcanzable: son guardas de entrada y de
respuesta malformada, y el modulo ya trae failpoints y un `client`
inyectable precisamente para poder probarlas sin red. Es exactamente el
tipo de hueco que el suelo del core existe para tapar, y que el suelo
del CLI excusa ("lo que falta son ramas de error que ya cubre
integracion") pero aqui no cubre nadie: la integracion con un proveedor
real no se ha ejecutado nunca porque no hay credenciales.

Que este fichero NO hace
------------------------
No prueba que Anthropic ni OpenAI respondan. Eso no se puede sin
credenciales y sigue sin estar probado, y el registro de H9 lo dice
expresamente. Lo que se prueba aqui es que el adaptador RECHAZA bien lo
que no deberia aceptar, que es la mitad del contrato que si es local.
"""

from __future__ import annotations

import json

import httpx
import pytest

from skillgraph.core.errors import (
    NotFoundError,
    OutcomeInvalidError,
    ValidationError,
)
from skillgraph.runtime.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)
from skillgraph.runtime.http_adapter import (
    _FAILPOINT_429,
    _FAILPOINT_TIMEOUT,
    HttpAgentAdapter,
    _build_prompt,
    _build_strategy,
    _config_from_env,
    _default_model,
    _parse_anthropic_response,
    _parse_llm_text_as_agent_result,
    _parse_openai_response,
    _ProviderConfig,
    _RetryPolicy,
)


def _handoff(*, included: tuple[str, ...] = ()) -> Handoff:
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
        knowledge=HandoffKnowledge(recipe_ref="r-1", included=included),
        execution=HandoffExecution(
            workspace_ref="/tmp",
            source_revision="abc",
            budget={"tokens": 1024},
        ),
        expected_result="outcome",
        capabilities=("c-1",),
    )


def _adapter(**kw) -> HttpAgentAdapter:
    return HttpAgentAdapter(provider="anthropic", api_key="k-test", **kw)


def _sin_dormir(monkeypatch: pytest.MonkeyPatch) -> None:
    """El backoff real son segundos; aqui son irrelevantes."""
    monkeypatch.setattr("skillgraph.runtime.http_adapter.time.sleep", lambda _s: None)


# --- Config: las guardas de __post_init__ y el provider desconocido ---


class TestLaConfigRechazaLoQueNoDebeAceptar:
    def test_proveedor_invalido(self) -> None:
        with pytest.raises(ValidationError, match="provider invalido"):
            _ProviderConfig(provider="gemini", api_key="k", model="m")  # type: ignore[arg-type]

    def test_api_key_requerida(self) -> None:
        with pytest.raises(ValidationError, match="api_key requerida"):
            _ProviderConfig(provider="openai", api_key="", model="m")

    def test_model_requerido(self) -> None:
        with pytest.raises(ValidationError, match="model requerido"):
            _ProviderConfig(provider="openai", api_key="k", model="")

    def test_el_adaptador_tambien_rechaza_proveedor_invalido(self) -> None:
        with pytest.raises(ValidationError, match="provider invalido"):
            HttpAgentAdapter(provider="gemini", api_key="k")  # type: ignore[arg-type]

    def test_provider_desconocido_desde_entorno(self) -> None:
        with pytest.raises(ValidationError, match="provider desconocido"):
            _config_from_env("gemini")  # type: ignore[arg-type]

    def test_provider_sin_modelo_default(self) -> None:
        with pytest.raises(ValidationError, match="sin modelo default"):
            _default_model("gemini")  # type: ignore[arg-type]

    def test_estrategia_para_proveedor_no_soportado(self) -> None:
        """`_build_strategy` tiene una tercera salida que la config
        nunca alcanza, porque `__post_init__` ya filtra. Se prueba
        forzando el campo, que es lo unico que puede llegar ahi."""
        config = _ProviderConfig(provider="openai", api_key="k", model="m")
        object.__setattr__(config, "provider", "gemini")
        with pytest.raises(ValidationError, match="provider no soportado"):
            _build_strategy(config)


# --- El prompt: la rama de knowledge.included no se ejercitaba ---


class TestElPromptProyectaElConocimientoIncluido:
    def test_incluye_los_items(self) -> None:
        prompt = _build_prompt(_handoff(included=("k-1", "k-2")))
        assert "- included:" in prompt
        assert "  - k-1" in prompt
        assert "  - k-2" in prompt

    def test_sin_conocimiento_no_inventa_la_seccion(self) -> None:
        prompt = _build_prompt(_handoff())
        assert "- included:" not in prompt
        assert "- recipe_ref: r-1" in prompt


# --- Respuestas malformadas: las guardas de los dos parsers ---


class TestAnthropicRechazaRespuestasMalformadas:
    def test_content_no_es_lista(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="sin content"):
            _parse_anthropic_response({"content": "texto"})

    def test_content_vacio(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="sin content"):
            _parse_anthropic_response({"content": []})

    def test_content0_no_es_dict(self) -> None:
        with pytest.raises(OutcomeInvalidError, match=r"content\[0\] no es dict"):
            _parse_anthropic_response({"content": ["texto plano"]})

    def test_text_no_es_str(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="text vacio"):
            _parse_anthropic_response({"content": [{"type": "text", "text": 42}]})

    def test_text_en_blanco(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="text vacio"):
            _parse_anthropic_response({"content": [{"type": "text", "text": "   "}]})


class TestOpenAIRechazaRespuestasMalformadas:
    def test_choices_no_es_lista(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="sin choices"):
            _parse_openai_response({"choices": {}})

    def test_choices_vacio(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="sin choices"):
            _parse_openai_response({"choices": []})

    def test_choices0_no_es_dict(self) -> None:
        with pytest.raises(OutcomeInvalidError, match=r"choices\[0\] no es dict"):
            _parse_openai_response({"choices": ["texto"]})

    def test_message_no_es_dict(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="message no es dict"):
            _parse_openai_response({"choices": [{"message": "texto"}]})

    def test_content_no_es_str(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="content vacio"):
            _parse_openai_response({"choices": [{"message": {"content": None}}]})

    def test_content_en_blanco(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="content vacio"):
            _parse_openai_response({"choices": [{"message": {"content": " "}}]})


class TestElTextoDelLlmSeParseaOseRechaza:
    def test_json_valido(self) -> None:
        r = _parse_llm_text_as_agent_result(
            json.dumps({"outcome": "ok", "result": {}}), provider="anthropic"
        )
        assert r.outcome == "ok"

    def test_envuelto_en_fences_de_markdown(self) -> None:
        crudo = "```json\n" + json.dumps({"outcome": "ok", "result": {}}) + "\n```"
        r = _parse_llm_text_as_agent_result(crudo, provider="openai")
        assert r.outcome == "ok"

    def test_json_invalido(self) -> None:
        with pytest.raises(OutcomeInvalidError, match="JSON invalido"):
            _parse_llm_text_as_agent_result("no soy json", provider="anthropic")

    def test_json_valido_pero_no_es_dict(self) -> None:
        """La guarda «JSON no es dict»: una lista es JSON valido."""
        with pytest.raises(OutcomeInvalidError, match="JSON no es dict"):
            _parse_llm_text_as_agent_result("[1, 2, 3]", provider="openai")


# --- Reintentos agotados: las dos rutas que acaban en NotFoundError ---


class TestReintentosAgotados:
    def test_timeout_agotado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_FAILPOINT_TIMEOUT, "1")
        _sin_dormir(monkeypatch)
        with pytest.raises(NotFoundError, match="timeout/network"):
            _adapter(max_retries=1).invoke(_handoff())

    def test_429_agotado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_FAILPOINT_429, "1")
        _sin_dormir(monkeypatch)
        with pytest.raises(NotFoundError, match="429"):
            _adapter(max_retries=1).invoke(_handoff())


class TestElBackoffCreceYEstaAcotado:
    def test_el_reparto_va_de_exp_a_1_25_exp(self) -> None:
        """La implementacion es `exp = min(base * 2**attempt, max)` y
        luego suma `jitter = uniform(0, 0.25 * exp)`.

        La primera version de este test afirmaba `sleep_seconds(0) <=
        base_delay_s`, que es FALSO: el jitter es aditivo, asi que el
        primer reintento cae en `(1.0, 1.25]`. La asercion estaba mal,
        no el codigo, y por eso lo que se corrige es la asercion.
        """
        politica = _RetryPolicy(max_retries=6, base_delay_s=1.0, max_delay_s=8.0)
        for attempt in range(7):
            exp = min(1.0 * 2**attempt, 8.0)
            resultado = politica.sleep_seconds(attempt)
            assert exp <= resultado <= 1.25 * exp + 1e-9, (
                f"attempt={attempt}: {resultado} fuera de [{exp}, {1.25 * exp}]"
            )

    def test_nunca_supera_el_tope_por_jitter(self) -> None:
        politica = _RetryPolicy(max_retries=20, base_delay_s=1.0, max_delay_s=8.0)
        for attempt in range(20):
            assert politica.sleep_seconds(attempt) <= 8.0 * 1.25

    def test_es_un_float(self) -> None:
        assert isinstance(_RetryPolicy().sleep_seconds(0), float)


# --- El cliente por defecto: la rama httpx.Timeout sin client inyectado ---


class TestElPostSinClienteInyectadoConstruyeSuTimeout:
    def test_usa_el_timeout_configurado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Con `client` inyectado (respx) esta rama no se ejecuta nunca:
        todos los tests de red la esquivan, y la de produccion es justo
        la que construye su propio `httpx.Timeout`."""
        vistos: list[httpx.Timeout] = []

        class _Falso(httpx.Client):
            def __init__(self, **kw) -> None:
                vistos.append(kw["timeout"])
                super().__init__(**kw)

            def post(self, *a, **kw):  # type: ignore[override]
                return httpx.Response(
                    200,
                    json={"content": [{"type": "text", "text": '{"outcome":"ok","result":{}}'}]},
                )

        monkeypatch.setattr("skillgraph.runtime.http_adapter.httpx.Client", _Falso)
        adaptador = _adapter(connect_timeout_s=3.5)
        resultado = adaptador.invoke(_handoff())

        assert resultado.outcome == "ok"
        assert vistos, "no se llego a construir ningun httpx.Client"
        assert vistos[0].connect == 3.5
