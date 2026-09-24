# Release v0.7.3 — Cierre del caso V4 de LIMITACIÓN-7

**Tag**: `v0.7.3` → `987be068c7f2b6d17aa6c209489906f94a542568`
**SHA release**: `987be068` (apunta al commit `6a536ac` que es el
último commit con cambios de código en el camino del fix; el SHA
documental del tag puede diferir marginalmente tras sincronizaciones
de evidencia UAT, sin afectar el código ejecutado).

**Código examinado**: `6a536acfa0566ae785fa42a9d72f24e13e973877`
- Subject: *"test(limitacion-7): T19 cubre rollback path del _atomic REAL"*
- Merge commit: `6697c25` (rama `h9-limitacion-7-storage-transactions` → `main`)
- Commits de código entre `255596a` (padre del merge) y `6a536ac`:
  - `ff22eb8` feat(storage): V4 record_trace atomic via BEGIN/COMMIT/ROLLBACK
  - `e5a9454` refactor(storage): alinea _atomic con patron de *_atomically (Exception)
  - `4025a87` style: ruff clean (SIM105 try/except/pass -> contextlib.suppress; I001 imports)
  - `6a536ac` test(limitacion-7): T19 cubre rollback path del _atomic REAL

**Commits posteriores al tag** (no incluidos en v0.7.3):
- Documentales: `8c0614b`, `9587b02`, `d4d96f7`, `5c40fa4`, `e499443`,
  `3628de3`, `1e9ea64`, `244f3c0` (cierre procedural de la propia
  evidencia, sin cambios de código).
- **V6 fix** (separado del release v0.7.3):
  - `a6bb5ab` fix(storage): make record_claim evidence links atomic
  - Acompaña al test `tests/test_h9_limitacion_7_v6_record_claim.py`
    (T20) como prueba focal de la no-atomicidad previamente
    desapercibida en `Storage.record_claim()`.

**Fecha**: 2026-09-24
**Rama**: `h9-limitacion-7-storage-transactions` → merge en `main`

## Resumen ejecutivo

`v0.7.3` cierra **un solo caso** de la grieta transaccional
identificada como **LIMITACIÓN-7**: `Storage.record_trace()`. La
función ejecutaba 1 `INSERT` en `outcome_traces` seguido de N
`INSERT`s en `outcome_trace_links`, pero usaba el patrón heredado
`with self._tx()` que bajo `isolation_level=None` NO abre
transacción real — cada `execute()` es autocommit por sentencia.

Esto significaba que si una llamada a `record_trace()` recibía un
trace con 3 referencias de evidencia y la 3ª sentencia fallaba,
las 2 primeras ya estaban confirmadas: el `outcome_traces` row
quedaba huérfano sin sus enlaces en `outcome_trace_links`. El
estado era visible para lecturas posteriores y bloqueaba la
reconciliación operativa del trace.

`v0.7.3` introduce un nuevo helper `Storage._atomic()` que realiza
`BEGIN` / `COMMIT` / `ROLLBACK` explícitos sobre `_conn`
(alineado con el patrón ya usado por las APIs `*_atomically` de
v0.7.1) y migra `Storage.record_trace()` para usarlo. Si una
sentencia falla, la transacción rollbackea el conjunto completo
en una sola operación. La integración se acredita con tests de
fault injection (T17, T19).

## Cambios funcionales

### `Storage._atomic` (nuevo)

Helper de transacción explícita. Estructura:

```python
@contextmanager
def _atomic(self) -> Iterator[sqlite3.Cursor]:
    self._conn.execute("BEGIN")
    cur = self._conn.cursor()
    try:
        yield cur
        self._conn.execute("COMMIT")
    except BaseException:
        with suppress(sqlite3.Error):
            self._conn.execute("ROLLBACK")
        raise
```

- `BEGIN` / `COMMIT` explícitos (no usa `with self._conn:`, que es
  no-op bajo `isolation_level=None`).
- `ROLLBACK` envuelto en `contextlib.suppress` (patrón heredado
  de `*_atomically`): si el rollback también falla, no enmascara la
  excepción original.
