# SkillGraph Bench

Suite de **benchmarks** (no tests) para los nucleos criticos del
sistema. Mide tiempos de las rutas calientes para detectar regresiones
de rendimiento y guiar optimizaciones.

## Filosofia

- **Observabilidad, no cobertura**: los benches viven fuera de
  ``src/skillgraph/`` y NO se cuentan en la cobertura productiva.
- **Sin red, sin reloj oculto**: usa ``time.perf_counter_ns`` local,
  el corpus es sintetico (Storage SQLite en tempdir).
- **Determinismo razonable**: medianas sobre N repeticiones; acepta
  ~10% de jitter por JIT/GC sin alarmarse.
- **Portable**: solo stdlib + las dependencias del proyecto.

## Modulos

| Modulo | Mide |
| --- | --- |
| `bench/bench_context.py` | `ContextController.compile_handoff` y `refresh_handoff` sobre un corpus sintetico de N claims. |

## Uso rapido

```bash
# Bench por defecto (10 / 100 / 1000 claims) con tabla humana:
mise exec -- python -m bench.bench_context

# Sizes custom:
mise exec -- python -m bench.bench_context --sizes 50 500 5000

# Solo JSON (para CI / pipelines):
mise exec -- python -m bench.bench_context --json > bench-2026-09-25.json
```

## Salida (formato humano)

```text
| claims | src | compile_cold(ms) | compile_warm(ms) | refresh_warm(ms) | included | hash |
| --- | --- | --- | --- | --- | --- | --- |
| 10    | 2   | 0.551            | 0.296            | 0.323            | 10       | `ff8d7b793724` |
| 100   | 15  | 2.734            | 2.507            | 2.570            | 100      | `8ba0b4bd5861` |
| 1000  | 143 | 31.xxx           | ...              | ...              | 1000     | `xxxxxxxxxxxx` |
```

## Salida (formato JSON)

```json
{
  "schema": "skillgraph.bench.v1",
  "python_version": "3.13.15",
  "rows": [
    {
      "claims": 10,
      "sources": 2,
      "entities": 2,
      "compile_cold_ms": 0.551,
      "compile_warm_median_ms": 0.296,
      "refresh_warm_median_ms": 0.323,
      "included_count": 10,
      "context_hash": "ff8d7b793724"
    }
  ]
}
```

## Interpretacion

- **compile_cold**: incluye warm-up de SQLite (preparacion de stmts,
  carga de modulos). Es el coste de la primera llamada en un proceso
  nuevo.
- **compile_warm**: mediana de N repeticiones. Representa el coste
  steady-state de la operacion principal.
- **refresh_warm**: coste de `refresh_handoff` con un `previous_hash`
  valido. Idealmente deberia ser O(1) si no hay cambios (hoy siempre
  recompila — el bench revela la oportunidad de cache).

Reglas de pulgar para regresiones:

| Delta en `compile_warm` | Severidad |
| --- | --- |
| `< 5%`                  | ruido     |
| `5% - 20%`              | revisar   |
| `> 20%`                 | regresion |

## Tests de smoke

`tests/test_bench_smoke.py` valida:

- Exit code 0 en corrida default.
- Schema JSON estable (`skillgraph.bench.v1`).
- `--sizes` respeta la cantidad solicitada.
- Cada row lleva hash de 12 chars + `included_count` correcto.

No ejecuta assertions sobre timings (eso seria fragil en CI).

## Diseno del corpus sintetico

- N claims distribuidas en `ceil(N/7)` sources.
- Cada source tiene 1 entity + hasta 7 claims (una por predicado
  canonico de `CLAIM_PREDICATES`).
- Esto respeta la unicidad
  `(subject, predicate, source, checked_at_revision)` y produce un
  volumen realista sin necesidad de fixtures externas.
