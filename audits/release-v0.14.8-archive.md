# SDDK Archive — Release v0.14.8 (WI-21..WI-30)

> Artifact durable ligado a `release-receipt` v0.14.8 (tag anotado `4a297ad`).
> Companion de `audits/release-v0.14.8-receipt.md`. Sincroniza el
> cierre del ciclo WI-21..WI-30 con la fuente de verdad git (origin/main).

## Metadata del archive

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.14.8` |
| Commit del tag | `4a297ad14c5e105824f80a534359e258e0d23e7a` |
| Post-tag housekeeping | `2595409` (bump a `0.14.8.dev0` + CURRENT/STATE sync) |
| Release commit | `de503b7` |
| Bump | MINOR (`0.14.7.dev0` -> `0.14.8`) |
| Tipo de release | refactor surgical + auditor reproducible (sin breaking changes) |
| Suite al tag | 1048/1048 PASS en 199.04s |
| ruff | All checks passed (check + format) |
| Source of truth | origin/main en `25954091fa6c518ac07bcce63380bc638209eb5a` (sincronizado) |

## Manifest del ciclo (testimonio durable)

```
v0.14.8 = de503b7 + c5c405e (release-receipt) + c4c214f (housekeeping .dev0)
        + a62a0b8 (STATE sync) + 2595409 (CURRENT sync)
