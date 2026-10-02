# ADR-0015 — Modelo de amenaza (STRIDE) y trazabilidad defensiva

Estado: aceptado (sesion 2026-09-25, ciclo STEWARDSHIP-T3-001).

## Contexto

SkillGraph es una plataforma local-first que ejecuta agentes sobre
runs persistidos en SQLite. La iniciativa `g-skillgraph-bootstrap`
ha cerrado 8 Etapas (0..6 + 5/8 Trabajos de Etapa 7) con 830 tests
verdes y 17 releases. El roadmap blueprint-v1 lista entre los Trabajos
pendientes de Etapa 7:

- **T3 Threat model**: "Sin threat model formal. No hay STRIDE/abuse-cases
  documentados." (de `audits/h9-addendum-2026-09-25.md`, seccion E2-Seguridad).

Aun con redaccion, locks, multi-tenancy y APIs atomicas (H9-Plan-B)
implementados, el sistema carece de un **modelo explicito** de:

1. Que superficies estan expuestas y a quien.
2. Que propiedades defensivas (C/I/A) estan garantizadas por que
   mecanismo.
3. Donde estan los gaps testeables y los que requieren mitigaciones
   externas.

Sin este modelo, una auditoria externa o un reviewer no puede
diferenciar "lo que esta cubierto" de "lo que no se ha considerado".

## Decision

Adoptar **STRIDE** como marco de analisis, con los siguientes **perfiles
de atacante asumidos** (el modelo es defendible para una plataforma
local-first multi-tenant; queda registrado para revision del operador):

### Perfiles de atacante asumidos

- **A1 — Atacante externo sin credenciales**: no tiene acceso al
  filesystem local ni al binario. Modelo: no es threat model relevante
  para una herramienta CLI local (no expone puertos); queda fuera del
  alcance. **Asuncion**: el operador despliega en un host con
  filesystem permissions correctas.

- **A2 — Atacante local no autenticado (tenant_attacker)**: tiene
  acceso al binario y a `~/.local/share/skillgraph/` (path configurable).
  Puede ejecutar `sg` CLI y leer SQLite files. **No** tiene credenciales
  de ningun tenant. **Objetivos realistas**: SQL injection via CLI args,
  bypass de tenant_id en queries, escape de sandbox del Adapter.

- **A3 — Atacante autenticado tenant_user (cross-tenant)**: tiene
  credenciales validas para tenant T1 (via variable de entorno o
  parametro CLI). Intenta leer/escribir datos de tenant T2 adyacente.
  **Objetivos**: bypass de la clausula `WHERE tenant_id = ?`.

- **A4 — Atacante local con shell (operator_untrusted)**: tiene
  shell en el host y acceso al codigo fuente. Puede leer secretos
  del entorno, modificar SQLite files, etc. **No** es threat model
  defensible por software (el operador con shell es equivalente a
  root). **Asuncion**: este perfil queda fuera del alcance; las
  mitigaciones son operativas (filesystem permissions, etc.).

### Alcance del modelo

- **Dentro del alcance**: Storage (SQLite queries), RunController,
  EventLog, locks, redaction, multi-tenancy, CLI runner (input
  parsing), promotion, handoff integrity.
- **Fuera del alcance**: Adapter real HTTP/LLM (E1, sin implementar),
  T5 backups, T6 observabilidad.

## Analisis STRIDE por superficie

### S1 — Storage (SQLite)

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **S**poofing | OK | Las queries filtran por `tenant_id, project_id` en todos los paths verificados (211 ocurrencias de `tenant_id` en `storage.py`). Tests `_test_isolation_*` (E2E-08) verifican cross-tenant rejection. |
| **T**ampering | OK (parcial) | `*_atomically` APIs cierran grietas B/C/D (nodo+evento). **Gap**: grieta A (workflow_runs↔runtime_events en `create_run`, `transition_run_state`) sigue abierta. Documentado en deuda_tecnica_residual. |
| **R**epudiation | OK | `runtime_events` append-only con `UNIQUE(event_id)`. Cada mutacion del estado emite al menos 1 evento (excepto en la grieta A). Tests T10 verifican idempotencia. |
| **I**nformation Disclosure | OK | Redaction policy por tenant (v0.13.0). 21 tests en `test_redaction.py`. CLI `sg policy get/set`. |
| **D**enial of Service | OK | RunBudget (v0.12.0): max_visits, max_runtime_seconds, max_events. cancel_run (v0.8.0). |
| **E**levation of Privilege | OK | Storage NO expone SQL crudo al exterior. La unica entrada es via APIs publicas validadas. Verificado por tests de "no storage._conn en CLI" (P4 cerrado). |

