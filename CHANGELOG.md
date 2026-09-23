# Changelog

All notable changes to SkillGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
derived from the commit history via Conventional Commits.

Tipos:
- `feat` → MINOR (nueva capacidad observable).
- `fix` → PATCH (corrección).
- `feat!` / `fix!` / footer `BREAKING CHANGE` → MAJOR.
- `refactor`, `test`, `docs`, `spec`, `chore`, `style` → sin bump de versión.

## [0.4.0] — 2026-09-23

**Resumen**: cierra el gap declarado en `specs/h4-slice-3.md` limitación 3.
`expansion apply` ahora persiste la propuesta y crea marker `.applied`,
haciendo que `list --stage APPLIED` funcione (antes retornaba vacío).
`expansion show` ahora incluye el campo `stage` en el payload JSON.

Compatibilidad hacia atrás mantenida: ningún cambio en códigos de salida,
firmas de comandos, ni en el formato del plan persistido.

### Features (MINOR bump)

- `162a708` **feat(h4-slice-3)**: APPLIED marker + `show.stage` field.
  - `cmd_expansion_apply` ahora persiste la propuesta en
    `expansion_proposals/<id>.json` (si no existe, mismo patrón que
    `cmd_expansion_propose`) y crea marker adyacente `<id>.json.applied`
    con timestamp UTC y `applied_by: "expansion-apply-cli"`.
  - `cmd_expansion_list` y `cmd_expansion_show` leen markers:
    precedencia `ARCHIVED > APPLIED > REJECTED > PROPOSED`.
  - `cmd_expansion_show` añade `"stage": "..."` al payload JSON.
  - Refactor: extrae `_infer_proposal_stage()` y
    `_collect_rejection_ids()` para evitar duplicación entre list y show.

### Estado verificable al tag

- **HEAD**: `162a708` (pre-tag).
- **Tests**: 368 passed en 117s (362 → 368, delta +6 tests focales).
- **Cobertura**: sin cambio material (cli.py 31% in-process; tests
  reales E2E).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.3.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.

## [0.3.0] — 2026-09-23

**Resumen**: primera release taggeada. H0-H5 (excepto H6 y H7)
completados con criterios de aceptación verificados. 14/16 UAT PASS,
2 BLOCKED honestos por falta de spec del operador.

### Features (MINOR bump)

#### H4 — Expansión controlada

- `6f93eb2` **feat(h4)**: Expansion controlada (DISCOVER → APPLY)
  cierra UAT-08/09.
- `bd95d29` **feat(h4-cli)**: expansion propose/apply/validate/rejections
  + E2E para UAT-08/09.
- `3b307f3` **feat(h4-slice-3)**: policy engine P1..P5 + EVALUATE + CLI
  list/show/archive.
- `b7b2d5e` **feat(h4)**: DecisionNode outcomes + max_visits self-loops
  (+7 tests).

Criterio legal HITOS.md H4: "Añadir una investigación imprevista a una
ejecución sin alterar el resultado de nodos anteriores."
- UAT-08 PASS (`tests/uat-evidence/UAT-08.json`): apply incorpora
  únicamente el cambio solicitado; nodos originales intactos.
- UAT-09 PASS (`tests/uat-evidence/UAT-09.json`): propuesta con
  capability no registrada es rechazada con rc=10 y evidencia JSON
  persistida en `expansion_rejections/`.

Limitaciones documentadas (`specs/h4-audit-penal.md`):
- E2E es `representative` (Storage SQLite local), no
  `acceptance_aligned` (sin stress concurrente, sin crash recovery
  verificado en kill-9). Refinamiento pendiente para slice-4.

#### H5 — Adopción de skills

- `26ac401` **feat(h5)**: skill_import (UAT-11 BLOCKED→PASS) +
  `skill_importer` + `cmd pack import`.

Criterio legal HITOS.md H5: "Adoptar una skill real y conservar una
referencia verificable a sus instrucciones originales."
- UAT-11 PASS (`tests/uat-evidence/UAT-11.json`): `pack_import` rc=0,
  `structured_ok=True`, `script_ignored=True`, `scripts_detected=True`.

Decisión documentada (`specs/h5-source-conservation-decision.md`):
- Conservación por referencia (path+content_hash), NO duplicación de
  bytes. Justificado por blueprint §10 §5-6.

#### Otros feats

- `d72bbff` **feat(uat)**: UAT-16 BLOCKED→PASS (handoff_json persiste
  tras revision change).
- `b06cc15` **feat(h3-s1)**: Knowledge ADT + Storage delta.
- `4d8e80c` **feat(ci)**: `scripts/ci.sh` como gate único + pairwise
  import.
