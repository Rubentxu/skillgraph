"""WI-46: un `bool` no es un `integer` (ni un `number`).

Defecto real, encontrado al perseguir la cobertura de
`domain/pack_loader.py` (98%, con la rama `integer` sin ejecutar).

En Python `isinstance(True, int)` es `True`, porque `bool` hereda de
`int`. El validador declarativo de packs comprobaba

    if field_schema == "integer" and not isinstance(value, int):

asi que un `True` atravesaba la validacion de un campo declarado
`integer` sin rechistar. Lo mismo con `number`, que acepta `(int, float)`.

Consecuencia: un Domain Pack puede declarar `retries: integer` y
aportar `retries: true`. El loader lo acepta como valido, y el
consumidor recibe un booleano donde esperaba un entero. El error sale
mas tarde, en el punto de uso, y sin relacion con su causa.

No es un caso teorico: `True` y `1` son indistinguibles para
`isinstance`, asi que cualquier valor booleano emitido por JSON o YAML
(YAML los escribe sin comillas) atraviesa la puerta.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.domain.pack_loader import _make_schema_validator


class TestBoolIsNotAnInteger:
    """El contrato que el validador deberia honorar y no honora."""

    def test_bool_rechazado_como_integer(self) -> None:
        """Un True en un campo `integer` debe ser ValidationError."""
        validate = _make_schema_validator("Brick", {"fields": {"edad": "integer"}})
        with pytest.raises(ValidationError, match="esperaba integer"):
            validate({"edad": True})

    def test_bool_rechazado_como_number(self) -> None:
        """`number` acepta (int, float); un bool tampoco es un number."""
        validate = _make_schema_validator("Brick", {"fields": {"ratio": "number"}})
        with pytest.raises(ValidationError, match="esperaba number"):
            validate({"ratio": False})

    @pytest.mark.parametrize("valor", [True, False])
    def test_ambos_valores_booleanos_rechazados(self, valor: bool) -> None:
        validate = _make_schema_validator("Brick", {"fields": {"n": "integer"}})
        with pytest.raises(ValidationError):
            validate({"n": valor})

    def test_integer_valido_sigue_pasando(self) -> None:
        """No se rompe el camino feliz: 0 y negativos son enteros."""
        validate = _make_schema_validator("Brick", {"fields": {"n": "integer"}})
        validate({"n": 0})
        validate({"n": -1})
        validate({"n": 42})

    def test_number_acepta_int_y_float_legitimos(self) -> None:
        validate = _make_schema_validator("Brick", {"fields": {"x": "number"}})
        validate({"x": 1})
        validate({"x": 1.5})
        validate({"x": 0.0})

    def test_boolean_acepta_bool_legitimo(self) -> None:
        """Un campo declarado `boolean` si admite True/False."""
        validate = _make_schema_validator("Brick", {"fields": {"flag": "boolean"}})
        validate({"flag": True})
        validate({"flag": False})

    def test_integer_rechaza_string_numerico(self) -> None:
        """El bug es bool/int, no una falta de coercion: "5" no vale."""
        validate = _make_schema_validator("Brick", {"fields": {"n": "integer"}})
        with pytest.raises(ValidationError, match="esperaba integer"):
            validate({"n": "5"})

    def test_lista_de_integers_tambien_rechaza_bool(self) -> None:
        """La misma regla aplica dentro de `list_of`."""
        validate = _make_schema_validator("Brick", {"fields": {"ns": {"list_of": "integer"}}})
        with pytest.raises(ValidationError, match="esperaba integer"):
            validate({"ns": [1, True, 3]})


class TestPrimitivesStayDistinct:
    """Cada tipo primitivo acepta lo suyo y nada mas."""

    def test_string_no_acepta_int(self) -> None:
        validate = _make_schema_validator("Brick", {"fields": {"s": "string"}})
        with pytest.raises(ValidationError, match="esperaba string"):
            validate({"s": 1})

    def test_boolean_no_acepta_int(self) -> None:
        """Y al reves: 1 no es True, aunque True sea 1."""
        validate = _make_schema_validator("Brick", {"fields": {"flag": "boolean"}})
        with pytest.raises(ValidationError, match="esperaba boolean"):
            validate({"flag": 1})
