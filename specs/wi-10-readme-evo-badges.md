# WI-10 — README badges + texto evolution-v2 (H10..H15)

**WorkItem ID**: WI-10
**Fecha**: 2026-09-26
**Workflow SDDK**: A-min (single apply, scope acotado a docs/)
**Status**: ✅ CLOSED

## Contexto

Tras WI-06/07/08/09 (suite 984/984 PASS, nucleo evolution-v2 al ≥93%),
el README principal quedaba stale:
- Badge de tests: `405/405` (valor pre-WI-01; congelado desde v0.6.0).
- Texto del estado: solo cubre blueprint v1 (H0..H9); no menciona
  evolution-v2 (H10..H15), que está cerrado al 100%.

WI-10 sincroniza el README para reflejar la realidad post-stewardship
créatif, sin tocar la prosa original.

## Decisiones

- **D-31**: WI-10 = solo README. NO toca código, ni tests, ni CI.
- **D-32**: Mantener el badge "405 → 984" + añadir badge "evolution_v2
  100% (H11..H15)" para que la portada refleje ambos logros.
- **D-33**: NO release/tag en este workitem.
- **D-34**: Mantener `__version__ = "0.14.5.dev0"` (sin bump).

## Scope

Único archivo objetivo: `README.md` (EN + ES, simétrico).

## Cambios aplicados

1. **L12-14 (badges)**: `405/405` → `984/984`, añadir badge
   `evolution_v2 100% (H11..H15)`.
2. **L41 (EN)**: párrafo nuevo "evolution-v2 line" explicando el H10..H15
   (file signatures, scopes, expert handoffs, validation receipts,
   bounded self-improvement, persistido como `Evidence`).
3. **L53 (EN tabla)**: fila nueva "Evolution v2 (H11..H15)" + fila
   "984/984 tests".
4. **L173 (ES)**: párrafo espejo en español.
5. **L185-187 (ES tabla)**: filas espejo.

## Verificación

- `grep "\b405\b\|\b830\b\|\b855\b\|\b888\b\|\b929\b\|\b957\b"`
  en `README.md` → 0 matches (no quedan números stale).
- Estructura del documento conservada: misma prosa para secciones
  que no cambian (Why SkillGraph, Quickstart, Architecture, etc.).
- Working tree: solo `README.md` modificado.

## Definition of Done

- [x] Spec WI-10 creada (`specs/wi-10-readme-evo-badges.md`).
- [x] Badge `984/984` en header.
- [x] Badge nuevo `evolution_v2 100% (H11..H15)` en header.
- [x] Párrafo evolution-v2 en EN + ES.
- [x] Filas tabla EN + ES actualizadas con H11..H15 + 984/984.
- [x] `STATE.yaml` next_workitem actualizado a WI-10 → siguiente bloque.
- [x] `SESSION-JOURNAL.md` entrada WI-10.
- [x] Sin cambios en código. Suite 984/984 PASS sigue vigente.
- [x] ruff format + check: no afectados (no hay `.py` tocado).
- [x] Commit atómico.
- [x] NO release/tag (regla D-33).

## Próximos pasos

- Bump `0.14.5.dev0` → `0.14.6` + tag anotado `v0.14.6`:
  PENDIENTE de aprobación operador tras WI-10 (workitem legítimo
  de release, NO se ejecuta sin consigna).
- Próximo bloque substantivo de roadmap: si operador no aprueba
  release, el agente entra en modo de espera honesto. Backlog
  pendiente de spec: deuda arquitectónica (H-01..H-06, H-10),
  E1 Adapter real, T3 Threat model, T5 Backups CLI, T6 Observabilidad.
