# `pipelinek` cachea el stage de tests y no lo invalida al cambiar el codigo

> Observado el 2026-09-28 sobre `pipelinek` v0.39.0 con `.pipeline.kts`
> sin cambios desde `8ec0645` (sha256 `0665345f…`).

## Lo que se observa

El journal de `.pipelinek/db.sqlite` distingue dos formas de stage:

**Ejecución real** (06:50Z, 1413 tests):

```
StageStarted   unit-tests
StepStarted    unit-tests/sh-0
EchoOutputCaptured  "…1413 passed in 407.93s (0:06:47)"
StepFinished   unit-tests/sh-0
StageFinished  unit-tests  success
```

**Reproducción de caché** (08:36Z y 10:09Z, tras cambiar el código):

```
StageStarted   unit-tests
StageFinished  unit-tests  success
```

Sin `StepStarted`, sin `EchoOutputCaptured`, sin salida. Los cinco
stages terminan en `success` y el run entero en `success`, en 7–16
segundos, sin que se haya ejecutado un solo test.

## Por qué importa

`AGENTS.md` define la CI local como la única autoridad para declarar el
repositorio verificado. Si un stage de tests puede reportar `success`
sin ejecutar nada, entonces **un pipeline en verde no prueba que los
tests hayan pasado**. La distinción importa especialmente después de
un cambio que toca `src/`, que es justo cuando el verde significa algo.

La clave de caché es el **hash del script** (`.pipeline.kts`), no el
commit. Es la misma `d7b5eb81…` en los tres runs con HEAD distinto. Y
`pipelinek` reutiliza además el mismo `runId` en todas las
invocaciones, así que consultar "el último run" por `runId` agrega
varias ejecuciones y mezcla un `StepFailed` antiguo con el `success`
actual.

## Consecuencia practica

Un run en verde solo es evidencia si el journal muestra
`StepStarted` + `EchoOutputCaptured` para el stage `unit-tests`. Un
`StageFinished success` a secas es un caché hit y no prueba nada.

Mientras tanto, la verificación real se puede hacer replicando los
comandos del script directamente, que es lo que se hizo para este
commit: `uv sync --dev`, `uv run pytest --no-header -q` (con
cobertura, que es la configuración del repo), `uv run ruff check src
tests`, y las dos comprobaciones de `.pipelinek/control/`.

## Lo que NO se ha hecho

No se ha modificado `.pipeline.kts` para forzar la invalidación. El
cambio podría ser añadir el commit a la clave de caché, o ejecutar
los tests fuera del mecanismo cacheable, pero ambas son decisiones
sobre la CI local y tocan la autoridad de verificación del proyecto:
un `pipelinek` que no ejecuta lo que dice ejecutar es peor que uno
lento. Queda abierto.

## Reconfirmado 2026-09-28 (commit `dfc70c8`)

El defecto sigue vigente y **es peligroso por su forma**, no por lo
que falla: un run que no ejecutó nada y aun así termina en
`Pipeline finished with SUCCESS`.

Lo observado tras el refactor de `pack_loader` (HEAD `dfc70c8`):

```
$ pipelinek run --db .pipelinek/db.sqlite --control-root .pipelinek/control .pipeline.kts
Pipeline finished with SUCCESS      <- exit code 0
```

Un verde de este tipo es **falso**. La inspeccion del journal
(`events` filtrado por el ultimo `CompilationStarted`) da:

```
run_id: f9db5154-8345-49c3-acd8-eab2dd902bcc | eventos: 12
StageFinished  discover-repo  -> success
StageFinished  sync-deps      -> success
StageFinished  unit-tests     -> success      <- sin StepStarted
StageFinished  evidence       -> success
RunFinished                     -> success
```

Sin `StepStarted` ni `EchoOutputCaptured` en `unit-tests`: es un cache
hit, no una ejecucion. El ultimo run **real** de esa misma base es de
las 06:57Z con **1413 tests**, mientras que el codigo de `dfc70c8`
tiene **1455**. Es decir: la CI verde de las 15:19Z nunca vio este
cambio.

## Workaround verificado: journal y control-root nuevos

Un `--db` y un `--control-root` limpios fuerzan la ejecucion real,
porque la clave de cache cuelga del estado del control root y no del
script:

```bash
pipelinek run --db "$SCRATCH/pipeline-fresh.sqlite" \
              --control-root "$SCRATCH/pipeline-control" .pipeline.kts
```

Es lo que se debe usar mientras el defecto siga abierto: el
`Pipeline finished with SUCCESS` de un control root limpio sí es
evidencia, y se distingue de un cache hit porque el journal muestra
`StepStarted` + `EchoOutputCaptured` con la cuenta de tests.

## Regla operativa mientras tanto

`Pipeline finished with SUCCESS` **no basta**. Antes de citar un run
como evidencia hay que comprobar en el journal que el stage
`unit-tests` emitio `StepStarted` y `EchoOutputCaptured`. Si no los
emitio, el verde es decorativo y la verificacion real se hace
replicando los comandos del script.

