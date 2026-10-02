# ADR-0022 — Descomposición del facade `Storage`: mixin de delegaciones, schema y mappers

Estado: aceptado (sesión 2026-10-02, ciclo
`p-b7740b96d79ec013/wi65-storage-facade-decomposition`; fase 1 y fase 2
ejecutadas, umbral del audit cruzado).

## Contexto

`src/skillgraph/platform/storage.py` era el god module H-01 del repo:
**1807 LoC** y una única clase `Storage` con **80 métodos**, de los que
**65 no hacían nada más que reenviar** a los cinco componentes que WI-56
ya había extraído (ADR-0016). Solo 7 métodos tenían SQL vivo.

La medición por AST (reproducible, `audits/audit_debt.py` más el
clasificador de `evidence/wi65-storage-facade-exploration.md`) dio:

| Grupo | Métodos | LoC |
|---|---:|---:|
| Delegación fina | 65 | 759 |
| Métodos con SQL vivo | 7 | 189 |
| Otros (propiedades, lifecycle) | 8 | 112 |
| Módulo (imports, DDL, mappers, dataclasses) | — | ~747 |

Las 65 delegaciones se agrupaban de forma **disyunta** por componente:
knowledge (31), runs (19), promotions (7), events (4) y policy (4). Cada
grupo llama a un único accessor, así que la extracción es mecánica.

## Decisión

Dos fases, mismo patrón estrangulador de ADR-0016/0018/0020, con umbral
**<800 LoC por fichero**:

- **Fase 1**: las 65 delegación salen a cinco mixin en
  `storage_delegations.py`, uno por componente. Cuerpos movidos
  **verbatim** por AST: sin lógica, ramas ni rutas de error nuevas.
- **Fase 2**: los **12 mappers fila→DTO** y `_uid` salen a
  `row_mappers.py`, y el **DDL** (`_SCHEMA_SQL`, 248 LoC) más
  `SCHEMA_VERSION` salen a `schema.py`.

`storage.py` queda en **623 LoC** (1807 → 1024 → 623).

### Por qué mixin y no `__getattr__`

`__getattr__` dinámico rompería el tipado estático que AGENTS.md §4.1
exige explícito. El mixin conserva las anotaciones reales de cada
método, mantiene `Storage` como la misma clase con los mismos 72
métodos públicos, y obliga a **cero ediciones en callers**. `__all__`
declara los nombres re-exportados para que ruff no los borre por F401.

### Por qué los mappers y el DDL sí pueden moverse

Los mappers son funciones **puras**: reciben una fila, devuelven un DTO,
sin `self`, sin conexión, sin reloj. Es el mismo criterio y el mismo
motivo de cambio que hizo `knowledge_mappers.py` en WI-60
(ADR-0020). El DDL es una **constante**: no comparte razón de cambio
con los métodos del facade.

### Qué NO se mueve, y por qué

ADR-0016 exige que los atómicos H9/H10 compartan `self._conn` con el
resto **sin duplicarlo**, y que `SqliteEventStore` reutilice
`_insert_event_in_tx`. Por tanto `_tx`, `_atomic`, `_migrate`,
`_insert_event_in_tx` y `_atomic_state_and_event` **se quedan en
`Storage`**. La red `test_wi65_storage_schema_mappers.py` falla si
alguno de ellos se extrae, y comprueba además que `_atomic` siga
operando sobre `self._conn`.

## Consecuencias

- `Storage` deja de ser una god class: 623 LoC, 15 métodos, todos con
  SQL vivo o lifecycle. Su responsabilidad es la que el nombre dice.
- **El shim de compatibilidad es obligatorio.** Tres módulos importan
  desde `skillgraph.platform.storage` por el corte 5 de ADR-0016:
  `event_store` (`_SCHEMA_SQL`, `_row_to_stored_event`),
  `policy_store` (`_row_to_stored_budget`) y `knowledge_repository`
  (`_uid`). Sin re-export, revientan.
- Sin cambio de schema, sin cambio de comportamiento observable y sin
  cambio de API pública.

### Regresiones reales presas durante la ejecución

Ambas las detectó la red antes de llegar a `main`, y ambas son
reutilizables como advertencia para cualquier corte futuro:

1. **`ruff --fix` borró los re-exports por F401.** Al mover los
   métodos, `Storage` dejó de referenciar internamente `StoredClaim`,
   `StoredEvidence`, `StoredRelation` y `StoredResource`, y el autofix
   los eliminó. Siete módulos los importan desde `storage`: el borrado
   reventó **61 tests de golpe** sin tocar el facade. Se restauran y se
   declaran en `__all__`.
2. **Un test de conformidad de Protocol quedó obsoleto.**
   `_public_methods` de `test_persistence_ports.py` filtraba por
   `__qualname__.startswith("Storage")`, que solo mira el cuerpo de la
   clase. Con herencia, los métodos tienen qualname del mixin, así que
   declaraba roto un `Storage` que **sí** cumple el Protocol. Se
   corrigió el helper para preguntar por el conjunto accesible, que es
   lo que el test afirma.

## Alternativas rechazadas

- **Extraer la clase entera sin ADR**: los atómicos H9/H10 comparten
  `self._conn`; partirlos sin decisión explícita rompería H9/H10.
- **`__getattr__` dinámico**: rompe el tipado estático (§4.1) y oculta
  la superficie real de la clase a cualquier lector.
- **Mover también `_tx`/`_atomic`**: contradice ADR-0016 y el motivo por
  el que `SqliteEventStore` es el último cluster extraído.
- **Subir el umbral del audit a 1000 LoC** en vez de extraer: escondería
  la métrica en vez de resolver el problema.

## Red de contrato

- `tests/test_wi65_storage_facade_delegations.py` (fase 1, 34 tests):
  herencia real, identidad de función, mixins disjuntos, superficie
  pública preservada y guarda de re-exports.
- `tests/test_wi65_storage_schema_mappers.py` (fase 2, 25 tests): los
  12 mappers son puros y viven fuera, el DDL se importa en vez de
  redefinirse, los atómicos se quedan, el shim sigue resolviendo y
  `storage.py` queda bajo 800 LoC.
