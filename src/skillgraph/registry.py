"""Registro de tipos de bricks (Etapa 0 / S0).

Decisión clave de la implementación:
- El registro es **inmutable desde fuera**: los tipos se declaran al
  arranque y no se modifican durante una ejecución.
- La validación estructural (campos obligatorios, tipos básicos) se hace
  una sola vez aquí para evitar duplicación con el parser y con el
  futuro repositorio de almacenamiento (Etapa 1 / S1).

Doc 03 §3 y §4 marcan los campos comunes:
    apiVersion, kind, metadata.name, metadata.namespace, spec
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from skillgraph.bricks import Brick
from skillgraph.errors import UnknownKindError, ValidationError

# Validador puro: recibe el `spec` (dict) y devuelve None si OK;
# lanza `ValidationError` con mensaje tipado si falla.
SpecValidator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class BrickType:
    """Declaración de un tipo de brick."""

    api_version: str
    kind: str
    validate_spec: spec_validator_alias  # type: ignore[valid-type]
    # `namespace` queda libre: el blueprint permite tipos en cualquier
    # namespace siempre que no colisionen con los reservados del núcleo
    # (doc 03 §5).

    # Si quisiéramos reservar namespaces del núcleo, lo haríamos en
    # un único punto aquí para no duplicar la regla en cada validador.
    RESERVED_NAMESPACES: ClassVar[frozenset[str]] = frozenset({"core", "skillgraph"})


# Alias para que el typing no se queje del Callable posicional.
spec_validator_alias = Callable[[dict[str, Any]], None]


class BrickRegistry:
    """Catálogo en memoria de tipos conocidos.

    Construido por `load_defaults`. NO se permite `register()` en
    ejecución: la idea es que un Domain Pack añada sus tipos antes
    de iniciar el plano de control (Etapa 5).
    """

    def __init__(self) -> None:
        self._types: dict[tuple[str, str], BrickType] = {}

    def declare(self, brick_type: BrickType) -> None:
        key = (brick_type.api_version, brick_type.kind)
        if key in self._types:
            raise ValidationError(
                f"Tipo ya declarado: apiVersion={brick_type.api_version!r} kind={brick_type.kind!r}"
            )
        self._types[key] = brick_type

    def has(self, api_version: str, kind: str) -> bool:
        return (api_version, kind) in self._types

    def validate(self, brick: Brick) -> None:
        key = (brick.api_version, brick.kind)
        if key not in self._types:
            raise UnknownKindError(
                f"Tipo no registrado: apiVersion={brick.api_version!r} kind={brick.kind!r}"
            )
        brick_type = self._types[key]
        if brick_type.api_version != brick.api_version:
            # Doble check por si el dict se construye a mano.
            raise UnknownKindError(
                f"apiVersion inconsistente: declarado "
                f"{brick_type.api_version!r}, recurso {brick.api_version!r}"
            )
        brick_type.validate_spec(brick.spec)


# ---------------------------------------------------------------------------
# Validadores mínimos para los tipos del spike S0.
# El objetivo es COMPROBAR el contrato, no implementar el dominio entero.
# ---------------------------------------------------------------------------


def _require_keys(spec: dict[str, Any], keys: tuple[str, ...], *, ctx: str) -> None:
    for key in keys:
        if key not in spec:
            raise ValidationError(f"{ctx}: clave obligatoria ausente: {key!r}")


def _validate_decision(spec: dict[str, Any]) -> None:
    _require_keys(spec, ("ctx_recipe_ref", "outcomes"), ctx="DecisionNode.spec")
    if not isinstance(spec["ctx_recipe_ref"], str):
        raise ValidationError("DecisionNode.spec.ctx_recipe_ref debe ser string")
    outcomes = spec["outcomes"]
    if not isinstance(outcomes, list) or not outcomes:
        raise ValidationError("DecisionNode.spec.outcomes debe ser lista no vacía")
    for i, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict):
            raise ValidationError(f"DecisionNode.spec.outcomes[{i}] debe ser mapping")
        if "name" not in outcome or not isinstance(outcome["name"], str):
            raise ValidationError(f"DecisionNode.spec.outcomes[{i}].name debe ser string")


def _validate_action(spec: dict[str, Any]) -> None:
    _require_keys(spec, ("inputs", "transitions"), ctx="ActionNode.spec")
    inputs = spec["inputs"]
    if not isinstance(inputs, list):
        raise ValidationError("ActionNode.spec.inputs debe ser lista")
    transitions = spec["transitions"]
    if not isinstance(transitions, dict) or not transitions:
        raise ValidationError("ActionNode.spec.transitions debe ser mapping no vacío")
    for state in transitions:
        if not isinstance(state, str):
            raise ValidationError("ActionNode.spec.transitions: claves deben ser string")


def _validate_domain_pack(spec: dict[str, Any]) -> None:
    _require_keys(spec, ("version",), ctx="DomainPack.spec")
    if not isinstance(spec["version"], str):
        raise ValidationError("DomainPack.spec.version debe ser string")
    capabilities = spec.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise ValidationError("DomainPack.spec.capabilities debe ser lista")


# ---------------------------------------------------------------------------
# Bootstrap del catálogo: SOLO tipos del spike S0.
# Los Domain Packs añadirán los suyos en Etapa 5 (doc 03 §5).
# ---------------------------------------------------------------------------


def load_defaults() -> BrickRegistry:
    """Devuelve un registro con los tipos mínimos del spike S0."""
    reg = BrickRegistry()
    reg.declare(
        BrickType(
            api_version="skillgraph.dev/v1alpha1",
            kind="DecisionNode",
            validate_spec=_validate_decision,
        )
    )
    reg.declare(
        BrickType(
            api_version="skillgraph.dev/v1alpha1",
            kind="ActionNode",
            validate_spec=_validate_action,
        )
    )
    reg.declare(
        BrickType(
            api_version="skillgraph.dev/v1alpha1",
            kind="DomainPack",
            validate_spec=_validate_domain_pack,
        )
    )
    return reg
