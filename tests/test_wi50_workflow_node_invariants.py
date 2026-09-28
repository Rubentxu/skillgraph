"""`WorkflowNode.__post_init__` valida y luego reconcilia: son dos cosas.

El constructor hacia dos trabajos distintos y los moria en un solo
`__post_init__` de cc=12: comprobar que los campos obligatorios son
presentes y coherentes, y decidir que valores de `outcomes` y
`max_visits` se derivan de `metadata` segun el `kind`.

Estos tests fijan **que** se valida, **en que orden** (que error gana
cuando hay varios) y **que** reconcilia. El ultimo punto es el que
importa de verdad: `outcomes` no se acepta desde el llamante, se
deriva, y un `ActionNode` que declara outcomes por metadata los
respeta. Ese comportamiento se apoya en la verdad de `metadata`
(degraded mode) y no es accidental.
"""

from __future__ import annotations

from typing import Any

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.resources.workflow import WorkflowNode

# ---------------------------------------------------------------------------
# Base valida: sin esto cada testARIA fallando por otra razon
# ---------------------------------------------------------------------------


def _valid(**overrides: Any) -> dict[str, Any]:
    """Campos minimos de un ActionNode valido, con overrides puntuales."""
    base: dict[str, Any] = {
        "name": "n1",
        "kind": "ActionNode",
        "namespace": "ns",
        "api_version": "v1",
        "resource_revision": 1,
        "expected_result": "ok",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Guardas de campos obligatorios
# ---------------------------------------------------------------------------


def test_minimal_action_node_is_accepted() -> None:
    """Un ActionNode con los campos minimos se construye sin error."""
    node = WorkflowNode(**_valid())
    assert node.name == "n1"
    assert node.outcomes == ()
    assert node.max_visits is None


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("name", "WorkflowNode.name vacio"),
        ("namespace", "WorkflowNode.namespace vacio"),
        ("api_version", "WorkflowNode.api_version vacio"),
        ("expected_result", "WorkflowNode.expected_result vacio"),
    ],
)
def test_empty_required_field_is_rejected(field: str, message: str) -> None:
    """Cada campo obligatorio vacio se rechaza con su propio mensaje.

    Parametrizado porque son cuatro guardas con el mismo patron pero
    mensajes distintos: un solo ejemplo no pinsa que los otros tres
    tambien existen.
    """
    with pytest.raises(ValidationError, match=message):
        WorkflowNode(**_valid(**{field: ""}))


@pytest.mark.parametrize("bad_kind", ["", "ActorNode", "decisionnode", "ACCION"])
def test_kind_outside_the_closed_set_is_rejected(bad_kind: str) -> None:
    """`kind` pertenece a un Literal cerrado: cuatro casos distintos.

    Se incluye el minusculo y el mayusculo a proposito, porque la
    comparacion es exacta y una tolerancia por caso seria un contrato
    distinto del declarado.
    """
    with pytest.raises(ValidationError, match=r"WorkflowNode\.kind invalido"):
        WorkflowNode(**_valid(kind=bad_kind))


def test_resource_revision_below_one_is_rejected() -> None:
    """`resource_revision` es un entero >= 1; 0 no es una revision."""
    with pytest.raises(ValidationError, match="resource_revision debe ser >= 1"):
        WorkflowNode(**_valid(resource_revision=0))


def test_metadata_must_be_a_dict() -> None:
    """`metadata` es el unico campo libre, pero sigue siendo dict."""
    with pytest.raises(ValidationError, match=r"WorkflowNode\.metadata debe ser dict"):
        WorkflowNode(**_valid(metadata=[("outcomes", ["ok"])]))


# ---------------------------------------------------------------------------
# Orden de las guardas: cual error gana
# ---------------------------------------------------------------------------


def test_name_is_validated_before_kind() -> None:
    """Con dos campos invalidos, el mensaje dice cual se comprobo primero.

    Fijar el orden importa: sin esto, reordenar las guardas seria un
    cambio de contrato silencioso para quien lee el mensaje de error.
    """
    with pytest.raises(ValidationError, match=r"WorkflowNode\.name vacio"):
        WorkflowNode(**_valid(name="", kind="NoExiste"))


def test_kind_is_validated_before_outcomes() -> None:
    """Un kind invalido falla antes que un metadata.outcomes mal formado.

    Es decir: el kind se valida en la guarda, no en la reconciliacion.
    """
    with pytest.raises(ValidationError, match=r"WorkflowNode\.kind invalido"):
        WorkflowNode(**_valid(kind="NoExiste", metadata={"outcomes": "no-es-lista"}))


