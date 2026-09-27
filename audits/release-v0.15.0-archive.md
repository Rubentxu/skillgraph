# SDDK Archive — Release v0.15.0 (R0 housekeeping + WI-31 + WI-35)

> Artifact durable ligado a `release-receipt` v0.15.0 (tag anotado `0d73f73`).
> Companion de `audits/release-v0.15.0-receipt.md`. Sincroniza el cierre
> del ciclo R0 + WI-31 + WI-35 con la fuente de verdad git (origin/main).

## Metadata del archive

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.15.0` |
| Tag SHA | `0d73f731dd9142cd44b5be27965f642ab03254b1` |
| Commit del tag | `4d6d1b430ca3f726a080e12c37dd58180d72483b` |
| Bump | MINOR (`0.14.8.dev0` -> `0.15.0`) |
| Tipo de release | housekeeping + refactor Protocol + docs + 1 BREAKING compat |
| Suite al tag | 1078/1078 PASS en 204.03s |
| ruff | All checks passed (check + format) |
| Coverage al tag | 95.25% lines / 90.54% branches |
| Source of truth | origin/main (push pendiente en este archive; ver abajo) |

## Manifest del ciclo (testimonio durable)

```
v0.15.0 = 4d6d1b4 (build release: bump version + STATE/CURRENT/CHANGELOG sync)
       + 6e5566e + 7e5566e + cf04b57 (amends intermedios antes del tag final)
       + 0d73f73 (tag anotado con mensaje completo)

Componentes del ciclo (entre v0.14.8 y v0.15.0, 11 commits en main):
  R0:
    QW-PREP = preparacion de archivos (commit anadido al rebase)
    QW-A 1dd1fd1 fix(http_adapter): Anthropic default migrated retired model
    QW-B 3b16e71 fix(redaction)! BREAKING: EventLog default none -> metadata
    QW-C 13a6fa5 feat(storage): Storage context manager + idempotent close
    QW-D c516abe refactor(runtime_types): EVENT_KINDS single-source-of-truth
    QW-E 3cf5182 refactor(runtime_types): SOURCE_KINDS single-source-of-truth
    QW-F ff714df chore(coverage): fail_under=80 + omit entry points + QW-G
    QW-H 73eb973 refactor(uat_audit): uat_08/09 leen evidencia E2E existente
    QW-I 29e990a docs(blueprint): snapshot versionado + sync script idempotente
  WI-31:
    e82c670 refactor(runcontroller): cast Storage Protocol + knowledge_repository()
            factor + 7 tests; housekeeping sddk post-impl
  WI-35:
    2adeb52 docs(state): prioridad_6 sddk_cycle_methodology + journal entry
```

## Cierre del ciclo

- **release-receipt**: `audits/release-v0.15.0-receipt.md` (156 LoC).
- **archive-manifest**: este archivo (`audits/release-v0.15.0-archive.md`).
- **CHANGELOG sync**: entrada `[0.15.0]` anadida al tope (Keep-a-Changelog).
- **STATE.yaml sync**:
  - `tests.total` 1048 -> 1078 (+30 reales; memoria previa era 1068, off-by-10).
  - `tests.duration_s` 180 -> 528 (re-medido en HEAD).
  - `package_version` `0.14.8.dev0` -> `0.15.0`.
  - `release.tag` `v0.14.0` -> `v0.15.0` (con `release.releases[]` extendida
    para cubrir el gap historico v0.14.1..v0.14.8 que faltaba del historial).
  - `release.fecha` `2026-09-24` -> `2026-09-27`.
- **CURRENT.md sync**: header refleja v0.15.0 + tag SHA + WI-31/WI-35 status.
- **Encoding fix**: CURRENT.md `Última verificación` (UTF-8 `c3 ba 6c 74 69 6d 61`).
- **SDDK closure**: OK. Tag anotado en commit valido, release_governance 2/2 PASS.

## Source of truth (origin/main)

Estado de sincronizacion con `origin/main`:

| Concepto | Estado | Evidencia |
|----------|--------|-----------|
| HEAD local | `4d6d1b4` | `git rev-parse HEAD` |
| Tag `v0.15.0` | anotado en `4d6d1b4` | `git rev-parse v0.15.0^{}` |
| `origin/main` HEAD | pendiente de push | `git push origin main v0.15.0` |
| Pre-push hook | conocido a colgar (workaround `--no-verify`) | convencion R0 + WI-31 |

> **Nota**: el push al remote esta pendiente al momento de emitir este archive.
> El operador decidira cuando ejecutar `git push origin main v0.15.0` con
> smoke pre-validation (patron R0: si el pre-push hook cuelga, `--no-verify`
> es la salida documentada).

## Comandos reproducibles

```bash
# 1. Smoke pre-push (validacion rapida):
uv run pytest tests/test_release_governance.py -v  # 2/2 PASS
uv run pytest --no-header -q                       # 1078/1078 PASS

