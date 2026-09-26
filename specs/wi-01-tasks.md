# WI-01 — Tasks (release & integration readiness)

> Cada task es **commit-ready**. El criterio de cierre de cada task
> es **observable** (comando + exit code + evidencia textual). Las
> tasks se ejecutan en orden; el cierre de la última desbloquea
> `apply.verify` y `release`.

## T-01 · Crear el test de release governance

**Commit:** `test(release-governance): contrato __version__ ↔ git tag`

**Cambios:**
- Crear `tests/test_release_governance.py` con la función
  `test_version_matches_git_tag()` que cubra las tres ramas:
  1. HEAD etiquetado `v<X>.<Y>.<Z>` y `__version__` sin sufijo
     `.devN` → deben coincidir.
  2. HEAD no etiquetado o posterior a la etiqueta más reciente →
     `__version__` debe terminar en `.dev0` o `.devN`.
  3. Caso de fallo: `__version__ = "0.7.0.dev0"` con HEAD no
     etiquetado → falla con mensaje "release governance drift".

**Verificación local:**
- `pytest tests/test_release_governance.py -v` exit 1 (rojo)
  porque `__version__ = "0.7.0.dev0"` no cumple ninguna rama.

## T-02 · Bumpear `__version__` a `0.14.1.dev0`

**Commit:** `release(version): bump 0.7.0.dev0 → 0.14.1.dev0`

**Cambios:**
- `src/skillgraph/__init__.py:27`: `__version__ = "0.14.1.dev0"`.

**Verificación local:**
- `python -c "import skillgraph; print(skillgraph.__version__)"`
  imprime `0.14.1.dev0`.
- `pytest tests/test_release_governance.py -v` exit 0 (verde)
  porque rama 2 aplica.

## T-03 · Cambiar `mise.toml` a `--group dev` (PEP 735)

**Commit:** `chore(tooling): uv sync --group dev (PEP 735)`

**Cambios:**
- `mise.toml`: `[tasks.sync] run = "uv sync --group dev"`.
- Añadir `[tasks.release-gate] run = "uv run pytest
  tests/test_release_governance.py -v"`.

**Verificación local:**
- `bash -c "set -e; uv sync --group dev"` exit 0.
- `mise run sync` exit 0.
- `mise run release-gate` exit 0.

## T-04 · Alinear licencia a SPDX Apache-2.0 y subir coverage gate

**Commit:** `chore(pyproject): license SPDX Apache-2.0 + coverage
fail_under=60`

**Cambios:**
- `pyproject.toml`:
  - `license = "Apache-2.0"` (string SPDX, no `text =`).
  - `[tool.coverage.report] fail_under = 60`.
- `LICENSE` permanece intacto.

**Verificación local:**
- `grep -F 'license = "Apache-2.0"' pyproject.toml` exit 0.
- `uv run pytest --cov=skillgraph --cov-fail-under=60 --no-header -q`
  exit 0.

## T-05 · Crear `SECURITY.md`

**Commit:** `docs(security): SECURITY.md con proceso de divulgación`

**Cambios:**
- Crear `SECURITY.md` con:
  - Canal de reporte: GitHub Security Advisories.
  - Ventana: 90 días para vulnerabilidades altas.
  - Formato: divulgación coordinada.
  - Política de no-action para issues públicos sobre vulnerabilidades
    activas.

**Verificación local:**
- `test -f SECURITY.md` exit 0.
- `grep -q "coordinated disclosure" SECURITY.md` exit 0.
- `grep -q "90 days" SECURITY.md` exit 0.

## T-06 · Reconciliar CURRENT.md / STATE.yaml

**Commit:** `docs(state): reconciliar CURRENT/STATE a baseline 918`

**Cambios:**
- `CURRENT.md`: actualizar cifras a `tests 918`,
  `duration 160.74s`, `HEAD <sha tras T-02>`, `SemVer 0.14.1.dev0`,
  fecha `2026-09-26`. Mantener referencia al WI-01 y al pipelinek.
- `STATE.yaml` `tests:`:
  - `total: 918`
  - `passed: 918`
  - `duration_s: 161`
  - añadir `package_version: "0.14.1.dev0"`.

**Verificación local:**
- `grep -F "918" CURRENT.md STATE.yaml` exit 0 en ambos.
- `grep -F "0.14.1.dev0" STATE.yaml` exit 0.

## T-07 · Mover checkpoints superseded a `audits/historical/`

**Commit:** `docs(checkpoints): archivar superseded 2026-09-25 y 2026-09-26`

**Cambios:**
- `git mv SESSION-CHECKPOINT-2026-09-25.md
  audits/historical/`.
- `git mv SESSION-CHECKPOINT-2026-09-26.md
  audits/historical/SESSION-CHECKPOINT-2026-09-26-superseded.md`.
- Mantener `SESSION-CHECKPOINT-2026-09-26-FIN.md` en raíz como
  cierre provisional.

**Verificación local:**
- `ls audits/historical/ | grep SESSION-CHECKPOINT` exit 0
  muestra los dos movidos.
- `test -f SESSION-CHECKPOINT-2026-09-26-FIN.md` exit 0.

## T-08 · Entradas en CHANGELOG y SESSION-JOURNAL

**Commit:** `docs(changelog+journal): entrada 0.14.1 + erratum v0.14.0`

