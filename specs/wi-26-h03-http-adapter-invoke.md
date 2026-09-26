# WI-26: deuda H-03 (http_adapter.invoke cc=12)

## Objetivo

Reducir cc de `HttpAgentAdapter.invoke` (cc=12). El alto cc venia
de la logica inline de dispatch HTTP: branches por status_code
(200 / 429 / 5xx / otros 4xx) + retry loop con sleep + multiple
raise segun el tipo de excepcion.

## Cambio

- Nueva clase `RetryableHttpStatus(Exception)` con `code = "sg_http_retryable"`.
  Es una senal interna del adapter: cuando `_dispatch_response`
  ve 429 o 5xx, lanza `RetryableHttpStatus` en vez de
  `NotFoundError`. No es `SkillGraphError` (no la ve el usuario:
  el `invoke` la atrapa, aplica retry, y solo si se agotan los
  intentos la convierte en `NotFoundError`).
- Extraido `_dispatch_response(response) -> AgentResult` (cc=4):
  pura logica de dispatch por status_code. Lanza:
    - 200 -> parse_response del strategy
    - 429/5xx -> RetryableHttpStatus
    - otros 4xx -> ValidationError (cliente)

`invoke` queda como orquestador (cc=7) con un `try` y 3
`except` (timeout/network, RetryableHttpStatus, otros).

## Compatibilidad

- 100% backward-compatible:
  - Mismas excepciones finales que ve el usuario (NotFoundError
    para 429/5xx/timeout tras agotar retries, ValidationError
    para 4xx). El retry loop sigue siendo identico.
  - Mismos mensajes (mismo formato "HTTP NNN: ...").
- 27/27 tests PASS en test_http_adapter + test_http_adapter_repr_no_disclosure.

## Decision previa (D-59)

- **D-59**: Cuando un metodo tiene logica de dispatch por valor
  (status_code, kind, etc.) con ramas que terminan en raise y
  raise "post-loop", extraer a un helper que NO hace raise
  policy, solo raise tipado por tipo de respuesta. El caller
  decide la politica de retry/error.

## Evidencia

- `invoke` cc: 12 -> 7 (-42%).
- `_dispatch_response`: cc=4.
- 1044/1044 PASS en suite completa (303.19s).
- ruff: All checks passed.