### S2 — Multi-tenant isolation

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **S**poofing | OK | `tenant_id` es smart constructor (`validate_tenant_id`), fuente unica (Storage). |
| **T**ampering | OK | `_source_to_payload` y `_entity_to_payload` filtran por `project_id` ademas de `tenant_id` (mejora documentada, commit del 2026-09-23). |
| **I**nformation Disclosure | OK | E2E-08 (test_h9_storage_knowledge_brick) verifica rechazo explicito de cross-tenant source lookup con mensaje generico (sin filtrar el source_id). |
| **E**levation | OK | RunController es inyectado por tenant; no comparte Storage entre tenants en el mismo proceso (cada llamada recibe su tenant_id). |

### S3 — Locks (v0.14.0)

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **T**ampering | OK | `RunLock` con fcntl advisory locks (POSIX) + timeout configurable. Tests `test_locks.py` con `multiprocessing` verifican 2 procesos se serializan. |
| **D**enial of Service | OK | `--lock-timeout-seconds` configurable. LockUnavailable tipado. |
| **R**epudiation | OK | El lock libera en `__exit__` (context manager) o en `release()` explicito. Tests cubren happy path y timeout. |
| **Gap** | Documentado | "Concurrencia real entre procesos: probada con multiprocessing (2 procesos), pero no certificada con proveedores reales ni bajo carga" (deuda_tecnica_residual). Cierre requiere spec de que es "stress". |

### S4 — Redaction (v0.13.0)

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **I**nformation Disclosure | OK | `RedactionPolicy` Literal ("none"\|"metadata"\|"payload"\|"full"). `redact_payload` cubre 4 politicas x happy/edge. 21 tests. |
| **Tampering** | OK | Validacion de policy en smart constructor. No bypass via string comparison. |
| **Gap** | Documentado | "Threat model (T3 del ROADMAP) NO ejecutado. No hay STRIDE/abuse-cases documentados." -> **ESTE ADR lo cierra**. |

### S5 — Adapter (fake/recording)

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| (todos) | N/A | FakeAgentAdapter y RecordingAdapter son deterministas (no invocan red ni LLM). Documentado en UAT-14. |
| **Gap** | ABIERTO | E1 Adapter real HTTP/LLM/anthropic/openai/local-llm requiere spec operador (proveedor + credenciales + timeouts + retries + sanitization). |

### S6 — Promotion (H6/H7, v0.6.0)

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **T**ampering | OK | `promotion.py` requiere `Authorization` (signed + autorizacion explicita). patch validation. Tests verifican que un patch sin autorizacion no se aplica. |
| **R**epudiation | OK | Outbox pattern en `storage.py` con eventos `PromotionProposed`, `PromotionAuthorized`, `PromotionApplied`. Idempotencia por `UNIQUE(event_id)`. |
| **E**levation | OK | Politicas en `graph_expansion.py`: `_validate_decision`, `_validate_action`, `_validate_domain_pack` (98% coverage). |

### S7 — CLI runner (input parsing)

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **T**ampering | OK | argparse valida tipos y choices antes de invocar la API. Tests `test_cli_branches.py` cubren argparse errors. |
| **I**njection | OK | Tenant/project IDs pasan por `validate_tenant_id` / `validate_project_id`. SQL parameters (no string interpolation). Tests verifican. |
| **Gap** | Documentado | `cli/runner.py` 49% cobertura (gap estructural, pytest-cov no rastrea subprocess). Audit en `audits/runner-coverage-2026-09-25.md`. Aceptado. |

### S8 — Adapter HTTP real (Anthropic + OpenAI) — WI-12 + WI-13

WI-12 introdujo `HttpAgentAdapter` (strategies Anthropic + OpenAI, retry
exponencial con jitter, failpoints `SKILLGRAPH_FAILPOINT_HTTP_{TIMEOUT,429,500}`).
WI-13 (`8213ea4`) anadio los flags CLI `--adapter http --llm-provider
{anthropic,openai}`. Esta superficie es nueva respecto al modelo previo
(S5: fake/recording era N/A para STRIDE). Ahora los Handoffs reales
cruzan la frontera del proceso via red hacia proveedores externos.

