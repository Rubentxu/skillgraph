# implementation-receipt — WI-45

Cycle: `p-74299cf88f51dab9/wi-45-uow-coverage`
WorkItem: `e01ff5ba-754c-4c27-8b60-a73056c9f6d3`
Path: B-direct
Date: 2026-09-27

## Qué se entregó

Dos commits atómicos:

| Commit | Alcance |
|---|---|
| `8ec0645` | `fix(ci)`: versiona `.pipeline.kts` y usa rutas absolutas en `sh()` |
| `3237a94` | `fix(platform)`: repara 7 delegaciones rotas de `SqliteUnitOfWork` |

## Criterios de aceptación (verificados, no supuestos)

| Criterio | Objetivo | Observado | Cómo se midió |
|---|---|---|---|
| Cobertura `platform/uow.py` | ≥ 90% | **100%** (94/94 stmts) | `pytest tests/test_wi45_uow_delegation.py tests/test_uow.py --cov=skillgraph.platform.uow` |
| Suite completa | 0 fallos | **1209 passed** | `uv run pytest` (pre-commit hook: 353s) |
| Regresiones | 0 | baseline 1172 → 1209 (**+37**) | diff de recuento |
| Lint | limpio | `All checks passed!` | `ruff check src tests` + `ruff format --check` |
| CI local | SUCCESS real | 5/5 `StageFinished success`, `RunFinished success`, 0 `StepFailed` | `pipelinek run` con DB y control-root limpios |
| Árbore | limpio | vacío | `git status --porcelain` |

## Defectos de producto encontrados y reparados

Raíz común: los 5 adapters de `SqliteUnitOfWork` se instancian en
`Storage.__init__` pero **ningún módulo de `src/` los invoca**. Son un
espejo muerto de la API de `Storage`, escrito en WI-33 R2 (único commit
`b42a2a8`) y nunca cableado. Por eso sus 7 delegaciones rotas eran
invisibles: un test de cobertura no detecta una línea que nunca se
ejecuta.

1. `SqlitePolicyAdapter.get_redaction_policy` → `Storage.get_redaction_policy`: **no existía**. El real es `get_policy`.
2. `SqlitePolicyAdapter.set_redaction_policy` → `Storage.set_redaction_policy`: **no existía**. El real es `upsert_policy`.
3. `complete_node_execution`: pasaba `tenant_id`, `project_id`, `context_hash`; la facade solo acepta `node_execution_id`/`outcome`/`result_json`. `TypeError` en el primer uso.
4. `mark_node_failed`: mismo defecto de keywords.
5. `create_run`: pasaba `run_id`; la facade genera siempre el id. Parámetro **insatisfacible**, eliminado para alinear con el puerto.
6. `record_event`: pasaba un `RuntimeEvent` entero donde la facade espera campos planos.
7. `list_promotions`: pasaba `limit=`, que la facade no acepta.

Además, 4 variantes atómicas reenviaban `**kwargs` de forma opaca con
nombres distintos a los del destino (`event` vs `event_completed` +
`event_evidence`). Ahora explícitas, y por tanto verificables.

## Guardas estructurales (falsificadas, no supuestas)

Dos guardas AST comprueban que cada `self._storage.<m>(...)` apunta a un
método que existe **y** pasa solo keywords que la firma real acepta.

Ambas se verificaron falsificables reintroduciendo el bug exacto que
previenen:

- Restaurar `get_redaction_policy` → falla el guard de existencia y el
  round-trip de política.
- Restaurar `tenant_id`/`project_id` en `complete_node_execution` →
  falla el guard de keywords con
  `keywords inexistentes ['project_id', 'tenant_id']; la facade acepta ['node_execution_id', 'outcome', 'result_json']`.

## Contratos reales verificados contra el código

| Supuesto | Realidad |
|---|---|
| `complete_node_execution` acepta `context_hash` | No lo acepta |
| `create_run` acepta `run_id` | Siempre genera el id |
| Estado terminal de nodo = `COMPLETED` | Es `SUCCEEDED` |
| `recover_interrupted` deja `FAILED` | Deja `READY` (reintentable) |
| `event_kind` de evidencia = `EvidenceRecorded` | Es `EvidenceProduced` |
| `PROMOTION_STATUSES` incluye `APPLIED` | No: `FAILED, IN_PROGRESS, PENDING, PUBLISHED` |

## Hallazgo sobre el gate de CI (commit `8ec0645`)

El gate de CI local canónico **mentía en vez de fallar**:

1. `$REPO_ROOT` no lo define `pipelinek` v0.39.0. Cada
   `sh("$REPO_ROOT/...")` se ejecutaba contra `/...`.
2. `.pipeline.kts` estaba en `.gitignore`, así que la definición del
   gate no vivía bajo control de versiones.
3. Con la DB cacheada, un `SUCCESS` se emite en 5.6s **sin ejecutar
   ningún stage**. Verde sin verificación.

Contrapruebas: con DB limpia y el script sin corregir, el mismo
pipeline reporta `RunFinished outcome=failure` en `discover-repo/sh-1`.

## Blockers abiertos (no resueltos, no esquivados)

- **B1**: `sddk release plan` exige `Cargo.toml` (lockstep de versión) en un proyecto Python. El binario SDDK contiene **0 referencias a `pyproject`**.
- **B2**: `sddk release apply` exige `permissions.yaml`, que el framework 1.171.2 no provee.

Ninguno se resuelve fabricando manifiestos, permisos, tags ni receipts.

## Trabajo restante

Ninguno dentro de WI-45. Queda abierto y **fuera de alcance**: decidir
si los 5 adapters deben cablearse en producción o retirarse por ser un
espejo muerto. Es una decisión de arquitectura que requiere su propio
WorkItem.
