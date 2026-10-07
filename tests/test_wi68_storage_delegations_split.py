"""Red de contrato WI-68: `storage_delegations` se desdobla en 5 modulos.

`storage_delegations.py` daba 915 LoC porque cinco razones de cambio
distintas (knowledge, runs, promotions, events, policy) compartian
fichero. Ninguna clase pasaba de 366 LoC ni ningun metodo de 27: el
problema no era concentracion de responsabilidad sino de fichero.

ADR-0022 fase 1 metio los cinco mixin en un modulo porque venian de un
corte unico; WI-68 los separa, con el mismo criterio que ADR-0024
aplico a `RunController`.

Lo que esta red fija:

1. Cada mixin vive en su modulo, y ese modulo define **solo** ese mixin
   (sin estado ni funciones libres a nivel de modulo).
2. `storage_delegations` sigue funcionando como indice: reexporta los
   cinco, asi que `Storage` y cualquier llamador previo no cambian.
   Un re-export que se rompe aparece como ImportError lejos, asi que la
   identidad de clase se comprueba aqui.
3. `Storage` sigue heredando los mismos cinco mixin, y los metodos
   siguen siendo **la misma funcion** (identidad, no igualdad).
4. Ningun modulo nuevo supera el umbral de 800 LoC del audit.

El comportamiento ya lo cubren los tests de WI-56 y WI-65; esta red
fija la estructura, que es lo que un movimiento verbatim puede romper
en silencio.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from skillgraph.platform import storage_delegations as index
from skillgraph.platform.storage import Storage

MIXIN_MODULES: dict[str, str] = {
    "KnowledgeDelegations": "skillgraph.platform.knowledge_delegations",
    "RunDelegations": "skillgraph.platform.run_delegations",
    "PromotionDelegations": "skillgraph.platform.promotion_delegations",
    "EventStoreDelegations": "skillgraph.platform.event_store_delegations",
    "PolicyDelegations": "skillgraph.platform.policy_delegations",
}

ALL_MIXINS: tuple[type, ...] = tuple(getattr(index, n) for n in MIXIN_MODULES)


def _mixin_methods(cls: type) -> set[str]:
    return {
        name
        for name, value in vars(cls).items()
        if not name.startswith("__") and inspect.isfunction(value)
    }


class TestOneModulePerMixin:
    @pytest.mark.parametrize("name,mod_name", sorted(MIXIN_MODULES.items()))
    def test_module_defines_exactly_its_mixin(self, name: str, mod_name: str) -> None:
        import importlib

        mod = importlib.import_module(mod_name)
        tree = ast.parse(Path(mod.__file__).read_text())
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        assert classes == [name], f"{mod_name} deberia definir solo {name}: {classes}"
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pytest.fail(f"funcion libre no prevista en {mod_name}: {node.name}")
            if isinstance(node, ast.Assign):
                pytest.fail(f"estado de modulo no previsto en {mod_name}: {node.targets}")

    @pytest.mark.parametrize("mod_name", sorted(MIXIN_MODULES.values()))
    def test_module_under_800_loc(self, mod_name: str) -> None:
        path = Path(__file__).resolve().parent.parent / "src" / (mod_name.replace(".", "/") + ".py")
        loc = len(path.read_text().splitlines())
        assert loc < 800, f"{mod_name} sigue en {loc} LoC"


class TestIndexReexports:
    @pytest.mark.parametrize("name", sorted(MIXIN_MODULES))
    def test_index_reexports_the_class(self, name: str) -> None:
        """ImportError en otro modulo es el modo de fallo que esto evita."""
        import importlib

        mod = importlib.import_module(MIXIN_MODULES[name])
        assert getattr(index, name) is getattr(mod, name), (
            f"storage_delegations.{name} no es la misma clase que su modulo"
        )

    def test_index_declares_all(self) -> None:
        assert set(index.__all__) == set(MIXIN_MODULES)

    def test_index_is_small(self) -> None:
        """Un indice, no un god module disfrazado."""
        path = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "skillgraph"
            / "platform"
            / "storage_delegations.py"
        )
        loc = len(path.read_text().splitlines())
        assert loc < 100, f"el indice deberia ser un re-export, pesa {loc} LoC"

    def test_index_defines_no_mixin_itself(self) -> None:
        """El shim no debe re-definir ninguna clase."""
        tree = ast.parse(
            (
                Path(__file__).resolve().parent.parent
                / "src"
                / "skillgraph"
                / "platform"
                / "storage_delegations.py"
            ).read_text()
        )
        assert not [n for n in tree.body if isinstance(n, ast.ClassDef)]


class TestStorageStillInherits:
    @pytest.mark.parametrize("mixin", ALL_MIXINS, ids=lambda m: m.__name__)
    def test_in_mro(self, mixin: type) -> None:
        assert mixin in Storage.__mro__, f"{mixin.__name__} salio del MRO"

    @pytest.mark.parametrize("mixin", ALL_MIXINS, ids=lambda m: m.__name__)
    def test_not_redefined_on_storage(self, mixin: type) -> None:
        redefined = sorted(_mixin_methods(mixin) & set(vars(Storage)))
        assert not redefined, f"Storage vuelve a definir {redefined}"

    @pytest.mark.parametrize("mixin", ALL_MIXINS, ids=lambda m: m.__name__)
    def test_function_identity(self, mixin: type) -> None:
        for name in _mixin_methods(mixin):
            assert getattr(Storage, name) is getattr(mixin, name), (
                f"Storage.{name} no es identica a {mixin.__name__}.{name}"
            )

    def test_method_count_preserved(self) -> None:
        moved = set().union(*(_mixin_methods(m) for m in ALL_MIXINS))
        # 65 -> 67 en B4. Lo que se conserva aqui no es la cifra, es que
        # lo que el corte movio a los mixin sigue siendo alcanzable desde
        # `Storage`: por eso el bucle de alcanzabilidad va DESPUES de la
        # cifra y no dentro de ella. Los dos nombres nuevos son
        # `get_resource_status` y `update_resource_status`.
        # B27 lo subio a 69 con `conflicts_for`, el delegate que hace
        # preguntable una contradiccion entre afirmaciones.
        # B29 lo subio a 70 con `claims_at_revision`, que hace preguntable una
        # ventana de vigencia. Y el bucle de alcanzabilidad que viene DESPUES es
        # el que de verdad importa: un metodo que sube la cifra pero se deja
        # de alcanzar desde `Storage` seria un delegate muerto, y la cifra no
        # lo veria.
        # B32 lo subio a 71 con `claims_desde_commit`, el delegate que hace
        # preguntable que se afirmo DESDE UN COMMIT, y por eso mismo exige
        # que el bucle de alcanzabilidad de abajo lo encuentre en `Storage`.
        assert len(moved) == 71, f"esperados 71 metodos de delegacion, hay {len(moved)}"
        for name in moved:
            assert callable(getattr(Storage, name, None)), f"{name} ya no es alcanzable"
