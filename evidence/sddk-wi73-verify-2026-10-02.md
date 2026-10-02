# WI-73 — Informe de verificación

> Ciclo `p-b7740b96d79ec013/wi-73-p3-aggregate-file-signatures`, fase
> Verify. Implementación en `efccd2c`. Base del workitem: `e477241`.

## 1. Requisitos uno a uno

| Requisito | Verificación | Resultado |
|---|---|---|
| REQ-1 extrae el invariante | `test_helper_exists_with_a_name_that_states_the_invariant`, `test_public_method_no_longer_inlines_the_isolation_loop`, `test_public_method_delegates_to_the_helper` | PASS |
| REQ-2 aislamiento intacto | `TestUatEvo08ProjectIsolation` preexistente (sin modificar) + `test_cross_project_source_is_rejected_without_leaking_its_id` + `test_unknown_source_is_silently_skipped` | PASS |
| REQ-3 sin cambio de contrato | `test_isolation_is_checked_before_any_signature_is_read` (orden), `test_type_guard_still_raises_type_error`, `test_empty_members_still_short_circuits`, `test_aggregate_still_returns_signatures_for_valid_members` | PASS |
| REQ-4 sin for-solo-acumula | el segundo bucle es comprehension; `ruff` limpio | PASS |
| REQ-5 oráculo diferencial | §2 | PASS |
| REQ-6 el guard no se toca | `test_type_guard_still_raises_type_error` | PASS |

## 2. Equivalencia medida

`aggregate_file_signatures` 86 → **72 LoC**, cc 8 → **3**.
`_sources_in_scope` (nuevo): 34 LoC, cc 5.
Fichero 627 → 648 LoC. Funciones P3: 5 → **4**. God modules 0.
cc máximo del repo: 10 (sin cambio).

Los **53 tests de knowledge** de `test_h12_file_signature_scopes.py`,
`test_h13_handoff_expert.py` y `test_h9_coverage_knowledge_controller.py`
pasan **sin haber sido modificados**.

## 3. Mutaciones: tres, todas detectadas

| # | Mutación | Detectada por |
|---|---|---|
| M1 | **filtrar en silencio** el cruce de proyecto en vez de rechazarlo | 3 tests nuevos **y** el preexistente de H12 |
| M2 | el mensaje de rechazo revela el `source_id` | 3 tests |
| M3 | la comprehension se mueve antes del aislamiento | 1 test de orden |

M1 es la que justifica la red: es la fuga de contenido que UAT-EVO-08
prohíbe, y el hecho de que la red **preexistente** también la cazara
confirma que el invariante ya estaba protegido y que el corte lo
conservó en vez de duplicarlo.

## 4. Dos errores míos, y por qué importan

1. **Monkeypatch sobre un dataclass frozen.** `KnowledgeController` es
   `frozen=True`, así que asignar `list_file_signatures_for_source` lanza
   `FrozenInstanceError`. La espia pasa a ser una subclase, que además
   demuestra que el punto de observación es el método y no un detalle
   del storage.
2. **El test de fuga ejercitaba el caso equivocado.** No registró el
   source en p1, así que era el caso 3 (no existe en ninguna parte) y no
   el caso 2 (existe en otro proyecto): el helper lo omitía en silencio
   y el test fallaba por el motivo equivocado. **Un test que falla por
   el motivo equivocado no es un test rojo útil**: da falsa confianza
   sobre qué se está midiendo.

## 5. Hallazgos reportados sin actuar

- **Punto ciego del audit.** `list_file_signatures_for_source` mide cc
  10 (la mayor del módulo) con 58 LoC. Los dos umbrales del audit (80
  LoC y cc 20) no la capturan. Medida y reportada; no cortada, porque
  abrir un frente nuevo a mitad de otro es inventar deuda.
- **Convención no escrita.** `TypeError` para validar tipos,
  `ValidationError` para validar valores. `file_handoff._validate_inputs`
  tiene cuatro `TypeError` iguales y AGENTS §1.2 no la menciona. Cambiar
  una instancia dejando cuatro hermanas crearía inconsistencia.

## 6. Deuda restante, con prioridad

Las 4 funciones P3 que quedan **no tienen cc alto**: `build_parser`
(409, cc 1, tabla declarativa), `compile_handoff` (90, cc 2, lineal),
`compile_handoff_from_scopes` (85, cc 1, lineal) y `promote_candidate`
(84, cc 4, marginal). Partir las tres lineales sería ceremonia.

Por tanto el frente P3 está, en la práctica, **agotado**: no queda
candidata que merezca un corte. Lo que queda por decidir es si se abre
frente para el punto ciego del audit (cc 10) o se acepta. Esa decisión
es del operador y está planteada en `STATE.yaml.next_workitem`.

## 7. Verificación de gobernanza

`Pipeline finished with SUCCESS`, runId `dcf2c481`, 7 `StepStarted`,
7 `StepFinished`, 5/5 `StageFinished` en `success`, 0 `StepFailed`, y
`2215 passed in 89.49s` capturado en `EchoOutputCaptured`. Binario
`0.39.0`. `.pipeline.kts` sin drift.
