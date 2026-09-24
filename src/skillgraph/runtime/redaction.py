"""Politicas de redaccion de payloads para el EventLog (Etapa 7 / S5).

Doc externo:
  external/blueprint-v1/docs/06-controladores.md §9 (politicas).

Un Run emite eventos con payloads que pueden contener secretos
(API keys, tokens, paths absolutos de workspace, etc.). Persistir
esos payloads en SQLite los hace visibles a cualquier agente o
humano que lea la DB. La politica de redaccion decide que se
persiste y que se reemplaza por `[REDACTED]`.

Reglas:
- Politica pura: `redact_payload` no lee reloj, no toca I/O, es
  una funcion pura (mismo input -> mismo output).
- Sin estado mutable. Si la politica fuera configurable por
  tenant, vive en Storage (no en este modulo).
- Politica explicita: si no se aplica, el payload pasa integro
  (regla `none`).
"""

from __future__ import annotations

from typing import Any, Final, Literal

from skillgraph.core.errors import ValidationError

#: Politicas soportadas. Anadir una nueva politica es un cambio de
#: contrato del blueprint (no se hace por feature creep).
RedactionPolicy = Literal["none", "metadata", "payload", "full"]

#: Conjunto canonico exportado para validacion runtime.
_REDACTION_POLICIES: Final[frozenset[str]] = frozenset(
    {"none", "metadata", "payload", "full"}
)

#: Marcador de redaccion. Constante para que el caller pueda
#: detectar y formatear en UIs.
REDACTED_MARKER: Final[str] = "[REDACTED]"


def validate_policy(policy: str) -> RedactionPolicy:
    """Smart constructor: valida y devuelve un `RedactionPolicy` tipado.

    Raises:
        ValidationError: si la politica no esta en el conjunto canonico.
    """
    if policy not in _REDACTION_POLICIES:
        raise ValidationError(
            f"redaction_policy invalida: {policy!r} "
            f"(esperado una de {sorted(_REDACTION_POLICIES)})"
        )
    # El check `in _REDACTION_POLICIES` ya valida la pertenencia.
    return policy  # type: ignore[return-value]


def redact_payload(
    payload: dict[str, Any], policy: RedactionPolicy
) -> dict[str, Any]:
    """Aplica la politica de redaccion al payload.

    Politicas (todas son funciones puras):
    - `none`: devuelve una copia superficial del payload sin
      modificar nada (compat con el comportamiento previo a S5).
    - `metadata`: conserva las claves pero reemplaza todos los
      valores por `REDACTED_MARKER`. Mantiene la estructura de
      claves (util para depuracion sin exponer valores).
    - `payload`: redaccion recursiva: cualquier valor que NO sea
      lista/tupla/dict se reemplaza por `REDACTED_MARKER`; las
      colecciones se procesan recursivamente. Ideal para payloads
      mixtos (algunos campos son publicos, otros no).
    - `full`: devuelve `{}`. El payload completo se descarta;
      solo se conserva la existencia del evento.

    Args:
        payload: diccionario a redactar. NO se muta.
        policy: politica a aplicar (debe estar validada).

    Returns:
        Nuevo diccionario (nunca mutamos el input).
    """
    validate_policy(policy)
    if policy == "none":
        # Copia superficial para no exponer referencias mutables.
        return dict(payload)
    if policy == "metadata":
        return {k: REDACTED_MARKER for k in payload}
    if policy == "full":
        return {}
    # policy == "payload": redaccion recursiva.
    return _redact_recursive(payload)


def _redact_recursive(value: Any) -> Any:
    """Redaccion recursiva para `policy='payload'`.

    Reglas:
    - dict: aplica redaccion a cada valor; mantiene la clave.
    - list/tuple: aplica redaccion a cada elemento.
    - cualquier otro: REDACTED_MARKER.
    """
    if isinstance(value, dict):
        return {k: _redact_recursive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_recursive(x) for x in value]
    if isinstance(value, tuple):
        return tuple(_redact_recursive(x) for x in value)
    return REDACTED_MARKER
