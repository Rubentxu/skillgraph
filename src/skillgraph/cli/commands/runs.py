"""Subcomandos `sg runs` (WI-53, ADR-0018).

Segundo corte del estrangulamiento H-02: los 5 handlers `cmd_runs_*`
salen de `cli/runner.py` verbatim (lazy imports incluidos). `runner`
conserva alias para su tabla de dispatch y sus usos internos de
`_open_project_storage`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skillgraph.cli.support import (
    EXIT_DOMAIN,
    EXIT_OK,
    _open_project_storage,
    resolve_project,
)


def cmd_runs_list(args: argparse.Namespace) -> int:
    """Lista Runs del proyecto via `RunController.list_runs`.

    Read-only: no emite eventos. Salida CSV-like para legibilidad
    en shell (una linea por run con columnas estables).
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=FakeAgentAdapter(Path("/dev/null")),  # list no invoca adapter
        )
        runs = ctl.list_runs(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            state=args.state,
            limit=args.limit,
        )
        if not runs:
            print("(sin runs)")
            return EXIT_OK
        print(f"{'run_id':<40} {'state':<11} {'current_node':<20} {'executed':<10} {'events':<8}")
        for r in runs:
            print(
                f"{r.run_id:<40} {r.state:<11} "
                f"{(r.current_node or '-'):<20} "
                f"{','.join(r.executed_nodes):<10} {r.events_emitted:<8}"
            )
        return EXIT_OK


def cmd_runs_show(args: argparse.Namespace) -> int:
    """Muestra el snapshot de un Run via `RunController.show_run`.

    Read-only: no emite eventos. Salida en formato key=value para
    que un caller shell pueda parsear con awk/cut.
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=FakeAgentAdapter(Path("/dev/null")),  # show no invoca adapter
        )
        snap = ctl.show_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=args.run_id,
        )
        print(f"run_id={snap.run_id}")
        print(f"state={snap.state}")
        print(f"current_node={snap.current_node or '-'}")
        print(f"executed_nodes={','.join(snap.executed_nodes) or '-'}")
        print(f"events_emitted={snap.events_emitted}")
        return EXIT_OK


def cmd_runs_logs(args: argparse.Namespace) -> int:
    """Muestra el timeline de eventos de un Run via `RunController.logs_run`.

    Read-only: no emite eventos. Salida CSV-like con una linea por
    evento: `seq event_kind timestamp payload_summary`.
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=FakeAgentAdapter(Path("/dev/null")),  # logs no invoca adapter
        )
        logs = ctl.logs_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=args.run_id,
        )
        if args.limit is not None:
            logs = logs[: args.limit]
        if not logs:
            print("(sin eventos)")
            return EXIT_OK
        print(f"{'seq':<6} {'event_kind':<22} {'timestamp':<26} payload")
        for entry in logs:
            # Resumen corto del payload (primer nivel clave=valor).
            kv = ",".join(f"{k}={v!s:.40}" for k, v in entry.event.payload.items())
            print(
                f"{entry.sequence:<6} {entry.event.event_kind:<22} {entry.event.timestamp:<26} {kv}"
            )
        return EXIT_OK


def cmd_runs_cancel(args: argparse.Namespace) -> int:
    """Cancela un Run existente via `RunController.cancel_run`.

    No necesita Adapter: la cancelacion ocurre en la capa de
    orquestacion sin volver a invocar al agente. La operacion
    es atomica (transicion de estado + evento RunCompleted en
    una sola TX, via `transition_run_state_atomically`).
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=FakeAgentAdapter(Path("/dev/null")),  # cancel no invoca adapter
        )
        snap = ctl.cancel_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=args.run_id,
        )
        print(f"run_id={snap.run_id} state={snap.state}")
        return EXIT_OK


def cmd_runs_budget(args: argparse.Namespace) -> int:
    """Muestra el RunBudget activo de un Run (S4 Etapa 7).

    Read-only: NO emite eventos. Si el Run no tiene budget, imprime
    `(sin budget)`. Salida key=value parseable con awk/cut.
    """
    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        # Validamos existencia del Run con un try/except explicito para
        # emitir un mensaje de error claro cuando es NotFoundError.
        from skillgraph.core.errors import NotFoundError

        try:
            storage.get_run(
                tenant_id=project["tenant_id"],
                project_id=project["name"],
                run_id=args.run_id,
            )
        except NotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return EXIT_DOMAIN

        row = storage.get_budget(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=args.run_id,
        )
        if row is None:
            print("(sin budget)")
            return EXIT_OK
        print(f"run_id={args.run_id}")
        print(f"max_visits={row['max_visits'] if row['max_visits'] is not None else '-'}")
        print(
            "max_runtime_seconds="
            f"{row['max_runtime_seconds'] if row['max_runtime_seconds'] is not None else '-'}"
        )
        print(f"max_events={row['max_events'] if row['max_events'] is not None else '-'}")
        return EXIT_OK
