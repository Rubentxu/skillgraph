# Release receipt — v0.16.8

| Campo | Valor |
|---|---|
| Tag | `v0.16.8` (anotada) |
| Objeto de etiqueta remoto | `2afe78ea93afdae4b499e414fe0aa2ecb22aef82` |
| Peel remoto de la etiqueta | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| `origin/main` | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| `__version__` en el tag | `0.16.8` (SemVer puro, verificado con `git show v0.16.8^{}:src/skillgraph/__init__.py` **antes** de publicar) |
| Tag anterior | `v0.16.7` (peel `0fc7018`) |
| Commits incluidos | 13 (`4d64ad6..df72bcc`) |
| Suite completa | **1754 passed** en 450.62s |
| Release governance gate | 2 passed |
| Publicación | `origin/main` = `df72bcc`, etiqueta `v0.16.8` en el remoto con peel verificado |
| Fecha | 2026-09-29 |

## SemVer derivado del historial (no decidido a mano)

Conteo real de `git log --format=%s v0.16.7..HEAD` en el momento de
etiquetar:

| Tipo | Conteo | Efecto en SemVer |
|---|---|---|
| `refactor` | 5 | ninguno (cambia la forma, no el contrato) |
| `test` | 2 | ninguno |
| `chore` | 5 | ninguno |
| `docs` | 2 | ninguno |
| `feat` | 0 | — |
| `fix` | 0 | — |
| breaking | 0 | — |

**PATCH.** MINOR descartado por no haber `feat`; MAJOR descartado por
no haber breaking change. 13 commits, ninguno de ellos entrega
capacidad nueva a nivel de release.

## Contenido

### `docs(architecture)` (26dd8bc) — ADR-0016

Descompone el god-module `platform/storage.py` en componentes reales.
Decide el patrón (strangler de 5 cortes), la propiedad de la conexión
(`Storage._conn` compartida, `_tx`/`_atomic` resueltas late para no
romper el monkeypatching de H9/H10) y la regla de cero ediciones en
callers (REQ-WI56-1/I1).

### `refactor(storage)` × 5 — los cinco cortes

| Corte | Commit | Componente |
|---|---|---|
| 1 | `ce0f291` | `SqliteRunRepository` |
| 2 | `7001479` | `SqlitePolicyStore` |
| 3 | `c125715` | `SqliteKnowledgeRepository` |
| 4 | `6895725` | `SqliteEventStore` |
| 5 | `f439c74` | `SqlitePromotionRepository` |

Cada corte tiene su red de contrato escrita **antes** del refactor, con
RED honesto: el test fallaba solo por la identidad del facade, no por
comportamiento roto. Los accessors del facade (`Storage.run_repository()`
etc.) devolvían antes un shim `-> self` por structural subtyping ( WI-31)
y ahora devuelven el componente real.

SQL vivo restante en `storage.py`: únicamente DDL (`_SCHEMA_SQL`),
`_migrate` y los helpers atómicos `_insert_event_in_tx` /
`_atomic_state_and_event`. **2837 → 1807 LoC** (−36%).

### `chore(repo)` (8eda4ea) — el fallo que bloqueaba la release

`.jcode-scratch/` no estaba en `.gitignore`. Es el directorio donde se
escriben los journals de `pipelinek` con journal fresco y los recibos
en curso, así que **cada verificación dejaba entradas no versionadas
en `git status --porcelain`**. Ese árbol limpio es requisito explícito
del paso 1 del checklist de release de SDDK
(`prompts/sddk/phases/release.md`): el propio acto de verificar
bloqueaba la release que estaba verificando.

Verificado con `git check-ignore -v` →
`.gitignore:54:.jcode-scratch/`.

### `docs(release)` (df72bcc) — tres derbes de documentación

- **`STATE.yaml`**: declaraba 27 releases pero la lista terminaba en
  v0.16.0. Siete releases publicadas (v0.16.1..v0.16.7) no estaban
  registradas. Rehechas con SHA, fecha y nota reales, cada SHA
  verificado contra `git rev-list -1 <tag>` y `git rev-parse <tag>`.
  El bloque `release:` cabecera pasa de v0.16.0 a v0.16.8.
- **`CHANGELOG.md`**: mismo hueco. Las siete versiones existían como
  etiqueta y como commits, pero no como entradas.
- **`CURRENT.md`**: seguía diciendo «RELEASE v0.16.8 EN PREPARACION».
- Journal de CI persistido en `evidence/pipelinek/journal-8eda4ea.sqlite`.

## Verificación

