"""Helper centralizado para escribir evidencia UAT con lock por uat_id.

Historia y motivacion (DT-2 del stewardship backlog):
- `_save_evidence` en `uat_audit.py` ya tenia `fcntl.flock` desde H8.
- `_emit_uat_08_evidence` y `_emit_uat_09_evidence` en
  `test_h4_expansion_cli.py` escribian SIN lock (riesgo bajo porque los
  tests corren seriales hoy, pero documentado en STATE.yaml como lock
  pendiente para cuando se active pytest-xdist).
- Este modulo centraliza el patron de lock para que cualquier escritor
  futuro herede la proteccion sin reinventarla.

Reglas:
- Lock por `uat_id` (granularidad fina: dos UATs distintos no se
  bloquean entre si).
- Escritura atomica via `os.replace` desde `.tmp`: el lector nunca ve
  un archivo parcialmente escrito.
- `fcntl.flock` es POSIX; en Windows cae a un no-op silencioso con
  warning (mismo patron que `runtime/locks.py`).
- El archivo `.lock` se mantiene tras la escritura (mismo patron que
  `runtime/locks.py`); el `flock` se libera al salir del `with`, pero
  el inode vive. Esto es intencional: `flock` libera el lock al cerrar
  el fd, no requiere borrar el archivo.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# fcntl es POSIX. En Windows cae al fallback no-op.
try:
    import fcntl  # type: ignore[import-not-found]

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False


def save_with_lock(
    evidence_dir: Path,
    uat_id: str,
    payload: dict[str, Any],
    *,
    history_keep: bool = False,
) -> Path:
    """Escribe `payload` como `<uat_id>.json` bajo `evidence_dir` con lock.

    Args:
        evidence_dir: directorio donde persiste `tests/uat-evidence/`.
        uat_id: identificador del UAT (e.g. ``"UAT-08"``); tambien
            determina el nombre del archivo y del lock.
        payload: dict serializable a JSON.
        history_keep: si True, antes de sobreescribir archiva la version
            previa en ``history/<uat_id>/<timestamp>-<status>.json``
            (patron de H8, usado solo por `_save_evidence` de uat_audit.py).
            Default False (escritura idempotente sin historial).

    Returns:
        Path al archivo final escrito.

    Raises:
        TypeError: si `payload` no es serializable a JSON.
        OSError: si no se puede crear `evidence_dir` o el lock file.
    """
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out = evidence_dir / f"{uat_id}.json"
    lock_path = evidence_dir / f"{uat_id}.lock"
    content = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)

    # Lock por uat_id. Si fcntl no esta disponible (Windows), cae a
    # no-op silencioso: el resto de la escritura sigue siendo atomica
    # via os.replace, asi que no se rompe la consistencia, solo se
    # pierde la serializacion entre procesos concurrentes.
    with lock_path.open("w") as lock_fd:
        if _HAS_FCNTL:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError as exc:
                print(
                    f"warning: flock fallo en {lock_path}: {exc}; "
                    f"cayendo a escritura sin lock ({sys.platform})",
                    file=sys.stderr,
                )
        try:
            if history_keep and out.exists():
                _archive_previous(out, evidence_dir / "history" / uat_id)
            _atomic_write(out, content)
        finally:
            if _HAS_FCNTL:
                with contextlib.suppress(OSError):
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    return out


def _archive_previous(out: Path, hist_dir: Path) -> None:
    """Archiva la version previa de `out` en `hist_dir` antes de sobreescribir."""
    hist_dir.mkdir(parents=True, exist_ok=True)
    try:
        prev = json.loads(out.read_text(encoding="utf-8"))
        stamp = prev.get("verified_at") or prev.get("timestamp") or _now_iso()
        prev_status = prev.get("status", "UNKNOWN")
    except (ValueError, TypeError):
        stamp, prev_status = _now_iso(), "UNKNOWN"
    arch = hist_dir / f"{stamp.replace(':', '')}-{prev_status}.json"
    if not arch.exists():
        arch.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")


def _atomic_write(target: Path, content: str) -> None:
    """Escribe `content` a `target` via `.tmp` + `os.replace` (atomico)."""
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _now_iso() -> str:
    """ISO 8601 UTC sin microsegundos (mismo patron que `runtime/engine.py`)."""
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextlib.contextmanager
def evidence_lock(evidence_dir: Path, uat_id: str):
    """Context manager de lock por uat_id sin escritura automatica.

    Util cuando el caller quiere hacer multiples operaciones bajo el
    mismo lock (e.g. archivar + escribir + notificar).

    Args:
        evidence_dir: directorio del lock.
        uat_id: identificador del UAT.
    """
    evidence_dir.mkdir(parents=True, exist_ok=True)
    lock_path = evidence_dir / f"{uat_id}.lock"
    with lock_path.open("w") as lock_fd:
        if _HAS_FCNTL:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError as exc:
                print(
                    f"warning: flock fallo en {lock_path}: {exc}",
                    file=sys.stderr,
                )
        try:
            yield
        finally:
            if _HAS_FCNTL:
                with contextlib.suppress(OSError):
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
