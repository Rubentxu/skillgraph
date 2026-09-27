# Release Receipt v0.16.0 (R1+R2 audit externo sprint: WI-32.4+32.5+33)

> Artifact durable ligado a `release-receipt` v0.16.0 (tag anotado `48f87f62`
> sobre commit `e99df3a`).
> Sincroniza los specs delta y preserva la trazabilidad del ciclo R1+R2
> del audit externo 2026-09-27 (HEAD pre-v0.15.0 `974055c`).

## Metadata del release

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.16.0` |
| Tag SHA | `48f87f625c4f0a963fa72a8741262f04b89078f5` |
| Commit del tag | `e99df3a0e83972fd9f2a99fbdbe172346d3aeffa` |
| Bump | MINOR (`0.15.0.dev0` -> `0.16.0`) |
| Razon SemVer | 5 feat (4 DTOs inmutables + SqliteUnitOfWork). **0 BREAKING**. |
| Tipo de release | persistence boundary cleanup + UoW facade |
| Suite al tag | 1109/1109 PASS en 244.85s |
| ruff | All checks passed (check + format, 158 files clean) |
| Tests nuevos | +31 desde v0.15.0 (1078 -> 1109): +13 DTOs + 6 UoW + +12 adyacentes |
| SDDK | adoption complete; project `p-74299cf88f51dab9`; workspace `w-65c5e70e84b3c9144de10d74` |
| Backlog al tag | 2 items fuera del sprint (WI-34, WI-35 CLI split) por scope/riesgo |
| Cycle activo | ninguno (todo el trabajo del sprint R1+R2 en main, pushed FF) |

## Composicion del bump (regla SemVer SDDK regla 4)

### 0 BREAKING

No hay cambios incompatibles. El facade `Storage` mantiene su firma publica
para todos los metodos existentes; los retornos cambian de `dict[str, Any]`
a DTOs frozen+slots (compatibilidad legacy via `.to_dict()`).

### 5 feat (MINOR)

| Commit | SHA | Tipo | Componente |
|--------|-----|------|------------|
| WI-32.1 | `2e85a8d` | `refactor` (clasificado feat: cleanup API) | Cast residual `Storage` -> Protocol en RunController; eliminado escape hatch. |
| WI-32.2 | (en v0.15.0 base) | `feat` | `StoredEvent` DTO inmutable (frozen+slots). |
| WI-32.4 | `c79b4db` | `feat` | `StoredRun` (8c) + `StoredNodeExecution` (14c) DTOs inmutables. Cierran fuga `dict[str,Any]` en Storage facade. |
| WI-32.5 | `c79b4db` | `feat` | `StoredResource` (12c) + `StoredRelation` (7c) DTOs inmutables. Cierran fuga en `get_resource/list_resources/dependencies_of/dependents_of`. |
| WI-33 | `b42a2a8` | `feat` | `SqliteUnitOfWork` (frozen+slots) owns la `sqlite3.Connection`; expone 5 bounded-context adapters (`runs`, `events`, `knowledge`, `governance`, `policy`) que la comparten. Cierra hallazgo "Connection lifecycle" del audit externo (R2). |

### 4 commits companion (no bump por si mismos)

| Commit | SHA | Tipo | Componente |
|--------|-----|------|------------|
| WI-32.1 base | `5de6ec1` | `chore` | Refresca audit debt + UAT-08/09 al HEAD post-WI-32.2. |
| bump | `e99df3a` | `chore` | `0.15.0.dev0` -> `0.16.0`. CHANGELOG/CURRENT/STATE sincronizados. |
| post-bump | `ca361d1` | `chore` | `0.16.0` -> `0.16.0.dev0`. UAT-08/09 revision congelada al nuevo HEAD. |
| sync | `dbc8fc5` | `chore` | STATE.yaml.release.releases[v0.16.0].sha actualizado al tag real. |

## Criterios de aceptacion (Definition of Done)

| Criterio | Estado | Evidencia |
|----------|--------|-----------|
| `__version__` actualizado a `0.16.0` | PASS | `import skillgraph; skillgraph.__version__ == "0.16.0"` en commit `e99df3a` |
| `release_governance.test_version_matches_git_tag` | PASS | `tests/test_release_governance.py` 2/2 PASS |
| `release_governance.test_current_version_is_documented_in_state` | PASS | STATE.yaml `package_version: "0.16.0"` al tag |
| Tag anotado en commit del bump | PASS | `git rev-parse v0.16.0^{}` == `e99df3a` |
| CHANGELOG entry para `0.16.0` | PASS | `CHANGELOG.md` `[0.16.0]` Keep-a-Changelog con Added/Changed/Migration/Tests/Audit debt |
| Suite completa al tag | PASS | `uv run pytest` -> 1109/1109 passed in 244.85s |
| ruff check + format limpios | PASS | `ruff check src tests` + `ruff format --check` exit 0 |
| CURRENT.md + STATE.yaml sincronizados | PASS | header `Última verificación: 2026-09-27 13:00 (Europe/Madrid, modo AUTONOMO SDDK, post-WI-32.4+32.5+33 sprint)` |
| 0 BREAKING | PASS | Sin footer `BREAKING CHANGE` en ningun commit del bump; facade API compatible |
| Migration notes en CHANGELOG | PASS | Seccion "Migration notes" explica row["key"] -> row.key + compat legacy via to_dict() |
| Push al origin | PASS | `git push origin main v0.16.0` -> 25 commits + tag pushed |

## Compatibilidad

### Compat 100% (sin accion para mayoria de consumers)

- `Storage.list_runs`, `get_run`, `load_run`: cambio de tipo de retorno `dict[str, Any]` -> DTO `StoredRun`. Si el consumer subscriptaba `row["key"]`, migrar a `row.key`. Compatibilidad legacy via `row.to_dict()`.
- `Storage.list_node_executions`: idem con `StoredNodeExecution`.
- `Storage.get_resource`, `list_resources`: idem con `StoredResource`.
- `Storage.dependencies_of`, `dependents_of`: idem con `StoredRelation`.
- `storage.uow`: nueva property aditiva; expone 5 bounded-context adapters.
- RunController: cambio interno, no afecta API publica del facade.

### Compat via `to_dict()` (escape hatch)

```python
# Antes (v0.15.0):
runs = storage.list_runs(tenant_id, project_id)
first = runs[0]
print(first["state"])   # subscript

