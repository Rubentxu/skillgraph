"""KnowledgeInvalidator: traversal de dependencias + invalidacion + refresh.

Doc externo:
  specs/h3-slice-4.md (sub-spec firmado en el H3).
  external/blueprint-v1/docs/08-conocimiento-y-contexto.md (literal).

Algoritmo de invalidacion (orden exacto del blueprint §8):
  detect_source_change(source_id)
    -> locate_direct_claims(source_id)
    -> traverse_relevant_dependencies(transitively, max_hops)
    -> mark_affected_claims_stale(claim_ids)
    -> identify_active_consumers(claim_ids)        -- (vacio en H3)
    -> schedule_required_refresh()                -- (delegado al caller)
    -> emit_event KnowledgeInvalidated

Refresh (D19):
  KnowledgeController.refresh_source(source_id, *, new_revision):
    -> lee source, captura nueva revision via Git (fuera de scope H3
       si no hay dulwich; sino reusa blob_shas del Storage).
    -> marca stale=0 las Claims que ahora vuelven a referenciar la
       nueva revision.
    -> emit_event KnowledgeRefreshed.
"""

from __future__ import annotations

import uuid
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from skillgraph.errors import (
    HopLimitExceededWarning,
)
from skillgraph.knowledge import Claim, ClaimID, SourceID

if TYPE_CHECKING:
    from skillgraph.knowledge_controller import KnowledgeController


DEFAULT_MAX_HOPS: int = 2
"""Default traversal depth (D17)."""


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _new_event_id(kind: str) -> str:
    """Genera event_id estable via UUIDv5 sobre (kind, timestamp slot)."""
    return f"evt-{uuid.uuid5(uuid.NAMESPACE_URL, f'{kind}-{_now_iso()}')}"


# ---------------------------------------------------------------------------
# Pure traversal helpers (no I/O)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InvalidationResult:
    """Resultado del traversal."""

    invalidated_claim_ids: tuple[ClaimID, ...]
    hop_chain: tuple[int, ...]  # distribucion de hops por claim invalidado
    truncated: bool  # True si se emitio HopLimitExceededWarning


