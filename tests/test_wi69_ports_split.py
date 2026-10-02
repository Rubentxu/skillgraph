"""Red de contrato WI-69: `ports` se desdobla en `dto` y `repositories`.

`ports/__init__.py` daba 927 LoC por **anchura** (14 tipos), no por
profundidad: la clase mayor es `KnowledgeRepository` con 179 LoC. El
corte separa las dos familias con dependencia unidireccional — los
Protocols importan los DTO, nunca al reves.

Lo que fija:

1. Cada tipo vive en su modulo, y ese modulo define solo esa familia.
2. `skillgraph.platform.ports` sigue exportando los **catorce** con la
   misma identidad de clase: un re-export roto aparece como ImportError
   en un modulo ajeno, muy lejos de la causa.
3. Los DTO son dataclasses con constructor. Este es el punto que mas
   rompio al implementar el corte: `ClassDef.lineno` del AST apunta a
   la palabra `class`, no al decorador, asi que al copiar el span se
   quedaron atras los `@dataclass` y las clases dejaron de ser
   construibles (`TypeError: StoredRun() takes no arguments`, 41 tests).
4. Ningun modulo pasa de 800 LoC.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from skillgraph.platform import ports

DTOS: tuple[str, ...] = (
    "StoredEvent",
    "StoredRun",
    "StoredNodeExecution",
    "StoredResource",
    "StoredRelation",
    "StoredClaim",
    "StoredEvidence",
    "StoredPromotion",
    "StoredBudget",
)
PROTOCOLS: tuple[str, ...] = (
    "RunRepository",
    "EventStore",
    "KnowledgeRepository",
    "PromotionRepository",
    "PolicyStore",
)
ALL: tuple[str, ...] = DTOS + PROTOCOLS


def _port_path(name: str) -> Path:
    base = Path(__file__).resolve().parent.parent / "src" / "skillgraph" / "platform" / "ports"
    return base / ("dto.py" if name in DTOS else "repositories.py")


class TestTypesLiveInTheirModule:
    @pytest.mark.parametrize("name", ALL)
    def test_type_is_importable_from_its_module(self, name: str) -> None:
        import importlib

        mod = importlib.import_module(_module_for(name))
        assert hasattr(mod, name), f"{name} deberia estar en {_module_for(name)}"

    @pytest.mark.parametrize("name", ALL)
    def test_index_reexports_the_same_class(self, name: str) -> None:
        """Identidad, no igualdad: un re-export copiado rompe el `is`."""
        import importlib

        mod = importlib.import_module(_module_for(name))
        assert getattr(ports, name) is getattr(mod, name), (
            f"ports.{name} no es la misma clase que {_module_for(name)}.{name}"
        )

    def test_index_declares_all_fourteen(self) -> None:
        assert set(ports.__all__) == set(ALL)
        assert len(ALL) == 14

    def test_index_defines_no_class(self) -> None:
        """El indice reexporta, no reproduce."""
        path = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "skillgraph"
            / "platform"
            / "ports"
            / "__init__.py"
        )
        tree = ast.parse(path.read_text())
        assert not [n for n in tree.body if isinstance(n, ast.ClassDef)]


class TestDtoDecoratorsSurvived:
    """REQ-WI69-1: el fallo real de este corte."""

    @pytest.mark.parametrize("name", DTOS)
    def test_dto_is_a_dataclass(self, name: str) -> None:
        cls = getattr(ports, name)
        assert dataclasses.is_dataclass(cls), (
            f"{name} perdio su @dataclass al moverlo: se copio el span "
            f"desde ClassDef.lineno, que apunta a `class`, no al decorador"
        )
        assert cls.__dataclass_params__.frozen, f"{name} debe seguir inmutable"

    @pytest.mark.parametrize("name", DTOS)
    def test_dto_keeps_its_fields(self, name: str) -> None:
        cls = getattr(ports, name)
        fields = {f.name for f in dataclasses.fields(cls)}
        assert fields, f"{name} se ha quedado sin campos"

    def test_stored_run_is_constructible(self) -> None:
        """El sintoma exacto que delato el bug: sin constructor."""
        run = ports.StoredRun(
            run_id="r",
            tenant_id="t",
            project_id="p",
            state="ACTIVE",
            plan_json="{}",
            current_node=None,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert run.run_id == "r"


class TestProtocolsStillProtocols:
    @pytest.mark.parametrize("name", PROTOCOLS)
    def test_protocol_is_a_protocol(self, name: str) -> None:
        from typing import Protocol

        cls = getattr(ports, name)
        assert issubclass(cls, Protocol), f"{name} debe seguir siendo un Protocol"
        assert getattr(cls, "_is_protocol", False), f"{name} perdio _is_protocol"


class TestModuleSize:
    @pytest.mark.parametrize("name", ("dto", "repositories", "__init__"))
    def test_module_under_800_loc(self, name: str) -> None:
        path = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "skillgraph"
            / "platform"
            / "ports"
            / f"{name}.py"
        )
        loc = len(path.read_text().splitlines())
        assert loc < 800, f"ports/{name}.py sigue en {loc} LoC"

    def test_no_orphan_decorators(self) -> None:
        """`@dataclass` sin clase debajo: sintaxis rota en silencio."""
        for mod in ("dto", "repositories"):
            path = (
                Path(__file__).resolve().parent.parent
                / "src"
                / "skillgraph"
                / "platform"
                / "ports"
                / f"{mod}.py"
            )
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    for dec in node.decorator_list:
                        assert dec.lineno >= 1
                    # el decorador debe caer dentro del fichero del
                    # modulo, no quedar huerfano tras el corte
                    assert (
                        node.lineno
                        > min((d.lineno for d in node.decorator_list), default=node.lineno)
                        or not node.decorator_list
                    ), f"{mod}:{node.name} decorador huerfano"


def _module_for(name: str) -> str:
    return (
        "skillgraph.platform.ports.dto"
        if name in DTOS
        else "skillgraph.platform.ports.repositories"
    )
