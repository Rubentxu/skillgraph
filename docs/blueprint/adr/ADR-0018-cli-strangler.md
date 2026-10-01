# ADR-0018 — Descomposición del CLI por estrangulamiento en componentes de comando

Estado: aceptado (sesión 2026-10-01, ciclo `wi-52-cli-strangler-cut1-expansion`).

## Contexto

`src/skillgraph/cli/runner.py` es, tras la descomposición de Storage
(ADR-0016), el mayor god-module del repo: **2357 LoC, 70 funciones
top-level** (medido por AST al abrir el ciclo). El audit de deuda
(`audits/architecture-debt-2026-10-01.md`) lo mantiene como entrada P1
de "god modules", categoría que por convención del repo exige ADR.

El módulo ya recibió dos refactorías previas que NO cambiaron su
naturaleza monolítica: WI-41 (tabla de dispatch única en vez del
if-chain de `main`) y WI-43 (extracción del parser a `cli/parser.py`).
Quedan dentro: 11 clusters `cmd_<dominio>` (976 LoC) y ~1380 LoC de
helpers compartidos (`resolve_project`, `ProjectResolver`, I/O de
plan, `EXIT_*`, builders de adapter...).

Mapa medido por cluster (AST, 2026-10-01):

| Cluster | funcs | LoC |
|---|---:|---:|
| expansion | 7 | 256 |
| runs | 5 | 166 |
| promotion | 3 | 129 |
| pack | 2 | 116 |
| knowledge | 5 | 101 |
| project | 3 | 70 |
| backup | 4 | 38 |
| brick / run / policy / init | 5 | 100 |
| (no-cmd: helpers compartidos) | ~35 | ~1380 |

## Decision

Estrangulamiento por cluster (O1), el mismo patrón de ADR-0016
trasladado al CLI:

1. **Componentes reales**: cada cluster `cmd_<dominio>` sale a
   `src/skillgraph/cli/commands/<dominio>.py` con sus helpers privados
   (los de uso exclusivo del cluster, verificado por grep de
   call-sites antes de mover).
2. **`cli/support.py`**: los helpers genuinamente compartidos
   (`EXIT_*`, `ProjectResolver`, `resolve_project`,
   `_open_project_or_error`, I/O de plan) viven allí. `runner` los
   re-importa; los componentes de comando importan desde `support`,
   **nunca desde `runner`** (prohibido el ciclo runner↔commands; lo
   fija el test de identidad del corte).
3. **Cero ediciones en callers**: `runner` conserva alias de import
   para todo lo que su `__all__` exporta y para los nombres que la
   tabla de dispatch (WI-41) referenciaba. La tabla, el parser (WI-43)
   y los tests H4/UAT no se editan.
4. **Red de identidad por corte**: antes de dar por bueno cada corte,
   un test afirma `runner.cmd_X is commands.<dominio>.cmd_X` (y que
   `runner` NO redefina helpers movidos). Es la misma red de contrato
   por identidad que usaron los cortes de ADR-0016.
5. **Cortes en orden de valor/riesgo**: expansion (el mayor, 256 LoC,
   con red de tests H4 propia) → runs → promotion → pack → knowledge
   → el resto. Cada corte es un commit atómico con la suite completa
   verde (hook pre-commit).

### Alternativas rechazadas

- **Mover helpers sin crear componentes** (todo a un `cli/support.py`
  gigante): reduce LoC de runner pero no crea módulos con una razón
  para cambiar; es barajar, no estrangular.
- **Dividir por capas técnica** (un módulo de "utils", otro de
  "formateo"): rompe la cohesión por dominio que la tabla de dispatch
  ya delimita.
- **Repetir WI-43** (otro parser): el parser ya es un módulo propio;
  el peso restante son handlers y helpers, no argv.

## Consecuencias

- `runner.py` baja de 2357 LoC en cada corte; el objetivo declarado de
  H-02 es dejarlo por debajo del umbral de god-module (>800 LoC) con
  `main` + dispatch + helpers de orquestación del ciclo `run`.
- La superficie pública del CLI (`runner.__all__`: `EXIT_*`,
  `ProjectResolver`, `cmd_*`) NO cambia: los consumidores que importan
  desde `runner` siguen funcionando (verificado por la red de
  identidad y la suite).
- Cada corte añade un módulo `cli/commands/<dominio>.py` cuya única
  razón de cambiar es su dominio; `support.py` acumula solo lo
  compartido por ≥2 clusters (los de uso exclusivo se van con su
  cluster).
- Corte 1 (este ADR + ejecución): `expansion` — 7 handlers + 5 helpers
  privados + 2 de apoyo (`_utcnow_iso`, `_load_registry`) salen a
  `cli/commands/expansion.py`; `support.py` estrena EXIT_*/resolver/
  plan-I/O. runner: 2357 → ~1756 LoC.

## Referencias

- ADR-0016: patrón de estrangulamiento con redes de identidad y cero
  ediciones en callers, del que este ADR es el traslado al CLI.
- WI-41 (dispatch table), WI-43 (`cli/parser.py`), WI-44
  (`resolve_project`): las costuras que este ADR aprovecha.
- `audits/architecture-debt-2026-10-01.md`: estado de deuda que motiva
  H-02.
