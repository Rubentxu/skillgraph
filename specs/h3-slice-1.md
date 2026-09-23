# Slice 1 — Knowledge ADT + Storage delta

> Sub-spec del H3 (`specs/h3-knowledge.md`). Define Slice 1 con
> detalle de contratos, schema SQL y tests. NO se ejecuta antes
> de que el spec H3 esté firmado (D2, D3, D4).
> Estado: **DISEÑO**, listo para implementar tras firma.

## 1. Objetivo

Introducir las entidades de **conocimiento** (Source, Entity, Claim,
Evidence, Finding, OutcomeTrace) como ADT frozen + tipos literales
centralizados, y añadir las tablas SQL mínimas para persistirlas.

**Lo que este slice entrega:**
- Modelo de datos verificable (los Claims pueden ser revisados contra
  sus Evidences).
- Storage idempotente para alta/baja/modificación de cada entidad.
- Tests unitarios que cubren: schema migration idempotente,
  idempotencia de upsert, UNIQUE constraints, y propiedades
  inmutabilidad del ADT.

**Lo que este slice NO entrega (queda en slices 2-5):**
- Invalidación transitiva (slice 4).
- Compilación de Handoff con ContextRecipe (slice 5).
- Git fingerprinting real (slice 3) — aquí solo los tipos y el
  esqueleto de `GitSource` para que el modelo esté completo.

## 2. Decisiones de diseño tomadas en este slice

### D5 — Inmutabilidad por hash de contenido

Las Evidences son **inmutables**: si el contenido cambia, se crea
una Evidence nueva con `evidence_id` distinto (UUIDv5 sobre
`source_id + content_hash` o UUIDv4 si no se deriva nada estable).

Las Claims **no son inmutables** en su forma: el mismo
`(subject_entity_id, predicate, source_id)` puede re-registrarse
con un `checked_at_revision` distinto. La unicidad es por
`(subject, predicate, source, checked_at_revision)`.

Esto preserva trazabilidad: las Claims antiguas quedan como
histórico; las nuevas reemplazan a las anteriores por
`MAX(checked_at_revision)`.

### D6 — Tipos literales centralizados

Todos los Literal types se añaden a `runtime_types.py` (extensión
del módulo que ya existe con `NodeKind`, `RunState`, `NodeState`):

```python
# Source kinds (incluye Git para slice 3)
SourceKind = Literal["git_commit", "git_tree", "local_file", "external_doc"]

# Freshness de Source
FreshnessState = Literal["fresh", "stale", "archived"]

# Claim predicates iniciales (H3 cubre estos; otros vendrán en H5 con Domain Packs)
ClaimPredicate = Literal[
    "line_count",         # int (LOC)
    "function_count",     # int
    "imports_module",     # module name (str)
    "defines_symbol",     # qualified name (str)
    "test_passes",        # bool
    "file_exists",        # bool
    "spec_revision",      # int
]

# Finding results
FindingResult = Literal["pass", "fail", "inconclusive"]

# Outcome trace kinds
TraceKind = Literal["SoftwareExecutionSlice"]  # extensible en H5

# Finding rule refs (extensible; H3 incluye reglas de software)
RuleRef = Literal["max_lines_per_function", "max_complexity", "naming_convention"]
```

### D7 — Naming consistente con Etapa 2

- IDs como `NewType` (`SourceID`, `EntityID`, `ClaimID`, `EvidenceID`,
  `FindingID`, `TraceID`).
- Smart constructors que validan no-vacío y formato (`SourceID("git:abc:src.py")`,
  `EntityID("file:src/foo.py")`).
- Excepciones específicas: `InvalidSourceIDError`, `InvalidEntityIDError`,
  añadidas a `errors.py`.

### D8 — Storage como add-only en tablas nuevas

NO se modifican tablas existentes (`resources`, `relations`,
`workflow_runs`, `node_executions`, `run_events`). Las 7 tablas
nuevas se crean con `CREATE TABLE IF NOT EXISTS` en
`Storage._migrate()`. Idempotente y seguro.

## 3. ADT en `src/skillgraph/knowledge.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NewType, Literal, NamedTuple

from skillgraph.runtime_types import (
    SourceKind, FreshnessState, ClaimPredicate, FindingResult,
    TraceKind, RuleRef,
)

