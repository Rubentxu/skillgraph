# H4 Expansion controlada — slice-3

> Status: **DRAFT** (2026-09-23). Se publica antes de implementar.
> Su proposito es cerrar el diseno de (a) persistencia durable de
> propuestas y rechazos en `Storage`, (b) etapa EVALUATE para
> propuestas `auto_signed`, y (c) refino del policy engine mas alla
> del registry check.

---

## 1. Contexto

### 1.1. Lo que slice-1 (6f93eb2) y slice-2 (bd95d29) cerraron

- ADT `GraphExpansionProposal` + `PatchOp` (AddNode/AddTransition/
  RemoveTransition) + `Authorization` (auto_signed/manual_signed).
- Pipeline puro `propose → validate → authorize → apply_expansion`.
- `ExpansionResult` estilo Either (`_Ok`/`_Err`).
- 6 invariantes: I1 capabilities, I2 transiciones validas,
  I3 attachment conocido, I4 no ciclos, I5 base_revision valida,
  I6 no nodos duplicados.
- WorkflowPlan inmutable: `apply_expansion` devuelve plan NUEVO.
- CLI `sg expansion {propose,apply,validate,rejections}` con 6
  subprocess tests E2E.
- Evidence JSON legal en `tests/uat-evidence/UAT-08.json` y
  `UAT-09.json` (PASS).

### 1.2. Lo que slice-3 cierra

**A. Persistencia durable de propuestas y rechazos.**
Actualmente `cmd_expansion_propose` y `record_rejection` escriben a
JSON files planos en `project_dir/expansion_proposals/` y
`expansion_rejections/`. Esto tiene problemas:

- No hay transaccion: un crash entre `_write_plan_to_storage` y
  `record_rejection` deja el storage inconsistente.
- No hay indice: listar todas las propuestas requiere escanear
  directorio.
- No hay consulta por `proposal_id` eficiente.
- Los 6 E2E subprocess tests escriben a `tests/uat-evidence/`
  (no tmp_path), con riesgo de race condition si pytest-xdist
  se activa (caveat ya documentado en STATE.yaml).

**B. Etapa EVALUATE para `auto_signed`.**
Actualmente `auto_signed` se acepta sin revision (`_require_authorization`
solo verifica `granted_at` no vacio). Esto es insuficiente:
una propuesta `auto_signed` con capability no registrada pasa
el authorize pero falla en validate. El orden correcto es
**EVALUATE antes de AUTHORIZE**: el sistema debe pre-validar
que la propuesta es ejecutable; solo entonces autoriza.

**C. Policy engine refinado.**
El registry check basico ("capability existe en brick") no captura:
- Conflictos entre propuestas concurrentes (dos propuestas que
  modifican el mismo nodo).
- Restricciones de scope (NODE vs TRANSITION vs SUBGRAPH).
- Limites de budget (maximo N nodos por expansion).
- Whitelist/blacklist de operaciones (e.g. bloquear RemoveNode en
  cualquier expansion — coherente con H4 ciclos y decision donde
  RemoveNode NO es PatchOp valido por diseno).

---

## 2. Diseno slice-3

### 2.1. ADT nuevo en `src/skillgraph/graph_expansion.py`

```python
@dataclass(frozen=True, slots=True)
class ProposalStage:
    """Estado del ciclo de vida de una propuesta."""

    stage: Literal["PROPOSED", "EVALUATED", "AUTHORIZED", "APPLIED", "REJECTED", "ARCHIVED"]
    entered_at: str  # ISO-8601 UTC
    entered_by: str  # "validator-cli" | "policy-engine"
    note: str = ""


@dataclass(frozen=True, slots=True)
class StoredProposal:
    """Propuesta + metadata de persistencia en storage."""

    proposal: GraphExpansionProposal
    stage: ProposalStage
    created_at: str
    last_updated_at: str
    storage_key: str  # "<tenant>/<project>/<proposal_id>"
    evaluation_result: ValidationResult | None = None
    authorization_at: str | None = None
    applied_at: str | None = None
    rejection_reason: str | None = None
    rejected_at: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Decision del policy engine sobre una propuesta."""

    accepted: bool
    reason: str
    violated_rules: tuple[str, ...] = ()  # P1..P5 (ver §2.3)
    warnings: tuple[str, ...] = ()
```

### 2.2. Storage schema (extender `src/skillgraph/storage.py`)

