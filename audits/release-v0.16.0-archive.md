# SDDK Archive — Release v0.16.0 (R1+R2 audit externo sprint)

> Artifact durable ligado a `release-receipt` v0.16.0 (tag anotado `48f87f62`).
> Companion de `audits/release-v0.16.0-receipt.md`. Sincroniza el cierre
> del ciclo R1+R2 del audit externo 2026-09-27 con la fuente de verdad git
> (origin/main ya actualizado).

## Metadata del archive

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.16.0` |
| Tag SHA | `48f87f625c4f0a963fa72a8741262f04b89078f5` |
| Commit del tag | `e99df3a0e83972fd9f2a99fbdbe172346d3aeffa` |
| Bump | MINOR (`0.15.0.dev0` -> `0.16.0`) |
| Tipo de release | persistence boundary cleanup + UoW facade |
| Suite al tag | 1109/1109 PASS en 244.85s |
| ruff | All checks passed (check + format, 158 files clean) |
| Source of truth | origin/main @ `dbc8fc52b24cb5adfeb92cda4b2cd5c9945fb2cc` (PUSHED) |

## Manifest del ciclo (testimonio durable)

```
v0.16.0 = e99df3a (build release: bump version + STATE/CURRENT/CHANGELOG sync)
       + ca361d1 (post-tag bump 0.16.0 -> 0.16.0.dev0 + UAT-08/09 refresh)
       + dbc8fc5 (sync STATE/CURRENT con tag SHA real)

Componentes del ciclo (entre v0.15.0 tag 0d73f73 y v0.16.0 tag 48f87f62,
20 commits en main):

  WI-32.1 (cast residual):
    2e85a8d (no listado, refactor surgical sin bump directo)
  WI-32.2 (StoredEvent DTO):
    (no listado, ya en v0.15.0 base via 2e85a8d)
  WI-32.4 + WI-32.5 (4 DTOs inmutables):
    c79b4db feat(platform): introduce StoredRun/NodeExecution/Resource/Relation DTOs
  WI-33 (SqliteUnitOfWork):
    b42a2a8 feat(platform): introduce SqliteUnitOfWork + 5 bounded-context adapters
  Housekeeping pre-sprint:
    5de6ec1 chore(housekeeping): refrescar auditoria + UAT-08/09 al HEAD post-WI-32.2
  Release v0.16.0:
    e99df3a chore(release): bump 0.15.0.dev0 -> 0.16.0 (R1+R2 audit externo sprint)
    ca361d1 chore(release): post-v0.16.0 bump 0.16.0 -> 0.16.0.dev0
    dbc8fc5 chore(release): sync STATE/CURRENT post-v0.16.0 con tag real