- `3bc66d9` **feat(H2)**: tests subprocess CLI run + resume-or-start
  (UAT-04/06/07 E2E).
- `007db8d` **feat(cli)**: añadir `__main__.py` para `python -m
  skillgraph`.
- `a3f7950` **feat(etapa2/S7)**: DSL tipado + PlanBuilder funcional +
  loader Markdown.
- `e763102` **feat(e2-s4+s5)**: WorkflowPlan + RunController +
  ejecución recuperable.
- `92a5174` **feat(e2-s3)**: AgentAdapter + FakeAgentAdapter +
  RecordingAdapter.
- `64bc05d` **feat(e2-s2)**: Handoff materializado con serialización
  estable y SHA-256.
- `92929a9` **feat(e2-s1)**: runtime append-only + EventLog con
  idempotencia por UNIQUE.
- `fb0e56a` **feat(e1)**: CLI real + catálogo + UAT-01..03 PASS.
- `15957d7` **feat(s1)**: almacenamiento SQLite con WAL, aislamiento y
  latencia.
- `0a92c84` **feat(s0)**: brick mínimo Markdown+YAML con parser,
  registro y validación.

### Fixes (PATCH bump)

- `ff433aa` **fix(types)**: SourceKind incluye `skill_pack` y Source
  valida kind en `__post_init__`. Cierra bug silencioso donde
  `from __future__ import annotations` desactivaba Literal-check.
- `e69a8e4` **fix(uat)**: UAT-10 predicados válidos + chequeo
  `seed_rc` y `stale_listed`.
- `bdd196f` **fix(cli)**: UAT-06 max_iterations respeta el límite + 4
  tests honestos.

### Refactors

- `1039171` **refactor + test(paths)**: añadir tests + refactor para
  que la rama nt sea testeable.

### Tests añadidos (sin bump)

- `0e96495` **test(parser)**: 12 tests ramas de error (coverage
  77%→100%).
- `b6ca7e1` **test(plan-loader)**: 13 tests load_plan_file + error
  branches (coverage 48%→100%, dato heredado 69% obsoleto).
- `629be65` **test(recipe)**: 22 tests `__post_init__` + from_dict
  (coverage 73%→100%).
- `7c3f3f4` **test(uat)**: gap coverage UAT en CI — 5 wrappers
  pytest + 2 honest blockers.

### Specs (sin bump)

- `7233fac` spec(h4-audit-penal): cruce H4 slices 1+2 vs blueprint
  literal.
- `92d70e2` spec(h5-audit-penal): cruce H5 skill_import vs blueprint
  literal.
- `81fbb0e` spec(h4-slice-3): propuesta storage persistente + EVALUATE
  + policy engine.
- `2d01a06` spec(uat-coverage-gap): audita que UATs se validan
  automáticamente en CI.

### Estado verificable al tag

- **HEAD**: `076f6e9` (pre-tag) → `v0.3.0` (post-tag).
- **Tests**: 362 passed en 54s (315→362, delta +47 en ciclos de
  stewardship).
- **Cobertura**: 77% total. Módulos críticos `parser.py`, `plan_loader.py`,
  `recipe.py`: 100%. Módulos runtime: 88-100%. `cli.py`: 31% en
  pytest-cov (cobertura real mayor vía tests subprocess E2E no
  contables por cobertura in-process).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos.
- **`scripts/ci.sh`**: OK (format + lint + pytest, replicable por
  cualquier runner externo).
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas

- **UAT-12 (H6 multipropósito)**: BLOCKED. Requiere spec del operador
  para `Character/StoryArc`.
- **UAT-13 (H7 promoción entre bases)**: BLOCKED. Requiere spec del
  operador.
- **H4 slice-4** (deferido por decisión explícita en
  `specs/h4-slice-3.md`): sin migración SQLite, sin gating de
  `auto_signed` via evaluation_result.
- **`paths.py` rama Windows**: no ejercitable en CI Linux
  (`LOCALAPPDATA/USERPROFILE`).
- **`recipes.runtime.dispositivos externos`**: tiktoken solo si H4+
  exige Adapter real.

### Antiobjetivos respetados

- No se introdujo base de grafos especializada.
- No se introdujo scheduler distribuido.
- No se introdujo sistema de agentes permanentes sin requisito
  observado.

## Comparativa con releases anteriores

Esta es la **primera release taggeada** del proyecto.
El historial completo de commits previos forma parte del cuerpo
desarrollado hacia esta release.

[0.3.0]: #030--2026-09-23
