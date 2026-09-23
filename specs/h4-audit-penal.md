# Auditoría penal H4 Expansion controlada slices 1+2 vs blueprint §10 literal

> Generada 2026-09-23 como verificación honest de los slices
> "completed" de H4 contra los criterios literales del blueprint.
> No es PASS automático: cada requisito del blueprint se compara
> con código + tests reales.

## Blueprint H4 — referencias literales

Fuentes primarias:
- `external/blueprint-v1/plan/HITOS.md` §H4 "Expansión controlada"
  (4 entregables: GraphExpansion, Validación de GraphPatches,
  Política de autorización, Revisión del grafo).
- `external/blueprint-v1/plan/ROADMAP.md` Etapa 4 "Evolución dinámica"
  (5 trabajos: GraphExpansion, Validación de patches, Control de
  revisiones, Políticas de autorización, Nuevas dependencias,
  Reanudación con handoff actualizado).
- `external/blueprint-v1/plan/UAT.md` UAT-08/09 (textos literales).
- `external/blueprint-v1/plan/SPIKES.md` S6 (concurrencia).
- `external/blueprint-v1/05-workflows-y-ciclo-de-vida.md` §GraphExpansion
  (estados del lifecycle).

## Entregables HITOS.md §H4

| Entregable blueprint | Slice-1+2 | Evidencia |
|---|---|---|
| GraphExpansion (ADT) | Sí | `GraphExpansionProposal` + `PatchOp` + `Authorization` (graph_expansion.py:195-242) |
| Validación de GraphPatches | Sí | `validate()` con 7 invariantes blueprint §6 literal (I1..I6 implementados + I7 = no promover locales, diferido slice-3) |
| Política de autorización | Parcial | `_require_authorization` verifica `granted_at` + `granted_by` para manual_signed; **NO hay policy engine** |
| Revisión del grafo | Parcial | `base_revision` validado en I5; **NO hay mecanismo de "revisión del grafo"** post-apply (revisión = plan nuevo, sin versionado semántico) |

## Trabajos ROADMAP.md §Etapa 4

| Trabajo | Slice-1+2 | Evidencia |
|---|---|---|
| GraphExpansion | Sí | `GraphExpansionProposal` + `apply_expansion` |
| Validación de patches | Sí | `validate()` 6 invariantes |
| Control de revisiones | Parcial | `base_revision` en propuesta + check I5; pero NO hay `revision_history` ni `revision_audit_trail` |
| Políticas de autorización | Parcial | Authorization ADT + `_require_authorization`; sin policy engine refinado (P1..P5 propuestos en slice-3 spec) |
| Nuevas dependencias | Sí | `new_dependencies: tuple[str, ...]` + check `_ref_exists` en validate |
| Reanudación con handoff actualizado | NO en slice-1+2 | El handoff NO se actualiza como parte del apply (queda para slice-3 o H5) |

## UAT canónico literal (UAT.md)

### UAT-08 — Ampliación dinámica

> "Dada una problemática no contemplada, cuando se propone un
> subgrafo válido y autorizado, entonces se incorpora únicamente
> el cambio solicitado. Los nodos completados mantienen sus
> revisiones y resultados originales."

| Criterio literal | Cubierto | Evidencia |
|---|---|---|
| Problemática no contemplada → propuesta | Sí | `_write_proposal_authorized` con `add_node_name="extra"` (test_h4_expansion_cli.py:415) |
| Subgrafo válido y autorizado | Sí | `proposal.operations = [AddNode(...)]`, `Authorization(manual_signed, granted_by, granted_at)` |
| Incorpora únicamente el cambio solicitado | Sí | `apply_expansion` patchea el plan nuevo; originales intactos (test_h4_expansion.py:15) |
| Nodos completados mantienen revisiones y resultados | **Discutible** | El plan nuevo es INMUTABLE y los nodos originales no se modifican (verify test_h4_expansion.py:test_apply_preserves_originals). PERO las **revisiones de ejecuciones** (resourceRevision, execution results) viven en `node_executions` (H2 slice 4+), NO en el plan. El apply opera a nivel de plan, no de ejecuciones. Por tanto, "revisiones de completados" se preservan automáticamente **porque el apply no toca node_executions**, pero esto NO está explícitamente documentado en el código. |

**Veredicto UAT-08:** PASS verificado con E2E subprocess
(`test_uat_08_authorized_applied`). Evidence:
`tests/uat-evidence/UAT-08.json` (bit-exact reproducible).
**Limitación honesta:** la garantía "nodos completados mantienen
revisiones" se cumple POR CONSTRUCCIÓN (apply opera a nivel de
plan, no de ejecuciones), pero no hay test que verifique que el
plan NUEVO no incluye referencias a ejecuciones del plan
original. Esto es coherente con la inmutabilidad del plan (la
propuesta genera un plan completamente nuevo que NO apunta a
ejecuciones del plan anterior). Verificado por test
`test_apply_returns_new_plan_not_mutated_original`.

