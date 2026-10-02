# Runbook de Observabilidad — SkillGraph (T6 roadmap, WI-16)

> Documento vivo. Mantenido por el operador / agente de stewardship.
> Auditable: cualquier cambio debe aparecer en `CURRENT.md` (sección
> Reactivacion).

## 1. Alcance y principios

### 1.1 Que observamos

SkillGraph es **local-first**: la mayoria de los Runs se ejecutan en
una sola maquina, sin un sistema externo de observabilidad. La
observabilidad se organiza en tres niveles:

| Nivel | Mecanismo | Persistencia | Retencion |
|-------|-----------|--------------|-----------|
| **Eventos de negocio** | `runtime_events` table (Storage, SQLite, append-only) | Disco (WAL) | Indefinida (protegida por backup WI-15) |
| **Logs estructurados** | `print(...)` en CLI + journald opcional | stdout/journal | 30 dias (default journald) |
| **Metricas operacionales** | `runctl snapshot.state` + counters ad-hoc | derivan de eventos | calculo bajo demanda |

### 1.2 Que NO observamos todavia (P3 deferred)

- Trazas distribuidas (OpenTelemetry): irrelevante en local-first.
- Metricas con Prometheus: no aplica en local-first.
- Logs remotos (Datadog, Sentry, etc.): opt-in por el operador
  externo (configurar rsyslog/journald remote).
- Redaction automatica de tenant data en logs: implementado solo
  parcialmente (P3 deferred, ADR-0015 gap I/c).

### 1.3 Principios

1. **Append-only**: el EventLog nunca se borra ni reescribe
   (`UNIQUE(event_id)` previene duplicados; UPDATE/DELETE prohibidos
   por convencion; ver `runtime_events` schema).
2. **Inmutable**: cada evento lleva `tenant_id`, `project_id`,
   `run_id`, `node_execution_id`, `event_id` (UUID). El identificador
   `event_id` se usa para idempotencia.
3. **Local-first**: cero dependencias externas. Todo se persiste en
   SQLite local + stdout/journald del sistema.
4. **Auditable**: cualquier operacion que muta el EventLog es
   trazable a un `actor` (CLI user, agente LLM, automation).

## 2. Eventos de negocio

### 2.1 Tabla `runtime_events`

Schema (Storage, SQLite):

```sql
CREATE TABLE IF NOT EXISTS runtime_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,           -- RunCreated, NodeScheduled, etc.
    run_id TEXT,                         -- nullable
    resource_ref TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,             -- ISO 8601 UTC
    schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_run
    ON runtime_events(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS events_by_resource
    ON runtime_events(tenant_id, project_id, resource_ref);
```

### 2.2 Tipos de evento

Lista canonica (ver `src/skillgraph/runtime/runtime.py`):

| EventType | Cuando se emite |
|-----------|-----------------|
| `RunCreated` | Al arrancar un Run |
| `NodeScheduled` | Antes de ejecutar un nodo |
| `NodeCompleted` | Tras ejecutar un nodo (success) |
| `NodeFailed` | Tras un fallo (exception o `SkillGraphError`) |
| `RunCompleted` | Run termina en COMPLETED |
| `RunCancelled` | Run termina en CANCELLED |
| `RunFailed` | Run termina en FAILED |
| `PromotionProposed` | Submit de patch de expansion |
| `PromotionAuthorized` | Patch firmado |
| `PromotionApplied` | Patch aplicado al plan |

Anadir un valor nuevo es **cambio de contrato** del blueprint.
Requiere ADR.

### 2.3 Como consultar

```bash
# Timeline de eventos de un run (CSV-like: seq event_kind timestamp payload)
sg runs logs <project> <run_id>

# Filtrar por tipo via grep
sg runs logs <project> <run_id> | grep NodeFailed

# Filtrar y obtener payload completo via sqlite3 directo
sqlite3 ~/.local/share/skillgraph/tenants/<tenant>/projects/<proj>/project.sqlite \
  "SELECT payload_json FROM runtime_events
   WHERE run_id = ? AND event_kind = 'NodeFailed'"
```

