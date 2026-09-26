# WI-01 — Release & integration readiness (P0 de la auditoría 2026-09-26)

> Spec derivada del informe técnico integral (HEAD `b1bb264`) y de las
> decisiones del operador en sesión `2026-09-26T11:47:32Z`. El WI-01 es
> **predecesor bloqueante** del WI-02 (refactor B+C de puertos de
> persistencia) y del WI-03 (división de Storage y CLI): sin CI verde
> y sin identidad de versión única, no se puede firmar DONE de ningún
> WI posterior.

## 1. Contexto y motivación

El repositorio muestra tres hallazgos críticos concurrentes que
invalidan cualquier afirmación de release/integration readiness:

1. `mise run sync` y el workflow de GitHub Actions invocan
   `uv sync --extra dev`, pero `dev` está declarado como
   `[dependency-groups]` (PEP 735). Resultado: el comando falla con
   `Extra 'dev' is not defined in the optional-dependencies table for
   'skillgraph'` y CI no llega a ejecutar lint ni tests.

2. La etiqueta `v0.14.0` apunta a `d50f666` con anotación propia y
   mensaje "739/739 verde", pero el HEAD actual (`b1bb264`) y el
   propio `v0.14.0` contienen `__version__ = "0.7.0.dev0"` en
   `src/skillgraph/__init__.py:27`. Hatch toma la versión del paquete
   desde ese fichero, así que el artefacto etiquetado se identifica
   como 0.7.0.dev0.

3. La verdad operacional está distribuida: `CURRENT.md`, `STATE.yaml`,
   `SESSION-CHECKPOINT-*.md`, `CHANGELOG.md` y `SESSION-JOURNAL.md`
   contienen cifras de tests incompatibles (772/830/904/918) según el
   documento consultado. El conteo real medido en baseline local es
   **918 passed en 160.74 s**.

Además hay dos hallazgos de empaquetado y un olor arquitectónico de
documentación:

- `pyproject.toml` declara `license = { text = "Proprietary" }`
  pero `LICENSE` contiene Apache-2.0.
- `README.md` enlaza a `SECURITY.md`, que no existe.
- La auditoría externa afirmaba que `external/blueprint-v1/` y
  `external/evolution-v2/` estaban ausentes, pero la inspección del
  árbol confirma que **sí existen**; la afirmación estaba
  desactualizada.

## 2. Objetivo

Restaurar release/integration readiness con **CI local
canónico = `pipelinek`**, **una única fuente SemVer** sincronizada
entre `__version__` y la etiqueta git, y **una única verdad
operacional** reconciliada a partir del baseline real (918 tests).

## 3. Decisiones explícitas

- **D-01.** El CI dominante es local: `pipelinek run` sobre
  `.pipeline.kts`. GitHub Actions se queda como notificación
  informativa y se desacopla del gate de admisión. Documentado en
  `AGENTS.md` §"CI Local Obligatorio".
- **D-02.** La regla de empaquetado dev es `--group dev`
  (PEP 735) en lugar de `--extra dev`. Se elimina la confusión
  extra-vs-group.
- **D-03.** Versión del paquete en este ciclo = **`0.14.1`**,
  según la decisión del operador 2026-09-26T11:55:39Z. Secuencia:
  1. `v0.14.0` (HEAD `d50f666`) **NO SE TOCA**. Permanece como
     release histórica; queda documentada como erratum de
     versionado (package metadata decía `0.7.0.dev0` cuando se
     etiquetó). El CHANGELOG y AGENTS.md declaran el erratum.
  2. Durante el trabajo de este WI,
     `__version__ = "0.14.1.dev0"` en
     `src/skillgraph/__init__.py`.
  3. Tras `pipelinek run` SUCCESS y todos los AC PASS, segundo bump
     a `__version__ = "0.14.1"` en un commit de release.
  4. Etiqueta anotada **`v0.14.1`** sobre ese commit. Sin
     `--force` sobre ningún tag previo. Sin `v0.14.0-r2` (SemVer
     daría precedencia inferior, justo lo contrario de lo que
     conceptualmente se quiere).
  5. WI-02 parte de `0.14.2.dev0` o `0.15.0.dev0` solo si WI-02
     introduce capacidad/API pública que justifique MINOR.
- **D-04.** La regla AGENTS.md exige que **el valor de
  `__version__` en HEAD == la etiqueta anotada más reciente**
  (release gate). El release gate es un test pytest nuevo que
  compara `__version__` con el `git describe --tags` parseado a
  SemVer. Si HEAD no está etiquetado, el test asume `dev` y
  acepta.
- **D-05.** Coverage `fail_under` sube de 0 a **60** global.
  No se imponen focales por módulo en este WI: se documenta como
  follow-up en WI-02 si el refactor de puertos cambia los radios
  de cobertura.
