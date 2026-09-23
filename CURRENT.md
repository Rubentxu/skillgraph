# CURRENT — puntero operativo

> Última verificación: 2026-09-23 12:32 (Europe/Madrid).
> Revisión: pendiente (H5 skill_import implementado; commit en curso).

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1 → Etapa 2 → Etapa 3.
Source of truth: `external/blueprint-v1/plan/ROADMAP.md`, `external/blueprint-v1/plan/HITOS.md`,
`external/blueprint-v1/plan/UAT.md`, `external/blueprint-v1/adr/`.

## Hito y trabajo activo

- H0 (Blueprint validado) **cerrado**.
- H1 (Recursos persistentes) **cerrado**.
- H2 (Ejecución local) **cerrado**.
- **H3 (Conocimiento & Context) CERRADO**. 5 slices implementadas.
- **H5 (Asimilación de skills) CERRADO**. UAT-11 verificado end-to-end.
- H4 (Expansion controlada), H6 (multipropósito), H7 (release candidate)
  del blueprint NO implementados (UAT-08/09/12/13 BLOCKED honestos).
- UAT-16 cerrado (H7 release candidate NO implementado, pero el
  criterio legal del blueprint ya se cumple via persistencia de
  handoff_json en node_executions).
- Trabajo activo: H5 skill_import (skill_importer.py + cmd_pack_import
  + 8 tests focalizados + UAT-11 BLOCKED→PASS).
- Siguiente: H4 Expansion controlada o H6 multipropósito. Operador decide.

## Último estado comprobado

- Repo: rama `main`, **253 tests pytest verde**, lint format+check limpio.
- Auditoría UAT honesta: **12/16 PASS, 0 FAIL, 4 BLOCKED honestos**.
- Python 3.13.15 via `mise`; `uv` para resolver venv reproducible.

### H5 skill_import — diseño

Pipeline: `IMPORT → ANALYZE → STRUCTURE → VALIDATE → REGISTER`.

- `analyze_skill(path)`:
  - Hashea contenido (sha256) sin ejecutarlo.
  - Clasifica archivos por extension (markdown_doc, json_config,
    yaml_config, python_script, plain_text, binary, unknown).
  - **python_script**: detectado, registrado en `scripts_detected`
    y `entries_ambiguous` con `ambiguity='ignored'`. **NUNCA se ejecuta.**
  - Capacidades extraidas = headers h2/h3 literales (NO reinterpreta).
- `register_imported_skill(storage, ...)`: persiste Source con
  `kind='skill_pack'` y `content_hash`. NO inventa claims/entities;
  la fuente se conserva como material original.
- CLI: `sg pack import <project> <path> [--report PATH]`.

### Reglas duras (verificadas en tests)

- Script Python con `raise SystemExit(99)` NO hace fallar el import
  (test_script_never_executes_during_import).
- `print('pwned')` en script NO aparece en stdout (verificado en UAT-11).
- Capacidades extraidas: el campo `nota_honesta` afirma literalmente
  "NO decisiones verificadas".

### Limitaciones declaradas

- Capacidades extraidas son SEÑALES heurísticas, no decisiones.
  Sin Adapter real (H7+) no se pueden 'verificar' capacidades de
  comportamiento.
- Sin API CLI para listar packs importados (`sg pack list`).
  Mejora futura.

### Mejoras legales de UATs en este turno

- **UAT-03**: aniadida verificación de capabilities persistidas en
  storage (query directa `SELECT spec_json WHERE name='software-pack'`,
  debe contener `'review'` y `'review.run'`).
- **UAT-05**: aniadido step `compile` best-effort que imprime el JSON
  completo del handoff; verificado que contiene `recipe_ref`,
  `definition_kind`, source original. Cubre "entradas obligatorias,
  decisiones aplicables y conocimiento vigente".
- **UAT-06**: docstring actualizado (el bug "frontier ejecuta TODOS"
  ya estaba arreglado en commit bdd196f; antes el docstring mentía).
- **UAT-16**: pasó de BLOCKED a PASS. Verifica que `node_executions.
  handoff_json` persiste el handoff completo tras cambiar la
  resourceRevision del brick.

### Decisiones tomadas en este turno

- **Dedup**: `now_iso` centralizado en `runtime.py`, 3 módulos
  reexportan con `as _now_iso`. Imports redundantes (`UTC`,
  `datetime`) quitados.
- **UAT-05 fortalecido**: verificación real del contenido del handoff
  (recipe_ref, definition_kind) en lugar de solo rc=10/rc=0.
- **UAT-03 fortalecido**: query directa al storage verifica que las
  capabilities (`spec.capabilities[].name='review'`, `entrypoint='review.run'`)
  están en `spec_json`.
- **UAT-16 implementado** (de BLOCKED a PASS): flujo end-to-end que
  ejecuta workflow v1, captura handoff_json, cambia a v2, ejecuta
  nuevo workflow, verifica coexistencia e inalterabilidad del viejo.

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
