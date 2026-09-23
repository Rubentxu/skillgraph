# CURRENT — puntero operativo

> Última verificación: 2026-09-23 10:36 (Europe/Madrid).
> Revisión: `05dcb58 spec(h3): sub-specs slices 2-5 + spec padre compactado`.

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1 → Etapa 2.
Source of truth: `external/blueprint-v1/plan/ROADMAP.md`, `external/blueprint-v1/README.md`,
`external/blueprint-v1/adr/`.

## Hito y trabajo activo

- H0 (Blueprint validado) **cerrado**.
- H1 (Recursos persistentes) **cerrado**.
- H2 (Ejecución local) **cerrado**: vertical slices S0..S5 verdes, subcomando `run`
  con fixtures, ResumeOrStart (bug real fix), tests E2E subprocess UAT-04/06/07.
- Deuda H2 restante: el controller **NO soporta workflows cíclicos** (deuda
  real para H4+ / DecisionNode). Documentada y testeada; no se intentó cubrir
  en H2.
- Trabajo activo: **H3 spec borrador** (`specs/h3-knowledge.md`,
  commit `903f252`). 4 decisiones pendientes (D1 git lib,
  D2 brick, D3 sync invalidación, D4 token budget). NO se
  implementa nada hasta que el spec esté firmado.
- Siguiente desbloqueado: **resolver las 4 decisiones D1-D4 + firma
  del spec**, luego arrancar Slice 1 (Knowledge ADT + Storage delta).

## Último estado comprobado

- Repo: rama `main`, **26 commits limpios, lint verde, 161 tests verdes**.
- Working tree: limpio. CI pasa localmente con `scripts/ci.sh` (~43s).
- Python 3.13.15 via `mise`; `uv` para resolver venv reproducible.
- Bootstrap del paquete: `hatchling`, `py.typed`, dev deps PEP 735.
- Spikes S0..S5 ejecutados y verificados con tests de extremo a extremo.
- CLI ejecuta `init/project create/list/inspect/brick/run` con códigos
  de error tipados (todas las ramas tienen test subprocess o in-process).
- UAT-01..07 PASS contra la CLI real (subprocess donde es posible).
- CI mínimo (`scripts/ci.sh`) ejecutable localmente y replicable por cualquier
  runner externo.
- AGENTS.md cerrado: Section 11 (Haskell-inspired functional programming)
  con 15 subsecciones.
- Spec H3 diseño completo (`specs/h3-knowledge.md`).
  - D1 cerrada con spike (`dulwich`, commit `0e94e16`).
  - 5 sub-specs (slices 1-5) diseñados y commiteados:
    `specs/h3-slice-1.md` ... `specs/h3-slice-5.md`.
  - Total tests previstos tras firma: **161 → 225**.
  - D2/D3/D4 pendientes de firma. Recomendación agente: brick +
    warning-strict + caracteres.

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

## Bloqueos abiertos

- **b3 (SDDK adopción real)** bloqueado por bug del binario SDDK:
  cada invocación de `sddk config resolve --cwd` devuelve un `workspace_id`
  distinto, así que el `set on --workspace` no se encuentra con el
  `resolve`. Confirmado reproduciendo. **No es un gate del usuario**; es
  bug de toolchain. Workaround aplicado: continuamos sin SDDK porque
  S0..S5 + Etapas 0..2 no dependen de él.

## Próxima acción concreta

1. ~~Cerrar docs de la auditoría honesta (CURRENT/STATE/SESSION).~~ Hecho (`d39c6d3`).
2. ~~**Etapa 3 — diseño primero**: spec corto + descomposición.~~ Hecho (`903f252`, `specs/h3-knowledge.md`).
3. **Resolver las 4 decisiones pendientes del spec H3** (D1 git lib, D2 brick, D3 sync invalidación, D4 token budget) y firmarlo. Sin spec firmado, no se implementa.
4. Tras firma: arrancar Slice 1 (Knowledge ADT + Storage delta).
5. Mantener `scripts/ci.sh` ejecutándose localmente en cada commit hasta que haya runner externo configurado.

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