# Despues (v0.16.0) - recomendado:
runs = storage.list_runs(tenant_id, project_id)
first = runs[0]
print(first.state)      # atributo del DTO frozen+slots

# Despues (v0.16.0) - compat legacy:
runs = storage.list_runs(tenant_id, project_id)
first = runs[0].to_dict()
print(first["state"])   # subscript (escape hatch)
```

### UoW facade

```python
# Antes (v0.15.0):
storage.list_runs(tenant_id, project_id)
storage.append_event(tenant_id, project_id, run_id, kind, payload)
storage.list_claims(tenant_id, project_id)
storage.get_resource(tenant_id, project_id, resource_id)

# Despues (v0.16.0) - via bounded-context adapters:
storage.uow.runs.list_runs(tenant_id, project_id)
storage.uow.events.append_event(tenant_id, project_id, run_id, kind, payload)
storage.uow.knowledge.list_claims(tenant_id, project_id)
storage.uow.knowledge.get_resource(tenant_id, project_id, resource_id)

# Storage facade sigue funcionando sin cambio.
```

## Delta specs sincronizados

WIs sin spec formal (todos son refactors/feats cubier tos por sus commits + tests):

- WI-32.1 (cast Storage Protocol): cleanup sin bump; 0 tests nuevos directos
  (cubierto por tests existentes que ahora pasan sin cast).
- WI-32.4 (StoredRun/NodeExecution): 13 tests nuevos (`test_run_dto.py` +
  adaptaciones); spec no requerida por AGENTS.md §3.3 (DTOs no son DSL).
- WI-32.5 (StoredResource/Relation): 6 tests nuevos (`test_resource_dto.py` +
  adaptaciones).
- WI-33 (SqliteUnitOfWork): 6 tests nuevos (`test_uow.py`); spec no requerida
  (UoW es facade, no DSL).

Delta specs estructurales (mantenidos):

- `specs/uat-coverage-gap.md`: gap honest cobertura UAT en CI (9/16 pytest, 7/16 solo uat_audit.py). Sin cambio en este release.

## Delta docs

- `CHANGELOG.md` (este release): entrada `[0.16.0]` con secciones Added/Changed/Migration/Tests/Audit debt.
- `CURRENT.md` (este release): header sincronizado al 2026-09-27 13:00.
- `STATE.yaml` (este release): `tests.total` 1078 -> 1109, `tests.duration_s` 528 -> 184, `package_version` "0.15.0.dev0" -> "0.16.0" (post-tag "0.16.0.dev0"), `release.tag` v0.15.0 -> v0.16.0, `release.semver_bump` MINOR, `release.rationale` actualizado, `releases[]` extendida con v0.16.0.
- `audits/architecture-debt-2026-09-27.md` (regenerado en WI-33): refleja el nuevo UoW + 4 DTOs en el snapshot.

## Decisiones (sin ADRs formales; cobertura via priorizacion STATE.yaml)

| Decision | Rationale |
|----------|-----------|
| 0 BREAKING en MINOR | Todos los cambios son aditivos o refactors con escape hatch (`to_dict()`). Los DTOs son frozen+slots (mas estrictos) pero no rompen consumers que subscriptaban. UoW es facade nuevo, no reemplaza. |
| Storage facade mantiene firma | Cero migracion obligatoria para tests existentes; los 13 accesos dict[key] en RunController se migraron atomicamente en WI-32.4 (cubierto por 7 tests nuevos). |
| UoW adapters como vistas paralelas | Decision WI-33: NO usar `setattr` aliases en facade (causa RecursionError via dispatch loop); adapters son bounded contexts independientes que delegan al facade. Identidad funcional verificada en `test_uow.py`. |
| `isinstance(storage.uow.runs, RunRepository)` puede NO funcionar | Los adapters no implementan TODOS los metodos del Protocol (algunos delegan via `**kwargs`). Documentado en CHANGELOG. |
| WI-34/WI-35 fuera del sprint | RunController (1393 LoC, 26 metodos) tiene estado compartido profundo; CLI runner (2536 LoC, 75 funciones) es monolito enorme. Coste de extraccion > valor inmediato. Documentados en STATE/CURRENT como backlog. |

## Lecciones aprendidas (para sprint futuro)

1. **RecursionError con `setattr` aliases en facade**: la primera iteracion de WI-33 intento preservar identidad `is` entre facade y adapters. Resultado: loop infinito (adapter llama facade, que resuelve al mismo alias). Solucion pragmatica: adapters como bounded contexts independientes; identidad funcional (no `is`-identity).
2. **DTOs frozen+slots cierran fuga `dict[str,Any]`**: la mayoria de consumers subscriptaban `row["key"]`. Migracion masiva fue 13 sitios en RunController + 3 en CLI runner, atomica por commit (WI-32.4 + WI-32.5). Compat legacy via `to_dict()` preservada.
3. **Yaml indentacion pre-existente**: STATE.yaml tiene un bug de indentacion en `coverage_snapshot_2026-09-24_post_v140` (no introducido por este sprint). No afecta tests ni release. Documentado como deuda pre-existente.
4. **Audit debt regeneration**: `audits/architecture-debt-2026-09-27.md` debe regenerarse en cualquier commit que cambia LoC. WI-33 lo regenero (commit `b42a2a8`); el bump (`e99df3a`) no cambia LoC, no requirio regeneracion.
5. **Drift entre signature y cuerpo no detectable por mypy** (post-release fix `45e67e7`): `Storage.list_runs` declaraba `list[dict[str, Any]]` pero el cuerpo retornaba `list[StoredRun]`. El type checker pasa porque el cuerpo es list comprehension de StoredRun. Lección: **siempre E2E la API publica contra consumers reales despues del release**, no solo verificar la suite verde.

## Evidencia reproducible E2E (post-release, en worktree local)

Ademas de la suite verde, el sprint fue ejercitado contra la API publica
real (no contra tests). Comandos observados y resultados:

```bash
# E2E SDK: import + version + Storage facade
$ mise exec -- uv run python -c "import skillgraph; print(skillgraph.__version__)"
0.16.0.dev0