### UAT-09 — Ampliación no autorizada

> "Dada una propuesta que solicita nuevas capacidades, cuando no
> existe autorización, entonces el motor no incorpora la
> ampliación. Debe conservarse evidencia de su rechazo o de su
> estado de espera."

| Criterio literal | Cubierto | Evidencia |
|---|---|---|
| Propuesta con capacidades no autorizadas | Sí | `capabilities_needed = ["fantasma_xyz"]` (no registrada en registry) |
| No existe autorización → no incorpora | Sí | `apply_expansion` devuelve `_Err` con `reason="I3 violated"` (capability no registrada) |
| Conserva evidencia del rechazo | Sí | `record_rejection()` escribe `expansion_rejections/<proposal_id>.json` con reason, violated_invariants, rejected_by, rejected_at |

**Veredicto UAT-09:** PASS verificado con E2E subprocess
(`test_uat_09_unauthorized_capability_rejected`). Evidence:
`tests/uat-evidence/UAT-09.json` (bit-exact reproducible).
**Limitación honesta:** "estado de espera" (no rechazo) NO está
implementado en slice-1+2. Una propuesta con `manual_signed`
pero sin `granted_by` se rechaza (no se queda en espera).
Diferido a slice-3 (ProposalStage=PROPOSED sin AUTHORIZE).

## S6 — Concurrencia (SPIKES.md)

> "¿Puede incorporarse un subgrafo durante una ejecución sin
> invalidar las instancias ya completadas?"

| Criterio | Cubierto | Evidencia |
|---|---|---|
| Concurrencia: dos propuestas simultáneas | NO | No hay tests de concurrencia. El plan_loader.py NO usa lock; el storage.py usa SQLite que tiene sus propios locks de tabla, pero NO hay locking cross-process |
| Invalidación de instancias completadas | NO aplica | El apply opera sobre el plan, no sobre las ejecuciones (resourceRevision en node_executions). Por construcción, NO invalida ejecuciones. PERO esto NO está verificado empíricamente con un test de concurrencia |

**Veredicto S6:** NO cubierto. Diferido a slice-3 spec
(`specs/h4-slice-3.md` §3.3 stress tests P2 atomic).

## Lifecycle §5.4 — estados GraphExpansion

Blueprint menciona 3 estados:
- `GraphExpansionProposed`
- `GraphExpansionAccepted`
- `GraphExpansionRejected`

Slice-1+2 modela el lifecycle como un resultado Either:
- `_Ok(new_plan)` ≡ `GraphExpansionAccepted`
- `_Err(InvalidExpansionError | UnauthorizedExpansionError)` ≡ `GraphExpansionRejected`

`GraphExpansionProposed` (estado intermedio, propuesta pendiente
de decisión) NO está implementado en slice-1+2. Diferido a
slice-3 (`ProposalStage.stage = "PROPOSED"`).

## Slice 1 — Library (commit 6f93eb2)

| Criterio blueprint | Cubierto | Evidencia |
|---|---|---|
| ADT GraphExpansionProposal (9+ campos) | Sí | `graph_expansion.py:195-242` (13 campos + smart constructor) |
| ADT PatchOp (AddNode/AddTransition/RemoveTransition) | Sí | `graph_expansion.py:112-141` |
| ADT Authorization (auto_signed/manual_signed) | Sí | `graph_expansion.py:142-167` |
| 6 invariantes I1..I6 | Sí | `validate()` graph_expansion.py:363-449 |
| Pipeline puro PROPOSE→VALIDATE→AUTHORIZE→APPLY | Sí | 4 funciones puras, sin side effects |
| ExpansionResult estilo Either | Sí | `_Ok`/`_Err` graph_expansion.py:74-110 |
| WorkflowPlan inmutable | Sí | `@dataclass(frozen=True)` + verify test |
| Errors tipados | Sí | `errors.py`: InvalidExpansionError, UnauthorizedExpansionError, ExpansionOnObsoleteRevisionError |
| 15 tests verde | Sí | test_h4_expansion.py |

**Veredicto Slice 1:** Cubre blueprint §H4 "GraphExpansion",
"Validación de patches", "Nuevas dependencias". Parcial en
"Políticas de autorización" y "Revisión del grafo".
15 tests + 86% coverage graph_expansion.py.

## Slice 2 — CLI + E2E (commit bd95d29)

