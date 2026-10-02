"""Red de contrato WI-65 fase 2: schema y row mappers salen de `storage`.

Continua ADR-0020 (que extrajo los mappers de
`knowledge_repository.py` a `knowledge_mappers.py`) para el modulo que
queda tras la fase 1. Umbral del audit: <800 LoC por fichero.

Contrato fijado aqui:

1. Los **5 mappers fila->DTO** y `_uid` viven en
   `skillgraph.platform.row_mappers`. Son funciones puras: reciben una
   fila y devuelven un DTO, sin `self`, sin conexion, sin reloj.
   (WI-81: eran 12. Los 7 restantes eran alias de retro-compatibilidad
   de WI-56 sin callers; ver `tests/test_wi81_dead_aliases.py`.)
2. El **DDL** (`_SCHEMA_SQL`, 248 LoC) y `SCHEMA_VERSION` viven en
   `skillgraph.platform.schema`. Es una constante: no tiene razon de
   cambio junto a los metodos del facade.
3. `storage` **re-exporta** ambos porque tres modulos los importan
   desde ahi (ADR-0016 corte 5): `event_store` importa `_SCHEMA_SQL` y
   `_row_to_stored_event`, `policy_store` importa `_row_to_stored_budget`
   y `knowledge_repository` importa `_uid`. Sin el shim, esos imports
   revientan.
4. Lo que **NO** se mueve: `_tx`, `_atomic`, `_migrate`,
   `_insert_event_in_tx` y `_atomic_state_and_event`. ADR-0016 exige que
   los atomicos H9/H10 compartan `self._conn` con el resto sin
   duplicarlo; `_insert_event_in_tx` lo necesita `SqliteEventStore`.
   Este test falla si alguno de ellos se extrae.
5. `storage.py` queda por debajo de 800 LoC.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from skillgraph.platform import storage
from skillgraph.platform.row_mappers import MAPPER_NAMES, _row_to_run
from skillgraph.platform.schema import SCHEMA_SQL

MAPPERS_ON_STORAGE: tuple[str, ...] = MAPPER_NAMES

# ADR-0016: los atomicos H9/H10 deben SEGUIR en Storage.
MUST_STAY_IN_STORAGE: frozenset[str] = frozenset(
    {
        "_tx",
        "_atomic",
        "_migrate",
        "_insert_event_in_tx",
        "_atomic_state_and_event",
    }
)

DOWNSTREAM_IMPORTERS: tuple[str, ...] = (
    "skillgraph.platform.event_store",
    "skillgraph.platform.policy_store",
    "skillgraph.platform.knowledge_repository",
    "skillgraph.platform.knowledge_mappers",
    "skillgraph.platform.run_repository",
    "skillgraph.platform.promotion_repository",
)


class TestMappersMoved:
    def test_mappers_live_in_row_mappers_module(self) -> None:
        from skillgraph.platform import row_mappers

        for name in MAPPERS_ON_STORAGE:
            assert hasattr(row_mappers, name), f"{name} no esta en row_mappers"

    def test_storage_does_not_redefine_mappers(self) -> None:
        """WI-86: `storage` ya no los reexporta, y no los define.

        Antes este test afirmaba `getattr(storage, name) is
        getattr(row_mappers, name)`: correcto cuando `storage` reexportaba.
        WI-86 midio que los 7 simbolos aparecian **dos veces** en
        `storage.py` —el import y `__all__`— y **cero** en codigo, y que
        los 5 consumidores podian ir a la hoja directamente. El
        contrato nuevo es mas fuerte que el viejo: no basta con que sean
        el mismo objeto, es que el facade no los anuncie en absoluto.
        """
        from skillgraph.platform import row_mappers

        for name in MAPPERS_ON_STORAGE:
            assert not hasattr(storage, name), (
                f"storage vuelve a exponer {name}: el re-export que WI-86 "
                f"retiro ha vuelto, y con el la superficie que storage no "
                f"sostiene"
            )
            assert not hasattr(storage.Storage, name), (
                f"Storage vuelve a definir {name}: debe tomarlo de row_mappers"
            )
            assert hasattr(row_mappers, name), f"{name} desaparecio de row_mappers"

    def test_mappers_are_pure(self) -> None:
        """Ningun mapper toca self, conexion ni reloj."""
        from skillgraph.platform import row_mappers

        tree = ast.parse(Path(row_mappers.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                src = ast.get_source_segment(Path(row_mappers.__file__).read_text(), node) or ""
                assert "self." not in src, f"{node.name} usa self."
                assert "_conn" not in src, f"{node.name} toca la conexion"

    def test_uid_is_not_reexported(self) -> None:
        """WI-86: `_uid` ya no pasa por el facade.

        Antes: `storage._uid is row_mappers._uid`. Ahora el unico sitio
        donde vive `_uid` es `row_mappers`, y su unico consumidor real
        (`knowledge_repository`) lo importa de ahi. Lo que se vigila es
        que no vuelva a colarse una copia en el facade.
        """
        from skillgraph.platform import knowledge_repository, row_mappers

        assert not hasattr(storage, "_uid"), "storage vuelve a reexportar _uid"
        assert knowledge_repository._uid is row_mappers._uid, (
            "knowledge_repository debe resolver al MISMO _uid de row_mappers, no a una copia"
        )


class TestSchemaMoved:
    def test_schema_constants_live_in_schema_module(self) -> None:
        from skillgraph.platform import schema

        assert schema.SCHEMA_SQL
        assert isinstance(schema.SCHEMA_VERSION, int)

    def test_storage_re_exports_schema(self) -> None:
        from skillgraph.platform import schema

        assert storage._SCHEMA_SQL is schema.SCHEMA_SQL
        assert storage.SCHEMA_VERSION == schema.SCHEMA_VERSION

    def test_storage_imports_schema_instead_of_redefining_it(self) -> None:
        """El re-export SI pone el nombre en el namespace de `storage`;
        lo que no puede es volver a DEFINIR el literal. Se comprueba a
        nivel AST, no con `vars()`, que no distingue las dos cosas."""
        tree = ast.parse(Path(storage.__file__).read_text())
        redefined = [
            node.lineno
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == "_SCHEMA_SQL" for t in node.targets)
        ]
        assert not redefined, (
            f"storage.py vuelve a asignar _SCHEMA_SQL en la linea {redefined} "
            f"en vez de importarlo de skillgraph.platform.schema"
        )

    def test_schema_declares_its_public_names(self) -> None:
        from skillgraph.platform import schema

        assert {"SCHEMA_SQL", "SCHEMA_VERSION"} <= set(schema.__all__)


class TestAtomicsStayInStorage:
    """ADR-0016: los atomicos H9/H10 se quedan."""

    @pytest.mark.parametrize("name", sorted(MUST_STAY_IN_STORAGE))
    def test_atomic_helper_still_defined_on_storage(self, name: str) -> None:
        assert name in vars(storage.Storage), (
            f"{name} debe seguir en Storage: ADR-0016 exige que los "
            f"atomicos compartan self._conn sin duplicarlo"
        )

    def test_atomics_still_use_the_shared_connection(self) -> None:
        body = inspect.getsource(storage.Storage._atomic)
        assert "self._conn" in body, (
            "_atomic debe seguir operando sobre self._conn: los "
            "componentes de WI-56 lo resuelven tarde contra la misma"
        )


class TestShimPreserved:
    """Los imports de los componentes de WI-56 no se rompen."""

    @pytest.mark.parametrize("module_name", DOWNSTREAM_IMPORTERS)
    def test_downstream_module_imports(self, module_name: str) -> None:
        import importlib

        importlib.import_module(module_name)

    def test_event_store_still_sees_schema(self) -> None:
        from skillgraph.platform import event_store

        assert event_store._SCHEMA_SQL is SCHEMA_SQL

    def test_event_store_still_sees_event_mapper(self) -> None:
        """WI-86: `event_store` lo ve, pero ya no a traves del facade.

        La intencion original —que `event_store` vea el mapper de verdad y
        no una copia— sigue viva; lo que cambia es de donde lo saca. Si
        el import se moviera a la hoja, esto seguiria pasado, y por eso
        la comprobacion de que la hoja es una hoja esta en
        `tests/test_wi86_no_facade_hop.py`.
        """
        from skillgraph.platform import event_store, row_mappers

        assert event_store._row_to_stored_event is row_mappers._row_to_stored_event
        assert not hasattr(storage, "_row_to_stored_event"), (
            "storage vuelve a exponer el mapper: event_store debe tomarlo de row_mappers"
        )

    def test_five_mappers_moved(self) -> None:
        """Guarda el recuento: un mapper olvidado no se nota solo.

        WI-81 bajo el recuento de 12 a 5. Los 7 que se fueron eran alias
        de WI-56, no mappers, y `test_wi81_dead_aliases.py` es quien
        vigila ahora que no vuelvan a colarse en la cuenta.
        """
        assert len(MAPPERS_ON_STORAGE) == 5, f"esperados 5 mappers, hay {len(MAPPERS_ON_STORAGE)}"

    def test_representative_mapper_is_callable(self) -> None:
        assert callable(_row_to_run)

    def test_runtime_constructed_dtos_are_importable(self) -> None:
        """Guarda contra la regresion real de esta fase.

        Los mappers CONSTRUYEN DTOs (`return StoredRun(...)`). Con
        `from __future__ import annotations` una anotacion es una cadena
        perezosa, pero la llamada es una busqueda real: si el DTO queda
        bajo `if TYPE_CHECKING:`, ruff pasa (F401 lo acepta) y el
        NameError aparece en runtime, al ejecutar el mapper. 133 tests
        caidos por esto. Se comprueba que todo nombre construido a nivel
        de modulo exista de verdad en el namespace del modulo.
        """
        from skillgraph.platform import row_mappers

        path = Path(row_mappers.__file__)
        tree = ast.parse(path.read_text())

        def _is_type_checking(node: ast.stmt) -> bool:
            return (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"
            )

        # Dos pasadas: `ast.walk` es BFS y visita el `if TYPE_CHECKING`
        # ANTES que el import que contiene, asi que restar en el mismo
        # bucle noeria nada y la guarda perderia dientes.
        all_imports: set[str] = set()
        hidden: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                all_imports |= {a.asname or a.name for a in node.names}
        for node in ast.walk(tree):
            if _is_type_checking(node):
                for inner in ast.walk(node):
                    if isinstance(inner, (ast.Import, ast.ImportFrom)):
                        hidden |= {a.asname or a.name for a in inner.names}
        runtime_imports = all_imports - hidden

        local_defs = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        resolved = runtime_imports | local_defs | set(vars(row_mappers))
        builtins = {"json", "tuple", "list", "str", "int", "dict", "len", "isinstance"}
        missing = {
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id not in builtins
            and n.func.id not in resolved
        }
        assert not missing, (
            f"row_mappers construye en runtime {sorted(missing)} pero no lo "
            f"importa en runtime: NameError al ejecutar el mapper"
        )

    def test_at_least_one_mapper_constructs_a_dto(self) -> None:
        """Evita que la guarda anterior se vuelva trivial si todo se
        convierte en anotaciones."""
        from skillgraph.platform import row_mappers

        src = Path(row_mappers.__file__).read_text()
        assert "return StoredRun(" in src
        assert "return StoredEvent(" in src


class TestStorageUnderThreshold:
    def test_storage_module_is_below_800_loc(self) -> None:
        path = Path(storage.__file__)
        loc = len(path.read_text().splitlines())
        assert loc < 800, (
            f"storage.py sigue en {loc} LoC: la fase 2 no alcanzo el umbral que fija el audit"
        )
