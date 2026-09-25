"""Tests para `tests._evidence_lock` (DT-2 stewardship backlog).

Contratos verificados:
- Escritura simple produce JSON valido y deja el lock file.
- Escritura concurrente al mismo uat_id produce un archivo final
  coherente (una sola evidencia, JSON valido).
- Escritura concurrente a uat_ids distintos NO se bloquea entre si.
- El contexto `evidence_lock` libera al salir del `with`.
- El fallback de fcntl en Windows no rompe la consistencia (cubierto
  via monkeypatch del modulo, ya que la plataforma real es Linux).
- `save_with_lock` crea `evidence_dir` si no existe (idempotente).
- `history_keep=True` archiva la version previa en
  `history/<uat_id>/<timestamp>-<status>.json`.
- Escritura atomica: aunque el caller pase un payload no serializable,
  no se corrompe el archivo previo.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests._evidence_lock import _HAS_FCNTL, evidence_lock, save_with_lock


def test_save_with_lock_creates_file_and_lock(tmp_path: Path) -> None:
    """Escritura simple produce JSON valido y deja lock file."""
    target = save_with_lock(tmp_path, "UAT-01", {"uat_id": "UAT-01", "status": "PASS"})
    assert target.is_file()
    assert target.name == "UAT-01.json"
    lock_path = tmp_path / "UAT-01.lock"
    assert lock_path.is_file(), "lock file debe persistir tras la escritura"
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {"uat_id": "UAT-01", "status": "PASS"}


def test_save_with_lock_creates_evidence_dir(tmp_path: Path) -> None:
    """`evidence_dir` se crea si no existe."""
    nested = tmp_path / "deep" / "nested" / "evidence"
    assert not nested.exists()
    save_with_lock(nested, "UAT-02", {"x": 1})
    assert nested.is_dir()
    assert (nested / "UAT-02.json").is_file()


def test_concurrent_writes_same_uat_id_produce_valid_json(tmp_path: Path) -> None:
    """N hilos escribiendo al mismo uat_id: el archivo final es JSON valido.

    Verifica que el lock previene la corrupcion del archivo. Sin lock,
    los hilos podrian entrelazar `write_text` y dejar un archivo
    parcialmente escrito. El contrato es: el archivo final contiene
    EXACTAMENTE el JSON de UNO de los hilos (no una mezcla).
    """
    n_threads = 8
    payloads = [{"uat_id": "UAT-CC", "thread_id": i, "data": "x" * 100} for i in range(n_threads)]

    def writer(payload: dict) -> None:
        save_with_lock(tmp_path, "UAT-CC", payload)

    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        list(ex.map(writer, payloads))

    target = tmp_path / "UAT-CC.json"
    assert target.is_file()
    # El JSON debe ser parseable y pertenecer a UNO de los payloads originales.
    parsed = json.loads(target.read_text(encoding="utf-8"))
    assert parsed in payloads, f"Archivo final no es ninguno de los payloads escritos: {parsed}"


def test_concurrent_writes_distinct_uat_ids_dont_block(tmp_path: Path) -> None:
    """N hilos escribiendo a uat_ids distintos NO se bloquean entre si.

    Verifica la granularidad fina del lock: cada uat_id tiene su propio
    lock file, asi que escritores a uat_ids distintos son paralelos.
    """
    n_threads = 6

    def writer(i: int) -> None:
        save_with_lock(tmp_path, f"UAT-{i:02d}", {"uat_id": f"UAT-{i:02d}", "i": i})

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        list(ex.map(writer, range(n_threads)))
    elapsed = time.monotonic() - start

    # Cada archivo debe existir y contener su payload.
    for i in range(n_threads):
        target = tmp_path / f"UAT-{i:02d}.json"
        assert target.is_file()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data == {"uat_id": f"UAT-{i:02d}", "i": i}

    # Si los locks fuesen globales, N escrituras secuenciales con el
    # `os.replace` costarian mas. Aqui exigimos que el tiempo total
    # sea claramente sub-lineal (heuristica: <2x una sola escritura).
    # No es un test estricto de paralelismo (CI ruidoso), pero detecta
    # regresiones obvias tipo "todos los writers van al mismo lock".
    single_start = time.monotonic()
    save_with_lock(tmp_path, "UAT-SOLO", {"a": 1})
    single_elapsed = time.monotonic() - single_start
    # Si el lock se volviera global, `elapsed` ~ n * single_elapsed.
    # Permitimos 4x de margen para jitter de CI.
    assert elapsed < single_elapsed * 4 + 0.5, (
        f"Escrituras concurrentes a uat_ids distintos tardan {elapsed:.3f}s "
        f"vs single {single_elapsed:.3f}s; lock parece global"
    )


def test_history_keep_archives_previous(tmp_path: Path) -> None:
    """Con history_keep=True, la version previa se archiva antes de sobreescribir."""
    save_with_lock(tmp_path, "UAT-H", {"uat_id": "UAT-H", "version": 1, "status": "OLD"})
    save_with_lock(tmp_path, "UAT-H", {"uat_id": "UAT-H", "version": 2}, history_keep=True)
    hist_dir = tmp_path / "history" / "UAT-H"
    assert hist_dir.is_dir()
    archived = list(hist_dir.iterdir())
    assert len(archived) == 1, f"esperaba 1 archivo archivado, encontre {len(archived)}"
    archived_data = json.loads(archived[0].read_text(encoding="utf-8"))
    assert archived_data["version"] == 1
    assert archived_data["status"] == "OLD"
    # El archivo final es la version 2.
    final = json.loads((tmp_path / "UAT-H.json").read_text(encoding="utf-8"))
    assert final["version"] == 2


def test_history_keep_false_does_not_archive(tmp_path: Path) -> None:
    """Con history_keep=False (default), no se archiva la version previa."""
    save_with_lock(tmp_path, "UAT-NH", {"v": 1})
    save_with_lock(tmp_path, "UAT-NH", {"v": 2})  # history_keep=False por default
    assert not (tmp_path / "history").exists()


def test_evidence_lock_context_manager_releases() -> None:
    """El context manager `evidence_lock` adquiere y libera el lock."""
    with tempfile_for_test() as tmp:
        with evidence_lock(tmp, "UAT-CTX"):
            # Dentro del bloque, otro intento de tomar el mismo lock
            # bloquearia; no lo verificamos por timing, sino por
            # observacion: el lock file existe.
            assert (tmp / "UAT-CTX.lock").is_file()
        # Tras el with, el lock fd esta cerrado. El archivo `.lock`
        # puede seguir presente (patron de runtime/locks.py).
        assert (tmp / "UAT-CTX.lock").is_file()


def test_windows_fallback_does_not_corrupt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Si fcntl no esta disponible, la escritura sigue siendo atomica via os.replace."""
    # Forzar el path de "no fcntl" sin importar fcntl realmente.
    monkeypatch.setattr("tests._evidence_lock._HAS_FCNTL", False)
    target = save_with_lock(tmp_path, "UAT-WIN", {"x": 1})
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {"x": 1}


