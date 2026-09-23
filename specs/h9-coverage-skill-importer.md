# H9-Coverage-3 — Cobertura `domain/skill_importer.py` 89% → ≥95%

## Objetivo

Cubrir las ramas no ejercitadas del modulo `src/skillgraph/domain/skill_importer.py`
(126 stmts, 32 branches, actualmente 89% cover / 7 brpart) sin modificar
codigo de produccion.

## Inventario de ramas no cubiertas (estado pre-slice)

Reportadas por `pytest --cov` con `tests/test_skill_importer.py` (8 tests):

| Lineas    | Branch / stmt                                   | Cobertura                                  |
|-----------|-------------------------------------------------|--------------------------------------------|
| 130       | suffix `.yaml`/`.yml` → `yaml_config`           | No cubierto                                |
| 134       | mimetype `text/*` → `plain_text`                | No cubierto                                |
| 136       | mimetype None → `unknown`                      | No cubierto                                |
| 160-161   | `_read_text_safely` returns None on UnicodeError| No cubierto                                |
| 189-191   | `root.is_file()` (analyze_skill sobre archivo)  | No cubierto                                |
| 239-246   | `kind == "unknown"` → ambiguous entry           | No cubierto                                |
| 252->205  | markdown decodeable pero `_read_text_safely` OK | **Inverso de la rama ya cubierta**         |
| 293       | `register_skill` con `locator_extra` no-None    | No cubierto                                |

## Plan de tests (8 nuevos, todas en `test_h9_coverage_skill_importer.py`)

1. **`yaml_config` por extension** — archivo `.yaml` produce kind=`yaml_config`.
2. **`plain_text` por mimetype text/*** — archivo `.txt` (mimetype `text/plain`)
   produce kind=`plain_text` cuando mimetypes no matchea por extension.
   Estrategia: usar `.txt` con mimetype detectable.
3. **`unknown` cuando mimetypes no detecta** — archivo `.xyz` (extension sin
   mimetype registrado) produce kind=`unknown`.
4. **`_read_text_safely` returns None on UnicodeError** — archivo con bytes
   no-UTF-8 produce `None` (cubrira la linea 160-161).
5. **`analyze_skill` sobre archivo unico** — un `.md` suelto (no directorio)
   activa la rama `root.is_file()`.
6. **`ambiguous entry` para kind=unknown** — archivo `.xyz` se reporta como
   ambiguous con razon `Extension desconocida`.
7. **`register_skill` con locator_extra** — pasa `locator_extra={"git_url": "x"}`
   al registrar y verifica que el locator resultante lo incluye.

## Criterio de cierre

- `pytest --cov=skillgraph.domain.skill_importer` ≥ 95%.
- `scripts/ci.sh` 100% verde (sin regresiones).
- `ruff check src tests` All checks passed.
- Sin modificacion de `src/skillgraph/domain/skill_importer.py` (refactor de
  cobertura, no de funcionalidad).

## Riesgo / valor

- **Riesgo**: bajo. Tests aditivos sin tocar codigo de produccion.
- **Valor**: modulo critico del H5 skill_import cierra del 89% al ≥95%.
  Cubre la heuristica de clasificacion (extension + mimetype fallback) y
  las ramas de `analyze_skill`/`register_skill` no testeadas.
- **Sin decision material**: no introduce nuevos contratos ni cambia APIs.
