"""Tests del helper `_build_adapter` para `sg run`.

WI-13: CLI wiring del HttpAgentAdapter en `cmd_run`. El helper resuelve
`--adapter {fake,http}` y construye el adapter correspondiente leyendo
variables de entorno para el caso HTTP.

Cobertura:
- TestAdapterCliBuildFake: caso default (fake) y explicit fake.
- TestAdapterCliBuildHttp: caso http con env (anthropic, openai) y
  override de timeout/modelo.
- TestAdapterCliBuildHttpMissingKey: error tipado si falta la API key.
- TestAdapterCliBuildRejectsInvalid: coverage del path default por si
  se introduce un valor fuera de {fake, http}.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from skillgraph.cli.commands.run import _build_adapter
from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.runtime.agent import FakeAgentAdapter

# ---------------------------------------------------------------------------
# TestAdapterCliBuildFake
# ---------------------------------------------------------------------------


class TestAdapterCliBuildFake:
    """Caso default: FakeAgentAdapter."""

    def test_returns_fake_adapter_when_kind_missing(self, tmp_path: Path) -> None:
        """Si args no tiene atributo `adapter`, devuelve FakeAgentAdapter."""
        args = argparse.Namespace()  # sin atributo adapter
        adapter = _build_adapter(args, tmp_path)
        assert isinstance(adapter, FakeAgentAdapter)

    def test_returns_fake_adapter_when_kind_is_fake(self, tmp_path: Path) -> None:
        """Si args.adapter == 'fake' (default), devuelve FakeAgentAdapter."""
        args = argparse.Namespace(adapter="fake")
        adapter = _build_adapter(args, tmp_path)
        assert isinstance(adapter, FakeAgentAdapter)


# ---------------------------------------------------------------------------
# TestAdapterCliBuildHttp
# ---------------------------------------------------------------------------


class TestAdapterCliBuildHttp:
    """Caso http: HttpAgentAdapter con API key del entorno."""

    def test_anthropic_provider_reads_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Con ANTHROPIC_API_KEY y --adapter=http --llm-provider=anthropic,
        construye HttpAgentAdapter con provider=anthropic."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
        args = argparse.Namespace(
            adapter="http",
            llm_provider="anthropic",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        adapter = _build_adapter(args, tmp_path)
        # El HttpAgentAdapter no es FakeAgentAdapter.
        assert not isinstance(adapter, FakeAgentAdapter)
        assert adapter.provider == "anthropic"
        assert adapter.api_key == "sk-ant-test-12345"

    def test_openai_provider_reads_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Con OPENAI_API_KEY y --adapter=http --llm-provider=openai,
        construye HttpAgentAdapter con provider=openai."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-67890")
        args = argparse.Namespace(
            adapter="http",
            llm_provider="openai",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        adapter = _build_adapter(args, tmp_path)
        assert adapter.provider == "openai"
        assert adapter.api_key == "sk-openai-test-67890"

    def test_custom_model_is_honored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--llm-model=claude-opus-4-20250514 sobrescribe el default."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
        args = argparse.Namespace(
            adapter="http",
            llm_provider="anthropic",
            llm_model="claude-opus-4-20250514",
            llm_timeout_s=30.0,
        )
        adapter = _build_adapter(args, tmp_path)
        assert adapter.model == "claude-opus-4-20250514"

    def test_custom_timeout_is_honored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--llm-timeout-s=5.0 sobrescribe el default 30.0."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
        args = argparse.Namespace(
            adapter="http",
            llm_provider="anthropic",
            llm_model=None,
            llm_timeout_s=5.0,
        )
        adapter = _build_adapter(args, tmp_path)
        assert adapter.timeout_s == 5.0

    def test_default_timeout_not_overridden(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si --llm-timeout-s == 30.0 (default), no se modifica el adapter."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
        args = argparse.Namespace(
            adapter="http",
            llm_provider="anthropic",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        adapter = _build_adapter(args, tmp_path)
        # El default del adapter debe ser 30.0 tambien.
        assert adapter.timeout_s == 30.0


# ---------------------------------------------------------------------------
# TestAdapterCliBuildHttpMissingKey
# ---------------------------------------------------------------------------


class TestAdapterCliBuildHttpMissingKey:
    """Error tipado si falta la API key del proveedor."""

    def test_anthropic_missing_key_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin ANTHROPIC_API_KEY y --llm-provider=anthropic, lanza SkillGraphError."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        args = argparse.Namespace(
            adapter="http",
            llm_provider="anthropic",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        with pytest.raises(SkillGraphError):
            _build_adapter(args, tmp_path)

    def test_openai_missing_key_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin OPENAI_API_KEY y --llm-provider=openai, lanza SkillGraphError."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        args = argparse.Namespace(
            adapter="http",
            llm_provider="openai",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        with pytest.raises(SkillGraphError):
            _build_adapter(args, tmp_path)

    def test_anthropic_does_not_pick_openai_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si solo hay OPENAI_API_KEY y se pide anthropic, debe fallar
        (cada proveedor exige SU propia key)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-67890")
        args = argparse.Namespace(
            adapter="http",
            llm_provider="anthropic",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        with pytest.raises(SkillGraphError):
            _build_adapter(args, tmp_path)


# ---------------------------------------------------------------------------
# TestAdapterCliBuildRejectsInvalid
# ---------------------------------------------------------------------------


class TestAdapterCliBuildRejectsInvalid:
    """Cobertura defensiva: cualquier valor no-fake cae en http.

    argparse valida con choices=['fake','http'], pero el helper usa
    getattr default 'fake', asi que un valor raro activaria http sin
    env y fallaria tipadamente.
    """

    def test_unknown_kind_raises_validation_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si --adapter tiene un valor fuera de {fake,http}, el helper
        rechaza con ValidationError (error tipado, no retorno silencioso)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        args = argparse.Namespace(
            adapter="bogus",
            llm_provider="anthropic",
            llm_model=None,
            llm_timeout_s=30.0,
        )
        with pytest.raises(ValidationError):
            _build_adapter(args, tmp_path)
