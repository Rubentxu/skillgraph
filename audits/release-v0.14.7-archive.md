# SDDK Archive — Release v0.14.7 (WI-12..WI-17)

> Artifact durable ligado a `release-receipt` v0.14.7 (tag anotado `5b7e296`).
> Sincroniza los specs delta y preserva la trazabilidad del ciclo.

## Metadata del release

| Campo | Valor |
|-------|-------|
| Tag anotado | `v0.14.7` |
| Commit del tag | `5b7e2968c1ac013de9cee67f73aa6ea1ec3fa736` |
| Post-tag housekeeping | `da0afc3` (bump a `0.14.7.dev0`) |
| State sync | `dbf7cef` (STATE.yaml + CURRENT.md) |
| Bump | MINOR (`0.14.6.dev0` -> `0.14.7`) |
| Tipo de release | FEAT + DOC acumulado (capacidades nuevas) |
| Suite al tag | 1044/1044 PASS en 180.48s |
| ruff | All checks passed |
| Tests nuevos | +35 (WI-12: +25, WI-13: +11, WI-14: +2, WI-15: +22, WI-17: 0) |
| WI-16 docs-only | runbook 9 secciones, 0 tests |

## Delta specs sincronizados

Los specs creados durante este ciclo (versionados en `specs/`):

- `specs/wi-12-http-adapter.md` — E1 Adapter real Anthropic + OpenAI.
- `specs/wi-13-cli-http-wiring.md` — CLI wiring `sg run --adapter http`.
- `specs/wi-14-t3-threat-model-http.md` — T3 STRIDE S8 + repr redact.
- `specs/wi-15-t5-backups-cli.md` — T5 `sg backup create|list|restore`.
- `specs/wi-16-t6-observability-runbook.md` — T6 runbook auditable.
- `specs/wi-17-h06-redundant-imports.md` — H-06 deuda tecnica.

## Delta docs

- `docs/observability-runbook.md` (nuevo, 300 LoC, 9 secciones).
- `docs/architecture/ADR-0015-threat-model-stride.md` (extendido: S8 + 5 gaps).

## Decisiones (D-46..D-50)

- **D-46** Adapter drop-in replacement via Protocol `AgentAdapter`.
- **D-47** Claim optimista refutado por RED test: `api_key` filtraba en
  repr; mitigacion `field(repr=False)` + `__repr__` explicito.
- **D-48** Backups ZIP + SHA-256 + `Connection.backup()` atomico.
- **D-49** Observabilidad 3 niveles (eventos / logs / metricas).
- **D-50** H-06 fix minimo: import redundante eliminado.

## Hallazgos honestos del ciclo

- **WI-14**: el claim inicial "el repr NO expone api_key" era FALSO.
  RED test revelo el dataclass auto-generado mostraba TODOS los campos.
  Leccion: claims de seguridad con tests que los verifiquen.
- **WI-16**: 4 claims del primer borrador del runbook eran incorrectos
  (schema column names, exit codes reales, sg runs logs API,
  audits/locks-*.md inexistente) — corregidos contra codigo real.

## Manifest del ciclo (testimonio durable)

```
v0.14.7 = 5b7e296 + dbf7cef (post-tag + state sync)
HEAD actual: dbf7cef
ahead of origin/main: 32 commits
push: PENDIENTE (regla WI-01: aprobacion operador)
```

## Compatibilidad

- 100% backward-compatible. Default `--adapter=fake` preserva los
  UAT fixtures (16/16 PASS). STRIDE S8 no cambia contratos. Backups
  son CLI read/write sobre data-root existente (sin migracion).

## Seguridad

- api_key nunca en logs (D-47).
- Backups sin cifrado (P3 deferred; recomendar gpg/age externo).
- HTTPS enforced por httpx en adapter HTTP.

## Pendiente para el siguiente ciclo (roadmap)

- **Deuda arquitectonica restante**: H-01 Storage god-class (2407 LoC),
  H-02 CLI god-module (2332 LoC), H-03 funciones cc>10, H-05 `_DummyStorage`,
  H-10 `locks.py` drift Windows.
- **P3 deferred (no bloquea release)**: redaction de Handoff antes de
  enviar al LLM, budget de tokens por tenant, cifrado en reposo,
  scheduling automatico de backups.

## Cierre del ciclo

- **release-receipt**: v0.14.7 (tag anotado, mensaje multi-linea
  coherente con v0.14.1..v0.14.6).
- **archive-manifest**: este archivo.
- **SDDK closure**: OK. El operador puede invocar `git push origin main`
  + `git push origin v0.14.7` cuando apruebe.
