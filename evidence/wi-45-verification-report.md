# verification-report — WI-45

Cycle: `p-74299cf88f51dab9/wi-45-uow-coverage`
WorkItem: `e01ff5ba-754c-4c27-8b60-a73056c9f6d3`
Phase: verify · Path: B-direct
Date: 2026-09-27

## Veredicto

**PASS.** Los criterios de aceptación de WI-45 se verifican de forma
observable, no por inspección del código.

## `tests-pass`

| Comprobación | Resultado | Evidencia reproducible |
|---|---|---|
| Cobertura `platform/uow.py` | **100%** (94/94 stmts, 0 miss) | `pytest tests/test_wi45_uow_delegation.py tests/test_uow.py -q --cov=skillgraph.platform.uow --cov-report=term` → 43 passed |
| Suite completa | **1209 passed**, 0 fallos | `uv run pytest` — ejecutado dos veces: 752s antes del commit, 353s por el pre-commit hook |
| Regresiones | **0** | baseline 1172 → 1209 (+37 tests nuevos) |
| Tests nuevos | **37 passed** | `tests/test_wi45_uow_delegation.py`, sin mocks, contra `Storage` real en `tmp_path` |

## `policy-compliant`

| Comprobación | Resultado | Evidencia reproducible |
|---|---|---|
| `ruff check src tests` | `All checks passed!` (exit 0) | digest `sha256:f0d0b1081d9d3ebb26c4c93543053ecdc0a58998f22c071dc4ddb26021b57645` |
| `ruff format --check src tests` | 167 files already formatted | ejecutado en ambos pre-commit hooks |
| CI local canónico | 5/5 `StageFinished success` | `pipelinek run` con DB y control-root **limpios** (no cacheado) |
| Árbol de trabajo | limpio | `git status --porcelain` vacío |

## Falsificación de las guardas (no basta con que pasen)

Una guarda que nunca falla no prueba nada. Ambas se verificaron
reintroduciendo el defecto exacto que previenen:

| Guarda | Defecto reintroducido | Resultado |
|---|---|---|
| Existencia de método | `get_policy` → `get_redaction_policy` | **FAIL** (guard de existencia + round-trip de política) |
| Compatibilidad de keywords | `tenant_id`/`project_id` en `complete_node_execution` | **FAIL** con `keywords inexistentes ['project_id', 'tenant_id']; la facade acepta ['node_execution_id', 'outcome', 'result_json']` |

Tras restaurar, ambas vuelven a **PASS**.

## Verificación de que el CI gate no miente

Tres contrapruebas sobre `pipelinek`:

1. **Caché**: con la DB cacheada, `SUCCESS` en 5.6s **sin ejecutar un solo stage**.
2. **Rutas rotas**: con DB limpia y el script sin corregir, `RunFinished outcome=failure` en `discover-repo/sh-1` (`ls: no se puede acceder a '/pyproject.toml'`).
3. **Script correcto**: con DB limpia y rutas absolutas, 5/5 stages `success` y `RunFinished success`, con la salida de pytest y ruff capturadas en el journal.

## Riesgos residuales

- Los 5 adapters siguen sin cablearse en producción: el trabajo es
  correcto pero **no está en el camino de ejecución**. Cubrirlo era el
  objetivo de WI-45; cablearlo es una decisión de arquitectura aparte.
- Los 4 `**kwargs` opacos de otras partes del código no se han
  auditado: la auditoría se limitó a los 5 adapters de `uow.py`.

## Blockers (no resueltos, no esquivados)

- **B1**: `sddk release plan` exige `Cargo.toml` (lockstep de versión) en un proyecto Python; el binario SDDK tiene 0 referencias a `pyproject`.
- **B2**: `sddk release apply` exige `permissions.yaml`, que el framework 1.171.2 no provee.

Ninguno se resuelve fabricando manifiestos, permisos, tags ni receipts.