> **Nota**: `sg runs logs` es el comando canonico para vision
> humana. Salida CSV-like, una linea por evento
> (`seq event_kind timestamp payload_summary`). Implementacion en
> `src/skillgraph/cli/runner.py:cmd_runs_logs`. Para queries
> avanzadas, usar `sqlite3` directo sobre el project.sqlite.

## 3. Logs estructurados (CLI)

### 3.1 Convencion de salida

Toda la CLI imprime por stdout con prefijos descriptivos:

- `Backup creado: ...`
- `Estado: COMPLETED`
- `Eventos emitidos: 12`
- `ERROR (<codigo>): <mensaje>` (stderr)

NO usamos `print` con formato libre en modulos de dominio: solo en
el CLI.

### 3.2 Codigos de exit

`EXIT_OK = 0`, `EXIT_VALIDATION = 12`, `EXIT_PARSE = 3`,
`EXIT_DB_MISSING = 5`, etc. Definidos en `src/skillgraph/cli/runner.py`
(constantes module-level). Permiten al operador ramificar en scripts
sin parsear stdout.

### 3.3 journald (Linux)

Si el operador ejecuta `sg` desde un servicio systemd, los logs van
a journald automaticamente. Para activar persistencia:

```ini
# /etc/systemd/system/sg-run.service
[Service]
ExecStart=/usr/bin/env sg run --adapter fake myproject /path/to/plan.md
StandardOutput=journal
StandardError=journal
```

Para consultar:

```bash
journalctl -u sg-run.service --since "1 hour ago"
```

### 3.4 NO redirigir logs a archivos rotados manualmente

journald se encarga de la rotacion. `journalctl --vacuum-time=30d`
limpia entradas antiguas.

## 4. Metricas operacionales

SkillGraph NO expone un endpoint de metricas. Las metricas se derivan
**bajo demanda** de los eventos:

```bash
# Cuantos Runs hubo en las ultimas 24h?
sqlite3 ~/.local/share/skillgraph/tenants/<tenant>/projects/<proj>/project.sqlite \
  "SELECT COUNT(*) FROM runtime_events
   WHERE event_kind = 'RunCreated'
     AND timestamp > datetime('now', '-1 day')"

# Distribucion de outcomes
sqlite3 ... "SELECT event_kind, COUNT(*) FROM runtime_events
   WHERE event_kind IN ('RunCompleted','RunCancelled','RunFailed')
     AND timestamp > datetime('now', '-7 day')
   GROUP BY event_kind"

# Latencia media por nodo (ms)
sqlite3 ... "SELECT
   json_extract(payload_json, '$.node_name') AS node,
   AVG(json_extract(payload_json, '$.duration_ms')) AS avg_ms
 FROM runtime_events
 WHERE event_kind = 'NodeCompleted'
   AND timestamp > datetime('now', '-7 day')
 GROUP BY node
 ORDER BY avg_ms DESC
 LIMIT 20"
```

> **Importante**: `payload_json` es JSON serializado. Usar
> `json_extract` para campos especificos. Los nombres exactos de
> campos dependen del `event_kind`; ver schema en `runtime.py`.

## 5. Sinks y enrutamiento

### 5.1 Por nivel

| Nivel | Destino default | Configurable |
|-------|----------------|--------------|
| Eventos de negocio | SQLite local | No (siempre local) |
| Logs CLI | stdout/stderr | Via systemd o redirection |
| Errores | stderr | Via systemd |

### 5.2 NO soportado todavia (P3 deferred)

- Sink a archivo con rotacion automatica (logrotate): usar
  journald + `journalctl --vacuum-time`.
- Sink a S3/syslog/HTTP: el operador externo configura
  `rsyslog`/`fluentd`/`vector`.
- Sink de eventos de negocio a Kafka: no aplica en local-first.

## 6. Retencion y backup

### 6.1 Retencion de eventos

**Sin limite duro automatico**. Los eventos viven hasta que el
operador borre el proyecto o purgue manualmente. El contrato del
runtime es append-only (sin UPDATE/DELETE en el codigo de
aplicacion); pero el operador puede ejecutar DELETE manual
sobre la tabla si lo necesita (es una operacion administrativa,
no de runtime).

