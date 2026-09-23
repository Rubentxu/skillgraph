# H9-Coverage-7 — Cobertura `resources/workflow.py` 93% → ≥95%

## Objetivo

Cubrir las ramas no ejercitadas del modulo `src/skillgraph/resources/workflow.py`
(105 stmts, 60 branches, actualmente 93% cover / 6 brpart) sin modificar
codigo de produccion.

## Inventario de ramas no cubiertas (estado pre-slice)

Reportadas por `pytest --cov` con la suite completa:

| Lineas    | Branch / stmt                                              | Cobertura                                  |
|-----------|------------------------------------------------------------|--------------------------------------------|
| 32        | `_declared_outcomes` con raw no-lista o no-strings          | **No cubierto** (ValidationError)          |
| 43        | `_declared_max_visits` con raw no-int o < 1                | **No cubierto** (ValidationError)          |
| 82        | `WorkflowNode.metadata` no es dict                         | **No cubierto** (ValidationError)          |
| 92        | `WorkflowNode` ActionNode con outcomes via metadata        | **No cubierto** (rama verdadera)           |
| 128       | `WorkflowPlan.initial` vacio                               | **No cubierto** (ValidationError)          |
| 133       | `WorkflowPlan.transition.source` no es nodo del plan       | **No cubierto** (ValidationError)          |

## Plan de tests (6 nuevos, todas en `test_h9_coverage_workflow.py`)

1. **`_declared_outcomes` con raw no-lista** — `metadata.outcomes = "ok"`
   en ActionNode → `ValidationError`.
2. **`_declared_max_visits` con raw negativo** — `metadata.max_visits = -1`
   en cualquier nodo → `ValidationError`.
3. **`WorkflowNode.__post_init__` metadata no-dict** — pasar `metadata="x"`
   → `ValidationError`.
4. **`WorkflowNode` ActionNode con outcomes via metadata** — crear
   ActionNode con `metadata.outcomes = ["ok"]` → outcomes se respetan
   (degraded mode).
5. **`WorkflowPlan.initial` vacio** — `WorkflowPlan(initial="")` →
   `ValidationError`.
6. **`WorkflowPlan.transition` con source fantasma** — transición cuyo
   source no está en los nodos → `ValidationError`.

## Criterio de cierre

- `pytest --cov=skillgraph.resources.workflow` ≥ 95%.
- `scripts/ci.sh` 100% verde.
- `ruff check src tests` All checks passed.
- Sin modificacion de `src/skillgraph/resources/workflow.py`.

## Riesgo / valor

- **Riesgo**: bajo. Tests aditivos sin tocar codigo de produccion.
- **Valor**: modulo del WorkflowPlan (Etapa 0/S0, base del sistema
  de ejecucion declarativo) pasa del 93% al ≥95%. Cubre las ramas
  defensivas de `__post_init__` y los validadores de `_declared_*`.
- **Sin decision material**: no introduce nuevos contratos.
