# CURRENT — puntero operativo

> Última verificación: 2026-09-23 08:42 (Europe/Madrid).
> Revisión: pre-commit (no hay commit todavía en este bootstrap).

## Goal

Arrancar SkillGraph siguiendo el blueprint: Etapa 0 (S0 + S1) → Etapa 1.
Source of truth: `docs/plan/ROADMAP.md`, `docs/README.md`, `docs/adr/`.

## Hito y trabajo activo

- Hito: **H0** (Blueprint validado).
- Trabajo activo: **b1 — bootstrap estructural** (en curso).
- Siguiente desbloqueado: **b2** (pyproject + commit del blueprint), **b3** (adopción SDDK), **b4** (documentos de estado).

## Último estado comprobado

- `git init -b main` OK; identidad `SDDK Orchestrator <sddk@skillgraph.local>`.
- `python3 --version` → **3.14.7** (>=3.11 ✓; registrado en `STATE.yaml.python`).
- Blueprint reubicado en `docs/` con su estructura (12 docs + 12 ADR + 6 plan + referencias + README).
- `.gitignore` creado; `src/skillgraph/` y `tests/` listos para contenido.

## Decisiones del operador registradas

1. SDDK **on** en este workspace (pendiente ejecutar `sddk-mode set on --workspace`).
2. `.zip` y `create.py` se conservan hasta confirmar versión de la copia descomprimida.
3. Python 3.11+ (runtime disponible: 3.14.7; CI candidato: 3.11).

## Bloqueos abiertos

Ninguno técnico.

## Próxima acción concreta

1. Terminar **b1**: añadir el `pyproject.toml` (hecho en este ciclo) y los stubs de paquete.
2. **b2**: primer commit del blueprint + estructura.
4. **b3**: ejecutar `sddk-mode set on --workspace` + `sddk adopt apply` + `sddk config resolve`.
5. **b4**: regenerar `CURRENT.md`/`STATE.yaml`/`SESSION-JOURNAL.md` tras el primer commit.
6. **s0-1**: crear fixtures Markdown+YAML y parser mínimo para S0.

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