# ---------------------------------------------------------------------------
# Reconciliacion: outcomes y max_visits se derivan de metadata
# ---------------------------------------------------------------------------


def test_decision_node_requires_declared_outcomes() -> None:
    """Un DecisionNode sin outcomes no puede existir: no tendria a donde ir."""
    with pytest.raises(ValidationError, match=r"DecisionNode requiere metadata\.outcomes"):
        WorkflowNode(**_valid(kind="DecisionNode"))


def test_decision_node_takes_its_outcomes_from_metadata() -> None:
    """`outcomes` del DecisionNode se derivan de metadata, no del llamante."""
    node = WorkflowNode(**_valid(kind="DecisionNode", metadata={"outcomes": ["si", "no"]}))
    assert node.outcomes == ("si", "no")


def test_action_node_may_declare_outcomes_in_metadata() -> None:
    """Un ActionNode que declara outcomes los respeta (degraded mode).

    `metadata` es la verdad: si el pack declara outcomes en un
    ActionNode, el constructor no los descarta ni los inventa.
    """
    node = WorkflowNode(**_valid(kind="ActionNode", metadata={"outcomes": ["retry"]}))
    assert node.outcomes == ("retry",)


def test_action_node_without_metadata_outcomes_stays_empty() -> None:
    """Un ActionNode sin outcomes declarados se queda con la tupla vacia."""
    node = WorkflowNode(**_valid(kind="ActionNode"))
    assert node.outcomes == ()


def test_declared_outcomes_override_the_caller_argument() -> None:
    """Lo declarado en metadata gana sobre el argumento `outcomes`.

    Es la invariante clave del tipo: `outcomes` es derivado, no
    constructor-accept. Si esto dejara de ser cierto, dos fuentes de
    verdad estarian escribiendo el mismo campo.
    """
    node = WorkflowNode(
        **_valid(kind="DecisionNode", outcomes=("mentira",), metadata={"outcomes": ["si"]})
    )
    assert node.outcomes == ("si",)


def test_max_visits_is_derived_from_metadata() -> None:
    """`max_visits` se lee de metadata cuando esta declarado."""
    node = WorkflowNode(**_valid(metadata={"max_visits": 3}))
    assert node.max_visits == 3


def test_max_visits_absent_stays_none() -> None:
    """Sin `max_visits` en metadata, el campo queda en None (ilimitado)."""
    assert WorkflowNode(**_valid()).max_visits is None


def test_declared_max_visits_override_the_caller_argument() -> None:
    """metadata es la verdad tambien para max_visits."""
    node = WorkflowNode(**_valid(max_visits=99, metadata={"max_visits": 2}))
    assert node.max_visits == 2


# ---------------------------------------------------------------------------
# Errores de la reconciliacion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["si", [1], [""], [None], {"si": 1}, 3, True])
def test_outcomes_metadata_must_be_non_empty_string_list(bad: object) -> None:
    """`outcomes` en metadata debe ser lista de strings no vacios.

    Parametrizado porque cada valor rompe el contrato por un motivo
    distinto, y un solo ejemplo dejaria sin cubrir la mayoria.
    """
    with pytest.raises(ValidationError, match="debe ser lista de strings no vacios"):
        WorkflowNode(**_valid(metadata={"outcomes": bad}))


@pytest.mark.parametrize("bad", [0, -1, "3", 2.5, True])
def test_max_visits_metadata_must_be_int_at_least_one(bad: object) -> None:
    """`max_visits` en metadata debe ser int >= 1 o estar ausente.

    `True` esta incluido a proposito y por un motivo concreto: en
    Python `isinstance(True, int)` es True, asi que un chequeo ingenuo
    acepta un booleano como limite de visitas. Y como `True == 1`, el
    nodo se queda con una sola visita sin que nadie lo haya pedido.
    """
    with pytest.raises(ValidationError, match="debe ser int >= 1 o ausente"):
        WorkflowNode(**_valid(metadata={"max_visits": bad}))


def test_max_visits_metadata_none_means_absent() -> None:
    """`max_visits` ausente, incluso declarado como None, no es un error.

    None significa "no declarado": `_declared_max_visits` lo traduce a
    la ausencia y el campo queda en None (ilimitado). Distinguirlo de
    un valor invalido es parte del contrato, no un caso accidental.
    """
    assert WorkflowNode(**_valid(metadata={"max_visits": None})).max_visits is None
