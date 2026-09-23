# H9-Coverage-2 — Cobertura `domain/pack_loader.py` 78% → ≥95%

## Objetivo

Cubrir las ramas no ejercitadas del modulo `src/skillgraph/domain/pack_loader.py`
(68 stmts, 46 branches, actualmente 78% cover / 11 brpart) sin modificar
codigo de produccion.

## Inventario de ramas no cubiertas (estado pre-slice)

Reportadas por `pytest --cov` con `tests/test_h6_multiproposito.py` (12 tests):

| Lineas  | Branch / stmt                                | Cobertura                                  |
|---------|----------------------------------------------|--------------------------------------------|
| 61      | `value` no es lista cuando `list_of` activo  | No cubierto                                |
| 70      | `value` no es number cuando `number` activo  | No cubierto                                |
| 74      | `value` no es boolean cuando `boolean` activo| No cubierto                                |
| 82      | `list_of` con `value` no-lista               | No cubierto                                |
| 87->54  | `field_schema` no es `str`                   | Cubierto implicitamente (no testeado)      |
| 93-97   | `elif "refs" in field_schema`                | **No cubierto** (rama passthrough)         |
| 98-101  | `else`: esquema no soportado                 | **No cubierto** (ValidationError)          |
| 102-106 | `else` (no dict, no str): esquema invalido   | **No cubierto** (ValidationError)          |
| 140     | `types_decl` no es lista                    | **No cubierto** (ValidationError)          |
| 147     | `entry` no es dict                          | **No cubierto** (ValidationError)          |
| 153     | `kind` no es string o vacio                 | **No cubierto** (ValidationError)          |
| 158     | `schema` no es dict                         | **No cubierto** (ValidationError)          |

## Plan de tests (10 nuevos, todas en `test_h9_coverage_pack_loader.py`)

1. **Compilacion schema: `refs`** — campo con `refs: [OtroKind]` debe aceptarse
   como passthrough (NO verifica FK; ese es trabajo del motor).
2. **Compilacion schema: `list_of` con value no-lista** — `fields: {tags: {list_of: string}}`
   + `value="not a list"` debe lanzar ValidationError mencionando "esperaba lista".
3. **Compilacion schema: `number` mismatch** — `fields: {ratio: "number"}`
   + `value="1.5"` debe lanzar ValidationError mencionando "number".
4. **Compilacion schema: `boolean` mismatch** — `fields: {active: "boolean"}`
   + `value=1` debe lanzar ValidationError mencionando "boolean".
5. **Compilacion schema: dict no soportado** — `fields: {weird: {unknown: 1}}`
   debe lanzar ValidationError mencionando "no soportado".
6. **Compilacion schema: schema no es dict ni str** — `fields: {weird: 42}`
   debe lanzar ValidationError mencionando "invalido".
7. **`declare_types_from_pack`: `types` no es lista** — `pack.spec.types="nope"`
   debe lanzar ValidationError mencionando "spec.types debe ser lista".
8. **`declare_types_from_pack`: entry no es dict** — `pack.spec.types=["nope"]`
   debe lanzar ValidationError mencionando "esperaba mapping".
9. **`declare_types_from_pack`: kind vacio** — `pack.spec.types=[{}]`
   debe lanzar ValidationError mencionando "kind".
10. **`declare_types_from_pack`: schema no es dict** — `pack.spec.types=[{"kind": "X", "schema": "nope"}]`
    debe lanzar ValidationError mencionando "schema".

## Criterio de cierre

- `pytest --cov=skillgraph.domain.pack_loader` ≥ 95%.
- `scripts/ci.sh` 100% verde (sin regresiones).
- `ruff check src tests` All checks passed.
- Sin modificacion de `src/skillgraph/domain/pack_loader.py` (refactor de cobertura,
  no de funcionalidad).

## Riesgo / valor

- **Riesgo**: bajo. Tests aditivos sin tocar codigo de produccion.
- **Valor**: modulo critico del H6 multiprosito (UAT-12) pasa del 78% al ≥95%,
  cerrando ramas que validan el contrato del Domain Pack declarativo.
- **Sin decision material**: no introduce nuevos contratos ni cambia APIs.
