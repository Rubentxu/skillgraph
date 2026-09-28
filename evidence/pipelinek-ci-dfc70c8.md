# pipelinek CI local — run genuino sobre `dfc70c8`

> Observado el 2026-09-28 con `pipelinek` v0.39.0, `.pipeline.kts` sin
> cambios desde `8ec0645` (sha256 `0665345f…`).

## Por que este run y no el de las 15:19Z

El run de las 15:19Z sobre el journal del repo termino en
`Pipeline finished with SUCCESS` **sin ejecutar un solo test**: fue un
cache hit (ver `pipelinek-cache-does-not-invalidate-on-source-change.md`).
Este run se lanzo con journal y control-root limpios, lo que fuerza la
ejecucion real. Es el unico verde de esta sesion que se puede citar.

## Command

```bash
pipelinek run --db "$SCRATCH/pipeline-fresh.sqlite" \
              --control-root "$SCRATCH/pipeline-control" .pipeline.kts
```

## Resultado

```
Pipeline finished with SUCCESS      (exit code 0)
```

Journal: `evidence/pipelinek/journal-dfc70c8.sqlite`
sha256 `d1bdb47d4806264577f721d3b0c17bf06c12249eed8e201ca025035bead6cd5f`
(53248 bytes)

## Criterios de exito de AGENTS.md, uno a uno

| # | Criterio | Verificacion |
|---|----------|--------------|
| 1 | `Pipeline finished with SUCCESS` terminal | OBSERVED, exit 0 |
| 2 | Journal con eventos tipados | `CompilationStarted` 1, `RunStarted` 1, `StageStarted` 5, `StepStarted` 8, `EchoOutputCaptured` 8, `StageFinished` 5, `RunFinished` 1 |
| 3 | Control root con los cuatro directorios | `last-run`, `retry-control`, `wait-until-control`, `workspace` |
| 4 | Cero `StepFailed` y cero `RunFinished/failure` | `StepFailed: 0`, unico `RunFinished` con `outcome: success` |
| 5 | sha-256 de `.pipeline.kts` sin drift | `0665345f…`, ultimo cambio en `8ec0645` |

## Evidencia de que los tests se ejecutaron de verdad

A diferencia de los cache hits, este run tiene `StepStarted` y
`EchoOutputCaptured` en el stage `unit-tests`, y la cuenta coincide con
el codigo de `dfc70c8`:

```
1455 passed in 438.37s (0:07:18)
StageFinished unit-tests success
All checks passed!          <- lint
last-run present            <- evidence
workspace tracking present  <- evidence
RunFinished success
```

Los 1455 son los tests del codigo con el refactor de `pack_loader`
incluido. El ultimo run real sobre el journal del repo era de las
06:57Z con **1413**: la diferencia (42 tests) es exactamente lo que ese
verde decorativo no habia visto.

## Stages ejecutados

`discover-repo`, `sync-deps`, `unit-tests`, `lint`, `evidence` — los
cinco, todos `success`, ninguno de cache.