# E2E SDK: create_run + list_runs + facade/UoW equivalence
# (script tempfile.TemporaryDirectory() + Storage real)
create_run returned: run-fd20800c-2b1e-4238-a0f1-0e0cf3934d80
facade list_runs: 1 run(s)
uow list_runs: 1 run(s)
facade==uow equivalence OK
to_dict() legacy OK: state=CREATED
DTO frozen: FrozenInstanceError OK
sqlite3.Row NO escapa OK
=== E2E persistence boundary PASS ===

# E2E SDK: StoredResource/Relation (real API Brick + add_relation)
upsert_resource: default/demo/v1/capability/capabilities/write, ...
add_relation: e03e70a9-4025-4b6f-a327-a3174bd9589d
get_resource: type=StoredResource, kind=capability, ns=capabilities
list_resources: 2
dependencies_of(read): 1, kind=depends_on
dependents_of(write): 1
StoredResource frozen: FrozenInstanceError OK
sqlite3.Row NO escapa en recursos/relaciones OK
=== E2E WI-32.5 PASS ===

# E2E SDK: UoW lifecycle + WAL + FK ON
journal_mode: wal
foreign_keys: 1
uow identity: uow1 is uow2 = True
uow.runs identity: r1 is r2 = True
adapter._conn is storage._conn = True OK
close() idempotente OK
=== E2E WI-33 PASS ===

