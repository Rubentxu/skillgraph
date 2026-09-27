"""Fixtures y configuración compartida para la suite de SkillGraph.

Reglas de la estrategia de tests (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Fixtures sin credenciales, red ni proveedor LLM.
- Aislamiento: cada test que toque el sistema de archivos recibe un
  `tmp_path` propio (pytest lo inyecta automáticamente). Aquí solo
  exponemos fábricas deterministas.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

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


@pytest.fixture
def storage_cleanup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cierra los ``Storage`` creados por un test legacy al finalizarlo.

    Algunos módulos históricos construyen ``Storage`` directamente en helpers
    en vez de inyectarlo mediante una fixture. El fixture conserva la
    propiedad de la conexión dentro del test y garantiza el cierre explícito
    en el teardown, sin introducir un ``__del__`` silencioso en producción.
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
