"""El despacho de campos del esquema declarativo es una tabla, no un arbol.

`_make_schema_validator` media cc=13 con 5 niveles de anidamiento porque
`_validate` encadenaba `isinstance` -> `in` -> rama -> rama. Cada forma
de campo soportada (primitivo, `list_of`, `refs`) es una regla
independiente, y las reglas admitidas son un conjunto cerrado: por eso
encajan en un dispatch por tabla en vez de en un `if/elif`.

Estos tests fijan el comportamiento de cada fila de la tabla y el
contrato del valor invalido, sin depender de la forma que tome el
despacho por dentro.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.domain.pack_loader import _make_schema_validator

# ---------------------------------------------------------------------------
# Filas del dispatch: una regla por forma de campo admitida
# ---------------------------------------------------------------------------


def test_primitive_field_accepts_matching_value() -> None:
    """Campo primitivo: si el valor casa con el tipo, pasa."""
    v = _make_schema_validator("Brick", {"fields": {"edad": "integer"}})
    v({"edad": 3})  # no lanza


def test_primitive_field_rejects_mismatching_value() -> None:
    """Campo primitivo: un valor que no casa lanza ValidationError."""
    v = _make_schema_validator("Brick", {"fields": {"edad": "integer"}})
    with pytest.raises(ValidationError, match=r"esperaba integer, recibio str"):
        v({"edad": "tres"})


def test_list_field_checks_every_element() -> None:
    """`list_of` valida cada elemento, no solo el primero."""
    v = _make_schema_validator("Brick", {"fields": {"tags": {"list_of": "string"}}})
    v({"tags": ["a", "b", "c"]})
    with pytest.raises(ValidationError, match=r"tags\[1\]"):
        v({"tags": ["a", 7, "c"]})


def test_list_field_rejects_non_list() -> None:
    """`list_of` sobre un valor que no es lista lanza."""
    v = _make_schema_validator("Brick", {"fields": {"tags": {"list_of": "string"}}})
    with pytest.raises(ValidationError, match="esperaba lista"):
        v({"tags": "a"})


def test_refs_field_is_passthrough() -> None:
    """`refs` se acepta sin validar la FK: es trabajo del motor, no del pack.

    El valor puede ser cualquier cosa, incluso una lista de nombres.
    """
    v = _make_schema_validator("Brick", {"fields": {"link": {"refs": ["Otro"]}}})
    v({"link": "inst-1"})
    v({"link": ["inst-1", "inst-2"]})


def test_unknown_primitive_type_is_rejected() -> None:
    """Un tipo primitivo no declarado no es "cualquier cosa": es un error.

    Sin esta fila, un typo en el esquema pasaria inadvertido hasta que
    el valor no casara con un tipo inexistente.
    """
    v = _make_schema_validator("Brick", {"fields": {"x": "typo"}})
    with pytest.raises(ValidationError):
        v({"x": 1})


# ---------------------------------------------------------------------------
# Contrato del valor no admitido
# ---------------------------------------------------------------------------


def test_dict_field_without_known_key_is_rejected() -> None:
    """Un dict de esquema que no es `list_of` ni `refs` no se adivina."""
    v = _make_schema_validator("Brick", {"fields": {"x": {"raro": "string"}}})
    with pytest.raises(ValidationError, match="no soportado"):
        v({"x": "valor"})


@pytest.mark.parametrize("bad", [1, 1.5, True, None, ["string"]])
def test_non_string_non_dict_schema_is_rejected(bad: object) -> None:
    """El esquema de un campo debe ser string o dict; cualquier otra cosa no.

    Parametrizado porque cada valor ejercita el mismo contrato desde un
    tipo distinto, y un solo ejemplo no pinsa el tipo del error.
    """
    v = _make_schema_validator("Brick", {"fields": {"x": bad}})
    with pytest.raises(ValidationError, match="invalido"):
        v({"x": "valor"})


def test_absent_field_is_skipped_unless_required() -> None:
    """Un campo ausente solo es error si aparece en `required`."""
    optional = _make_schema_validator("Brick", {"fields": {"x": "integer"}})
    optional({})  # no lanza

    required = _make_schema_validator("Brick", {"required": ["x"], "fields": {"x": "integer"}})
    with pytest.raises(ValidationError, match="campo obligatorio ausente"):
        required({})


def test_error_message_names_the_kind_and_field() -> None:
    """El mensaje identifica kind y campo: sin eso el pack author no puede arreglarlo."""
    v = _make_schema_validator("Character", {"fields": {"age": "integer"}})
    with pytest.raises(ValidationError) as exc:
        v({"age": "x"})
    msg = str(exc.value)
    assert "Character" in msg
    assert "age" in msg