| Comprobación | Resultado |
|---|---|
| `pipelinek run` (journal fresco) | `Pipeline finished with SUCCESS`, 1754 passed in 450.62s, `StepStarted` 8, `StepFailed` 0 |
| Journal de CI persistido | `evidence/pipelinek/journal-8eda4ea.sqlite`, sha256 `8c7d8a4d…`, 53248 bytes |
| `ruff check src tests` | limpio (`All checks passed!` en el journal) |
| `ruff format --check src tests` | 188 archivos ya formateados (pre-commit) |
| Release governance gate | 2 passed |
| `yaml.safe_load(STATE.yaml)` | OK, 35 releases listadas |
| `origin/main` | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| Etiqueta remota | objeto `2afe78e`, peel `df72bcc` |
| Permisos | `sddk-release` permitido para `git.tag` y `git.push` en fase `release` |

Los cinco criterios de éxito de `AGENTS.md` se verificaron uno a uno
sobre el run genuino, no sobre un cache hit.

## La CI verde no es evidencia por sí sola

Este repositorio ya tiene documentada una trampa: `pipelinek` produce
`Pipeline finished with SUCCESS` sin ejecutar un solo test cuando el
cache de compilación acierta. Un run de cache tiene `StageFinished` y
cero `StepStarted`. Citar ese verde como verificación habría sido
falso, y ya pasó en v0.16.5.

Por eso el run de esta release se lanzó con journal y control-root
limpios, y el journal se inspeccionó evento a evento antes de dar la
release por buena: 38 eventos, `StepStarted` 8, `StepFailed` 0, y el
contenido capturado del stage de tests dice literalmente
`1754 passed in 450.62s`.

## Bloqueantes

### B1 — `sddk release plan` exige `Cargo.toml` (sigue vigente)

```
$ sddk release plan --tag v0.16.8
error: VERSION LOCKSTEP ERROR: could not read …/Cargo.toml:
No such file or directory (os error 2)
```

Re-verificado hoy sobre el framework **2.0.1**, no heredado de la
sesión anterior. El proyecto es Python (hatchling + uv) y su única
fuente de verdad de versión es `src/skillgraph/__init__.py:__version__`
(regla 12 de `AGENTS.md`). El binario de SDDK tiene 0 referencias a
`pyproject`.

**No se fabrica un `Cargo.toml`.** La release se hizo por el camino
manual ya documentado desde v0.16.4: commit con versión pura, etiqueta
anotada, verificación del peel, push, y comprobación independiente del
estado remoto. Es más lento que el planner, pero no miente sobre la
naturaleza del proyecto.

### B2 — cerrado

`permissions.yaml` ausente **no** era una carencia del framework, era un
archivo del proyecto que este repositorio no declaraba. Ya existe con
contenido real y `sddk permission check` devuelve `allowed: true` para
`git.tag` y `git.push`. No se fabricó un registro de permisos: se
declaró uno con los agentes y capacidades que el trabajo realmente
ejerce.

### B3 — rama del genesis inexistente (sigue abierto)

El ledger del ciclo `wi-45` registra `feat/wi-45-uow-coverage`, que
nunca existió en el evento inmutable `cycle.created`. El ledger es
append-only: corregirlo está prohibido. No bloquea la release, pero
impide que `release.complete` de ese ciclo se registre limpiamente.

## Deuda que esta release deja visible

- **Realimentación infinita de la evidencia UAT**:
  `tests/uat_audit.py` graba `git rev-parse HEAD` dentro del propio
  JSON de evidencia. Cada commit invalida la evidencia del commit
  anterior y vuelve a ensuciar el árbol. No es un bug de esta release
  sino del diseño del auditor, y explica por qué la sesión anterior
  encontró el árbol sucio al empezar. Arreglarlo es un cambio de
  contrato del formato de evidencia y merece su propio ciclo.
- **Defecto de caché de `pipelinek`**: sigue abierto y deliberadamente
  no tocado, porque corregirlo exige modificar `.pipeline.kts`, que es
  la autoridad de verificación del proyecto. Decisión del mantenedor.

## Procedimiento reproducido

```bash
# 1. gates locales
uv run pytest -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run pytest tests/test_release_governance.py -q     # falla: estado pre-etiqueta

# 2. CI canónica con journal y control-root limpios (fuerza ejecución real)
pipelinek run --db <scratch>/pipeline.sqlite \
              --control-root <scratch>/control .pipeline.kts

# 3. commit con versión pura, etiqueta, y verificación del peel
git tag -a v0.16.8 -m "…" HEAD
git show v0.16.8^{}:src/skillgraph/__init__.py | grep __version__   # 0.16.8 puro
git rev-parse v0.16.8^{}                                          # == HEAD

# 4. gate en verde
uv run pytest tests/test_release_governance.py -q     # 2 passed

# 5. publicar y verificar por lectura independiente
git push origin main && git push origin v0.16.8
git fetch origin main
git ls-remote origin refs/heads/main 'refs/tags/v0.16.8*'
```
