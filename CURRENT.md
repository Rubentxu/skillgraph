# CURRENT — puntero operativo

> Última verificación: 2026-09-23 09:00 (Europe/Madrid).
> Revisión: `0433b63 test(registry): cerrar ramas de validacion + properties en relations`.

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1.
Source of truth: `external/blueprint-v1/plan/ROADMAP.md`, `external/blueprint-v1/README.md`,
`external/blueprint-v1/adr/`.

## Hito y trabajo activo

- Hito: **H0** (Blueprint validado) + **H1** (Recursos persistentes) **cerrados**.
- Trabajo activo: **continuación del roadmap** (Etapa 2 — ejecución recuperable).
- Siguiente desbloqueado: **b3** (SDDK, bloqueado por bug externo) →
  **`spec → tasks → apply`** del primer WorkItem de Etapa 2.

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

1. Cerrar ciclo de bootstrap con `STATE.yaml`/`SESSION-JOURNAL.md`
   actualizados.
2. **Siguiente WorkItem (Etapa 2)**: diseño del primer vertical slice
   de ejecución determinista — `RunController` + `FakeAgentAdapter` +
   handoff mínimo (subgrafo de 2-3 nodos: decisión → acción → result).
3. Documentar el WorkItem y delegar a través del workflow SDDK cuando
   el bug de adopción esté resuelto. Si no se resuelve, ejecutar
   directamente con TDD focalizado como en S0/S1/Etapa1.

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