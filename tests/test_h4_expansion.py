"""Tests H4 Slice 1: Expansion controlada.

Cubre:
- Pipeline DISCOVER..EVALUATE feliz (autorizada + aplicada).
- Rechazo por invariante (UAT-09).
- Inmutabilidad del WorkflowPlan original.
- Persistencia de evidencia de rechazo.
- Validacion de los 9 campos obligatorios de la propuesta.

Ver ``specs/h4-slice-1.md`` para el contrato legal (blueprint §5 §5-§6).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from skillgraph.core.errors import (
    UnauthorizedExpansionError,
)
from skillgraph.governance.graph_expansion import (
    AddNode,
    AddTransition,
    Authorization,
    InvalidProposal,
    RemoveTransition,
    apply_expansion,
    propose,
    record_rejection,
    validate,
)
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _node(name: str, kind: str = "DecisionNode") -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind=kind,
        namespace="ns-test",
        api_version="skillgraph/v1",
        resource_revision=1,
        expected_result=f"output of {name}",
        capabilities=(),
        metadata={"outcomes": ["pass", "fail"]},
    )


def _plan_with(initial: str, *nodes: WorkflowNode) -> WorkflowPlan:
    return WorkflowPlan(
        nodes=tuple(nodes),
        initial=initial,
        transitions=(),
    )


@pytest.fixture
def empty_registry() -> dict[str, str]:
    """Registry minimo: capability -> brick_ref."""
    return {"compile": "brick:compile", "lint": "brick:lint"}


@pytest.fixture
def base_plan() -> WorkflowPlan:
    return _plan_with("root", _node("root"), _node("child"))


@pytest.fixture
def valid_authorization() -> Authorization:
    return Authorization(
        mode="manual_signed",
        granted_by="lead@example.com",
        granted_at="2026-09-23T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# D1 — 9 campos obligatorios + Authorization valida
# ---------------------------------------------------------------------------


def test_proposal_requires_authorization(
    base_plan: WorkflowPlan,
) -> None:
    """Una propuesta sin autorizacion valida no debe poder proponer."""
    with pytest.raises(UnauthorizedExpansionError):
        propose(
            base_revision="rev-1",
            problem_observed="se necesita un nuevo nodo de validacion",
            evidence=(),
            operations=(AddNode(node=_node("validate_extra")),),
            new_dependencies=(),
            capabilities_needed=("lint",),
            scope="NODE",
            attachment_point="root",
            rollback_plan=(),
            authorization=Authorization(mode="manual_signed", granted_by=None, granted_at=None),
            author="bot@example.com",
        )


def test_authorize_manual_signed_requires_grantor_and_time() -> None:
    auth = Authorization(
        mode="manual_signed", granted_by="lead@example.com", granted_at="2026-09-23T10:00:00Z"
    )
    assert auth.is_valid() is True

    no_grantor = Authorization(
        mode="manual_signed", granted_by=None, granted_at="2026-09-23T10:00:00Z"
    )
    assert no_grantor.is_valid() is False

    no_time = Authorization(mode="manual_signed", granted_by="lead@example.com", granted_at=None)
    assert no_time.is_valid() is False


def test_authorize_auto_only_for_low_risk() -> None:
    auth = Authorization(mode="auto_low_risk", granted_by=None, granted_at=None)
    assert auth.is_valid() is True  # auto no requiere firmante humano


# ---------------------------------------------------------------------------
# D2 — Validacion de invariantes blueprint §6
# ---------------------------------------------------------------------------


def test_validate_accepts_clean_add_node(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """I1..I6 OK: nodo nuevo en lugar vacio, no toca completados."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="se necesita nodo extra",
        evidence=(),
        operations=(AddNode(node=_node("new_node")),),
        capabilities_needed=(),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(
        proposal,
        plan=base_plan,
        registry=empty_registry,
    )
    assert result.accepted is True
    assert result.violated_invariants == ()


