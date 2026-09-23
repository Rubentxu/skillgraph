"""Adapter de agente y resultado determinista (Etapa 2 / S3).

Doc externo:
  external/blueprint-v1/docs/06-controladores.md §6 (extensiones
  Python: se ejecutan mediante un adaptador autorizado, devuelven
  resultados estructurados).
  external/blueprint-v1/docs/15-resultados-y-evidencia.md

Reglas de diseno:
- El Adapter recibe un Handoff y devuelve un `AgentResult` estructurado.
- El Adapter NO conoce Storage, RunController ni nada del core: solo
  recibe el Handoff y emite un resultado (por eso Handoff esta
  serializado de forma estable: para que el Adapter pueda cachearlo
  sin pedir nada mas).
- El Adapter NO se ejecuta automaticamente al importar un Domain Pack
  (UAT-14: importar NO ejecuta scripts).
- `FakeAgentAdapter` se usa para tests y para el modo determinista
  local. Lee fixtures desde un directorio:
    <fixtures_root>/<tenant_id>/<project_id>/<node_execution_id>.json
  La fixture es un JSON con `outcome` y `result`. Si no existe,
  NotFoundError: el Adapter no improvisa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from skillgraph.errors import NotFoundError, OutcomeInvalidError, ValidationError
from skillgraph.handoff import Handoff
from skillgraph.runtime_types import OutcomeLabel


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Lo que un Adapter devuelve tras ejecutar un nodo."""

    outcome: OutcomeLabel
    """Etiqueta declarativa: para DecisionNode, una opcion del outcome
    declarado; para ActionNode, una transicion declarada."""

    result: dict[str, Any]
    """Payload arbitrario serializable. NO puede contener codigo
    ejecutable (UAT-14, UAT-15)."""

    evidence_ref: str | None = None
    """Identificador de la evidencia (e.g. handoff hash, archivo)."""

    @staticmethod
    def from_fixture(payload: dict[str, Any]) -> AgentResult:
        if not isinstance(payload, dict):
            raise ValidationError(
                f"resultado del agente debe ser dict, recibio {type(payload).__name__}"
            )
        if "outcome" not in payload or not isinstance(payload["outcome"], str):
            raise ValidationError("falta `outcome` (str) en resultado del agente")
        if "result" not in payload or not isinstance(payload["result"], dict):
            raise ValidationError("falta `result` (dict) en resultado del agente")
        outcome_raw = payload["outcome"]
        if not outcome_raw:
            raise OutcomeInvalidError("outcome vacio en fixture")
        result = payload["result"]
        evidence_ref = payload.get("evidence_ref")
        if evidence_ref is not None and not isinstance(evidence_ref, str):
            raise ValidationError("evidence_ref debe ser str o ausente")
        return AgentResult(outcome=outcome_raw, result=result, evidence_ref=evidence_ref)


class AgentAdapter(Protocol):
    """Contrato del adaptador. Implementaciones: Fake, HTTP, LLM."""

    def invoke(self, handoff: Handoff) -> AgentResult: ...


class FakeAgentAdapter:
    """Adapter determinista para tests y modo local.

    Busca fixtures en `<fixtures_root>/<tenant_id>/<project_id>/<node_id>.json`.
    El `node_id` por defecto es `HandoffIdentity.node_execution_id`, pero
    se puede sobrescribir por `behavior.definition_name` si el caller
    prefiere fixtures por nombre de brick.
    """

    def __init__(self, fixtures_root: Path) -> None:
        if fixtures_root is None:  # pragma: no cover
            raise ValidationError("fixtures_root requerido")
        self._root = Path(fixtures_root)

    def invoke(self, handoff: Handoff) -> AgentResult:
        candidates = [
            self._root
            / handoff.identity.tenant_id
            / handoff.identity.project_id
            / f"{handoff.identity.node_execution_id}.json",
            self._root
            / handoff.identity.tenant_id
            / handoff.identity.project_id
            / f"{handoff.behavior.definition_name}.json",
            self._root
            / handoff.behavior.definition_namespace
            / f"{handoff.behavior.definition_name}.json",
        ]
        for path in candidates:
            if path.is_file():
                return self._load(path, handoff)
        raise NotFoundError(
            f"fixture de agente no encontrada para "
            f"node_execution_id={handoff.identity.node_execution_id!r} "
            f"definition_name={handoff.behavior.definition_name!r} "
            f"en {self._root}"
        )

    def _load(self, path: Path, handoff: Handoff) -> AgentResult:
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"fixture invalida en {path}: {exc.msg}") from exc
        result = AgentResult.from_fixture(payload)
        # Verificar que el outcome es consistente con la declaracion.
        # El Fake NO improvisa outcomes: si el outcome es `selected` y el
        # nodo es una DecisionNode, debe estar en la lista de outcomes.
        # Si no, dejamos pasar (la validacion completa es del Controller).
        _ = handoff  # handoff disponible para checks futuros
        return result


class RecordingAdapter:
    """Adapter que envuelve a otro y registra invocaciones.

    Util para tests: ver que el controller llamo N veces con
    que handoffs. NO modifica el resultado del adaptador envuelto.
    """

    def __init__(self, inner: AgentAdapter) -> None:
        self._inner = inner
        self.calls: list[Handoff] = []

    def invoke(self, handoff: Handoff) -> AgentResult:
        self.calls.append(handoff)
        return self._inner.invoke(handoff)

    def __len__(self) -> int:
        return len(self.calls)
