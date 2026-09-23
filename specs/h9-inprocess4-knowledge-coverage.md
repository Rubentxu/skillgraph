# H9-InProcess-4: cobertura in-process de `knowledge refresh/compile/trace`

## Contexto

InProcess-1/2/3 cubrieron in-process los comandos:
- InProcess-1 (H9-BSlice1): promotion list
- InProcess-2 (H9-InProcess-2): promotion submit/reconcile, pack load, expansion show
- InProcess-3 (H9-InProcess-3): knowledge stale/invalidate, brick register

Quedan **3 comandos sin cobertura in-process**, ya cubiertos por
subprocess E2E (`tests/test_cli_branches.py::TestKnowledge*`):
- `sg knowledge refresh` (cmd_knowledge_refresh, runner.py:332)
- `sg knowledge compile` (cmd_knowledge_compile, runner.py:348)
- `sg knowledge trace` (cmd_knowledge_trace, runner.py:389)

## Alcance

Replica el patrón de `test_h9_cli_inproc_knowledge_brick.py`:
- `cmd_*` se invoca con `argparse.Namespace(...)` directamente.
- `capsys` para capturar stdout/stderr.
- `_bootstrap` con `cmd_init` + `cmd_project_create` y tmp_path.

## Smoke empirico previo

Antes de escribir los tests, ejecutar `cmd_*` para conocer
contratos observables reales (return code, formato stdout,
excepciones que se propagan). Documentar asunciones defectuosas
que surjan.

## Criterios de aceptacion

- 8-10 tests focales cubriendo:
  - happy path (rc=0 + formato esperado de stdout).
  - error path (exit code != 0 + stderr/raise segun wrapper).
  - al menos 1 test por comando que verifique el contrato externo.
- Red de seguridad por introspeccion cuando aplique (e.g.,
  `cmd_*` no captura excepciones que deberia capturar segun spec).
- Todos verdes sin tocar codigo de produccion (refactor de
  cobertura, no de funcionalidad).

## Riesgos

- `cmd_knowledge_compile` captura `SkillGraphError` y devuelve
  `EXIT_DOMAIN`. Verificar que NO se propaga la excepcion.
- `cmd_knowledge_trace` no captura errores: si el run no
  existe, OutcomeTracer.from_run podria lanzar. Documentar.
- `cmd_knowledge_refresh` requiere `args.revision` (int). Si
  llega None podria lanzar. Verificar.

## Pendiente (no en este slice)

- H9-BSlice3 cierre completo (S1-S9) ya esta cerrado en
  commits `6f8337e..381f4f5` (2026-09-23). Grieta de
  no-atomicidad sigue abierta como punto de recuperacion
  futuro.
- ADR para cierre de la grieta: queda fuera de H9-InProcess-4.
