# ADR-0023 — `_execute_one` en fases nombradas: el orden es la invariante

Estado: aceptado (sesión 2026-10-02, ciclo `wi-66-execute-one-phases`).

## Contexto

`RunController._execute_one` eran **143 LoC**: la segunda función más
larga del repo tras `build_parser` (409, que es un orquestador
declarativo con cc baja) y la primera por longitud real.

El problema no era solo longitud. Los 9 pasos lineales estaban
envueltos en comentarios que explican **invariantes de atomicidad
H9/H10**: que el `NodeExecution` RUNNING se inserte antes de compilar el
handoff para que `_mark_node_failed` tenga fila que actualizar, que el
`context_hash` se persista antes de invocar al adapter, que el budget se
compruebe antes de tocar el nodo. Toda esa información — *por qué* el
orden es ese — estaba dentro del cuerpo de la función, invisible para
quien leyera el flujo.

## Decisión

El mismo criterio de fases que WI-64 (`_resolve_run_inputs` 89 → 25
LoC) aplicado a los 9 pasos, en **cuatro fases nombradas** cuyo nombre
dice qué protege cada una:

| Fase | Método | LoC | Invariante que nombra |
|---|---|---:|---|
| 1 | `_node_guard` | 33 | budget e idempotencia, antes de tocar el nodo |
| 2 | `_compile_node_handoff` | 66 | H9-context-in-run: FAILED sin invocar adapter |
| 3 | `_invoke_node_adapter` | 29 | frontera con código externo: no tumba el run |
| 4 | `_settle_node_outcome` | 38 | outcome declarado y cierre atómico |

`_execute_one` queda en **74 LoC** y solo orquesta. Dos records
frozen (`_NodeGuard`, `_NodeExecution`) evitan repetir cinco parámetros
en cada llamada y concentran lo que las fases comparten.

### Traducción de retornos, y por qué es segura

`_fail_node_with` devuelve **siempre `False`** (documentado en su propio
docstring). Por eso las fases 2 y 3 pueden devolver `Handoff | None` y
`AgentResult | None`: el `None` significa "nodo ya marcado FAILED", y el
orquestador traduce a `False`, que es exactamente lo que devolvía el
`return self._fail_node_with(...)` original. La equivalencia no es
coincidencia: depende de esa invariante, y la red la fija.

## Consecuencias

- El segundo hallazgo P3 del audit (funciones >80 LoC) queda resuelto
  para `_execute_one`.
- **Coste consciente**: el fichero crece de 1289 a ~1420 LoC, porque
  el desglose paga firmas, docstrings y dos records. El audit mide
  >80 LoC por *función* para P3 y >800 por *fichero* para god module, y
  son cosas distintas: se arregla P3 empeorando el número de god
  module. El módulo estaba y sigue sobre el umbral, así que el plan no
  cambia: fase 2 de ADR-0019.
- Sin cambio de comportamiento: 1966 tests, incluidos los 433 de
  runtime/H9/H10 que cubren la atomicidad.

## La red que lo protege

`tests/test_wi66_execute_one_phases.py` (16 tests) fija, sobre un
`RunController` real con SQLite en `tmp_path`:

1. **El orden de los colaboradores de primer nivel.** Es lo que
   sostiene H9/H10. Se registra con espías que delegan en los
   originales: no se reimplementa la lógica en el test.
2. Los cortocircuitos no tocan lo que no deben: budget agotado no abre
   `NodeExecution`; nodo ya SUCCEEDED no la abre; intentos agotados no
   crean una tercera fila.
3. `_fail_node_with` sigue terminando en `return False`.
4. `_execute_one` y las cuatro fases quedan bajo 80 LoC.

### Una decisión de la red que merece registro

El log plano de espías **no** servía como contrato: `_is_budget_exhausted`
llama a su vez a `_node_executions_for`, así que el número de llamadas
incluye las internas. Fijar la secuencia exacta produce un contrato
frágil que describe la implementación, no la invariante. La red
compara el **orden de primera aparición** de los colaboradores de
primer nivel, que es lo que realmente importa.

## Alternativas rechazadas

- **Dejar los 143 LoC**: la información de *por qué* el orden es ese
  seguiría enterrada en el flujo.
- **Extraer el adapter a un componente**: el `Adapter` ya es un
  `Protocol` inyectado (AGENTS.md §4.3); el problema no era la
  dependencia sino la longitud del orquestador.
- **Reordenar pasos "porque se lee mejor"**: prohibido. El orden es la
  garantía.
