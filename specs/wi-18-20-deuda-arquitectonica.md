# WI-18..WI-20: Deuda arquitectonica (H-10, H-03, H-05)

## Objetivo

Continuar cerrando la deuda arquitectonica documentada en el
backlog pendiente (post-WI-12..WI-17). Tres items pequenos pero
de alto valor:

- **WI-18 H-10**: docstring de `locks.py` prometia "msvcrt lazy
  import" pero el codigo tiene `import fcntl` top-level.
  Refactor: docstring honesto que refleja la realidad.
- **WI-19 H-03**: `_make_schema_validator._validate` tenia cc=22.
  Refactor: extraer `_check_required`, `_check_primitive`,
  `_check_list`. `_validate` queda en cc=7.
- **WI-20 H-05**: `_DummyStorage` era un anti-patron (clase con
  `__getattr__` que lanza `FileNotFoundError` cuando el proyecto
  no existe). Bug real: los callers no capturaban la excepcion
  y mostraban traceback feo. Refactor: raise directo en
  `_open_known_project` + handler global en `main()`.

## Decision previa (D-51)

- **D-51** H-05 fix: el `_DummyStorage` existia para "evitar imports
  fragiles" (segun docstring) pero introducia un bug de UX. El fix
  es raise directo (mas simple, mas testeable, mejor mensaje).

## Cambios

### `src/skillgraph/runtime/locks.py` (WI-18)

- Docstring honesto: **Windows NO soportado**, el modulo falla
  con `ImportError` si se importa en Windows. Tests usan
  `@pytest.mark.skipif(os.name == "nt", ...)`. Esto refleja la
  realidad (proyecto solo se testea en Linux/macOS).

### `src/skillgraph/domain/pack_loader.py` (WI-19)

- Extraidos `_check_required`, `_check_primitive`, `_check_list`
  del closure `_validate`.
- `_validate` queda con cc=7 (era cc=22).
- 0 cambios en API publica. Tests pasan (10/10).

### `src/skillgraph/cli/runner.py` (WI-20)

- `_open_known_project`: raise `FileNotFoundError` con mensaje
  legible cuando el proyecto no existe (incluye nombre del
  proyecto, tenant, data_root, y sugerencia `sg project create`).
- `main()`: handler `except FileNotFoundError` global que imprime
  mensaje y retorna `EXIT_PROJECT_NOT_FOUND = 4`.
- Clase `_DummyStorage` eliminada (anti-patron).
- Imports locales redundantes en `cmd_knowledge_compile`
  (ya cerrado en WI-17).

### `tests/test_h9_cli_inproc_knowledge_refresh_compile_trace.py`

- 2 tests actualizados: ya no esperan el mensaje generico de
  `_DummyStorage`, ahora verifican el mensaje legible del nuevo
  raise.

## Compatibilidad

- 100% backward-compatible en API publica.
- Cambio de comportamiento en CLI: cuando el proyecto no existe,
  el usuario ahora ve un mensaje legible (`ERROR: proyecto
  'missing' no encontrado en el catalog ...`) en lugar de un
  traceback. Exit code 4 (EXIT_PROJECT_NOT_FOUND) consistente.

## Evidencia

- `uv run pytest` (suite completa) -> **1044/1044 PASS** en 188.77s.
- `uv run ruff check src tests` -> All checks passed.
- cc de `_validate` en pack_loader: 22 -> 7 (~68% reduccion).
- 0 `_DummyStorage` en el codigo de produccion.

## Pendiente

- **WI-21+ (deuda restante)**: H-01 Storage god-class (2407 LoC),
  H-02 CLI god-module (2332 LoC), H-03 funciones con cc 11..15
  restantes.
- Bump `0.14.7.dev0 -> 0.14.8` cuando haya suficientes feats.
- Push a origin (regla WI-01, ahora ~38 commits ahead).
