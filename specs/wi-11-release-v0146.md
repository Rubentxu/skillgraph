# WI-11 — Release v0.14.6 (housekeeping: coverage hardening H-14 + docs sync)

**WorkItem ID**: WI-11
**Fecha**: 2026-09-26
**Workflow SDDK**: A-min (single apply, scope acotado a release_governance)
**Status**: ✅ CLOSED

## Contexto

Tras WI-06/07/08/09/10 (5 WIs de housekeeping: 3 commits coverage +
2 commits docs), el repositorio está en estado verificable:

- Suite: **984/984 PASS** en 174.26s (era 957 → +27 tests).
- Núcleo evolution-v2 (H11..H15): ≥93% cobertura en todos los modulos.
- UAT: 16/16 PASS, invariante al avance.
- 0 deuda testeable abierta (`sddk debt report` → 0 findings).
- README + CURRENT.md sincronizados con la realidad post-stewardship.

**Disparador de release** (regla 6 — SDDK):
- Feature completa + criterios verificados.
- Cadencia inteligente (5 WIs agrupados, no micro ni big-bang).
- SEMVER: PATCH (0 breaking API, 0 feat nuevo, solo tests + docs).

## Decisiones

- **D-35**: Bump `__version__ = "0.14.5.dev0"` → `"0.14.6"` (PATCH).
  Razon SEMVER: los 5 commits WI-06..WI-10 son housekeeping
  puro (3 tests + 2 docs), 0 cambios en API pública.
- **D-36**: Tag anotado `v0.14.6` con mensaje multi-línea (patrón
  consistente con v0.14.1..v0.14.5).
- **D-37**: NO push a `origin` (regla WI-01 vigente). Tag queda
  local; push pendiente de aprobación operador.
- **D-38**: NO archivado formal SDDK (requiere `permissions.yaml`
  o `--delivery-kind ManagedClosureDelivery`, no expuestos).
- **D-39**: Mantener `STATE.yaml.release.tag=v0.14.0` (referencia
  histórica) pero actualizar contador `releases_total` y `tag_sha`.

## Scope

Único cambio en producción: `src/skillgraph/__init__.py:27` (`__version__`).
Más CHANGELOG.md, STATE.yaml, CURRENT.md, SESSION-JOURNAL.md, specs/.

## Cambios aplicados

1. `src/skillgraph/__init__.py`: `__version__ = "0.14.6"`.
2. `CHANGELOG.md`: entrada nueva `## v0.14.6 — WI-06..WI-10 housekeeping`.
3. `STATE.yaml`: tests 957→984, current_workitem WI-11,
   next_workitem WI-12 (siguiente bloque roadmap pendiente de spec),
   `releases_total` actualizado.
4. `CURRENT.md`: header version `0.14.5.dev0` → `0.14.6`,
   timestamp 18:18 → 18:23, marker "post-WI-11".
5. `SESSION-JOURNAL.md`: entrada WI-11.
6. Tag anotado `v0.14.6` con mensaje detallado.
7. `specs/wi-11-release-v0146.md`: este spec (D-35..D-39).

## Verificación

- `uv run pytest` (suite completa) → 984/984 PASS.
- `uv run ruff check .` → All checks passed.
- `git rev-parse v0.14.6` → SHA actual.
- `python -c "import skillgraph; print(skillgraph.__version__)"` → `0.14.6`.
- `tests/test_release_governance.py` 2/2 PASS (cumple reglas de bump).
- Pre-commit hook verde.

## Definition of Done

- [x] Spec WI-11 creada (`specs/wi-11-release-v0146.md`).
- [x] Bump `__version__ = "0.14.6"`.
- [x] Suite completa 984/984 PASS (verificada pre-bump).
- [x] Tag anotado `v0.14.6` con mensaje coherente.
- [x] CHANGELOG.md actualizado.
- [x] STATE.yaml / CURRENT.md / SESSION-JOURNAL.md sincronizados.
- [x] ruff format + check limpios.
- [x] Commit atómico `build(release): bump 0.14.5.dev0 -> 0.14.6 (WI-11)` + tag.
- [x] NO push a origin (regla WI-01).

## Próximos pasos

- **Push**: pendiente aprobación operador. 22 commits ahead of origin,
  ahora tras WI-11: 23 commits (incluye bump `__version__`).
- **Próximo bloque roadmap**: pendiente de spec operador. Backlog
  documentado en `CURRENT.md` "Pendientes" + `STATE.yaml` (deuda
  arquitectónica, E1 Adapter real, T3 Threat, T5 Backups, T6
  Observabilidad).
