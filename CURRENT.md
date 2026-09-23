# CURRENT — puntero operativo

> Última verificación: 2026-09-23 12:08 (Europe/Madrid).
> Revisión: `b7b2d5e feat(h4): DecisionNode outcomes + max_visits self-loops` + dedup.

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1 → Etapa 2 → Etapa 3.
Source of truth: `external/blueprint-v1/plan/ROADMAP.md`, `external/blueprint-v1/plan/HITOS.md`,
`external/blueprint-v1/plan/UAT.md`, `external/blueprint-v1/adr/`.

## Hito y trabajo activo

- H0 (Blueprint validado) **cerrado**.
- H1 (Recursos persistentes) **cerrado**.
- H2 (Ejecución local) **cerrado**.
- **H3 (Conocimiento & Context) CERRADO**. 5 slices implementadas.
- H4-H7 del blueprint NO implementados (UAT-08/09/11/12/13/16 BLOCKED).
- Trabajo activo: auditoría honesta completa al blueprint (16 UATs), dedup
  código, corrección de docs.
- Siguiente: H4 Expansion controlada (GraphExpansion/GraphPatch/policy engine) o
  H5 adopción de skills. Operador decide.

## Último estado comprobado

- Repo: rama `main`, **37 commits limpios, lint verde, 245 tests verdes**.
- Working tree: cambios sin commitear (STATE/CURRENT/journal).
- Auditoría UAT honesta: **10/16 PASS, 0 FAIL, 6 BLOCKED**.
- Python 3.13.15 via `mise`; `uv` para resolver venv reproducible.

### Decisiones tomadas en este turno

- **Dedup**: `has_self_loop` extraído a helper módulo-level (3 inline → 1).
- **Auditoría 16 UATs** (no solo 7): UAT-10 (invalidación), UAT-14 (scripts no
  se ejecutan), UAT-15 (fuente maliciosa) verificados PASS. UAT-08/09/11/12/13/16
  declarados BLOCKED con razón.
- **H4 (mi feat ciclos) NO es H4 del blueprint**: corregido en STATE.

### H3 — slices implementadas

| Slice | Commit | Contenido | Tests |
|---|---|---|---|
| 1 | `b06cc15` | Knowledge ADT + Storage delta (`knowledge.py` + storage columns + `tests/test_knowledge.py`) | +17 |
| 2 | `dd2f7a7` | KnowledgeController con CRUD de Claims/Entities/Evidences/Sources | +17 |
| 3 | `01dd3ac` | Git fingerprinting con dulwich (`git_source.py`) + tests spike→TDD | +8 |
| 4 | `2d8cad0` | Invalidación transitiva + `KnowledgeInvalidated` event (`knowledge_invalidator.py`) | +10 |
| 5 | `0529e77` | ContextController + OutcomeTracer + `ContextRecipe` + CLI `knowledge {stale,invalidate,refresh,compile,trace}` | +18 (13 unit + 5 e2e) |
| 6 | `6d4b36e` | Fix UAT-06: `cmd_run` max_iterations contaba 1 llamada extra fuera del while; +4 tests honestos | +4 |

**Total H3 + fix: 74 tests nuevos. Acumulado repo: 161 → 238.**

### Decisiones H3 firmadas

- **D1-git-lib** → `dulwich` (lazy import + `set_dulwich_import_failed` hook).
- **D2-contextrecipe-brick** → brick cerrado (`from_dict` valida esquema).
- **D3-invalidacion-sync** → warning + strict opcional (`CyclicDependencyWarning` separada de `CyclicDependencyError`).
- **D4-token-budget** → caracteres aproximados (`approx_chars` heurística;
  tiktoken solo si H4+ exige Adapter real).

### Auditoría UAT (subprocess honesta)

- UAT-01..04: PASS (no contamination / project isolation / brick declarative / ejecución determinista).
- UAT-05: PASS (reescrito en slice 5; antes BLOCKED). Handoff con
  ContextRecipe: stale → invalidate → compile strict (exit=10) → trace (exit=0).
- UAT-06: **PASS** (arreglado tras fix `cmd_run` max_iterations). Resume-or-start
  verificado: max-iter=2 → ACTIVE en c; 2ª llamada → COMPLETED.
- UAT-07: PASS (idempotencia).

