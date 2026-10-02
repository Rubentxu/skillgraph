"""WI-86: los mappers se importan de la hoja, no a traves del facade.

Medido el 2026-10-02: los 7 simbolos que `platform/storage.py` importa y
reexporta (`MAPPER_NAMES` y los 6 `_row_to_*`/`_uid`) aparecen
**exactamente dos veces** en el fichero — una en el `import` y otra en
`__all__` — y **ninguno se usa en una sola linea de codigo dentro de
`storage.py`**. La capa entera existe para servir a hermanos.

Y sus consumidores son **cinco**, no los dos que nombra el comentario del
propio bloque de re-export:

    event_store, policy_store, knowledge_claims,
    promotion_repository, run_repository

`row_mappers` es una hoja: importa `sqlite3`, `typing` y
`skillgraph.platform.ports`. No hay ciclo que justifique el rodeo, asi que
cada consumidor debe importar de ahi directamente.

El defecto es el mismo que WI-81 una generacion mas abajo: un modulo
declara en `__all__` simbolos que no usa, y con eso anuncia una superficie
que no sostiene. Quien lea `storage.__all__` concluirá que
`platform.storage` es la direccion canonica de los mappers, cuando lo es
`row_mappers`.

Estos tests son la red PREVIA: se escriben en rojo y fijan que el
movimiento no puede cambiar el objeto al que resuelve cada consumidor.
La comparacion es por **identidad**, no por igualdad: mover un import sin
cambiar el simbolo es el requisito; dos funciones iguales no serian.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from skillgraph.platform import row_mappers

PLATFORM = Path(__file__).resolve().parent.parent / "src" / "skillgraph" / "platform"

# Los simbolos que storage reexporta y que, medido, no usa para nada
# dentro de si. `_uid` se incluye: mismo patron, 2 apariciones, 0 usos.
FACADE_EXPORTS: tuple[str, ...] = (
    "MAPPER_NAMES",
    "_row_to_node_execution",
    "_row_to_run",
    "_row_to_stored_budget",
    "_row_to_stored_event",
    "_row_to_stored_promotion",
    "_uid",
)

# Los 5 consumidores reales. El comentario del bloque de re-export nombra
# solo event_store y policy_store; el resto no estaba inventariado.
CONSUMERS: tuple[str, ...] = (
    "event_store",
    "knowledge_repository",
    "policy_store",
    "promotion_repository",
    "run_repository",
)

MAPPER_SYMBOLS: tuple[str, ...] = (
    *(n for n in FACADE_EXPORTS if n.startswith("_row_to_")),
    "_uid",
)


def _imported_names(module: str) -> frozenset[str]:
    """Nombres que `module` saca de `skillgraph.platform.storage`."""
    tree = ast.parse((PLATFORM / f"{module}.py").read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "skillgraph.platform.storage":
            out.update(a.name for a in node.names)
    return frozenset(out)


class TestNoHopThroughTheFacade:
    @pytest.mark.parametrize("module", CONSUMERS)
    def test_consumer_does_not_take_mappers_from_storage(self, module: str) -> None:
        """Ningun consumidor saca un mapper del facade."""
        taken = _imported_names(module) & set(FACADE_EXPORTS)
        assert not taken, (
            f"{module}.py sigue importando {sorted(taken)} desde "
            f"skillgraph.platform.storage. `row_mappers` es una hoja: el "
            f"import directo es seguro y no hay ciclo que lo justifique."
        )

    def test_storage_does_not_reexport_them(self) -> None:
        """`storage.__all__` no anuncia una superficie que no sostiene."""
        storage = importlib.import_module("skillgraph.platform.storage")
        leaked = set(FACADE_EXPORTS) & set(storage.__all__)
        assert not leaked, (
            f"storage.__all__ sigue exportando {sorted(leaked)}, que no se "
            f"usan dentro de storage.py. Anunciar una superficie que no se "
            f"sostiene es el mismo fallo que WI-81, una generacion mas abajo."
        )

    def test_storage_does_not_import_them(self) -> None:
        """No basta con sacarlos de `__all__`: tampoco deben importarse.

        La v1 de este test miraba si `storage.py` importaba desde
        `skillgraph.platform.storage`, o sea desde si mismo. Eso es
        imposible y el test no podia fallar nunca: una asercion vacia es
        peor que no tenerla, porque aparenta cubrir algo. Lo que hay que
        mirar es el modulo del que **si** los saca: `row_mappers`.
        """
        tree = ast.parse((PLATFORM / "storage.py").read_text(encoding="utf-8"))
        taken: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "skillgraph.platform.row_mappers"
            ):
                taken.update(a.name for a in node.names)
        leaked = taken & set(FACADE_EXPORTS)
        assert not leaked, (
            f"storage.py sigue importando {sorted(leaked)} desde row_mappers "
            f"sin usarlos; ruff los borra por F401 en cuanto `__all__` deja "
            f"de declararlos, y con ellos cae el re-export que los herederos "
            f"no necesitan"
        )

    def test_facade_exports_were_never_used_inside_storage(self) -> None:
        """El array de exports que la migracion elimina: 0 usos internos.

        Esta es la medicion que justifica todo el work item. Si un dia un
        simbolo de la lista pasa a usarse dentro de `storage.py`, el
        criterio cambia y este test avisa en vez de dejar que alguien
        'simplifique' el re-export de un simbolo que si hace falta.
        """
        source = (PLATFORM / "storage.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name) and inner.id in FACADE_EXPORTS:
                    pytest.fail(
                        f"storage.py usa {inner.id} en la linea {inner.lineno}. "
                        f"La premisa de WI-86 (re-export sin uso interno) ha "
                        f"cambiado: revisar la decision antes de seguir."
                    )


class TestIdentityIsPreserved:
    """La migracion no puede cambiar el objeto al que resuelve cada consumidor."""

    @pytest.mark.parametrize("symbol", MAPPER_SYMBOLS)
    def test_row_mappers_still_owns_the_mappers(self, symbol: str) -> None:
        assert hasattr(row_mappers, symbol), f"row_mappers perdio {symbol}"

    @pytest.mark.parametrize("module", CONSUMERS)
    def test_consumer_resolves_to_the_row_mappers_object(self, module: str) -> None:
        """Identidad, no igualdad: el simbolo movido es el MISMO objeto."""
        mod = importlib.import_module(f"skillgraph.platform.{module}")
        for symbol in MAPPER_SYMBOLS:
            if not hasattr(mod, symbol):
                continue
            assert getattr(mod, symbol) is getattr(row_mappers, symbol), (
                f"{module}.{symbol} no es el MISMO objeto que "
                f"row_mappers.{symbol}: la migracion sustituyo el simbolo "
                f"por otro equivalente en vez de mover el import"
            )


class TestRowMappersStaysALeaf:
    def test_row_mappers_imports_nothing_that_imports_it(self) -> None:
        """La hoja debe seguir siendolo, o el import directo dejaria de ser seguro."""
        tree = ast.parse((PLATFORM / "row_mappers.py").read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for module in imported:
            assert not module.startswith("skillgraph.platform.storage"), (
                f"row_mappers importa {module}: dejaria de ser una hoja"
            )
            for sibling in CONSUMERS:
                assert not module.endswith(f".{sibling}"), (
                    f"row_mappers importa {module}: ciclo con {sibling}"
                )
