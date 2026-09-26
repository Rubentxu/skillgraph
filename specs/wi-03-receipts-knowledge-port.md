# WI-03 — Governance: receipts migra de `storage._conn` a KnowledgeRepository (AC-5 follow-up)

## Motivación

El refactor WI-02b (v0.14.3) cerró los escape hatches `_conn.execute` en
KnowledgeController, KnowledgeInvalidator y ContextController (AC-5 PASS).
Pero quedó **un sitio residual** descubierto durante un audit transversal
post-WI-02b:

- `src/skillgraph/governance/receipts.py:366` (función `list_applicable_receipts`)
  accede directamente a `storage._conn.execute("SELECT source_id FROM sources ...")`
  en lugar de delegar en un API público de Storage.

Esto **viola la regla arquitectónica "Storage encapsula SQL"** (AGENTS.md
§8, ADR-0014) que WI-02b promovió. La deuda es menor (1 sitio, 1 SELECT)
pero material: cualquiera que lea `receipts.py` verá una excepción a la
regla y la propagará.

Este WI la cierra por completo.

## Decisión material (D-15)

`list_sources()` se añade al `KnowledgeRepository` Protocol (duck typing)
y se implementa en `Storage`. La firma es:

```python
def list_sources(
    self, *, tenant_id: str, project_id: str
) -> tuple[Source, ...]:
    """Sources del tenant/project (read-only)."""
```

(equivalente al patrón ya usado para `list_evidence_for_source`,
`list_evidences_for_source`, etc.).

`receipts.list_applicable_receipts` se migra a llamar `storage.list_sources(...)`.

## Scope

### In-scope
- Añadir `list_sources` a Protocol (`src/skillgraph/platform/ports/__init__.py`).
- Implementar `list_sources` en Storage (`src/skillgraph/platform/storage.py`).
- Migrar `list_applicable_receipts` en `src/skillgraph/governance/receipts.py`.
- Añadir 1-2 tests de caracterización para `Storage.list_sources`.
- Actualizar test existente de `receipts.py` si lo necesita (no debería).
- Documentar en CHANGELOG [0.14.4].
- Bump version 0.14.3 → 0.14.4 (PATCH — refactor puro sin API change).
- Tag anotado `v0.14.4`.

### Out-of-scope
- Migración de otros módulos (`catalog.py` usa su propio `_conn` para
  un SQLite distinto del Storage de proyecto; queda como P5 stewardship
  pendiente, separado).
- Cualquier cambio funcional a `list_applicable_receipts` (semántica idéntica).
- Push automático (autorización pendiente del operador, regla vigente).

## AC

- **AC-1**: `Storage.list_sources(tenant_id, project_id)` existe y devuelve
  la tupla esperada de `Source` (test unit verde).
- **AC-2**: `KnowledgeRepository` Protocol declara `list_sources` y Storage
  la implementa estructuralmente (test `test_persistence_ports.py` verde).
- **AC-3**: `receipts.list_applicable_receipts` ya **NO** accede a
  `storage._conn` (verificación: `grep "_conn" src/skillgraph/governance/receipts.py`
  → 0 resultados en código de producción; comentarios no cuentan).
- **AC-4**: `tests/test_h14_validation_receipts.py` sigue **PASS** sin
  cambios semánticos (misma cobertura, mismos resultados observables).
- **AC-5**: 927/927 tests PASS baseline preservado (+1..2 nuevos).
- **AC-6**: `ruff format + ruff check` limpios.
- **AC-7**: `pipelinek run` → SUCCESS.
- **AC-8**: `__version__ = "0.14.4"`, tag anotado `v0.14.4` creado.
- **AC-9**: CHANGELOG.md tiene entrada [0.14.4] antes de la de v0.14.3.

## Definition of Done

- Commits atómicos: 1 commit work + 1 commit bump + tag.
- Conventional Commits estricto.
- Sin regresiones (927 baseline → ≥927 PASS).
- SDDK close-out documentado.

## Trazabilidad

- Especificación D-15 (este WI).
- Spec WI-02b (D-08..D-13, AC-5): define regla "Storage encapsula SQL".
- ADR-0014 (in-memory/_conn encapsulation): precedente arquitectónico.
- WI-02b AC-5 verification: `grep "_conn" src/skillgraph/knowledge/`
  → exit 1. Este WI extiende esa garantía a `governance/`.
