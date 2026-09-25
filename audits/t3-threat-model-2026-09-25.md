# T3 Threat model — Audit de verificacion

**ADR (filesystem local, no trackeado)**: `external/blueprint-v1/adr/ADR-0015-threat-model-stride.md`
**Audit (persiste en git)**: este fichero
**Tests (persisten en git)**: `tests/test_t3_threat_model_attestation.py`
**Fecha**: 2026-09-25
**Ciclo**: STEWARDSHIP-T3-001

## Resultado

Modelo STRIDE documentado con 7 superficies (S1..S7), 4 perfiles de
atacante asumidos (A1..A4) y 4 gaps abiertos registrados.

| Superficie | STRIDE state | Tests verificables | Resultado |
|---|---|---|---|
| S1 Storage | OK (parcial, gap A) | `test_t3_threat_model_attestation.py::TestS1*` | PASS 4/4 |
| S2 Multi-tenant | OK + gap conocido (mensaje filtra source_id) | `TestS2CrossTenantLookupRejected` | PASS 1/1 |
| S3 Locks | OK + gap conocido (stress) | `TestS3LocksAcquisitionAndTimeout` | PASS 2/2 |
| S4 Redaction | OK | `TestS4RedactionTypedPolicies` | PASS 5/5 |
| S5 Adapter | N/A (fake) | `TestS5AdapterIsDeterministic` | PASS 1/1 |
| S6 Promotion | OK | `TestS6PromotionRequiresAuthorization` | PASS 1/1 |
| S7 CLI runner | OK | `TestS7CLIInputValidation` | PASS 1/1 |

**Total**: 14 tests, 14 PASS.

## Gaps abiertos (registrados en ADR-0015)

1. **Grieta A workflow_runs↔runtime_events**: NO cerrada por H9-Plan-B
   (que cerro B/C/D). Coste estimado 300-800 LoC.
2. **Mensaje de error filtra source_id** (S2/I, gap menor): el
   `KnowledgeController.get_source` retorna `UnknownSourceError` con
   el source_id en el mensaje. Fix: refactor del controller para
   emitir mensaje generico. Coste: ~10 LoC + 1 test.
3. **Certificacion stress concurrencia** (S3): probada con 2 procesos
   en `test_locks.py`, no certificada bajo carga. Requiere spec.
4. **Audit post-schema-change** (S1): NO formalizado.

## Decisiones de diseno

- **Modelo de atacante A1..A4 explicitado**: el ADR no asume
  implicitamente. A4 (atacante con shell) queda fuera del alcance
  por construccion (mitigacion operativa).
- **S2 OK con gap honesto**: el test de cross-tenant verifica que el
  controller NO ve la source, pero NO verifica que el mensaje de
  error NO filtra el source_id. Ese gap se documenta, no se testa
  como OK.
- **S5 N/A honesto**: FakeAgentAdapter no hace red. Si en el futuro
  se introduce Adapter real (E1), el modelo debe extenderse.
- **Test S3 con threading**: la verificacion de LockUnavailable
  requiere un holder concurrente. Usa `threading.Event` para
  sincronizar y evitar flakiness.

## Verificacion

```bash
$ mise exec -- uv run pytest tests/test_t3_threat_model_attestation.py -q
14 passed in 0.97s

$ mise exec -- uv run ruff check tests/test_t3_threat_model_attestation.py
All checks passed!

$ wc -l tests/test_t3_threat_model_attestation.py external/blueprint-v1/adr/ADR-0015-threat-model-stride.md
  385 tests/test_t3_threat_model_attestation.py
  173 docs/architecture/ADR-0015-threat-model-stride.md
```

## Lecciones aprendidas

- **API discovery es costoso**: escribir tests contra un codebase
  desconocido requirio inspeccionar firmas reales (Storage.create_run,
  Authorization.mode/granted_by, RuntimeEvent.event_kind, RunLock.take).
  Esto es parte del costo del stewardship T3 pero los tests quedan
  como red de seguridad ante regresiones.

- **Gap descubierto durante testing**: el `get_source` del controller
  filtra source_id en el mensaje. Esto NO estaba documentado en
  deuda_tecnica_residual. Es un finding nuevo que se agrega al ADR.

- **SIM117 en pytest.raises + nested with**: ruff no permite combinar
  `with pytest.raises(X):` con `with lock_b.take(...)`. Workaround:
  `# noqa: SIM117` en la linea. Es idiomatico para verificar
  excepciones en context managers.

- **Decision de scope**: el modelo NO cubre Adapter real (E1) ni
  T5/T6 porque no estan implementados. Esto evita speculation.

## Siguiente

- Si el operador quiere cerrar el gap S2 (mensaje filtra source_id),
  crear un test que verifique el mensaje generico + refactor del
  controller. Estimado: 30 min.
- Si se introduce Adapter real (E1), extender el modelo con
  threats de prompt injection y data exfiltration.
