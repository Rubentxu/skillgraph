# SESSION-JOURNAL

Diario cronológico de la iniciativa SkillGraph.
Resumen + referencia verificable. NO reproducir logs ni transcripciones.

## 2026-09-23 — Sesión de descubrimiento y bootstrap

### Resumen

- Sesión arranca como **orquestador SDDK** bajo paraguas persistente (overlay activo).
- Pre-flight SDDK: `~/.jcode/bin/sddk-mode` → `MODE=undeclared`, `REASON=no-entry` (sin entrada de workspace). Se reporta y se mantiene el rol.
- El workspace NO era repo git. Tampoco había código del producto, solo el blueprint descomprimido + `.zip` + `create.py`.
- Decisiones del operador registradas: SDDK `on`, conservar `.zip`/`create.py` hasta validar la copia descomprimida, Python 3.11+ (runtime disponible 3.14.7).
- Bootstrap estructural iniciado:
  - `git init -b main` + identidad local.
  - `.gitignore` con caches, build, `.skillgraph/`, IDE.
  - Blueprint movido de `skillgraph-blueprint/` a `docs/` (12 docs + 12 ADR + 6 plan + referencias + `README.md`).
  - `pyproject.toml` con paquete `skillgraph` (>=3.11), deps mínimas (`PyYAML`, `pytest`, `ruff`).
  - `src/skillgraph/{__init__,cli}.py` con stub CLI de cableado (sin lógica de producto).
  - `src/skillgraph/py.typed` (PEP 561).
  - `CURRENT.md`, `STATE.yaml`, `SESSION-JOURNAL.md` creados.
- **Bloque b1 cerrado** con `mise.toml` fijando Python 3.13.15 + uv 0.12.17, `.venv/` creado, dev deps instaladas (`pytest 9.1.1`, `ruff 0.16.8`, `PyYAML 6.0.3`).
- **Refinamiento de pyproject (decisión operador: bootstrap Python inteligente y actual)**:
  - Backend migrado de `setuptools` → `hatchling>=1.25` (build moderno).
  - Versión ahora `dynamic = ["version"]`, leída de `src/skillgraph/__init__.py::__version__` (una sola fuente de verdad).
  - Dev deps movidas a `[dependency-groups]` (PEP 735) compatibles con `uv` y `pip>=25`.
  - `py.typed` PEP 561 declarado en wheel y sdist.
  - `pytest` con `--strict-config`, `xfail_strict`, `branch coverage` activo.
  - `ruff` con `format` y `lint` (E/F/I/B/UP/SIM/RUF), `docstring-code-format`.
  - `README.md` de raíz añadido para que hatch resuelva el readme del paquete.
- **Verificación reproducible**: wheel + sdist construyen, `uv pip show skillgraph` reporta `Version=0.1.0.dev0`, wheel instalado en venv fresco (`/tmp/sgfresh`) ejecuta `skillgraph --version` correctamente.
- Documentación del blueprint reubicada en `external/blueprint-v1-content/` para cumplir RF-11 (no escribir archivos internos en repositorios fuente). El `.zip` y `create.py` se conservan en `external/` por decisión del operador.
- Input externo `Diseñar-árboles-de-decisión-para-agentes.md` movido a `external/inputs/` (no versionado).

### Evidencia verificable

- `git rev-parse --is-inside-work-tree` → `true`.
- `python3 --version` (sistema) → `Python 3.14.7`; `mise exec -- python -V` → `Python 3.13.15`.
- `uv build --wheel` → `Successfully built /tmp/sg-wheel/skillgraph-0.1.0.dev0-py3-none-any.whl`.
- `uv build --sdist` → `Successfully built /tmp/sg-wheel/skillgraph-0.1.0.dev0.tar.gz`.
- METADATA del wheel: `Name=skillgraph`, `Version=0.1.0.dev0`, `Requires-Python=>=3.11`, `Requires-Dist: pyyaml>=6.0`.
- `ruff check src tests` → `All checks passed!`.
- `ruff format --check src tests` → `2 files already formatted`.
- `pytest` (vacío, sin tests todavía) → `collected 0 items`.
- `skillgraph --version` → `skillgraph 0.1.0.dev0`.
- Wheel instalado en venv fresco: `skillgraph --version` → `skillgraph 0.1.0.dev0`.

### Decisiones pendientes

- Adopción SDDK real (ejecutar `sddk-mode set on --workspace` y `sddk adopt apply`).
- Política de borrado de `.zip` y `create.py` cuando el commit inicial esté hecho (siguen en `external/`).
- Python version objetivo en CI (3.13 confirmado para local; CI queda libre hasta primer ciclo de CI).

### Siguiente paso

b2 (primer commit del bootstrap) → b3 (adopción SDDK) → b4 (regenerar documentos de estado con el commit) → s0-1 (fixtures + parser Markdown+YAML).