SourceID = NewType("SourceID", str)
EntityID = NewType("EntityID", str)
ClaimID = NewType("ClaimID", str)
EvidenceID = NewType("EvidenceID", str)
FindingID = NewType("FindingID", str)
TraceID = NewType("TraceID", str)


# Smart constructors
def source_id(raw: str) -> SourceID:
    if not raw or not raw.strip():
        raise InvalidSourceIDError("source_id no puede estar vacío")
    return SourceID(raw.strip())

def entity_id(raw: str) -> EntityID:
    if not raw or ":" not in raw:
        raise InvalidEntityIDError(
            f"entity_id debe tener formato 'kind:key' (recibido {raw!r})"
        )
    return EntityID(raw)


@dataclass(frozen=True, slots=True)
class Source:
    source_id: SourceID
    kind: SourceKind
    content_hash: str
    locator: dict[str, Any]          # paths, urls, etc.; JSON estable
    git_commit_sha: str | None
    git_tree_sha: str | None
    working_tree_status: dict[str, Any] | None
    checked_at: str                 # ISO-8601 UTC
    freshness: FreshnessState

    def __post_init__(self) -> None:
        if not self.content_hash:
            raise InvalidSourceError("content_hash no puede estar vacío")
        if self.kind.startswith("git_") and not self.git_commit_sha:
            raise InvalidSourceError(
                f"Source {self.source_id!r} kind={self.kind} requiere git_commit_sha"
            )


@dataclass(frozen=True, slots=True)
class Entity:
    entity_id: EntityID
    kind: str                       # "file", "function", "module", "contract", ...
    stable_key: str                 # path relativo o qualified name


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: EvidenceID
    kind: str                       # "metric", "snippet", "log_line", "commit_message"
    content: dict[str, Any] | str
    source_id: SourceID
    observed_at: str                # ISO-8601 o commit SHA


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: ClaimID
    subject_entity_id: EntityID
    predicate: ClaimPredicate
    object_literal: Any             # int, str, bool; depende del predicate
    source_id: SourceID
    evidence_ids: tuple[EvidenceID, ...] = field(default_factory=tuple)
    extraction_method: str          # "static_analysis", "git_log", "manual"
    extractor_version: str          # "skillgraph/0.1.0"
    checked_at_revision: str        # commit SHA, ISO timestamp, o version semver
    stale: bool = False


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: FindingID
    entity_id: EntityID
    observation: str                # human-readable
    rule_ref: RuleRef
    rule_version: str               # "skillgraph-rules/0.1.0"
    evidence_ids: tuple[EvidenceID, ...]
    result: FindingResult
    valid_until_revision: str | None


@dataclass(frozen=True, slots=True)
class OutcomeTrace:
    trace_id: TraceID
    kind: TraceKind
    name: str
    project_id: str
    created_at: str
    # NO duplica contenido; solo referencias (ver blueprint §9)
    claim_refs: tuple[ClaimID, ...] = field(default_factory=tuple)
    evidence_refs: tuple[EvidenceID, ...] = field(default_factory=tuple)
```

## 4. Schema SQLite (en `storage.py`)

```sql
CREATE TABLE IF NOT EXISTS sources (
    source_id        TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    locator_json     TEXT NOT NULL,
    git_commit_sha   TEXT,
    git_tree_sha     TEXT,
    working_tree_status_json TEXT,
    checked_at       TEXT NOT NULL,
    freshness        TEXT NOT NULL DEFAULT 'fresh'
);
CREATE INDEX IF NOT EXISTS idx_sources_project
    ON sources(tenant_id, project_id);

CREATE TABLE IF NOT EXISTS entities (
    entity_id        TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    stable_key       TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, kind, stable_key)
);