- **D-06.** `CURRENT.md`, `STATE.yaml`, último `SESSION-CHECKPOINT-*.md`
  y `CHANGELOG.md` se reconcilian a partir del baseline real
  ejecutado en este WI. La fuente única de cifras de tests pasa a
  ser la salida del último run de `pipelinek`.
- **D-07.** La metadata de licencia se alinea a Apache-2.0 (el
  fichero `LICENSE` real) corrigiendo `pyproject.toml`. Se crea
  `SECURITY.md` con proceso mínimo de reporte.

## 4. Contrato observable

### 4.1. CI local

- `pipelinek validate .pipeline.kts` retorna `VALIDATION SUCCESSFUL`.
- `pipelinek run` ejecuta las 4 stages
  (`discover-repo`, `sync-deps`, `unit-tests`, `evidence`) y termina
  con `Pipeline finished with SUCCESS`.
- La stage `sync-deps` invoca `uv sync --group dev` y NO `--extra
  dev`. El test del contrato es `mise run sync` ejecutado desde
  shell bash con `set -e`: exit 0.

### 4.2. Identidad de versión

- `src/skillgraph/__init__.py` declara `__version__ = "0.14.1.dev0"`
  durante el trabajo; tras CI verde, segundo commit lo eleva a
  `"0.14.1"`.
- `python -c "import skillgraph; print(skillgraph.__version__)"`
  imprime `0.14.1.dev0` (work) o `0.14.1` (release).
- El comando `hatch version` (o `uv version`) reporta lo mismo.
- Existe un test pytest nuevo
  (`tests/test_release_governance.py::test_version_matches_git_tag`)
  que pasa si y solo si:
  - HEAD está etiquetado como `v<X>.<Y>.<Z>` y
    `__version__` (sin sufijo `.devN`) == `<X>.<Y>.<Z>`, **o bien**
  - HEAD no está etiquetado **o** está en un commit posterior a la
    etiqueta más reciente, en cuyo caso `__version__` debe
    terminar en `.dev0` o `.devN`.
- El test falla con mensaje explícito si el HEAD etiquetado dice una
  cosa y el `__version__` dice otra, o si el HEAD no etiquetado
  tiene `__version__` sin sufijo `.devN`.

### 4.3. Documentación reconciliada

- `CURRENT.md` declara `tests 918`, `duration 160.74s`,
  `HEAD <sha tras bump>` con fecha `2026-09-26`, `SemVer 0.14.1.dev0`
  (work) o `0.14.1` (release).
- `STATE.yaml` declara `tests.total = 918`,
  `tests.passed = 918`, `tests.duration_s = 161`,
  `package_version = "0.14.1.dev0"` (work) o `"0.14.1"` (release).
- `CHANGELOG.md` contiene una entrada nueva
  `[0.14.1] - 2026-09-26` con la lista de cambios de este WI
  **y una nota de erratum para `v0.14.0`** declarando que esa
  etiqueta queda como histórica y NO se reescribe.
- `SESSION-CHECKPOINT-2026-09-26-FIN.md` se conserva como cierre
  del ciclo. `SESSION-CHECKPOINT-2026-09-26.md` y
  `SESSION-CHECKPOINT-2026-09-25.md` se marcan como superseded y se
  mueven a `audits/historical/`.
- `SESSION-JOURNAL.md` recibe una entrada "WI-01 cycle".

### 4.4. License y security

- `pyproject.toml` declara `license = "Apache-2.0"` (SPDX) en vez de
  `Proprietary`.
- `LICENSE` permanece intacto.
- `SECURITY.md` existe en la raíz con un proceso mínimo:
  - canal de reporte por GitHub Security Advisories.
  - ventana de respuesta: 90 días para vulnerabilidades altas.
  - formato de divulgación coordinada.

## 5. Criterios de aceptación

