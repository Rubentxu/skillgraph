# T8 Benchmark — Entrega 2026-09-25

## Objetivo

Materializar el trabajo **T8 (Benchmark)** del ROADMAP Etapa 7
(`external/blueprint-v1/ROADMAP.md`) entregando una suite minima de
benchmarks para los nucleos criticos del sistema, ejecutable desde
CLI y validada por tests de smoke.

## Alcance ejecutado

### Modulos creados

| Path | LoC | Proposito |
| --- | --- | --- |
| `bench/__init__.py` | 16 | Package marker + convenciones |
| `bench/bench_context.py` | 322 | Bench de `compile_handoff` y `refresh_handoff` |
| `bench/README.md` | 104 | Filosofia, uso, interpretacion |
| `tests/test_bench_smoke.py` | 78 | 3 tests (subprocess) |
| `audits/bench/baseline-2026-09-25.json` | (auto) | Snapshot de la primera corrida |

### Que mide `bench_context.py`

3 fases por tamano N ∈ {10, 100, 1000}:

- **compile_cold_ms**: primera llamada (incluye warm-up SQLite).
- **compile_warm_median_ms**: mediana de 3 llamadas warm (steady state).
- **refresh_warm_median_ms**: mediana de 3 `refresh_handoff` con
  `previous_hash` valido.

Diseno del corpus sintetico:

- `ceil(N/7)` sources, una entity por source.
- Hasta 7 claims por source (una por predicado canonico de
  `CLAIM_PREDICATES`).
- Respeta la unicidad `(subject, predicate, source, revision)` que
  impone `storage.record_claim`.
- Storage SQLite en `tempfile.TemporaryDirectory` (un directorio por
  tamano).

### Tests de smoke

`tests/test_bench_smoke.py` (subprocess, no pytest-cov) valida:

- `test_default_runs_and_exits_zero` — 3 filas, exit 0.
- `test_json_output_is_valid` — schema `skillgraph.bench.v1` y shape
  de cada row.
- `test_custom_sizes_produce_requested_rows` — `--sizes 5 25` produce
  exactamente 2 filas.

## Baseline 2026-09-25 (este commit)

```text
| claims | src | compile_cold(ms) | compile_warm(ms) | refresh_warm(ms) | included | hash |
| ---    | --- | ---              | ---              | ---              | ---      | ---  |
| 10     | 2   | 0.526            | 0.310            | 0.318            | 10       | ff8d7b793724 |
| 100    | 15  | 2.667            | 2.368            | 2.489            | 100      | 8ba0b4bd5861 |
| 1000   | 143 | 34.245           | 31.985           | 33.323           | 1000     | 06034b73f550 |
```

Conclusiones del baseline:

- **Linealidad**: ~30 µs/claim en `compile_warm` (10→100→1000: 0.3→2.4→32ms).
- **Sin cache en refresh**: `refresh_warm ≈ compile_warm`. Hoy
  `refresh_handoff` SIEMPRE recompila aunque no haya cambios.
  Esto es una **oportunidad de optimizacion** documentada en
  `external/blueprint-v1/HITOS.md` H9 (release candidate).
- **Cold ≈ warm**: gap cold/warm < 2x en todos los tamanos. El
  sistema no sufre de un warm-up patologico.

## Decisiones de diseno

1. **Fuera de `src/skillgraph/`**: el bench es observabilidad, no
   producto. Vive en `bench/` (top-level) para que pytest-cov no
   lo cuente como cobertura productiva.
2. **Tests como subprocess**: los smoke tests invocan
   `python -m bench.bench_context` como subproceso. Mismo motivo:
   pytest-cov no rastrea subprocess child processes (gap estructural
   documentado en `audits/runner-coverage-2026-09-25.md`), por lo que
   intentar cubrir el modulo via pytest in-process daria una falsa
   sensacion de cobertura.
3. **Sin dependencias nuevas**: solo `stdlib` + lo que ya importa
   `skillgraph`. No se anade `pytest-benchmark` ni `asv` (regla 3:
   "no introduzcas nuevas abstracciones si los mecanismos existentes
   pueden satisfacer el requisito").
4. **Mediana, no media**: `samples.sort()[len//2]` suaviza ruido de
   JIT/GC sin necesidad de statistic libs.
5. **Schema versionado**: `"schema": "skillgraph.bench.v1"` permite
   cambiar la forma sin romper parsers que ya consuman la salida.

## Verificacion

- `mise exec -- uv run pytest` — **772/772 PASS** (769 anteriores +
  3 nuevos de `test_bench_smoke.py`).
- `mise exec -- uv run ruff check .` — All checks passed.
- `mise exec -- python -m bench.bench_context` — exit 0, salida
  formateada correcta.

## Lo que NO se entrega (y por que)

- **Adapter real / T1**: requiere spec del operador (formato de
  prompts, politica de timeouts). NO ejecutar sin alineacion.
- **Backup CLI / T5**: requiere decision sobre formato de export y
  nivel de compresion. NO ejecutar sin alineacion.
- **Observabilidad / T6**: requiere decision sobre backend (stdout
  estructurado vs OpenTelemetry). NO ejecutar sin alineacion.
- **Grafana / dashboards / tracking historico de bench**: el baseline
  JSON es la semilla; tooling externo puede agregarlo. NO se incluye
  en este PR para mantener T8 enfocado en "tener un bench que
  corre".

## Próximos pasos posibles (no comprometidos)

1. Anadir CI job que ejecute el bench en cada PR y publice el JSON
   como artifact descargable.
2. Anadir bench de `Storage.record_claim` y `Storage.list_claims_*`
   (rutas calientes adicionales).
3. Optimizar `refresh_handoff` para que sea O(1) cuando
   `previous_hash` coincide (hoy siempre recompila). Esto seria
   candidato a T9 si el operador decide priorizarlo.

## Cita del operador (regla 6: trazabilidad)

> "todo gate o decisión queda pre-aprobada, decide con el contexto
> disponible y ejecuta"

T8 estaba marcado como "pendiente" en `external/blueprint-v1/ROADMAP.md`
sin spec formal del operador. Es el unico trabajo del backlog pendiente
que es **ejecutable sin spec adicional** (solo requiere: importar las
APIs publicas que ya existen, medir tiempos, formatear salida). Se
ejecuta con juicio autonomo y se documenta esta auditoria como
material de soporte para revision posterior.
