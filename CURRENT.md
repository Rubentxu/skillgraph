# CURRENT — puntero operativo

> Última verificación: 2026-09-23 10:47 (Europe/Madrid).
> Revisión: `05dcb58 spec(h3): sub-specs slices 2-5 + spec padre compactado`.

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1 → Etapa 2.
Source of truth: `external/blueprint-v1/plan/ROADMAP.md`, `external/blueprint-v1/README.md`,
`external/blueprint-v1/adr/`.

## Hito y trabajo activo

- H0 (Blueprint validado) **cerrado**.
- H1 (Recursos persistentes) **cerrado**.
- H2 (Ejecución local) **cerrado** con la nota honesta: **UAT-06 FAIL**
  (bug `_calculate_frontier` ejecuta TODOS los nodos en una sola pasada;
  deuda H4+). Evidencia en `tests/uat-evidence/UAT-06.json`.
- Trabajo activo: **H3 firma del spec + Slice 1 (Knowledge ADT + Storage)**.
  Auditoría UAT honesta creada (`tests/uat_audit.py` + 7 evidencias JSON).
- Siguiente desbloqueado: **Slice 1** (`specs/h3-slice-1.md`, +17 tests).

## Último estado comprobado

- Repo: rama `main`, **27 commits limpios, lint verde, 161 tests verdes**.
- Working tree: limpio (con cambios sin commitear en `tests/uat_audit.py`,
  `tests/uat-evidence/`, `STATE.yaml`, `CURRENT.md`).
- CI pasa localmente con `scripts/ci.sh` (~43s).
- Python 3.13.15 via `mise`; `uv` para resolver venv reproducible.
- Bootstrap del paquete: `hatchling`, `py.typed`, dev deps PEP 735.
- **Auditoría UAT honesta** (subprocess real) ejecutada: 5 PASS, 1 FAIL
  (UAT-06 bug `_calculate_frontier`), 1 BLOCKED (UAT-05 H3 pendiente).
  Evidencias en `tests/uat-evidence/UAT-0{1..7}.json`.
- AGENTS.md cerrado: Section 11 (Haskell-inspired functional programming)
  con 15 subsecciones.
- Spec H3 diseño completo (`specs/h3-knowledge.md`).
  - D1 cerrada con spike (`dulwich`, commit `0e94e16`).
  - D2/D3/D4 firmadas implícitamente por el usuario con recomendaciones agente:
    brick + warning-strict + caracteres.
  - 5 sub-specs (slices 1-5) diseñados y commiteados.
  - Total tests previstos tras firma: **161 → 225**.

## Decisiones del operador registradas

1. SDDK **on** en este workspace (intento fallido por bug externo del binario
   `sddk` que devuelve `workspace_id` distinto por invocación). Workaround:
   continuamos sin SDDK porque las Etapas 0..2 no dependen de él.
2. `.zip` y `create.py` se conservan hasta confirmar versión de la copia descomprimida.
3. Python 3.13.15 (runtime local; 3.14 disponible en sistema).
4. **No Rust en el bootstrap**: solo cuando un cuello de botella justifique
   la integración, detrás de interfaz Python. Tabla de triggers GO en este mismo archivo.
5. **Ciclos en workflows NO se soportan** en H2. El controller calcula
   frontier por current_node y termina cuando el current ya está SUCCEEDED
   incluso si su successor es otro nodo del mismo run. Es deuda H4+,
   se documenta aquí.
6. **D2/D3/D4 firmadas implícitamente** (operador aprueba recomendaciones del
   agente: brick + warning-strict + caracteres).

## Bloqueos abiertos

- **b3 (SDDK adopción real)** bloqueado por bug del binario SDDK:
  cada invocación de `sddk config resolve --cwd` devuelve un `workspace_id`
  distinto, así que el `set on --workspace` no se encuentra con el
  `resolve`. Confirmado reproduciendo. **No es un gate del usuario**; es
  bug de toolchain. Workaround aplicado: continuamos sin SDDK porque
  S0..S5 + Etapas 0..2 no dependen de él.
- **UAT-06 FAIL**: bug `_calculate_frontier` (deuda H4+, no bloquea H3).

## Próxima acción concreta

1. ~~Auditoría UAT honesta subprocess con sistema de evidencias.~~ Hecho
   (`tests/uat_audit.py` + `tests/uat-evidence/`).
2. ~~Firma del spec H3 (D2/D3/D4).~~ Recomendaciones agente aprobadas por
   operador implícito. Spec pasa de DISEÑO-COMPLETO a SIGNED.
3. **Implementar Slice 1** (`specs/h3-slice-1.md`): Knowledge ADT en
   `src/skillgraph/knowledge.py` + Storage delta + 17 tests en
   `tests/test_knowledge.py`. Cerrar slice → commit → verificar que los
   161 tests siguen verdes y los 17 nuevos pasan.
4. Mantener `scripts/ci.sh` ejecutándose localmente en cada commit hasta
   que haya runner externo configurado.

## Valoración Rust (decisión operador 2026-09-23)

**Recomendación: NO meter Rust en el bootstrap.** Abrir puerta solo cuando un
spike demuestre cuello de botella real en uno de estos 5 puntos:

| # | Pieza | Trigger GO | Estado |
|---|---|---|---|
| 1 | Validación de esquemas de recursos (bricks) | >100 ms / brick sobre 5k schemas | Spike S4 pendiente |
| 2 | Hash + serialización de handoff inmutable | >200 ms / materialización | Etapa 2 — NO se disparó |
| 3 | Invalidación incremental de conocimiento (DFS tipado) | >500 ms sobre 10k Claims + 50k Relations | Etapa 3 |
| 4 | Cálculo de frontera de workflow | >200 ms sobre 1k nodos | Etapa 2 — NO se disparó |
| 5 | Fingerprinting Git incremental | >1 s por 1k archivos cambiados | Etapa 3 |

**Forma de integración (cuando entre):** binario CLI o PyO3 detrás de
interfaz Python (`Storage`, `Validator`, `HandoffHasher`, `FrontierResolver`).
El plano de control sigue en Python (ADR-0001).

**Antiobjetivo del roadmap**: no introducir una base de grafos especializada,
scheduler distribuido o sistema de agentes permanentes sin un requisito
observado. Rust como acelerador sí; Rust como framework, no.
