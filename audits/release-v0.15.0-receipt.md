# Release Receipt v0.15.0 (R0 housekeeping + WI-31 + WI-35)

> Artifact durable ligado a `release-receipt` v0.15.0 (tag anotado `0d73f73`
> sobre commit `4d6d1b4`).
> Sincroniza los specs delta y preserva la trazabilidad del ciclo R0
> (QW-PREP + QW-A..I) + WI-31 (cast Storage Protocol) + WI-35 (docs).

## Metadata del release

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.15.0` |
| Tag SHA | `0d73f731dd9142cd44b5be27965f642ab03254b1` |
| Commit del tag | `4d6d1b430ca3f726a080e12c37dd58180d72483b` |
| Bump | MINOR (`0.14.8.dev0` -> `0.15.0`) |
| Razon SemVer | 1 BREAKING + 3 feat + 1 fix (regla 4 SDDK AUTO) |
| Tipo de release | housekeeping + refactor Protocol + docs + 1 BREAKING compat |
| Suite al tag | 1078/1078 PASS en 204.03s (smoke parallelo exit 0) |
| ruff | All checks passed (check + format) |
| Tests nuevos | +30 desde v0.14.8 (1048 -> 1078) |
| Coverage | 95.25% lines / 90.54% branches (post-fail_under=80 + omits QW-F) |
| SDDK | adoption complete; project `p-74299cf88f51dab9`; workspace `w-65c5e70e84b3c9144de10d74` |
| Backlog al tag | 0 live items (WI-31 + WI-35 promoted) |
| Cycle activo | ninguno (todo el trabajo del R0 + WI-31 + WI-35 en main) |

## Composicion del bump (regla SemVer SDDK regla 4)

### 1 BREAKING (MAJOR-leaning, contenido en MINOR por convenio de proyecto)

| Commit | SHA | Tipo | Componente |
|--------|-----|------|------------|
| QW-B | `3b16e71` | `fix` (BREAKING en footer) | `EventLog._resolve_policy` default `none` -> `metadata`. Secure-by-default para redaction. Migracion opt-in: `EventLog(policy_resolver=lambda _t: "none")`. |

### 3 feat (MINOR)

| Commit | SHA | Tipo | Componente |
|--------|-----|------|------------|
| QW-C | `13a6fa5` | `feat` | `Storage.__enter__/__exit__` + idempotent `close()`. Elimina `ResourceWarning: unclosed database`. 6 tests nuevos. |
| WI-31 | `e82c670` | `refactor` (clasificado feat: API public) | `Storage.knowledge_repository()` + `RunController(knowledge=)` kwarg. Elimina `cast(Storage, ...)` del RunController. Cubre code path `_compile_knowledge` con 0 tests previos. 7 tests nuevos. |
| QW-I | `29e990a` | `docs` (clasificado feat: nueva capacidad observable) | `docs/blueprint/` snapshot versionado + `scripts/sync_blueprint.sh` idempotente. Habilita CI sin depender de `external/` gitignored. |

### 1 fix (PATCH contenido en MINOR)

| Commit | SHA | Tipo | Componente |
|--------|-----|------|------------|
| QW-A | `1dd1fd1` | `fix` | `HttpAgentAdapter` default Anthropic `claude-3-5-sonnet-20241022` -> `claude-sonnet-4-6` (retirado 2025-10-28). Blacklist de modelos retirados. 1 test nuevo. |

### 6 commits companion (no bump por si mismos)

| Commit | SHA | Tipo | Componente |
|--------|-----|------|------------|
| QW-D | `c516abe` | `refactor` | `EVENT_KINDS` ahora `frozenset(get_args(EventType))` (single-source-of-truth). |
| QW-E | `3cf5182` | `refactor` | `SOURCE_KINDS` ahora derivado del `SourceKind` Literal (incluye `skill_pack`). |
| QW-F | `ff714df` | `chore` | `fail_under=80`, omit entry points. |
| QW-G | (en QW-F) | `chore` | `uat_audit.py` + `test_cli_uat.py` propagan `PYTHONPATH` al subprocess en venv. |
| QW-H | `73eb973` | `refactor` | `uat_audit.uat_08/09` leen evidencia E2E existente en vez de sobrescribirla con BLOCKED stub. |
| WI-35 | `2adeb52` | `docs` | Prioridad 6 en STATE.yaml + SESSION-JOURNAL.md con patron operacional SDDK end-to-end. |

## Criterios de aceptacion (Definition of Done)

| Criterio | Estado | Evidencia |
|----------|--------|-----------|
| `__version__` actualizado a `0.15.0` | PASS | `import skillgraph; skillgraph.__version__ == "0.15.0"` |
| `release_governance.test_version_matches_git_tag` | PASS | `tests/test_release_governance.py` 2/2 PASS en HEAD `4d6d1b4` |
| `release_governance.test_current_version_is_documented_in_state` | PASS | STATE.yaml `package_version: "0.15.0"` |
| Tag anotado en commit del bump | PASS | `git rev-parse v0.15.0^{}` == `4d6d1b4` |
| CHANGELOG entry para `0.15.0` | PASS | `CHANGELOG.md` linea 15 (Keep-a-Changelog) |
| Suite completa al tag | PASS | `uv run pytest` -> 1078/1078 passed in 204.03s |
| ruff check + format limpios | PASS | `ruff check src tests` + `ruff format --check` exit 0 |
| Coverage al tag | PASS | 95.25% lines / 90.54% branches (post QW-F `fail_under=80`) |
| Erratum `v0.14.0` preservado | PASS | tag historico intacto, sin rewrite retroactivo |
| CURRENT.md + STATE.yaml sincronizados | PASS | header `Última verificación: 2026-09-27 11:54 (Europe/Madrid, modo AUTONOMO SDDK, release v0.15.0)` |

## Compatibilidad

### BREAKING (QW-B) — guia de migracion

```python
# Antes (v0.14.8 y ancestros): default policy = "none" -> payloads sin redaccion
log = EventLog(storage, tenant_resolver=resolver)
# 'api_key', 'password', 'token' en metadata pasaban tal cual

