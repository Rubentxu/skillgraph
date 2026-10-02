"""Red de contrato WI-67: `RunController` delega su ejecucion en mixin.

ADR-0019 fase 2. Tras WI-66, `RunController` era un god module de
**1421 LoC** y una unica clase con 37 metodos. La medicion por AST
agrupa esos metodos en clusters disjuntos por dominio:

| Cluster | Metodos | LoC |
|---|---:|---:|
| ejecucion de nodo | 12 | 405 |
| consulta/observabilidad | 8 | 214 |
| budget | 2 | 107 |
| ciclo de vida del run | 6 | 219 |
| transiciones/locks | 5 | 137 |
| handoff/knowledge | 2 | 101 |
| `__init__` | 1 | 69 |

Este corte mueve los tres primeros a mixin, dejando `RunController` con
14 metodos y ~695 LoC: por debajo del umbral de 800 del audit.

Lo que la red fija:

1. Los 22 metodos movidos se **heredan**, no se redefinen, y
   `RunController.<m>` es la MISMA funcion que `<Mixin>.<m>`.
2. La superficie publica de `RunController` no cambia: ningun metodo
   aparece ni desaparece, ni público ni privado.
3. Los clusters son **disjuntos**: ningun metodo en dos mixin.
4. `RunController` queda por debajo de 800 LoC.
5. Los mixin no importan `RunController` (seria un ciclo), y solo usan
   `self.*`: no capturan estado.

El comportamiento NO se reimplementa aqui. Lo cubren los 1966 tests
existentes, incluidos los 433 de runtime/H9/H10 que fijan la
atomicidad. Esta red fija la **estructura** del corte, que es lo unico
que un movimiento verbatim puede romper en silencio.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from skillgraph.runtime.node_execution_delegations import (
    NodeExecutionDelegations,
)
from skillgraph.runtime.run_budget_delegations import RunBudgetDelegations
from skillgraph.runtime.run_observability_delegations import (
    RunObservabilityDelegations,
)
from skillgraph.runtime.runcontroller import RunController

MIXINS: tuple[type, ...] = (
    NodeExecutionDelegations,
    RunObservabilityDelegations,
    RunBudgetDelegations,
)

EXPECTED_MIXIN_MEMBERS: dict[str, frozenset[str]] = {
    "NodeExecutionDelegations": frozenset(
        {
            "_execute_one",
            "_node_guard",
            "_compile_node_handoff",
            "_invoke_node_adapter",
            "_settle_node_outcome",
            "_open_node_execution",
            "_finalize_node_success",
            "_fail_node_with",
            "_mark_node_failed",
            "_node_executions_for",
            "_latest_node_execution",
            "_node_has_execution",
        }
    ),
    "RunObservabilityDelegations": frozenset(
        {
            "list_runs",
            "show_run",
            "logs_run",
            "_count_events",
            "_snapshot",
            "_calculate_frontier",
            "_count_executed",
            "_executed_node_names",
        }
    ),
    "RunBudgetDelegations": frozenset({"_is_budget_exhausted", "_emit_budget_exceeded"}),
}

ALL_MOVED: frozenset[str] = frozenset().union(*EXPECTED_MIXIN_MEMBERS.values())


def _defined(cls: type) -> set[str]:
    return {n for n, v in vars(cls).items() if inspect.isfunction(v)}


class TestMixinWiring:
    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_mixin_in_mro(self, mixin: type) -> None:
        assert mixin in RunController.__mro__, (
            f"{mixin.__name__} no esta en el MRO de RunController: el corte no ocurrio"
        )

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_expected_members_present(self, mixin: type) -> None:
        expected = EXPECTED_MIXIN_MEMBERS[mixin.__name__]
        missing = expected - _defined(mixin)
        assert not missing, f"{mixin.__name__} no define {sorted(missing)}"

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_no_redefinition_on_runcontroller(self, mixin: type) -> None:
        redefined = sorted(_defined(mixin) & _defined(RunController))
        assert not redefined, (
            f"RunController vuelve a definir {redefined}: la delegacion esta duplicada, no heredada"
        )

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_function_identity(self, mixin: type) -> None:
        for name in _defined(mixin):
            assert getattr(RunController, name) is getattr(mixin, name), (
                f"RunController.{name} no es identica a {mixin.__name__}.{name}"
            )

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_resolves_to_the_mixin(self, mixin: type) -> None:
        for name in _defined(mixin):
            owner = getattr(RunController, name).__qualname__.split(".")[0]
            assert owner == mixin.__name__, (
                f"RunController.{name} resuelve a {owner}, no a {mixin.__name__}"
            )


class TestClustersDisjoint:
    def test_no_method_in_two_mixins(self) -> None:
        seen: dict[str, str] = {}
        for mixin in MIXINS:
            for name in _defined(mixin):
                assert name not in seen, f"{name} esta en {seen.get(name)} y {mixin.__name__}"
                seen[name] = mixin.__name__
        assert len(seen) == 22, f"esperados 22 metodos movidos, hay {len(seen)}"

    def test_every_moved_method_is_reachable(self) -> None:
        reachable = set(ALL_MOVED)
        for mixin in MIXINS:
            for name in _defined(mixin):
                assert name in reachable, f"{name} se movio sin estar en la lista"

    @pytest.mark.parametrize(
        "mod_name",
        [
            "node_execution_delegations",
            "run_observability_delegations",
            "run_budget_delegations",
        ],
    )
    def test_mixin_module_has_no_import_cycle(self, mod_name: str) -> None:
        import importlib

        mod = importlib.import_module(f"skillgraph.runtime.{mod_name}")
        src = Path(mod.__file__).read_text()
        assert "from skillgraph.runtime.runcontroller import" not in src, (
            f"{mod_name} importa runcontroller: eso es un ciclo"
        )
        assert "import RunController" not in src


class TestPublicSurfaceUnchanged:
    """Ni un metodo aparece ni desaparece."""

    def test_no_public_method_lost(self) -> None:
        """Comparado con el estado previo al corte (37 metodos, 12
        publicos). Se fija el conjunto, no el orden."""
        # `vars()` solo ve el namespace propio. La superficie que
        # importa es la ACCESIBLE, que incluye lo heredado de los mixin
        # (mismo error que el de test_persistence_ports en WI-65).
        current = {n for n, _ in inspect.getmembers(RunController, inspect.isfunction)}
        public = {n for n in current if not n.startswith("_")}
        assert public == {
            "create_run",
            "reconcile_run",
            "list_runs",
            "show_run",
            "logs_run",
            "cancel_run",
        }, f"superficie publica inesperada: {sorted(public)}"

    def test_all_moved_methods_still_exist(self) -> None:
        for name in ALL_MOVED:
            assert callable(getattr(RunController, name, None)), (
                f"{name} ya no es alcanzable desde RunController"
            )

    @pytest.mark.parametrize(
        "name",
        [
            # Nombres que src/ y tests/ consumen DESDE `runcontroller`,
            # aunque su definicion viva ahora en otro modulo. Varios se
            # acceden como atributo (`runcontroller.BudgetViolationKind`),
            # no por `from ... import`, asi que un grep de imports no
            # los ve: por eso la lista es explicita y esta red la fija.
            "BudgetViolationKind",
            "RunBudget",
            "RunSnapshot",
            "RuntimeEventLog",
            "MAX_NODE_ATTEMPTS",
            "new_node_execution_id",
            "new_run_id",
            "plan_from_json",
            "plan_to_json",
            "result_to_jsonable",
            "has_self_loop",
            "is_outcome_declared",
            "_NodeGuard",
            "_NodeExecution",
        ],
    )
    def test_reexport_still_importable(self, name: str) -> None:
        import skillgraph.runtime.runcontroller as mod

        assert hasattr(mod, name), (
            f"runcontroller.{name} ya no existe: lo borra ruff por F401 "
            f"en cuanto RunController deja de usarlo, y revienta en el "
            f"modulo que lo consume, no aqui"
        )
        assert name in mod.__all__, f"{name} debe declararse en __all__"

    def test_reconcile_signature_unchanged(self) -> None:
        params = list(inspect.signature(RunController.reconcile_run).parameters)
        assert params[1:4] == ["tenant_id", "project_id", "run_id"], params


class TestModuleUnderThreshold:
    def test_runcontroller_below_800_loc(self) -> None:
        path = Path(RunController.__module__.replace(".", "/") + ".py")
        real = Path(__file__).resolve().parent.parent / "src" / path
        loc = len(real.read_text().splitlines())
        assert loc < 800, f"runcontroller.py sigue en {loc} LoC"

    @pytest.mark.parametrize(
        "mod_name",
        [
            "node_execution_delegations",
            "run_observability_delegations",
            "run_budget_delegations",
        ],
    )
    def test_delegation_module_is_cohesive(self, mod_name: str) -> None:
        """Un modulo por dominio, y sin funciones libres."""
        import importlib

        mod = importlib.import_module(f"skillgraph.runtime.{mod_name}")
        tree = ast.parse(Path(mod.__file__).read_text())
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        mixins = [c for c in classes if c in {m.__name__ for m in MIXINS}]
        records = [c for c in classes if c not in {m.__name__ for m in MIXINS}]
        assert len(mixins) == 1, f"{mod_name} deberia definir un mixin: {classes}"
        if mod_name == "node_execution_delegations":
            # los dos records de WI-66 viajan con su cluster
            assert set(records) == {"_NodeGuard", "_NodeExecution"}, records
            for r in records:
                node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == r)
                assert node.decorator_list, f"{r} debe seguir siendo frozen dataclass"
        else:
            assert not records, f"{mod_name} no deberia definir records: {records}"
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pytest.fail(f"funcion libre no prevista en {mod_name}: {node.name}")

    @pytest.mark.parametrize(
        "mod_name",
        [
            "node_execution_delegations",
            "run_observability_delegations",
            "run_budget_delegations",
        ],
    )
    def test_mixins_capture_no_module_state(self, mod_name: str) -> None:
        """Cada metodo debe operar sobre `self`, nada de estado global."""
        import importlib

        mod = importlib.import_module(f"skillgraph.runtime.{mod_name}")
        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Solo el PRIMER argumento es `self`; el resto son los
                # parametros del metodo.
                assert node.args.args and node.args.args[0].arg == "self", (
                    f"{node.name} no es metodo: {[a.arg for a in node.args.args]}"
                )
                # Nodo AST, no subcadena: "budget global del Run" esta
                # en los comentarios y un `in "global"` daria falso
                # positivo.
                assert not [n for n in ast.walk(node) if isinstance(n, ast.Global)], (
                    f"{node.name} declara global"
                )