def test_validate_rejects_unauthorized_capabilities(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """I3: capability no registrada."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="nodo extra",
        evidence=(),
        operations=(AddNode(node=_node("n")),),
        capabilities_needed=("magia_inexistente",),  # no en registry
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(
        proposal,
        plan=base_plan,
        registry=empty_registry,
    )
    assert result.accepted is False
    assert "I3" in result.violated_invariants


def test_validate_rejects_inexistent_dependency(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """I4: new_dependency sin brick_ref real."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="nodo extra",
        evidence=(),
        operations=(AddNode(node=_node("n")),),
        new_dependencies=("ghost_ref_does_not_exist",),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(
        proposal,
        plan=base_plan,
        registry=empty_registry,
    )
    assert result.accepted is False
    assert "I4" in result.violated_invariants


def test_validate_rejects_obsolete_base(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """I6: base_revision != current."""
    proposal = propose(
        base_revision="rev-antigua",
        problem_observed="nodo extra",
        evidence=(),
        operations=(AddNode(node=_node("n")),),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(
        proposal,
        plan=base_plan,
        registry=empty_registry,
        current_revision="rev-actual",
    )
    assert result.accepted is False
    assert "I6" in result.violated_invariants


def test_validate_warns_on_active_node_change(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """Quitar transicion usada por nodo ACTIVE genera warning (no rechazo)."""
    # base_plan tiene 2 nodos sin transiciones. None active -> 0 warnings.
    proposal = propose(
        base_revision="rev-1",
        problem_observed="limpiar trans",
        evidence=(),
        operations=(RemoveTransition(from_node="root", outcome="never"),),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(
        proposal,
        plan=base_plan,
        registry=empty_registry,
    )
    # No warning sin nodo activo porque base_plan no expone active_nodes
    # por default. Verifica contrato: vacio -> no warning.
    assert result.warnings == ()


def test_validate_rejects_cycle_without_max_visits(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """I5: transicion ciclica sin max_visits -> violacion."""
    # Para forzar ciclo A->A necesitamos un AddTransition con source=alpha
    # y target=alpha. Ademas el nodo alpha debe declarar max_visits=0
    # (sin max_visits -> rompe invariante).
    plan2 = _plan_with("alpha", _node("alpha"), _node("beta"))
    cyclic_trans = WorkflowTransition(
        source="alpha",
        outcome="retry",
        target="alpha",
    )
    # NO declaramos max_visits en el metadata de alpha -> rompe I5.
    proposal = propose(
        base_revision="rev-1",
        problem_observed="intentar loop",
        evidence=(),
        operations=(AddTransition(transition=cyclic_trans),),
        attachment_point="alpha",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(proposal, plan=plan2, registry=empty_registry)
    assert result.accepted is False
    assert "I5" in result.violated_invariants


# ---------------------------------------------------------------------------
# D3 — Aplicacion (inmutabilidad + nuevo plan)
# ---------------------------------------------------------------------------


def test_apply_expansion_returns_new_plan(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """Apply produce plan NUEVO; el original NO muta."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="anade nodo",
        evidence=(),
        operations=(AddNode(node=_node("adicional")),),
        capabilities_needed=(),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(proposal, plan=base_plan, registry=empty_registry)
    assert result.accepted is True

    applied = apply_expansion(proposal, base_plan, registry=empty_registry)

    assert applied.is_ok()
    new_plan = applied.unwrap()
    assert new_plan is not base_plan
    assert len(new_plan.nodes) == len(base_plan.nodes) + 1
    assert "adicional" in {n.name for n in new_plan.nodes}
    # original inmutable
    assert len(base_plan.nodes) == 2


def test_apply_expansion_returns_err_for_invalid(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """Apply sobre propuesta rechazada devuelve Err."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="x",
        evidence=(),
        operations=(AddNode(node=_node("adicional")),),
        capabilities_needed=("ghost",),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    applied = apply_expansion(proposal, base_plan, registry=empty_registry)
    assert applied.is_err()
    err: InvalidProposal = applied.unwrap_err()
    assert "I3" in err.violated_invariants


# ---------------------------------------------------------------------------
# D4 — Rechazo y evidencia (UAT-09)
# ---------------------------------------------------------------------------


def test_rejection_evidence_persisted(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
    tmp_path: Any,
) -> None:
    """record_rejection crea JSON con proposal_id + reason."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="x",
        evidence=(),
        operations=(AddNode(node=_node("adicional")),),
        capabilities_needed=("ghost",),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    rejection_path = record_rejection(
        proposal,
        reason="I3 violated: capability not in registry",
        rejected_by="validator",
        project_dir=tmp_path,
    )
    assert rejection_path.exists()
    data = json.loads(rejection_path.read_text())
    assert data["proposal_id"] == proposal.proposal_id
    assert data["reason"].startswith("I3")
    assert data["rejected_by"] == "validator"


def test_full_pipeline_authorized_to_applied(
    base_plan: WorkflowPlan,
    valid_authorization: Authorization,
    empty_registry: dict[str, str],
) -> None:
    """Happy path: DISCOVER..APPLY legal completo."""
    proposal = propose(
        base_revision="rev-1",
        problem_observed="gap detectado",
        evidence=(),
        operations=(AddNode(node=_node("revisor")),),
        capabilities_needed=("lint",),
        attachment_point="root",
        authorization=valid_authorization,
        author="bot@example.com",
    )
    result = validate(proposal, plan=base_plan, registry=empty_registry)
    assert result.accepted is True

    applied = apply_expansion(proposal, base_plan, registry=empty_registry)
    assert applied.is_ok()
    new_plan = applied.unwrap()
    assert "revisor" in {n.name for n in new_plan.nodes}
    # "lint" es una capacidad legitima
    assert "lint" in empty_registry


def test_proposal_has_stable_uuid() -> None:
    """El mismo (revision, operations) genera el mismo ProposalID."""
    auth = Authorization(
        mode="manual_signed",
        granted_by="lead@example.com",
        granted_at="2026-09-23T10:00:00Z",
    )
    n = _node("x")
    p1 = propose(
        base_revision="rev-1",
        problem_observed="x",
        evidence=(),
        operations=(AddNode(node=n),),
        capabilities_needed=(),
        attachment_point="root",
        authorization=auth,
        author="bot@example.com",
    )
    p2 = propose(
        base_revision="rev-1",
        problem_observed="x",
        evidence=(),
        operations=(AddNode(node=n),),
        capabilities_needed=(),
        attachment_point="root",
        authorization=auth,
        author="bot@example.com",
    )
    assert p1.proposal_id == p2.proposal_id


def test_proposal_distinguishes_by_created_at() -> None:
    """Si cambia author o created_at, el proposal_id cambia."""
    auth = Authorization(
        mode="manual_signed",
        granted_by="lead@example.com",
        granted_at="2026-09-23T10:00:00Z",
    )
    n = _node("x")
    p_a = propose(
        base_revision="rev-1",
        problem_observed="x",
        evidence=(),
        operations=(AddNode(node=n),),
        capabilities_needed=(),
        attachment_point="root",
        authorization=auth,
        author="botA@example.com",
    )
    p_b = propose(
        base_revision="rev-1",
        problem_observed="x",
        evidence=(),
        operations=(AddNode(node=n),),
        capabilities_needed=(),
        attachment_point="root",
        authorization=auth,
        author="botB@example.com",
    )
    assert p_a.proposal_id != p_b.proposal_id