- `except BaseException` (no `Exception`) para alinearse con el
  patrón de los APIs atómicos preexistentes.

### `Storage.record_trace` (modificado)

| Aspecto | Antes | Después |
|---|---|---|
| Context manager | `with self._tx()` | `with self._atomic()` |
| Docstring | Sin nota transaccional | Documenta garantía + ref V4 |
| Manejo de fallos | Sin rollback (autocommit) | ROLLBACK explícito al fallar |

Texto del cambio: 1 línea efectiva (`_tx` → `_atomic`) + 5 líneas
de docstring justificando el porqué.

### Tests nuevos

- **`tests/test_h9_limitacion_7_slice1.py`** (5 tests):
  - **T15** `_migrate()` es idempotente bajo fallo parcial.
  - **T16** `upsert_resource()` es idempotente sin transacción explícita.
  - **T17** `record_trace()` con 2 claims + 1 evidence: forzar fallo
    en la 4ª execute y verificar rollback real (0 filas en
    `outcome_traces` y `outcome_trace_links`).
  - **T18** `register_promotion()` es idempotente por `idempotency_key`.
  - **T19** Path real de rollback del `_atomic` (no override de los
    tests): invoca `_atomic` directamente con una excepción de
    aplicación y comprueba que el rollback funciona sobre el código
    real (`storage.py:387-393`).

Patrón de fault injection: `FaultyStorage` subclass con
`CountingCursor` envuelve `sqlite3.Cursor.execute` (que es
read-only a nivel C) y dispara `RuntimeError` en la N-ésima
sentencia.

## Compatibilidad

**Resultados observados en el clon del SHA `6a536ac`** (no en HEAD
del main, que ya incluye el fix V6 en `a6bb5ab`):

- **Pytest contra el código del tag**: `637 passed, 1 skipped` en
  122 s. (El skip es `tests/test_cli_uat.py:363`, preexistente en el
  proyecto — el blueprint no está versionado en el repo.)
- **`bash scripts/ci.sh` completo**: EXIT 1. Aborta en el **gate 1
  (ruff format --check)** sobre `tests/test_h9_limitacion_7_slice1.py`
  (el archivo que contiene T19, mezcla `with pytest.raises(...)` y
  `with s._atomic()...`). `ruff check src tests` reporta además 1
  error **SIM117** en el mismo T19 (nested `with`). Este estado es
  **heredado del propio árbol del tag**, no es regresión del fix V4
  y queda documentado como límite de la CI histórica de v0.7.3.
- **`python tests/uat_audit.py`** (modo lectura): `PASS=16 FAIL=0
  BLOCKED=0` (consulta los 16 JSON en `tests/uat-evidence/`).
- **Cobertura `storage.py`**: 96% (subió de 95% al añadir T19).
- **0 breaking changes**: APIs públicas no cambian. Las firmas de
  `record_trace` se mantienen, solo cambia el comportamiento
  interno de manejo de errores.

**Lo que el release v0.7.3 NO certifica para el run de CI**:

  El gate oficial `bash scripts/ci.sh` falla por formato/lint en
  T19. Esta clase de fallo es una característica del árbol del tag,
  no fue subsanada por este release y no debe atribuirse a una
  certificación retroactiva. Si se requiere CI verde en este código,
  el paso a realizar es un commit posterior al tag (`chore(...)`)
  que arregle formato y lint en `tests/test_h9_limitacion_7_slice1.py`,
  no una modificación del SHA del tag.

## Reproducción

```bash
git checkout v0.7.3
uv sync
mise exec -- uv run pytest
mise exec -- uv run python tests/uat_audit.py
```

Para regenerar la batería de evidencia capturada contra esta
revisión exacta, se necesita un `git worktree` en `6a536ac` (la
revisión previa a los 13 commits documentales posteriores al tag)
o equivalente. Esa evidencia no se incluye en este release — ver
la sección "Lo que v0.7.3 NO cierra" más abajo.

## Lo que `v0.7.3` sí cierra

