"""Fixtures y configuración compartida para la suite de SkillGraph.

Reglas de la estrategia de tests (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Fixtures sin credenciales, red ni proveedor LLM.
- Aislamiento: cada test que toque el sistema de archivos recibe un
  `tmp_path` propio (pytest lo inyecta automáticamente). Aquí solo
  exponemos fábricas deterministas.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from skillgraph.platform.storage import Storage


@pytest.fixture
def fixtures_dir() -> Path:
    """Raíz de fixtures versionadas: `tests/fixtures/`."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tmp_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Directorio de datos aislado y variable de inyección para el núcleo.

    Cada test recibe un `tmp_path` único (pytest) y el helper fija las
    variables de entorno que el núcleo debe respetar durante este test
    (skillgraph todavía no las lee; el contrato se introduce en e1-1).
    """
    root = tmp_path / "skillgraph-data"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SKILLGRAPH_DATA_ROOT", str(root))
    yield root
    # monkeypatch restaura las variables automáticamente al salir del test.


@pytest.fixture(autouse=True)
def storage_cleanup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cierra todo ``Storage`` creado durante el test, sin opt-in por módulo.

    ``Storage`` expone ``close()`` y context manager (WI-15 / v0.15.0), pero
    muchos tests históricos construyen la instancia en helpers o fixtures
    locales y nunca la cierran. Cada uno deja una ``sqlite3.Connection``
    abierta, que CPython reporta como ``ResourceWarning: unclosed database``
    cuando el GC la reclama.

    Antes de WI-40 el cleanup era opt-in (``storage_cleanup`` como fixture
    normal) y solo lo adoptaban 6 ficheros; los ~154 creators restantes
    fugaban. Al ser ``autouse=True`` el cierre pasa a ser una invariante
    de la suite en vez de una disciplina por fichero.

    El cierre ocurre en orden inverso al de construcción para respetar
    dependencias de teardown. No necesita proteccion extra: `Storage.close()`
    ya es idempotente y suprime `sqlite3.ProgrammingError`, asi que una
    instancia que el test cerro con `with` no rompe el teardown.

    No se introduce un ``__del__`` en producción: la propiedad de la
    conexión sigue siendo del que la abre (AGENTS.md §8, R2).
    """
    created: list[Storage] = []
    original_init = Storage.__init__

    def tracked_init(storage: Storage, path: str | Path) -> None:
        original_init(storage, path)
        created.append(storage)

    monkeypatch.setattr(Storage, "__init__", tracked_init)
    yield
    for storage in reversed(created):
        storage.close()


@pytest.fixture(autouse=True)
def sqlite_cleanup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cierra las conexiones ``sqlite3`` crudas creadas durante el test.

    Complementa a `storage_cleanup`, que solo ve las instancias de
    ``Storage``. Quedan conexiones sueltas por dos motivos:

    1. Tests que abren la conexión directamente (``sqlite3.connect``) para
       inspeccionar o sembrar la base: helpers de verificación de CLI,
       ``EventLog`` sobre ``:memory:`` y aserciones de importer.
    2. ``with sqlite3.connect(path) as conn`` NO cierra la conexión: el
       context manager de ``sqlite3`` solo confirma la transacción. Quien
       aplica el idiom de los context managers espera un cierre que no existe.

    El fixture envuelve ``sqlite3.connect`` y cierra en teardown, en orden
    inverso, todo lo que el test dejó abierto. Es la misma invariante que
    `storage_cleanup`, pero para la clase de fuga que aquel no puede ver.

    Se instrumenta el punto de creación en vez de parchear los ~10 sitios
    uno a uno porque: (a) ``with sqlite3.connect`` es un error sistémico, no
    un descuido puntual, y corregirlo a mano no cierra la clase de fuga; y
    (b) la suite no tiene fixtures ``module``/``session`` que reutilicen una
    conexión entre tests, así que cerrar al final de cada test nunca pisa
    recursos compartidos.
    """
    created: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect

    def tracked_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = original_connect(*args, **kwargs)
        created.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    yield
    for conn in reversed(created):
        # Una conexión ya cerrada o en estado inválido no debe enmascarar el
        # resultado real del test: el cleanup nunca es el motivo del fallo.
        with suppress(sqlite3.Error):
            conn.close()
