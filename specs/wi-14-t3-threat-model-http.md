# WI-14: T3 Threat model — superficie HTTP (S8)

## Objetivo

Extender el modelo STRIDE (ADR-0015) para cubrir la superficie nueva
introducida por WI-12 + WI-13: `HttpAgentAdapter` con credenciales
reales hacia Anthropic y OpenAI. Documentar abuse-cases y gaps
residuales antes de promover WI-12/13 a release.

## Decision previa (D-47)

- WI-12/13 introducen **S8** (Adapter HTTP real) al catalogo STRIDE
  (S1..S7 ya documentados). Antes era "N/A: fake adapter" (S5).
- **Hallazgo honesto**: el claim inicial "el repr NO expone api_key" era
  **falso** — el dataclass auto-generado muestra TODOS los campos.
  RED test (test_http_adapter_repr_no_disclosure.py) lo evidencia.
- **Mitigacion aplicada**: `api_key: str = field(repr=False)` +
  `__repr__` explicito que solo muestra provider/model/timeouts.
- Tests verificables: 27 PASS (25 WI-12 + 2 WI-14).

## Cambios

### `docs/architecture/ADR-0015-threat-model-stride.md`

1. Nueva seccion **S8 — Adapter HTTP real (Anthropic + OpenAI)**:
   - STRIDE: S/T/R/I/D/E cubiertos.
   - 4 OK, 2 mitigados con gaps menores (P3 deferred).
   - 2 gaps menores registrados:
     - I/c: Handoff completo viaja al LLM (potencial disclosure).
     - D/b: Rate limits sin budget por tenant.
2. **Gaps abiertos**: E1 Adapter real marcado **CERRADO** (WI-12 + WI-13),
   gaps menores separados como item 5 (P3 deferred).
3. **Tests verificables**: anadidos `test_http_adapter.py` (25) y
   `test_cli_adapter_wiring.py` (11) como evidencia de S8.

### `src/skillgraph/runtime/http_adapter.py`

- `api_key: str = field(repr=False)` — evita dataclass auto-repr leak.
- `__repr__` explicito: `HttpAgentAdapter(provider='anthropic',
  model='claude-3-5-sonnet-20241022', timeout_s=30.0, max_retries=3)`.
- NO incluye `api_key`, `base_url` (puede ser local proxy), `client`
  (httpx.Client puede contener headers).

### `tests/test_http_adapter_repr_no_disclosure.py` (nuevo, 2 tests)

- `test_repr_does_not_contain_api_key_value`: RED -> GREEN tras
  `field(repr=False) + __repr__`.
- `test_str_does_not_contain_api_key_value`: mismo check sobre `str()`.

## Hallazgos (abuse-cases)

| STRIDE | Abuse-case | Estado |
|--------|-----------|--------|
| **S**poofing | Adversario con acceso a env vars roba API key | Mitigado: env vars solo en proceso, no en CLI args ni fixtures |
| **T**ampering | Adversario MITM entre proceso y api.anthropic.com | Mitigado: HTTPS enforced, sin http plano |
| **R**epudiation | Operador niega haber ejecutado un Run | Mitigado: EventLog append-only con `RunStarted/NodeScheduled` |
| **I**nformation Disclosure | api_key en logs via repr/str | **CERRADO** (D-47): field(repr=False) + __repr__ explicito |
| **I**nformation Disclosure | Handoff sensible viaja al LLM | Gap P3: usar `--adapter fake` para datos sensibles |
| **D**enial of Service | Retry storm por respuesta lenta | Mitigado: backoff exponencial con jitter |
| **D**enial of Service | Rate limits de proveedor agotados | Gap P3: budget por tenant deferred |
| **E**levation of Privilege | Adapter ejecuta codigo arbitrario | NO posible: solo HTTP POST a URL hardcoded |

## Compatibilidad

- **Backward-compatible**: ningun cambio en la API publica. El repr
  cambia (menos campos), pero los tests existentes no asumian el
  contenido del repr.
- 0 cambios en CLI.

## Evidencia

- `uv run pytest tests/test_http_adapter.py tests/test_http_adapter_repr_no_disclosure.py` -> 27/27 PASS
- `uv run ruff check src tests` -> All checks passed
- ADR-0015 extendido con S8 + 5 gaps abiertos documentados.

## Pendiente tras WI-14

- **WI-15 (T5 Backups CLI)**: `sg backup create|restore|list`.
- **WI-16 (T6 Observabilidad)**: runbook sinks + retención.
- **WI-17+ (deuda arquitectónica)**: H-01..H-10.
- Bump `0.14.6.dev0 → 0.14.7` con WI-12/13/14 agrupados (FEAT x3
  suficiente para MINOR bump).
- Push a origin (regla WI-01).
