# ADR-0020 — Estrangulamiento de SqliteKnowledgeRepository: mappers primero, clusters después

Estado: aceptado (sesión 2026-10-02, ciclo `wi-60-knowledge-repo-mappers`; fase 1 ejecutada, fase 2 planificada).

## Contexto

`src/skillgraph/platform/knowledge_repository.py` es el tercer god
module vigente: **986 LoC**, con la clase `SqliteKnowledgeRepository`
concentrando **811 LoC** (claims, evidencias, relaciones, recursos,
reportes de cobertura) y **7 mappers puros** de fila-SQLite a DTO
(`row_to_source`, `row_to_evidence`, `row_to_stored_claim`,
`row_to_stored_evidence`, `row_to_claim`, `row_to_resource`,
`row_to_relation`; ~117 LoC) a nivel de módulo.

Consumidores de los mappers: los métodos de la propia clase y los
**shims de compatibilidad de `storage.py`** (corte 5 de ADR-0016:
`_row_to_source` hace import diferido
`from skillgraph.platform.knowledge_repository import row_to_source`),
por lo que cualquier reubicación debe conservar los nombres en
`knowledge_repository` (re-export).

## Decision

Mismo patrón por fases de ADR-0018/0019, con umbral <800 LoC:

- **Fase 1 (esta)**: los 7 mappers puros salen a
  `src/skillgraph/platform/knowledge_mappers.py` (módulo real con una
  sola razón de cambio: el contrato fila→DTO). `knowledge_repository`
  los re-importa; los shims de `storage.py` y los métodos de la clase
  no se editan.
- **Fase 2**: dividir la clase por clusters (claims / evidencias+relaciones /
  recursos+reportes) en componentes que compartan la conexión, según
  el patrón ADR-0016; `SqliteKnowledgeRepository` queda como fachada
  que delega.
- **Umbral**: la fase 1 deja el fichero en ~870 LoC (aún >800); cruzar
  el umbral requiere la fase 2, que se planificará con mapa propio.

### Alternativas rechazadas

- **Extraer la clase entera sin ADR**: el split por clusters necesita
  decidir fronteras (claims vs evidencias vs recursos) con mapa de
  call-sites; hacerlo sin ADR repite el patrón "barajar sin decidir".
- **Mover los mappers dentro de la clase como métodos estáticos**:
  empeora la testabilidad (los mappers son funciones puras y así
  permanecen).

## Consecuencias

- Fase 1: `knowledge_mappers.py` nuevo (módulo puro, sin SQL);
  `knowledge_repository.py` 986 → ~870 LoC con re-imports; shims de
  `storage.py` intactos.
- La red de identidad fijará `knowledge_repository.row_to_X is
  knowledge_mappers.row_to_X` para los 7.
- Fase 2 requerirá ADR-propia si las fronteras de cluster difieren de
  lo esbozado aquí.

## Referencias

- ADR-0016 (patrón de repositorios con conexión compartida y shims de
  compatibilidad).
- ADR-0018/0019 (redes de identidad por corte).
- `audits/architecture-debt-2026-10-02.md`: ranking vigente.
