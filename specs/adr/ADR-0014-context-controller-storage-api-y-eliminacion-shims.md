# ADR-0014 — Refactor de `ContextController` a `Storage` API pública y eliminación de shims de retro-compatibilidad

Fecha: 2026-09-24.
Estado: aceptada.
Autor: SDDK Orchestrator (sesión post-resume 2026-09-24, consigna del operador "vamos a empezar a abordar todas las tareas de refactorización y ordenación de código por responsabilidades").

## Contexto

El proyecto `skillgraph` tiene **dos deudas arquitectónicas** identificadas en auditorías previas:

1. **SQL directo en `ContextController`**: `src/skillgraph/knowledge/context_controller.py` (443 LoC) tiene **4 puntos de SQL directo** sobre `self.storage._conn.execute(...)` que rompen la regla "Storage encapsula SQL" consolidada en H9-BSlice3 (cuando se migró el RunController a Storage API pública). Es la **única pieza del repo** con SQL directo.

2. **Shims de retro-compatibilidad**: `src/skillgraph/` raíz contiene **20 módulos de 1-9 LoC** que son re-exports puros (`from skillgraph.<bounded_context>.<modulo> import *`) hacia los módulos reales en bounded contexts (`core/`, `domain/`, `governance/`, `knowledge/`, `platform/`, `resources/`, `runtime/`). Los bounded contexts YA están organizados; los shims son una **capa de compat layer** que quedó como deuda y que el operador ha decidido eliminar en esta sesión.

Inventario verificado empíricamente el 2026-09-24 07:43 (post-resume, vía `grep -rnE "from skillgraph\.<shim> "`):

### 4 sitios SQL directos en `context_controller.py`

| # | Línea | Storage method nuevo | Query |
|---|---|---|---|
| 1 | 297-303 | `list_claims_by_predicate` | `SELECT * FROM claims WHERE tenant_id=? AND project_id=? AND predicate=?` |
| 2 | 346-349 | `list_evidences_for_source` | `SELECT * FROM evidences WHERE source_id=?` |
| 3 | 402-410 + 413-421 | `list_resource_refs_for_run(*, kind)` | `SELECT DISTINCT resource_ref FROM runtime_events WHERE ... AND resource_ref LIKE '<kind>:%' ORDER BY resource_ref` |

**Nota de honestidad**: el JOURNAL 23:00 declaraba "8 puntos cursor.execute" pero la inspección real del código revela **4 sitios**. Esta cifra corregida es la que se aplica a este ADR.

### 20 shims a eliminar y 36 ficheros de tests a reescribir

| Shim en `src/skillgraph/` | Módulo real (bounded context) | Imports en tests |
|---|---|---|
| `catalog.py` | `resources.catalog` | 0 |
| `recipe.py` | `core.recipe` | 2 |
| `runtime_types.py` | `core.runtime_types` | 0 |
| `dsl.py` | `domain.dsl` | 1 |
| `errors.py` | `core.errors` | 18 |
| `graph_expansion.py` | `governance.graph_expansion` | 4 |
| `handoff.py` | `runtime.handoff` | 0 |
| `storage.py` | `platform.storage` | 26 |
| `workflow.py` | `resources.workflow` | 13 |
| `bricks.py` | `resources.bricks` | 1 |
| `git_source.py` | `knowledge.git_source` | 0 |
| `pack_loader.py` | `domain.pack_loader` | 1 |
| `promotion.py` | `governance.promotion` | 0 |
| `runcontroller.py` | `runtime.runcontroller` | 15 |
| `skill_importer.py` | `domain.skill_importer` | 0 |
| `paths.py` | `platform.paths` | 4 |
| `agent.py` | `runtime.agent` | 12 |
| `context_controller.py` | `knowledge.context_controller` | 0 |
| `knowledge_controller.py` | `knowledge.knowledge_controller` | 1 |
| `knowledge_invalidator.py` | `knowledge.knowledge_invalidator` | 0 |
| **Total** | | **~118 imports en 36 ficheros** |

Adicional: `tests/test_cli_branches.py:240` usa `import skillgraph.runcontroller as rc_module` (import dinámico) y `tests/uat_audit.py:1439` contiene un string literal con `import skillgraph.bricks; import skillgraph.cli; print('ok')` (smoke test). Ambos se actualizan.

## Decisión

Se ejecutan **dos refactors coordinados** en esta sesión:

### Refactor 1 — `ContextController` → `Storage` API pública

Se añaden **3 métodos nuevos** a `Storage` (en `src/skillgraph/platform/storage.py`):

