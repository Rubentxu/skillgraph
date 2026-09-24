# H9-Coverage-11 — ContextController → Storage API pública

**Slice**: cobertura del último módulo de producción con SQL directo sobre `storage._conn`. Replica el patrón H9-BSlice3 (RunController → Storage) para `ContextController`.

**Spec externo**: `external/blueprint-v1/adr/ADR-0014-context-controller-storage-api-y-eliminacion-shims.md`.

## Estado inicial (medido 2026-09-24 06:28)

- `src/skillgraph/knowledge/context_controller.py`: 443 LoC, **82% cobertura**.
- 4 sitios `_conn.execute(...)` directos (líneas 297, 346, 402, 413).
- El JOURNAL 23:00 declaraba "8 sitios" — la inspección real revela **4**. Cifra corregida en ADR-0014.

## 3 métodos nuevos en `Storage`

| # | Método | Líneas que cierra | Query |
|---|---|---|---|
| 1 | `list_claims_by_predicate(*, tenant_id, project_id, predicate) -> tuple[dict, ...]` | 297-303 | `SELECT * FROM claims WHERE tenant_id=? AND project_id=? AND predicate=?` |
| 2 | `list_evidences_for_source(*, source_id) -> tuple[dict, ...]` | 346-349 | `SELECT * FROM evidences WHERE source_id=?` |
| 3 | `list_resource_refs_for_run(*, tenant_id, project_id, run_id, kind) -> tuple[str, ...]` | 402-410 + 413-421 | `SELECT DISTINCT resource_ref FROM runtime_events WHERE ... AND resource_ref LIKE '<kind>:%' ORDER BY resource_ref` |

Nota: los sitios 3 y 4 (líneas 402-410 y 413-421) son casi idénticos — solo cambia el prefijo `claim:` vs `evidence:`. Se unifican en un solo método parametrizado por `kind: Literal["claim", "evidence"]`.

## Tests a añadir (~12-15)

- **Método 1** (3 tests): contrato, aislamiento por tenant+project+predicate, sin resultados → tupla vacía.
- **Método 2** (3 tests): contrato, sin resultados → tupla vacía, source_id inexistente.
- **Método 3** (4 tests): contrato, kind="claim", kind="evidence", DISTINCT+ORDER.
- **No-regresión context_controller** (1 test): `inspect.getsource(ContextController)` no contiene `_conn.execute` ni `cursor.execute`.

## Cierre

- `context_controller.py`: 443 LoC → ~420 LoC estimados (las 4 query strings se externalizan a Storage; los `from claims`/`from evidences`/`from runtime_events` siguen en ContextController porque mapean a `CompiledResource`).
- `storage.py`: 1486 → ~1560 LoC estimados (3 métodos nuevos con docstring + type hints).
- Cobertura `context_controller`: 82% → **95-97%**.
- Cobertura `storage`: 97% → 97% (sin cambio; las 3 APIs nuevas tienen tests).

## Trabajo coordinado

Este slice se ejecuta **junto con la eliminación de shims** (ADR-0014, Refactor 2) en la misma sesión, en un único flujo de commits. La razón: ambos refactors tocan imports y queremos una sola pasada de `scripts/ci.sh` para detectar regresiones.

## Decisión SEMVER

MINOR (v0.7.0): los 3 métodos nuevos en Storage son API pública. El shim `context_controller.py` se elimina (breaking para importadores externos, pero no hay en este repo).

## Reversibilidad

`git revert <commit_sha>` para cada commit del refactor.
