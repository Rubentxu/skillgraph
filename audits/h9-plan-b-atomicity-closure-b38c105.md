# H9-Plan-B — Cierre de la grieta atómica estado↔evento

**Rama**: `h9-plan-b-atomicity`
**SHAs final**: 
- Implementación: `0946d39` — `feat(storage): atomic state+event writes via BEGIN/COMMIT/ROLLBACK (H9-Plan-B)`
- Style: `b38c105` — `style: ruff format storage + atomicity tests`

**Caracterización previa**: [`h9-plan-b-atomicity-characterization.md`](h9-plan-b-atomicity-characterization.md)

## Resultado

Tres grietas atómicas (B/C/D) del documento de caracterización cerradas.
Se cumple el contrato: una mutación de `node_executions` y su(s) evento(s)
en `runtime_events` se confirman o rollbackean como una sola unidad.

| Test                                          | Coverage                          |
|-----------------------------------------------|-----------------------------------|
| T7 `start_node_execution_atomically`          | RUNNING + NodeStarted             |
| T8 `complete_node_execution_atomically`       | SUCCEEDED + NodeCompleted + EvidenceProduced |
| T9 `mark_node_failed_atomically`              | FAILED + NodeFailed               |
| T10 idempotencia por `UNIQUE(event_id)`       | UAT-07                             |
| T11 introscpección: no se usa `EventLog`      | Mantiene el contrato de Storage  |

**Total**: 11/11 tests nuevos, 630/630 tests totales (619 originales + 11
nuevos), 16/16 UAT PASS, ruff clean, format clean.

## APIs nuevas en `Storage`

| Método | Firma |
|--------|-------|
| `start_node_execution_atomically` | `(event, node_execution_id, tenant_id, project_id, run_id, node_name, attempt, context_hash, handoff_json)` |
| `complete_node_execution_atomically` | `(event_completed, event_evidence, node_execution_id, outcome, result_json)` |
| `mark_node_failed_atomically` | `(event, node_execution_id, error)` |

Helper común: `_atomic_state_and_event(event, exec_sql)` — usa BEGIN +
`exec_sql` + INSERT evento + COMMIT, con ROLLBACK explícito si algo lanza.

## Decisión técnica: BEGIN/COMMIT/ROLLBACK explícitos

La caracterización indicaba que SQLite en `isolation_level=None` con
`with self._conn:` ejecuta autocommit por sentencia **y no rollbackea**
en body con excepción. Esto se confirmó empíricamente:

```python
with self._conn:
    self._conn.execute(INSERT_INTO_T)  # confirmado al instante
    raise RuntimeError("boom")
# rows de T siguen existiendo — ROLLBACK NO ocurrio
```

**Decisión**: para las 3 APIs atómicas se usa BEGIN/COMMIT/ROLLBACK
explícitos sobre `self._conn`. Esto se hace en `_atomic_state_and_event`
y como excepción inline en `complete_node_execution_atomically` (que
inserta 2 eventos y no encaja en el helper de 1 evento).

La grieta preexistente del `with self._conn:` en `_tx()` y el resto del
Storage **NO se cierra en Plan B**. Queda registrada como
LIMITACIÓN-7 (ver abajo).

## Limitaciones declaradas (no cerradas en Plan B)

- **LIMITACIÓN-7**: `Storage._tx()` y los demás APIs existentes
  (`upsert_resource`, `start_node_execution`, `complete_node_execution`,
  `mark_node_failed`, ...) siguen usando `with self._conn:` que NO rollbackea.
  Solo las 3 APIs nuevas atómicas usan BEGIN/COMMIT/ROLLBACK explícitos.
  Cerrar la grieta completa del Storage requiere cambiar muchas llamadas;
  esto sería un Plan A' o un H10 aparte.
- **Plan A (cobertura)** y **Plan C (concurrencia/backup/adaptador real)**
  siguen diferidos. Plan B solo cierra la grieta atómica.
- **Adaptador real no usado en UAT-15 (atomicidad)** — los tests atómicos
  usan `FakeAgentAdapter`. La atomicidad bajo el adaptador real aún no
  está validada; sin embargo, las APIs atómicas nuevas NO cambian el flujo
  del adaptador (siguen insertando eventos via `EventLog.append` para
  escenarios no-B/C/D).

## UAT evidence

SHA referenciado en `tests/uat-evidence/UAT-{08,09,...}.json`:
`b38c105108e08c48bb9bfa45299c6444dfa342d7`.

16/16 UAT PASS re-ejecutado post-Plan-B.

## Próximo paso (decisión operador)

Plan B cierra la grieta atómica — sin tocar Plan A ni Plan C. Las opciones
para continuar son:
1. Merge `h9-plan-b-atomicity` → `main` → tag `v0.7.1` (SEMVER derivado por
   nueva funcionalidad compatible hacia atrás).
2. Continuar con **LIMITACIÓN-7** antes de mergear: reescribir todas las
   APIs de Storage para usar transacciones explícitas (riesgo: regresiones
   si no se cubren todos los códigos de error, tests tenderían a duplicar
   esfuerzo).
3. Abrir Plan A (cobertura) sobre la base ya cerrada de Plan B.
4. Abrir Plan C (concurrencia/backup/adaptador real) sobre Plan B cerrado.

Recomiendo **1 + 3**: mergear Plan B cerrado (es un win), abrir Plan A
para subir cobertura de storage y dejarla en el ecosistema de gates
existentes.