```sql
-- Migration version 4 (la ultima actual es v3).
CREATE TABLE IF NOT EXISTS expansion_proposals (
    storage_key TEXT PRIMARY KEY,        -- "<tenant>/<project>/<proposal_id>"
    proposal_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    proposal_json TEXT NOT NULL,         -- GraphExpansionProposal serializado
    stage TEXT NOT NULL,                 -- ProposalStage.stage
    created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    evaluation_json TEXT,                -- ValidationResult | None
    authorization_at TEXT,
    applied_at TEXT,
    rejection_reason TEXT,
    rejected_at TEXT,
    UNIQUE (tenant_id, project_id, proposal_id)
);

CREATE INDEX IF NOT EXISTS ix_proposals_project
    ON expansion_proposals(tenant_id, project_id, stage);

CREATE TABLE IF NOT EXISTS expansion_rejections (
    storage_key TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    proposal_json TEXT NOT NULL,         -- copia para audit forense
    reason TEXT NOT NULL,
    rejected_at TEXT NOT NULL,
    rejected_by TEXT NOT NULL,
    violated_invariants TEXT,            -- JSON array
    policy_violations TEXT,              -- JSON array (P1..P5)
    stage TEXT NOT NULL,                 -- "EVALUATE" | "AUTHORIZE" | "APPLY"
    UNIQUE (tenant_id, project_id, proposal_id)
);

-- Migrar JSON files existentes a SQLite (one-shot).
INSERT OR IGNORE INTO expansion_proposals (...)
    SELECT ... FROM expansion_proposals_json_files;
```

**Decisiones de diseno:**

- **NO** usar tabla nueva para `expansion_proposals_json_files`. La
  migracion es one-shot en codigo Python, no en SQL, para mantener
  la transicion audit friendly.
- `proposal_json` se persiste COMPLETO (no fragmentado) para que la
  audit forense tenga la propuesta original, no una vista derivada.
- `stage` se mantiene como string (no FK a otra tabla) para permitir
  evolution sin migracion.
- `policy_violations` separado de `violated_invariants` para que
  audit distinga "esto fallo en el validador puro" vs "esto fue
  rechazado por politica".

### 2.3. Policy engine

```python
@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Contexto para que el policy engine decida."""

    proposal: GraphExpansionProposal
    plan: WorkflowPlan
    registry: Mapping[str, str]
    concurrent_proposals: tuple[StoredProposal, ...]
    project_settings: Mapping[str, str]


class PolicyEngine(Protocol):
    """Interface para policy engines. Implementacion por defecto: DefaultPolicyEngine."""

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision: ...


class DefaultPolicyEngine:
    """Reglas P1..P5 (orden de evaluacion)."""

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        violations: list[str] = []

        # P1: max operations per proposal (settings: max_ops_per_proposal).
        if len(ctx.proposal.operations) > self._max_ops(ctx):
            violations.append(
                f"P1: {len(ctx.proposal.operations)} ops > "
                f"max_ops_per_proposal={self._max_ops(ctx)}"
            )

        # P2: no concurrent proposals on same attachment_point.
        for other in ctx.concurrent_proposals:
            if (
                other.proposal.attachment_point == ctx.proposal.attachment_point
                and other.stage.stage in ("PROPOSED", "EVALUATED", "AUTHORIZED")
            ):
                violations.append(
                    f"P2: concurrent proposal {other.proposal.proposal_id} "
                    f"on attachment_point={ctx.proposal.attachment_point}"
                )

        # P3: scope restrictions (settings: allowed_scopes).
        if self._allowed_scopes() and ctx.proposal.scope not in self._allowed_scopes():
            violations.append(
                f"P3: scope={ctx.proposal.scope} not in allowed_scopes={self._allowed_scopes()}"
            )

        # P4: blacklist de operations (settings: forbidden_ops).
        # Coherente con H4 ciclos y decision: RemoveNode NO es PatchOp
        # valido por diseno. Si por error se intenta usar, P4 lo bloquea
        # (defensa en profundidad).
        forbidden = self._forbidden_ops()
        for op in ctx.proposal.operations:
            if type(op).__name__ in forbidden:
                violations.append(f"P4: op={type(op).__name__} in forbidden_ops={forbidden}")

        # P5: budget cap (settings: max_nodes_per_project).
        projected_node_count = len(ctx.plan.nodes) + sum(
            1 for op in ctx.proposal.operations if isinstance(op, AddNode)
        )
        if projected_node_count > self._max_nodes():
            violations.append(
                f"P5: projected_nodes={projected_node_count} > "
                f"max_nodes_per_project={self._max_nodes()}"
            )

        return PolicyDecision(
            accepted=not violations,
            reason="OK" if not violations else "; ".join(violations),
            violated_rules=tuple(violations),
        )
```

### 2.4. Pipeline revisado (EVALUATE antes de AUTHORIZE)