- **LIMITACIÓN-7 V4**: `Storage.record_trace()` ya no deja traces
  huérfanos ante un fallo a mitad de la operación. La garantía
  atómica queda acreditada por 2 tests independientes (T17 con
  override y T19 con código real).

- **Inventario de LIMITACIÓN-7 (slice 1)**: las 4 funciones
  multi-statement restantes del Storage quedaron **explícitamente
  clasificadas** como fuera del alcance del fix de v0.7.3:
  - `V1 _migrate()`: EXCLUIDA por idempotencia (`IF NOT EXISTS`).
  - `V2 upsert_resource()`: EXCLUIDA por idempotencia (PK
    reemplaza fila).
  - `V3 add_relation()`: EXCLUIDA (SELECT-then-INSERT retorna sin
    escribir si ya existe).
  - `V5 register_promotion()`: EXCLUIDA (SELECT-then-INSERT raise
    antes del INSERT si ya existe).

## Lo que `v0.7.3` NO cierra (sigue abierto)

### LIMITACIÓN-7 V6 — `Storage.record_claim()` (corregida en commit posterior al tag)

`record_claim()` con `evidence_ids` no vacías ejecuta 1 INSERT en
`claims` + N INSERTs en `claim_evidence`. Con el mismo patrón
`with self._tx()`, una sentencia intermedia que falle deja el
claim parcialmente confirmado. La corrección de V6 está
versionada en el commit `a6bb5ab` (posterior al tag v0.7.3) y su
prueba focal T20 está en `tests/test_h9_limitacion_7_v6_record_claim.py`.

**V6 NO está incluida en v0.7.3.** Forma parte de una release
posterior, aún por versionar.

### `workflow_runs` ↔ `RunCreated` / `RunCompleted`

Las mutaciones de `workflow_runs` siguen usando APIs no-atómicas.
Esto está fuera del alcance de LIMITACIÓN-7 y pertenece al Plan C
(separación descrita en el roadmap).

### APIs legacy no-atómicas de Storage

`upsert_resource`, `start_node_execution`, `complete_node_execution`,
`mark_node_failed` (todas sin sufijo `_atomically`) siguen
implementadas con `with self._conn:` y NO rollbackean en
`isolation_level=None`. El runtime ya está migrado a las versiones
`*_atomically` (v0.7.2), pero cualquier llamada externa a esas
APIs sigue siendo responsabilidad del caller asegurar atomicidad
externa. Migrar las firmas legacy es un refactor mayor fuera del
alcance de v0.7.3.

## Evidencia

> **Nota de procedencia**: la siguiente tabla describe qué artefactos
> cubren el código de v0.7.3 y cuáles son evidencia complementaria
> generada fuera del tag.

| Artefacto | Procedencia | ¿Certifica v0.7.3? |
|---|---|---|
| `audits/release-v0.7.3-summary.md` | Este slice documental (commit posterior al tag) | Documenta el código del tag |
| `audits/cleanroom-evidence/skillgraph-v0.7.3-audit-bundle.tar.gz` | Pendiente | Generado contra `6a536ac` (código del tag) |
| `audits/cleanroom-evidence/ci-output-v0.7.3.txt` | Pendiente | Capturado contra `6a536ac` |
| `audits/cleanroom-evidence/uat-audit-v0.7.3.txt` | Pendiente | Capturado contra `6a536ac` |
| `tests/uat-evidence/UAT-08.json` | Modificado en working tree (no commiteado) | Anclado a `8c0614b`, **no a v0.7.3** — requiere contraste con log real de auditoría |
| `tests/uat-evidence/UAT-09.json` | Modificado en working tree (no commiteado) | Anclado a `8c0614b`, **no a v0.7.3** — requiere contraste con log real de auditoría |

**Regla de procedencia aplicada**: los UAT-08/09.json incluyen el
campo `revision` apuntando al SHA `8c0614b`, que es posterior al
tag v0.7.3. Hasta que se regenere evidencia contra el SHA del tag
y se añada al campo `revision`, **los UAT-08/09.json NO acreditan
v0.7.3**. Su uso como evidencia del release requiere trabajo de
publicación autorizado adicional.
