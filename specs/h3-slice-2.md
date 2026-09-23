# Slice 2 — KnowledgeController (sin invalidación transitiva)

> Sub-spec del H3 (`specs/h3-knowledge.md`) y de Slice 1
> (`specs/h3-slice-1.md`). Define la clase de alto nivel que
> envuelve los métodos de Storage introducidos en Slice 1.
> NO se ejecuta antes de que el spec H3 esté firmado (D2, D3, D4)
> y Slice 1 implementado.
> Estado: **DISEÑO**.

## 1. Objetivo

Introducir `KnowledgeController` como API de alto nivel para las
operaciones de conocimiento. Encapsula los métodos de Storage del
Slice 1 (`register_source`, `record_claim`, etc.) y añade:

- **Validación previa** a cada llamada a Storage (tipos literales,
  formatos, no-vacíos).
- **Generación automática de IDs** (`SourceID`, `EntityID`, `ClaimID`,
  `EvidenceID`) usando UUIDv5 con un namespace estable por proyecto.
- **Logging estructurado** vía el sistema de EventLog de Etapa 2.
- **Manejo de errores tipado**: cada fallo devuelve `SkillGraphError`
  con código `sg_*`.

**Lo que este slice entrega:**
- `src/skillgraph/knowledge_controller.py` con la clase.
- 14 tests unitarios que cubren happy path + errores tipados.

**Lo que este slice NO entrega (queda en slices 3-5):**
- Invalidación transitiva (slice 4).
- Git fingerprinting real (slice 3).
- ContextController (slice 5).

## 2. Decisiones de diseño

### D9 — UUIDv5 para IDs derivados

```python
import uuid
NAMESPACE_KNOWLEDGE = uuid.UUID("...")  # constante de proyecto

def make_claim_id(*, subject_entity_id: EntityID, predicate: str,
                  source_id: SourceID, checked_at_revision: str) -> ClaimID:
    seed = f"{subject_entity_id}|{predicate}|{source_id}|{checked_at_revision}"
    return ClaimID(f"claim-{uuid.uuid5(NAMESPACE_KNOWLEDGE, seed)}")
```

**Motivo:** IDs reproducibles permiten idempotencia sin UNIQUE
adicional en Storage. La unicidad sigue garantizada por el UNIQUE
constraint de la tabla.

### D10 — KnowledgeController NO depende de Storage directamente

Recibe un `Storage` por inyección y una `tenant_id` + `project_id`
en su `__init__` (frozen dataclass). Esto permite:

- Mockear Storage en tests sin tocar SQLite.
- Reutilizar el mismo controller con distintas `(tenant, project)`.
- Testeo determinista con fixtures inyectados.

```python
@dataclass(frozen=True, slots=True)
class KnowledgeController:
    storage: Storage
    tenant_id: str
    project_id: str

    def register_source(self, *, source: Source) -> None: ...
    def record_claim(self, *, claim: Claim) -> ClaimID: ...
```

### D11 — Validación previa con excepciones específicas

Cada método público:

1. Valida inputs (`__post_init__` en ADT + chequeos aquí si son
   parámetros sueltos).
2. Llama al método Storage.
3. Si Storage lanza `IdempotencyError`, el controller lo registra
   como warning y devuelve el ID existente (idempotencia
   transparente para el caller).
4. Otros errores de Storage se propagan sin envolver.

### D12 — NO se importa `dulwich` aquí

Slice 2 NO toca Git fingerprinting. Las sources `git_commit` y
`git_tree` se pueden registrar a mano (con `git_commit_sha` y
`git_tree_sha` rellenados por el caller), pero el controller no
las inspecciona. Eso es Slice 3.

## 3. API pública

```python
class KnowledgeController:
    """API de alto nivel para Source/Entity/Claim/Evidence."""

    # Sources
    def register_source(self, *, source: Source) -> SourceID
    def get_source(self, *, source_id: SourceID) -> Source | None
    def mark_source_stale(self, *, source_id: SourceID) -> None
    def mark_source_fresh(self, *, source_id: SourceID) -> None

    # Entities
    def upsert_entity(self, *, entity: Entity) -> EntityID
    def get_entity(self, *, entity_id: EntityID) -> Entity | None
    def find_entity(self, *, kind: str, stable_key: str) -> Entity | None

    # Evidences
    def record_evidence(self, *, evidence: Evidence) -> EvidenceID
    def get_evidences_for_claim(self, *, claim_id: ClaimID) -> tuple[Evidence, ...]

    # Claims
    def record_claim(self, *, claim: Claim) -> ClaimID
    def get_claim(self, *, claim_id: ClaimID) -> Claim | None
    def list_claims_for_source(self, *, source_id: SourceID) -> list[Claim]
    def list_claims_for_subject(self, *, subject_entity_id: EntityID) -> list[Claim]

    # Findings
    def record_finding(self, *, finding: Finding) -> FindingID

    # Outcome traces
    def record_trace(self, *, trace: OutcomeTrace) -> TraceID
    def link_trace(self, *, trace_id: TraceID, link_kind: str, link_id: str, position: int) -> None
```

