# H9-Coverage-1: cobertura de `graph_expansion.py` Either-style API

## Contexto

Tras el cierre de H9-BSlice3 y H9-InProcess-4, la cobertura
de `src/skillgraph/governance/graph_expansion.py` queda en
89% (285 stmts, 21 missed, 19 branch parts). El snapshot
del 2026-09-23 indica 86%; las cifras reales con pytest-cov
muestran 89%.

El modulo expone una API Either-style (`ExpansionResult`
con `is_ok`/`is_err`/`unwrap`/`unwrap_err`) que es
completamente testeable, pero varias ramas quedan sin
ejercitar.

## Ramas sin cubrir (de pytest --cov=term-missing)

| Linea | Codigo | Descripcion |
|---|---|---|
| 68 | `InvalidProposal.to_dict` | nunca se llama |
| 103 | `ExpansionResult.unwrap` en Err | raise path del Either |
| 108 | `ExpansionResult.unwrap_err` en Ok | raise path del Either |
| 164 | `Authorization.is_active` modo `policy_approved` | sin granted_by |
| 262 | `_require_problem` con string vacio | raise `InvalidExpansionError` |
| 267 | `_require_attachment` con point desconocido | raise |
| 288 | `propose` con `operations=()` | raise |
| 290 | `propose` con `author=""` | raise |
| 318 | `_find_capable` falso | any() sin match |
| 339 | `_has_cycle_via_new_transitions` edges de plan.transitions | edges.setdefault |
| 352 | `bfs_cycle` detecta nodo ya en seen | return True |
| 357 | `bfs_cycle` back-edge detectado | return True |
| 406 | `W1` warning: RemoveTransition sobre nodo activo | advertencia |
| 466 | `_cycle_source_nodes` edges de plan.transitions | setdefault |
| 517-520 | apply_expansion RemoveTransition filtra new_transitions | rama elif |
| 533-539 | `WorkflowPlan integrity check failed` exception path | return Err |

## Alcance

Tests focales que ejercitan cada una de las 16 ramas
listadas arriba. Sin tocar codigo de produccion (refactor
de cobertura, no de funcionalidad).

Patron: imports + dataclasses existentes, asserts sobre
excepciones y retornos. Red de seguridad no aplica aqui
porque las ramas ya existen y el modulo es estable.

## Criterios de aceptacion

- 12-16 tests focales (uno por rama).
- Cobertura `graph_expansion.py` >= 95% tras el slice.
- `scripts/ci.sh` verde sin tocar nada que no sea el archivo
  nuevo de tests.

## Riesgos

- Las ramas 533-539 (`WorkflowPlan integrity check failed`)
  son fragiles: dependen de que `__post_init__` valide
  algo. Si pytest no encuentra una entrada facil, el test
  puede ser fragil. En ese caso, se documenta y se acepta
  como no-cubierto.
- `_cycle_source_nodes` (linea 466) y `_has_cycle_via_new_transitions`
  comparten el setdefault de edges; cubrirlos todos puede
  requerir planes sinteticos con multiples nodos.

## Pendiente (fuera de scope)

- Refactor para migrar `storage._conn` en knowledge/ (14
  referencias en context_controller + knowledge_controller
  + knowledge_invalidator). Es decision material y refactor
  grande.
- H4-slice-4 pipeline gating de auto_signed via
  evaluation_result: deferido en H4-slice-3.
- Grieta de no-atomicidad Estado↔Eventos: ADR pendiente.
