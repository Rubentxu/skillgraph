# H9-Coverage-5 — Cobertura `resources/catalog.py` 88% → ≥95%

## Objetivo

Cubrir las ramas no ejercitadas del modulo `src/skillgraph/resources/catalog.py`
(46 stmts, 6 branches, actualmente 88% cover / 2 brpart) sin modificar
codigo de produccion.

## Inventario de ramas no cubiertas (estado pre-slice)

Reportadas por `pytest --cov` con `tests/test_cli_uat.py` (10 tests):

| Lineas    | Branch / stmt                                          | Cobertura                                  |
|-----------|--------------------------------------------------------|--------------------------------------------|
| 76        | `register_project` con duplicado -> IdentityConflict    | **No cubierto**                            |
| 96-100    | `list_projects` con resultados                         | **No cubierto** (rama verdadera)           |
| 105       | `open_catalog` con path NO `.sqlite` -> ValidationError| **No cubierto**                            |

## Plan de tests (4 nuevos, todas en `test_h9_coverage_catalog.py`)

1. **`register_project` duplicado** — `register_project` con el mismo
   `(tenant_id, name)` dos veces -> `IdentityConflictError`.
2. **`list_projects` con proyectos** — registrar 2 proyectos, listarlos,
   verificar orden por nombre y contenido.
3. **`list_projects` tenant vacio** — `list_projects` con un tenant
   sin proyectos devuelve `[]` (rama verdadera con 0 rows).
4. **`open_catalog` path no `.sqlite`** — path `catalog.db` (sin extension
   correcta) -> `ValidationError`.

## Criterio de cierre

- `pytest --cov=skillgraph.resources.catalog` ≥ 95%.
- `scripts/ci.sh` 100% verde (sin regresiones).
- `ruff check src tests` All checks passed.
- Sin modificacion de `src/skillgraph/resources/catalog.py` (refactor de
  cobertura, no de funcionalidad).

## Riesgo / valor

- **Riesgo**: bajo. Tests aditivos sin tocar codigo de produccion.
- **Valor**: modulo del catalogo (Etapa 1, persistencia de identidad
  tenant/project) pasa del 88% al ≥95%. Cubre la validacion de path
  en `open_catalog` (rechazo temprano de paths no-sqlite) y el
  branch de duplicados en `register_project`.
- **Sin decision material**: no introduce nuevos contratos ni cambia APIs.