```
[1] PROPOSE   cmd_expansion_propose
     └─> validate(proposal, plan, registry)
     └─> Si ok: stage = EVALUATED
     └─> Si falla: record_rejection(stage="EVALUATE")

[2] EVALUATE  policy_engine.evaluate(ctx)
     └─> Si accepted: stage = AUTHORIZED (auto_signed)
     └─> Si rejected: record_rejection(stage="EVALUATE", policy=P1..P5)

[3] AUTHORIZE (manual_signed)  requiere granted_by != None y granted_at valido
     └─> Si ok: stage = AUTHORIZED
     └─> Si falla: record_rejection(stage="AUTHORIZE")

[4] APPLY     apply_expansion(proposal, plan, registry)
     └─> Si ok: persist new plan + stage = APPLIED
     └─> Si falla: record_rejection(stage="APPLY")
```

**Cambio en `_require_authorization`:**
- ANTES (slice-1): solo verifica `granted_at` no vacio.
- AHORA (slice-3): para `auto_signed`, requiere que `EVALUATE` haya
  pasado (campo `evaluation_result` no None y `accepted=True`).
- Para `manual_signed`, mantiene el check de `granted_by` +
  `granted_at`.

### 2.5. CLI extendido

- `sg expansion list [--stage STAGE] [--project NAME]`: lista
  propuestas persistidas (no JSON files). Filtra por stage y proyecto.
- `sg expansion show <proposal_id> [--project NAME]`: imprime
  StoredProposal completo (JSON pretty).
- `sg expansion archive <proposal_id> [--project NAME]`: mueve a
  stage ARCHIVED (no se borra; audit forense).

### 2.6. Settings nuevos (en `~/.config/skillgraph/settings.toml`)

```toml
[expansion]
max_ops_per_proposal = 20
max_nodes_per_project = 1000
allowed_scopes = ["NODE", "TRANSITION", "SUBGRAPH"]  # vacio = todos
forbidden_ops = ["RemoveNode"]  # defensa en profundidad
```

Defaults razonables que NO cambian comportamiento slice-1+2:
- `max_ops_per_proposal = 20` (las 6 invariantes no limitan ops
  por propuesta; este es un nuevo gate).
- `max_nodes_per_project = 1000` (sin uso actual; gate futuro).
- `allowed_scopes` vacio = todos (no rompe nada).
- `forbidden_ops = ["RemoveNode"]` (RemoveNode NO existe como
  PatchOp; es defensa en profundidad).

---

## 3. Tests propuestos

### 3.1. Library (in-process, `tests/test_h4_expansion_storage.py`)

| # | Test | Cubre |
|---|------|-------|
| 1 | `test_proposal_persists_to_sqlite` | Storage escribe `proposal_json` completo |
| 2 | `test_proposal_loads_by_storage_key` | round-trip persistencia |
| 3 | `test_proposal_list_filters_by_stage` | index por stage funciona |
| 4 | `test_proposal_migrates_from_json_file` | one-shot migration no pierde datos |
| 5 | `test_rejection_persists_to_sqlite` | rejection con violated + policy |
| 6 | `test_evaluate_runs_before_authorize_for_auto_signed` | cambio de orden |
| 7 | `test_policy_engine_p1_max_ops` | limite operations |
| 8 | `test_policy_engine_p2_concurrent_proposals` | attachment conflict |
| 9 | `test_policy_engine_p3_scope_restriction` | scope no permitido |
| 10 | `test_policy_engine_p4_forbidden_ops` | RemoveNode bloqueado |
| 11 | `test_policy_engine_p5_budget_cap` | max_nodes_per_project |
| 12 | `test_policy_engine_default_settings_allow_existing_proposals` | no regression |
| 13 | `test_authorization_requires_evaluation_for_auto_signed` | nuevo gate |
| 14 | `test_archive_stage_is_terminal` | ARCHIVED no transiciona |

**Total: 14 tests library.**

### 3.2. E2E subprocess (`tests/test_h4_expansion_cli_slice3.py`)

| # | Test | Cubre |
|---|------|-------|
| 1 | `test_uat_08_persists_proposal_to_sqlite` | UAT-08 con evidencia en SQLite |
| 2 | `test_uat_09_persists_rejection_to_sqlite` | UAT-09 con evidencia en SQLite |
| 3 | `test_expansion_list_after_apply` | lista propuestas aplicadas |
| 4 | `test_expansion_show_full_proposal` | imprime StoredProposal |
| 5 | `test_expansion_archive_terminal` | archive funciona |
| 6 | `test_policy_violation_emits_rejection_with_pcode` | UAT-09 con reason P1..P5 |

