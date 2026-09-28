# Release receipt — v0.16.4

| Campo | Valor |
|---|---|
| Tag | `v0.16.4` (anotada) |
| `__version__` en el tag | `0.16.4` (SemVer puro) |
| `__version__` actual en HEAD | `0.16.4.dev0` (trabajo posterior a la etiqueta) |
| Tag anterior | `v0.16.3` (peel `95d4c8a`) |
| Commits incluidos | 11 |
| Suite completa | 1431 passed |
| `governance/backups.py` | 94.14% → 95% |
| Release governance gate | 2 passed |
| Fecha | 2026-09-28 |

## SemVer derivado del historial (no decidido a mano)

Conteo real de `git log --format=%s v0.16.3..HEAD`:

| Tipo | Conteo | Efecto en SemVer |
|---|---|---|
| `fix` | 1 | PATCH |
| `refactor` | 1 | ninguno (sin cambio de contrato) |
| `docs` | 6 | ninguno |
| `chore` | 2 | ninguno |
| `feat` | 0 | — |
| breaking | 0 | — |

PATCH por `fix`. MINOR descartado por no haber `feat`; MAJOR descartado
por no haber breaking change.

## Contenido

### `fix(audit)` (b1894ed) — la auditoría afirmaba deuda que ya no existe

La sección de recomendaciones de `audits/audit_debt.py` estaba escrita a
mano con cifras congeladas, mientras las tablas automáticas del mismo
informe se calculaban del árbol AST. El resultado era un documento que se
contradecía a sí mismo:

| Función | Afirmado | Medido |
|---|---:|---:|
| `main` (runner.py) | cc=43, 58 LoC | **cc=5, 29 LoC** |
| `cmd_run` (runner.py) | cc=22, 122 LoC | **cc=6, 34 LoC** |
| `_make_schema_validator` (pack_loader.py) | cc=22, 77 LoC | **cc=13, 70 LoC** |

Los tres P0 fueron refactorizados en WI-23..WI-27; la lista escrita a
mano sobrevivió a los refactors. P1 también estaba desfasado en ambos
sentidos: `storage.py` no tenía 2407 LoC sino 2837, y `runner.py` no
tenía 2477 sino 2248.

El defecto de fondo no era el documento: `test_audit_debt_smoke` exigía
literalmente el texto obsoleto (`assert "main" in text, "falta mencion de
main() cc=43"`), de modo que **la suite blindaba la mentira** y ninguna
regeneración podía corregirla.

Ahora las recomendaciones se derivan de la medición (P0..P4), y
`tests/test_audit_debt_accuracy.py` ata cada cifra citada a la cc medida
en `src/`. El informe regenerado declara 0 hotspots públicos cc≥20 con
máximo público medido 14.

### `refactor(backups)` (f9099aa) — la política de respaldo, por fin aislada

Con la auditoría ya honesta, el hotspot real era `_collect_files` con
cc=14, la función privada más compleja de `backups.py` y también la que
decide qué datos entran en un backup. Se extraen dos helpers con una
regla cada uno:

- `_collect_project_dbs`: recorre `tenants/<t>/projects/<p>/`. El conteo
  va por directorios y la inclusión por bases existentes: un proyecto sin
  `project.sqlite` cuenta como proyecto pero no aporta fichero.
- `_collect_agent_files`: la regla "los fixtures de agente son datos,
  `__pycache__` no".

`_collect_files` queda como composición: cc 14 → 3. Sin cambio de
comportamiento observable — mismo orden, mismo conteo, mismos ficheros —
y los 10 tests de round-trip, restore y WAL siguen verdes.

Cobertura de `backups.py` 94.14% → 95%: los helpers nuevos se cubren con
tests que no dependen de crear un backup entero.

## Verificación

- `uv run pytest tests/` — **1431 passed** (644.38s con cobertura).
- `tests/test_backups.py` — 37 passed (6 nuevos), 10 de ellos de
  round-trip / restore / WAL.
- `tests/test_audit_debt_accuracy.py` + `test_audit_debt_smoke.py` — 9 passed.
- `tests/test_wi40_audit_annals.py` — 4 passed (el marcador append-only se
  conserva intacto).
- `tests/test_release_governance.py` — 2 passed.
- `uv run ruff check` y `uv run ruff format --check` — limpios.

### Falsificación del gate nuevo

Reinyectar la mentira antigua en `audit_debt.py` hace fallar el test con
el valor real al lado:

```
main: prosa afirma cc=43, medido cc=5 (ya refactorizado)
```

El gate funciona: no es una aserción decorativa.

## Ruta de release y bloqueos B1/B2

El camino completo `sddk release apply` sigue bloqueado:

- **B1** — `sddk release plan` exige un `Cargo.toml` en la raíz. Re-verificado
  el 2026-09-28 con el binario actual: `strings $(which sddk) | grep -c
  pyproject` → **0**. No existe ninguna rama de código que sepa leer un
  manifiesto Python, y el lockstep se evalúa antes de elegir ruta, así que
  `--route local` no lo evita:

      VERSION LOCKSTEP ERROR: could not read <root>/Cargo.toml

  No es corregible desde este repositorio: requiere un cambio en el
  framework.

- **B2** — resuelto en `00e4012` con `permissions.yaml`.

- **B3** — el ledger del ciclo registra una rama (`feat/wi-45-uow-coverage`)
  que nunca existió en el evento inmutable `cycle.created`. Crear la rama no
  arregla el gate y editar el ledger append-only está prohibido.

## Secuencia de versión respetada

El gate de gobernanza rechazó el primer intento, correctamente: con HEAD
sin etiquetar y `__version__ = "0.16.4"` puro, el estado es exactamente
la deriva que §12 prohíbe. La secuencia correcta es commit con
`0.16.4.dev0` y la etiqueta en el commit de release, que es lo que se
aplicó.