## 4. Errores nuevos

Slice 2 añade:

```python
class UnknownSourceError(SkillGraphError):           code = "sg_unknown_source"
class UnknownEntityError(SkillGraphError):           code = "sg_unknown_entity"
class UnknownClaimError(SkillGraphError):            code = "sg_unknown_claim"
class StaleKnowledgeWarning(SkillGraphWarning):      code = "sg_stale_knowledge"
```

`SkillGraphWarning` es una clase base nueva en `errors.py` para
warnings no fatales. NO rompe el flujo; el caller decide qué hacer
(log, abortar, continuar).

## 5. Tests (`tests/test_knowledge_controller.py`)

**14 tests propuestos:**

### Happy path (5)
1. `test_register_and_get_source_roundtrip` — Source→record→get OK.
2. `test_upsert_entity_returns_existing_id` — idempotente.
3. `test_record_claim_returns_generated_id` — ClaimID con formato `claim-{uuid5}`.
4. `test_find_entity_by_kind_and_key` — búsqueda sin saber entity_id.
5. `test_record_trace_with_links_preserves_order` — list_links ordenado.

### Errores tipados (5)
6. `test_register_invalid_source_raises_invalid_source_error` — Source con
   `content_hash=""` falla en `__post_init__`.
7. `test_get_unknown_source_raises` — `UnknownSourceError`.
8. `test_record_claim_for_unknown_entity_raises` — FK violation → `UnknownEntityError`.
9. `test_record_evidence_for_unknown_source_raises` — FK violation → `UnknownSourceError`.
10. `test_get_unknown_claim_raises` — `UnknownClaimError`.

### Idempotencia (2)
11. `test_register_source_idempotent` — mismo source_id dos veces,
    el segundo no crea duplicado.
12. `test_record_claim_idempotent_on_full_tuple` — mismo
    (subject, predicate, source, revision) → mismo ClaimID.

### Inyección (2)
13. `test_controller_uses_injected_storage` — Storage fake (no SQLite)
    recibe las llamadas correctas.
14. `test_controller_isolates_tenants` — dos `KnowledgeController`
    con distinto `tenant_id` no se ven entre sí.

## 6. Criterios de aceptación

Slice 2 completado cuando:
1. 14 tests verdes (`bash scripts/ci.sh` → 161+14 = **175 passed**).
2. `ruff format` + `ruff check` verde.
3. `KnowledgeController` NO importa `dulwich` ni `pygit2`.
4. Cada método público tiene tests para happy path Y error path.
5. Commit: `feat(h3-s2): KnowledgeController de alto nivel (sin transitiva)`.

## 7. Out of scope

- **Invalidación transitiva** (`invalidate_from_source`): NO se
  implementa aquí. El campo `stale` ya existe en la tabla pero
  ningún método lo propaga. Eso es Slice 4.
- **Git fingerprinting**: el controller acepta `Source(kind="git_commit")`
  con `git_commit_sha` rellenado por el caller, pero NO inspecciona
  el repo. Eso es Slice 3.
- **ContextController / OutcomeTracer**: slice 5.

## 8. Riesgos

### R4 — UUIDv5 con semilla larga

`uuid.uuid5(namespace, seed)` con seed > 256 bytes puede ser lento.
Nuestras semillas son ~100 chars → OK. Pero si en el futuro se
incluyen paths muy largos en la semilla, revisar.

### R5 — Tenant isolation requiere UNIQUE constraints correctos

Si el UNIQUE en `claims` no incluye `tenant_id`, dos proyectos
distintos podrían chocar en `checked_at_revision`. Slice 1 ya
lo incluye en los UNIQUE que importan. Slice 2 NO toca schema.

## 9. Referencias

- Spec padre: `specs/h3-knowledge.md` §2.3.
- Slice 1: `specs/h3-slice-1.md` (define Storage que Slice 2 envuelve).
- ADR-0011: controladores.
