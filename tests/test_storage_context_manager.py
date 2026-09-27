"""Tests QW-C: Storage como context manager.

Cierra el derivado de los 303 ``ResourceWarning: unclosed database``
en pytest: ``Storage(path)`` debe soportar ``with`` para que el
cuerpo del bloque NO tenga que recordar ``storage.close()``.

Verifica:
- Context manager cierra la conexion al salir.
- Doble ``close()`` es idempotente (no rompe).
- Excepcion dentro del ``with`` se propaga despues de cerrar.
- Tests existentes con ``storage.close()`` explicito siguen funcionando
  (compatibilidad hacia atras).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage


class TestStorageContextManager:
    """QW-C: ``with Storage(path) as s: ...`` cierra al salir."""

    def test_with_closes_connection_on_exit(self, tmp_path: Path) -> None:
        """``with`` cierra la conexion SQLite sin ResourceWarning."""
        db = tmp_path / "test.db"
        with Storage(db) as s:
            s._conn.execute("CREATE TABLE t(x INTEGER)")
            s._conn.execute("INSERT INTO t VALUES (1)")
            conn = s._conn
        # Tras salir del with, la conexion fue cerrada.
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_with_propagates_exception(self, tmp_path: Path) -> None:
        """Excepcion en el cuerpo se propaga despues de cerrar."""
        db = tmp_path / "test.db"
        with pytest.raises(ValueError, match="boom"):
            with Storage(db) as s:
                s._conn.execute("CREATE TABLE t(x INTEGER)")
                raise ValueError("boom")
        # Conexion cerrada: la instancia queda en estado consistente.
        # Reabrir y leer debe funcionar.
        with Storage(db) as s2:
            rows = s2._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert any("t" in r[0] for r in rows)

    def test_double_close_is_idempotent(self, tmp_path: Path) -> None:
        """``close()`` puede llamarse 2 veces sin error."""
        db = tmp_path / "test.db"
        s = Storage(db)
        s.close()
        # Segunda llamada: no raise.
        s.close()

    def test_with_then_manual_close_idempotent(self, tmp_path: Path) -> None:
        """``with`` + ``close()`` explicito: no rompe."""
        db = tmp_path / "test.db"
        with Storage(db) as s:
            s._conn.execute("CREATE TABLE t(x INTEGER)")
        # Llamar close() despues del with: idempotente.
        s.close()

    def test_legacy_close_still_works(self, tmp_path: Path) -> None:
        """Tests legacy con ``s = Storage(...); s.close()`` siguen OK."""
        db = tmp_path / "test.db"
        s = Storage(db)
        s._conn.execute("CREATE TABLE t(x INTEGER)")
        s._conn.execute("INSERT INTO t VALUES (42)")
        rows = s._conn.execute("SELECT x FROM t").fetchall()
        assert rows[0][0] == 42
        s.close()
        with pytest.raises(sqlite3.ProgrammingError):
            s._conn.execute("SELECT 1")

    def test_with_returns_storage(self, tmp_path: Path) -> None:
        """``__enter__`` devuelve el Storage (no un proxy)."""
        db = tmp_path / "test.db"
        with Storage(db) as s:
            assert isinstance(s, Storage)
            # Podemos llamar metodos tipicos.
            assert s.path == db


@pytest.fixture
def tmp_path_for_storage(tmp_path: Path) -> Path:
    """Helper: paths de Storage en tmpdir."""
    return tmp_path