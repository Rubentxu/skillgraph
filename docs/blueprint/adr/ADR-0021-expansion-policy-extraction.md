# ADR-0021 — Extracción del subsistema de policy de graph_expansion

Estado: aceptado (sesión 2026-10-02, ciclo `wi-62-expansion-policy-extraction`; ejecutada).

## Contexto

`src/skillgraph/governance/graph_expansion.py` (862 LoC) es el cuarto
god module vigente tras resolver H-02 (ADR-0018), fase 1 de ADR-0019
y fase 2a de ADR-0020. Contiene un **subsistema de policy altamente
cohesivo** (~196 LoC): `ProposalStageName`, `ProposalStage`,
`PolicySettings`, `PolicyContext`, `PolicyDecision`, `PolicyEngine`,
`_check_p1..p5`, `DefaultPolicyEngine`, `EvaluationResult`,
`evaluate_proposal` (reglas P1..P5 del slice-3 del H4).

Consumidores: SOLO `tests/test_h4_expansion_slice3.py` (importa
PolicyContext/PolicyDecision/PolicyEngine/PolicySettings/
evaluate_proposal desde graph_expansion) y el `__all__` del módulo.
Ningún otro módulo de `src/` lo usa — el CLI consume
propose/validate/apply, no el engine.

Dependencias runtime del bloque: `now_iso()` (de `runtime.engine`,
externo — sin riesgo de ciclo) y `AddNode` (isinstance en P5). El
resto son anotaciones (con `from __future__ import annotations`,
diferidas).

## Decision

Extraer el subsistema completo a
`src/skillgraph/governance/expansion_policy.py`:

- **Cero dependencia runtime de graph_expansion**: las anotaciones
  (`GraphExpansionProposal`, `WorkflowPlan`, `Scope`, `AddNode`,
  `Mapping`) van bajo `TYPE_CHECKING`; `now_iso` se importa de
  `runtime.engine` directamente.
- **P5 cambia isinstance por chequeo de nombre** (`type(op).__name__ ==
  "AddNode"`), alineado con el estilo que P4 ya usa para
  `forbidden_ops`. No hay subclases de los PatchOps en el repo
  (dataclasses frozen+slots); el cambio elimina la única dependencia
  runtime y queda documentado aquí.
- **graph_expansion conserva re-export runtime** de los 9 símbolos
  públicos del subsistema (`__all__` intacto; el test H4-slice3 sigue
  importando desde graph_expansion sin edición).
- Red de identidad: `graph_expansion.X is expansion_policy.X` para los
  9 símbolos + graph_expansion por debajo del umbral (<800 LoC).

## Consecuencias

- `graph_expansion.py` 862 → ~665 LoC: **fuera de god files** (quedan
  storage 1807, runcontroller 1289, ports 927).
- `expansion_policy.py` nuevo (~200 LoC): una sola razón de cambio
  (las reglas P1..P5).
- El `__all__` de graph_expansion NO cambia (los consumidores externos
  no se editan); internamente el módulo importa del nuevo.
- Falsos-fantasma cubiertos por la red: las rutas
  `(dominio, sub)` del CLI no se tocan (el subsistema no es ruta de
  dispatch).

## Referencias

- ADR-0018/0019/0020: patrón de estrangulamiento con redes de
  identidad.
- `tests/test_h4_expansion_slice3.py`: red funcional previa de las
  reglas P1..P5 (permanece verde sin edición).
