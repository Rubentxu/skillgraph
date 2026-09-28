# pipelinek CI para el refactor de `WorkflowNode.__post_init__`

Corrida de `pipelinek` que valida los dos commits de este bloque:

- `21087d1` — `fix(workflow): rechazar bool en metadata.max_visits`
- `2d55c8d` — `refactor(workflow): bajar cc=12 a cc=1`

## Por que journal y control-root nuevos

El defecto documentado en
`evidence/pipelinek-cache-does-not-invalidate-on-source-change.md` hace que
reutilizar el journal `.pipelinek/db.sqlite` pueda devolver
`Pipeline finished with SUCCESS` sin ejecutar un solo `StepStarted`. Un
verde con journal reutilizado no es evidencia de nada.

Por eso esta corrida usa rutas limpias:

```bash
pipelinek run --db evidence/pipelinek/refactor-21087d1/journal.sqlite \
              --control-root evidence/pipelinek/refactor-21087d1/control \
              .pipeline.kts
```

## Resultado observado

| Dato | Valor |
|---|---|
| Linea terminal | `Pipeline finished with SUCCESS` |
| Tests | 1489 passed in 300.98s (0:05:00) |
| Lint | `All checks passed!` |
| Stages | `discover-repo`, `sync-deps`, `unit-tests`, `lint`, `evidence` — todas `success` |
| Ultimo evento | `RunFinished` `outcome=success`, `diagnostics=[]` |
| SHA-256 del journal | `97e0b81e2306e776ba5ef11d6d87180cd492ded2998e3f1db1533bf729bcd3bb` |

El journal contiene 38 eventos con `StepStarted` reales en los cinco
stages, que es justo lo que faltaba en la corrida cacheada que se
documento como defecto.

## Nota

El pre-commit hook del repositorio tambien ejecuta la suite completa
antes de dejar pasar cada commit, asi que `21087d1` y `2d55c8d` fueron
validados dos veces de forma independiente.
