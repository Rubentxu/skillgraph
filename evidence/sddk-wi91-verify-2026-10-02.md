# WI-91 — El registro de conformidad H9 afirmaba cuatro cosas falsas

- **Ciclo**: `p-b7740b96d79ec013/wi-91-h9-conformance-record`
- **Fecha**: 2026-10-02
- **HEAD al cierre del fix**: el commit de este bloque

## Qué es este artefacto y por qué importa

`STATE.yaml.goal.h9_addendum_2026_09_25` es el documento que decide si
el hito **H9 (Release candidate)** del blueprint está cumplido. No es una
nota: es el veredicto de conformidad de un hito, y su `conformance_score`
es la cifra que se cita al decidir si la iniciativa puede cerrarse.

Se escribió el **2026-09-25**. El **2026-09-26**, `v0.14.7` entregó los
cuatro entregables que el registro daba por incompletos (WI-12 a WI-17).
El registro no se revalidó.

**Cuatro de sus cinco afirmaciones sobre el código eran falsas, y nada lo
detectaba.**

## La medición

| E | El registro afirmaba (2026-09-25) | Medido contra el árbol (2026-10-02) | Veredicto del registro |
|---|---|---|---|
| **E1** | `PENDIENTE`; «`agent.py` expone únicamente `FakeAgentAdapter`»; «CLI runner acepta `--adapter=fake` (único valor contractual)» | `runtime/http_adapter.py:330` `HttpAgentAdapter` con estrategias Anthropic + OpenAI; `http_adapter_from_env:463`; `cli/commands/run.py:265` acepta `--adapter=http` | **FALSO** |
| **E2** | «Threat model (T3) **NO ejecutado**. No hay STRIDE/abuse-cases» | `docs/architecture/ADR-0015-threat-model-stride.md`; `specs/wi-14-t3-threat-model-http.md`; `tests/test_t3_threat_model_attestation.py` | **FALSO** |
| **E3** | «grieta de no-atomicidad `workflow_runs ↔ runtime_events` preservada por diseño»; «Coste estimado: **300-800 LoC** + tests de concurrencia» | `create_run_atomically` (`run_repository.py:641`) hace ambas escrituras en **un solo** `BEGIN/COMMIT` vía `_atomic_state_and_event`; **vivo**: lo llama `RunController.create_run` (`runcontroller.py:228`); 3 rutas atómicas en el mismo fichero | **FALSO** |
| **E4** | «**No hay runbook formal** de despliegue/operación (T6 observabilidad)» | `docs/observability-runbook.md` (10 900 B); `specs/wi-16-t6-observability-runbook.md`; `runtime/run_observability_delegations.py` | **FALSO** |
| **E5** | 16/16 UAT PASS | `python -m tests.uat_audit` → `PASS=16 FAIL=0 BLOCKED=0` | **CIERTO** |

Los 23 tests que respaldan E1/E2/E3 (`test_t3_threat_model_attestation.py`,
`test_http_adapter_repr_no_disclosure.py`, `test_h9_run_lifecycle_atomic.py`)
estaban verdes durante todo el tiempo que el registro afirmaba lo contrario.

## El patrón de fondo

No es un error de redacción. Es que un registro de estado **sin testigo
verificable envejece en silencio**, porque nadie lo relee cuando el
código avanza por debajo. Los tres workitems anteriores de esta misma
línea Ya habían producido variantes del mismo fallo:

- **WI-85** — 7 claves duplicadas en `STATE.yaml`; `tests.total` parseaba como `85%`.
- **WI-86** — un registro decía que WI-65 estaba pendiente cuando ya se había entregado.
- **este bloque** — 4 de 5 afirmaciones de un veredicto de conformidad, falsas.

## La corrección

Cada entregable lleva ahora `evidencia_paths`: el testigo que el guard
comprueba. `conformance_score` pasa de `4/5 (80%)` a `5/5 (100%)`, y las
afirmaciones que arrastraban la misma premisa quedan marcadas:

- `stewardship_backlog.prioridad_1_spec_s7plus.accion_requerida` decía
  «operador elige entre A/B/C/D». Medido: A y D cerradas desde 2026-09-25,
  y **B quedó inútil** porque sus tres componentes duros (T1 adapter,
  T3 threat model, T6 observabilidad) se entregaron en `v0.14.7`.
- `next_action` era una foto del 2026-09-25 («17 releases, 772/772
  tests»). Marcado como histórico, no como instrucción.