# 2. Push (con workaround para el pre-push hook):
git push origin main v0.15.0 --no-verify  # si el hook cuelga (>120s)

# 3. Post-tag housekeeping (post-push):
#   - Bump 0.15.0 -> 0.15.0.dev0
#   - STATE.yaml release.evidencia.tag_sha = 0d73f731dd9142cd44b5be27965f642ab03254b1
#   - CURRENT.md "Version activa" 0.15.0 (tag anotado v0.15.0) -> 0.15.0.dev0
#   - Commit: chore(release): post-tag bump 0.15.0 -> 0.15.0.dev0
#   - Push con --no-verify si el hook cuelga
```

## Compatibilidad: guia de migracion (para tenants con EventLog pre-0.15.0)

```python
# ANTES (v0.14.8 y ancestros): EventLog con policy_resolver explicito NO cambia.
#   log = EventLog(storage, policy_resolver=lambda _t: "metadata")  # explicito

# AHORA (v0.15.0): default seguro. Si necesitas el comportamiento previo:
log = EventLog(
    storage,
    policy_resolver=lambda _t: "none",  # opt-in a no-redaction
)
```

No hay otra guia de migracion: el resto de cambios son 100% backward-compat.

## Erratum preservado

`v0.14.0` permanece como evidencia historica de una release publicada con
package metadata defectuosa (`__version__ = "0.7.0.dev0"`). La release
correctiva sigue siendo `v0.14.1` (WI-01). Regla 12 AGENTS.md: la
provenance historica no se reescribe.

## Lecciones operacionales (para archive)

1. **Encoding `Ú` en CURRENT.md**: tres pasadas de bash + Python fallaron
   en restaurar el byte `c3 ba`; el `edit` tool con `old_string`/`new_string`
   es la unica via robusta. Documentado en `release-v0.15.0-receipt.md`.
2. **Tag anotado + amend**: incompatible. Workflow optimo: amend hasta que
   el commit del bump este estabilizado, *luego* tag.
3. **Smoke paralelo**: usar `uv run pytest` en background durante release
   para confirmar el conteo real antes de taggear. Mi memoria era off-by-10
   (1068 vs 1078); el collect-only es la fuente canonica.
4. **QW-B unica BREAKING** del ciclo: QW-A es fix/PATCH (migracion sin accion),
   QW-C/I/WI-31 son feat/MINOR, QW-D/E/F/G/H/WI-35 son companion sin bump.

## Estado de salud post-release

- Adopt: complete (p-74299cf88f51dab9 / w-65c5e70e84b3c9144de10d74).
- Framework: SDDK 1.171.2.
- Tests: 1078/1078 PASS.
- Coverage: 95.25% lines / 90.54% branches.
- Backlog: 0 live items (todos los del R0 + WI-31 + WI-35 promoted o completed).
- Cycle activo: ninguno.
- Errata: 303 ResourceWarnings residuales, `paths.py` 81% branches Windows,
  `cli/runner.py` 49% coverage. No bloquean release.
