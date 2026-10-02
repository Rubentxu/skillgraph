# Auditoria de deuda arquitectonica (2026-10-02)

Generada por `audits/audit_debt.py` (WI-28). Reproducible:
`python audits/audit_debt.py` desde la raiz del repo.

## Resumen ejecutivo

- **78** modulos Python, **20779** LoC, **769** funciones.
- **0** archivos >800 LoC (god modules).
- **0** funciones publicas con cc>=20 (refactor obligatorio).
- **0** funciones privadas con cc>=20 (refactor opcional).
- **4** funciones >80 LoC (legibilidad mejorable).
- **0** funciones con anidamiento >=5 niveles.

## Archivos grandes (>800 LoC)

H-01 Storage god-class y H-02 CLI god-module son las entradas mas impactantes.

| LoC | Path |
|----:|------|

## Hotspots publicos (cc>=20, refactor obligatorio)

| cc | LoC | Funcion | Path |
|---:|----:|---------|------|

## Funciones largas (>80 LoC)

Top 20 funciones por LoC. Muchas son orquestadores coordinando handlers; en si no
son problematicas si tienen baja cc y helpers atomicos con test coverage.

| LoC | Funcion | Path |
|----:|---------|------|
| 409 | `build_parser` | `src/skillgraph/cli/parser.py` |
| 90 | `compile_handoff` | `src/skillgraph/knowledge/context_controller.py` |
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

- Ninguno.

**P2 - Hotspots privados cc>=20** (opcional, valor pedagogico):

- Ninguno.

**P3 - Funciones largas >80 LoC**: 4 en total.
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