CREATE TABLE IF NOT EXISTS evidences (
    evidence_id      TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    content_json     TEXT NOT NULL,
    source_id        TEXT NOT NULL REFERENCES sources(source_id),
    observed_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id              TEXT PRIMARY KEY,
    tenant_id             TEXT NOT NULL,
    project_id            TEXT NOT NULL,
    subject_entity_id     TEXT NOT NULL REFERENCES entities(entity_id),
    predicate             TEXT NOT NULL,
    object_literal_json   TEXT NOT NULL,
    source_id             TEXT NOT NULL REFERENCES sources(source_id),
    extraction_method     TEXT NOT NULL,
    extractor_version     TEXT NOT NULL,
    checked_at_revision   TEXT NOT NULL,
    stale                 INTEGER NOT NULL DEFAULT 0,
    UNIQUE (subject_entity_id, predicate, source_id, checked_at_revision)
);
CREATE INDEX IF NOT EXISTS idx_claims_subject
    ON claims(subject_entity_id, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_stale
    ON claims(stale) WHERE stale = 1;

CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id      TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_id   TEXT NOT NULL REFERENCES evidences(evidence_id),
    PRIMARY KEY (claim_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id          TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    entity_id           TEXT NOT NULL REFERENCES entities(entity_id),
    observation         TEXT NOT NULL,
    rule_ref            TEXT NOT NULL,
    rule_version        TEXT NOT NULL,
    evidence_ids_json   TEXT NOT NULL,
    result              TEXT NOT NULL,
    valid_until_revision TEXT
);

CREATE TABLE IF NOT EXISTS outcome_traces (
    trace_id      TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    project_id    TEXT NOT NULL,
    kind          TEXT NOT NULL,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcome_trace_links (
    trace_id      TEXT NOT NULL REFERENCES outcome_traces(trace_id),
    link_kind     TEXT NOT NULL CHECK (link_kind IN ('claim','evidence','relation')),
    link_id       TEXT NOT NULL,
    position      INTEGER NOT NULL,
    PRIMARY KEY (trace_id, link_kind, link_id)
);
```

**Notas sobre el schema:**
- `claim_evidence` es N:M (un Claim se sostiene en varias Evidences; una
  Evidence puede sustentar varios Claims).
- `outcome_trace_links.position` permite ordenar el recorrido.
- `stale` indexado parcialmente para invalidación rápida (slice 4).
- Todas las tablas tienen `(tenant_id, project_id)` para aislamiento
  per-proyecto.

## 5. Métodos nuevos en `Storage`

```python
# Sources
def register_source(self, *, tenant_id, project_id, source: Source) -> None
def get_source(self, *, tenant_id, project_id, source_id: SourceID) -> Source | None
def update_source_freshness(self, *, tenant_id, project_id, source_id, freshness) -> None

# Entities
def upsert_entity(self, *, tenant_id, project_id, entity: Entity) -> None
def get_entity(self, *, tenant_id, project_id, entity_id: EntityID) -> Entity | None

# Evidences
def record_evidence(self, *, tenant_id, project_id, evidence: Evidence) -> None
def get_evidences_for_claim(self, *, tenant_id, project_id, claim_id: ClaimID) -> tuple[Evidence, ...]

# Claims
def record_claim(self, *, tenant_id, project_id, claim: Claim) -> ClaimID
def get_claim(self, *, tenant_id, project_id, claim_id: ClaimID) -> Claim | None
def list_claims_for_source(self, *, tenant_id, project_id, source_id: SourceID) -> list[Claim]
def attach_evidence_to_claim(self, *, tenant_id, project_id, claim_id, evidence_id) -> None

# Findings
def record_finding(self, *, tenant_id, project_id, finding: Finding) -> None

# Outcome traces
def record_trace(self, *, tenant_id, project_id, trace: OutcomeTrace) -> None
def link_trace(self, *, tenant_id, project_id, trace_id, link_kind, link_id, position) -> None
```

Cada método:
- Idempotente donde tiene sentido (`upsert_entity`, `record_trace`,
  `attach_evidence_to_claim`).
- Lanza `IdempotencyError` en colisiones reales (no en re-registros
  con misma clave).
- Lanza `NotFoundError` si FK falla.
- Acepta y devuelve los ADT frozen, no dicts (consistencia con
  `upsert_resource` que sí acepta `Brick`).

## 6. Errores nuevos en `errors.py`

```python
class InvalidSourceIDError(SkillGraphError):     code = "sg_invalid_source_id"
class InvalidEntityIDError(SkillGraphError):     code = "sg_invalid_entity_id"
class InvalidSourceError(SkillGraphError):       code = "sg_invalid_source"
class UnknownClaimPredicateError(SkillGraphError): code = "sg_unknown_predicate"
```

## 7. Tests (`tests/test_knowledge_storage.py`)

**17 tests propuestos**, agrupados:

### Schema (4)
1. `test_migrate_is_idempotent` — llamar `_migrate()` 5 veces seguidas
   no rompe nada, no duplica índices.
2. `test_migrate_creates_all_seven_tables` — verifica que las 7 tablas
   existen post-migrate.
3. `test_migrate_does_not_touch_existing_tables` — `resources`,
   `relations`, `workflow_runs`, etc., siguen con su schema original.
4. `test_indexes_exist_for_stale_and_subject` — verifica índices
   `idx_claims_stale` y `idx_claims_subject`.

### Sources (3)
5. `test_register_and_get_source_roundtrip` — roundtrip Source→row→Source.
6. `test_register_source_rejects_invalid_kind` — Literal check.
7. `test_register_git_source_requires_commit_sha` — `Source(git_commit)`
   sin SHA lanza `InvalidSourceError`.

### Entities (2)
8. `test_upsert_entity_is_idempotent` — misma clave → mismo `entity_id`.
9. `test_upsert_entity_different_kind_same_key` — `file:foo.py` y
   `module:foo.py` son entities distintas (UNIQUE sobre kind+key).

### Claims (4)
10. `test_record_claim_returns_claim_id` — básico.
11. `test_record_claim_idempotent_on_revision` — misma
    (subject, predicate, source, checked_at_revision) → UNIQUE OK.
12. `test_record_claim_with_different_revision_creates_new` — nueva
    revision = nueva Claim, la vieja queda como histórico.
13. `test_attach_evidence_to_claim_roundtrip` — N:M funciona.

### Evidence + Finding (2)
14. `test_record_evidence_with_invalid_source_raises` — FK falla.
15. `test_record_finding_stores_evidence_ids_as_json` — la lista
    serializada se recupera igual.

### Trace (1)
16. `test_record_trace_with_links_preserves_order` — `position`
    mantiene el orden del OutcomeTrace.

### Inmutabilidad ADT (1)
17. `test_dataclass_frozen_slots_raises_on_mutation` — `Claim.foo = 1`
    lanza `FrozenInstanceError`. `__slots__` previene atributos
    nuevos.

## 8. Criterios de aceptación del slice

El slice se considera **completado** cuando:

1. Los 17 tests de §7 pasan (`bash scripts/ci.sh` → `161 passed` → `178 passed`).
2. `ruff format` y `ruff check` verde.
3. `Storage._migrate()` es idempotente (cubierto por test 1).
4. Las 7 tablas NO interfieren con las tablas existentes
   (cubierto por test 3).
5. Los ADT son `frozen=True, slots=True` (cubierto por test 17).
6. Commit separado con mensaje:
   `feat(h3-s1): Knowledge ADT + Storage delta (H3 Slice 1)`.

## 9. Out of scope de este slice

- **Invalidación transitiva**: el campo `stale` existe y se puede
  actualizar manualmente, pero NO hay algoritmo que lo propague.
  Eso es slice 4.
- **`KnowledgeController`**: NO se crea la clase todavía. Los métodos
  de Storage son la API de bajo nivel. La clase de alto nivel
  (con `register_source`, `record_claim`, etc.) llega en slice 2.
- **Git fingerprinting**: `Source(kind="git_commit", ...)` se puede
  registrar, pero `GitSource.from_commit` no existe todavía. Eso
  es slice 3.
- **ContextRecipe / ContextController / OutcomeTracer**: slice 5.

## 10. Riesgos identificados

### R1 — Cardinalidad del `stale` index parcial

SQLite soporta índices parciales (`WHERE stale = 1`) desde 3.8.
Python 3.13 usa SQLite 3.45+ → OK.

### R2 — JSON storage de `object_literal` y `content`

`object_literal_json` y `content_json` se almacenan como TEXT.
El tipo Python se reconstruye con `json.loads`. Costo: parse en cada
read. Para H3 esto es aceptable (decenas, no millones de Claims).
Si R3 lo justifica, se considera una columna tipada por predicate.

### R3 — Crecimiento del catálogo de Claims

Una Claim por `(subject, predicate, source, checked_at_revision)`.
Si un proyecto hace 100 commits por día sobre 1000 entidades con
5 predicates cada una → 500k Claims/día. Inaceptable para SQLite
sin partition.

**Decisión consciente para H3:** limitar el alcance a proyectos
pequeños (<10k Claims). H4+ introduce particionado por
`checked_at_revision` (mantener solo N revisiones, archivar el resto).

## 11. Referencias

- Spec padre: `specs/h3-knowledge.md` §2, §3.
- ADR-0007: knowledge vinculado a fuentes (procedencia).
- ADR-0011: controladores (este slice NO añade Controller todavía).
- Blueprint §8 (conocimiento), §5 (Git fingerprinting básico).
