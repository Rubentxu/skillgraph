"""Subcomandos `sg runs` (WI-53, ADR-0018).

Segundo corte del estrangulamiento H-02: los 5 handlers `cmd_runs_*`
salen de `cli/runner.py` verbatim (lazy imports incluidos). `runner`
conserva alias para su tabla de dispatch y sus usos internos de
`_open_project_storage`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from skillgraph.cli.support import (
    EXIT_DOMAIN,
    EXIT_OK,
    _open_project_storage,
    resolve_project,
)


class _Presentable(Protocol):
    """Lo minimo que un comando necesita de una vista para imprimirla (B7).

    Es un Protocol y no `object` porque la primera version de `_emit`
    admitia cualquier cosa y lo pagaba con `type: ignore`. En este repo
    no corre type-checker — no hay mypy ni pyright en CI — asi que el
    Protocol NO habria atrapado el fallo por si solo: lo atraparia un
    test. Se declara igualmente porque acota la superficie que `_emit`
    necesita y porque hace explicito, en el punto donde se decide, que
    `to_text` no es de todas las vistas. `runs show` llego a reventar
    con `TypeError` por un kwarg que `TableView` si acepta y
    `DetailView` no, y el que lo vigila es
    `test_show_conserva_su_contrato_de_clave_valor`.
    """

    def to_json_text(self) -> str: ...


def _emit(vista: _Presentable, formato: str | None, texto: Callable[[], str]) -> str:
    """La MISMA vista, en texto o en JSON (B7).

    Se decide aqui y no en cada comando para que la eleccion sea la misma
    en todas partes: si cada comando escribiera su propio
    `if args.format == "json"`, el primero que se olvidara de la rama
    seria el que solo funciona para personas, que es exactamente el
    defecto que el gate quiere cerrar.

    `texto` es un callable y no un `str` ya calculado por dos razones.
    Una: la vista se construye una sola vez, y un `str` evaluado en el
    punto de llamada obligaria a construirla otra vez para el JSON.
    Dos, y es la que importa: QUE representacion es «el texto» lo sabe
    el comando, no la vista. `runs list` imprime una tabla y `runs show`
    imprime `clave=valor`, y son contratos externos distintos — hay
    callers que los leen con `awk`—. Un `_emit` que impusiera una unica
    forma de texto habria tenido que romper uno de los dos.

    `formato=None` cae a texto, y NO es una comodidad: los handlers se
    llaman tambien con un `Namespace` construido a mano —los tests
    in-process de WI-63 lo hacen—, y `getattr(args, "format", None)` es
    lo que evita que un `AttributeError` aparezca en un camino que antes
    de B7 funcionaba. Una bandera nueva no puede romper a quien no la
    pide.
    """
    if formato == "json":
        return vista.to_json_text()
    return texto()


def cmd_runs_list(args: argparse.Namespace) -> int:
    """Lista Runs del proyecto via `RunController.list_runs`.

    Read-only: no emite eventos. Salida CSV-like para legibilidad
    en shell (una linea por run con columnas estables).
    """
    from skillgraph.presentation.widgets import run_view
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
        # Una sola vista, dos representaciones (B7). El `print` de antes
        # construia las filas aqui, y por eso no habia forma de que otra
        # superficie —una TUI— leyera lo mismo: tendria que reescribir
        # estos mismos f-strings, y las dos acabarian divergiendo.
        #
        # `(sin runs)` se conserva literal: `test_cli_runs_inspect.py` lo
        # fija como contrato de un proyecto vacio, y cambiarlo por el
        # `(sin resultados)` por defecto de la vista seria una ruptura
        # silenciosa de una linea que ya se leia en scripts.
        vista = run_view(tuple(runs))
        print(
            _emit(
                vista,
                getattr(args, "format", None),
                lambda: vista.to_text(vacio="(sin runs)"),
            )
        )
        return EXIT_OK


def cmd_runs_show(args: argparse.Namespace) -> int:
    """Muestra el snapshot de un Run via `RunController.show_run`.

    Read-only: no emite eventos. Salida en formato key=value para
    que un caller shell pueda parsear con awk/cut.
    """
    from skillgraph.presentation.widgets import run_detail, timeline_view
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
        # El objetivo de B7 dice que un operador abre un run y ve el estado
        # Y el timeline que lo explico. El snapshot sin la linea de tiempo
        # dice COMO termino el run, no POR QUE.
        eventos = ctl.logs_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=args.run_id,
        )
        #
        # Y aqui esta el otro contrato: en TEXTO, `runs show` sigue siendo
        # `clave=valor`, que es lo que el docstring del comando promete y
        # lo que `test_cli_runs_inspect.py` fija. El panel legible que
        # B7 anade (`to_text`) y el JSON van en las representaciones
        # nuevas; el texto por defecto no se sustituye. Sustituirlo habria
        # sido la forma facil de cerrar el bloque, y habria roto a
        # cualquiera que lea `state=` con un `cut`.
        vista = run_detail(snap, timeline=timeline_view(tuple(eventos)))
        print(_emit(vista, getattr(args, "format", None), vista.to_key_value))
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
