# CURRENT — puntero operativo

> Última verificación: 2026-09-23 09:15 (Europe/Madrid).
> Revisión: `e763102 feat(e2-s4+s5): WorkflowPlan + RunController + ejecucion recuperable`.

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1.
Source of truth: `external/blueprint-v1/plan/ROADMAP.md`, `external/blueprint-v1/README.md`,
`external/blueprint-v1/adr/`.

## Hito y trabajo activo

- Hito: **H0** (Blueprint validado) + **H1** (Recursos persistentes) **cerrados**.
- Vertical slice Etapa 2 **completo** (127 tests verdes, 9 commits).
- Trabajo activo: **subcomando CLI `run` + fixtures end-to-end + cierre del ciclo en docs**.
- Siguiente desbloqueado: **Etapa 3** (control-flow dinámico: ContextController + KnowledgeController + Discovery).

## Último estado comprobado

- Repo: rama `main` con 5 commits limpios, lint verde, 40 tests verdes en 11 s.
- Python 3.13.15 via `mise`; `uv` para resolver venv reproducible.
- Bootstrap del paquete: `hatchling`, `py.typed`, dev deps PEP 735.
- Spikes S0 y S1 ejecutados y verificados con tests de extremo a extremo.
- CLI ejecuta `init/project create/list/inspect/brick` con códigos de error tipados.
- UAT-01..03 PASS contra la CLI real (subprocess).
- Deuda H0 cerrada: `registry.py` 88% cobertura; ramas de validación
  tipada y properties de relaciones ejercitadas.

## Decisiones del operador registradas

1. SDDK **on** en este workspace (intento fallido por bug externo).
2. `.zip` y `create.py` se conservan hasta confirmar versión de la copia descomprimida.
3. Python 3.11+ (runtime: 3.13.15 en local; 3.14.7 disponible en sistema).
4. **No Rust en el bootstrap**: solo cuando un cuello de botella justifique
   la integración, detrás de interfaz Python.

## Bloqueos abiertos

- **b3 (SDDK adopción real)** bloqueado por bug del binario SDDK:
  cada invocación de `sddk config resolve --cwd` devuelve un `workspace_id`
  distinto, así que el `set on --workspace` no se encuentra con el
  `resolve`. Confirmado reproduciendo: `w-403ce06c...`, `w-680bc8...`,
  `w-b90869...`, etc. El shim pasa el cwd pero el binario parece ignorar
  el determinismo por path. **No es un gate del usuario**; es bug de
  toolchain. Workaround aplicado: continuamos sin SDDK porque S0, S1 y
  Etapa 1 no dependen de él. Reabrir b3 cuando arreglen el binario.

## Próxima acción concreta

1. ~~Cerrar ciclo de bootstrap con `STATE.yaml`/`SESSION-JOURNAL.md` actualizados.~~ Hecho (commit `7f7e4d9`).
2. ~~Diseñar Etapa 2: ejecutar el primer vertical slice.~~ Hecho (commits `92929a9`, `64bc05d`, `92a5174`, `e763102`).
3. **Subcomando CLI `run`** + **fixture end-to-end CLI** que ejercite el RunController desde la CLI (cierre H2 por la via UAT).
4. **Etapa 3** (siguiente): ContextController (receta de handoff con obligatorias + opcionales) y KnowledgeController (Claims/Evidence con invalidación). Diseno: leer `external/blueprint-v1/docs/07-contexto-y-handoff.md` y `08-conocimiento.md`, escribir spec corto y descomponer en 3-5 slices.

## Valoración Rust (decisión operador 2026-09-23)

**Recomendación: NO meter Rust en el bootstrap.** Abrir puerta solo cuando un
spike demuestre cuello de botella real en uno de estos 5 puntos:

| # | Pieza | Trigger GO | Estado |
|---|---|---|---|
| 1 | Validación de esquemas de recursos (bricks) | >100 ms / brick sobre 5k schemas | Spike S4 pendiente |
| 2 | Hash + serialización de handoff inmutable | >200 ms / materialización | Etapa 2 |
| 3 | Invalidación incremental de conocimiento (DFS tipado) | >500 ms sobre 10k Claims + 50k Relations | Etapa 3 |
| 4 | Cálculo de frontera de workflow | >200 ms sobre 1k nodos | Etapa 2 |
| 5 | Fingerprinting Git incremental | >1 s por 1k archivos cambiados | Etapa 3 |

**Forma de integración (cuando entre):** binario CLI o PyO3 detrás de
interfaz Python (`Storage`, `Validator`, `HandoffHasher`, `FrontierResolver`).
El plano de control sigue en Python (ADR-0001).

**Antiobjetivo del roadmap**: no introducir una base de grafos especializada,
scheduler distribuido o sistema de agentes permanentes sin un requisito
observado. Rust como acelerador sí; Rust como framework, no.