"""Subcomando `sg run` y su orquestacion (WI-55, ADR-0018).

Sexto corte del estrangulamiento H-02: `cmd_run` y sus helpers
(`_resolve_run_inputs`, `_reconcile_until_terminal`, `_build_adapter`,
`_find_active_run_id`, `_resolve_fixtures_root`) salen de
`cli/runner.py` verbatim. Con este corte runner queda por debajo del
umbral de god file (>800 LoC) del audit de deuda.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skillgraph.cli.support import (
    EXIT_DB_MISSING,
    EXIT_OK,
    EXIT_PARSE,
    EXIT_PLAN_NOT_FOUND,
    EXIT_RUN_FAILED,
    EXIT_RUN_INCOMPLETE,
    resolve_project,
)
from skillgraph.core.errors import ParseError
from skillgraph.platform.paths import agents_root, resolve_data_root
from skillgraph.platform.storage import Storage
from skillgraph.resources.plan_loader import load_plan_file

if TYPE_CHECKING:
    from skillgraph.runtime.runcontroller import RunController


def _resolve_run_inputs(
    args: argparse.Namespace,
) -> tuple[RunController, Storage, str, str, str, str]:
    """Valida input + construye controller + Run (nuevo o resumed).

    Returns:
        Tupla ``(ctl, storage, run_id, tenant_id, project_name,
        project_db_error, plan_or_None)``. ``project_db_error`` es el
    exit code si algo fallo (no-None), y ``plan_or_None`` es None en
    el caso de fallo (el caller propaga el error al usuario).
    """
    from skillgraph.runtime.runcontroller import RunBudget, RunController

    project, err = resolve_project(args, args.project)
    if err is not None:
        return None, None, None, None, None, err
    if not args.plan.is_file():
        print(
            f"ERROR: plan no encontrado: {args.plan}",
            file=sys.stderr,
        )
        return None, None, None, None, None, EXIT_PLAN_NOT_FOUND
    try:
        plan = load_plan_file(args.plan)
    except ParseError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return None, None, None, None, None, EXIT_PARSE
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        return None, None, None, None, None, EXIT_DB_MISSING

    fixtures_root = args.fixtures_root or agents_root(resolve_data_root(args.data_root))
    fixtures_root.mkdir(parents=True, exist_ok=True)
    adapter = _build_adapter(args, fixtures_root)
    storage = Storage(db_path)
    ctl = RunController(
        runs=storage,
        events=storage,
        policy=storage,
        adapter=adapter,
    )

    # Resume-or-start: si ya existe un Run no terminal para este
    # proyecto, lo reanudamos. Asi el usuario puede re-invocar
    # `run` tras un crash y el controller reanuda el mismo Run
    # con su current_node y sus NodeExecutions. Cumple UAT-06.
    existing_run_id = _find_active_run_id(
        storage,
        tenant_id=project["tenant_id"],
        project_id=project["name"],
    )
    if existing_run_id is not None:
        run_id = existing_run_id
    else:
        # S4 Etapa 7: construye RunBudget solo si el usuario paso
        # al menos un limite. Si los tres son None, budget=None
        # (compat con Runs anteriores).
        budget: RunBudget | None = None
        if any(
            v is not None
            for v in (
                args.budget_visits,
                args.budget_runtime_seconds,
                args.budget_events,
            )
        ):
            budget = RunBudget(
                max_visits=args.budget_visits,
                max_runtime_seconds=args.budget_runtime_seconds,
                max_events=args.budget_events,
            )
        run_id = ctl.create_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            plan=plan,
            budget=budget,
        )
    return (
        ctl,
        storage,
        run_id,
        project["tenant_id"],
        project["name"],
        None,
    )


def _reconcile_until_terminal(
    ctl: RunController,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    max_iterations: int,
) -> tuple[str, str, tuple[str, ...], int, bool]:
    """Bucle de reconciliacion hasta terminal o max_iterations.

    Returns:
        Tupla ``(state, current_node, executed_nodes_tuple,
        events_emitted, hit_max_iterations)``.
    """
    from skillgraph.core.runtime_types import is_terminal_run_state

    iterations = 1
    snap = ctl.reconcile_run(
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
    )
    while not is_terminal_run_state(snap.state) and iterations < max_iterations:
        iterations += 1
        snap = ctl.reconcile_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
    hit_max = not is_terminal_run_state(snap.state) and iterations >= max_iterations
    if hit_max:
        print(
            f"WARN: max-iterations alcanzado ({max_iterations}); "
            f"estado={snap.state} current={snap.current_node}",
            file=sys.stderr,
        )
    return (
        snap.state,
        snap.current_node,
        tuple(snap.executed_nodes),
        snap.events_emitted,
        hit_max,
    )


def cmd_run(args: argparse.Namespace) -> int:
    """Crea un Run desde un WorkflowPlan.md y reconcilia hasta terminal.

    Cierra H2 por la via UAT: el usuario real ejecuta el CLI.
    """
    ctl, storage, run_id, tenant_id, project_name, early_exit = _resolve_run_inputs(args)
    if early_exit is not None:
        return early_exit

    try:
        state, _current_node, executed_nodes, events_emitted, _hit_max = _reconcile_until_terminal(
            ctl,
            tenant_id=tenant_id,
            project_id=project_name,
            run_id=run_id,
            max_iterations=args.max_iterations,
        )
    finally:
        storage.close()

    print(f"Run: {run_id}")
    print(f"Estado: {state}")
    print(f"Nodos ejecutados: {', '.join(executed_nodes) or '(ninguno)'}")
    print(f"Eventos emitidos: {events_emitted}")
    adapter_kind = getattr(args, "adapter", "fake")
    print(f"Tipo de adapter: {adapter_kind}")
    print(f"Fixtures de agente: {_resolve_fixtures_root(args)}")
    # Codigos distintos segun estado para que el shell pueda
    # ramificar sin parsear la salida.
    if state == "COMPLETED":
        return EXIT_OK
    if state == "FAILED":
        return EXIT_RUN_FAILED
    return EXIT_RUN_INCOMPLETE


def _build_adapter(args: argparse.Namespace, fixtures_root: Path) -> Any:
    """Construye el adapter segun --adapter (fake | http).

    fake: FakeAgentAdapter con fixtures_root (default; comportamiento
        historico, determinista).
    http: HttpAgentAdapter leyendo ANTHROPIC_API_KEY o OPENAI_API_KEY
        del entorno segun --llm-provider.

    Raises:
        SkillGraphError (via http_adapter_from_env) si --adapter=http
        y la variable de entorno del proveedor no esta definida.
    """
    from skillgraph.core.errors import ValidationError
    from skillgraph.runtime.agent import FakeAgentAdapter

    kind = getattr(args, "adapter", "fake")
    if kind == "fake":
        return FakeAgentAdapter(fixtures_root)
    if kind == "http":
        from skillgraph.runtime.http_adapter import http_adapter_from_env

        provider = getattr(args, "llm_provider", "anthropic")
        model = getattr(args, "llm_model", None)
        timeout_s = getattr(args, "llm_timeout_s", 30.0)
        adapter = http_adapter_from_env(provider, model=model)
        # Override timeout si el usuario lo especifico.
        if timeout_s != 30.0:
            object.__setattr__(adapter, "timeout_s", timeout_s)
        return adapter
    # argparse normalmente bloquea esto via choices=['fake','http'];
    # este error existe para usos programaticos sin argparse.
    raise ValidationError(f"adapter invalido: {kind!r} (esperado: 'fake' | 'http')")


def _find_active_run_id(storage: Storage, *, tenant_id: str, project_id: str) -> str | None:
    """Devuelve el run_id del Run mas reciente en estado no terminal
    para (tenant, project), o None si no hay ninguno.

    No terminal = CREATED, ACTIVE o WAITING (ver
    ``Storage.NON_TERMINAL_RUN_STATES``). COMPLETED/FAILED/CANCELLED
    se consideran terminales y el siguiente `run` debe crear uno nuevo.
    Cumple UAT-06: tras un crash con un run ACTIVE, el CLI lo encuentra
    y lo reanuda en lugar de crear uno nuevo.

    Refactor H9-BSlice2: delega en ``Storage.find_active_run`` (API publica).
    """
    return storage.find_active_run(tenant_id=tenant_id, project_id=project_id)


def _resolve_fixtures_root(args: argparse.Namespace) -> Path:
    """Resuelve el fixtures_root final tras defaults (sigue a cmd_run)."""
    fixtures_root = args.fixtures_root or agents_root(resolve_data_root(args.data_root))
    fixtures_root.mkdir(parents=True, exist_ok=True)
    return fixtures_root
