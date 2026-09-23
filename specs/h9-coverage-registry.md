# H9-Coverage-6 — Cobertura `resources/registry.py` 93% → ≥95%

## Objetivo

Cubrir las ramas no ejercitadas del modulo `src/skillgraph/resources/registry.py`
(72 stmts, 32 branches, actualmente 93% cover / 5 brpart) sin modificar
codigo de produccion.

## Inventario de ramas no cubiertas (estado pre-slice)

Reportadas por `pytest --cov` con la suite completa:

| Lineas      | Branch / stmt                                          | Cobertura                                  |
|-------------|--------------------------------------------------------|--------------------------------------------|
| 79          | `brick_type.api_version != brick.api_version`          | **Dead code por construccion** (ver nota) |
| 108->105    | outcomes[i]['name'] no-string                          | **No cubierto**                            |
| 122         | `_validate_action` transitions con claves no-string    | **No cubierto**                            |
| 130->exit   | `_validate_domain_pack` capabilities no-list           | **No cubierto** (rama verdadera)           |

**Nota sobre linea 79**: el doble check `brick_type.api_version != brick.api_version`
en `validate()` es **logica muerta por construccion**. El dict lookup en
linea 71-75 usa `brick.api_version` como parte de la key, asi que el
`BrickType` recuperado en linea 76 SIEMPRE tiene el mismo `api_version`
que el Brick. La rama nunca se ejecuta sin alterar el dict privado.
Se documenta como defensive branch no testeable (no se cubre con
un test que mute `_types` directamente — eso seria fragilidad).

## Plan de tests (3 nuevos, todas en `test_h9_coverage_registry.py`)

1. **`_validate_decision` con outcome name no-string** — outcomes con
   `{"name": 123}` → `ValidationError` "outcomes[i].name debe ser string".
2. **`_validate_action` con transition key no-string** — transitions con
   clave entera → `ValidationError` "claves deben ser string".
3. **`_validate_domain_pack` con capabilities no-lista** — `capabilities: "x"`
   → `ValidationError` "capabilities debe ser lista".

## Criterio de cierre

- `pytest --cov=skillgraph.resources.registry` ≥ 95%.
- `scripts/ci.sh` 100% verde.
- `ruff check src tests` All checks passed.
- Sin modificacion de `src/skillgraph/resources/registry.py`.

## Riesgo / valor

- **Riesgo**: bajo. Tests aditivos sin tocar codigo de produccion.
- **Valor**: modulo del registro de tipos (Etapa 0/S0, base del
  Domain Pack declarativo) pasa del 93% al ≥95%. Cubre las ramas
  defensivas de los validadores estructurales.
- **Sin decision material**: no introduce nuevos contratos.