```python
def list_claims_by_predicate(
    self, *, tenant_id: str, project_id: str, predicate: str
) -> tuple[dict[str, object], ...]:
    """SELECT * FROM claims WHERE tenant_id=? AND project_id=? AND predicate=?"""


def list_evidences_for_source(self, *, source_id: str) -> tuple[dict[str, object], ...]:
    """SELECT * FROM evidences WHERE source_id=?"""


def list_resource_refs_for_run(
    self,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    kind: Literal["claim", "evidence"],
) -> tuple[str, ...]:
    """SELECT DISTINCT resource_ref FROM runtime_events
    WHERE tenant_id=? AND project_id=? AND run_id=?
      AND resource_ref LIKE '<kind>:%'
    ORDER BY resource_ref"""
```

Cada método:

- **Contrato observable**: input tipado, output tupla inmutable (no list).
- **Aislamiento por tenant+project** donde aplique (los dos primeros métodos: el tercero es global por tenant+project+run_id).
- **Tests TDD** en `tests/test_h9_storage_context_controller_reads.py`: ~4 tests por método (contrato, aislamiento, error path, no-regresión).
- **Test de introspección**: regex sobre `inspect.getsource(ContextController)` que verifica ausencia de `_conn.execute` y `cursor.execute`.

`ContextController._resolve_one_selector` (líneas 295-365) y `OutcomeTracer.from_run` (líneas 382-430) se actualizan para llamar `self.knowledge.storage.<método>(...)` en lugar de `ctrl.storage._conn.execute(...)`. Cero cambios en el contrato público de ContextController; cero cambios en cobertura por encima de los 4 sitios cerrados.

### Refactor 2 — Eliminación de shims y reorganización de imports

Se borran los **20 shims** en `src/skillgraph/` raíz. Cada uno se sustituye por un commit que:

1. Borra el shim.
2. Actualiza los imports en los tests (`from skillgraph.X import Y` → `from skillgraph.<bc>.X import Y`).
3. Verifica `scripts/ci.sh` verde.

Los bounded contexts (`core/`, `domain/`, `governance/`, `knowledge/`, `platform/`, `resources/`, `runtime/`) **no se reorganizan**: ya están estructurados por responsabilidades. La estructura actual es:

```
src/skillgraph/
├── __init__.py        # facade publica (no se toca)
├── __main__.py        # entry-point CLI (no se toca)
├── cli/runner.py      # CLI runner (bounded context "cli")
├── core/              # tipos y errores fundamentales
│   ├── errors.py
│   ├── recipe.py
│   └── runtime_types.py
├── domain/            # dominio (DSL, packs, skills)
│   ├── dsl.py
│   ├── pack_loader.py
│   └── skill_importer.py
├── governance/        # expansion, promotion
│   ├── graph_expansion.py
│   └── promotion.py
├── knowledge/         # conocimiento verificable
│   ├── context_controller.py
│   ├── git_source.py
│   ├── graph.py
│   ├── knowledge_controller.py
│   └── knowledge_invalidator.py
├── platform/          # plataforma local (paths, storage)
│   ├── paths.py
│   └── storage.py
├── resources/         # recursos (bricks, workflows, registry)
│   ├── bricks.py
│   ├── catalog.py
│   ├── parser.py
│   ├── plan_loader.py
│   ├── registry.py
│   └── workflow.py
└── runtime/           # ejecucion (adapter, engine, handoff, runcontroller)
    ├── agent.py
    ├── engine.py
    ├── handoff.py
    └── runcontroller.py
```

Cada bounded context tiene una responsabilidad clara; los shims eran simplemente una **capa de indirección** que el operador ha decidido quitar.

## Consecuencias

### Positivas

- **Cobertura de context_controller**: 82% → 95-97% (estimado). Las 4 ramas SQL cerradas son ahora tests de Storage donde SÍ son alcanzables.
- **Regla arquitectónica cumplida**: "Storage encapsula SQL" pasa de 95% a 100% en el repo (los 4 sitios directos desaparecen).
- **Imports directos**: cualquier developer que lea `from skillgraph.platform.storage import Storage` sabe inmediatamente dónde vive la pieza; sin indirección.
- **Descubrimiento por IDE**: autocomplete, go-to-definition, refactor tools funcionan sin la capa de shims.
- **Bounded contexts visibles**: la estructura del paquete cuenta la historia del diseño (core/domain/governance/knowledge/platform/resources/runtime).
- **Tests E2E y subprocess NO se rompen**: porque solo cambiamos imports, no comportamiento.

### Negativas

