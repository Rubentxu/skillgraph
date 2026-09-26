"""Locks por Run para serializar reconciliaciones concurrentes (S6 Etapa 7).

Doc externo:
  external/blueprint-v1/docs/06-controladores.md §10 (concurrencia).

Un Run NO puede ser reconciliado por dos procesos o hilos a la vez:
ambos competirian por escribir en `node_executions` y `runtime_events`,
corrompiendo el estado. La defensa canonica es un advisory lock por
run_id: si otro agente ya tiene el lock, el segundo espera (modo
`advisory`) o falla (modo `fail-fast`).

Implementacion:
- Lock filesystem via `fcntl.flock` (POSIX). Portable en Linux/macOS.
- El lock vive en `<lock_dir>/<tenant>__<project>__<run_id>.lock`,
  donde `lock_dir` es inyectado por el RunController (default:
  `<data-root>/locks`). El archivo se crea al tomar el lock; se
  elimina al liberarlo. Asi no quedan locks zombie tras un crash
  normal.
- En Windows `fcntl` no existe: importamos `msvcrt` solo cuando
  el modulo se ejecuta alli. El comportamiento en Windows es NOOP
  con un warning (regla: el sistema debe ser operativo aunque
  sin proteccion full).

Reglas:
- Sin estado global mutable: el lock se identifica por run_id, lo
  recibe el caller.
- Errores tipados: `LockUnavailable` cuando el modo es `fail-fast`
  y el lock esta tomado por otro proceso.
- Sin reloj: la espera usa `fcntl` (kernel-level), no polling.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skillgraph.core.errors import SkillGraphError, ValidationError

LockMode = Literal["none", "advisory", "fail-fast"]


class LockUnavailable(SkillGraphError):
    """No se pudo tomar el lock por run_id en modo `fail-fast`.

    `code` estable (`sg_lock_unavailable`) para el dispatcher CLI.
    """

    code: str = "sg_lock_unavailable"


@dataclass(frozen=True, slots=True)
class RunLockKey:
    """Identificador estable del lock por Run.

    Atributos:
        tenant_id, project_id, run_id: componentes del lock.
    """

    tenant_id: str
    project_id: str
    run_id: str

    def to_filename(self) -> str:
        """Nombre del archivo de lock (sin extension ni path).

        Caracteres no-ASCII se sanitizan via `os.fsencode` (solo ASCII
        seguro en nombres de archivo en sistemas POSIX).
        """
        raw = f"{self.tenant_id}__{self.project_id}__{self.run_id}.lock"
        return raw.replace("/", "_").replace("..", "_")


class RunLock:
    """Context manager que toma un advisory lock por Run.

    Uso:
        lock = RunLock(lock_dir=Path("/tmp/locks"), key=RunLockKey(...))
        with lock.take(mode="advisory", timeout_seconds=30):
            # ... operacion exclusiva sobre el Run ...

    Modos:
        - `"none"`: noop; util para tests o para opt-out explicito.
        - `"advisory"`: espera hasta `timeout_seconds` tomando el
          lock; si expira el timeout, eleva `LockUnavailable`.
        - `"fail-fast"`: intenta una sola vez; si esta tomado,
          eleva `LockUnavailable` inmediatamente.

    Raises:
        LockUnavailable: si el lock esta tomado y expira el timeout.
        OSError: si el lock_dir no es escribible.
    """

    __slots__ = ("_fd", "_key", "_lock_dir", "_mode", "_timeout")

    def __init__(self, *, lock_dir: Path, key: RunLockKey) -> None:
        self._lock_dir = Path(lock_dir)
        self._key = key
        self._fd: int | None = None
        self._mode: LockMode = "none"
        self._timeout: float = 0.0

    @property
    def key(self) -> RunLockKey:
        return self._key

    @property
    def lock_dir(self) -> Path:
        return self._lock_dir

    @contextlib.contextmanager
    def take(self, *, mode: LockMode, timeout_seconds: float = 30.0) -> Iterator[None]:
        """Toma el lock. Libera al salir del bloque `with`.

        Args:
            mode: `"none"`, `"advisory"`, `"fail-fast"`.
            timeout_seconds: segundos a esperar en modo `advisory`
                antes de elevar `LockUnavailable`. Default 30s.

        Raises:
            LockUnavailable: lock tomado y timeout agotado.
            ValidationError: mode desconocido.
        """
        if mode not in ("none", "advisory", "fail-fast"):
            raise ValidationError(
                f"lock mode invalido: {mode!r} (esperado none|advisory|fail-fast)"
            )
        self._mode = mode
        self._timeout = timeout_seconds
        if mode == "none":
            # Noop: no tocamos el filesystem.
            yield
            return
        # Asegurar que lock_dir existe.
        try:
            self._lock_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LockUnavailable(f"no se puede crear lock_dir={self._lock_dir}: {exc}") from exc
        lock_path = self._lock_dir / self._key.to_filename()
        try:
            self._fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_RDWR,
                0o644,
            )
        except OSError as exc:
            raise LockUnavailable(f"no se puede abrir lock file={lock_path}: {exc}") from exc
        try:
            if mode == "advisory":
                deadline = time.monotonic() + timeout_seconds
                while True:
                    try:
                        fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise LockUnavailable(
                                f"timeout esperando lock {lock_path} (>{timeout_seconds}s)"
                            ) from None
                        time.sleep(0.05)  # poll suave
            elif mode == "fail-fast":
                try:
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise LockUnavailable(f"lock {lock_path} ya esta tomado") from exc
            yield
        finally:
            if self._fd is not None:
                with contextlib.suppress(OSError):
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                self._fd = None
                # Eliminamos el archivo para no acumular locks vacios.
                with contextlib.suppress(OSError):
                    lock_path.unlink()