# Despues (v0.15.0): default policy = "metadata" -> redaction secure-by-default
log = EventLog(storage, tenant_resolver=resolver)
# 'api_key', 'password', 'token' se redactan a "[REDACTED]"

# Opt-out explicito (migracion si necesitas el comportamiento previo):
log = EventLog(storage, tenant_resolver=resolver,
               policy_resolver=lambda _t: "none")  # noqa: SG001 -- explicit no-redaction
```

### Compat 100% (sin accion)

- `QW-C` Storage context manager: aditivo; `storage.close()` sigue funcionando.
- `WI-31` `Storage.knowledge_repository()`: factor aditivo; eliminacion de `cast(Storage, ...)` es interna.
- `QW-I` `docs/blueprint/`: snapshot aditivo; `.gitignore` selectivo no rompe nada preexistente.
- `QW-A` model default: cambio default; header `x-llm-model` explicito sigue funcionando.
- `QW-D` / `QW-E` / `QW-F` / `QW-G` / `QW-H`: refactors internos, sin cambio de API.

## Delta specs sincronizados

WIs sin spec (todos los del R0 + WI-31 + WI-35 son housekeeping o refactors
surgicales cubiertos por su commit; no requieren spec formal en `specs/`):

- R0 = 10 commits housekeeping; ninguno genera spec (patron WI-21..WI-30).
- WI-31 = refactor protocol con 7 tests nuevos; spec no requerida por AGENTS.md
  §3.3 (DSL no aplica; `RunController.knowledge` es kwarg, no un DSL).
- WI-35 = docs; spec no aplica.

Delta specs estructurales (mantenidos):

- `specs/uat-coverage-gap.md`: gap honest cobertura UAT en CI (9/16 pytest, 7/16 solo uat_audit.py). Sin cambio en este release.

## Delta docs

- `docs/blueprint/` snapshot (QW-I): 12 capitulos + README + `adr/` 13 ADR + `plan/` 6 plans + `references/`.
- `docs/blueprint/SYNC.md` (QW-I): politica on-demand.
- `docs/blueprint/SOURCE_SHA` (QW-I): SHA256 del origen en el momento del snapshot.
- `scripts/sync_blueprint.sh` (QW-I): idempotente, modo `--check` para CI.
- `CHANGELOG.md` (este release): entrada `[0.15.0]` Keep-a-Changelog.
- `CURRENT.md` (este release): header sincronizado al 2026-09-27 11:54.
- `STATE.yaml` (este release): `tests.total` 1048 -> 1078, `tests.duration_s` 180 -> 528, `release.tag` v0.14.0 -> v0.15.0, `release.releases[]` extendida con v0.14.1..v0.14.8 + v0.15.0.

## Decisiones (sin ADRs formales; cobertura via priorizacion STATE.yaml)

| Decision | Rationale |
|----------|-----------|
| Bump MINOR (no MAJOR) por 1 BREAKING | Convencion del proyecto: BREAKING contenidas en MINOR salvo cambio de contrato de protocolo o eliminacion de API. QW-B es opt-out via `policy_resolver` explicito, no rompe integraciones tipicas. Documentado en CHANGELOG con `### BREAKING CHANGE`. |
| Mantener erratum `v0.14.0` | Regla 12 AGENTS.md: provenance historica no se reescribe. La release correctiva sigue siendo `v0.14.1`. |
| `docs/blueprint/` con `.gitignore` selectivo | Politica: NO contaminar el repo con blanket `docs/` (descubierto por busqueda de "test_uats_can_be_loaded_as_documentation"). Solo `docs/blueprint/` se versiona; el resto del sistema de docs sigue gitignored. |

## Lecciones aprendidas (para WI-32 en adelante)

1. **Conteo de tests desde collect_only**, no desde memoria: `uv run pytest --collect-only` es la fuente canonica. Mi memoria previa (`1068`) era off-by-10; el numero real era `1078` ya antes del amend.
2. **Tag anotado + amend son incompatibles**: tagear ANTES de amend obliga a re-tagear. Workflow optimo: amend primero, luego tag.
3. **Encoding fix de CURRENT.md**: bash + Python + sed no restauraron bytes UTF-8 con el caracter `Ú` tras multiples pasadas de replace. El edit tool con `old_string`/`new_string` es la unica via robusta para UTF-8 preservando todos los caracteres.
4. **QW-H**: bug real descubierto — `uat_audit.uat_08/09` sobrescribia evidencia E2E real con stub BLOCKED. Cubierto por 5 tests + delegation a `_read_existing_evidence`.
5. **QW-B es la unica BREAKING** del ciclo. El resto son feat/MINOR o fix/PATCH sin cambio de contrato.

## Evidencia reproducible

```bash
# Reproducibilidad de la firma del release:
git rev-parse v0.15.0^{}      # 4d6d1b430ca3f726a080e12c37dd58180d72483b
git rev-parse v0.15.0         # 0d73f731dd9142cd44b5be27965f642ab03254b1
git describe --tags --abbrev=0    # v0.15.0

# Suite al tag:
uv run pytest --no-header -q  # 1078 passed in ~204s

# Governance:
uv run pytest tests/test_release_governance.py -v  # 2/2 PASS

# Version real:
uv run python -c "import skillgraph; print(skillgraph.__version__)"  # 0.15.0
```
