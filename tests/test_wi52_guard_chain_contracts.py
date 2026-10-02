"""Red de contrato para las dos cadenas de guardas que quedan.

`WorkflowPlan.__post_init__` (cc=12) y `ValidationReceipt.__post_init__`
(cc=11) estan ya al 100 por ciento de lineas cubiertas por los tests
existentes, y eso no dice nada del contrato: mide que se ejecuten,
no que ganen el error correcto cuando hay varios fallos a la vez.

Estos tests fijan el orden de evaluacion de las guardas, que es
observable, y los bordes exactos de cada regla.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.governance.receipts import ValidationReceipt
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _node(name: str, **kw: object) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="ns",
        api_version="v1",
        resource_revision=1,
        expected_result="r",
        **kw,  # type: ignore[arg-type]
    )


def _trans(src: str, tgt: str, outcome: str = "ok") -> WorkflowTransition:
    return WorkflowTransition(source=src, outcome=outcome, target=tgt)


def _plan(nodes: tuple[WorkflowNode, ...], trans: tuple[WorkflowTransition, ...]) -> WorkflowPlan:
    return WorkflowPlan(nodes=nodes, initial=nodes[0].name, transitions=trans)


def _receipt(**kw: object) -> ValidationReceipt:
    base: dict[str, object] = {
        "receipt_id": "r-1",
        "command": "pytest",
        "revision": "abc123",
        "timestamp": "2026-09-28T10:00:00Z",
        "verdict": "pass",
        "tests_run": 10,
        "tests_passed": 10,
        "artifact_path": "/tmp/a.json",
        "scope": "unit",
    }
    base.update(kw)
    return ValidationReceipt(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# WorkflowPlan.__post_init__
# --------------------------------------------------------------------------


class TestWorkflowPlanHappyPath:
    def test_plan_minimo_valido(self) -> None:
        plan = _plan((_node("a"),), ())
        assert plan.initial == "a"
        assert plan.transitions == ()

    def test_plan_con_transicion_interna_valido(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        assert len(plan.transitions) == 1

    def test_auto_bucle_interno_valido(self) -> None:
        plan = _plan((_node("a"),), (_trans("a", "a"),))
        assert len(plan.transitions) == 1


class TestWorkflowPlanNodes:
    def test_plan_sin_nodos_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="sin nodos"):
            WorkflowPlan(nodes=(), initial="a", transitions=())

    def test_initial_vacio_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="initial vacio"):
            WorkflowPlan(nodes=(_node("a"),), initial="", transitions=())

    def test_initial_inexistente_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="no es un nodo del plan"):
            WorkflowPlan(nodes=(_node("a"),), initial="z", transitions=())

    def test_plan_sin_nodos_gana_sobre_initial_invalido(self) -> None:
        """El orden es observable: sin nodos se queixa de nodos primero."""
        with pytest.raises(ValidationError, match="sin nodos"):
            WorkflowPlan(nodes=(), initial="", transitions=())


class TestWorkflowPlanTransitionEndpoints:
    def test_source_inexistente_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"source .* no es nodo"):
            _plan((_node("a"),), (_trans("z", "a"),))

    def test_target_inexistente_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"target .* no es nodo"):
            _plan((_node("a"),), (_trans("a", "z"),))

    def test_source_gana_sobre_target_invalido(self) -> None:
        """Ambas aristas malas en la misma transicion: gana `source`."""
        with pytest.raises(ValidationError, match="source"):
            _plan((_node("a"),), (_trans("z", "y"),))

    def test_source_invalido_gana_sobre_outcome_no_declarado(self) -> None:
        """Las aristas se validan antes que los outcomes declarados."""
        src = _node("a", outcomes=("ok",))
        with pytest.raises(ValidationError, match=r"source .* no es nodo"):
            _plan((src, _node("b")), (_trans("z", "b", outcome="nope"),))


class TestWorkflowPlanDeclaredOutcomes:
    def test_outcome_no_declarado_rechazado(self) -> None:
        src = _node("a", outcomes=("ok",))
        with pytest.raises(ValidationError, match="no esta en outcomes declarados"):
            _plan((src, _node("b")), (_trans("a", "b", outcome="nope"),))

    def test_outcome_declarado_aceptado(self) -> None:
        src = _node("a", outcomes=("ok", "fail"))
        plan = _plan((src, _node("b")), (_trans("a", "b", outcome="fail"),))
        assert plan.transitions[0].outcome == "fail"

    def test_nodo_sin_outcomes_declarados_acepta_cualquiera(self) -> None:
        """Sin declaracion no hay restriccion: es el caso por defecto."""
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b", outcome="cualquier"),))
        assert plan.transitions[0].outcome == "cualquier"

    def test_metadata_outcomes_alimenta_la_validacion(self) -> None:
        """`metadata` es la verdad: sus outcomes restringen la transicion."""
        src = _node("a", metadata={"outcomes": ["ok", "fail"]})
        with pytest.raises(ValidationError, match="no esta en outcomes declarados"):
            _plan((src, _node("b")), (_trans("a", "b", outcome="nope"),))

    def test_nodo_sin_outcomes_loguea_la_comprobacion(self) -> None:
        """DecisionNode sin outcomes declarados es invalido (H4)."""
        from skillgraph.resources.workflow import _declared_outcomes

        assert _declared_outcomes({}) == ()
        assert _declared_outcomes({"outcomes": ["a", "b"]}) == ("a", "b")


# --------------------------------------------------------------------------
# ValidationReceipt.__post_init__
# --------------------------------------------------------------------------


class TestReceiptHappyPath:
    def test_recibo_valido_pasa(self) -> None:
        receipt = _receipt()
        assert receipt.verdict == "pass"
        assert receipt.is_pass is True

    def test_verdict_fail_valido(self) -> None:
        receipt = _receipt(verdict="fail")
        assert receipt.is_pass is False

    def test_recibo_con_dependencias_valido(self) -> None:
        receipt = _receipt(dependency_revisions={"a": "sha"})
        assert receipt.dependency_revisions == {"a": "sha"}


class TestReceiptRequiredFields:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("receipt_id", "receipt_id vacio"),
            ("command", "command vacio"),
            ("revision", "revision vacia"),
            ("timestamp", "timestamp vacio"),
            ("artifact_path", "artifact_path vacio"),
            ("scope", "scope vacio"),
        ],
    )
    def test_campo_obligatorio_vacio_rechazado(self, field: str, expected: str) -> None:
        with pytest.raises(ValidationError, match=expected):
            _receipt(**{field: ""})

    def test_receipt_id_vacio_gana_sobre_command_vacio(self) -> None:
        """El orden de las guardas de campo vacio es observable."""
        with pytest.raises(ValidationError, match="receipt_id vacio"):
            _receipt(receipt_id="", command="")


class TestReceiptVerdict:
    def test_verdict_invalido_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="verdict invalido"):
            _receipt(verdict="PASS")

    def test_verdict_vacio_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="verdict invalido"):
            _receipt(verdict="")

    def test_verdict_no_string_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="verdict invalido"):
            _receipt(verdict=1)


class TestReceiptCounters:
    def test_tests_run_negativo_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="tests_run negativo"):
            _receipt(tests_run=-1, tests_passed=0)

    def test_tests_passed_negativo_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="tests_passed negativo"):
            _receipt(tests_run=5, tests_passed=-1)

    def test_passed_mayor_que_run_rechazado(self) -> None:
        with pytest.raises(ValidationError, match=r"tests_passed .* > tests_run"):
            _receipt(tests_run=5, tests_passed=6)

    def test_passed_igual_a_run_aceptado(self) -> None:
        receipt = _receipt(tests_run=5, tests_passed=5)
        assert receipt.tests_passed == 5

    def test_run_cero_con_passed_cero_aceptado(self) -> None:
        receipt = _receipt(tests_run=0, tests_passed=0)
        assert receipt.tests_run == 0

    def test_tests_run_negativo_gana_sobre_passed_negativo(self) -> None:
        with pytest.raises(ValidationError, match="tests_run negativo"):
            _receipt(tests_run=-1, tests_passed=-2)

    def test_run_negativo_gana_sobre_passed_mayor_que_run(self) -> None:
        with pytest.raises(ValidationError, match="tests_run negativo"):
            _receipt(tests_run=-1, tests_passed=5)

    def test_bool_como_contador_rechazado(self) -> None:
        """`bool` se rechaza como contador desde WI-49 (release v0.16.9).

        Este test fijaba ANTES la coercion `True` -> 1 "preservada por
        comparacion"; WI-49 convirtio esa preservacion en rechazo
        explicito porque el cross-check solo la detectaba en una
        direccion (`tests_run=True` con `tests_passed<=1` pasaba en
        silencio). Red de regresion del cambio de contrato.
        """
        with pytest.raises(ValidationError, match="tests_run debe ser int, no bool"):
            _receipt(tests_run=True, tests_passed=0)
        with pytest.raises(ValidationError, match="tests_passed debe ser int, no bool"):
            _receipt(tests_run=0, tests_passed=True)


class TestReceiptFieldOrder:
    def test_campo_vacio_gana_sobre_verdict_invalido(self) -> None:
        with pytest.raises(ValidationError, match="command vacio"):
            _receipt(command="", verdict="INVALID")

    def test_verdict_invalido_gana_sobre_contadores_invalidos(self) -> None:
        with pytest.raises(ValidationError, match="verdict invalido"):
            _receipt(verdict="INVALID", tests_run=-1, tests_passed=-1)

    def test_contadores_ganan_sobre_artifact_path_vacio(self) -> None:
        with pytest.raises(ValidationError, match="tests_run negativo"):
            _receipt(tests_run=-1, artifact_path="")


class TestReceiptImmutability:
    def test_replace_reevalida(self) -> None:
        """`replace` vuelve a pasar por __post_init__: no es un escape."""
        receipt = _receipt()
        with pytest.raises(ValidationError, match="tests_run negativo"):
            replace(receipt, tests_run=-1)

    def test_extra_metadata_libre_no_se_valida(self) -> None:
        receipt = _receipt(extra_metadata={"cualquier": [1, 2]})
        assert receipt.extra_metadata == {"cualquier": [1, 2]}
