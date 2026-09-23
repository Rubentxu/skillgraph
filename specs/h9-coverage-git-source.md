# H9-Coverage-4 — Cobertura `knowledge/git_source.py` 86% → ≥95%

## Objetivo

Cubrir las ramas no ejercitadas del modulo `src/skillgraph/knowledge/git_source.py`
(135 stmts, 42 branches, actualmente 86% cover / 11 brpart) sin modificar
codigo de produccion.

## Inventario de ramas no cubiertas (estado pre-slice)

Reportadas por `pytest --cov` con `tests/test_git_source.py` (8 tests):

| Lineas        | Branch / stmt                                       | Cobertura                                  |
|---------------|-----------------------------------------------------|--------------------------------------------|
| 78-79         | `_import_dulwich` ImportError                       | Cubierto por test_dulwich_unavailable      |
| 140           | `commit_obj.type_name != b"commit"`                 | **No cubierto** (ValueError)               |
| 159->162      | `source_id is None` (rama verdadera con default)    | **Inverso ya cubierto**                    |
| 200->206      | `self.pathspecs` truthy en `refresh()`              | **No cubierto** (rama verdadera)           |
| 237->241      | `until_commit is None` (rama verdadera)             | **No cubierto** (rama verdadera)           |
| 252-253       | `ch.new.path` cuando `ch.old.path` no existe        | **No cubierto**                            |
| 255           | `path is None: continue`                            | **No cubierto** (caso defensivo)           |
| 257-260       | status `added`/`deleted` (sha None)                 | **No cubierto**                            |
| 273->277      | `self.pathspecs` truthy en `detect_changes()`       | **No cubierto**                            |
| 325->exit     | `obj.type_name == b"tree"` recursión                | **No cubierto** (rama verdadera)           |
| 349-350       | `_matches_pathspec` literal (no glob)               | **No cubierto**                            |
| 357-358       | `_safe_capture_status` éxito                        | **No cubierto** (captura real)             |

## Plan de tests (8 nuevos, todas en `test_h9_coverage_git_source.py`)

1. **`from_commit` con sha que NO apunta a commit** — usar un SHA de un blob/tag,
   esperar `ValueError` con "sha no apunta a un commit".
2. **`refresh()` con pathspecs** — verificar que filtra blobs correctamente.
3. **`detect_changes` con until_commit=None** — usa HEAD como default.
4. **`detect_changes` con pathspecs** — filtra cambios correctamente.
5. **`detect_changes` cubre status `added` (file nuevo)** — segundo commit con
   un archivo nuevo, status debe ser `added`.
6. **`detect_changes` cubre status `deleted` (file eliminado)** — segundo commit
   sin un archivo, status debe ser `deleted`.
7. **`_matches_pathspec` literal (no glob)** — pathspec literal como prefijo
   (`'src'`) matchea `src/a.py` pero NO `src_old/x.py`.
8. **`_safe_capture_status` éxito (sin raise)** — repo limpio → dict con keys.

## Criterio de cierre

- `pytest --cov=skillgraph.knowledge.git_source` ≥ 95%.
- `scripts/ci.sh` 100% verde.
- `ruff check src tests` All checks passed.
- Sin modificacion de `src/skillgraph/knowledge/git_source.py`.

## Riesgo / valor

- **Riesgo**: bajo. Tests aditivos sin tocar codigo de produccion.
- **Valor**: modulo critico del H3 slice 3 (Git fingerprinting dulwich)
  pasa del 86% al ≥95%. Cubre todas las ramas de `detect_changes`
  (added/deleted/modified) y `refresh()` con pathspecs.
- **Sin decision material**: no introduce nuevos contratos ni cambia APIs.
