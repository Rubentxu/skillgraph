# Auditoria de deuda arquitectonica (2026-10-01)

Generada por `audits/audit_debt.py` (WI-28). Reproducible:
`python audits/audit_debt.py` desde la raiz del repo.

## Resumen ejecutivo

- **57** modulos Python, **19610** LoC, **744** funciones.
- **6** archivos >800 LoC (god modules).
- **0** funciones publicas con cc>=20 (refactor obligatorio).
- **0** funciones privadas con cc>=20 (refactor opcional).
- **10** funciones >80 LoC (legibilidad mejorable).
- **0** funciones con anidamiento >=5 niveles.

## Archivos grandes (>800 LoC)

H-01 Storage god-class y H-02 CLI god-module son las entradas mas impactantes.

| LoC | Path |
|----:|------|
| 1807 | `src/skillgraph/platform/storage.py` |
| 1525 | `src/skillgraph/cli/runner.py` |
| 1445 | `src/skillgraph/runtime/runcontroller.py` |
| 986 | `src/skillgraph/platform/knowledge_repository.py` |
| 927 | `src/skillgraph/platform/ports/__init__.py` |
| 862 | `src/skillgraph/governance/graph_expansion.py` |

## Hotspots publicos (cc>=20, refactor obligatorio)

| cc | LoC | Funcion | Path |
|---:|----:|---------|------|

## Funciones largas (>80 LoC)

Top 20 funciones por LoC. Muchas son orquestadores coordinando handlers; en si no
son problematicas si tienen baja cc y helpers atomicos con test coverage.

| LoC | Funcion | Path |
|----:|---------|------|
| 409 | `build_parser` | `src/skillgraph/cli/parser.py` |
| 143 | `_execute_one` | `src/skillgraph/runtime/runcontroller.py` |
| 116 | `extract_file_signatures` | `src/skillgraph/knowledge/file_signature.py` |
| 101 | `analyze_skill` | `src/skillgraph/domain/skill_importer.py` |
| 92 | `cmd_expansion_apply` | `src/skillgraph/cli/commands/expansion.py` |
| 90 | `compile_handoff` | `src/skillgraph/knowledge/context_controller.py` |
| 89 | `_resolve_run_inputs` | `src/skillgraph/cli/runner.py` |
| 86 | `aggregate_file_signatures` | `src/skillgraph/knowledge/knowledge_controller.py` |
| 85 | `compile_handoff_from_scopes` | `src/skillgraph/knowledge/file_handoff.py` |
| 84 | `promote_candidate` | `src/skillgraph/governance/improvement.py` |

## Anidamiento profundo (>=5 niveles)

- Ninguna funcion con anidamiento >=5. ✓

## Recomendaciones (derivadas de la medicion)

Esta seccion se genera desde las metricas de este mismo informe. No
hay cifras escritas a mano: si una funcion baja de cc=20, desaparece de
P0 sin que nadie tenga que acordarse de borrarla.

**P0 - Hotspots publicos cc>=20** (refactor obligatorio):

- Ninguno. Ninguna funcion publica de `src/` alcanza cc=20 (maximo medido: 10).

**P1 - God modules** (>800 LoC, deuda estructural):

- `src/skillgraph/platform/storage.py` (1807 LoC): requiere ADR previo, porque tocarlo afecta a contratos publicos y frontera de dominio.
- `src/skillgraph/cli/runner.py` (1525 LoC): requiere ADR previo, porque tocarlo afecta a contratos publicos y frontera de dominio.
- `src/skillgraph/runtime/runcontroller.py` (1445 LoC): requiere ADR previo, porque tocarlo afecta a contratos publicos y frontera de dominio.
- `src/skillgraph/platform/knowledge_repository.py` (986 LoC): requiere ADR previo, porque tocarlo afecta a contratos publicos y frontera de dominio.
- `src/skillgraph/platform/ports/__init__.py` (927 LoC): requiere ADR previo, porque tocarlo afecta a contratos publicos y frontera de dominio.
- `src/skillgraph/governance/graph_expansion.py` (862 LoC): requiere ADR previo, porque tocarlo afecta a contratos publicos y frontera de dominio.

**P2 - Hotspots privados cc>=20** (opcional, valor pedagogico):

- Ninguno.

**P3 - Funciones largas >80 LoC**: 10 en total.
En su mayoria son orquestadores con baja cc y helpers atomicos con
cobertura; ver la tabla de arriba. Prioridad baja.

**P4 - Anidamiento >=5 niveles** (decision tree en vez de composicion):

- Ninguno.

### Politica recomendada

- Los WIs de complejidad siguen el patron helper-extraction ya
  establecido (D-52..D-60): extraer helpers atomicos y medibles.
- Los WIs P1 (god modules) requieren un ADR previo porque tocan
  contratos publicos y frontera de dominio.
- Cualquier release mantiene cero hotspots publicos cc>=20, o
  documenta la excepcion de forma explicita.


<!-- ANNALS:append-only -->

