# WI-23: deuda H-03 (runtime.locks.Take cc=16)

## Objetivo

Reducir cc de `RunLock.take` (cc=16) en
`src/skillgraph/runtime/locks.py`. El alto cc venia del bucle
while-with-retry + try/except anidados en `advisory`, mas el
try/except separado de `fail-fast`.

## Cambio

`take` queda como orquestador puro (5 ramas de decision) con 4
helpers privados:

- `_acquire_with_timeout(fd, lock_path, *, timeout_seconds)`
  (estatico, cc=4): bucle de espera en modo `advisory`.
- `_acquire_fail_fast(fd, lock_path)` (estatico, cc=2): intento
  unico con `LOCK_NB`.
- `_open_lock(lock_path) -> int` (cc=3): mkdir + os.open, ambos
  con su propio `LockUnavailable` tipado.
- `_release(fd, lock_path)` (cc=1): best-effort flock(UN) +
  os.close + unlink.

## Compatibilidad

- 100% backward-compatible: mismos `LockUnavailable` con los mismos
  mensajes ("timeout esperando lock X (>Ys)" / "lock X ya esta
  tomado" / "no se puede crear lock_dir=X" / "no se puede abrir
  lock file=X").
- Mismo `ValidationError` ante mode invalido.
- 14/14 tests PASS en `tests/test_locks.py`.

## Decision previa (D-55)

- **D-55**: Context manager "tomar lock" tiene 4 fases
  (validar mode, abrir, adquirir, release). Cada fase se extrae
  a helper para que `take` solo coordine. Acquire se descompone
  en `_acquire_with_timeout` y `_acquire_fail_fast` (statics,
  sin self) para ser testables sin instancia.

## Evidencia

- `take` cc: 16 -> 5.
- 4 helpers extraidos, cc <= 4 cada uno.
- 1044/1044 PASS en suite completa (177.22s).
- ruff: All checks passed.