def test_payload_not_serializable_raises(tmp_path: Path) -> None:
    """Payload no serializable a JSON lanza TypeError, no corrompe el archivo previo."""
    save_with_lock(tmp_path, "UAT-ERR", {"before": True})
    with pytest.raises(TypeError):
        save_with_lock(tmp_path, "UAT-ERR", {"set_field": {1, 2, 3}})  # set no es JSON
    # El archivo previo sigue intacto.
    final = json.loads((tmp_path / "UAT-ERR.json").read_text(encoding="utf-8"))
    assert final == {"before": True}


def test_real_world_concurrent_uat_writers(tmp_path: Path) -> None:
    """Smoke test que reproduce el patron real: 2 uat_ids distintos,
    varios writers cada uno, contenido coherente."""
    # Simula pytest-xdist con 2 workers.
    barrier = threading.Barrier(4)

    def writer(uat_id: str, idx: int) -> None:
        barrier.wait()  # Sincronizar para maxima contention
        save_with_lock(tmp_path, uat_id, {"uat_id": uat_id, "idx": idx})

    threads = [
        threading.Thread(target=writer, args=("UAT-A", 1)),
        threading.Thread(target=writer, args=("UAT-A", 2)),
        threading.Thread(target=writer, args=("UAT-B", 1)),
        threading.Thread(target=writer, args=("UAT-B", 2)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # Cada uat_id tiene un archivo coherente.
    for uat_id in ("UAT-A", "UAT-B"):
        data = json.loads((tmp_path / f"{uat_id}.json").read_text(encoding="utf-8"))
        assert data["uat_id"] == uat_id
        assert data["idx"] in {1, 2}


# --- helpers ---


@contextmanager
def tempfile_for_test():
    """Crea un tmp_path-like para tests que usan `with`.

    Yields un Path unico por test (pytest tmp_path se inyecta pero
    este contextmanager aísla el ciclo de vida del lock fd).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.mark.skipif(not _HAS_FCNTL, reason="fcntl no disponible")
def test_has_fcntl_on_linux() -> None:
    """En Linux (CI), fcntl esta disponible y se usa el lock real."""
    assert _HAS_FCNTL is True
