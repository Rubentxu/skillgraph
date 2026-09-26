"""Tests de no-disclosure: `repr(HttpAgentAdapter)` no debe filtrar api_key.

WI-14 (T3 Threat model S8/Information Disclosure). La regla es:
el repr/str del adapter NUNCA debe incluir el contenido de `api_key`,
porque el repr puede terminar en logs, error reports, o dumps de debug.

Por defecto, `@dataclass(frozen=True, slots=True)` genera un __repr__
que muestra TODOS los campos, incluyendo `api_key`. Este test documenta
esa propiedad y la corrige si falla.
"""

from __future__ import annotations

from skillgraph.runtime.http_adapter import HttpAgentAdapter


class TestHttpAdapterReprNoDisclosure:
    """S8/I: __repr__ del adapter NO debe filtrar api_key."""

    SENSITIVE_VALUE = "sk-ant-secret-key-do-not-leak-12345"

    def _make(self) -> HttpAgentAdapter:
        return HttpAgentAdapter(
            provider="anthropic",
            api_key=self.SENSITIVE_VALUE,
            model="claude-3-5-sonnet-20241022",
        )

    def test_repr_does_not_contain_api_key_value(self) -> None:
        """El repr() del adapter NO contiene el valor completo de api_key."""
        adapter = self._make()
        rendered = repr(adapter)
        assert self.SENSITIVE_VALUE not in rendered, f"repr filtra api_key: {rendered!r}"

    def test_str_does_not_contain_api_key_value(self) -> None:
        """El str() del adapter NO contiene el valor completo de api_key."""
        adapter = self._make()
        rendered = str(adapter)
        assert self.SENSITIVE_VALUE not in rendered, f"str filtra api_key: {rendered!r}"
