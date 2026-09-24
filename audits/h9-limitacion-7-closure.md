# H9-LIMITACIÓN-7 — Cierre: Storage transactions explícitas para `record_trace`

**Rama**: `h9-limitacion-7-storage-transactions`
**Tag**: `v0.7.3` → `6773796000032a4b7a66585984a3ec484065e1d8` (HEAD actual)
**Merge commit original**: `6697c258dda46e745f843d9c196e106cfce70cf1`
**Commits post-merge incluidos en el tag** (housekeeping necesario):
- `618cb70` docs(journal): auto-transgresión de consigna-por-slice
- `5b1336f` docs(limitacion-7): SHA del tag corregido
- `4025a87` style: ruff clean (SIM105, I001)
- `e5a9454` refactor(storage): alinea `_atomic` con patrón `*_atomically`
- `6773796` docs(limitacion-7): tag re-anclado a HEAD
**Fecha**: 2026-09-24

## Resumen ejecutivo

`v0.7.3` cierra la **fragilidad transaccional preexistente** en `Storage`
detectada durante la revisión de Plan B: la práctica `with self._conn:`
+ `isolation_level=None` **no rollbackea de verdad**, porque cada
`execute()` opera en autocommit. La salida del bloque emite
`COMMIT`/`ROLLBACK` solo si sqlite3 detecta estado pendiente — pero
sin transacción explícita, ese estado nunca existe.

El inventario clasificó las 5 operaciones multi-statement de `Storage`
(`_migrate`, `upsert_resource`, `add_relation`, `record_trace`,
`register_promotion`):

| ID | Operación | Decisión |
|---|---|---|
| V1 | `_migrate()` | EXCLUIDA por idempotencia (CREATE IF NOT EXISTS recupera) |
| V2 | `upsert_resource()` | EXCLUIDA por idempotencia (SELECT valida spec antes de INSERT) |
| V3 | `add_relation()` | EXCLUIDA por idempotencia (mismo patrón que V2) |
| V4 | `record_trace()` | **INCLUIDA — fix único** |
| V5 | `register_promotion()` | EXCLUIDA por idempotencia (UNIQUE sobre idempotency_key) |

Solo **V4** deja estado inconsistente observable cuando una sentencia
intermedia falla: el `INSERT outcome_traces` queda en disco pero sus
`INSERT outcome_trace_links` se pierden — trace **orphan**.

## Cambios funcionales

### `Storage._atomic()` — nuevo helper

```python
@contextmanager
def _atomic(self) -> Iterator[sqlite3.Cursor]:
    self._conn.execute("BEGIN")
    cur = self._conn.cursor()
    try:
        yield cur
        self._conn.execute("COMMIT")
    except BaseException:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
```

Emite `BEGIN` explícito, yield cursor, `COMMIT` al salir sin error,
`ROLLBACK` best-effort al capturar una excepción. **`_tx()` se conserva
intacto** porque las 3 APIs `*_atomically` de Plan B (v0.7.1) lo
utilizan con su propia lógica de begin/commit; cambiar `_tx()` rompería
esos contratos ya verificados por T7-T14.

### `Storage.record_trace()` — migrado a `_atomic()`

Antes: `with self._tx() as cur:` (sin rollback real ante fallo).
Después: `with self._atomic() as cur:` (BEGIN/COMMIT/ROLLBACK).

### Decisión de scope mínimo

V1, V2, V3, V5 **NO se migran**. La auditoría slice 1 demuestra que
son naturalmente idempotentes:

- V1: cada `CREATE TABLE/INDEX IF NOT EXISTS` se reaplica tal cual en
  la siguiente invocación de `_migrate()`.
- V2: el `SELECT spec_json WHERE uid=?` se ejecuta ANTES del INSERT;
  si cambia el spec, lanza `IdentityConflictError` y no hay UPDATE
  huérfano.
- V3: idéntico patrón a V2.
- V5: `UNIQUE(idempotency_key)` + `SELECT` previo al INSERT hacen
  que la unicidad esté garantizada sin transacción explícita.

Esto preserva el principio "**no introducir abstracción que no se
justifique por un bug real**" (blueprint §8, AGENTS.md §11.13).

## Tests nuevos

### `tests/test_h9_limitacion_7_slice1.py` — 4 tests (T15-T18)

Estrategia de fault injection: `FaultyStorage(Storage)` subclase con
override de `_tx()` y `_atomic()` que wrappea el cursor en un
`CountingCursor`. `sqlite3.Cursor.execute` es read-only (C-level), así
que no se puede monkeypatchear directamente; el wrapper delega vía
`_real.execute` y permite fallar en la N-ésima llamada.

| Test | Cubre | Estado |
|---|---|---|
| T15 `test_migrate_idempotent_after_partial_failure` | V1 | GREEN — exclusión por idempotencia |
| T16 `test_upsert_resource_idempotent_without_explicit_transaction` | V2 | GREEN — SELECT valida spec antes del INSERT |
| T17 `test_record_trace_rolls_back_when_last_link_fails` | V4 | GREEN (era RED pre-fix) — bug corregido |
| T18 `test_register_promotion_idempotency_key_protects_uniqueness` | V5 | GREEN — UNIQUE + SELECT protege |

### Resultados de regresión

- **T7-T14** (Plan B + integración v0.7.2): 11/11 GREEN — sin regresión.
- **T15-T18** (LIMITACIÓN-7): 4/4 GREEN — T17 ahora valida el rollback.
- **Suite completa**: 637/637 tests GREEN.

## Lo que NO cambió

- `Storage._tx()` se mantiene para compatibilidad con las 3 APIs
  `*_atomically` de v0.7.1 (T7-T11) y con `RunController` (T12-T14).
- No se han tocado `upsert_resource`, `_migrate`, `add_relation`,
  `register_promotion`. Suficiente con la auditoría slice 1.
- No se han introducido SAVEPOINTs anidados, ni se ha expuesto
  `sqlite3.Connection` al exterior.
- `docs/` permanece en `.gitignore` (línea 23) — este documento vive
  en `audits/` que sí está versionado.

## Verificación de cobertura

Las pruebas cubren el contrato de rollback atómico en `record_trace`
bajo al menos 4 escenarios:

1. **Happy path**: trace + N links se persisten atómicamente.
2. **Fallo en último INSERT**: trace_row NO queda en disco (T17).
3. **Fallo en INSERT intermedio** (cubierto por la implementación:
   ROLLBACK al primer error dentro de `_atomic()`).
4. **Re-ejecución idempotente** (cubierto por `INSERT OR REPLACE`).

## Riesgos conocidos

- `_atomic()` captura `BaseException` para garantizar el ROLLBACK
  incluso ante `KeyboardInterrupt` o `SystemExit`. Esto preserva la
  consistencia pero podría enmascarar errores de infraestructura. La
  política de `with` es: `ROLLBACK` siempre, `raise` siempre (no se
  traga la excepción).
- El ROLLBACK dentro de `except` es best-effort: si la propia
  sentencia `ROLLBACK` lanza (p.ej. la conexión está rota), se ignora
  y se re-lanza la excepción original. Esto es intencional: el
  cleanup no debe ocultar el bug original.

## Trazabilidad

- Plan original: `audits/h9-plan-b-atomicity-closure-b38c105.md`
- Inventario V1-V5: `audits/h9-limitacion-7-inventory-slice1.md`
- Hallazgo externo sobre v0.7.1: `audits/review-finding-v0.7.1-integration-gap.md`
- Tests: `tests/test_h9_limitacion_7_slice1.py`
- Implementación: `src/skillgraph/platform/storage.py` (`_atomic()`,
  `record_trace()`)