```sql
-- Peligroso: borra TODOS los eventos de un proyecto.
-- Hacer backup ANTES (WI-15: sg backup create).
DELETE FROM runtime_events WHERE tenant_id = ? AND project_id = ?;
```

### 6.2 Backup antes de purgar

SIEMPRE ejecutar `sg backup create` antes de cualquier DELETE
masivo sobre `runtime_events`:

```bash
sg backup create                       # crea <data-root>/backups/skillgraph-<ts>.zip
sqlite3 ... "DELETE FROM runtime_events ..."  # purga
```

### 6.3 Retencion de backups

NO hay rotacion automatica de backups. El operador decide cuando
borrar:

```bash
# Borrar backups mas antiguos que 90 dias
find ~/.local/share/skillgraph/backups -name "skillgraph-*.zip" \
  -mtime +90 -delete
```

## 7. Alertas y SLOs

### 7.1 Indicadores a monitorizar manualmente

| Indicador | Query | Umbral sugerido |
|-----------|-------|-----------------|
| Runs fallidos / hora | `SELECT COUNT(*) FROM runtime_events WHERE event_kind='RunFailed' AND timestamp > datetime('now','-1 hour')` | <5% de Runs totales |
| Latencia p99 de nodos | percentil 99 de `duration_ms` en NodeCompleted | <30s (depende del adapter) |
| Adapter HTTP timeouts | `COUNT(*) WHERE event_kind='NodeFailed' AND json_extract(payload_json,'$.error') LIKE '%timeout%'` | 0 sostenidos |

### 7.2 Diagnostico de incidentes

1. **Run fallo**: `sg runs logs <project> <run_id> | grep NodeFailed`
   y leer el `payload_summary`. Anota `resource_ref` y el error.
2. **HTTP adapter no responde**: verificar env vars
   (`env | grep -E 'ANTHROPIC|OPENAI'`). Confirmar conectividad:
   `curl -fsS https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" -d '{}'`.
3. **Storage lock contention**: `sg runs logs <project> <run_id> | grep lock` y revisar `tests/test_locks.py` (cubierto en CI) y los ADRs relacionados.
4. **Catalog corrupto**: ejecutar `sg backup list` para localizar
   ultimo backup bueno. `sg backup restore <zip> <nuevo-data-root>`.

### 7.3 P3 deferred

- Dashboards pre-armados (Grafana, etc.).
- Alerting automatico (PagerDuty, etc.).
- Traces de ejecucion (OpenTelemetry).
- SLI/SLO formalizados con error budgets.

## 8. Compliance y auditoria

### 8.1 Retencion minima recomendada

| Tipo | Retencion | Justificacion |
|------|-----------|---------------|
| Eventos de Run | indefinida | reproducibilidad forense |
| Backups `.zip` | 90 dias | recuperacion ante disaster |
| Logs CLI | 30 dias | troubleshooting reciente |

### 8.2 Auditabilidad

Cada commit en el repo debe pasar por:

1. `uv run pytest` (suite 100%).
2. `uv run ruff check src tests` (0 errores).
3. Pre-commit hooks (formato + lint).
4. Audit dedicado si toca superficie nueva (ver `audits/`).

### 8.3 GDPR / datos sensibles

- **Handoff completo viaja al LLM** (gap menor ADR-0015 S8/I):
  para tenant data sensible, usar `--adapter fake` o
  redactar antes.
- **api_keys NUNCA en logs**: ADR-0015 S8/I cerrado por
  `field(repr=False)` + `__repr__` explicito en
  `HttpAgentAdapter` (D-47).
- **Backups `.zip` SIN cifrado**: si contienen tenant data
  sensible, cifrar externamente (gpg/age).

## 9. Referencias

- ADR-0015 (Threat model STRIDE): `docs/architecture/ADR-0015-threat-model-stride.md`.
- WI-15 (Backups CLI): `specs/wi-15-t5-backups-cli.md`.
- WI-14 (T3 S8 HTTP): `specs/wi-14-t3-threat-model-http.md`.
- Auditorias operacionales: `audits/`.
- RunController: `src/skillgraph/runtime/runcontroller.py`.
- Storage schema: `src/skillgraph/platform/storage.py`.