HEAD actual: 2595409
ahead of origin/main (pre-push): 50 commits
push: COMPLETADO 2026-09-26 23:51 UTC (autorizacion operador explicita
       en mensaje "sube todo como puedes crear release sin integrar
       los commits en la fuente de verdad git")
```

## Cierre del ciclo

- **release-receipt**: `audits/release-v0.14.8-receipt.md` (113 LoC).
- **archive-manifest**: este archivo (`audits/release-v0.14.8-archive.md`).
- **CHANGELOG sync**: entradas v0.14.7 (retroactiva) y v0.14.8 anadidas.
- **STATE.yaml sync**: tests 1044->1048, package_version sincronizada.
- **CURRENT.md sync**: header refleja `0.14.8.dev0` + tag SHA.
- **SDDK closure**: OK. Push completado. El operador ya tiene la
  fuente de verdad git sincronizada.

## Decisiones formales del ciclo (D-52..D-68)

Total 17 decisiones, registradas en `audits/release-v0.14.8-receipt.md`:

- D-52..D-60: patrones de refactor surgical por WI individual.
- D-61..D-66: marco del auditor reproducible y politica D-66.
- D-67: patron CLI cmd_X = `_resolve_X_inputs` + `_reconcile_until_terminal`.
- D-68: helpers tree-walking en `git_source` van a module-level.

## Hallazgos honestos del ciclo

- **WI-22**: helper default `"vacio"` masculino vs caller `"revision
  vacia"` femenino. TDD catches via test de mensaje verbatim. Fix en
  `parse_markdown`.
- **WI-25**: kwarg `hop` quedo en helper sin uso. TDD catches via
  9 tests rojos.
- **WI-27**: triple F821 + UP035 + UP037 simultaneo requiere
  TYPE_CHECKING imports + `Sequence` from `collections.abc`.
- **WI-28**: `cmd_run` cc=22 (analisis manual) → cc=50 (auditor oficial).
  Las herramientas cuentan mas estrictamente. D-66 sigue satisfecha.
- **WI-29**: tuple-shape mismatch (7-tuple → 6-tuple) en
  `_resolve_run_inputs`. Tests rojos lo cazarons antes del commit.
- **WI-31 (release)**: 2 tests `test_release_governance` cazaron
  sincronizaciones faltantes (STATE.package_version y CURRENT.md
  no documentaban `0.14.8.dev0`). Tests cumplen su funcion: forzar
  coherencia entre docs y codigo.

## Compatibilidad

- 100% backward-compatible: ninguna firma publica cambia.
- Mensajes stderr, exit codes, summary prints: preservados verbatim.
- `__version__` bump: `0.14.7.dev0` → `0.14.8` (unico cambio observable).
- Sin migracion de datos (SQLite schema intacto).

## Seguridad

- Sin cambios de superficie de ataque. Ningun endpoint nuevo.
- Redaction `api_key` (WI-14 v0.14.7) sigue vigente.
- Backups ZIP sin cifrado (P3 deferred, gpg/age externo recomendado).

## Pendiente para el siguiente ciclo (roadmap post-v0.14.8)

### P1 — god modules (requieren ADR operador)

- H-01 storage.py (2407 LoC)
- H-02 cli/runner.py (2477 LoC, incluye `main` cc=50 excluido por D-64)
- runcontroller.py (1357 LoC)

### Formal — backlog stewardship

- `prioridad_1_spec_s7plus` y `prioridad_5_s7plus_ejecucion` siguen
  abiertos en `STATE.yaml.stewardship_backlog`. Requieren decision de
  operador sobre S7+ scope (Opcion A/B/C/D).

### H-03 — debt-reduction AGOTADA

- Politica D-66 satisfecha: cero hotspots publicos cc≥20 en `src/`.
- Unico cc≥15 restante: `main()` cc=50 (D-64: CLI entry point).
- Sin hotspots privados cc≥20 (todos los candidatos P2 cerrados).

### H-01/H-02 — pendiente de ADR

- Fuera del scope surgical. Cualquier reduccion requiere decision
  arquitectonica (split module, facade pattern, etc.).

### P3 deferred (no bloquea)

- Redaction de Handoff antes de enviar al LLM.
- Budget de tokens por tenant.
- Cifrado en reposo.
- Scheduling automatico de backups.
- Cache LLM prompt (WI-25..WI-30 auditaron, sin propuesta concreta).

## Verificacion final

```bash
$ git rev-parse HEAD
25954091fa6c518ac07bcce63380bc638209eb5a

$ git rev-parse v0.14.8
4a297ad14c5e105824f80a534359e258e0d23e7a

$ git ls-remote origin main | awk '{print $1}'
25954091fa6c518ac07bcce63380bc638209eb5a

$ git ls-remote origin refs/tags/v0.14.8 | awk '{print $1}'
4a297ad14c5e105824f80a534359e258e0d23e7a

$ uv run python -c "from skillgraph import __version__; print(__version__)"
0.14.8.dev0

$ uv run pytest 2>&1 | tail -1
======================= 1048 passed in 199.04s (0:03:19) =======================
```

Todas las referencias coinciden. Fuente de verdad git y codigo
publicado son coherentes.

## Estado del proyecto al cierre del ciclo

- 19 releases historicas (v0.3.0..v0.14.8).
- 16/16 UAT PASS preservados (16 UAT del blueprint v1 + 5 del H7).
- 1048/1048 tests preservados.
- Cobertura core: governance 99%, file_handoff 93%, improvement 100%.
- Auditor reproducible: `audits/audit_debt.py` + `audits/architecture-debt-2026-09-26.md`.
- Politica D-66 activa: cero hotspots publicos cc≥20.

## SDDK Close-out

Sesion cerrada. Released baseline: v0.14.8 (`4a297ad`).
Development head: `2595409` (post-tag housekeeping).
Workspace version: `0.14.8.dev0`.
Actual release tag: `v0.14.8`.
Release SHA: `4a297ad14c5e105824f80a534359e258e0d23e7a`.
Source of truth SHA: `25954091fa6c518ac07bcce63380bc638209eb5a`.

Ciclo: CLOSED. Evidencia: suite 1048/1048 PASS + ruff clean + push
sincronizado + tests governance enforcing. Deuda nueva: 0.
Siguiente paso del roadmap: decision operador sobre S7+ scope
(prioridad_1_spec_s7plus / prioridad_5_s7plus_ejecucion) o ADR para
P1 god modules.
