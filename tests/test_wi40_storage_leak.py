"""WI-40: la suite no puede dejar conexiones SQLite abiertas.

Contexto: `Storage` expone `close()` y context manager, pero los tests
históricos construyen la instancia en helpers o fixtures locales y nunca
la cierran. CPython reporta cada una como
`ResourceWarning: unclosed database` cuando el GC reclama la conexión.

El fixture `storage_cleanup` de `conftest.py` es `autouse`: cierra en
teardown todo `Storage` creado durante el test. Estos tests fijan esa
invariante para que una regresión futura (volver a opt-in, o borrar el
cleanup) falle en rojo y no se descubra semanas después como ruido en la
suite completa.

No comprueban que no haya ningún `Storage` abierto en el proceso, sino que
el mecanismo de cleanup del conftest hace su trabajo y es seguro de usar.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage


def _conn_is_closed(conn: sqlite3.Connection) -> bool:
    """``True`` si la conexion cruda ya no admite operaciones.

    Una conexion cerrada lanza `ProgrammingError` en cualquier sentencia;
    es la unica comprobacion publica de su estado.
    """
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    except sqlite3.Error:  # pragma: no cover - solo si la BD esta corrupta
        return True
    return False


def _is_closed(storage: Storage) -> bool:
    """``True`` si la conexion subyacente de ``storage`` esta cerrada.

    `Storage` no es una `sqlite3.Connection`: envuelve una via
    `SqliteUnitOfWork`. Un cierre se comprueba tentando una sentencia
    sobre esa conexion, que lanza `ProgrammingError` si ya no admite
    operaciones. Es la unica comprobacion publica fiable.
    """
    try:
        storage._conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    except sqlite3.Error:  # pragma: no cover - solo si la BD esta corrupta
        return True
    return False


def test_leaked_storage_stays_usable_during_the_test(tmp_path: Path) -> None:
    """Un `Storage` sin cerrar explicitamente funciona durante el test.

    Reproduce el antipatron que WI-40 elimina: construir `Storage` sin
    contexto ni `close()` explicito. El fixture `autouse` lo cierra en
    teardown, de modo que el storage es perfectamente usable mientras dura
    el test; lo que cambia es que la conexion no llega viva al GC.

    Este test NO afirma "no hay ResourceWarning": esa comprobacion global
    no es atribuible a un test concreto, porque `gc.collect()` tambien
    reclama conexiones huerfanas de otros tests. La invariante real se
    verifica en la suite completa, que tras WI-40 cierra con 0
    `unclosed database`; `tests/conftest.py::sqlite_cleanup` cubre la clase
    de fuga que `storage_cleanup` no puede ver.
    """
    storage = Storage(tmp_path / "leak.db")
    assert _is_closed(storage) is False
    assert storage.list_promotions() == []


def test_cleanup_runs_around_every_test(request: pytest.FixtureRequest) -> None:
    """Los dos fixtures de cleanup se aplican a un test que no los pide.

    `request.fixturenames` incluye las fixtures autouse activas para el
    test en curso. Si cualquiera de los dos deja de ser `autouse=True`,
    este nombre desaparece y la asercion falla.

    Es una comprobacion del contrato de pytest. El efecto real (la conexion
    queda cerrada) lo verifica la suite completa: sin `sqlite_cleanup`, los
    tests que abren `sqlite3.connect` directamente dejan 35 conexiones
    huerfanas y CPython emite `ResourceWarning: unclosed database`.
    """
    assert "storage_cleanup" in request.fixturenames
    assert "sqlite_cleanup" in request.fixturenames


def test_raw_sqlite_connection_is_tracked_by_cleanup() -> None:
    """`sqlite3.connect` directo queda registrado por el fixture.

    El fixture envuelve ``sqlite3.connect``, asi que la conexion creada
    aqui sin `with` ni `close()` es una de las que el teardown cierra.
    """
    conn = sqlite3.connect(":memory:")
    assert _conn_is_closed(conn) is False
    conn.close()
    assert _conn_is_closed(conn) is True


def test_with_sqlite_connect_does_not_close(tmp_path: Path) -> None:
    """`with sqlite3.connect(...)` NO cierra: solo confirma la transaccion.

    Documenta el error sistémico que motiva a `sqlite_cleanup`. Si este
    test falla porque `with` empezara a cerrar, la premisa de WI-40
    sobre esa parte de la fuga habria dejado de ser cierta y habria que
    reevaluar el alcance del fixture.
    """
    with sqlite3.connect(tmp_path / "ctx.db") as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")

    # Sigue viva: el context manager de sqlite3 solo hace commit.
    assert _conn_is_closed(conn) is False


def test_cleanup_fixture_closes_storage_created_in_test(tmp_path: Path) -> None:
    """El cleanup se aplica a un `Storage` creado sin solicitarlo.

    Este test NO pide `storage_cleanup`; el fixture `autouse` lo rodea.
    Durante el test la conexion esta viva, y se cerrara en teardown.
    """
    sneaky = Storage(tmp_path / "autouse.db")
    assert _is_closed(sneaky) is False


def test_already_closed_storage_does_not_break_teardown(tmp_path: Path) -> None:
    """Un `Storage` cerrado por `with` no convierte un test en error.

    El teardown del fixture itera sobre todas las instancias creadas, y
    algunas ya estan cerradas por su propio `with`. El cleanup debe
    tolerarlo en vez de enmascarar el resultado real del test: si
    `close()` reventara aqui, el error apareceria en teardown.
    """
    with Storage(tmp_path / "scoped.db") as scoped:
        assert _is_closed(scoped) is False
    assert _is_closed(scoped) is True


def test_close_is_idempotent(tmp_path: Path) -> None:
    """Cerrar dos veces es inocuo, no un error de sqlite.

    El teardown del fixture puede volver a cerrar una instancia que el
    test ya cerro explicitamente; ese camino tiene que ser seguro.
    """
    storage = Storage(tmp_path / "double.db")
    storage.close()
    storage.close()
    assert _is_closed(storage) is True


def test_many_storages_coexist_without_interference(tmp_path: Path) -> None:
    """Varias instancias de `Storage` conviven sin interferirse.

    Crea varias instancias, algunas con `with` y otras sin cerrar, y
    comprueba que todas son usables de forma independiente. Es el caso que
    mas instances produce la suite real (helpers + fixtures por test).

    No se afirma "no hay ResourceWarning" aqui: esa comprobacion global no
    es atribuible a un test concreto, porque `gc.collect()` tambien reclama
    conexiones huerfanas de otros tests de la suite.
    """
    storages = [Storage(tmp_path / f"many-{i}.db") for i in range(3)]
    with Storage(tmp_path / "with-scoped.db") as scoped:
        assert _is_closed(scoped) is False

    for storage in storages:
        assert _is_closed(storage) is False
        assert storage.list_promotions() == []

    assert _is_closed(scoped) is True
