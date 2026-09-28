# Release receipt — v0.16.5

| Campo | Valor |
|---|---|
| Tag | `v0.16.5` (anotada, objeto `50aaa1f`) |
| Commit etiquetado | `15258c0` |
| `__version__` en el tag | `0.16.5` (SemVer puro, verificado con `git show v0.16.5^{}:src/skillgraph/__init__.py` **antes** de publicar) |
| Tag anterior | `v0.16.4` (peel `7d5aa91`) |
| Commits incluidos | 3 (`e647ee7`, `dfc70c8`, `9079012`) |
| Suite completa | 1455 passed |
| `domain/pack_loader.py` | cc 13 → 3, nesting 5 → 2, cobertura 95% |
| Release governance gate | 2 passed |
| Publicación | `origin/main` = `15258c0`, tag `v0.16.5` en el remoto |
| Fecha | 2026-09-28 |

## SemVer derivado del historial (no decidido a mano)

Conteo real de `git log --format=%s v0.16.4..HEAD`:

| Tipo | Conteo | Efecto en SemVer |
|---|---|---|
| `refactor` | 2 | ninguno (sin cambio de contrato) |
| `test` | 1 | ninguno |
| `chore` | 2 | ninguno |
| `docs` | 1 | ninguno |
| `feat` | 0 | — |
| breaking | 0 | — |

PATCH. MINOR descartado por no haber `feat`; MAJOR descartado por no
haber breaking change. La regla es que un `refactor` no sube la versión
menor: cambia la forma, no el contrato.

## Contenido

### `refactor(cli)` (e647ee7) — `cmd_promotion_reconcile` cc 14 → 7

Extraídas `_select_promotion_failpoint`, `_abort_with_failpoint`,
`_apply_pending_promotions` y `_reconcile_summaries`.

De paso se implementó el failpoint `after_apply_first`, que estaba
**documentado pero no existía**. Esto no es cosmético: el failpoint
simula la caída en el punto más peligroso de la promoción, cuando la
claim ya está en el destino pero el outbox aún no está `PUBLISHED`. Con
él existe un test de subprocess que prueba el estado de split real y
que la reconciliación lo reanuda de forma idempotente.

### `refactor(domain)` (dfc70c8) — `_make_schema_validator` cc 13 → 3, nesting 5 → 0

El esquema de un campo admite tres formas y solo tres: tipo primitivo,
`list_of` y `refs`. Estaban codificadas como una cadena de `isinstance`
anidados, y además dentro de un closure, de modo que la auditoría
atribuía al factory la complejidad de todas sus reglas.

- Las reglas pasan a funciones de módulo con `_FieldContext` explícito
  en vez de capturar `kind`. Cada una es medible y testeable por
  separado.
- El despacho pasa a `match`/`case`, que es lo que corresponde a un
  dominio cerrado (regla 2.1 de `AGENTS.md`).

Medido con `audits/audit_debt.py`:

| | antes | después |
|---|---:|---:|
| `_make_schema_validator` cc | 13 | 3 |
| `_make_schema_validator` nesting | 5 | 2 |
| Entradas en "anidamiento profundo (>=5)" | 2 | 0 |

Con esto quedan cerrados **los dos hotspots reales** que la auditoría
corregida exponía, y con ellos el backlog item
`bl-bl-01M3M2QG8500038785DM19QD00`.

Comportamiento intacto, incluida la precedencia cuando un dict declara
`list_of` y `refs` a la vez (`list_of` gana, igual que antes). Los 14
tests nuevos fijan el contrato de cada fila del despacho, así que el
comportamiento no depende de la forma interna.

### `test(ci)` (9079012) — la CI verde no ejecutaba tests

El run de `pipelinek` de las 15:19Z devolvió
`Pipeline finished with SUCCESS` **sin ejecutar un solo test**. No es
interpretación: ese run tiene cinco `StageFinished` y cero
`StepStarted`. El último run real de esa base era de las 06:57Z con
1413 tests, mientras el código tenía 1455.

Es decir, la CI verde de esa sesión nunca vio los refactors de este
release. Citar ese verde como verificación habría sido falso.

El commit deja el workaround verificado (journal y control-root
limpios fuerzan la ejecución real: 1455 passed), el journal
persistido en `evidence/pipelinek/` con su sha256, y la regla
operativa: un verde no es evidencia hasta que el journal muestra
`StepStarted` + `EchoOutputCaptured` en el stage de tests.

## Verificación

