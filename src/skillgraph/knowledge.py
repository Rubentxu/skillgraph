"""Modelo de conocimiento H3 (Slice 1).

Doc externo:
  external/blueprint-v1/docs/08-conocimiento-y-contexto.md
  external/blueprint-v1/adr/ADR-0007-conocimiento-vinculado-a-fuentes.md

Este modulo define los ADT **inmutables** que representan las entidades
del subsistema de conocimiento:

- `Source`      Una unidad de contenido identificable (commit, archivo, doc).
- `Entity`      Algo sobre lo que se afirma (file, function, module, ...).
- `Evidence`    Un dato observable extraido de una Source.
- `Claim`       Una afirmacion sobre una Entity, sostenida por Evidences.
- `Finding`     Resultado de aplicar una regla a una Entity.
- `OutcomeTrace` Un recorrido verificable que enlaza Claims y Evidences.

Por que frozen + slots:
- `frozen=True`  garantiza que una vez emitido un Claim, su contenido
  no cambia. Es la base de la trazabilidad.
- `slots=True`   elimina `__dict__` y rechaza atributos no declarados;
  detecta typos en tests antes de que se propaguen a SQL.

Por que smart constructors:
- `SourceID("")` debe fallar rapido, no propagar una ID vacia hasta el
  momento del INSERT.
- `EntityID("foo.py")` sin prefijo `kind:` es ambiguo en el catalogo;
  lo rechazamos al cruzar el limite del modulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NewType

from skillgraph.errors import (
    InvalidEntityIDError,
    InvalidSourceError,
    InvalidSourceIDError,
    UnknownClaimPredicateError,
)
from skillgraph.runtime_types import (
    CLAIM_PREDICATES,
    ClaimPredicate,
    FindingResult,
    FreshnessState,
    RuleRef,
    SourceKind,
    TraceKind,
)

# --- Identificadores nominales (NewType sobre str) -----------------------
#
# NewType no afecta runtime (siguen siendo str), pero el type-checker
# trata `SourceID` y `EntityID` como tipos incompatibles. Asi, pasar un
# `EntityID` donde se espera `SourceID` falla en `mypy` sin afectar
# serializacion JSON ni queries SQL.

SourceID = NewType("SourceID", str)
"""Identificador unico de una Source. Formato libre, no vacio."""

EntityID = NewType("EntityID", str)
"""Identificador unico de una Entity. Formato obligatorio `kind:key`."""

ClaimID = NewType("ClaimID", str)
"""Identificador unico de una Claim (UUIDv5 derivado del contenido)."""

EvidenceID = NewType("EvidenceID", str)
"""Identificador unico de una Evidence (UUIDv5 sobre source_id+content)."""

FindingID = NewType("FindingID", str)
"""Identificador unico de un Finding."""

TraceID = NewType("TraceID", str)
"""Identificador unico de un OutcomeTrace."""


# --- Smart constructors ---------------------------------------------------
#
# Validan los invariantes de formato en el limite del modulo, NO dentro
# de Storage. Asi, si alguien crea un `Source` con un ID vacio pero no
# lo persiste, el error ya esta capturado.


def source_id(raw: str) -> SourceID:
    """Smart constructor para SourceID: rechaza vacios."""
    if not raw or not raw.strip():
        raise InvalidSourceIDError("source_id no puede estar vacio")
    return SourceID(raw.strip())


def entity_id(raw: str) -> EntityID:
    """Smart constructor para EntityID: exige formato `kind:key`."""
    if not raw or ":" not in raw:
        raise InvalidEntityIDError(f"entity_id debe tener formato 'kind:key' (recibido {raw!r})")
    return EntityID(raw)


# --- ADT inmutables -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Source:
    """Una unidad de contenido de la que se extrae evidencia.

    El `content_hash` identifica el contenido (e.g. SHA-256 para un
    commit Git, sha256 de bytes para un archivo, URL+timestamp para
    external_doc). Si el contenido cambia, se crea una Source nueva
    con `source_id` distinto.

    Invariantes (validados en `__post_init__`):
    - `content_hash` no vacio.
    - Si `kind` empieza por `git_`, entonces `git_commit_sha` obligatorio.
    """

    source_id: SourceID
    kind: SourceKind
    content_hash: str
    locator: dict[str, Any]
    git_commit_sha: str | None
    git_tree_sha: str | None
    working_tree_status: dict[str, Any] | None
    checked_at: str  # ISO-8601 UTC
    freshness: FreshnessState

    def __post_init__(self) -> None:
        if not self.content_hash:
            raise InvalidSourceError("content_hash no puede estar vacio")
        if self.kind.startswith("git_") and not self.git_commit_sha:
            raise InvalidSourceError(
                f"Source {self.source_id!r} kind={self.kind} requiere git_commit_sha"
            )


@dataclass(frozen=True, slots=True)
class Entity:
    """Algo sobre lo que se afirma algo (Claim) o se aplica una regla (Finding).

    `kind` describe el tipo (file, function, module, contract, ...).
    `stable_key` es un identificador estable (path relativo o qualified name).
    """

    entity_id: EntityID
    kind: str
    stable_key: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """Un dato observable extraido de una Source.

    `content` puede ser `dict[str, Any]` (e.g. metricas) o `str`
    (e.g. snippet de codigo). La serializacion a SQL lo trata siempre
    como JSON.
    """

    evidence_id: EvidenceID
    kind: str  # "metric" | "snippet" | "log_line" | "commit_message"
    content: dict[str, Any] | str
    source_id: SourceID
    observed_at: str  # ISO-8601 o commit SHA


@dataclass(frozen=True, slots=True)
class Claim:
    """Afirmacion verificable sobre una Entity, sostenida por Evidences.

    La unicidad en BD es por
    `(subject_entity_id, predicate, source_id, checked_at_revision)`,
    asi que el mismo Claim se puede re-registrar bajo una nueva
    `checked_at_revision` para representar la evolucion historica.
    """

    claim_id: ClaimID
    subject_entity_id: EntityID
    predicate: ClaimPredicate
    object_literal: Any  # int | str | bool; depende del predicate
    source_id: SourceID
    evidence_ids: tuple[EvidenceID, ...] = field(default_factory=tuple)
    extraction_method: str = "static_analysis"
    extractor_version: str = "skillgraph/0.1.0"
    checked_at_revision: str = ""
    stale: bool = False

    def __post_init__(self) -> None:
        if self.predicate not in CLAIM_PREDICATES:
            raise UnknownClaimPredicateError(
                f"predicate {self.predicate!r} no registrado en CLAIM_PREDICATES"
            )


@dataclass(frozen=True, slots=True)
class Finding:
    """Resultado de aplicar una regla a una Entity.

    `valid_until_revision` opcional: si el siguiente commit invalida
    la regla, el Finding queda como `inconclusive` por diseno del
    KnowledgeController (slice 2).
    """

    finding_id: FindingID
    entity_id: EntityID
    observation: str
    rule_ref: RuleRef
    rule_version: str
    evidence_ids: tuple[EvidenceID, ...]
    result: FindingResult
    valid_until_revision: str | None


@dataclass(frozen=True, slots=True)
class OutcomeTrace:
    """Recorrido verificable: enlaza Claims y Evidences en orden.

    Por diseno NO duplica contenido: solo almacena referencias (ver
    blueprint §9). El lector (humano o agente) reconstruye el contenido
    desde los IDs via Storage.
    """

    trace_id: TraceID
    kind: TraceKind
    name: str
    project_id: str
    created_at: str
    claim_refs: tuple[ClaimID, ...] = field(default_factory=tuple)
    evidence_refs: tuple[EvidenceID, ...] = field(default_factory=tuple)


__all__ = [
    "Claim",
    "ClaimID",
    "Entity",
    "EntityID",
    "Evidence",
    "EvidenceID",
    "Finding",
    "FindingID",
    "OutcomeTrace",
    "Source",
    "SourceID",
    "TraceID",
    "entity_id",
    "source_id",
]
