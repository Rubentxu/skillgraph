# H9-Coverage-9: cobertura `skillgraph.knowledge.knowledge_controller` (93% -> 96%)

## Objetivo

Cubrir las ramas no ejercitadas de
`src/skillgraph/knowledge/knowledge_controller.py` para superar el umbral
de 95% exigido por el blueprint (AGENTS.md §6.3).

## Estado previo

Cobertura global del modulo: **93%** (115 stmts, 5 miss, 22 branches, 4 miss).

Ramas no cubiertas (smoke empirico + lectura del codigo):

| Linea     | Descripcion                                                                                                  | Estado              |
|-----------|--------------------------------------------------------------------------------------------------------------|---------------------|
| 74-75     | `make_evidence_id(source_id, content_repr)` - funcion pura determinista via UUIDv5                           | **alcanzable**     |
| 216       | `raise` no-FK en `record_evidence` (re-raise generico)                                                       | **alcanzable solo via mock de error no-FK**; no testeamos |
| 280-281   | `raise` no-FK/no-UnknownEntity en `record_claim` (re-raise generico)                                         | **alcanzable solo via mock de error no-FK**; no testeamos |
| 342->358  | `record_finding` con `finding_id=""` -> genera via `make_finding_id`                                          | **alcanzable**     |

## Tests añadidos

`tests/test_h9_coverage_knowledge_controller.py` (+5 tests):

| Test                                                  | Cubre        |
|-------------------------------------------------------|--------------|
| `test_make_evidence_id_is_deterministic`              | L74-75       |
| `test_make_evidence_id_changes_with_content`          | L74-75       |
| `test_make_finding_id_is_deterministic`               | L78-86 (idem) |
| `test_record_finding_generates_id_when_empty`         | L342-358     |
| `test_record_finding_uses_provided_id_when_set`       | L358 (else)  |

## Notas

- Las lineas **216** y **280-281** (re-raise generico no-FK en `record_evidence`
  / `record_claim`) son **branches defensivos** que requieren que Storage
  levante un error inesperado no-FK. Sin un mock/storage real que genere
  tales errores, no se pueden cubrir sin fragility. Se documentan como
  dead code operativo.
- `make_evidence_id` no se llamaba directamente desde ningun test previo;
  solo transitivamente via `record_evidence` cuando no se pasa ID.
- `make_finding_id` solo se invoca desde `record_finding` cuando
  `finding_id=""`. Eso requiere pasar un `Finding` con `FindingID("")`,
  lo cual ahora testeamos.

## Resultado

- **96%** de covertura del modulo (subida de 93% -> 96% con 5 tests).
  Reporte coverage.py: 115 stmts, 3 miss, 22 branches, 3 miss. Faltan
  L216 y L280-281 (defensivas re-raise no-FK).
- 602/602 tests verde (en 112s).
- ruff + format + ci.sh: OK.
- Sin modificacion de produccion.

## Commits

- `test(coverage): H9-Coverage-9 knowledge_controller.py (93%->96%)`