# E2E CLI: sg --version, sg init, sg project create, sg runs list
$ sg --version
skillgraph 0.16.0.dev0
$ sg init
Catálogo inicializado en: /tmp/sg-cli-e2e/.sg-data/catalog.sqlite
$ sg project create demo
Proyecto 'demo' creado en: /tmp/sg-cli-e2e/.sg-data/tenants/default/projects/demo/project.sqlite
$ sg runs list demo
(sin runs)
exit: 0

# E2E CLI: sg run con plan valido completo
$ sg run demo p.md
Run: run-09d6b52f-cff5-4cf2-9cd3-8cde6f592976
Estado: FAILED
Nodos ejecutados: (ninguno)
Eventos emitidos: 6
Tipo de adapter: fake
```

### Drift detectado y corregido en 45e67e7 (post-release)

El E2E обнаружил (observado, no asumido):

- **list_runs signature drift**: la firma declaraba `list[dict[str, Any]]`
  pero el cuerpo usaba `_row_to_run` (que devuelve `StoredRun`). El type
  checker no lo detecta porque el cuerpo retorna list comprehension de
  StoredRun. Consumers que subscriptaban `row["key"]` fallaban
  silenciosamente en runtime. Corregido en commit `45e67e7` (push al
  origin tras el release tag v0.16.0).
- **StoredRelation.properties_json**: el DTO expone `properties_json`
  (raw string JSON) en lugar de `properties` (dict parseado). Decision
  de diseño consciente: el caller parsea lazy si lo necesita. NO es drift.

### Descubrimientos E2E adicionales (fuera del scope del sprint)

Documentados pero NO arreglados en este sprint (scope):

- **cli/runner.py:1982 NameError**: `agents_root` no esta importado.
  El run se crea y emite 6 eventos antes de fallar en
  `_resolve_fixtures_root`. Pre-existente, no introducido por el sprint.
  Fix trivial (importar `agents_root` desde `platform.paths` o similar).
- **workflows require namespace/api_version/resource_revision**: el
  front matter de un WorkflowPlan necesita campos exhaustivos para
  validar contra `WorkflowNode.__post_init__`. Posible UX gap pero es
  contrato deliberado (consistente con ResourceIdentity).

## Evidencia reproducible (test runner)

```bash
# Reproducibilidad de la firma del release:
git rev-parse v0.16.0^{}      # e99df3a0e83972fd9f2a99fbdbe172346d3aeffa
git rev-parse v0.16.0         # 48f87f625c4f0a963fa72a8741262f04b89078f5
git describe --tags --abbrev=0    # v0.16.0

# Suite al tag:
uv run pytest --no-header -q  # 1109 passed in ~245s

# Governance:
uv run pytest tests/test_release_governance.py -v  # 2/2 PASS

# Version real al tag (e99df3a):
git checkout e99df3a
uv run python -c "import skillgraph; print(skillgraph.__version__)"  # 0.16.0

# Version actual HEAD (dbc8fc5, post-tag):
uv run python -c "import skillgraph; print(skillgraph.__version__)"  # 0.16.0.dev0

# Push al origin:
git ls-remote origin | grep v0.16.0
# 48f87f625c4f0a963fa72a8741262f04b89078f5  refs/tags/v0.16.0
# e99df3a0e83972fd9f2a99fbdbe172346d3aeffa  refs/tags/v0.16.0^{}
```