| Comprobación | Resultado |
|---|---|
| Suite completa | 1455 passed |
| `ruff check src tests` | limpio |
| `ruff format --check src tests` | 173 archivos ya formateados |
| Release governance gate | 2 passed |
| pipelinek (run genuino) | `Pipeline finished with SUCCESS`, 5 stages, `StepFailed: 0` |
| Journal de CI persistido | `evidence/pipelinek/journal-dfc70c8.sqlite`, sha256 `d1bdb47d…` |
| `origin/main` | `15258c0` |
| Tag remoto | `refs/tags/v0.16.5` = `50aaa1f`, peel `15258c0` |

Los cinco criterios de éxito de `AGENTS.md` se verificaron uno a uno
sobre el run genuino, no sobre un cache hit. Ver
`evidence/pipelinek-ci-dfc70c8.md`.

## Secuencia de versión respetada

1. HEAD con `__version__ = "0.16.4.dev0"` (trabajo en curso).
2. Commit `15258c0` con `0.16.5` puro — el gate falla aquí, que es lo
   correcto: HEAD sin etiquetar no puede llevar versión pura.
3. Etiqueta `v0.16.5` sobre `15258c0` → gate **2 passed**.
4. Commit posterior con `0.16.5.dev0` (trabajo tras la etiqueta).

La comprobación de que el commit etiquetado lleva la versión pura se
hizo **antes** de crear la etiqueta y **antes** de publicar nada, que
es exactamente el error que se cometería sin mirar y que ya se detectó
una vez en `v0.16.4`.

## Bloqueantes

### B1 — `sddk release plan` exige `Cargo.toml` (sigue vigente)

```
$ sddk release plan --tag v0.16.5
error: VERSION LOCKSTEP ERROR: could not read …/Cargo.toml:
No such file or directory (os error 2)
```

El proyecto es Python (hatchling + uv) y su única fuente de verdad de
versión es `src/skillgraph/__init__.py:__version__` (regla 12 de
`AGENTS.md`). El binario de SDDK tiene 0 referencias a `pyproject`.

**No se fabrica un `Cargo.toml`.** La release se hizo por el camino
manual ya documentado para `v0.16.4`: commit con versión pura,
etiqueta anotada, receipt, push. Es más lento que el planner, pero no
miente sobre la naturaleza del proyecto.

### B2 — diagnóstico falso, ya refutado

`permissions.yaml` ausente no es un defecto del framework: es un
archivo del proyecto. Ver `evidence/b1-b2-diagnosis-correction.md`. No
se fabricó un registro de permisos para desbloquear nada.

### B3 — rama del genesis inexistente

El ledger del ciclo registra `feat/wi-45-uow-coverage`, que nunca
existió en el evento inmutable `cycle.created`. El ledger es
append-only: corregirlo está prohibido. No bloquea el release, pero
impide que `release.complete` quede registrado en SDDK.

## Estado de la deuda tras este release

- Cero hotspots públicos con cc >= 20 (máximo medido: 12).
- Cero funciones con anidamiento >= 5.
- Backlog de SDDK **vacío**: los dos items registrados
  (`bl-bl-01M3M2QG8500038785DM19QD00` y `bl-bl-01M3M03BX9000387804E2AGXM0`)
  se promovieron a `wi-45-uow-coverage`, que es el ciclo que realmente
  resolvió su trabajo. `BACKLOG.md` vuelve a estar vacío porque ya no
  queda trabajo registrado pendiente.
- Siguiente ranking medido, si se quiere continuar:
  `__post_init__` de `resources/workflow.py` cc=12,
  `_reconcile_run_locked` cc=11, `__post_init__` de
  `governance/receipts.py` cc=11.
- Deuda abierta y **deliberadamente no tocada**: el defecto de caché
  de `pipelinek`. Corregirlo exige tocar `.pipeline.kts`, es decir la
  autoridad de verificación del proyecto. Es decisión del mantenedor.

## Procedimiento reproducido

```bash
# 1. suite y gates
uv run pytest -q
uv run ruff check src tests && uv run ruff format --check src tests

# 2. commit con versión pura, tras verificar que el gate aún falla
#    (estado intermedio esperado)
uv run pytest tests/test_release_governance.py -q   # 1 failed, 1 passed

# 3. commit y etiqueta
git commit -m "chore(release): v0.16.5, commit que etiqueta el release"
git show HEAD:src/skillgraph/__init__.py | grep __version__   # 0.16.5 puro
git tag -a v0.16.5 -m "…" HEAD

# 4. gate en verde
uv run pytest tests/test_release_governance.py -q   # 2 passed

# 5. publicar y verificar en el remoto
git push origin main && git push origin v0.16.5
git ls-remote origin refs/heads/main refs/tags/v0.16.5
```
