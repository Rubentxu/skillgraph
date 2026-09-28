"""Red de seguridad para el refactor de `graph_expansion`.

El modulo tiene 98% de cobertura de lineas y 78 tests, pero eso mide
ejecucion, no contrato. Estos tests fijan el comportamiento observable
de las funciones que se van a separar, para que un refactor de forma
no pueda cambiar el resultado sin romper algo aqui.

Cubre los puntos calientes de `graph_expansion.py`:
- `_has_cycle_via_new_transitions` (cc=13) y `_cycle_source_nodes` (cc=6)
- `_check_cycle_bound` (cc=11)
- `DefaultPolicyEngine.evaluate` (cc=12), reglas P1..P5
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import pytest

from skillgraph.governance.graph_expansion import (
    AddNode,
    AddTransition,
    Authorization,
    DefaultPolicyEngine,
    GraphExpansionProposal,
    PolicyContext,
    PolicySettings,
    _check_cycle_bound,
    _cycle_source_nodes,
    _has_cycle_via_new_transitions,
    propose,
)
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

# --------------------------------------------------------------------------
# helpers de construccion
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


def _trans(src: str, tgt: str) -> WorkflowTransition:
    return WorkflowTransition(source=src, outcome="ok", target=tgt)


def _plan(nodes: tuple[WorkflowNode, ...], trans: tuple[WorkflowTransition, ...]) -> WorkflowPlan:
    """WorkflowPlan exige >=1 nodo, initial existente y aristas internas."""
    initial = nodes[0].name
    return WorkflowPlan(nodes=nodes, initial=initial, transitions=trans)


def _auth() -> Authorization:
    return Authorization(
        mode="manual_signed",
        granted_by="op@example.com",
        granted_at="2026-09-28T10:00:00Z",
    )


def _proposal(**kw: object) -> GraphExpansionProposal:
    """Construye una propuesta via `propose` (rechaza operations vacias).

    Los P2/P3 no miran las operations, asi que por defecto se mete un
    AddNode inocuo y se sobreescribe cuando el test necesita otra cosa.

    `proposal_id` es un UUIDv5 sobre (rev, tipos de ops, caps,
    attachment_point, author), asi que dos propuestas con los mismos
    campos tienen el MISMO id. Para simular concurrencia real hay que
    varyar alguno de esos, no solo el attachment_point.
    """
    base: dict[str, object] = {
        "operations": (AddNode(node=_node("extra")),),
        "attachment_point": "root",
        "scope": "NODE",
    }
    base.update(kw)
    return propose(
        base_revision=str(base.pop("base_revision", "rev-1")),
        problem_observed="test wi51",
        evidence=(),
        operations=base.pop("operations"),  # type: ignore[arg-type]
        capabilities_needed=base.pop("capabilities_needed", ()),  # type: ignore[arg-type]
        new_dependencies=base.pop("new_dependencies", ()),  # type: ignore[arg-type]
        attachment_point=str(base.pop("attachment_point")),  # type: ignore[arg-type]
        scope=str(base.pop("scope")),  # type: ignore[arg-type]
        authorization=_auth(),
        author=str(base.pop("author", "tester")),
        **base,  # type: ignore[arg-type]
    )


def _settings(**kw: object) -> PolicySettings:
    return PolicySettings(**kw)  # type: ignore[arg-type]


def _ctx(
    proposal: GraphExpansionProposal,
    *,
    plan: WorkflowPlan | None = None,
    concurrent: tuple[GraphExpansionProposal, ...] = (),
    registry: Mapping[str, str] | None = None,
    **settings: object,
) -> PolicyContext:
    return PolicyContext(
        proposal=proposal,
        plan=plan if plan is not None else _plan((_node("a"),), ()),
        registry=registry if registry is not None else {},
        concurrent_proposals=concurrent,
        settings=_settings(**settings),
    )


# --------------------------------------------------------------------------
# _has_cycle_via_new_transitions
# --------------------------------------------------------------------------


class TestHasCycleViaNewTransitions:
    def test_plan_minimo_no_tiene_ciclo(self) -> None:
        """WorkflowPlan no admite plan vacio: el caso minimo es un nodo."""
        assert _has_cycle_via_new_transitions((), (), _plan((_node("a"),), ())) is False

    def test_transicion_lineal_no_tiene_ciclo(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        assert _has_cycle_via_new_transitions((), (), plan) is False

    def test_ciclo_bidireccional_se_detecta(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"), _trans("b", "a")))
        assert _has_cycle_via_new_transitions((), (), plan) is True

    def test_transicion_nueva_cierra_ciclo(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        assert _has_cycle_via_new_transitions((), (_trans("b", "a"),), plan) is True

    def test_transicion_nueva_no_crea_ciclo(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        got = _has_cycle_via_new_transitions((_node("c"),), (_trans("b", "c"),), plan)
        assert got is False

    def test_auto_bucle_sobre_si_mismo(self) -> None:
        plan = _plan((_node("a"),), ())
        assert _has_cycle_via_new_transitions((), (_trans("a", "a"),), plan) is True

    def test_ciclo_en_componente_desconectada(self) -> None:
        plan = _plan(
            (_node("a"), _node("b"), _node("x"), _node("y")),
            (_trans("a", "b"), _trans("x", "y"), _trans("y", "x")),
        )
        assert _has_cycle_via_new_transitions((), (), plan) is True

    def test_camino_largo_sin_ciclo(self) -> None:
        nodes = tuple(_node(c) for c in "abcdef")
        trans = tuple(_trans(a, b) for a, b in zip("abcde", "bcdef", strict=True))
        assert _has_cycle_via_new_transitions((), (), _plan(nodes, trans)) is False

    def test_ciclo_de_tres_nodos(self) -> None:
        plan = _plan(
            (_node("a"), _node("b"), _node("c")),
            (_trans("a", "b"), _trans("b", "c"), _trans("c", "a")),
        )
        assert _has_cycle_via_new_transitions((), (), plan) is True

    def test_no_muta_el_plan(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        _has_cycle_via_new_transitions((), (), plan)
        assert plan.nodes[0].name == "a"
        assert len(plan.transitions) == 1


# --------------------------------------------------------------------------
# _cycle_source_nodes
# --------------------------------------------------------------------------


class TestCycleSourceNodes:
    def test_sin_ciclo_devuelve_vacio(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        assert _cycle_source_nodes((), (), plan) == ()

    def test_detecta_ambos_extremos_de_un_bidireccional(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"), _trans("b", "a")))
        assert set(_cycle_source_nodes((), (), plan)) == {"a", "b"}

    def test_ciclo_creado_por_transicion_nueva(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        assert set(_cycle_source_nodes((), (_trans("b", "a"),), plan)) == {"a", "b"}

    def test_camino_de_tres_no_es_ciclo(self) -> None:
        plan = _plan(
            (_node("a"), _node("b"), _node("c")),
            (_trans("a", "b"), _trans("b", "c")),
        )
        assert _cycle_source_nodes((), (), plan) == ()

    def test_no_muta_el_plan(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        _cycle_source_nodes((), (), plan)
        assert len(plan.nodes) == 2


# --------------------------------------------------------------------------
# _check_cycle_bound (I5)
# --------------------------------------------------------------------------


class TestCheckCycleBound:
    def test_sin_ciclo_no_viola_i5(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"),))
        proposal = _proposal(
            operations=(AddNode(node=_node("c")), AddTransition(transition=_trans("b", "c")))
        )
        assert _check_cycle_bound(proposal, plan) == ()

    def test_ciclo_sin_max_visits_viola_i5(self) -> None:
        plan = _plan((_node("a"), _node("b")), (_trans("a", "b"), _trans("b", "a")))
        proposal = _proposal(
            operations=(
                AddNode(node=_node("c")),
                AddTransition(transition=_trans("b", "a")),
            )
        )
        assert _check_cycle_bound(proposal, plan) == ("I5",)

    def test_ciclo_con_max_visits_adequate_no_viola_i5(self) -> None:
        a = replace(_node("a"), max_visits=2)
        b = replace(_node("b"), max_visits=2)
        plan = _plan((a, b), (_trans("a", "b"), _trans("b", "a")))
        proposal = _proposal(operations=(AddNode(node=_node("c")),))
        assert _check_cycle_bound(proposal, plan) == ()

    def test_ciclo_con_max_visits_en_solo_un_extremo_viola_i5(self) -> None:
        a = replace(_node("a"), max_visits=2)
        plan = _plan((a, _node("b")), (_trans("a", "b"), _trans("b", "a")))
        proposal = _proposal(operations=(AddNode(node=_node("c")),))
        assert _check_cycle_bound(proposal, plan) == ("I5",)

    def test_add_node_nuevo_en_ciclo_sin_max_visits_viola_i5(self) -> None:
        plan = _plan((_node("a"), _node("c2")), (_trans("a", "c2"),))
        proposal = _proposal(
            operations=(
                AddNode(node=_node("c2")),
                AddTransition(transition=_trans("a", "c2")),
                AddTransition(transition=_trans("c2", "a")),
            )
        )
        assert _check_cycle_bound(proposal, plan) == ("I5",)

    def test_nodo_nuevo_con_max_visits_adequate_no_viola_i5(self) -> None:
        a = replace(_node("a"), max_visits=2)
        c = replace(_node("c"), max_visits=3)
        plan = _plan((a,), ())
        proposal = _proposal(
            operations=(
                AddNode(node=c),
                AddTransition(transition=_trans("a", "c")),
                AddTransition(transition=_trans("c", "a")),
            )
        )
        assert _check_cycle_bound(proposal, plan) == ()


# --------------------------------------------------------------------------
# DefaultPolicyEngine.evaluate: reglas P1..P5
# --------------------------------------------------------------------------


class TestPolicyEvaluateHappyPath:
    def test_proposal_dentro_de_los_limites_acepta(self) -> None:
        decision = DefaultPolicyEngine().evaluate(_ctx(_proposal()))
        assert decision.accepted is True
        assert decision.violated_rules == ()
        assert decision.reason == "OK"


class TestPolicyEvaluateP1MaxOps:
    def test_supera_max_ops_viola_p1(self) -> None:
        ops = tuple(AddTransition(transition=_trans(f"n{i}", f"n{i + 1}")) for i in range(4))
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), max_ops_per_proposal=3)
        )
        assert decision.accepted is False
        assert any(r.startswith("P1:") for r in decision.violated_rules)

    def test_igual_a_max_ops_no_viola_p1(self) -> None:
        ops = tuple(AddTransition(transition=_trans(f"n{i}", f"n{i + 1}")) for i in range(3))
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), max_ops_per_proposal=3)
        )
        assert not any(r.startswith("P1:") for r in decision.violated_rules)

    def test_mensaje_p1_incluye_cantidades(self) -> None:
        ops = tuple(AddTransition(transition=_trans(f"n{i}", f"n{i + 1}")) for i in range(5))
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), max_ops_per_proposal=1)
        )
        assert "5 ops" in decision.reason
        assert "max_ops_per_proposal=1" in decision.reason


class TestPolicyEvaluateP2Concurrent:
    def test_mismo_attachment_point_viola_p2(self) -> None:
        other = _proposal(attachment_point="root", author="otro")
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(attachment_point="root"), concurrent=(other,))
        )
        assert any(r.startswith("P2:") for r in decision.violated_rules)

    def test_mismo_proposal_id_no_viola_p2(self) -> None:
        """Un proposal no compite consigo mismo."""
        mine = _proposal(attachment_point="root")
        same = replace(mine)
        decision = DefaultPolicyEngine().evaluate(_ctx(mine, concurrent=(same,)))
        assert not any(r.startswith("P2:") for r in decision.violated_rules)

    def test_distinto_attachment_point_no_viola_p2(self) -> None:
        other = _proposal(attachment_point="otro")
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(attachment_point="root"), concurrent=(other,))
        )
        assert not any(r.startswith("P2:") for r in decision.violated_rules)


class TestPolicyEvaluateP3Scope:
    def test_scope_fuera_de_allowlist_viola_p3(self) -> None:
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(scope="FLOW"), allowed_scopes=("NODE",))
        )
        assert any(r.startswith("P3:") for r in decision.violated_rules)

    def test_scope_dentro_de_allowlist_no_viola_p3(self) -> None:
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(scope="NODE"), allowed_scopes=("NODE",))
        )
        assert not any(r.startswith("P3:") for r in decision.violated_rules)

    def test_allowlist_vacia_no_viola_p3(self) -> None:
        decision = DefaultPolicyEngine().evaluate(_ctx(_proposal(scope="FLOW"), allowed_scopes=()))
        assert not any(r.startswith("P3:") for r in decision.violated_rules)


class TestPolicyEvaluateP4ForbiddenOps:
    def test_operacion_prohibida_viola_p4(self) -> None:
        ops = (AddNode(node=_node("z")),)
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), forbidden_ops=("AddNode",))
        )
        assert any(r.startswith("P4:") for r in decision.violated_rules)

    def test_operacion_permitida_no_viola_p4(self) -> None:
        ops = (AddNode(node=_node("z")),)
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), forbidden_ops=("RemoveNode",))
        )
        assert not any(r.startswith("P4:") for r in decision.violated_rules)

    def test_cada_operacion_prohibida_genera_una_violacion(self) -> None:
        ops = (AddNode(node=_node("z")), AddNode(node=_node("w")))
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), forbidden_ops=("AddNode",))
        )
        p4 = [r for r in decision.violated_rules if r.startswith("P4:")]
        assert len(p4) == 2


class TestPolicyEvaluateP5Budget:
    def test_proyecta_mas_nodos_de_lo_permitido_viola_p5(self) -> None:
        plan = _plan((_node("a"), _node("b")), ())
        ops = (AddNode(node=_node("c")), AddNode(node=_node("d")))
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), plan=plan, max_nodes_per_project=3)
        )
        assert any(r.startswith("P5:") for r in decision.violated_rules)

    def test_justo_en_el_limite_no_viola_p5(self) -> None:
        plan = _plan((_node("a"), _node("b")), ())
        ops = (AddNode(node=_node("c")),)
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), plan=plan, max_nodes_per_project=3)
        )
        assert not any(r.startswith("P5:") for r in decision.violated_rules)

    def test_solo_cuenta_addnode_no_addtransition(self) -> None:
        plan = _plan((_node("a"),), ())
        ops = (
            AddTransition(transition=_trans("a", "b")),
            AddTransition(transition=_trans("b", "c")),
        )
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), plan=plan, max_nodes_per_project=1)
        )
        assert not any(r.startswith("P5:") for r in decision.violated_rules)

    def test_mensaje_p5_reporta_proyectado_y_maximo(self) -> None:
        plan = _plan((_node("a"),), ())
        ops = (AddNode(node=_node("c")),)
        decision = DefaultPolicyEngine().evaluate(
            _ctx(_proposal(operations=ops), plan=plan, max_nodes_per_project=1)
        )
        assert "projected_nodes=2" in decision.reason
        assert "max_nodes_per_project=1" in decision.reason


class TestPolicyEvaluateComposition:
    def test_reporta_todas_las_violaciones_a_la_vez(self) -> None:
        ops = tuple(AddNode(node=_node(f"n{i}")) for i in range(4))
        other = _proposal(attachment_point="root")
        decision = DefaultPolicyEngine().evaluate(
            _ctx(
                _proposal(operations=ops, scope="FLOW", attachment_point="root"),
                plan=_plan((_node("a"),), ()),
                concurrent=(other,),
                max_ops_per_proposal=1,
                allowed_scopes=("NODE",),
                forbidden_ops=("AddNode",),
                max_nodes_per_project=1,
            )
        )
        prefixes = {r.split(":")[0] for r in decision.violated_rules}
        assert prefixes == {"P1", "P2", "P3", "P4", "P5"}

    def test_reason_une_las_violaciones_con_punto_y_coma(self) -> None:
        decision = DefaultPolicyEngine().evaluate(
            _ctx(
                _proposal(operations=(AddNode(node=_node("z")),), scope="FLOW"),
                allowed_scopes=("NODE",),
                max_ops_per_proposal=0,
            )
        )
        assert "; " in decision.reason

    def test_aceptar_deja_reason_ok(self) -> None:
        decision = DefaultPolicyEngine().evaluate(_ctx(_proposal()))
        assert decision.reason == "OK"

    def test_no_muta_el_contexto(self) -> None:
        ctx = _ctx(_proposal())
        before = (len(ctx.proposal.operations), len(ctx.concurrent_proposals))
        DefaultPolicyEngine().evaluate(ctx)
        assert (len(ctx.proposal.operations), len(ctx.concurrent_proposals)) == before


@pytest.mark.parametrize(
    ("trans", "expected"),
    [
        ((), False),
        ((("a", "b"),), False),
        ((("a", "b"), ("b", "a")), True),
    ],
)
def test_parametrico_deteccion_de_ciclo(trans: tuple[tuple[str, str], ...], expected: bool) -> None:
    names = tuple(sorted({n for t in trans for n in t})) or ("solo",)
    plan = _plan(tuple(_node(n) for n in names), tuple(_trans(*t) for t in trans))
    assert _has_cycle_via_new_transitions((), (), plan) is expected