| ID | Criterio | Comprobación | Estado al cierre |
|---|---|---|---|
| AC-1 | `mise run sync` (o `uv sync --group dev`) exit 0 | `bash -c "set -e; mise run sync"` exit 0 | PASS |
| AC-2 | `pipelinek run .pipeline.kts` termina SUCCESS | exit 0 + "Pipeline finished with SUCCESS" | PASS |
| AC-3 | `__version__ == "0.14.1.dev0"` durante el trabajo, `"0.14.1"` tras CI verde, y hatch lo lee | `python -c "import skillgraph; print(skillgraph.__version__)"` -> `0.14.1.dev0` / `0.14.1` | PASS |
| AC-4 | Test de release gate pasa | `pytest tests/test_release_governance.py -v` exit 0 | PASS |
| AC-5 | Coverage fail_under = 60, suite pasa | `pytest --cov` exit 0, coverage ≥ 60 | PASS |
| AC-6 | CURRENT/STATE/changelog reconciliados | grep de "918" en los 3 ficheros, fechas coherentes | PASS |
| AC-7 | pyproject license = Apache-2.0 SPDX | `grep 'license = "Apache-2.0"' pyproject.toml` | PASS |
| AC-8 | SECURITY.md existe y tiene proceso | `test -f SECURITY.md && grep -q 'coordinated disclosure' SECURITY.md` | PASS |
| AC-9 | Tag anotado `v0.14.1` creado sobre el commit de release; `v0.14.0` intacto en `d50f666`; CHANGELOG documenta erratum | `git tag -l --format='%(refname:short) %(objectname:short)' 'v0.14*'` muestra ambos; `git log v0.14.0..main --oneline` enumera los commits del WI-01 | PASS |
| AC-10 | ruff limpio | `mise run lint` exit 0 | PASS |

## 6. Out of scope (declarado)

- WI-02: refactor B+C de puertos (`RunRepository`, `EventStore`,
  `KnowledgeRepository`, `PromotionRepository`, `PolicyStore`).
- WI-03: división de `platform/storage.py` por capabilities.
- WI-04: división de `cli/runner.py` por command groups.
- WI-05: type checker progresivo (mypy/pyright).
- Funcionales pendientes declarados en `INITIATIVE-CLOSED.md`:
  E1 (adapter real), T5 (backups), T6 (observabilidad).

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El tag `v0.14.0` se preserva como evidencia histórica defectuosa; no usar `--force` sobre ningún tag publicado | La release correctiva es `v0.14.1`, anotada sobre el commit de release. CHANGELOG declara el erratum de `v0.14.0`. NO se publica `v0.14.0-r2` (SemVer le daría precedencia inferior) |
| Coverage `fail_under = 60` puede esconder regresiones de módulos críticos | Documentar el WI-02 como lugar donde se imponen focales |
| Cambiar `pyproject.toml license` puede romper herramientas que confían en `Proprietary` | El cambio refleja la realidad (LICENSE=Apache-2.0); consumers deben usar SPDX que es el estándar |
| `mise run sync` cambia comportamiento para humanos con shells que cachean | Documentar en CHANGELOG y en AGENTS.md; `uv` es idempotente |
| El test de release gate puede romper a un dev que commitea sin etiquetar | La rama "no etiquetado" del test acepta `.devN`; documentar |

## 8. Plan de aplicación (resumen)

1. Crear `tests/test_release_governance.py` con el test del contrato
   de versión.
2. Bumpear `__version__` a `0.14.1.dev0` en
   `src/skillgraph/__init__.py`.
3. Cambiar `mise.toml`:
   - `tasks.sync` a `uv sync --group dev`.
   - Añadir `tasks.test` (existe) confirmado.
   - Añadir `tasks.release-gate` ejecutando el nuevo test.
4. Cambiar `pyproject.toml`:
   - `license = "Apache-2.0"` (SPDX).
   - `fail_under = 60`.
   - Confirmar `[dependency-groups]` con `dev` y `docs`.
5. Crear `SECURITY.md`.
6. Reconciliar documentación:
   - Reescribir secciones de `CURRENT.md`.
   - Actualizar `STATE.yaml` `tests:`.
   - Entrada nueva en `CHANGELOG.md`.
   - Entrada en `SESSION-JOURNAL.md`.
   - Mover checkpoints superseded a `audits/historical/`.
7. Tras CI verde, bumpear a `__version__ = "0.14.1"` en commit de
   release. Crear etiqueta anotada **`v0.14.1`** sobre ese commit.
   Sin `--force` sobre `v0.14.0` (que queda intacto en `d50f666`).
8. Re-ejecutar `pipelinek run` tras el bump final y validar exit
   SUCCESS.

## 9. Definition of Done

- AC-1..AC-10 todos PASS.
- Commit firmado con mensaje `release(release-readiness): WI-01`.
- `pipelinek run` SUCCESS en este WI.
- `SESSION-CHECKPOINT-2026-09-26-FIN.md` actualizado con el cierre.

## 10. Trazabilidad

- Auditoría origen: informe técnico integral 2026-09-26
  (cabecera `HEAD b1bb264`).
- Decisión del operador: turno `2026-09-26T11:55:39Z`
  (B con `v0.14.1`; no `v0.14.0-r2`; `v0.14.0` queda como
  erratum histórico sin reescritura).
- Canon: `external/blueprint-v1/01-producto.md`,
  `external/evolution-v2/plan/` (no contradice).
- Specs relacionadas: ninguna previa; este es el primer WI
  post-auditoría.