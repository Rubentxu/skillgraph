# H9-LIMITACIÓN-7 — Slice 1: Inventario y caracterización

**Rama**: `h9-limitacion-7-storage-transactions`
**Estado**: RED (operaciones vulnerables caracterizadas; sin correcciones todavía)
**Pre-requisito**: docs/h9-plan-b-atomicity-characterization.md + audits/review-finding-v0.7.1-integration-gap.md

## Contexto técnico

`Storage` se conecta con `isolation_level=None`. En este modo:

- Cada `conn.execute()` ejecuta autocommit por sentencia.
- `with self._conn:` NO abre transacción implícita. Por tanto, varias
  sentencias dentro del `with` no se enrollan en una sola transacción:
  si una lanza después de que otra haya confirmado, la primera queda.
- `BEGIN` / `COMMIT` / `ROLLBACK` explícitos sí crean una transacción
  verdadera.

Verificación empírica previa (en la rama Plan B): `with self._conn:`
seguido de `self._conn.execute(INSERT)` + `raise RuntimeError` deja la
fila insertada en disco.

## Inventario de candidatos a vulnerabilidad

Criterio: una operación es **vulnerable a LIMITACIÓN-7** si ejecuta
más de una sentencia que DEBA ser atómica (semántica transaccional
expuesta al usuario) y no usa `BEGIN`/`COMMIT`/`ROLLBACK` explícitos.

### Grupo 1 — Vulnerables (multi-sentencia, sin transacción explícita)

| # | Función | Sentencias | Inconsistencia posible |
|---|---------|------------|------------------------|
| V1 | `_migrate()` | `executescript(SCHEMA)` + INSERT schema_version | El schema se aplica sin que `schema_version` quede registrado si la segunda sentencia falla. |
| V2 | `upsert_resource()` | SELECT spec_json + INSERT/UPDATE | Si UPDATE/INSERT falla tras SELECT, el caller observa inconsistencia (record sí existe, version no). El SELECT no causa daño, pero la "transacción" no existe. |
| V3 | `add_relation()` | SELECT existing + INSERT/UPDATE | Como V2 pero para relations. |
| V4 | `record_trace()` | INSERT trace + INSERT(s) trace_links | Si el INSERT de trace_links falla, el trace queda huérfano (sin sus enlaces). |
| V5 | `register_promotion()` | SELECT existing + INSERT/UPDATE | Como V2 pero para outbox de promoción. |

### Grupo 2 — NO vulnerables (1 sentencia, autocommit es suficiente)

| # | Función | Sentencias | Comentario |
|---|---------|------------|------------|
| N1 | `update_source_freshness()` | UPDATE | 1 stmt — autocommit OK. |
| N2 | `upsert_entity()` | INSERT OR REPLACE | 1 stmt — autocommit OK. |
| N3 | `record_evidence()` | INSERT OR IGNORE | 1 stmt — autocommit OK. |
| N4 | `record_claim()` | INSERT OR IGNORE | 1 stmt — autocommit OK. |
| N5 | `attach_evidence_to_claim()` | INSERT OR IGNORE | 1 stmt — autocommit OK. |
| N6 | `record_finding()` | INSERT OR REPLACE | 1 stmt — autocommit OK. |
| N7 | `append_trace_link()` | INSERT OR REPLACE | 1 stmt — autocommit OK. |
| N8 | `EventLog.append()` | INSERT | 1 stmt — autocommit OK. La atomicidad estado↔evento se hace en el runtime vía `*_atomically`, no aquí. |

### Grupo 3 — APIs no-atómicas existentes (legacy, usadas por RunController legacy pre-v0.7.2)

| # | Función | Sentencias | Comentario |
|---|---------|------------|------------|
| L1 | `recover_interrupted_node_executions()` | UPDATE (varias filas en 1 stmt SQL) | 1 stmt — autocommit OK. |
| L2 | `transition_run_state()` | UPDATE | 1 stmt — autocommit OK. |
| L3 | `start_node_execution()` (legacy) | INSERT | 1 stmt — autocommit OK. |
| L4 | `complete_node_execution()` (legacy) | UPDATE | 1 stmt — autocommit OK. |
| L5 | `mark_node_failed()` (legacy) | UPDATE | 1 stmt — autocommit OK. |
| L6 | `create_run()` | INSERT | 1 stmt — autocommit OK. |

Las 3 APIs `*_atomically` de v0.7.2 ya usan `BEGIN`/`COMMIT`/`ROLLBACK`
explícitos — no se tocan.

## Observación crítica

El uso de `with self._conn:` y `with self._tx():` que **NO** son
vulnerables (Grupo 2 + Grupo 3) es estilístico, no funcional. La
"transactional appearance" es engañosa pero el resultado en disco es
correcto (cada sentencia es atómica por autocommit).