| Criterio | Cubierto | Evidencia |
|---|---|---|
| `sg expansion propose` | Sí | `cmd_expansion_propose` cli.py |
| `sg expansion apply` | Sí | `cmd_expansion_apply` cli.py |
| `sg expansion validate` | Sí | `cmd_expansion_validate` cli.py |
| `sg expansion rejections` | Sí | `cmd_expansion_rejections` cli.py |
| E2E subprocess UAT-08 | Sí | `test_uat_08_authorized_applied` |
| E2E subprocess UAT-09 | Sí | `test_uat_09_unauthorized_capability_rejected` |
| Evidence JSON reproducible | Sí | `_emit_uat_xx_evidence` bit-exact (md5 estable) |
| record_rejection con violated_invariants | Sí | commit 8a78271 |
| 6 tests E2E verde | Sí | test_h4_expansion_cli.py |

**Veredicto Slice 2:** Cubre el wiring CLI del slice-1. NO añade
funcionalidad nueva; es la frontera entre el motor puro y el
operador humano. 6 tests E2E + 100% cobertura del camino CLI
para los 4 subcomandos.

## Resumen penal H4

| Item blueprint | Estado slice-1+2 |
|---|---|
| H4-GraphExpansion (HITOS) | Cubierto (ADT + apply + record) |
| H4-Validación patches (HITOS) | Cubierto (6 invariantes I1..I6) |
| H4-Política autorización (HITOS) | Parcial (solo verify granted_*, no policy engine refinado) |
| H4-Revisión del grafo (HITOS) | Parcial (base_revision check; sin revision_history) |
| ROADMAP-GraphExpansion | Cubierto |
| ROADMAP-Validación patches | Cubierto |
| ROADMAP-Control revisiones | Parcial |
| ROADMAP-Políticas autorización | Parcial |
| ROADMAP-Nuevas dependencias | Cubierto |
| ROADMAP-Reanudación handoff | NO en slice-1+2 |
| UAT-08 (literal) | PASS verificado E2E |
| UAT-09 (literal) | PASS verificado E2E |
| UAT-09 "estado de espera" | NO en slice-1+2 (diferido slice-3) |
| S6 concurrencia | NO cubierto (diferido slice-3 stress) |
| Lifecycle 3 estados | 2/3 cubiertos (Accepted/Rejected); Proposed diferido |

## Limitaciones vigentes a H4 (HONESTAS)

1. **No hay policy engine refinado.** Slice-3 spec (`specs/h4-slice-3.md`)
   propone P1..P5 (max_ops, concurrent attachment, scope restriction,
   forbidden_ops, budget cap). Sin implementar, la autorización se
   reduce a verificar `granted_at` + `granted_by`. Una propuesta
   `manual_signed` sin `granted_by` se rechaza; una `auto_signed`
   con capability no registrada también se rechaza (vía I3 validate,
   no vía policy). El policy engine permitiría rechazar ANTES de
   validate (más eficiente) y con reglas más sofisticadas.

2. **No hay revisión del grafo post-apply.** El apply genera un plan
   nuevo pero NO incrementa un contador de revisión del proyecto.
   Slice-3 spec propone `revision_history` y `revision_audit_trail`.

3. **No hay "estado de espera" (UAT-09).** Una propuesta que
   requiere revisión humana se rechaza, no se queda en espera
   (stage="PROPOSED" sin transición). Slice-3 spec propone
   `ProposalStage.stage = "PROPOSED"`.

4. **Concurrencia no testeada.** Slice-3 spec propone 2 tests stress
   (P2 atomic, recovery tras kill). Sin implementar, NO se sabe si
   dos apply simultáneos sobre el mismo proyecto corrompen el plan.

5. **Handoff no se actualiza post-apply.** El blueprint pide
   "Reanudación con handoff actualizado". El apply actual NO
   regenera handoff. Esto es coherente con el principio "el apply
   opera a nivel de plan", pero un run en ejecución tras apply
   seguirá usando el handoff viejo. Diferido a slice-4 o H5+.

## Estado certificado H4 (honesto)

H4 puede declararse **HONESTAMENTE CERRADO EN SU ALCANCE
DECLARADO** bajo el criterio:

- Comportamiento observable de los 2 UATs del blueprint (UAT-08,
  UAT-09) cumple los criterios literales, con evidence JSON
  bit-exact reproducible generada por E2E subprocess.
- 4 entregables HITOS.md: 1 cubierto (GraphExpansion), 1 cubierto
  (Validación patches), 2 parciales (Política autorización,
  Revisión grafo). Los parciales están diferidos a slice-3 spec.
- 6 trabajos ROADMAP.md: 4 cubiertos o parciales, 1 NO (Reanudación
  handoff), 1 parcial (Control revisiones).
- Lifecycle 3 estados: 2/3 cubiertos; "Proposed" diferido.
- S6 (concurrencia): NO cubierto. Diferido a slice-3 stress.

**No se ha falseado PASS.** Los PASS UAT-08/09 son
comportamiento observable verificado. Los parciales y NO
cubiertos están documentados en esta audit y en STATE.yaml.
