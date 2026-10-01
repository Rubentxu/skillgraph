# Release receipt — v0.16.9

| Campo | Valor |
|---|---|
| Tag | `v0.16.9` (anotada) |
| Objeto de etiqueta remoto | `ce35d9c393ff186374d6192cd9da3b037bd22f74` |
| Peel remoto de la etiqueta | `600279a1e1acfcfa94c7538b5e679f973b0e2997` |
| `origin/main` | `cdbfbb2548ca03240a26585b6daadaa79fb31549` (fast-forward `df72bcc..cdbfbb2`, 27 commits, verificado con `git ls-remote` tras el push) |
| `__version__` en el tag | `0.16.9` (SemVer puro, verificado con `git show v0.16.9^{}:src/skillgraph/__init__.py` **antes** de etiquetar) |
| Tag anterior | `v0.16.8` (peel `df72bcc`, en remoto) |
| Commits incluidos | 14 (`2e85c1e..HEAD-del-tag`, ver `git rev-list --count v0.16.8..v0.16.9`) |
| Suite completa | **1759 tests collected** (1754 + 5 nuevos de WI-49); PASS verificado por el hook pre-commit en cada fix y en el bump |
| Release governance gate | 2 passed (`mise exec -- uv run pytest tests/test_release_governance.py`) |
| Publicación | `origin/main` = `cdbfbb2`, etiqueta `v0.16.9` en el remoto con peel verificado (push aprobado por el operador, 2026-10-02) |
| Fecha | 2026-10-01 (tag) / 2026-10-02 (push) |

## SemVer derivado del historial (no decidido a mano)

Conteo real de `git log --format=%s v0.16.8..HEAD` en el momento de
etiquetar:

| Tipo | Conteo | Efecto en SemVer |
|---|---|---|
| `fix` | 3 | **PATCH** |
| `docs` | 4 | ninguno |
| `chore` | 2 | ninguno |
| `feat` | 0 | — |
| breaking | 0 | — |

**PATCH.** Los tres `fix` son de la misma clase de defecto (bool
aceptado como entero en datos declarados), ciclo
`wi-49-bool-int-declared-coercions`.

## Contenido

### Los tres fixes (WI-49)

| Commit | Superficie | Fuga que cierra |
|---|---|---|
| `8ba12f3` | `plan_loader._resource_revision` | `resourceRevision: true` → `int(True)`=1 pasaba el invariante `>= 1` en silencio: revisión que nadie declaró |
| `e95c5e9` | `BackupManifest.from_dict` | `size_bytes`/`tenant_count`/`project_count` booleanos → coercidos a 1 en el camino de restore |
| `6160ed5` | `ValidationReceipt._validate_counters` + `_payload_to_receipt` | `tests_run=True` con `tests_passed<=1` y `tests_passed=True` siempre, aceptados; el lector defensivo coercaba antes de validar |

La clase de defecto ya tenía dos fixes previos en v0.16.x
(`21087d1` metadata.max_visits, `dbe7f81` Recipe.token_budget/revision
— sustancia del ciclo wi-46 de la identidad archivada). WI-49 completa
el barrido de las superficies restantes con input declarado; las
coerciones internas (`engine.py`, `runcontroller.py`, `ports` para
SQLite) se revisaron y quedan fuera por diseño: o son datos ya
tipados en runtime o son la codificación intencional bool→0/1 de
SQLite.

### Verificación

- RED honesto: los 5 tests nuevos fallaron antes del fix (4 FAILED +
  1 que pasaba por el cross-check equivocado; se endureció su
  `match` a la guarda explícita).
- Tests afectados: 129 passed (plan_loader, backups, h14 receipts,
  workflow_plan, dsl).
- Suite completa: PASS en cada commit (hook pre-commit) y en el bump.
- ruff check + ruff format: limpios.

### Descubrimientos del ciclo

- La deuda P2 del ledger archivado (`cmd_promotion_reconcile` cc=14,
  `_make_schema_validator` cc=13/anidamiento 5) está **caducada**:
  miden cc=7/anidamiento 1 y cc=3/anidamiento 2 tras refactors
  posteriores (WI-29/WI-30 y afines). "Alerta de deuda sin criterios
  vigentes no es deuda real."
- wi-46 no estaba sin trabajo: su sustancia salió en `dbe7f81` y
  `21087d1` sin mencionar el ciclo en los mensajes. Cierre corregido
  con constancia en `evidence/sddk-context-recovery-2026-10-01.md` §2.
- pipelinek 0.43.0 (binario sin gobernar; canon AGENTS.md v0.39.0 no
  instalado) produce veredictos no fiables dentro del entorno
  agéntico: FAILURE falso (~10s) y SUCCESS sin evidencia de ejecución.
  Verificado por ejecución directa; pendiente decisión del operador
  (`evidence/sddk-context-recovery-2026-10-01.md` §6).
