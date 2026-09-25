# Slice 5 — ContextRecipe + ContextController + OutcomeTracer

> Sub-spec del H3 (`specs/h3-knowledge.md`). Cierra el gate del hito:
> "un agente simulado puede completar su trabajo sin historial
> conversacional" (HITOS.md H3).
> Depende de Slices 1-4 implementados.
> NO se ejecuta antes de que el spec H3 esté firmado (D2, D3, D4).
> Estado: **DISEÑO**.

## 1. Objetivo

Introducir:

1. **`ContextRecipe`** como nuevo brick kind (registrable como
   recurso). Permite versionar y compartir recetas de contexto.
2. **`ContextController`** que compila handoffs a partir de una
   receta: resuelve conocimiento obligatorio, expande relaciones,
   materializa el handoff inmutable, calcula `context_hash`.
3. **`OutcomeTracer`** que produce un `OutcomeTrace` desde un run_id:
   extrae los Claims/Evidences que el run tocó, los referencia (no
   los copia).
4. **Tests E2E subprocess** del UAT canónico H3 (modify source →
   invalidate → check stale → refresh → compile handoff sin
   historial conversacional).

## 2. Decisiones de diseño

### D20 — ContextRecipe como brick (D2 cerrada por defecto)

`ContextRecipe` se registra como nuevo kind en `registry.py`:

```python
@validate_spec
def _validate_context_recipe(spec: dict) -> None:
    _require_keys(
        spec, ("obligatory", "freshness_policy", "token_budget"), ctx="ContextRecipe.spec"
    )
    if not isinstance(spec.get("obligatory"), list):
        raise ValidationError("ContextRecipe.spec.obligatory debe ser lista")
    if spec.get("freshness_policy") not in {"strict", "best_effort"}:
        raise ValidationError("ContextRecipe.spec.freshness_policy debe ser strict o best_effort")
    # ... etc
```

Si D2 del spec H3 se cierra con "NO brick", Slice 5 carga la receta
desde un dict Python en vez de un brick. Mantenemos D20 como
defecto **solo si D2 está firmada como brick**.

### D21 — Handoff materializado + hash determinista

`ContextController.compile_handoff(recipe, node_definition)`:

1. Carga `recipe` (brick o dict).
2. Resuelve los `obligatory` selectors → lista de Claim/Evidence/Finding.
3. Expande relaciones transitivamente según `relation_selectors`.
4. Filtra por freshness:
   - `strict`: si alguna Claim stale → `StaleKnowledgeError`.
   - `best_effort`: marca stale pero permite continuar.
5. Aplica `overflow_strategy`:
   - `drop_optional`: descarta opcional para caber en presupuesto.
   - `fail`: si no cabe → `TokenBudgetExceededError`.
   - `truncate_finding`: corta Findings largos.
6. Serializa el handoff (reutiliza la lógica de Etapa 2 §handoff).
7. Calcula `context_hash = sha256(serialized)`.
8. Persiste el handoff inmutable.
9. Devuelve el `Handoff` con todo lo anterior.

### D22 — `token_budget` como caracteres aproximados (D4)

```python
def approx_chars(obj: dict | str) -> int:
    if isinstance(obj, str):
        return len(obj)
    return len(json.dumps(obj, ensure_ascii=False, sort_keys=True))
```

NO son tokens reales. Es una heurística documentada; suficiente
para el gate UAT. Si H4+ integra un Adapter LLM real, se mide
con `tiktoken` o equivalente.

### D23 — OutcomeTracer sin duplicar contenido

```python
class OutcomeTracer:
    @classmethod
    def from_run(
        cls,
        *,
        knowledge: KnowledgeController,
        run_id: str,
    ) -> OutcomeTrace:
        """Extrae las Claims/Evidences que el run tocó."""
```

