# WI-28: Auditoria de deuda arquitectonica (hito ceremonial)

## Objetivo

Caracterizar la deuda tecnica **pendiente** con metricas
reproducibles. Tras WI-23..WI-27 (5 refactors de complejidad
ciclomatica), necesitabamos visibilidad global de:

- Cuantos modulos >800 LoC quedan (god modules).
- Cuantas funciones publicas tienen cc>=20 (refactor obligatorio).
- Cuantas funciones privadas tienen cc>=20 (refactor opcional).
- Cuantas funciones son >80 LoC (legibilidad).
- Cuantas tienen anidamiento >=5 (composicion).

## Decision previa (D-61..D-66)

- **D-61**: Las auditorias de deuda son **scripts reproducibles**
  en `audits/` (no docs estaticos). Se pueden re-ejecutar despues
  de cada WI mayor para detectar cambios y progreso.
- **D-62**: Las metricas de cc usan el mismo algoritmo que los
  WI-21..WI-27 (1 + cada If/For/While/With + cada handler Try +
  cada value BoolOp + cada case Match). Esto permite comparar
  antes/despues con criterio homogeneo.
- **D-63**: Hotspots publicos cc>=20 son **refactor obligatorio**.
  Hotspots privados cc>=20 son refactor **opcional** (valor
  pedagogico o testabilidad) — no se factoriza por defecto.
- **D-64**: Funciones main() / dispatch_argparse / entry points
  NO se refactorizan surgicalmente aunque tengan cc alto; son
  cohesion points del modulo y se trataran via H-02 (god module).
- **D-65**: Smoke tests de auditoria NO cubren las metricas
  (eso es auditoria manual del reporte). Cubren:
  ejecutabilidad, formato del archivo, presencia de secciones
  esperadas, formato Markdown valido.
- **D-66**: Politica recomendada: **cero hotspots publicos cc>=20
  en cada release** o documentar la excepcion en CURRENT/CHANGELOG.

## Cambio

- `audits/audit_debt.py` (~215 LoC): script ejecutable idempotente.
  Lee `src/`, computa metricas via `ast`, escribe reporte en
  `audits/architecture-debt-YYYY-MM-DD.md`. CLI:
  `python audits/audit_debt.py`.
- `tests/test_audit_debt_smoke.py` (4 smoke tests, ejecutados
  via subprocess para no contaminar cobertura productiva).
- `audits/architecture-debt-2026-09-26.md`: reporte generado.
  46 modulos Python, 15985 LoC, 555 funciones.

## Compatibilidad

- Auditoria NO modifica codigo de `src/` ni tests existentes.
- Smoke tests suman 4 PASS / 0 FAIL a la suite sin regresiones.
- Ningun release existente se ve afectado.

## Hallazgos (estado al 2026-09-26 23:09)

- **God modules (LoC >800)**:
  1. `src/skillgraph/cli/runner.py` (2477) — H-02
  2. `src/skillgraph/platform/storage.py` (2407) — H-01
  3. `src/skillgraph/runtime/runcontroller.py` (1357)
  4. `src/skillgraph/governance/graph_expansion.py` (813)

- **Hotspots publicos cc>=20** (P0, refactor obligatorio):
  1. `main()` cc=43 — CLI entry point (NO refactor surgical, ver D-64).
  2. `cmd_run()` cc=22 — candidate a `_dispatch_run_subcommand(...)`.

- **Hotspots privados cc>=20** (P2, opcional):
  1. `_make_schema_validator()` cc=22 — pack_loader factory.

- **Hotspots cerrados en este ciclo WI-23..WI-27** (8 funciones):
  `_validate` 22→7, `validate` 24→4, `parse_markdown` 17→2,
  `take` 16→5, `record_validation_receipt` 14→5,
  `traverse_invalidations` 13→5, `HttpAgentAdapter.invoke` 12→7,
  `compile_handoff_from_scopes` 12→1.

- **Backlog priorizado del reporte**:
  - **P0**: `cmd_run` extraction + `_make_schema_validator` cleanup.
  - **P1**: H-01 / H-02 / runcontroller.py god modules (ADR previo).
  - **P2**: privadas cc>=20 caso por caso.
  - **P3**: funciones largas (>80 LoC) — ver tabla en reporte.

## Evidencia

- `python audits/audit_debt.py` -> escribe
  `audits/architecture-debt-2026-09-26.md` en <1s.
- `pytest tests/test_audit_debt_smoke.py -v` -> 4/4 PASS en 1.3s.
- Suite completa (sin cambios a src ni tests existentes): 1048/1048
  PASS (1044 anteriores + 4 nuevos).
- ruff: All checks passed.