**Total: 6 tests E2E.**

### 3.3. Stress / concurrencia (`tests/test_h4_expansion_concurrency.py`)

| # | Test | Cubre |
|---|------|-------|
| 1 | `test_two_concurrent_apply_on_same_attachment_p2_rejects` | P2 atomic |
| 2 | `test_recovery_after_kill_during_apply` | durability tras crash |

**Total: 2 tests stress.** (Estos SI elevan el feedback_loop de
`representative` a `acceptance_aligned` para UAT-09.)

### 3.4. Total slice-3

- 14 library + 6 E2E + 2 stress = **22 tests nuevos**.
- Estimado: ~22 tests × 80 LoC promedio = 1760 LoC nuevo (incluyendo
  fixtures, no solo assertions).

---

## 4. Limitaciones conocidas (las que slice-3 NO cierra)

1. **Transacciones cross-table**: `apply_expansion` modifica `plan_json`
   (filesystem) y `expansion_proposals` (SQLite). No hay una unica
   transaccion atomica que abarque ambos. Aceptable para slice-3;
   requiere journaling real para slice-4+.

2. **Locking pesimista vs optimista**: el policy engine detecta
   conflictos via `concurrent_proposals` (lectura). Si dos propuestas
   se crean en paralelo y se aplican antes de que la otra se indexe,
   el conflicto no se detecta. Requiere lock real (SQLite BEGIN
   IMMEDIATE o advisory lock) para slice-4+.

3. **Migracion backwards-compatible**: el JSON file plan sigue siendo
   la fuente de verdad para `apply_expansion`. Slice-3 migra el
   historial de proposals/rejections a SQLite pero el plan sigue
   en filesystem. Coherente con el principio "no romper lo que
   funciona".

4. **Settings.toml parsing**: el CLI debe leer settings via la
   API actual de paths.py. No anadir dependencia nueva.

---

## 5. Riesgos

| # | Riesgo | Mitigacion |
|---|--------|------------|
| R1 | La migration one-shot falla silenciosamente en proyectos existentes | Tests E2E con proyecto pre-poblado de JSON files |
| R2 | El policy engine rechaza propuestas slice-1 validas | Defaults conservadores + test 12 (no regression) |
| R3 | Concurrencia real no detectable en CI single-threaded | Tests stress en subprocess paralelos (`subprocess.Popen` × 2) |
| R4 | Settings.toml mal formado rompe el CLI | Try/except con defaults hard-coded + warning |
| R5 | El indice por stage degrada con muchos proyectos | Limite actual: <10K proposals por proyecto. OK para slice-3 |

---

## 6. Definition of Done

- [ ] `src/skillgraph/graph_expansion.py` extendido con `ProposalStage`,
      `StoredProposal`, `PolicyDecision`, `PolicyEngine`,
      `DefaultPolicyEngine`.
- [ ] `src/skillgraph/storage.py` migration v4 con `expansion_proposals`
      y `expansion_rejections`. Backwards compatible con JSON files.
- [ ] `src/skillgraph/cli.py` extendido con `list`, `show`, `archive`.
- [ ] `tests/test_h4_expansion_storage.py` (14 tests library).
- [ ] `tests/test_h4_expansion_cli_slice3.py` (6 tests E2E).
- [ ] `tests/test_h4_expansion_concurrency.py` (2 tests stress).
- [ ] ruff format+check limpios.
- [ ] Coverage `graph_expansion.py` >= 86%, `storage.py` >= 94%.
- [ ] `tests/uat-evidence/UAT-08.json` y `UAT-09.json` regenerados
      con nueva persistencia SQLite (mismo schema legal, distinta
      fuente de evidencia).
- [ ] STATE.yaml + SESSION-JOURNAL.md actualizados.
- [ ] Sin regresiones: 284 tests previos + 22 nuevos = 306 verde.

---

## 7. Preguntas abiertas para el operador

1. **Settings.toml**: ¿ruta absoluta hard-coded
   `~/.config/skillgraph/settings.toml` o usar el `paths.py`
   actual que respeta XDG? (Recomiendo paths.py para coherencia.)
2. **Auto_signed**: ¿la policy engine debe aceptar TODAS las
   auto_signed que pasen EVALUATE, o debe haber una whitelist
   de capabilities que pueden auto-asociarse? (Recomiendo
   whitelist opcional via settings; default = todo OK.)
3. **Stress tests**: ¿vale la pena invertir 2h en tests stress
   que probablemente fallen flaky en CI, o skip y dejar para
   slice-4? (Recomiendo al menos 1 test stress de P2; el segundo
   es nice-to-have.)
