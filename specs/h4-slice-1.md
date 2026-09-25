# Spec H4 Slice 1 — Expansion controlada: ADT + validación

> Status: **DRAFT** (firmada en este turno, 2026-09-23).
> Hito: H4 Expansion controlada (Etapa 4 del ROADMAP).
> Cierra: UAT-08 (autorizada) + UAT-09 (rechazada).

## 1. Principio rector (blueprint §5 §5-§6 literal)

Una ampliación incorpora **únicamente el cambio solicitado**, declarando
sus 9 campos obligatorios, validada contra las 6 invariantes del blueprint,
y autorizada de forma explícita antes de aplicarse. **Nunca** modifica
resultados históricos ni instancias activas en silencio.

Pipeline legal:
```
DISCOVER -> PROPOSE -> VALIDATE -> AUTHORIZE -> APPLY -> EXECUTE -> EVALUATE
```

## 2. ADT (módulo nuevo `src/skillgraph/graph_expansion.py`)

### 2.1. Propuesta (GraphExpansion)

```python
@dataclass(frozen=True, slots=True)
class GraphExpansionProposal:
    proposal_id: ProposalID  # uuid5 estable
    base_revision: str  # revision sobre la que se aplica
    problem_observed: str
    evidence: tuple[EvidenceRef, ...]  # (claim_id|evidence_id|relation_id)
    operations: tuple[PatchOp, ...]  # ops minimas solicitadas
    new_dependencies: tuple[str, ...]  # refs obligatorias
    capabilities_needed: tuple[str, ...]
    scope: Scope = Scope.NODE  # NODE | TRANSITION | SUBGRAPH
    attachment_point: str  # nombre del nodo
    rollback_plan: tuple[PatchOp, ...]  # ops inversas para reversibilidad
    authorization: Authorization  # tipo + cuando
    created_at: str  # ISO-8601 UTC
    author: str  # quien lo propuso
```

Los 9 campos obligatorios del blueprint §5 §5 + 2 nuestros para
trazabilidad (id, created_at, author).

### 2.2. Operaciones (PatchOp)

```python
@dataclass(frozen=True, slots=True)
class AddNode:
    node: WorkflowNode


@dataclass(frozen=True, slots=True)
class AddTransition:
    transition: WorkflowTransition


@dataclass(frozen=True, slots=True)
class RemoveTransition:
    from_node: str
    outcome: str


PatchOp = AddNode | AddTransition | RemoveTransition
```

**Decisión**: NO permitimos `RemoveNode` en este slice. Las invariantes
§6 "No reescribir resultados históricos" + "No alterar una instancia
activa silenciosamente" hacen que eliminar un nodo completado sea
ilegal sin migración. Para eso se usa `archived`.

### 2.3. Autorización

```python
@dataclass(frozen=True, slots=True)
class Authorization:
    mode: Literal["manual_signed", "policy_approved", "auto_low_risk"]
    granted_by: str | None
    granted_at: str | None  # ISO-8601 UTC

    def is_valid(self) -> bool:
        # manual_signed requires granted_by and granted_at
        # policy_approved requires granted_at
        # auto_low_risk only for op sets marcados LOW_RISK
```

### 2.4. Validación (validators)

Cada invariante de blueprint §6 tiene un validador independiente:

- `validate_no_rewrite_historical(proposal, completed_nodes)`: rechaza
  si una op elimina/modifica nodos completados.
- `validate_no_silent_active_change(proposal, active_nodes)`: rechaza
  si una op altera transiciones usadas por instancias activas.
- `validate_no_unauthorized_capabilities(proposal, registry)`: rechaza
  si `capabilities_needed` no estan registradas.
- `validate_no_inexistent_refs(proposal, registry)`: rechaza si
  `new_dependencies` referencian refs que no existen.
- `validate_no_cycles(proposal, plan)`: BFS para detectar nuevos ciclos.
  Si los hay, deben incluir `max_visits` (cubierto por slice-1 de H4).
- `validate_no_obsolete_base(proposal, current_rev)`: rechaza si
  `base_revision` != current.

### 2.5. Resultado de validación

```python
@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    reason: str  # "" si accepted
    violated_invariants: tuple[str, ...]  # codigos I1..I7 (blueprint §6 literal)
    warnings: tuple[str, ...]
```

### 2.6. Application (APPLY)

`apply_expansion(proposal, plan) -> Result[WorkflowPlan, InvalidProposal]`:

- Recompone un nuevo `WorkflowPlan` con los parches aplicados.
- NO muta el plan original.
- Devuelve `Err(InvalidProposal)` si la validación falla.

`InvalidProposal` lleva `reason` + `violated_invariants`.

### 2.7. Rechazo y evidencia

Si la propuesta es rechazada (autorizacion invalida o invariante rota),
se registra en un `PendingProposal` con `status="rejected"`,
`rejected_at`, `reason`. **UAT-09 exige evidencia de rechazo.**

## 3. Errores nuevos

```python
class InvalidExpansionError(SkillGraphError):
    """Una propuesta de expansion viola una invariante del blueprint §6."""


class UnauthorizedExpansionError(SkillGraphError):
    """Expansion sin autorizacion explicita valida."""


class ExpansionOnObsoleteRevisionError(SkillGraphError):
    """La base_revision declarada no coincide con la revision actual del plan."""
```

## 4. Storage delta (NO en este slice; diferido a slice 2)

- Tabla `expansion_proposals` con campos del dataclass.
- Tabla `expansion_rejections` para evidencia de UAT-09.

