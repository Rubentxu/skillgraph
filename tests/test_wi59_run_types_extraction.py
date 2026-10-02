"""Red de contrato WI-59 fase 1: tipos de run extraidos a `runtime.run_types`.

Primera fase de ADR-0019 (estrangulamiento de RunController): los tipos
y la serializacion de modulo salen a `run_types.py` y `runcontroller`
conserva re-imports, de modo que los 39 consumidores externos
(RunController x25, RunBudget x10, y 4 sueltos) no se editan.
"""

from __future__ import annotations

import skillgraph.runtime.run_types as run_types
from skillgraph.runtime import runcontroller


class TestRunTypesIdentity:
    """`runcontroller.X` DEBE ser el simbolo real de run_types, no una copia."""

    def test_run_budget_identity(self) -> None:
        assert runcontroller.RunBudget is run_types.RunBudget

    def test_run_snapshot_identity(self) -> None:
        assert runcontroller.RunSnapshot is run_types.RunSnapshot

    def test_runtime_event_log_identity(self) -> None:
        assert runcontroller.RuntimeEventLog is run_types.RuntimeEventLog

    def test_budget_violation_kind_identity(self) -> None:
        assert runcontroller.BudgetViolationKind is run_types.BudgetViolationKind

    def test_serialization_identity(self) -> None:
        assert runcontroller.plan_to_json is run_types.plan_to_json
        assert runcontroller.plan_from_json is run_types.plan_from_json
        assert runcontroller.result_to_jsonable is run_types.result_to_jsonable

    def test_id_factories_identity(self) -> None:
        assert runcontroller.new_run_id is run_types.new_run_id
        assert runcontroller.new_node_execution_id is run_types.new_node_execution_id


class TestRunControllerUntouched:
    """El god-class no se movio en fase 1: sigue siendo el de siempre."""

    def test_run_controller_class_stays_in_runcontroller(self) -> None:
        assert runcontroller.RunController.__module__ == "skillgraph.runtime.runcontroller"

    def test_runcontroller_does_not_redefine_moved_types(self) -> None:
        import inspect

        source = inspect.getsource(runcontroller)
        assert "class RunBudget" not in source
        assert "class RunSnapshot" not in source
        assert "def plan_to_json" not in source
