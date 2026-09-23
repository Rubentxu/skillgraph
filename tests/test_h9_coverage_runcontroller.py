"""H9-Coverage-8: cobertura de las ramas no ejercitadas de
`skillgraph.runtime.runcontroller` (94% -> >=95%).

Tras smoke empirico, las ramas marcadas como no cubiertas son:

- L257 (continue en bucle reconcile): rama inalcanzable por construccion
  (_execute_one retorna True solo si deja el node como SUCCEEDED o ya
  estaba SUCCEEDED via idempotencia; ambos casos hacen que
  `_latest_node_execution` retorne SUCCEEDED).
- L386-387 (last.state in {SUCCEEDED,FAILED,STOPPED,CANCELLED} -> []):
  inalcanzable por construccion (SUCCEEDED ya esta cubierto en el if
  previo; FAILED es manejado por el flujo que marca run FAILED terminal
  antes de re-entrar a _next_frontier; STOPPED/CANCELLED son dead).
- L410 (attempt > MAX_NODE_ATTEMPTS -> False): inalcanzable por el
  flujo normal (1ra falla marca run FAILED; no llega 2da invocacion).
  Solo seria alcanzable insertando FAILED rows manualmente via Storage
  para simular historia, pero eso es fragility.

Ramas ALCANZABLES que cubrimos:
- L369 (current is None en _next_frontier): 2do reconcile sobre run
  ya terminal COMPLETED.
- L625 (_node_has_execution): helper directo, True si existen
  executions; False si no.
- L628 (_count_executed): cuenta ejecuciones unicas; helper directo.

Spec: specs/h9-coverage-runcontroller.md.

Decisiones documentadas en spec:
- L257, L386-387, L410: dead code por construccion. NO testeamos
  mutando privates (fragilidad).
- L405 (idempotencia SUCCEEDED sin self-loop): dead code por
  construccion (SUCCEEDED+sin self-loop ya retorna [] en
  _next_frontier via L382, antes de que _execute_one sea llamado).
"""

from __future__ import annotations

from pathlib import Path

from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)
from skillgraph.runtime.agent import FakeAgentAdapter
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"


def _node(name: str, **kw: object) -> WorkflowNode:
    defaults: dict[str, object] = {
        "name": name,
        "kind": "ActionNode",
        "namespace": "shared",
        "api_version": "skillgraph.dev/v1alpha1",
        "resource_revision": 1,
        "expected_result": "ok",
    }
    defaults.update(kw)
    return WorkflowNode(**defaults)  # type: ignore[arg-type]


def _setup_run(tmp_path: Path) -> tuple[Storage, RunController, str]:
    """Crea un DAG lineal a->b terminado COMPLETED. Devuelve (storage, ctl, run_id)."""
    fx = tmp_path / "fx"
    fx.mkdir()
    for n in ("a", "b"):
        d = fx / TENANT / PROJECT
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{n}.json").write_text('{"outcome": "ok", "result": {"step": "x"}}')

    plan = WorkflowPlan(
        nodes=(_node("a"), _node("b")),
        transitions=(WorkflowTransition(source="a", outcome="ok", target="b"),),
        initial="a",
    )
    storage = Storage(tmp_path / "store.sqlite")
    ctl = RunController(storage=storage, adapter=FakeAgentAdapter(fx))
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
    # s1: ejecuta a -> SUCCEEDED, avanza current="b"
    ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    # s2: ejecuta b -> SUCCEEDED, run COMPLETED, current=None
    ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    return storage, ctl, run_id


# ---------------------------------------------------------------------------
# L369: _next_frontier con current is None (run terminal)
# ---------------------------------------------------------------------------


def test_next_frontier_returns_empty_when_run_completed(tmp_path: Path) -> None:
    """_calculate_frontier retorna [] cuando el run esta COMPLETED.

    Cubre L369 (`if current is None: return []`).
    """
    _, ctl, run_id = _setup_run(tmp_path)
    frontier = ctl._calculate_frontier(
        tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=_build_plan_for_completed_run()
    )
    assert frontier == []


def _build_plan_for_completed_run() -> WorkflowPlan:
    return WorkflowPlan(
        nodes=(_node("a"), _node("b")),
        transitions=(WorkflowTransition(source="a", outcome="ok", target="b"),),
        initial="a",
    )


# ---------------------------------------------------------------------------
# L625 + L628: helpers directos
# ---------------------------------------------------------------------------


def test_node_has_execution_true_and_count_executed(tmp_path: Path) -> None:
    """_node_has_execution True; _count_executed == 2 (a, b)."""
    _, ctl, run_id = _setup_run(tmp_path)
    assert ctl._node_has_execution(
        tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="a"
    )
    assert ctl._count_executed(tenant_id=TENANT, project_id=PROJECT, run_id=run_id) == 2


def test_node_has_execution_false_when_no_rows(tmp_path: Path) -> None:
    """_node_has_execution False para un nodo sin executions."""
    fx = tmp_path / "fx"
    fx.mkdir()
    plan = WorkflowPlan(
        nodes=(_node("a"),),
        initial="a",
    )
    storage = Storage(tmp_path / "store.sqlite")
    ctl = RunController(storage=storage, adapter=FakeAgentAdapter(fx))
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
    assert not ctl._node_has_execution(
        tenant_id=TENANT, project_id=PROJECT, run_id=run_id, node_name="a"
    )
    assert ctl._count_executed(tenant_id=TENANT, project_id=PROJECT, run_id=run_id) == 0
