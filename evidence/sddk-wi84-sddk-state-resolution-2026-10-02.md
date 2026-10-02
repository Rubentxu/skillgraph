# WI-84 — por qué los ciclos `RELEASE_PENDING` no alcanzan su terminal

- **Ciclo SDDK:** transversal (cierre de estado de `p-b7740b96d79ec013`)
- **Fecha:** 2026-10-02
- **BASE:** `2bd64da` (tras WI-82)

## El recuento real

`STATE.yaml.roadmap.next_workitem` decía, en el momento de abrir este
bloque:

> «(b) aprobar el cierre de los ciclos SDDK en `RELEASE_PENDING` — son 6,
> NO 7: wi-75…wi-80»

Medido contra el ledger
(`~/.local/state/sddk/projects/p-b7740b96d79ec013/ledger.sqlite`, tabla
`cycles`):

| status | n | ciclos |
|---|---|---|
| `CLOSED` | 14 | wi-49…wi-64, wi-57…wi-63b |
| **`RELEASE_PENDING`** | **10** | `wi-72`, `wi-73`, `wi-74`, `wi-75`, `wi-76`, `wi-77`, `wi-78`, `wi-79`, `wi-80`, `wi-81` |
| `OPEN` | 2 | `wi-65-subprocess-coverage-file`, `wi65-storage-facade-decomposition` |

**El registro estaba caducado por dos Razones a la vez**: wi-81 se creó
después de que se escribiera ese texto, y wi-72/73/74 nunca se contaron.
La cifra correcta es **10**, no 6.

## Por qué `release.complete` no se puede alcanzar

No es un gate pendiente de aprobación. Es una ruta que **no aplica a este
proyecto**. Medido, paso a paso:

**1. Las 10 necesitan dos requisitos que solo emite el paso de release.**

```
$ sddk cycle next --cycle …/wi-81-drop-dead-row-mapper-shims
  - transition: release.complete
    hint: requirement: merge-receipt; requirement: release-receipt
```

Los 12 ciclos abiertos (10 + 2) tienen `release: null` y `head: null` en su
manifiesto. Los dos requisitos no tienen comando `evaluate-gate`
asociado: los emite el paso de release.

**2. Los gates sí se pueden pasar, y se pasaron.** El motor no opone
resistencia: `release-uat-approved` y `no-pending-effects` aceptan
evidencia real (exigen `argv`, `exit_code` y `output_digest`, no un sello
en blanco). Ambos quedaron en `passed` para wi-81 con la evidencia del
audit UAT (`PASS=16 FAIL=0 BLOCKED=0`, digest
`fdf7073c5baf4bbf7f57569b929189baa065b852f2e185515876e6d66949114e`) y de
`git status --porcelain` vacío.

**3. El paso de release no existe para un proyecto Python.**

```
$ sddk release plan --tag v0.16.11
error: VERSION LOCKSTEP ERROR: could not read
  /var/…/skillgraph/Cargo.toml: No such file or directory (os error 2)
```

El plano de release de SDDK está construido sobre versionado **Rust en
lockstep**: lee `Cargo.toml` para derivar la versión. SkillGraph es un
paquete Python con `[tool.hatch.version] path =
"src/skillgraph/__init__.py"`. No hay `Cargo.toml` y no va a haberlo.

**4. Y además, la ruta que sí aplicaría empuja.** `sddk release apply
--route local` está documentada como *«Push the trunk branch and annotated
tag with local Git only»*. Publicar en el forge queda fuera de lo que la
consigna del operador pre-aprobó (que cubre gates y decisiones, no
publicación).

Conclusión: los 10 ciclos están en `RELEASE_PENDING` no por trabajo
pendiente —el trabajo está hecho, commiteado y publicado en `v0.16.11`—
sino porque **el terminal del workflow que les corresponde no es alcanzable
en un proyecto que no es Rust**.

## Qué se hizo

`sddk cycle supersede --reason external-obsolete --evidence-refs …`, con
este fichero como referencia en cada evento del ledger.

Sobre la razón: el enum ofrece `scope-invalid | goal-replaced |
external-obsolete` y **ninguna describe el caso real** — «trabajo
terminado y publicado, pero el terminal del framework no aplica». Se
elige `external-obsolete` como la más cercana (una circunstancia externa
al ciclo dejó obsoleto su camino de salida) y se deja constancia aquí de
que la clasificación es aproximada y el detalle está en la evidencia. La
razón es una etiqueta; este fichero es el registro.

`--evidence-refs` existe justo para eso: el ledger es append-only y
encadenado por hash, así que la verdad detallada viaja en la referencia en
lugar de quedar aplastada en un enum de tres valores.

### El procedimiento real de `cycle supersede` (3 pasos, medidos)

Ninguna de las tres cosas se deduce leyendo el `--help`. Esta es la forma
en que hay que invocarlo (`.pipelinek/wi84_supersede.sh`):

1. **El intento que falla es parte del protocolo.** `sddk cycle supersede`
   responde `ADMISSION: approval required before mutating 'cycle_state'`
   — pero ese fallo **registra la petición pendiente**. No es un rodeo que
   se pueda saltar; es el paso 1 de 3.
2. **`sddk approval grant`** con la capability que imprime el paso 1
   (`surface.cycle_state#cycle_supersede`). Sin este paso, el segundo
   intento vuelve a pedir aprobación.