def traverse_invalidations(
    *,
    controller: KnowledgeController,
    source_id: SourceID,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> InvalidationResult:
    """Recorre las Claims que dependen del source (transitivo).

    Estrategia H3:
      - claims directos (source_id = source_id).
      - claims indirectos via evidencia compartida:
        claim_inicial -> evidence -> otros_claims que la referencian.
      - claims indirectos via misma entity afectada.

    Devuelve InvalidationResult SIN mutar el Storage; el caller decide
    si marcar stale o no.
    """
    visited_claims: set[ClaimID] = set()
    visited_evidence: set[str] = set()
    hop_distribution: dict[ClaimID, int] = {}
    truncated = False
    current_frontier: list[ClaimID] = []

    # Hop 0: claims directos que referencian source_id.
    direct_claims = controller.list_claims_for_source(source_id=source_id)
    for c in direct_claims:
        if c.claim_id not in visited_claims:
            visited_claims.add(c.claim_id)
            hop_distribution[c.claim_id] = 0
            current_frontier.append(c.claim_id)

    # Iterar hops.
    for hop in range(1, max_hops + 1):
        if not current_frontier:
            break
        next_frontier: list[ClaimID] = []
        for claim_id in current_frontier:
            try:
                _claim = controller.get_claim(claim_id=claim_id)
            except Exception:
                continue
            for evidence in controller.get_evidences_for_claim(
                claim_id=claim_id,
            ):
                if evidence.evidence_id in visited_evidence:
                    continue
                visited_evidence.add(evidence.evidence_id)
                for other in _claims_using_evidence(
                    controller,
                    evidence.evidence_id,
                ):
                    if other in visited_claims:
                        # Revisita: el ciclo ya fue visitado.
                        # No es un error: el traversal es robusto
                        # porque `visited_claims` evita loops.
                        continue
                    visited_claims.add(other)
                    hop_distribution[other] = hop
                    next_frontier.append(other)
        current_frontier = next_frontier
        if hop == max_hops and current_frontier:
            truncated = True
            warnings.warn(
                f"max_hops={max_hops} alcanzado con frontier no vacia: "
                f"{len(current_frontier)} claims sin explorar",
                HopLimitExceededWarning,
                stacklevel=2,
            )

    return InvalidationResult(
        invalidated_claim_ids=tuple(visited_claims),
        hop_chain=tuple(hop_distribution[c] for c in visited_claims),
        truncated=truncated,
    )


def _claims_using_evidence(controller: KnowledgeController, evidence_id: str) -> Iterator[ClaimID]:
    """Yield ClaimID de las claims que referencian una evidence."""
    rows = controller.storage._conn.execute(
        "SELECT claim_id FROM claim_evidence WHERE evidence_id = ?",
        (evidence_id,),
    ).fetchall()
    for r in rows:
        yield ClaimID(r["claim_id"])


# ---------------------------------------------------------------------------
# Mutating API (delega al controller)
# ---------------------------------------------------------------------------


def invalidate_from_source(
    controller: KnowledgeController,
    *,
    source_id: SourceID,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> list[ClaimID]:
    """Invalida claims dependientes del source. Emite KnowledgeInvalidated."""
    # Validar source existente.
    controller.get_source(source_id=source_id)

    result = traverse_invalidations(
        controller=controller,
        source_id=source_id,
        max_hops=max_hops,
    )

    if not result.invalidated_claim_ids:
        return []

    # Marcar stale.
    for cid in result.invalidated_claim_ids:
        controller.storage._conn.execute(
            "UPDATE claims SET stale = 1 WHERE claim_id = ? AND tenant_id = ? AND project_id = ?",
            (cid, controller.tenant_id, controller.project_id),
        )
    controller.storage._conn.commit()

    # Emitir event.
    controller.storage.record_event(
        tenant_id=controller.tenant_id,
        project_id=controller.project_id,
        event_id=_new_event_id("KnowledgeInvalidated"),
        event_kind="KnowledgeInvalidated",
        resource_ref=f"source:{source_id}",
        payload={
            "source_id": source_id,
            "count": len(result.invalidated_claim_ids),
            "max_hops": max_hops,
            "truncated": result.truncated,
        },
    )
    return list(result.invalidated_claim_ids)


def refresh_source(
    controller: KnowledgeController,
    *,
    source_id: SourceID,
    new_revision: str,
) -> list[ClaimID]:
    """Marca stale=0 las Claims que pasan a referenciar `new_revision`.

    Una Claim se reactiva si y solo si su `checked_at_revision ==
    new_revision` (es la unica forma honesta de revalidar sin reejecutar
    extractors: el caller externo debera haber regenerado Claims con
    la nueva revision; este metodo reactiva los que coincidan).

    Emite `KnowledgeRefreshed` con la lista de ClaimIDs reactivados.
    Si la lista esta vacia y el caller habia solicitado refresh,
    emite ademas `HopLimitExceededWarning` solo si hubo truncation;
    en este metodo no hay traversal, asi que el warning no se emite.
    """
    controller.get_source(source_id=source_id)

    # Buscar Claims stale con la nueva revision y reactivarlas.
    rows = controller.storage._conn.execute(
        """
        UPDATE claims
        SET stale = 0
        WHERE tenant_id = ? AND project_id = ?
          AND source_id = ? AND checked_at_revision = ?
          AND stale = 1
        RETURNING claim_id
        """,
        (
            controller.tenant_id,
            controller.project_id,
            source_id,
            new_revision,
        ),
    ).fetchall()
    controller.storage._conn.commit()

    claim_ids: list[ClaimID] = [ClaimID(r["claim_id"]) for r in rows]

    controller.storage.record_event(
        tenant_id=controller.tenant_id,
        project_id=controller.project_id,
        event_id=_new_event_id("KnowledgeRefreshed"),
        event_kind="KnowledgeRefreshed",
        resource_ref=f"source:{source_id}",
        payload={
            "source_id": source_id,
            "new_revision": new_revision,
            "reactivated_count": len(claim_ids),
            "reactivated": list(claim_ids),
        },
    )
    return claim_ids


def list_stale_claims(
    controller: KnowledgeController,
) -> Sequence[Claim]:
    """Lista todas las Claims stale del (tenant, project)."""
    import json as _json

    from skillgraph.storage import _row_to_claim  # type: ignore[attr-defined]

    rows = controller.storage._conn.execute(
        """
        SELECT c.claim_id, c.subject_entity_id, c.predicate, c.object_literal_json,
               c.source_id, c.extraction_method, c.extractor_version,
               c.checked_at_revision, c.stale
        FROM claims c
        WHERE c.tenant_id = ? AND c.project_id = ? AND c.stale = 1
        ORDER BY c.checked_at_revision DESC
        """,
        (controller.tenant_id, controller.project_id),
    ).fetchall()

    out: list[Claim] = []
    for row in rows:
        ev_rows = controller.storage._conn.execute(
            "SELECT evidence_id FROM claim_evidence WHERE claim_id = ?",
            (row["claim_id"],),
        ).fetchall()
        ev_ids = [r["evidence_id"] for r in ev_rows]
        out.append(_row_to_claim(row, ev_ids, _json))  # type: ignore[arg-type]
    return out


__all__ = [
    "DEFAULT_MAX_HOPS",
    "InvalidationResult",
    "invalidate_from_source",
    "list_stale_claims",
    "refresh_source",
    "traverse_invalidations",
]