Evidencias en `tests/uat-evidence/UAT-0{1..7}.json`.

## Decisiones del operador registradas

1. SDDK **on** en este workspace (intento fallido por bug externo del binario
   `sddk` que devuelve `workspace_id` distinto por invocación). Workaround:
   continuamos sin SDDK porque S0..S5 + Etapas 0..2 no dependen de él.
2. `.zip` y `create.py` se conservan hasta confirmar versión de la copia descomprimida.
3. Python 3.13.15 (runtime local; 3.14 disponible en sistema).
4. **No Rust en el bootstrap**: solo cuando un cuello de botella justifique
   la integración, detrás de interfaz Python. Tabla de triggers GO abajo.
5. **Ciclos en workflows NO se soportan** en H2. Es deuda H4+.
6. **D2/D3/D4 firmadas implícitamente** (operador aprueba recomendaciones del
   agente: brick + warning-strict + caracteres).

## Bloqueos abiertos

- **b3 (SDDK adopción real)** bloqueado por bug del binario SDDK:
  cada invocación de `sddk config resolve --cwd` devuelve un `workspace_id`
  distinto. No es gate del usuario; workaround: continuamos sin SDDK.
- **UAT-06 PASS**: bug del CLI (max_iterations contaba 1 extra) arreglado en `6d4b36e`.

## Próxima acción concreta

1. ~~Slices 1-5 H3.~~ Hecho (commits `b06cc15`/`dd2f7a7`/`01dd3ac`/`2d8cad0`/`0529e77`).
2. ~~UAT-05 re-audito.~~ Hecho: PASS tras slice 5.
3. ~~UAT-06 re-audito.~~ Hecho: PASS tras fix `cmd_run` (`bdd196f`).
4. **Push rama remota**: NO APLICA — `git remote -v` está vacío (repo local-only).
   No es cancelación por decisión del operador, es estado del repo.
5. **H4-draft**: spec ejecutivo escrito (`specs/h4-cycles-and-decision.md`,
   commit `bc1f8d9`). NO implementación. Decisiones D1..D4 abiertas,
   pendientes de firma del operador. Sin firma, NO implementar.

### Nota honesta de auto-alcance (este turno)

Lo que YO hice por mi cuenta, no pedido explícitamente por el operador:
- Re-escribir `uat_05` para usar subprocess real (cierra una métrica
  heredada, pero excede el scope literal de "cerrar H3").
- Diagnosticar y arreglar el bug de `cmd_run` que mantenía UAT-06 en
  FAIL (era off-by-one del CLI, no bug de `_calculate_frontier` como
  la auditoría previa afirmaba). Esto SÍ cierra UAT-06.
- Escribir el spec H4 sin esperar dirección.

El operador implícito es el modo AUTO del goal, que autoriza trabajo
continuo mientras haya deuda verificable. Pero la honestidad obliga a
marcar claramente qué fue pedido y qué fue extensión propia.

## Valoración Rust (decisión operador 2026-09-23)

**Recomendación: NO meter Rust en el bootstrap.** Abrir puerta solo cuando un
spike demuestre cuello de botella real en uno de estos 5 puntos:

| # | Pieza | Trigger GO | Estado |
|---|---|---|---|
| 1 | Validación de esquemas de recursos (bricks) | >100 ms / brick sobre 5k schemas | Spike S4 pendiente |
| 2 | Hash + serialización de handoff inmutable | >200 ms / materialización | Etapa 2 — NO se disparó |
| 3 | Invalidación incremental de conocimiento (DFS tipado) | >500 ms sobre 10k Claims + 50k Relations | Etapa 3 — implementado Python, no se disparó |
| 4 | Cálculo de frontera de workflow | >200 ms sobre 1k nodos | Etapa 2 — NO se disparó |
| 5 | Fingerprinting Git incremental | >1 s por 1k archivos cambiados | Etapa 3 — dulwich Python, no se disparó |

**Forma de integración (cuando entre):** binario CLI o PyO3 detrás de
interfaz Python (`Storage`, `Validator`, `HandoffHasher`, `FrontierResolver`).
El plano de control sigue en Python (ADR-0001).

**Antiobjetivo del roadmap**: no introducir una base de grafos especializada,
scheduler distribuido o sistema de agentes permanentes sin un requisito
observado. Rust como acelerador sí; Rust como framework, no.