3. **`sddk cycle lock acquire --owner <owner>` antes del supersede.** Sin
   lease, el comando responde `lease conflict … held by <owner>` **aunque
   no exista fila en `cycle_leases`** y `cycle lock status` diga
   `lease: none`: el acquire es interno y el token que exige no es el que
   el caller cree tener. Adquirir explícitamente devuelve el
   `fencing_token` correcto.

Resultado: 10/10 `RELEASE_PENDING` → `CLOSED`, más 1 `OPEN` vacío.

## Los 2 ciclos `OPEN`: decisiones opuestas, y por qué

Los dos `OPEN` NO reciben el mismo tratamiento. La asimetría es el punto
de este work item.

### `wi-65-subprocess-coverage-file` → cerrado (`goal-replaced`)

Medido: **1 solo evento** en todo su historial (`cycle.created`), **0
artefactos**, nunca entró en `specify`. Es una cáscara.

Lo que el ledger **no** registra es el sujeto: el evento `cycle.created`
solo lleva `{"outcome":"succeeded","transition_id":"cycle.start"}`, sin
descripción. El único dato del alcance es el **nombre**.

El cierre se apoya en dos cosas, y conviene ser explícito sobre su
fuerza:

- El nombre `subprocess-coverage-file` coincide con el asunto que WI-75
  entregó: `b3b2ef7 fix(coverage): el CLI deja de estar ciego en la
  medicion de cobertura`, que produjo `scripts/coverage.sh` (5834 bytes,
  mtime 2026-10-02 13:03) con `data_file` absoluto, `parallel=true` y
  combinación de datos — es decir, literalmente «coverage de subproceso a
  fichero».
- `wi-65-subprocess-coverage-file` se creó a las **07:26:18Z** y
  `scripts/coverage.sh` es de las **13:03**: el ciclo posterior es el que
  hizo el trabajo.

**La premisa es una inferencia, no un hecho del ledger.** El informe de
WI-75 no menciona WI-65 y el ciclo no registra sujeto. Se cierra con
`goal-replaced` y esta nota deja constancia de que la confianza es
razonable, no demostrada. Si aparece la especificación original de este
ciclo y resulta ser de otro asunto, la decisión es revisable.

### `wi65-storage-facade-decomposition` → **NO se cierra**

Este es el hallazgo que evita el error de cerrar diez ciclos por simetría.

**Sí contiene trabajo real, medido y no ejecutado.** Su artefacto
`exploration-report` es un informe de exploración completo y de calidad:

- `storage.py` son 1807 LoC con **80 métodos** en una sola clase (god
  class H-01).
- **759 LoC (42%) son delegación pura** a los cinco componentes que WI-56
  ya extrajo, sin SQL ni lógica de negocio.
- Las 65 delegaciones se agrupan en **5 mixins perfectamente disjuntos**
  (31/19/7/4/4 métodos), cada uno llama a un único accessor. Cero
  acoplamiento cruzado: la extracción es mecánica.
- Estrategia por mixin, no `__getattr__`, para no perder el tipado estático
  que AGENTS.md §4.1 exige. **Cero ediciones en callers.**
- Riesgo acotado por los tests existentes más una red previa de identidad
  de API pública, siguiendo el patrón ya validado en WI-56.
- Y es honesto sobre su propio límite: 1807 → ~1048 LoC **no** cruza el
  umbral de 800, así que WI-65 se planifica en dos fases y la segunda
  (los ~747 LoC de módulo: DDL, dataclasses, helpers `_tx`/`_atomic`)
  requiere una decisión de ADR previa.

Cerrarlo sería tirar trabajo válido para dejar el tablero limpio. Se deja
`OPEN` y pasa a ser el **siguiente bloque sustantivo**, con la fase 1 ya
dimensionada.

## Lo que NO se hizo, y por qué

- **No se creó un `Cargo.toml` ficticio** para satisfacer el lockstep. Eso
  sería hacer pasar la auditoría por algo que no es, que es exactamente
  el patrón que este proyecto rechaza (`knowledge/git_source.py:365`).
- **No se hizo push.** La consigna pre-aprueba gates y decisiones, no
  publicación en el forge. 15 commits siguen sin publicar.
- **No se forzó `release.complete`**. Habría exigido `merge-receipt` y
  `release-receipt` que el motor no tiene de dónde sacar.
- **No se cerró `wi65-storage-facade-decomposition`.** Contiene un
  informe de exploración real, medido y no ejecutado. Cerrarlo sería
  aparentar orden y tirar trabajo válido.

## Conocimiento negativo

- `sddk cycle supersede --help` **documenta mal el enum**: el texto de
  `--reason` dice `scope_invalid | goal_replaced | external_obsolete`
  (con guiones bajos) y los valores reales llevan **guiones**. El comando
  falla con `invalid value` y solo lo sugiere el `tip:`.
- `sddk permission check` responde `agent agent is not declared in the
  permission registry` para cualquier `--agent agent`: los eventos del
  ledger los emite `{"kind":"system","id":"rubentxu"}`, no un agente con
  entrada en el registro. El permission registry no es por tanto una
  puerta real para este flujo; lo que manda es el frontier de `cycle next`.
- `sddk status --cycle` y `sddk project resolve` exigen argumentos que el
  `--help` de su subcomando no lista. La superficie de agent-help no es
  la superficie real.
