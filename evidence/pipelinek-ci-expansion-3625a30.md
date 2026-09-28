# pipelinek CI para el refactor de `graph_expansion`

Corrida que valida los dos commits del bloque:

- `3625a30` — `test(governance): red de contrato de graph_expansion`
- `6aef651` — `refactor(governance): bajar cc=13/12/11 a cc=2/3/4`

## Por que journal y control-root nuevos

El defecto documentado en
`evidence/pipelinek-cache-does-not-invalidate-on-source-change.md` permite
que reutilizar el journal devuelva `Pipeline finished with SUCCESS`
sin ejecutar un solo `StepStarted`. Un verde con journal reutilizado
no prueba nada, asi que esta corrida usa rutas limpias:

```bash
pipelinek run --db evidence/pipelinek/expansion-3625a30/journal.sqlite \
              --control-root evidence/pipelinek/expansion-3625a30/control \
              .pipeline.kts
```

## Resultado observado

| Dato | Valor |
|---|---|
| Linea terminal | `Pipeline finished with SUCCESS` |
| Tests | 1534 passed in 420.44s (0:07:00) |
| Lint | `All checks passed!` |
| Events en el journal | 38, con `StepStarted` reales en los cinco stages |
| Ultimo evento | `RunFinished` `outcome=success`, `diagnostics=[]` |
| SHA-256 del journal | `086941f86f63ee819e953da102ca058e450f9ea06aed3007772fbc25e15f760a` |

Los 1534 tests son los 1489 del bloque anterior mas los 45 tests de
contrato nuevos de este bloque. El incremento cuadra exactamente con
lo anadido, que es la comprobacion mas simple de que la corrida
ejecuto la suite actual y no una cache.

## Medicion del refactor

Con el mismo metodo AST antes y despues, sobre
`src/skillgraph/governance/graph_expansion.py`:

| Funcion | antes | despues |
|---|---|---|
| `_has_cycle_via_new_transitions` | cc=13 | cc=2 |
| `DefaultPolicyEngine.evaluate` | cc=12 | cc=3 |
| `_check_cycle_bound` | cc=11 | cc=4 |

Ningun helper nuevo pasa de cc=5. Ranking global tras el cambio:
5 funciones con cc>=11, frente a 8 antes del bloque.