Por ahora, las propuestas se persisten como archivos
`{data_root}/tenants/default/projects/<p>/expansion_proposals/<id>.json`
(simple, sin migracion storage.py). El slice-2 lo normaliza.

## 5. API pública módulo `graph_expansion`

```python
def propose(
    *,
    base_revision: str,
    problem_observed: str,
    evidence: tuple[EvidenceRef, ...],
    operations: tuple[PatchOp, ...],
    new_dependencies: tuple[str, ...] = (),
    capabilities_needed: tuple[str, ...] = (),
    scope: Scope = Scope.NODE,
    attachment_point: str,
    rollback_plan: tuple[PatchOp, ...] = (),
    authorization: Authorization,
    author: str,
) -> GraphExpansionProposal: ...


def validate(
    proposal: GraphExpansionProposal,
    *,
    plan: WorkflowPlan,
    registry: BrickRegistry,
    completed_nodes: frozenset[str] = frozenset(),
    active_nodes: frozenset[str] = frozenset(),
) -> ValidationResult: ...


def apply_expansion(
    proposal: GraphExpansionProposal,
    plan: WorkflowPlan,
    *,
    registry: BrickRegistry,
    completed_nodes: frozenset[str] = frozenset(),
    active_nodes: frozenset[str] = frozenset(),
) -> Result[WorkflowPlan, InvalidProposal]: ...


def record_rejection(
    proposal: GraphExpansionProposal, reason: str
) -> None: ...  # JSON en expansion_rejections/
```

## 6. Tests propuestos (12 tests, ~150 LoC)

> Nota sobre numeracion I1..I6: la **fuente de verdad** es
> `external/blueprint-v1/05-workflows-y-ciclo-de-vida.md` §6
> "Invariantes de expansion" (7 invariantes). El codigo
> (`graph_expansion.py`) usa la numeracion literal del blueprint
> (I1..I6 implementados; I7 = "no promover cambios locales a
> definiciones compartidas" documentado pero NO implementado en
> slice-1, queda para slice-3 policy engine P4 forbidden_ops).

1. `test_proposal_requires_all_9_fields`: propuesta sin un campo -> error.
2. `test_authorize_manual_signed_requires_grantor_and_time`.
3. `test_authorize_auto_only_for_low_risk_ops`: op de add_node OK; op
   remove_transition sobre nodo completado -> rechazada.
4. `test_validate_rejects_unauthorized_capabilities`: propuesta pide
   "no_registrada" -> violacion I3.
5. `test_validate_rejects_inexistent_dependency`: ref "X" no en registry -> I4.
6. `test_validate_rejects_cycle`: op crea ciclo A->B->A sin max_visits -> I5.
7. `test_validate_rejects_obsolete_base`: base_revision != current -> I6.
8. `test_validate_warns_on_active_node_change`: propone cambio de
   transicion usada por instancia ACTIVE -> warning (no rechazo; info).
9. `test_validate_accepts_clean_add_node`: agregar nodo nuevo sin tocar
   nada completado -> accepted.
10. `test_apply_expansion_returns_new_plan`: apply produce plan nuevo
    con op aplicada; plan original inmutable.
11. `test_rejection_evidence_persisted`: record_rejection crea JSON con
    proposal_id + reason + violacion.
12. `test_full_pipeline_authorized_to_applied`: ciclo completo
    DISCOVER..EVALUATE en el happy path.

**Invariantes blueprint §6 (codigo `graph_expansion.py`):**
- I1 (no reescribir resultados historicos): NO implementado a nivel
  de patch_op en slice-1. La garantia viene de que `apply_expansion`
  produce un plan NUEVO que NO referencia ejecuciones (resourceRevision)
  del plan anterior. Diferido a slice-3 si se requiere verificacion
  explicita.
- I2 (no alterar instancia activa silenciosamente): implementado como
  warning en `validate()` (no rechazo).
- I3 (no adquirir caps no autorizadas): implementado en `validate()`
  via `_find_capable` + registry.
- I4 (no introducir referencias inexistentes): implementado en
  `validate()` via `_ref_exists` para `new_dependencies`.
- I5 (no crear dependencias circulares sin salida): implementado en
  `validate()` via `_has_cycle_via_new_transitions`.
- I6 (no incorporar cambios sobre rev obsoleta): implementado en
  `validate()` via check `base_revision == plan.revision`.
- I7 (no promover cambios locales a definiciones compartidas): NO
  implementado en slice-1. Es exactamente lo que cubre la policy
  engine P4 (forbidden_ops) en slice-3 spec.

## 7. Riesgos identificados

- **R1 — Regresión en WorkflowPlan:** apply_expansion produce un plan
  NUEVO; el original no se toca. Pero aseguramos que `WorkflowPlan`
  sigue siendo `frozen`. Cobertura: tests con `assert plan_original.nodes
  == snapshot_inicial`.
- **R2 — Ciclo nuevo sin max_visits:** los `AddTransition` deben setear
  metadata `max_visits` obligatorio en transiciones ciclicas. Slice-1 de H4
  en mi feat anterior ya tiene `_declared_max_visits`, lo reusamos.
- **R3 — Persistencia JSON vs DB:** slice-1 usa JSON por simplicidad.
  Slice-2 lo migra a storage.py sin romper contratos.

## 8. Out of scope (explícito)

- NO modificamos `storage.py` en este slice.
- NO introducimos subgrafos politicos automáticos (eso es "policy engine"
  más alla del slice 1).
- NO permitimos `RemoveNode`.
- NO implementamos la transicion `EVALUATE` (eso sera slice 2, mide
  resultado tras ejecucion de la propuesta aplicada).
- NO H6 multipropósito (siguiente milestone).