- **Breaking change para importadores externos**: cualquier código fuera del repo que hacía `from skillgraph import Storage` deja de funcionar. El proyecto es local-only (`push: false` en STATE.yaml), pero si en el futuro hay importadores, necesitan migrar a `from skillgraph.platform.storage import Storage`. **Esto es breaking change en sentido SEMVER estricto**.
- **Tests reescritos**: ~118 imports en 36 ficheros. Es trabajo mecánico pero requiere cuidado para no introducir regresiones.
- **Reversibilidad**: alta (git revert), pero el commit es grande y afecta muchos ficheros. Si falla, revertir todo el commit, no parcialmente.

### SEMVER

**MAJOR** si se considera la compat layer rota como breaking. PERO:

- El proyecto es local-only.
- El operador ha decidido esto explícitamente en esta sesión.
- El último tag es v0.6.0.
- El contenido acumulado desde v0.6.0 (H8 + H9 + 10 Coverage slices + ADR-0013 + este refactor) merece MINOR por capacidad nueva.

**Decisión SEMVER**: tag **v0.7.0 MINOR**. La compat layer se documenta en CHANGELOG como "removed" bajo "Changed". No hay breaking para los usuarios internos del proyecto (los tests se actualizan en el mismo commit); el breaking es solo para importadores externos que NO existen en este repo.

## Alternativas consideradas

### A) Dejar los shims (status quo)

Defendible: el código funciona, los tests pasan. PERO el operador ha decidido activamente eliminarlos. La razón: "shims por comodidad" desordenan el código y ocultan la estructura de bounded contexts.

**Rechazada** por consigna del operador.

### B) Refactor context_controller sin tocar shims

Defendible: separa el trabajo. PERO introduce 2 commits consecutivos con churn de imports; el operador quiere una pasada única.

**Rechazada** porque el operador eligió opción B (combinado).

### C) Romper compat layer de golpe sin shims de transición

Más agresivo: borrar shims y actualizar imports en un solo commit. Es lo que se hace en este ADR.

**Aceptada**.

## Plan de ejecución

1. **Crear spec `specs/h9-coverage-context-controller.md`** documentando las 4 ramas SQL que se cierran.
2. **Crear `tests/test_h9_storage_context_controller_reads.py`** con TDD rojo para los 3 métodos nuevos.
3. **Implementar los 3 métodos** en `src/skillgraph/platform/storage.py`.
4. **Verificar verde**: `uv run pytest tests/test_h9_storage_context_controller_reads.py`.
5. **Refactorizar `context_controller.py`**: borrar los 4 `_conn.execute` y delegar en Storage.
6. **Tests de no-regresión**: añadir test que verifica por introspección (`inspect.getsource`) que `ContextController` ya no contiene `_conn.execute` ni `cursor.execute`.
7. **Verificar `scripts/ci.sh` verde**.
8. **Eliminar los 20 shims** en `src/skillgraph/`.
9. **Reescribir los ~118 imports** en los 36 ficheros de tests + los 2 strings/imports dinámicos.
10. **Verificar `scripts/ci.sh` verde otra vez**.
11. **Actualizar `STATE.yaml`**: tests 604 + ~16 nuevos = ~620; coverage_snapshot_2026-09-24; release.tag = v0.7.0; nota_cobertura con cifras actualizadas (context_controller 95-97%, sin shims listados).
12. **Actualizar `CURRENT.md`** con UPDATE 2026-09-24 (shims + refactor).
13. **Actualizar `SESSION-JOURNAL.md`** con entrada cronológica.
14. **Actualizar `CHANGELOG.md`** con bloque v0.7.0.
15. **Emitir tag v0.7.0** anotado.
16. **Commit atómico final** `chore(release): v0.7.0`.
17. **Reportar cierre** al operador.

## Rollback plan

Si cualquier paso falla de manera no recuperable:

- `git revert <commit_sha>` para cada commit del refactor (devuelve el estado anterior).
- `git tag -d v0.7.0` para borrar el tag si se emitió antes del fallo.

La refactorización es **mecánica y 1:1**: cada método nuevo en Storage tiene el mismo comportamiento que el `_conn.execute` original; cada import reescrito va al bounded context correcto. Riesgo bajo. Reversibilidad alta.

## Referencias

- `external/blueprint-v1/adr/ADR-0013-divergencia-h7-y-rectificacion-v060.md`: precedente de ADR para decisiones arquitectónicas con efecto sobre roadmap.
- `specs/h9-bslice3-runcontroller-storage.md` (en `docs/architecture/`): patrón aplicado en H9-BSlice3 para migrar RunController a Storage API pública. Este ADR replica el patrón para ContextController.
- `STATE.yaml#release.tag`: actualmente v0.6.0; pasa a v0.7.0 tras este refactor.
- `SESSION-JOURNAL.md` entrada 2026-09-24 07:43: refresh de checkpoint; este ADR es el siguiente paso material.
