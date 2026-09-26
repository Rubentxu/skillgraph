# WI-30: deuda H-03 (knowledge.git_source.GitSource.detect_changes cc=18)

## Objetivo

Reducir cc de `detect_changes` (cc=18) en
`src/skillgraph/knowledge/git_source.py`. Era el segundo hotspot
publico que quedaba tras WI-29 (junto a `main` que se excluye por
D-64).

## Cambio

Extraidos 3 helpers:

- `_resolve_commit_pair(since_commit, until_commit)` (metodo
  privado en `GitSource`): carga los dos commits y resuelve
  `until_commit=None` -> HEAD. Aislamos la dependencia de dulwich.
- `_resolve_change_path(ch)` (module-level): extrae el path de
  un tree change. Helper puro.
- `_classify_change_status(old_sha, new_sha)` (module-level):
  determina status (added/deleted/modified). Helper puro.

`detect_changes` queda como composicion declarativa (cc=8):
load commits -> for tree_changes -> build ChangedFile.

## Compatibilidad

- 100% backward-compat: mismas ChangedFile, mismo orden, mismos
  paths, mismos SHAs.
- Path resolution equivalente (old.path preferred, fallback new.path).
- Status classification equivalente (mismas tres ramas).
- 21/21 tests git/knowledge PASS, 1048/1048 suite.

## Decision previa (D-68)

- **D-68**: Helpers puros de tree-walking en `git_source` se
  extraen a module-level (no metodos) porque no necesitan `self`
  y eso facilita testearlos en aislamiento y mantenerlos
  congelados a cambios en `GitSource`.

## Evidencia

- `detect_changes` cc: 18 -> 8 (-56%).
- `_resolve_change_path` y `_classify_change_status`: helpers puros.
- 1048/1048 PASS en suite completa (176.30s).
- ruff: All checks passed.
- Tras este WI, **hotspots publicos cc>=15 restantes en `src/`**:
  solo `main()` cc=50 (excluido por D-64).
