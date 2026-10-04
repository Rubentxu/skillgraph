# B7 — Recibo de implementación

**Ciclo**: `p-b7740b96d79ec013/b7`
**Entrega**: `0d9d423`
**Base**: `218a2e3`

## Qué se entregó

| Fichero | Qué es |
|---|---|
| `src/skillgraph/presentation/views.py` | `Column`, `TableView`, `DetailView` — la forma |
| `src/skillgraph/presentation/widgets.py` | las diez proyecciones — el contenido |
| `src/skillgraph/presentation/__init__.py` | la superficie pública |
| `src/skillgraph/cli/parser.py` | `--format {text,json}` en dos comandos |
| `src/skillgraph/cli/commands/runs.py` | un único `_emit` |
| `tests/test_b7_operational_ux.py` | 23 tests |
| `scripts/measure_b7_operational_ux.py` | el medidor del gate |
| `scripts/mutate_b7_operational_ux.py` | la sonda de los guards |

11 ficheros, 1933 inserciones, 17 borrados.

## Verificación en el momento de la entrega

- Suite completa en el hook del commit: **3085 passed, 3 skipped, 0 failed**
- Tests de B7: **23 passed**
- Medidor del gate: `rc=0`, 0 de 3 huecos abiertos
- Contra-saltos de B7: **3/3**, cada uno con su propia causa
- `tests.total`: 3088, con el desglose medido

## Defectos reales corregidos durante la implementación

1. `to_json` ordenaba con `sorted(fila.items())`, que compara **valores** cuando
   hay empate de clave, y reventaba con `AttributeError` en filas con tuplas.
   Corregido a `sorted(fila)`.
2. `runs show` salía con `TypeError` en el camino de TEXTO — el de por
   defecto — porque `_emit` pasaba `vacio=` a `DetailView.to_text`, que no lo
   acepta. Lo cazó un guard nuevo, por `subprocess`.
3. `return EXIT_OK` duplicado en `cmd_runs_list`, código muerto.
4. El contra-salto del medidor copiaba el repo entero a `/tmp` y fallaba con
   `EDQUOT`. Ahora copia solo `src/` y `scripts/`: 1,1 MB.

## Requisito que se añadió al ejecutar

R6 — B7 no rompe el contrato `clave=valor` de `runs show`. No estaba en el
plan porque no se podía prever: apareció en U3, el cableado entre el comando y
la vista, que es donde la dependencia era más fuerte.