| STRIDE | Estado | Mitigacion / Gap |
|--------|--------|------------------|
| **S**poofing | OK | Credenciales solo via env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`); nunca en CLI args, fixtures, ni logs. `http_adapter_from_env()` rechaza `api_key=""` con `ValidationError` (`sg_*` exit code). Tests `TestHttpAgentAdapterEnvConfig` cubren fallback a env. |
| **T**ampering | OK | HTTPS enforced por httpx (no http plano configurable). Endpoint es `https://api.anthropic.com/v1/messages` o `https://api.openai.com/v1/chat/completions` (no user-controlled URL salvo via constructor `base_url` que es programatico). Body del request serializado por httpx (no manual concat). Headers firmados con `x-api-key` (Anthropic) o `Authorization: Bearer` (OpenAI). |
| **R**epudiation | OK | Cada invocacion del adapter registra `RunStarted` / `NodeScheduled` en EventLog (Storage append-only). `Handoff.context_hash` (SHA-256 sobre serializacion estable) garantiza reproducibilidad. Retry storms se mitigan con jitter exponencial (max 3 retries). |
| **I**nformation Disclosure | Mitigado | (a) Credenciales solo en env (no en logs). (b) `__repr__` del adapter NO expone `api_key` (verificado en `test_http_adapter.py::TestHttpAgentAdapterEnvConfig::test_repr_redacts_api_key`). (c) Request body envia `system_prompt` + `messages`; **gap menor**: el Handoff completo viaja al LLM (puede contener tenant data sensible). Recomendar `--adapter fake` o `--adapter redacted` para datos sensibles (P3 deferred). |
| **D**enial of Service | Mitigado | Retry con backoff exponencial (1s base / 8s max, jitter ±25%). Failpoints `SKILLGRAPH_FAILPOINT_HTTP_TIMEOUT/_429/_500` para testing sin red. `timeout_s=30` (configurable via `--llm-timeout-s`). **Gap menor**: rate limits de Anthropic/OpenAI aplican; un burst de Runs podria agotar cuota. Recomendar budget por tenant (P3 deferred). |
| **E**levation of Privilege | OK | Adapter solo expone `invoke(handoff: Handoff) -> AgentResult`. Sin `eval`, sin shell. Sin escritura a disco (no I/O oculto). Los env vars leídos son read-only. |

## Gaps abiertos (no cerrados por este ADR)

1. **Grieta A workflow_runs↔runtime_events**: NO cerrada por H9-Plan-B.
   Grietas B/C/D (nodo+evento) SI cerradas. Cierre de A requiere
   operaciones Storage atomicas que coordinen INSERT/UPDATE
   workflow_runs + INSERT runtime_events en una sola transaccion.
   Coste estimado: 300-800 LoC + tests de concurrencia con 2-4 procesos.

2. **E1 Adapter real**: **CERRADO** en WI-12 + WI-13 (`31562a8`,
   `8213ea4`). Ver seccion S8. Quedan 2 gaps menores (P3 deferred):
   (a) Handoff completo viaja al LLM (potencial disclosure de tenant
   data sensible); (b) rate limits de proveedor sin budget por tenant.

3. **Certificacion stress concurrencia**: PROBADO con 2 procesos en
   `test_locks.py`, NO certificado bajo carga real. Requiere spec.

4. **Audit post-schema-change**: NO formalizado. Migraciones son
   idempotentes pero no se ejecuta un audit post-cambio.

5. **STRIDE gaps menores en S8 (P3 deferred)**:
   - I/c: Redacción de Handoff antes de enviar al LLM (recomendar
     `--adapter fake` para datos sensibles).
   - D/b: Budget de tokens por tenant (evitar agotar cuota en burst).

## Tests verificables (este ADR anade commits)

- `tests/test_t3_threat_model_attestation.py`: tests parametrizados
  que verifican la **invariante** del modelo: "las superficies
  documentadas como OK siguen OK" (no son tests del modelo en si,
  sino tests de sus consecuencias testeables).
- `tests/test_http_adapter.py` (WI-12, 25 tests, 5 clases):
  `TestAnthropicStrategy`, `TestOpenAIStrategy`, `TestHttpAgentAdapter`,
  `TestHttpAdapterEnvConfig`, `TestRetryAndFailpoints`. Verifican S8.
- `tests/test_cli_adapter_wiring.py` (WI-13, 11 tests, 4 clases):
  verifican que la CLI NO expone credenciales, requiere env vars, y
  rechaza valores invalidos con `ValidationError`.
- `audits/t3-threat-model-2026-09-25.md`: audit inicial con 14 tests.

## Consecuencias

- Las **propiedades defensivas** del sistema quedan registradas con
  el mecanismo que las garantiza.
- Los **gaps** abiertos quedan explicitados con el esfuerzo estimado.
- El operador puede **vetar** el modelo de atacante asumido si su
  contexto difiere (ej. SaaS en vez de local-first).
- **No introduce cambios de codigo**: el ADR documenta el estado real
  sin modificar comportamiento.
- Tests adicionados son **verificables** (la invariante se mantiene o
  rompe visiblemente).

## Persistencia

Este ADR vive en `docs/architecture/ADR-0015-threat-model-stride.md`.
El directorio `external/` (donde viven los blueprints y ADRs del
blueprint-v1) esta gitignored por diseno (es input externo al
repo, no fuente de verdad versionada). Los ADRs nuevos que se
quieren persistir se guardan en `docs/architecture/`.

## Revisit trigger

Revisar si:
- Se introduce Adapter real (E1) -> el modelo de atacante debe
  extenderse para cubrir threats de prompt injection y data exfiltration.
- Se cierra la grieta A workflow_runs↔runtime_events -> actualizar
  seccion S1 "Tampering" a OK completo.
- Se ejecuta T5/T6 -> re-evaluar S1 "Information Disclosure" y S7.
- El operador veta el modelo de atacante asumido.
