"""H7 promocion entre bases (UAT-13): outbox persistente + reconciliacion
idempotente.

Criterio verificable (UAT-13):
"Dada una propuesta de promocion persistida en un proyecto, cuando se
interrumpe el proceso durante su publicacion, entonces la reconciliacion
permite completarla sin duplicar la capacidad compartida."

Patron del blueprint (doc 09):
"La promocion de conocimiento desde un proyecto a un catalogo compartido
utilizara:
  1. Resultado persistido en la base origen.
  2. Mensaje de outbox.
  3. Aplicacion idempotente en la base destino.
  4. Confirmacion de la operacion.
  5. Reconciliacion si se interrumpe el proceso."

Implementacion:
- `submit_proposal(storage, ...)`: inserta en promotion_outbox (status=PENDING).
- `apply_proposal(storage, ...)`: marca IN_PROGRESS, intenta aplicar al
  target, marca PUBLISHED. Es IDEMPOTENTE: si ya esta PUBLISHED,
  retorna sin duplicar.
- `reconcile_pending(storage, apply_fn)`: procesa todas las propuestas
  PENDING/IN_PROGRESS usando `apply_fn`. Si el proceso se interrumpio
  durante apply, la siguiente ejecucion completa la transicion.
- `idempotency_key`: source_project + knowledge_ref garantiza que la
  misma capacidad no se promueve dos veces.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from skillgraph.errors import ValidationError
from skillgraph.storage import Storage


def _compute_idempotency_key(source_project: str, knowledge_ref: str) -> str:
    """Clave estable que garantiza 'no duplicar la capacidad compartida'.

    Misma (source_project, knowledge_ref) -> misma key -> no se inserta
    una segunda propuesta.
    """
    if not source_project or not knowledge_ref:
        raise ValidationError("idempotency_key: source_project y knowledge_ref son obligatorios")
    return f"{source_project}::{knowledge_ref}"


def submit_proposal(
    storage: Storage,
    *,
    proposal_id: str,
    tenant_id: str,
    source_project: str,
    target_catalog: str,
    knowledge_ref: str,
    payload: dict[str, Any],
) -> None:
    """Paso 1-2: persistir propuesta en outbox origen (status=PENDING).

    Idempotente: si ya existe una propuesta con el mismo
    idempotency_key, lanza `IdentityConflictError` (storage layer).
    """
    idem = _compute_idempotency_key(source_project, knowledge_ref)
    storage.register_promotion(
        proposal_id=proposal_id,
        idempotency_key=idem,
        tenant_id=tenant_id,
        source_project=source_project,
        target_catalog=target_catalog,
        knowledge_ref=knowledge_ref,
        payload=payload,
    )


def apply_proposal(
    storage: Storage,
    proposal_id: str,
    *,
    apply_fn: Callable[[dict[str, Any]], bool],
) -> str:
    """Paso 3-4: aplica la propuesta al catalogo destino.

    `apply_fn(payload)` ejecuta la operacion de negocio (e.g. copiar
    el knowledge al catalogo destino). Debe devolver True si se aplico
    exitosamente (o si ya estaba aplicado: idempotencia).

    Devuelve el status final: 'PUBLISHED' o 'FAILED'.

    Idempotente:
    - Si status ya es PUBLISHED, retorna 'PUBLISHED' sin reaplicar.
    - Si status es FAILED, retorna 'FAILED' sin reintentar
      (requiere inspeccion manual).
    - Si status es PENDING o IN_PROGRESS (reanudacion tras crash),
      asegura que esta IN_PROGRESS, llama apply_fn, y si True ->
      PUBLISHED. Si apply_fn lanza o devuelve False, marca FAILED.
    """
    proposal = storage.get_promotion(proposal_id)
    if proposal is None:
        raise ValidationError(f"apply_proposal: proposal_id={proposal_id!r} no existe")

    status = proposal["status"]
    if status == "PUBLISHED":
        return "PUBLISHED"
    if status == "FAILED":
        return "FAILED"

    # status IN ('PENDING', 'IN_PROGRESS'): asegurar IN_PROGRESS.
    # Si era PENDING, transiciona. Si ya era IN_PROGRESS (reanudacion),
    # marca_in_progress devuelve False (idempotencia) -> OK, proceder.
    storage.mark_promotion_in_progress(proposal_id)

    try:
        ok = apply_fn(proposal["payload"])
    except Exception:
        storage.mark_promotion_failed(proposal_id)
        return "FAILED"

    if ok:
        storage.mark_promotion_published(proposal_id)
        return "PUBLISHED"
    storage.mark_promotion_failed(proposal_id)
    return "FAILED"


def reconcile_pending(
    storage: Storage,
    apply_fn: Callable[[dict[str, Any]], bool],
) -> list[dict[str, str]]:
    """Paso 5: reconcilia todas las propuestas PENDING/IN_PROGRESS.

    Devuelve una lista de `{proposal_id, status}` para cada propuesta
    procesada. La idempotencia de `apply_proposal` garantiza que si
    el proceso se interrumpio durante un apply anterior, esta llamada
    lo completa sin duplicar.
    """
    results: list[dict[str, str]] = []
    pending = storage.list_pending_promotions()
    for proposal in pending:
        final_status = apply_proposal(storage, proposal["proposal_id"], apply_fn=apply_fn)
        results.append({"proposal_id": proposal["proposal_id"], "status": final_status})
    return results


__all__ = [
    "_compute_idempotency_key",
    "apply_proposal",
    "reconcile_pending",
    "submit_proposal",
]