Lo que SÍ vulnera el contrato es **no rollbackear cuando falla una
operación multi-stmt** (Grupo 1). Esas son las únicas candidatas a
corrección.

## Tests de caracterización RED (a desarrollar)

Cada test de caracterización demuestra el bug VIVENCIALMENTE antes de
corregirlo. Patrón:

1. Insertar datos previos en la BD.
2. Monkeypatch sobre `Storage._conn.cursor().execute()` (o
   `Storage._conn.execute`) para inyectar un fallo en la segunda
   sentencia de la operación.
3. Llamar a la operación vulnerable.
4. Verificar que la primera sentencia ESTÁ en disco (bug confirmado)
   Y que debería haberse rollbackeado (semántica transaccional
   violada).

Cobertura de tests:

- T15: `_migrate()` segunda sentencia falla → schema_version INSERT
       no aparece (correcto: migraciones idempotentes).
- T16: `upsert_resource()` INSERT falla → SELECT no causa daño
       (1ª fila ya existe pero no causa daño aquí).
- T17: `record_trace()` segundo INSERT (trace_link) falla → trace
       queda sin enlaces (huérfano).
- T18: `enqueue_promotion()` INSERT falla → SELECT no causa daño.

## Política para Slice 2

Para las V-numeradas:

- Si la operación tiene semántica multi-stmt que DEBE ser atómica
  (V1, V4): reemplazar `with self._tx()` por un helper que use
  BEGIN/COMMIT/ROLLBACK explícitos.

- Si la operación es un pattern SELECT-then-INSERT-or-IGNORE-style
  (V2, V3, V5): el SELECT es solo informativo. La inconsistencia es
  semántica: la fila ya existe con id, pero su version/spec no se
  actualizó. La transacción no aporta atomicidad sobre datos que YA
  están en disco. NO se considera vulnerable y se documenta como
  exclusión expresa.

**Decisión preliminar**:

- **V1** (`_migrate()`): migraciones idempotentes. La pérdida de
  `schema_version` ante fallo entre `executescript` y el INSERT no
  es crítica: la próxima invocación de `_migrate()` repite el
  `executescript` (los CREATE TABLE son IF NOT EXISTS). Se clasifica
  como **EXCLUIDA** — la operación ya es robusta por idempotencia.

- **V2, V3, V5**: patrón SELECT-info + INSERT/UPDATE-or-FAIL.
  Vulnerabilidad teórica: si la lectura es informativa y la escritura
  falla, no hay daño persistente. Se clasifican como
  **EXCLUIDAS POR IDEMPOTENCIA** — la operación ya da garantías
  equivalentes porque INSERT OR IGNORE / UNIQUE constraint detectan
  la duplicación y la fila previa permanece válida.

- **V4** (`record_trace()`): VULNERABLE REAL. INSERT trace + INSERT
  trace_links. Si el segundo falla, trace queda huérfano. **ES LA
  ÚNICA CANDIDATA A CORRECCIÓN** en este slice.

Verificación: los tests RED siguientes deben demostrar que solo V4
tiene un fallo observable que afecte a la consistencia del estado.
Las demás se validarán como excluidas expresamente.

## Forma del contrato (anticipo Slice 2)

Un único helper de Storage:

```python
@contextmanager
def _atomic(self) -> Iterator[sqlite3.Cursor]:
    """Ejecuta BEGIN explicito, yield cursor, COMMIT/ROLLBACK segun
    exito o excepcion. Es la UNICA via de transacciones reales en
    Storage. _tx() queda deprecated para V4.
    """
    cur = self._conn.cursor()
    try:
        self._conn.execute("BEGIN")
        cur.execute(...)  # (no es asi, solo para entender la idea)
        yield cur
        self._conn.execute("COMMIT")
    except Exception:
        self._conn.execute("ROLLBACK")
        raise
```

Migrar solo `record_trace()` y `_migrate()` (si se considera
vulnerable, ver arriba) al nuevo helper.

## Lo que queda fuera de este slice (no se toca)

- `with self._conn:` en APIs legacy (Grupo 3) — no vulnerables.
- `_tx()` en APIs single-stmt (Grupo 2) — no vulnerables.
- `EventLog.append()` — la atomicidad estado↔evento se hace vía
  `*_atomically`; aquí la transaccionalidad es superflua.
- **NO se toca `workflow_runs` ↔ eventos** (consigna: gate separado).

## Estado actual

- Tests RED: PENDIENTE (Slice 1.b).
- Migración: PENDIENTE (Slice 2).
- Regresión: PENDIENTE (Slice 3).
- Gate: PENDIENTE.

Esta es la fase de caracterización.
