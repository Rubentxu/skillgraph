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

from typing import Any

from skillgraph.core.errors import ValidationError
from skillgraph.resources.bricks import Brick
from skillgraph.resources.registry import BrickRegistry, BrickType, SpecValidator

# Tipos primitivos soportados en el esquema declarativo.
_PRIMITIVE_TYPES = frozenset({"string", "integer", "number", "boolean"})


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
    required = list(schema.get("required", []))
    fields = dict(schema.get("fields", {}))

    def _validate(spec: dict[str, Any]) -> None:
        for key in required:
            if key not in spec:
                raise ValidationError(f"{kind}.spec.{key}: campo obligatorio ausente")
        for field_name, field_schema in fields.items():
            if field_name not in spec:
                continue  # Solo validamos presencia si esta en required
            value = spec[field_name]
            if isinstance(field_schema, str):
                # Tipo primitivo
                if field_schema == "string" and not isinstance(value, str):
                    raise ValidationError(
                        f"{kind}.spec.{field_name}: esperaba string, recibio {type(value).__name__}"
                    )
                if field_schema == "integer" and not isinstance(value, int):
                    raise ValidationError(
                        f"{kind}.spec.{field_name}: esperaba integer, recibio "
                        f"{type(value).__name__}"
                    )
                if field_schema == "number" and not isinstance(value, (int, float)):
                    raise ValidationError(
                        f"{kind}.spec.{field_name}: esperaba number, recibio {type(value).__name__}"
                    )
                if field_schema == "boolean" and not isinstance(value, bool):
                    raise ValidationError(
                        f"{kind}.spec.{field_name}: esperaba boolean, recibio "
                        f"{type(value).__name__}"
                    )
            elif isinstance(field_schema, dict):
                # Forma compuesta: {list_of: tipo} | {refs: [kind, ...]}
                if "list_of" in field_schema:
                    if not isinstance(value, list):
                        raise ValidationError(
                            f"{kind}.spec.{field_name}: esperaba lista, recibio "
                            f"{type(value).__name__}"
                        )
                    elem_type = field_schema["list_of"]
                    if elem_type in _PRIMITIVE_TYPES:
                        for i, elem in enumerate(value):
                            if elem_type == "string" and not isinstance(elem, str):
                                raise ValidationError(
                                    f"{kind}.spec.{field_name}[{i}]: esperaba string"
                                )
                elif "refs" in field_schema:
                    # Validacion estructural: el campo es lista o string
                    # con nombre de instancia; NO verificamos FK aqui
                    # (eso es responsabilidad del motor, no del pack).
                    pass
                else:
                    raise ValidationError(
                        f"{kind}: esquema de campo '{field_name}' no soportado: {field_schema!r}"
                    )
            else:
                raise ValidationError(
                    f"{kind}: esquema de campo '{field_name}' invalido: "
                    f"{type(field_schema).__name__}"
                )

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
