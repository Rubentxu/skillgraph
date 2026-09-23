# CURRENT — puntero operativo

> Última verificación: 2026-09-23 10:05 (Europe/Madrid).
> Revisión: `6011f60 test(cli): 8 tests ramas restantes (5,6,10,12,21 + helpers)`.

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
- Trabajo activo: cerrar docs de la auditoría honesta + limpieza final.
- Siguiente desbloqueado: **Etapa 3** (control-flow dinámico: ContextController +
  KnowledgeController + Discovery). Diseño pendiente, no implementación.

## Último estado comprobado

- Repo: rama `main`, **14 commits limpios, lint verde, 161 tests verdes**.
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

1. ~~Cerrar docs de la auditoría honesta (CURRENT/STATE/SESSION).~~ Hecho (este commit).
2. **Etapa 3 — diseño primero**: leer `external/blueprint-v1/docs/07-contexto-y-handoff.md`
   y `08-conocimiento.md`, escribir spec corto (siguiendo forma del spec de Etapa 2),
   descomponer en 3-5 slices de implementación.
3. NO implementar nada de Etapa 3 hasta que el spec esté firmado.
4. Mantener `scripts/ci.sh` ejecutándose localmente en cada commit hasta que
   haya runner externo configurado.

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
