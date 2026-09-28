# ADR-0016 — Descomposición de Storage por estrangulamiento de fachadas reales

Estado: aceptado (sesión 2026-09-28, ciclo wi-56-storage-decomposition, path A-lite).

## Contexto

`src/skillgraph/platform/storage.py` es el mayor god-module del repo:
2837 LoC, una sola clase `Storage` de 2260 LoC y 79 métodos públicos que
concentra 6 clusters de responsabilidad (runs, claims, resources,
policy, events, infraestructura de conexión/migración). El audit de
deuda vigente (`audits/architecture-debt-2026-09-28.md`, regenerado en
`1a23848`) lo marca como la entrada más impactante de la categoría P1,
que según las convenciones del repo exige ADR previa.

La exploración del ciclo midió lo siguiente (reporte
`art-38e6b24c2208-1a64280d`, reproducible por AST):

1. Las fachadas existentes NO son componentes. `Storage.run_repository()`,
   `.knowledge_repository()`, `.event_store()` y `.policy_store()`
   (storage.py:569..604) devuelven `self` con docstring explícito
   ("Equivalente a `self` mientras `Storage` mantenga todas las
   firmas"). Son vistas de tipado del WI-31/WI-02b sobre los Protocols
   `RunRepository`, `KnowledgeRepository`, `EventStore` y `PolicyStore`
   de `platform/ports/`. La descomposición real nunca se ejecutó.
2. Existen 634 call-sites que invocan métodos de Storage directamente
   fuera de storage.py (resources 221, runs 203, claims 99, policy 83,
   events 28), repartidos en 35/26/26/13/8 ficheros entre src/ y tests/.
3. Los atomicos H9/H10 (`transition_run_state_atomically`,
   `start/complete_node_execution_atomically`, `_atomic_state_and_event`)
   comparten `self._conn` y la suite runtime usa `storage._conn` en
   fixtures (test_runcontroller.py).

## Decision

Estrangulamiento (O1): extraer cada cluster a un componente SQLite real
(`SqliteRunRepository`, `SqlitePolicyStore`, `SqliteKnowledgeRepository`,
`SqliteEventStore`) en módulos nuevos bajo `src/skillgraph/platform/`,
que implementan los Protocols ya declarados en `platform/ports/`. Los
métodos homónimos de `Storage` se conservan como delegados hacia la
instancia del componente, de modo que los 634 call-sites NO se editan.

Propiedades obligatorias de la decisión:

- **Instancia única**: el accessor (`storage.run_repository()`, etc.)
  devuelve siempre la misma instancia (cacheada en el Storage).
- **Conexión compartida**: todos los componentes operan sobre la MISMA
  `sqlite3.Connection` de Storage. Prohibido abrir conexiones nuevas por
  componente; los atomicos H9/H10 conservan su semántica transaccional.
- **Schema intocado**: ningún corte altera tablas, índices ni triggers;
  la migración idempotente existente sigue siendo la única fuente.
- **Errores tipados intactos**: mismos subtipos de `SkillGraphError` y
  mismos códigos `sg_*` en los componentes.
- **SQL concentrado**: al cerrar los 4 cortes, `Storage` no contiene SQL
  directo (todo vive en los componentes) y storage.py queda bajo 700 LoC
  (verificación por `audits/audit_debt.py` en la pipeline canónica).

Orden de cortes (cada uno un vertical slice commiteado por separado, con
red de equivalencia previa y verificación por mutación cuando aplique):

1. `SqliteRunRepository` (cluster runs, 19 métodos, 203 call-sites):
   mayor acoplamiento con runtime, se ataca primero.
2. `SqlitePolicyStore` (11 métodos, 83 call-sites): el más aislado.
3. `SqliteKnowledgeRepository` (claims 17 + resources 14 métodos,
   320 call-sites): el más grande; se parte en 3a (claims) y 3b
   (resources) si el corte excede el tamaño sano de un slice.
4. `SqliteEventStore` (4 métodos, 28 call-sites): último porque los
   atomicos H9/H10 insertan eventos en la misma transacción; el corte
   exige compartir `_insert_event_in_tx` sin duplicarlo.

## Alternativas consideradas y rechazadas

- **O2 — Migración de receptores**: reescribir los 634 call-sites a
  `storage.run_repository().metodo(...)`. Rechazada: big-bang encubierto
  con riesgo alto y cero valor de comportamiento; queda registrada como
  opción futura SOLO si un ciclo posterior necesita romper la superficie
  `Storage` pública por otra razón.
- **O3 — Partición cosmica de módulos**: mover métodos a varios ficheros
  manteniendo la clase agregada. Rechazada: reduce LoC por fichero sin
  reducir el acoplamiento; O1 la supera y deja camino a O2 si algún día
  hace falta.

## Riesgos y mitigaciones

- R1 (superficie de 634 call-sites): mitigado por diseño — los delegados
  de `Storage` conservan firma y semántica; I1 de la spec prohíbe editar
  llamadores no declarados.
- R2 (transacciones H9/H10): mitigado por conexión compartida + los
  atomicos viven en el componente de runs desde el corte 1; los tests
  con `storage._conn` siguen operando sobre la misma conexión (I5).
- R3 (`platform/ports/__init__.py`, 927 LoC): conocida. Partir los
  Protocols queda como deuda para un ciclo posterior; este ADR NO lo
  autoriza.
- R4 (imports con efectos, UAT-14): los módulos nuevos solo importan
  stdlib + tipos del paquete; sin ejecución al importar.

## Consecuencias

- storage.py deja de ser god-module (objetivo < 700 LoC medidos).
- El Protocol `RunRepository` deja de satisfacerse "por superficie" y
  pasa a satisfacerse por composición: el consumidor que declare
  `RunRepository` recibe una clase con una sola responsabilidad.
- Los futuros features de runs/policy/knowledge/eventos tocan un
  componente, no el agregado.
- No hay cambio de comportamiento observable desde CLI ni de schema;
  SemVer esperado del ciclo: refactors + tests (sin release obligatoria,
  decisión al cierre con el historial verificado).

## Persistencia

- Spec del ciclo: `.pipelinek/cycle-artifacts/wi56-specification.md`
  (artefacto `specification`, sha256 f6c7b49b141130a2...).
- Reporte de exploración: `art-38e6b24c2208-1a64280d`.
- La verificación de cada corte vive en su commit (red de equivalencia +
  suite afectada + CI pipelinek con journal fresco).

## Revisit trigger

- Si un corte descubre que algún método del cluster es usado por otro
  cluster a través de SQL compartido (no por conexión), se detiene el
  slice, se documenta aquí como corrección y se replantea el orden.
- Si `platform/ports/__init__.py` se parte en un ciclo futuro, revisar
  la ubicación de los componentes para que protocolo e implementación
  queden en módulos espejo.
