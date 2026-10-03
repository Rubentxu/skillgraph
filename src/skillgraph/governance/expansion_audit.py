"""Persistencia del RECHAZO de una propuesta de expansion (UAT-09).

**POR QUE ESTE MODULO EXISTE.** `graph_expansion.py` proposer, valida,
autoriza y aplica. Registrar que algo se rechaza es otra cosa: es
escribir a disco un registro de auditoria, con su formato, su
directorio y su por que. No comparte invariante con el grafo.

No es una mudanza estetica. `graph_expansion.py` estaba en 787 de 800
LoC —al 98 % de su presupuesto— y la integracion del diff de B5 lo
cruzo. La salida no fue recortar prosa: la razon por la que la prosa
era larga es que el razonamiento no cabia alli, y por eso vive aqui y
en `graph_diff.py`.

`GraphExpansionProposal` se importa SOLO bajo TYPE_CHECKING: el modulo
que lo define reexporta esta funcion para no romper a quien la importa
desde ahi, y un import a nivel de modulo cerraria el ciclo. En
runtime la funcion solo LEE atributos de la propuesta, luego no
necesita el tipo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from skillgraph.runtime.engine import now_iso

if TYPE_CHECKING:
    from skillgraph.governance.graph_expansion import GraphExpansionProposal


def record_rejection(
    proposal: GraphExpansionProposal,
    *,
    reason: str,
    rejected_by: str,
    project_dir: Path,
    violated_invariants: tuple[str, ...] = (),
) -> Path:
    """Persiste evidencia de rechazo (UAT-09).

    Crea un archivo ``expansion_rejections/<proposal_id>.json`` dentro
    del directorio del proyecto. Devuelve la ruta del archivo.

    ``violated_invariants`` es opcional: si la rechazo viene del
    validador (I1..I6), se persiste para audit. Los rechazos por
    autorizacion (I0) o por error de carga no llevan invariantes.
    """
    target_dir = project_dir / "expansion_rejections"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{proposal.proposal_id}.json"
    payload = {
        "proposal_id": proposal.proposal_id,
        "author": proposal.author,
        "created_at": proposal.created_at,
        "problem_observed": proposal.problem_observed,
        "operations_count": len(proposal.operations),
        "capabilities_needed": list(proposal.capabilities_needed),
        "new_dependencies": list(proposal.new_dependencies),
        "attachment_point": proposal.attachment_point,
        "authorization_mode": proposal.authorization.mode,
        "rejected_by": rejected_by,
        "rejected_at": now_iso(),
        "reason": reason,
        "violated_invariants": list(violated_invariants),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return target
