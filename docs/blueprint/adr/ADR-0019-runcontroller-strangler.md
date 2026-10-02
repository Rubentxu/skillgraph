# ADR-0019 — Estrangulamiento de RunController por fases: tipos, motores y umbral

Estado: aceptado (sesión 2026-10-02, ciclo `wi-59-runcontroller-strangler-phase1`; fases 2-4 planificadas, no ejecutadas).

## Contexto

`src/skillgraph/runtime/runcontroller.py` es, tras resolver H-02
(ADR-0018), el segundo god module vigente: **1445 LoC** con un
god-class de **1193 LoC** (`RunController`, medido por AST al abrir el
ciclo) más ~250 LoC de tipos y serialización a nivel de módulo. El
audit de deuda vigente lo lista como P1 y la convención del repo exige
ADR previa.

A diferencia del CLI (ADR-0018), aquí NO hay tabla de dispatch que
delimite clusters: es una sola clase de dominio que orquesta el ciclo
de vida de los runs, y contiene los caminos críticos de atomicidad
(variantes `*_atomically`, ADR-0017) con sus redes de inyección de
fallos H9/H10. El coste de un movimiento equivocado es máximo.

Mapa medido (AST, 2026-10-02):

| Bloque | LoC | Naturaleza |
|---|---:|---|
| Tipos y serialización de módulo (`RunBudget`, `RunSnapshot`, `RuntimeEventLog`, `BudgetViolationKind`, `plan_to_json/from_json`, `result_to_jsonable`, `is_outcome_declared`, `new_run_id/new_node_execution_id`, `_noop_lock`) | ~250 | pura, cero dependencias de Storage |
| `RunController` (god-class) | 1193 | orquestación: reconciliation, recovery, snapshots, handoff, budgets, locks |

## Decision

Estrangulamiento por **fases de riesgo creciente**, con la regla de
siempre de este repo: cada fase es un commit atómico con suite
completa verde y red de identidad, y las rutas de escritura atómicas
(ADR-0017) NO se tocan hasta la última fase.

- **Fase 1 (esta)**: extraer el bloque puro de tipos/serialización a
  `src/skillgraph/runtime/run_types.py`. `runcontroller` conserva
  re-imports (25 call-sites de `RunController`, 10 de `RunBudget` y 4
  sueltos siguen importando desde `runcontroller` sin editar).
- **Fase 2**: extraer el motor de **snapshots y recovery**
  (`_snapshot`, `_recover_interrupted`, `_load_run` y DTO-building) a
  un colaborador de solo lectura.
- **Fase 3**: extraer el motor de **reconciliation**
  (`_execute_frontier` y ramas de terminación) respetando que los
  pares estado+evento sigan yendo por las variantes `*_atomically`.
- **Fase 4 (opcional, solo si las anteriores dejan el resto >800)**:
  handoff/budget enforcement.
- **Umbral objetivo**: `runcontroller.py` < 800 LoC (fuera de god
  files). Si las fases 1-3 no bastan, se acepta el residuo documentado
  en vez de forzar cortes de bajo valor.

### Alternativas rechazadas

- **Trocear el god-class de una vez** en múltiples servicios: máximo
  riesgo sobre los caminhos atómicos H9/H10 y sin red de identidad
  barata como la del CLI.
- **Extraer solo módulo-types sin ADR**: deja el plan de fases sin
  trazabilidad y repite el patrón "barajar sin decidir".
- **No hacer nada**: el audit lo mantiene P1 y es el segundo mayor del
  repo.

## Consecuencias

- Fase 1: `runcontroller.py` 1445 → ~1190 LoC; `runtime/run_types.py`
  nuevo con cero dependencias de Storage; los 39 consumidores externos
  de los tipos no se editan (re-export).
- Fases 2-3: cada motor nuevo será un colaborador con Tests de
  identidad y las redes H9/H10 intactas; ninguna variante
  `*_atomically` cambia de firma.
- La red de dispatch del CLI no se ve afectada (runcontroller no es
  ruta del dispatch).
- Métrica de éxito por fase: suite completa verde + identidad +
  LoC objetivo intermedio documentado en el journal.

## Referencias

- ADR-0017 (atomicidad estado-evento): las variantes `*_atomically`
  que fases 2-3 NO deben alterar.
- ADR-0018 (patrón de estrangulamiento + redes de identidad).
- `audits/architecture-debt-2026-10-02.md`: ranking de god modules
  vigente.
