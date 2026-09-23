# H9-Coverage-10: cobertura `skillgraph.resources.bricks` (91% -> 100%)

## Objetivo

Cubrir las lineas no ejercitadas de `src/skillgraph/resources/bricks.py`
para superar el umbral de 95% exigido por el blueprint (AGENTS.md §6.3).

## Estado previo

Cobertura global del modulo: **91%** (22 stmts, 2 miss).

Lineas no cubiertas:

| Linea | Descripcion                                                   |
|-------|---------------------------------------------------------------|
| 29    | `return {` cuerpo de `ResourceIdentity.as_dict()`             |
| 58    | `return self.identity.as_dict()` cuerpo de `Brick.uid_components` |

## Causa

`ResourceIdentity.as_dict()` no se invoca directamente desde ningun test
existente (solo transitivamente via `Brick.uid_components` -> delega ->
pero coverage reporta `as_dict` linea 29 como miss, no la linea 58).
La linea 58 queda miss porque `Brick.uid_components` solo se invoca en
pocos sitios y coverage no la cuenta consistentemente.

## Tests añadidos

`tests/test_h9_coverage_bricks.py` (+2 tests):

| Test                                                  | Cubre        |
|-------------------------------------------------------|--------------|
| `test_resource_identity_as_dict_has_all_fields`       | L29          |
| `test_brick_uid_components_delegates_to_identity`     | L58          |

## Resultado

- **100%** de covertura del modulo (subida de 91% -> 100% con 2 tests).
  Reporte coverage.py: 22 stmts, 0 miss.
- 604/604 tests verde (en 107s).
- ruff + format + ci.sh: OK.
- Sin modificacion de produccion.

## Commits

- `test(coverage): H9-Coverage-10 bricks.py (91%->100%)`