**Cambios:**
- `CHANGELOG.md`: nueva entrada al tope:
  ```
  ## [0.14.1] - 2026-09-26

  ### Release & integration readiness (WI-01)

  - CI local canónico `pipelinek`; `--extra dev` → `--group dev`.
  - Identidad de versión: `__version__` ahora `"0.14.1.dev0"`
    en work, `"0.14.1"` tras release.
  - `pyproject.toml` license SPDX Apache-2.0; coverage
    `fail_under = 60`.
  - `SECURITY.md` con proceso de divulgación coordinada.
  - Reconciliación documental: 918 tests, 160.74s.

  ### Erratum: v0.14.0

  La etiqueta `v0.14.0` queda como evidencia histórica de una
  release defectuosa (commit `d50f666`, package metadata
  `0.7.0.dev0`). NO se reescribe. La release correctiva es
  `v0.14.1`. SemVer no contempla reescritura retroactiva de
  versiones publicadas.
  ```
- `SESSION-JOURNAL.md`: nueva entrada al tope:
  ```
  ## WI-01 — Release & integration readiness

  Inicio: 2026-09-26T11:34:53Z
  Cierre previsto: tras `pipelinek run` SUCCESS.

  - Pre-flight SDDK: `sddk adopt apply` → status complete.
  - Baseline pytest: 918 passed / 160.74s / exit 0.
  - Auditoría origen: informe técnico integral
    2026-09-26 (HEAD `b1bb264`).
  - Decisión D-03 (operador 2026-09-26T11:55:39Z): release
    correctiva `v0.14.1`; `v0.14.0` se preserva como erratum.
  ```

**Verificación local:**
- `head -40 CHANGELOG.md` muestra la entrada nueva.
- `grep -F "WI-01" SESSION-JOURNAL.md` exit 0.

## T-09 · Regla de release en AGENTS.md

**Commit:** `docs(agents): regla release gate (tag ↔ __version__)`

**Cambios:**
- Añadir a `AGENTS.md` una nueva sección `§12 Regla de release`:
  - Una única fuente SemVer: `src/skillgraph/__init__.py:__version__`.
  - Hatch la lee (`[tool.hatch.version] path`).
  - Cada etiqueta `v<X>.<Y>.<Z>` debe corresponder a un commit
    cuyo `__version__` (sin sufijo `.devN`) sea `<X>.<Y>.<Z>`.
  - Commits de trabajo posteriores a una etiqueta deben
    incrementar `.dev0`, `.dev1`, etc.
  - Prohibido `--force` sobre etiquetas publicadas.
  - El release gate es un test pytest
    (`tests/test_release_governance.py`) que forma parte del
    admission gate de `pipelinek`.

**Verificación local:**
- `grep -F "## 12 Regla de release" AGENTS.md` exit 0.

## T-10 · Re-anotar `v0.14.1` sobre el commit de release y bump final

**Commit:** `release(version): bump 0.14.1.dev0 → 0.14.1 + tag v0.14.1`

**Precondición:** T-01..T-09 todos verdes y `pipelinek run` SUCCESS.

**Cambios:**
- `src/skillgraph/__init__.py:27`: `__version__ = "0.14.1"`.
- `git tag -a v0.14.1 -m "v0.14.1 — release & integration
  readiness (WI-01)"`.

**Verificación local:**
- `python -c "import skillgraph; print(skillgraph.__version__)"`
  imprime `0.14.1`.
- `git tag -l --format='%(refname:short) %(objectname:short)'
  'v0.14*'` muestra `v0.14.0 d50f666` y `v0.14.1 <HEAD>`.
- `git rev-parse v0.14.0` sigue devolviendo `d50f666`.

## T-11 · `pipelinek run` SUCCESS final

**No commit; verificación del WI.**

- `pipelinek validate .pipeline.kts` exit 0.
- `pipelinek run --db .pipelinek/db.sqlite --control-root
  .pipelinek/control .pipeline.kts` termina con
  `Pipeline finished with SUCCESS`.
- `mise run lint` exit 0.

## Resumen de commits (orden)

| # | Tipo | Ámbito | Mensaje |
|---|---|---|---|
| T-01 | test | release-governance | contrato __version__ ↔ git tag |
| T-02 | release | version | bump 0.7.0.dev0 → 0.14.1.dev0 |
| T-03 | chore | tooling | uv sync --group dev (PEP 735) |
| T-04 | chore | pyproject | license SPDX Apache-2.0 + coverage fail_under=60 |
| T-05 | docs | security | SECURITY.md con proceso de divulgación |
| T-06 | docs | state | reconciliar CURRENT/STATE a baseline 918 |
| T-07 | docs | checkpoints | archivar superseded 2026-09-25 y 2026-09-26 |
| T-08 | docs | changelog+journal | entrada 0.14.1 + erratum v0.14.0 |
| T-09 | docs | agents | regla release gate (tag ↔ __version__) |
| T-10 | release | version | bump 0.14.1.dev0 → 0.14.1 + tag v0.14.1 |
| T-11 | verify | (no commit) | pipelinek run SUCCESS |

## Cierre del WI

Cuando T-11 pase, ejecuto `agent-session close` con:
- AC-1..AC-10 PASS.
- Tag `v0.14.1` creado.
- Pipeline local SUCCESS.
- 918/918 tests verdes.
- Documentación reconciliada.