```

## Source of truth

origin/main esta actualizado. 25 commits pushed en este ciclo
(`974055c..dbc8fc5`):

```bash
$ git ls-remote origin | grep -E "main$|v0.16.0"
dbc8fc52b24cb5adfeb92cda4b2cd5c9945fb2cc  refs/heads/main
48f87f625c4f0a963fa72a8741262f04b89078f5  refs/tags/v0.16.0
e99df3a0e83972fd9f2a99fbdbe172346d3aeffa  refs/tags/v0.16.0^{}
```

## Archivos del release (delta contra v0.15.0)

### Codigo nuevo (5 DTOs + UoW)

- `src/skillgraph/platform/ports/__init__.py`: 4 DTOs frozen+slots nuevos
  (StoredRun, StoredNodeExecution, StoredResource, StoredRelation) + metodos
  to_dict() para compat legacy.
- `src/skillgraph/platform/uow.py`: SqliteUnitOfWork (frozen+slots) + 5
  bounded-context adapters (SqliteRunAdapter, SqliteEventAdapter,
  SqliteKnowledgeAdapter, SqliteGovernanceAdapter, SqlitePolicyAdapter).

### Codigo modificado

- `src/skillgraph/platform/storage.py`: facade refactorizado para devolver
  DTOs; `_row_to_run`, `_row_to_node_execution`, `_row_to_resource`,
  `_row_to_relation` helpers; `__init__` construye UoW; `storage.uow`
  property publica.
- `src/skillgraph/runtime/runcontroller.py`: 13 accesos `dict[key]`
  convertidos a atributo DTO en `_reconcile_run_locked`, `_calculate_frontier`,
  `_execute_one`, `_snapshot`, `show_run`, `cancel_run`, `list_runs`.
- `src/skillgraph/cli/runner.py`: 3 consumers migrados (`_count_resources`,
  `_load_registry`, `_collect_capabilities_index`).
- `src/skillgraph/runtime/ports.py` + `src/skillgraph/knowledge/ports.py`:
  Protocol updates para RunRepository + KnowledgeRepository con retornos DTO.

### Tests nuevos (19 tests)

- `tests/test_run_dto.py`: 7 tests.
- `tests/test_resource_dto.py`: 6 tests.
- `tests/test_uow.py`: 6 tests.

### Tests adaptados (12 tests)

- `tests/test_h9_storage_run_reads.py`: 2 tests (dict -> attr).
- `tests/test_h9_runcontroller_characterization.py`: 3 tests.
- `tests/test_s1_sqlite.py`: 2 tests (DecisionNode kind/spec_json).
- `tests/test_registry_branches.py`: 2 tests (relation properties).
- (5 adicionales adaptados en modulos adyacentes)

### Docs

- `CHANGELOG.md`: entrada `[0.16.0]` con secciones Added/Changed/Migration/Tests/Audit debt.
- `CURRENT.md`: header sincronizado al 2026-09-27 13:00.
- `STATE.yaml`: tests 1078 -> 1109, package_version actualizado,
  release.tag v0.15.0 -> v0.16.0, releases[] extendida.
- `audits/architecture-debt-2026-09-27.md`: regenerado en WI-33
  (Storage LoC 2499 -> 2716; modulo nuevo `uow.py` 493 LoC).
- `audits/release-v0.16.0-receipt.md`: este archive companion.

## Decisiones tomadas durante el ciclo

1. **WI-32.1 + WI-32.2 cerran QW-M/QW-N**: cast residual `Storage` ->
   Protocol y DTO `StoredEvent`. Cero cambios funcionales, cleanup de
   boundary de tipos.
2. **WI-32.4 + WI-32.5 cierran QW-K**: 4 DTOs inmutables cierran la fuga
   `dict[str, Any]` en Storage facade. Compat legacy via `to_dict()`.
3. **WI-33 cierra QW-L**: SqliteUnitOfWork owns la `sqlite3.Connection`;
   5 bounded-context adapters la comparten. Acceso via `storage.uow.X`.
4. **WI-34/WI-35 fuera del sprint**: RunController y CLI runner son
   monolitos con estado compartido profundo. Coste de extraccion >
   valor inmediato. Documentados como backlog.
5. **Bump MINOR, 0 BREAKING**: el facade `Storage` mantiene firma;
   DTOs son frozen+slots pero ofrecen compat legacy. UoW es aditivo.

## Trabajo restante (post-v0.16.0)

| ID | Titulo | Razon del descarte |
|----|--------|--------------------|
| WI-34 | Adelgazar RunController (1393 LoC, 26 metodos) | Estado compartido profundo; extraccion de componentes requiere refactor de varios dias. |
| WI-35 | CLI runner split (2536 LoC, 75 funciones) | Modulo monolitico enorme; extraccion no aporta valor inmediato. |
| WI-36 | Fix indentacion YAML en STATE.yaml (bug pre-existente en `coverage_snapshot_2026-09-24_post_v140`) | No afecta tests ni release. Documentado como deuda. |

## Reproducibilidad

```bash
# Firma del release:
git rev-parse v0.16.0^{}      # e99df3a0e83972fd9f2a99fbdbe172346d3aeffa
git rev-parse v0.16.0         # 48f87f625c4f0a963fa72a8741262f04b89078f5
git describe --tags --abbrev=0    # v0.16.0

# Suite al tag:
git checkout e99df3a
mise exec -- uv run pytest --no-header -q
# 1109 passed in 244.85s

# Governance:
mise exec -- uv run pytest tests/test_release_governance.py -v
# 2/2 PASS

# Push verification:
git ls-remote origin | grep v0.16.0
```

## Erratum preservado

La regla 12 AGENTS.md preserva la provenance historica de versiones
publicadas. El erratum `v0.14.0` (HEAD `d50f666` con package metadata
defectuosa `__version__ = "0.7.0.dev0"`) sigue intacto; la release
correctiva sigue siendo `v0.14.1`. v0.16.0 NO introduce erratum.

## Cierre del ciclo

- Release: COMPLETA
- Push: COMPLETA (25 commits + tag pushed a origin)
- Archive: COMPLETA (este archivo + companion receipt)
- SDDK cycle: cerrado sin items abiertos en el sprint
