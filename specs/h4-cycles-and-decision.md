# Spec H4 — Workflows cíclicos y DecisionNode

> Estado: **DRAFT**. NO firmado. Decisiones D1..D4 abiertas.
> Hito: H4 (cierre del blueprint `external/blueprint-v1/plan/ROADMAP.md` Etapas 0..3).
> Etapas previas: H0..H3 cerradas (33 commits, 238 tests, 7/7 UAT PASS).
> Deuda originada en: H2/H3 (DAG lineal, ciclos no soportados, sin DecisionNode).

## 1. Motivación

SkillGraph H2/H3 asume DAG lineal: `_calculate_frontier` siempre devuelve
`[current]` (un nodo), y `cmd_run` (post-fix `bdd196f`) ejecuta UN nodo
por llamada reconcile. Eso significa:

1. **Sin decisiones binarias**: no hay forma de declarar un nodo que elija
   entre A o B en función del resultado. Los planes hoy son siempre
   `transition: source=a, outcome=ok, target=b` con `ok` como outcome
   único — no hay un DSL que diga "si outcome=X entonces target=Y,
   si outcome=Z entonces target=W".
2. **Sin ciclos**: si `a` tiene una transición a sí mismo (retry-loop) o a
   un nodo ancestro (iteración), el `_calculate_frontier` actual devuelve
   `[]` (porque last.state es SUCCEEDED) y el run se marca COMPLETED
   falsamente.
3. **Sin presupuesto de nodos**: `cmd_run --max-iterations=N` ya respeta
   el límite, pero no hay forma de declarar "este run puede iterar hasta
   K veces" — el caller externo tiene que conocer el límite.

H4 cierra estos tres frentes.

## 2. Alcance propuesto (a confirmar por el operador)

### Slice 1 — DecisionNode ADT + DSL

- Nuevo `kind: DecisionNode` en `WorkflowPlan`. Igual forma que
  `ActionNode` pero con `outcomes: list[str]` explícito (default: ["ok"]).
- El Adapter (FakeAgentAdapter y siguientes) devuelve uno de los outcomes
  declarados. Si devuelve uno NO declarado: `ValidationError` inmediato.
- Transiciones: `transitions` ya soporta N transiciones desde la misma
  source. Solo hace falta garantizar que cada `target` existe.
- **Tests**: ~8 unit (DSL + Adapter + reconciliación con 2 outcomes).

### Slice 2 — Ciclos declarativos (max-iterations a nivel de nodo)

- Añadir campo opcional `max_visits: int | None` por nodo en `WorkflowPlan`.
- `_calculate_frontier` se extiende:
  - Si el `current_node` ya se ha ejecutado `max_visits` veces → no se
    re-ejecuta; run pasa a COMPLETED (con nota honesta "loop budget
    exhausted").
  - Si no, devuelve `[current]` igual que antes.
- **Tests**: ~6 unit (frontier, max_visits=2, max_visits=None).

### Slice 3 — Ciclos: idempotencia y reset (opcional, scope creep)

- Si una transición entrante lleva a un nodo ya SUCCEEDED, ¿se re-ejecuta
  o se considera el resultado válido?
- Decisión ABIERTA: SKIP (re-ejecución con nuevo `node_execution_id`)
  vs REUSE (mantener el mismo node_execution_id). SKIP es más honesto
  con el modelo actual; REUSE ahorra cómputo.
- Si se elige SKIP: ningún cambio adicional (ya funciona así).
- Si se elige REUSE: requiere tests que prueben no-duplicación.

## 3. Decisiones ABIERTAS (no firmar este spec sin respuesta)

### D1 — Alcance de H4

¿Slices 1+2 (mínimo viable, cierra deuda UAT-06-style y abre ciclos
simples), o slices 1+2+3 (cubre idempotencia en ciclos)?

**Recomendación agente**: 1+2. Slice 3 es scope creep sin requisito
observado. Esperar a que un caso real pida REUSE.

### D2 — Sintaxis DSL para DecisionNode

Dos opciones:

**A)** Extender `kind` a un Literal: `"ActionNode" | "DecisionNode"`.
DecisionNode tiene `outcomes: ["ok", "retry", "abort"]`.

**B)** Marcar ActionNode como `decision: true` con `outcomes` opcional.
Más simple, pero mezcla conceptos (un nodo es o acción o decisión, no
ambas).

**Recomendación agente**: A. Mantiene la purity ADT (cada `kind` un tipo
distinto) y permite que el Adapter firme contratos específicos por
kind. Ya tenemos precedent en H1 (WorkflowNode vs WorkflowPlan).

### D3 — Comportamiento del cycle budget exhausted

Cuando un nodo alcanza `max_visits` y aún hay transiciones que lo
apuntarían de nuevo:

**A)** Run → COMPLETED con `outcome: "budget_exhausted"` (sigue siendo
éxito, no se reintenta más).

**B)** Run → FAILED con `error: "max_visits_exceeded"`. El usuario decide
qué hacer.

**Recomendación agente**: B. FAILED es más honesto: el usuario sabe que
el plan no completó su intención original. COMPLETED-oculto enmascara
un fallo real.

### D4 — Adapter real para tokens (H4+ o fuera de scope)

El ContextController H3 usa `approx_chars` (heurística). Para H4+ con
presupuestos de tokens REALES harían falta tiktoken u otro tokenizador.

**Recomendación agente**: NO incluir en H4. Solo cuando un caso real
exija conteo exacto (no aproximado). Es H4+ o H5.

## 4. UAT canónico (a redactar tras firma)

Cuando el operador cierre D1..D4, este spec se actualizará con:

- **UAT-08**: DecisionNode con outcome="retry" re-ejecuta el mismo nodo.
- **UAT-09**: Run con `max_visits=2` en un nodo cíclico termina FAILED
  tras la 2ª visita.
- **UAT-10**: Plan con ciclos y `max_visits=None` ejecuta hasta K=infinito
  (probablemente limitado por `cmd_run --max-iterations`).

## 5. Plan de implementación (post-firma)

Estimación tras cerrar D1..D4:

- Slice 1 (DecisionNode): ~3-5 días. 8 tests.
- Slice 2 (max_visits): ~2-3 días. 6 tests.
- Total: ~5-8 días, ~14 tests nuevos, 2 UAT nuevos.

Total acumulado repo tras H4: 238 + 14 ≈ 252 tests.

## 6. Riesgos identificados

- **Spec firmado rápido sin tests**: este spec es ejecutivo. Sin D1..D4
  firmadas, NO implementar.
- **Ciclos con side-effects**: si un nodo cíclico tiene efectos
  externos (escribe a DB, hace commit Git), la decisión D3.B (FAILED)
  deja efectos a medias. Considerar "compensation brick" (H5+).
- **`max_visits` infinito y `cmd_run --max-iterations`**: ambos límites
  coexisten. El más restrictivo gana. Documentar.
