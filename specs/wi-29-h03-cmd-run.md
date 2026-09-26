# WI-29: deuda H-03 (cli.runner.cmd_run cc=22)

## Objetivo

Reducir cc de `cmd_run` (cc=22) en `src/skillgraph/cli/runner.py`.
Era el **unico hotspot publico** del catalogo P0 del WI-28 (junto
con `main` cc=43, que NO se refactoriza surgicalmente segun D-64).

## Cambio

Extraidos 3 helpers privados:

- `_resolve_run_inputs(args)` (cc=8): valida inputs (resolver lookup,
  plan file exist, parseo, db_path exist) y construye `RunController`
  + selecciona Run (resume-or-start via `_find_active_run_id`).
  - Patron de error: si falla, devuelve `(None, None, ..., exit_code)`
    y el caller propaga el exit code.
  - Lazy imports de `agents_root` y `RunBudget/RunController` dentro
    del cuerpo (evita ciclos + lazy-cost en arranque de CLI).
  - TYPE_CHECKING imports arriba para no romper F821/UP037.
- `_reconcile_until_terminal(ctl, *, tenant_id, project_id, run_id,
  max_iterations)` (cc=5): bucle de reconciliacion. Termina en
  estado terminal o cuando `iterations >= max_iterations` (con
  WARN explicito al stderr para que el usuario sepa que el
  limite se respeto).
- `_resolve_fixtures_root(args)`: helper auxiliar para el print de
  resumen. Idempotente con mkdir(parents=True, exist_ok=True).

`cmd_run` queda como orquestador puro (cc=5): una llamada a
`_resolve_run_inputs`, gestion del early-exit, bucle via
`_reconcile_until_terminal`, prints de resumen.

## Compatibilidad

- 100% backward-compatible: mismas mensajes en stderr, mismos
  exit codes (EXIT_PLAN_NOT_FOUND, EXIT_PARSE, EXIT_DB_MISSING,
  EXIT_OK, EXIT_RUN_FAILED, EXIT_RUN_INCOMPLETE).
- Resumen visual igual: misma secuencia de prints (`Run:`,
  `Estado:`, `Nodos ejecutados:`, etc.).
- WARN max-iterations preservado verbatim.
- 8/8 tests `test_cli_run_uat.py` + 125 tests CLI/runner PASS.

## Decision previa (D-67)

- **D-67**: Orquestadores CLI cmd_X con logica mixta (validacion
  + construccion + bucle + reports) se extraen a `_resolve_X_inputs`
  + `_run_X_until_terminal` + `_resolve_X_summary`. Patron
  `B + T`: el caller (cmd_X) queda como 3-line composition.

## Evidencia

- `cmd_run` cc: 22 -> 5 (-77%).
- `_resolve_run_inputs` cc=8 (89 LoC), `_reconcile_until_terminal` cc=5.
- 1048/1048 PASS en suite completa (182.31s).
- ruff: All checks passed.
- Tras este WI, **hotspots publicos cc>=20 restantes en `src/`**:
  solo `main()` cc=43 (excluido por D-64 — CLI entry point / H-02).
