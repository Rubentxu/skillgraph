# SkillGraph

> Plataforma local-first para convertir skills de agentes en workflows declarativos, verificables y extensibles.
>
> *Local-first platform for turning agent skills into declarative, verifiable, extensible workflows.*

<div align="center">

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org)
[![Status](https://img.shields.io/badge/status-3%20Alpha-orange)](https://pypi.org/classifiers/)
[![Tests](https://img.shields.io/badge/tests-405%2F405%20PASS-success)](tests/)
[![UAT](https://img.shields.io/badge/UAT-16%2F16%20PASS-success)](tests/uat-evidence/)

</div>

---

**English** | [Español](#español)

---

## English

**SkillGraph** is a local-first platform that turns agent skills (declarative Markdown+YAML descriptions of capabilities) into verifiable, deterministic workflows. The runtime guarantees that *what an agent says it will do* matches *what the executor actually does*, while keeping agents from running arbitrary code at import time.

### Why SkillGraph?

Most agent frameworks conflate **describing** a capability with **executing** it. SkillGraph keeps them separated:

- **Skills are data, not code.** A skill lives in a Markdown file with YAML frontmatter; it is parsed, validated, and registered. It never runs on import (zero `exec`, zero `importlib.magic`).
- **Workflows are immutable plans.** A workflow is a DAG of nodes with typed outcomes. The runtime walks it, recovering from crashes via persistent state.
- **Knowledge is incremental.** Imported skills produce typed Claims and Entities via a transitive invalidation graph; a refreshed source invalidates only what depends on it.
- **Extension is controlled.** Capabilities can only be added to a graph via a proposal pipeline (`DISCOVER → PROPOSE → VALIDATE → AUTHORIZE → APPLY`) with policy evaluation and audit trail.

### Current state

**Blueprint v1 is complete, including the public CLI integration (H8).** The roadmap now spans 10 milestones (H0..H6, H8, H9 — see `specs/adr/ADR-0013-divergencia-h7-y-rectificacion-v060.md` for the renumbering) and 16 acceptance tests; all of them have an implementation and verified evidence.

| Component | State | Evidence |
|---|---|---|
| Resources (H1) | ✅ Closed | `tests/test_*` |
| Recoverable execution (H2) | ✅ Closed | `tests/test_*` |
| Knowledge & Context (H3, 5 slices) | ✅ Closed | `tests/test_knowledge*` |
| Controlled expansion (H4, slices 1+2+3) | ✅ Closed | `tests/test_h4*` |
| Skill import (H5) | ✅ Closed | `tests/test_skill_importer.py` |
| Multipurpose: Domain Packs (H6) | ✅ Closed | `tests/test_h6_multiproposito.py` |
| Cross-base promotion (H7→H9, library) | ✅ Closed | `tests/test_h7_promocion.py` |
| **Public CLI integration (H8)**: `sg pack load`, `sg promotion submit/list/reconcile` with crash failpoints | ✅ Closed | `tests/test_h8_public_paths.py`, `tests/uat-evidence/UAT-12.json`, `tests/uat-evidence/UAT-13.json` |
| **16/16 UATs** | **✅ PASS** | `tests/uat-evidence/*.json` |

### Installation

```bash
# Option A: using mise + uv (recommended, what the developer uses)
mise install              # Python 3.13 + uv
mise run sync             # sync dependencies (uv sync --group dev)
mise run cli              # smoke-test the CLI

# Option B: plain uv
uv sync --group dev
uv run skillgraph --help
```

Requires Python ≥ 3.11. Tested on 3.11, 3.12, 3.13, 3.14.

### Quickstart

```bash
# Initialize a project (creates .skillgraph/ locally)
uv run skillgraph init ./my-project

# Import a skill pack (Markdown+YAML, NO code execution)
uv run skillgraph pack import ./my-project ./path/to/skill-pack.md

# Inspect the registered capabilities
uv run skillgraph knowledge show ./my-project

# Run a workflow against the project
uv run skillgraph run ./my-project ./workflow.yaml --max-iterations 50
```

### Architecture

SkillGraph is opinionated about boundaries. The four layers never cross:

1. **Resources** — Markdown+YAML bricks, parsed deterministically.
2. **Runtime** — workflow execution with persistent state (SQLite) and recovery.
3. **Knowledge** — typed graph (Claims/Entities/Evidences/Sources) with transitive invalidation.
4. **Control plane** — proposals, authorizations, policy engine, audit trail.

Internally, the codebase mirrors Haskell-style functional patterns (ADTs, immutability, pure transforms) in Python — see `AGENTS.md` §11 for the underlying philosophy.

### What is NOT here (yet, and why)

These are documented honestly in `CHANGELOG.md`:

- **Stress tests** (kill -9, real concurrency). The current E2E suite is *representative*, not *acceptance-aligned*. Promotion crash-recovery is covered by an injected failpoint (`SKILLGRAPH_FAILPOINT_PROMOTION`), not by real concurrency.
- **CLI 1st-person coverage** (in-process). E2E subprocess tests cover critical paths but aren't counted by pytest-cov.
- **No public Storage API to list all promotions** — `sg promotion list` reads `promotion_outbox` via direct SQL (read-only in the CLI layer).

### Documentation

| File | Purpose |
|---|---|
| `CURRENT.md` | Operational pointer (latest verified state, blockers, next action) |
| `STATE.yaml` | Structured durable state (workstreams, tests, UATs, releases) |
| `SESSION-JOURNAL.md` | Chronological log of significant decisions |
| `CHANGELOG.md` | Per-release record with acceptance criteria |
| `AGENTS.md` | Engineering policy and conventions for AI agents + humans |
| `.next-decision.md` | Deferred / out-of-initiative work candidates |
| `external/blueprint-v1/` | The canon for product/architecture (not in this repo) |

### Contributing

Contributions are welcome, but please **read `CONTRIBUTING.md` first**. Issues and PRs should reference a UAT (`UAT-NN`) when relevant so we can keep the evidence trail coherent.

### Local git hooks (defense in depth)

After cloning, run `bash scripts/install-hooks.sh` once to install the
project's local git hooks into `.git/hooks/`:

- **pre-commit**: runs `ruff check`, `ruff format --check`, and a pytest
  smoke subset on staged `.py` files.
- **pre-push**: runs the **full pytest suite** (~3 min) before accepting
  a push, preventing pushes that would break CI.

Bypasses (use sparingly, document in commit message when used):
- `git commit --no-verify` / `git push --no-verify` — skip all hooks.
- `HOOK_SKIP_TESTS=1 git commit` — skip pytest smoke in pre-commit.
- `HOOK_SKIP_PUSH_TESTS=1 git push` — skip full pytest in pre-push
  (e.g. experimental branches, CI config-only changes).

If you set `core.hooksPath` globally (some agents do), add a wrapper at
`~/.git-hooks/pre-commit` and `~/.git-hooks/pre-push` that delegates to
the local hook files, since Git ignores `.git/hooks/` when a global
`core.hooksPath` is set.

### Security

For vulnerability reports, see `SECURITY.md`. **Do not file public issues for security bugs.**

### License

Apache License 2.0. See [`LICENSE`](LICENSE) for the full text.

Copyright © 2026 Rubentxu.

---

## Español

**SkillGraph** es una plataforma local-first que convierte skills de agentes (descripciones declarativas Markdown+YAML de capacidades) en workflows verificables y deterministas. El runtime garantiza que *lo que un agente dice que hará* coincide con *lo que el ejecutor realmente hace*, evitando que los agentes ejecuten código arbitrario al importarse.

### ¿Por qué SkillGraph?

La mayoría de frameworks de agentes confunden **describir** una capacidad con **ejecutarla**. SkillGraph las mantiene separadas:

- **Las skills son datos, no código.** Una skill vive en un archivo Markdown con frontmatter YAML; se parsea, valida y registra. Nunca se ejecuta al importarla (cero `exec`, cero `importlib.magic`).
- **Los workflows son planes inmutables.** Un workflow es un DAG de nodos con outcomes tipados. El runtime lo recorre recuperándose de crashes vía estado persistente.
- **El conocimiento es incremental.** Las skills importadas producen Claims y Entities tipadas vía un grafo de invalidación transitiva; refrescar una fuente invalida solo lo que depende de ella.
- **La extensión es controlada.** Las capacidades solo pueden añadirse al grafo vía un pipeline de propuestas (`DISCOVER → PROPOSE → VALIDATE → AUTHORIZE → APPLY`) con evaluación de políticas y trazabilidad.

### Estado actual

**El blueprint v1 está completo, incluida la integración pública por CLI (H8).** El roadmap cubre ahora 10 hitos (H0..H6, H8, H9 — ver `specs/adr/ADR-0013-divergencia-h7-y-rectificacion-v060.md` para la renumeración) y 16 acceptance tests; todos tienen implementación y evidencia verificada.

| Componente | Estado | Evidencia |
|---|---|---|
| Recursos (H1) | ✅ Cerrado | `tests/test_*` |
| Ejecución recuperable (H2) | ✅ Cerrado | `tests/test_*` |
| Conocimiento & Contexto (H3, 5 slices) | ✅ Cerrado | `tests/test_knowledge*` |
| Expansión controlada (H4, slices 1+2+3) | ✅ Cerrado | `tests/test_h4*` |
| Importación de skills (H5) | ✅ Cerrado | `tests/test_skill_importer.py` |
| Multipropósito: Domain Packs (H6) | ✅ Cerrado | `tests/test_h6_multiproposito.py` |
| Promoción entre bases (H7→H9, biblioteca) | ✅ Cerrado | `tests/test_h7_promocion.py` |
| **Integración pública CLI (H8)**: `sg pack load`, `sg promotion submit/list/reconcile` con failpoints de crash | ✅ Cerrado | `tests/test_h8_public_paths.py`, `tests/uat-evidence/UAT-12.json`, `tests/uat-evidence/UAT-13.json` |
| **16/16 UATs** | **✅ PASS** | `tests/uat-evidence/*.json` |

### Instalación

```bash
# Opción A: usando mise + uv (recomendado, la que usa el desarrollador)
mise install              # Python 3.13 + uv
mise run sync             # sincronizar dependencias (uv sync --group dev)
mise run cli              # smoke-test del CLI

# Opción B: solo uv
uv sync --group dev
uv run skillgraph --help
```

Requiere Python ≥ 3.11. Probado en 3.11, 3.12, 3.13, 3.14.

### Inicio rápido

```bash
# Inicializar un proyecto (crea .skillgraph/ local)
uv run skillgraph init ./mi-proyecto

# Importar un pack de skills (Markdown+YAML, NO ejecuta código)
uv run skillgraph pack import ./mi-proyecto ./ruta/al/pack.md

# Inspeccionar las capacidades registradas
uv run skillgraph knowledge show ./mi-proyecto

# Ejecutar un workflow contra el proyecto
uv run skillgraph run ./mi-proyecto ./workflow.yaml --max-iterations 50
```

### Arquitectura

SkillGraph es opinado sobre las fronteras. Las cuatro capas nunca se cruzan:

1. **Recursos** — bricks en Markdown+YAML, parseados deterministamente.
2. **Runtime** — ejecución de workflow con estado persistente (SQLite) y recuperación.
3. **Conocimiento** — grafo tipado (Claims/Entities/Evidences/Sources) con invalidación transitiva.
4. **Plano de control** — propuestas, autorizaciones, motor de políticas, audit trail.

Internamente, el código sigue patrones funcionales estilo Haskell (ADTs, inmutabilidad, transformaciones puras) en Python — ver `AGENTS.md` §11 para la filosofía subyacente.

### Qué NO está aquí (todavía, y por qué)

Documentado honestamente en `CHANGELOG.md`:

- **Tests de stress** (kill -9, concurrencia real). La suite E2E actual es *representative*, no *acceptance-aligned*. La recuperación ante crash de promoción está cubierta por un failpoint inyectado (`SKILLGRAPH_FAILPOINT_PROMOTION`), no por concurrencia real.
- **Cobertura 1st-person del CLI** (in-process). Los tests E2E subprocess cubren los caminos críticos pero no cuentan en pytest-cov.
- **Sin API pública de Storage para listar todas las promociones** — `sg promotion list` lee `promotion_outbox` por SQL directo (solo lectura, en la capa CLI).

### Documentación

| Archivo | Propósito |
|---|---|
| `CURRENT.md` | Puntero operativo (estado verificado, bloqueos, próxima acción) |
| `STATE.yaml` | Estado durable estructurado (workstreams, tests, UATs, releases) |
| `SESSION-JOURNAL.md` | Log cronológico de decisiones significativas |
| `CHANGELOG.md` | Registro por release con criterios de aceptación |
| `AGENTS.md` | Política y convenciones de ingeniería para agentes IA + humanos |
| `.next-decision.md` | Candidatos de trabajo diferidos / fuera de la iniciativa |
| `external/blueprint-v1/` | El canon de producto/arquitectura (no está en este repo) |

### Contribuir

Las contribuciones son bienvenidas, pero por favor **lee primero `CONTRIBUTING.md`**. Las issues y PRs deben referenciar un UAT (`UAT-NN`) cuando aplique para mantener coherente la trazabilidad de evidencia.

### Git hooks locales (defensa en profundidad)

Tras clonar, ejecuta `bash scripts/install-hooks.sh` una vez para instalar
los git hooks locales del proyecto en `.git/hooks/`:

- **pre-commit**: ejecuta `ruff check`, `ruff format --check` y un smoke
  de pytest sobre archivos `.py` staged.
- **pre-push**: ejecuta la **suite completa de pytest** (~3 min) antes
  de aceptar un push, evitando pushes que romperían CI.

Bypasses (úsalos con moderación, documenta en el mensaje del commit cuando los uses):
- `git commit --no-verify` / `git push --no-verify` — salta todos los hooks.
- `HOOK_SKIP_TESTS=1 git commit` — salta el smoke de pytest en pre-commit.
- `HOOK_SKIP_PUSH_TESTS=1 git push` — salta el pytest completo en
  pre-push (e.g. ramas experimentales, cambios solo de CI).

Si configuras `core.hooksPath` globalmente (algunos agentes lo hacen),
añade un wrapper en `~/.git-hooks/pre-commit` y `~/.git-hooks/pre-push`
que delegue a los archivos de hook locales, ya que Git ignora
`.git/hooks/` cuando hay un `core.hooksPath` global activo.

### Seguridad

Para reportes de vulnerabilidades, ver `SECURITY.md`. **No abrir issues públicas para bugs de seguridad.**

### Licencia

Apache License 2.0. Ver [`LICENSE`](LICENSE) para el texto completo.

Copyright © 2026 Rubentxu.

---

<div align="center">

Built with intent and the discipline of an explicit, evidence-tracked roadmap.

*Construido con intención y la disciplina de un roadmap explícito y trazable.*

</div>