- `Opcion A.implementacion` describe lo que el addendum decía **en esa
  fecha**. Se conserva como historia y se marca `SUPERSEDIDO por WI-91`,
  porque reescribir un registro histórico no es corregirlo: es borrarlo.

## El guard: por qué tiene que morder en las dos direcciones

`tests/test_wi91_h9_conformance_record.py` exige que **estado y evidencia
sean verdad A LA VEZ**:

- el estado declarado es el medido → caza el **registro caducado**;
- los testigos declarados existen → caza la **afirmación sin respaldo**.

Un guard de una sola dirección deja pasar la mitad de los fallos, que es
justo la mitad que se cuela en un documento. La clase
`TestGuardMuerdeEnLasDosDirecciones` lo verifica alimentando las mismas
funciones con registros sintéticos que se saben incorrectos —incluido un
registro **conforme**, para comprobar que un guard que siempre falla no
pasa por guard.

## Lo que NO se corrige

**H9 no se declara cerrada.** Los cinco entregables están entregados y
verificados contra el código, pero el criterio de salida del hito exige
«escenarios reales con trazabilidad, aislamiento y recuperación», y eso
sólo se demuestra ejecutando contra un proveedor real, que necesita
credenciales que este entorno no tiene.

Declararla cerrada sería **el mismo defecto en la dirección contraria**:
sustituir una afirmación falsa por otra que nadie ha medido. El hueco
queda escrito y el test
`TestElCriterioDeSalidaNoSeDeclaraCumplidoSinEjecutarlo` impide que se
pierda de vista.

## Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | el registro vuelve a decir `E1: PENDIENTE` | **cazada** |
| M2 | se borra un testigo declarado del registro | **cazada** |
| M3 | el registro cita evidencia que no existe | **cazada** |
| M4 | **se borra `http_adapter.py` del disco** | **cazada** |
| M5 | `conformance_score` vuelve a `4/5` con 5 cumplidos | **cazada** |
| M6 | **se borra `docs/observability-runbook.md`** | **cazada** |

`cazadas=6  no-cazadas=0`

M4 y M6 son las importantes: no mutan el registro sino **el código**, y
comprueban que el guard vigila la realidad y no la copia de sí mismo.

## Conocimiento negativo

- **Un veredicto de conformidad sin testigo es una opinión con formato de
  dato.** Se lee como una medición y no lo es.
- **El fallo de una función de restauración no es ruido: es el que puede
  medir mal.** La primera versión de `.pipelinek/wi91_mutate.sh` borraba
  su propio directorio de respaldo (`rm -rf "$BAK"`) dentro de
  `restore()`. La segunda llamada no encontró con qué restaurar y la
  corrida terminó dejando `STATE.yaml` en el estado de la quinta
  mutación. **El control de baseline —«el guard debe estar verde antes de
  mutar»— fue lo que lo detectó y se negó a medir.** Sin ese control, el
  script habría reportado 6/6 cazadas sobre un árbol que ya no era el que
  se quería medir. Es la cuarta vez en tres bloques que una medición
  necesita autocontrol: sin él, el resultado es verde y falso.
- **Reescribir un registro histórico no es corregirlo, es borrarlo.** El
  bloque `Opcion A.implementacion` dice lo que el addendum afirmaba el
  2026-09-25. Eso fue cierto. Se conserva y se marca, en vez de
  reescribirlo para que no moleste.
- **Un registro que corrige una afirmación puede introducir la
  contraria.** Por eso el criterio de salida de H9 sigue declarado
  incumplido y hay un test que lo vigila.

## Deuda tangencial registrada, no medida

- **Colisión de numeración de ADR**: `ADR-0015` designa dos documentos
  distintos — `external/blueprint-v1/adr/ADR-0015-vocabulario-de-estados-como-fuente-unica.md`
  (WI-87, 2026-10-02) y `docs/architecture/ADR-0015-threat-model-stride.md`
  (WI-14, 2026-09-26). Ya existía una colisión previa en la serie del
  blueprint (`ADR-0013-anexo-trazado-carga-packs` y
  `ADR-0013-divergencia-h7-y-rectificacion-v060`). Medido, **no
  ejecutado**: renombrar exige actualizar ~8 referencias cruzadas en
  `docs/observability-runbook.md` y es una operación que decide el
  mantenedor, no el agente.