El trace referencia (vía `claim_refs`/`evidence_refs`) pero NO
copia el contenido. Si una Claim cambia después, el trace la
ve actualizada al consultarla. Esto cumple blueprint §9 ("no
duplica resúmenes").

### D24 — Sincronización con RunController ACTIVE (D3)

Si D3 se cierra con "warning + strict opcional":
- `ContextController.compile_handoff` con `freshness_policy=strict`
  lanza `StaleKnowledgeError` siempre que haya stale (incluso si
  el caller lo llamó desde un run ACTIVE).
- `compile_handoff` con `best_effort` añade el flag `stale=true` al
  handoff; el CLI/Adapter decide qué hacer (log, abortar, continuar).
- El RunController ACTIVE NO se invalida automáticamente por un
  `KnowledgeInvalidated` event; el siguiente `reconcile_run` lo
  detecta si la operación requiere strict.

## 3. API pública

```python
class ContextController:
    def __init__(self, *, knowledge: KnowledgeController, storage: Storage): ...

    def compile_handoff(
        self,
        *,
        recipe_ref: ResourceIdentity | dict,
        node_definition_ref: ResourceIdentity,
    ) -> Handoff: ...

    def refresh_handoff(self, *, context_hash: str) -> Handoff:
        """Recompila el handoff si la receta o el conocimiento han cambiado."""


class OutcomeTracer:
    @classmethod
    def from_run(
        cls,
        *,
        knowledge: KnowledgeController,
        run_id: str,
    ) -> OutcomeTrace: ...
```

## 4. Errores nuevos

```python
class StaleKnowledgeError(SkillGraphError):
    code = "sg_stale_knowledge"


class MissingObligatoryError(SkillGraphError):
    code = "sg_missing_obligatory"


class TokenBudgetExceededError(SkillGraphError):
    code = "sg_token_budget_exceeded"


class RecipeNotFoundError(SkillGraphError):
    code = "sg_recipe_not_found"
```

## 5. Tests (`tests/test_context_controller.py`)

**12 tests propuestos + 3 tests E2E subprocess en `test_cli_branches.py`:**

### Unit (12)
1. `test_compile_handoff_returns_handoff_with_hash` — hash determinista.
2. `test_compile_handoff_strict_rejects_stale` — `StaleKnowledgeError`.
3. `test_compile_handoff_best_effort_includes_stale_flag` — el flag se setea.
4. `test_compile_handoff_missing_obligatory_raises` — `MissingObligatoryError`.
5. `test_compile_handoff_token_budget_truncates_optional` — overflow_strategy=truncate.
6. `test_compile_handoff_token_budget_fail_raises` — overflow_strategy=fail.
7. `test_compile_handoff_idempotent` — misma recipe+knowledge → mismo hash.
8. `test_refresh_handoff_returns_new_hash` — knowledge cambia → hash cambia.
9. `test_outcome_tracer_references_claims_not_copies` — el trace tiene
   `claim_refs`, no `claims`.
10. `test_outcome_tracer_preserves_order` — orden del run se mantiene.
11. `test_recipe_as_brick_roundtrip` — ContextRecipe como brick pasa por
    registry/validate.
12. `test_recipe_as_dict_when_brick_disabled` — fallback dict funciona.

### Subprocess E2E (3) — añadidos a `test_cli_branches.py`
13. `test_knowledge_compile_subprocess_succeeds` — `python -m skillgraph.cli
    knowledge compile` exit=0.
14. `test_knowledge_compile_with_strict_rejects_subprocess` — exit=10 (DOMAIN).
15. `test_knowledge_trace_subprocess` — exit=0, output incluye trace_id.

## 6. Criterios de aceptación

Slice 5 completado cuando:
1. 15 tests (12 unit + 3 E2E) verdes.
2. UAT canónico de HITOS.md H3 completo: modify source → invalidate
   → check stale → refresh → compile handoff sin historial conversacional.
3. `ContextRecipe` registrado como brick en `registry.py` (si D2=brick)
   o documentado como dict-only (si D2=no-brick).
4. Commit: `feat(h3-s5): ContextRecipe + ContextController + OutcomeTracer`.

## 7. UAT canónico (literal)

Cierra H3. **Lo que el operador observa:**

```bash
# Setup
sg init --data-root /tmp/sg-h3
sg project create demo
sg brick demo project.md        # DomainPack software
sg knowledge extract demo       # extrae Claims iniciales
sg knowledge stale demo         # lista Claims (no stale)

# Cambio
echo "x = 1" >> src/foo.py
git -C /tmp/sg-h3 commit -am "modify foo.py"

# Invalidación
sg knowledge invalidate demo --source git:abc:src/foo.py
sg knowledge stale demo         # ahora hay stale

# Compile con strict (falla)
sg knowledge compile demo --recipe sw-characterize --strict
# exit != 0 (StaleKnowledgeError)

# Refresh
sg knowledge refresh demo --source git:abc:src/foo.py --revision HEAD
sg knowledge stale demo         # 0 stale

# Compile con strict (OK)
sg knowledge compile demo --recipe sw-characterize --strict
# exit = 0, handoff serializado a stdout

# Trace del último run
sg run demo /tmp/plan.md
sg knowledge trace demo --run run-XYZ
# exit = 0, trace con claim_refs
```

**Gate cumplido**: "un agente simulado puede completar su trabajo
sin historial conversacional" — el Handoff contiene todo lo
necesario para ejecutar el nodo, y el OutcomeTrace documenta qué
se tocó.

## 8. Out of scope

- **Domain Packs especializados** (software, narrative, learning):
  H5 introduce reglas propias. Slice 5 implementa las reglas
  genéricas (literales `RuleRef`) que H5 especializará.
- **Outcome traces narrativa / learning**: H5+. Slice 5 solo
  implementa `SoftwareExecutionSlice` (literal del blueprint §9).
- **Asimilación de skills externas**: H5.

## 9. Riesgos

### R12 — Recetas con selectores no resolubles

Si una receta referencia un entity_id que ya no existe,
`MissingObligatoryError`. Es correcto, pero el error message
debe ser accionable (incluir el selector que falló).

### R13 — Handoff muy grande

Si el conocimiento obligatorio suma >100MB, el handoff puede ser
enorme. Mitigación: el token_budget lo limita, pero hay un piso
de obligatorios que NO se trunca (blueprint §7 regla 4).

### R14 — Outcome trace creciendo sin bound

Un proyecto con muchos runs acumula muchos traces. Mitigación
futura (H4+): archivar traces terminales tras N días.

## 10. Referencias

- Spec padre: `specs/h3-knowledge.md` §2.2, §2.5.
- Slice 4 (invalidación).
- Slice 3 (Git fingerprinting).
- Blueprint §6 (ContextController), §7 (handoff), §8 (invalidación), §9 (trace).
- HITOS.md H3 (gate).
- ADR-0006 (handoff inmutable), ADR-0007 (procedencia).
