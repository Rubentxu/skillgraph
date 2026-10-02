"""Red de contrato WI-66: `_execute_one` en fases nombradas.

`_execute_one` eran **143 LoC**: el segundo metodo mas largo del repo
tras `build_parser`, y el primero por longitud real (los otros son
orquestadores declarativos con cc baja). El codigo eran 9 pasos
lineales envueltos en comentarios que explican invariantes H9/H10, asi
que la mejora no es solo de longitud: los nombres de las fases deben
decir **que invariante** protege cada paso.

Lo que esta red protege, en orden de importancia:

1. **El orden de los colaboradores no cambia.** Es lo que sostienen las
   invariantes de atomicidad H9/H10: el budget se comprueba ANTES de
   tocar el nodo; el `NodeExecution` RUNNING se inserta ANTES de
   compilar el handoff (para que `_mark_node_failed` tenga fila que
   actualizar); el `context_hash` se persiste ANTES de invocar al
   adapter. Un refactor que reordene pasos rompe esas garantias sin
   que ningun test de resultado lo note.
2. Los cortocircuitos siguen devolviendo el mismo veredicto y sin
   tocar lo que no deben: budget agotado -> `False` sin consultar
   ejecuciones; nodo ya SUCCEEDED sin self-loop -> `True` sin abrir
   NodeExecution; intentos agotados -> `False` sin abrir.
3. `_fail_node_with` sigue devolviendo siempre `False`.
4. `_execute_one` queda por debajo de 80 LoC (umbral P3 del audit).

Tests de forma y de orden sobre un `RunController` real con SQLite en
`tmp_path`, sin mocks de Storage: los espias solo envuelven metodos
del controlador para registrar el orden y delegan en los originales.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"
NODE = "n"


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
        capabilities=(),
        metadata={},
    )


def _plan(node_name: str = NODE) -> WorkflowPlan:
    return WorkflowPlan(nodes=(_node(node_name),), transitions=(), initial=node_name)


class _StubAdapter:
    """Adapter minimo: devuelve un outcome declarado por el plan."""

    def __init__(self, outcome: str = "ok") -> None:
        self.outcome = outcome
        self.calls: list[Any] = []

    def invoke(self, handoff: Any) -> Any:
        from skillgraph.runtime.agent import AgentResult

        self.calls.append(handoff)
        return AgentResult(outcome=self.outcome, result={"echo": True})


def _controller(tmp_path: Path, adapter: Any) -> tuple[RunController, Storage]:
    storage = Storage(tmp_path / "p.sqlite")
    storage.ensure_schema()
    ctl = RunController(runs=storage, events=storage, policy=storage, adapter=adapter)
    return ctl, storage


def _record_order(ctl: RunController, names: tuple[str, ...]) -> list[str]:
    """Envuelve los metodos indicados y registra el orden de llamada.

    Delega siempre en el original: el comportamiento no se altera, solo
    se observa. Es la unica forma de fijar el orden sin reimplementar
    la logica en el test.
    """
    log: list[str] = []
    for name in names:
        original = getattr(ctl, name)

        def wrapper(*args: Any, __n: str = name, __o: Any = original, **kw: Any) -> Any:
            log.append(__n)
            return __o(*args, **kw)

        setattr(ctl, name, wrapper)
    return log


TOP_LEVEL_STEPS: tuple[str, ...] = (
    "_is_budget_exhausted",
    "_node_executions_for",
    "_open_node_execution",
    "_build_handoff",
    "_finalize_node_success",
)

ORDERED_STEPS: tuple[str, ...] = TOP_LEVEL_STEPS


def _first_appearances(log: list[str]) -> list[str]:
    """Secuencia de nombres en orden de PRIMERA aparicion.

    El log plano no sirve como contrato: `_is_budget_exhausted` llama
    a su vez a `_node_executions_for`, asi que el numero de llamadas
    incluye las internas. Lo que sostiene las invariantes es el ORDEN
    en que aparecen los colaboradores de primer nivel, no cuantas veces
    se repiten los anidados.
    """
    seen: list[str] = []
    for name in log:
        if name in TOP_LEVEL_STEPS and name not in seen:
            seen.append(name)
    return seen


class TestPhasesExist:
    """Las fases nombradas existen y son metodos privados."""

    @pytest.mark.parametrize(
        "name",
        [
            "_node_guard",
            "_compile_node_handoff",
            "_invoke_node_adapter",
            "_settle_node_outcome",
        ],
    )
    def test_phase_method_exists(self, name: str) -> None:
        assert name.startswith("_"), "las fases son privadas"
        assert callable(getattr(RunController, name, None)), f"falta {name}"

    def test_execute_one_signature_unchanged(self) -> None:
        params = list(inspect.signature(RunController._execute_one).parameters)
        assert params == [
            "self",
            "tenant_id",
            "project_id",
            "run_id",
            "plan",
            "node_name",
        ], f"la firma cambio: {params}"
        assert (
            inspect.signature(RunController._execute_one).parameters["tenant_id"].kind
            is inspect.Parameter.KEYWORD_ONLY
        )

    def test_guard_record_is_frozen_with_slots(self) -> None:
        from skillgraph.runtime.runcontroller import _NodeGuard

        assert _NodeGuard.__dataclass_params__.frozen
        assert hasattr(_NodeGuard, "__slots__")

    def test_execution_record_is_frozen_with_slots(self) -> None:
        from skillgraph.runtime.runcontroller import _NodeExecution

        assert _NodeExecution.__dataclass_params__.frozen
        assert hasattr(_NodeExecution, "__slots__")


class TestCollaboratorOrder:
    """REQ-WI66-1: el orden es la invariante, no un detalle."""

    def test_happy_path_order(self, tmp_path: Path) -> None:
        adapter = _StubAdapter()
        ctl, storage = _controller(tmp_path, adapter)
        plan = _plan()
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        log = _record_order(ctl, ORDERED_STEPS)

        assert ctl._execute_one(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=plan, node_name=NODE
        )
        assert _first_appearances(log) == list(TOP_LEVEL_STEPS), (
            f"orden de colaboradores cambiado: {_first_appearances(log)}"
        )
        storage.close()

    def test_budget_checked_before_any_node_write(self, tmp_path: Path) -> None:
        """Si el budget esta agotado no se abre NADA del nodo."""
        adapter = _StubAdapter()
        ctl, storage = _controller(tmp_path, adapter)
        plan = _plan()
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        storage._conn.execute(
            "INSERT INTO run_budgets (run_id, tenant_id, project_id, "
            "max_visits, max_runtime_seconds, max_events) VALUES (?,?,?,0,0,0)",
            (run_id, TENANT, PROJECT),
        )
        storage._conn.commit()
        log = _record_order(ctl, ORDERED_STEPS)

        assert not ctl._execute_one(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=plan, node_name=NODE
        )
        assert _first_appearances(log)[0] == "_is_budget_exhausted"
        assert "_open_node_execution" not in log, (
            f"con budget agotado no se abre la NodeExecution: {log}"
        )
        assert "_finalize_node_success" not in log
        storage.close()

    def test_already_succeeded_short_circuits_before_open(self, tmp_path: Path) -> None:
        adapter = _StubAdapter()
        ctl, storage = _controller(tmp_path, adapter)
        plan = _plan()
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        assert ctl._execute_one(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=plan, node_name=NODE
        )
        log = _record_order(ctl, ORDERED_STEPS)

        assert ctl._execute_one(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=plan, node_name=NODE
        )
        assert _first_appearances(log) == [
            "_is_budget_exhausted",
            "_node_executions_for",
        ], f"un nodo ya SUCCEEDED no abre NodeExecution: {_first_appearances(log)}"
        assert len(adapter.calls) == 1, "el adapter no debe volver a invocarse"
        storage.close()

    def test_node_execution_opens_before_handoff_compile(self, tmp_path: Path) -> None:
        """H9-context-in-run: la fila RUNNING debe existir ANTES de
        compilar, para que `_mark_node_failed` tenga que actualizar."""
        adapter = _StubAdapter()
        ctl, storage = _controller(tmp_path, adapter)
        plan = _plan()
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)
        seen: list[tuple[str, int]] = []
        original_open = ctl._open_node_execution
        original_build = ctl._build_handoff

        def open_wrap(**kw: Any) -> Any:
            seen.append(("open", _rows(storage, run_id)))
            return original_open(**kw)

        def build_wrap(**kw: Any) -> Any:
            seen.append(("build", _rows(storage, run_id)))
            return original_build(**kw)

        ctl._open_node_execution = open_wrap  # type: ignore[method-assign]
        ctl._build_handoff = build_wrap  # type: ignore[method-assign]

        ctl._execute_one(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=plan, node_name=NODE
        )
        phases = [p for p, _ in seen]
        rows_when = dict(seen)
        assert phases == ["open", "build"], f"orden {phases}"
        assert rows_when["build"] >= 1, (
            "al compilar el handoff la NodeExecution RUNNING ya debe existir"
        )
        storage.close()


def _rows(storage: Storage, run_id: str) -> int:
    cur = storage._conn.execute("SELECT COUNT(*) FROM node_executions WHERE run_id = ?", (run_id,))
    return int(cur.fetchone()[0])


class TestShortCircuitVerdicts:
    def test_fail_node_with_always_returns_false(self) -> None:
        src = inspect.getsource(RunController._fail_node_with)
        assert src.rstrip().endswith("return False"), (
            "`_fail_node_with` debe seguir devolviendo False: las fases traducen ese retorno a None"
        )

    def test_attempts_exhausted_returns_false(self, tmp_path: Path) -> None:
        """Con MAX_NODE_ATTEMPTS ejecuciones previas no se abre una mas.

        Se generan de verdad (adapter que falla -> nodo FAILED) en vez
        de falsear `_node_executions_for`: el test no debe depender de
        la forma interna de la lectura.
        """

        class FailingAdapter:
            def invoke(self, handoff: Any) -> Any:
                raise ValueError("boom")

        ctl, storage = _controller(tmp_path, FailingAdapter())
        plan = _plan()
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=plan)

        opened: list[str] = []
        original_open = ctl._open_node_execution

        def open_wrap(**kw: Any) -> Any:
            opened.append("open")
            return original_open(**kw)

        ctl._open_node_execution = open_wrap  # type: ignore[method-assign]

        # Dos intentos fallidos: attempt 1 y 2.
        for _ in range(2):
            assert not ctl._execute_one(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id=run_id,
                plan=plan,
                node_name=NODE,
            )
        assert len(opened) == 2, f"dos intentos deben abrir dos filas: {opened}"

        # El tercero ya excede MAX_NODE_ATTEMPTS: no abre nada mas.
        opened.clear()
        assert not ctl._execute_one(
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id, plan=plan, node_name=NODE
        )
        assert opened == [], f"con los intentos agotados no se abre una NodeExecution mas: {opened}"
        rows = storage._conn.execute(
            "SELECT COUNT(*) FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert rows == 2, f"no debe existir una tercera fila: hay {rows}"
        storage.close()


class TestLegibility:
    def test_execute_one_is_under_80_loc(self) -> None:
        src = inspect.getsource(RunController._execute_one)
        loc = len(src.splitlines())
        assert loc < 80, f"_execute_one sigue en {loc} LoC: el umbral P3 del audit es 80"

    def test_no_phase_exceeds_80_loc(self) -> None:
        for name in (
            "_node_guard",
            "_compile_node_handoff",
            "_invoke_node_adapter",
            "_settle_node_outcome",
        ):
            loc = len(inspect.getsource(getattr(RunController, name)).splitlines())
            assert loc < 80, f"{name} tiene {loc} LoC"

    def test_no_single_method_exceeds_the_p3_threshold(self) -> None:
        """P3 del audit: ninguna funcion >80 LoC en este modulo.

        El fichero SI crecio (1289 -> ~1420) porque el desglose paga
        firmas, docstrings y dos records frozen. Ese coste se acepta de
        forma consciente: lo que el audit mide como P3 es la funcion,
        no el fichero, y `_execute_one` paso de 143 a 74 LoC. El
        umbral de god module (>800 LoC por fichero) lo cruza el modulo
        entero de todos modos, asi que no cambia el plan: fase 2 de
        ADR-0019.
        """
        import ast

        path = Path("src") / Path(RunController.__module__.replace(".", "/") + ".py")
        path = Path(__file__).resolve().parent.parent / path
        tree = ast.parse(path.read_text())
        big = [
            (n.name, n.end_lineno - n.lineno + 1)
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.end_lineno - n.lineno + 1 > 80
            and not n.name.startswith("__")
        ]
        assert not big, f"funciones >80 LoC en runcontroller: {big}"
