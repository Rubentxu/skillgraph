"""WI-48: un `list_of` con tipo mal escrito no puede dejar de validar.

WI-46 cerro el caso de un `bool` que atravesaba un campo declarado
`integer`, y de paso hizo que `_check_list` validara elementos de
cualquier tipo. Ese segundo arreglo quedo a medias.

`_check_list` hace:

    elem_type = field_schema["list_of"]
    if elem_type in _PRIMITIVE_TYPES:
        for i, elem in enumerate(value):
            ...

El guard es correcto en su forma, pero su rama de fallo no hace
nada: si `elem_type` no es un tipo primitivo conocido, la lista
entera se acepta sin mirar un solo elemento. Un typo en el pack
(`list_of: "str"` en vez de `"string"`, o `"int"` en vez de
`"integer"`) desactiva la validacion en silencio.

Y el error aparece tarde: no en la carga del pack, sino en el punto
de uso, con un mensaje que no mentiona el campo. Es el mismo modo de
fallo que WI-46 cerro en el caso escalar, y sigue abierto en el caso
de lista.

La asimetria es la prueba de que no es decision de diseno: el mismo
tipo mal escrito en un campo ESCALAR si se rechaza, y en una lista
no.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.domain.pack_loader import _PRIMITIVE_TYPES, _make_schema_validator


def _list_validator(elem_type: str) -> object:
    return _make_schema_validator("Brick", {"fields": {"x": {"list_of": elem_type}}})


class TestUnknownElemTypeIsRejected:
    """Un tipo de elemento desconocido se rechaza al declarar, no al usar."""

    @pytest.mark.parametrize(
        "elem_type",
        ["int", "float", "str", "Integer", "object", "refs", ""],
    )
    def test_unknown_elem_type_is_rejected(self, elem_type: str) -> None:
        """Antes: la lista pasaba sin validar NINGUN elemento."""
        with pytest.raises(ValidationError) as ei:
            _list_validator(elem_type)({"x": []})  # type: ignore[operator]
        assert "x" in str(ei.value)

    @pytest.mark.parametrize("elem_type", ["str", "int", "typo", "STRING"])
    def test_typo_does_not_disable_validation(self, elem_type: str) -> None:
        """El caso de dano real: un typo no puede pasar sin comprobar nada.

        Se usa una lista vacia y una con basura, y ambos deben fallar
        por el mismo motivo: el tipo declarado no existe.
        """
        for value in ([], [1, "dos", None]):
            with pytest.raises(ValidationError):
                _list_validator(elem_type)({"x": value})  # type: ignore[operator]

    def test_message_names_the_bad_type(self) -> None:
        """El error debe senalar el campo y el tipo, para que se pueda arreglar."""
        with pytest.raises(ValidationError) as ei:
            _list_validator("int")({"x": []})  # type: ignore[operator]
        msg = str(ei.value)
        assert "int" in msg
        assert "Brick" in msg

    def test_error_lists_the_accepted_types(self) -> None:
        """Decir WHICH types are valid convierte un fallo en una accion.

        Sin esta informacion el autor del pack tiene que abrir el
        codigo para descubrir que habia cuatro tipos y no seis.
        """
        with pytest.raises(ValidationError) as ei:
            _list_validator("int")({"x": []})  # type: ignore[operator]
        msg = str(ei.value)
        for valid in _PRIMITIVE_TYPES:
            assert valid in msg


class TestKnownElemTypesStillValidate:
    """Guarda de regresion: lo que ya funcionaba sigue funcionando."""

    @pytest.mark.parametrize(
        ("elem_type", "good", "bad", "bad_label"),
        [
            ("string", ["a", "b"], [1, None, True], "no-string"),
            ("integer", [0, 7], [True, 1.5, "3"], "bool y float no son integer"),
            ("number", [1, 2.5], [True, "x", None], "bool no es number"),
            ("boolean", [True, False], [1, "true", None], "int no es boolean"),
        ],
    )
    def test_good_values_pass(self, elem_type: str, good: list, bad: list, bad_label: str) -> None:
        _list_validator(elem_type)({"x": good})  # type: ignore[operator]

    @pytest.mark.parametrize(
        ("elem_type", "bad", "bad_label"),
        [
            ("string", [1], "int no es string"),
            ("integer", [True], "bool no es integer"),
            ("number", [True], "bool no es number"),
            ("boolean", [1], "int no es boolean"),
        ],
    )
    def test_bad_values_rejected(self, elem_type: str, bad: list, bad_label: str) -> None:
        for value in bad:
            with pytest.raises(ValidationError):
                _list_validator(elem_type)({"x": [value]})  # type: ignore[operator]

    def test_error_reports_the_offending_index(self) -> None:
        """`x[2]` dice WHICH elemento falla: sin eso hay que inspeccionar a mano."""
        with pytest.raises(ValidationError) as ei:
            _list_validator("integer")({"x": [1, 2, "tres"]})  # type: ignore[operator]
        assert "x[2]" in str(ei.value)


class TestTypeRegistryStaysInSyncWithMatcher:
    """`_PRIMITIVE_TYPES` y los `case` de `_matches` son el mismo dato duplicado.

    Anadir un tipo al conjunto sin anadir su `case` haria que
    `_matches` cayera en `case _` y devolviera `False` para
    cualquier valor, con lo que ese campo rechazaria todo sin decir
    por que. Es el mismo modo de fallo que WI-48, en un sitio mas.

    El `case _` es por tanto intencionadamente inalcanzable y queda
    sin cubrir: no se puede cubrir sin romper el invariante. Esta
    asercion lo vigila desde fuera.
    """

    def test_every_primitive_type_is_in_the_matcher(self) -> None:
        # El docstring de `_matches` declara estos cuatro. Si alguien
        # anade un quinto, esta asercion falla y obliga a actualizar
        # `_matches` Y este test a la vez.
        matched_cases = {"string", "integer", "number", "boolean"}
        assert matched_cases == _PRIMITIVE_TYPES, (
            f"desincronizado: _PRIMITIVE_TYPES={sorted(_PRIMITIVE_TYPES)} "
            f"pero _matches cubre {sorted(matched_cases)}. Anade el case "
            f"correspondiente y actualiza este test."
        )

    @pytest.mark.parametrize("elem_type", sorted(_PRIMITIVE_TYPES))
    def test_declared_type_accepts_at_least_one_value(self, elem_type: str) -> None:
        """Todo tipo declarado debe aceptar ALGO.

        Si `_matches` devolviera `False` siempre, el campo rechazaria
        todos los valores y el fallo se manifestaria como "el pack es
        invalido" sin relacion con la causa.
        """
        # Un `KeyError` aqui significaria que el parametro se desincronizo
        # entre el collect y la asercion de arriba. Es un fallo real, pero
        # opaco; se convierte en uno que se puede leer.
        samples = {"string": "a", "integer": 1, "number": 1.5, "boolean": True}
        assert elem_type in samples, f"falta una muestra valida para {elem_type!r}"
        v = _make_schema_validator("Brick", {"fields": {"x": elem_type}})
        v({"x": samples[elem_type]})  # no debe lanzar


class TestUnknownTypeIsDistinguishableFromBadValue:
    """ "El tipo no existe" y "el valor no es del tipo" son errores distintos.

    El segundo defecto no salio de un test, sino de leer el mensaje:
    un tipo desconocido caia en el mismo mensaje que un valor malo, y
    decia "esperaba int, recibio int". Quien lo lea no puede saber si
    el problema es su tipo o su valor, y parece un bug del validador.
    """

    def test_unknown_type_does_not_say_expected_int_received_int(self) -> None:
        v = _make_schema_validator("Brick", {"fields": {"edad": "int"}})
        with pytest.raises(ValidationError) as ei:
            v({"edad": 5})  # un int perfectly valido
        msg = str(ei.value)
        assert "desconocido" in msg
        assert "recibio" not in msg, f"mensaje no informativo: {msg!r}"

    def test_bad_value_still_reports_the_received_type(self) -> None:
        """El caso normal NO debe perder su mensaje: sigue diciendo el tipo real."""
        v = _make_schema_validator("Brick", {"fields": {"edad": "integer"}})
        with pytest.raises(ValidationError) as ei:
            v({"edad": "cinco"})
        msg = str(ei.value)
        assert "esperaba integer" in msg
        assert "recibio str" in msg
        assert "desconocido" not in msg

    def test_both_errors_name_the_field(self) -> None:
        """Sin el nombre del campo el mensaje no es accionable."""
        for schema, value in ((("edad"), 5), (("edad"), "x")):
            v = _make_schema_validator("Brick", {"fields": {"edad": schema}})
            with pytest.raises(ValidationError) as ei:
                v({"edad": value})
            assert "edad" in str(ei.value)


class TestScalarAsymmetryIsClosed:
    """El caso escalar ya se rechazaba. El de lista tambien debe."""

    @pytest.mark.parametrize("field_type", ["int", "str", "typo", "Integer"])
    def test_scalar_rejects_unknown_type(self, field_type: str) -> None:
        v = _make_schema_validator("Brick", {"fields": {"x": field_type}})
        with pytest.raises(ValidationError):
            v({"x": "cualquiera"})

    @pytest.mark.parametrize("field_type", ["int", "str", "typo"])
    def test_list_rejects_unknown_type_like_scalar(self, field_type: str) -> None:
        """Simetria: escalar y lista rechazan el mismo conjunto de typos."""
        v = _make_schema_validator("Brick", {"fields": {"x": field_type}})
        scalar_rejects = _raises(lambda: v({"x": "cualquiera"}))
        list_rejects = _raises(lambda: _list_validator(field_type)({"x": ["a"]}))  # type: ignore[operator]
        assert scalar_rejects is list_rejects, (
            f"asimetria para {field_type!r}: escalar rechaza={scalar_rejects}, "
            f"lista rechaza={list_rejects}"
        )


def _raises(fn: object) -> bool:
    try:
        fn()  # type: ignore[operator]
    except ValidationError:
        return True
    return False
