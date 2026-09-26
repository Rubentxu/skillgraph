# WI-16: T6 Observabilidad runbook

## Objetivo

Documentar la postura de observabilidad de SkillGraph: que se observa,
como, donde se persiste, y como recupera el operador ante incidentes.
Cumple el item `Observabilidad` del ROADMAP (sin detalle operativo previo).

## Decision previa (D-49)

- **3 niveles**: (a) Eventos de negocio (`runtime_events`, SQLite
  append-only); (b) Logs estructurados (CLI stdout/journald);
  (c) Metricas operacionales (derivadas bajo demanda de los eventos).
- **Local-first primero**: 0 dependencias externas. Prometheus/
  OpenTelemetry/Datadog son P3 deferred (no aplican en local-first).
- **Documento auditable**: claims concretos del runbook se verifican
  contra el codigo real (schema, exit codes, comandos).
- **Runbook = fuente de verdad operacional**, no docs marketing.

## Cambios

### `docs/observability-runbook.md` (nuevo, ~300 LoC, 9 secciones)

1. **Alcance y principios**: que observamos / que NO / 4 principios.
2. **Eventos de negocio**: schema `runtime_events` real
   (sequence/event_id/tenant_id/.../schema_version), tipos de evento,
   como consultar.
3. **Logs estructurados (CLI)**: convencion de salida, exit codes
   reales (OK=0, VALIDATION=12, PARSE=3, DB_MISSING=5), journald
   como sink recomendado.
4. **Metricas operacionales**: queries `sqlite3` directas (no Prometheus).
5. **Sinks y enrutamiento**: que hay y que NO.
6. **Retencion y backup**: eventos indefinidos, backups 90d default.
7. **Alertas y SLOs**: 3 indicadores sugeridos + 4 pasos de diagnostico.
8. **Compliance y auditoria**: retencion minima, GDPR para tenant data.
9. **Referencias**: links cruzados a ADRs y specs.

### Hallazgos durante la escritura (claims verificados)

- Schema `runtime_events` corregido para coincidir con el real
  (`event_kind` no `event_type`, `payload_json` no `payload`,
  `timestamp` no `occurred_at`).
- Exit codes corregidos: `EXIT_VALIDATION=12` (no 2), `EXIT_DB_MISSING=5`
  (no 4). Definidos en `runner.py` module-level, no en `exit_codes.py`.
- `sg runs logs` no soporta `--type`/`--json` flags (es CSV-like);
  queries avanzadas via `sqlite3` directo sobre project.sqlite.
- Referencia `audits/locks-*.md` no existe; apunta a
  `tests/test_locks.py` + ADRs.

## Compatibilidad

- Docs-only. 0 cambios en codigo. 0 cambios en tests.
- Backward-compatible 100%.

## Evidencia

- Archivo creado: `docs/observability-runbook.md` (300 LoC, 9 secciones).
- 0 tests necesarios (documento vivo, validado por revision humana).
- ruff: N/A (markdown).
- pytest: 1044/1044 PASS sin cambios.

## Pendiente tras WI-16

- **WI-17+ (deuda arquitectónica)**: H-01..H-10.
- Bump `0.14.6.dev0 → 0.14.7` con WI-12/13/14/15/16 acumulados
  (FEAT x3 + DOC x1 + CLI x1 + runbook x1).
- Push a origin (regla WI-01).
