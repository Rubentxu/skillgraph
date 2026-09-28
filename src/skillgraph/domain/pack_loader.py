"""Carga declarativa de Domain Packs: registro de tipos extensibles sin
tocar el codigo del nucleo.

H6 multiprosito (UAT-12): "el proyecto puede crear y relacionar
instancias sin modificar el codigo del nucleo". El nucleo
(`registry.py`, `bricks.py`, `parser.py`) sigue declarando SOLO
los tipos minimos del spike S0 (`DecisionNode`, `ActionNode`,
`DomainPack`). Los tipos especializados (`Character`, `StoryArc`,
etc.) se declaran **en runtime** mediante esta utilidad al cargar
un Domain Pack YAML.

Restricciones del blueprint respetadas:
- "El motor no debe ejecutar codigo arbitrario incluido en el YAML."
  Los validadores se generan desde esquemas declarativos
  (campos requeridos, tipos primitivos, refs a otros tipos). NO
  se evalua codigo del pack.
- "Cada nueva abstraccion debe responder a un caso concreto."
  El esquema declarativo es simple: required + fields + refs.
  Si se necesita mas, se aniade al esquema, NO al motor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skillgraph.core.errors import ValidationError
from skillgraph.resources.bricks import Brick
from skillgraph.resources.registry import BrickRegistry, BrickType, SpecValidator

# Tipos primitivos soportados en el esquema declarativo.
_PRIMITIVE_TYPES = frozenset({"string", "integer", "number", "boolean"})


def _matches(field_schema: str, value: object) -> bool:
    """¿El valor satisface el tipo primitivo declarado?

    Asume que `field_schema` ya es un tipo conocido: quien llama
    comprueba la pertenencia a `_PRIMITIVE_TYPES` antes de llegar
    aqui (via `_require_known_type`). El `case _` final no se da por
    alcanzado, pero se conserva para que anadir un tipo a
    `_PRIMITIVE_TYPES` sin tocar esta funcion falle ruidosamente en
    vez de devolver `False` en silencio.

    WI-46: `bool` hereda de `int` en Python, asi que
    `isinstance(True, int)` es `True`. Un chequeo ingenuo aceptaba un
    booleano en un campo declarado `integer` (y en `number`, que
    acepta `(int, float)`). Se excluye `bool` explicitamente: son
    cuatro tipos primitivos, disjuntos.
    """
    match field_schema:
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case _:
            return False


def _require_known_type(kind: str, field_name: str, declared: str, label: str) -> None:
    """Rechaza un tipo declarado que no existe en el registro.

    WI-48. Un esquema mal escrito (`str` por `string`, `int` por
    `integer`) es un error de DECLARACION, no de dato: se reporta
    aqui nombrando el campo, el tipo recibido y los que si valen.

    Sin esta comprobacion el fallo se manifestaba de dos formas
    distintas y ambas malas. En una lista, el guard
    `if elem_type in _PRIMITIVE_TYPES:` tenia una rama de fallo
    vacia, asi que la lista entera se aceptaba sin mirar un
    elemento. En un campo escalar, `_matches` devolvia `False` para
    un tipo desconocido y caia en el mismo mensaje que un valor
    erroneo: "esperaba int, recibio int", que no dice nada y parece
    un bug.

    `label` distingue "tipo" de "tipo de elemento" porque ambos se
    declaran en sitios distintos y el usuario necesita saber cual de
    los dos esta mal.
    """
    if declared not in _PRIMITIVE_TYPES:
        accepted = ", ".join(sorted(_PRIMITIVE_TYPES))
        raise ValidationError(
            f"{kind}.spec.{field_name}: {label} {declared!r} desconocido; "
            f"se esperaba uno de: {accepted}"
        )


@dataclass(frozen=True, slots=True)
class _FieldContext:
    """Identidad del tipo al que pertenece una regla de campo.

    Los mensajes de error son `"<kind>.spec.<field>"`: sin el `kind`
    los errores de dos packs distintos son indistinguibles, y sin el
    campo el pack author no sabe que arreglar. Este valor lo lleva
    explicito en vez de capturarlo del closure, para que las reglas
    sean funciones de modulo (medibles por separado) y no metodos
    disfrazados.
    """

    kind: str


def _reject(ctx: _FieldContext, field_name: str, expected: str, value: object) -> ValidationError:
    """Construye el `ValidationError` de un valor que no casa."""
    return ValidationError(
        f"{ctx.kind}.spec.{field_name}: esperaba {expected}, recibio {type(value).__name__}"
    )


def _check_required(ctx: _FieldContext, required: tuple[str, ...], spec: dict[str, Any]) -> None:
    """Falla si falta algun campo declarado en `required`."""
    for key in required:
        if key not in spec:
            raise ValidationError(f"{ctx.kind}.spec.{key}: campo obligatorio ausente")


def _check_primitive(ctx: _FieldContext, field_name: str, field_schema: str, value: object) -> None:
    """Valida un campo declarado con un tipo primitivo.

    El tipo se valida antes que el valor: son dos errores con dos
    arreglos distintos, y comprobarlos en otro orden confunde a quien
    lee el mensaje.
    """
    _require_known_type(ctx.kind, field_name, field_schema, "tipo")
    if not _matches(field_schema, value):
        raise _reject(ctx, field_name, field_schema, value)


def _check_list(ctx: _FieldContext, field_name: str, elem_type: str, value: object) -> None:
    """Valida un campo `{"list_of": T}`: la lista, y cada elemento."""
    if not isinstance(value, list):
        raise _reject(ctx, field_name, "lista", value)
    _require_known_type(ctx.kind, field_name, elem_type, "tipo de elemento")
    for i, elem in enumerate(value):
        if not _matches(elem_type, elem):
            raise _reject(ctx, f"{field_name}[{i}]", elem_type, elem)


def _check_field(ctx: _FieldContext, field_name: str, field_schema: Any, value: object) -> None:
    """Aplica la regla que corresponde a la forma del esquema.

    El esquema de un campo admite tres formas y solo tres: un tipo
    primitivo, `{"list_of": T}` o `{"refs": [...]}`. Como el dominio
    es cerrado, se decide con `match` en vez de con una cadena de
    `isinstance` anidados, que era lo que producia los 5 niveles.

    Args:
        ctx: kind propietario, para el mensaje de error.
        field_name: nombre del campo, para el mensaje de error.
        field_schema: lo declarado en `fields` para ese campo.
        value: el valor de la instancia.

    Raises:
        ValidationError: si la forma no esta admitida, o si el valor
            no satisface la regla declarada.
    """
    match field_schema:
        case str():
            _check_primitive(ctx, field_name, field_schema, value)
        case {"list_of": elem_type}:
            _check_list(ctx, field_name, elem_type, value)
        case {"refs": _}:
            # Validacion estructural: el campo es lista o string con
            # nombre de instancia; NO verificamos la FK aqui, porque
            # eso es responsabilidad del motor y no del pack.
            pass
        case dict():
            raise ValidationError(
                f"{ctx.kind}: esquema de campo '{field_name}' no soportado: {field_schema!r}"
            )
        case _:
            raise ValidationError(
                f"{ctx.kind}: esquema de campo '{field_name}' invalido: "
                f"{type(field_schema).__name__}"
            )


def _make_schema_validator(kind: str, schema: dict[str, Any]) -> SpecValidator:
    """Genera un validador `SpecValidator` a partir de un esquema declarativo.

    Esquema soportado:
      required: lista de campos obligatorios (strings).
      fields: mapping {nombre: tipo_primitivo} o {nombre: {list_of: tipo}}.
      refs: lista de kinds a los que este campo puede referenciar
            (validacion: NO se valida la FK, solo que el kind este
            declarado en el registry al momento de validar).

    El validador resultante NO ejecuta codigo del pack: solo aplica
    reglas estructurales declaradas.
    """
    ctx = _FieldContext(kind=kind)
    required = tuple(schema.get("required", ()))
    fields = dict(schema.get("fields", {}))

    def _validate(spec: dict[str, Any]) -> None:
        _check_required(ctx, required, spec)
        for field_name, field_schema in fields.items():
            if field_name not in spec:
                continue  # Solo validamos presencia si esta en required
            _check_field(ctx, field_name, field_schema, spec[field_name])

    return _validate


def declare_types_from_pack(registry: BrickRegistry, pack: Brick) -> list[str]:
    """Declara en `registry` los tipos definidos en `pack.spec.types`.

    `pack` debe ser un Brick con `kind == "DomainPack"` y
    `spec.types` como lista de dicts `{kind, schema}`.

    Devuelve la lista de kinds declarados (en orden). Si un kind ya
    esta declarado en el registry, lanza `ValidationError` (no se
    permite shadowing de tipos del nucleo ni redefinicion).

    Restriccion (doc 03 §5): el `namespace` del pack no puede ser
    uno de los reservados del nucleo (`core`, `skillgraph`).
    """
    if pack.kind != "DomainPack":
        raise ValidationError(
            f"declare_types_from_pack: esperaba kind='DomainPack', recibio kind={pack.kind!r}"
        )

    api_version = pack.api_version
    namespace = pack.identity.namespace
    if namespace in BrickType.RESERVED_NAMESPACES:
        raise ValidationError(
            f"DomainPack.metadata.namespace={namespace!r} es reservado del "
            f"nucleo; no se permite que un pack declare tipos aqui. "
            f"Reservados: {sorted(BrickType.RESERVED_NAMESPACES)}"
        )

    types_decl = pack.spec.get("types", [])
    if not isinstance(types_decl, list):
        raise ValidationError(
            f"DomainPack.spec.types debe ser lista; recibio {type(types_decl).__name__}"
        )

    declared: list[str] = []
    for entry in types_decl:
        if not isinstance(entry, dict):
            raise ValidationError(
                f"DomainPack.spec.types[{len(declared)}]: esperaba mapping, "
                f"recibio {type(entry).__name__}"
            )
        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValidationError(
                f"DomainPack.spec.types[{len(declared)}].kind: debe ser string no vacio"
            )
        schema = entry.get("schema", {})
        if not isinstance(schema, dict):
            raise ValidationError(
                f"DomainPack.spec.types[{len(declared)}].schema: "
                f"esperaba mapping, recibio {type(schema).__name__}"
            )
        validator = _make_schema_validator(kind, schema)
        reg_type = BrickType(
            api_version=api_version,
            kind=kind,
            validate_spec=validator,
        )
        # declare() ya valida duplicados; si los tipos del nucleo
        # (DecisionNode/ActionNode/DomainPack) colisionan, lanzara
        # ValidationError y nos protege contra shadowing.
        registry.declare(reg_type)
        declared.append(kind)

    return declared


def validate_instance_against_registry(registry: BrickRegistry, brick: Brick) -> None:
    """Valida una instancia contra el registry. Convenience helper.

    Lanza `UnknownKindError` si el kind no esta declarado, o
    `ValidationError` si el spec no cumple el esquema.
    """
    # `registry.validate()` ya hace todo lo que necesitamos:
    # - lanza UnknownKindError si (api_version, kind) no esta en el registry.
    # - busca el BrickType y ejecuta su validate_spec().
    registry.validate(brick)


__all__ = [
    "declare_types_from_pack",
    "validate_instance_against_registry",
]
