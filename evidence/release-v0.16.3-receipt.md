# Release receipt — v0.16.3

| Campo | Valor |
|---|---|
| Tag | `v0.16.3` (anotada, `git cat-file -t` = `tag`) |
| SHA del release | `95d4c8a3ffb370877e384011e040a3a79ba4af6d` |
| `__version__` en el tag | `0.16.3` (SemVer puro) |
| `__version__` actual en HEAD | `0.16.3.dev0` (trabajo posterior a la etiqueta) |
| Tag anterior | `v0.16.2` |
| Commits incluidos | 15 |
| Suite completa | 1422 passed |
| Cobertura total | 95.98% |
| ruff check / format | limpios |
| Fecha | 2026-09-28 |

## SemVer derivado del historial (no decidido a mano)

Conteo real de `git log --format=%s v0.16.2..v0.16.3`:

| Tipo | Conteo | Efecto en SemVer |
|---|---|---|
| `fix` | 2 | PATCH |
| `refactor` | 1 | ninguno (sin cambio de contrato) |
| `docs` | 9 | ninguno |
| `chore` | 3 | ninguno |
| `feat` | 0 | — |
| breaking | 0 | — |

PATCH por `fix`. MINOR descartado por no haber `feat`; MAJOR descartado
por no haber breaking change.

## Contenido

- **`fix(backups)` (70b3b2c) — pérdida de datos silenciosa.** `create_backup`
  copiaba los `.sqlite` con `zf.write(src)`, una copia cruda de fichero. El
  proyecto abre sus conexiones en **WAL**
  (`PRAGMA journal_mode = WAL` en `platform/storage.py` y
  `resources/catalog.py`), así que los datos confirmados viven en el
  fichero `-wal`. La copia del fichero principal se llevaba **4096 bytes
  vacíos** y dejaba atrás los datos: `create`, `verify` y `restore`
  terminaban en éxito y el restore devolvía **cero filas**.

  El módulo ya tenía `_sqlite_backup_to` escrita y **nunca conectada** (sin
  ningún call site en `src/` ni en `tests/`). Ahora los `.sqlite` se
  consolidan con la API `.backup()` a un staging temporal antes de
  empaquetarse, y las instantáneas se toman antes de abrir el ZIP para que
  una base ilegible no deje un `.zip` a medias.

- **`fix(domain)` (ac0c985)** — un tipo desconocido dentro de una lista ya
  no aborta la validación, y `refactor(domain)` (6343a64) saca la
  comprobación de tipos del closure del validador.

- **WI-45** — `platform/uow.py` mantiene el **100%** de cobertura (94/94
  statements) tras el arreglo de las 7 delegaciones rotas.

## Verificación

- **Suite completa**: `1422 passed`, exit 0, `1214.65s`, ejecutada con el
  comando exacto del pipeline (`uv run pytest --no-header -q` con
  cobertura). El stage `unit-tests` de `pipelinek` **no** sirve como
  evidencia aquí: su clave de caché es el script y no el commit, así que
  puede reportar `success` sin ejecutar un solo test (ver
  `evidence/pipelinek-cache-does-not-invalidate-on-source-change.md`).
- **Cobertura**: total `95.98%`; `governance/backups.py` 81.59% → **94.14%**;
  `platform/uow.py` **100%**.
- **Regresión WAL end-to-end**: 501 filas confirmadas, restore **501/501**.
- **9 tests de regresión y de política** añadidos en `tests/test_backups.py`;
  31/31 pasan en ese módulo y 76/76 en el conjunto afectado y adyacente.
- **Gate de admisión de release**: `tests/test_release_governance.py`
  → `2 passed`.

## Ruta de release y bloqueos B1/B2

El camino completo `sddk release apply` sigue bloqueado:

- **B1** — `sddk release plan` exige un `Cargo.toml` en la raíz; este
  proyecto es Python puro.
- **B2** — `sddk release apply` exige `permissions.yaml` en la raíz del
  proyecto. **No es una carencia del framework**: el archivo es nuestro y
  su esquema se verificó experimentalmente
  (`evidence/permissions-registry-schema.md`).

La release se hizo por la vía honesta que ya usaron los ciclos cerrados:
commit del bump, **etiqueta anotada** creada con `git tag -a`, y
`__version__` alineado. La evidencia de que la autoridad de release
completa está bloqueada está en `evidence/b1-b2-diagnosis-correction.md`.

## Nota sobre la creación de la etiqueta

`sddk git tag --name v0.16.3` creó una etiqueta **lightweight** en su
primera invocación, y su `--help` no expone ningún flag de anotación (la
anotación solo aparece en el flujo completo de `sddk release`, que usa
`git tag -a`). Tras borrarla, una segunda invocación devolvió
`status: succeeded` **sin crear ninguna ref**, porque su política de
idempotencia da por hecho que la etiqueta ya existe.

Por eso la etiqueta definitiva se creó con `git tag -a`, que es lo que
hacen `v0.16.2`, `v0.16.1` y `v0.15.0` (todas `tag`, ninguna `commit`).
Un `succeeded` que no cambia el estado del repositorio es peor que un
error visible, porque el gate de release reporting no lo distingue.

## Deriva post-etiqueta y su corrección

El commit `b6bab77` (versionado de `BACKLOG.md` y de
`audits/architecture-debt-2026-09-28.md`) entró **después** de crear la
etiqueta. Eso dejó HEAD posterior a `v0.16.3` con la versión todavía
plana, y el gate lo rechazó con honestidad:

```
release governance drift: HEAD posterior a la etiqueta 'v0.16.3'
(HEAD = b6bab7703a55), pero __version__ = '0.16.3' no termina en .devN
```

La corrección fue un commit nuevo (`63cc244`) que restaura
`0.16.3.dev0` y sincroniza `STATE.yaml` y `CURRENT.md`. **La etiqueta no
se reescribe**: `v0.16.3` sigue anotada y sigue apuntando a `95d4c8a`.
Reordenar o reetiquetar habría reescrito provenance ya publicada, que
`AGENTS.md` prohíbe explícitamente.

## Publicación

`v0.16.3` está publicada **solo en local**, y eso es la consecuencia
directa de B1, no una decisión pendiente.

El push no es un human gate esperando permiso: es una **prohibición
estructural**. `prompts/sddk/phases/apply.md`, sección
`## Push Discipline (binding)`, establece que los agentes apply no
ejecutan `git push` de ninguna forma y que el push a `main` es
responsabilidad exclusiva de `sddk-release` (push-to-main). Ese es
justamente el flujo que B1 bloquea.

Lo que sí está verificado y limpio: worktree con 0 cambios, 36 commits por
delante de `origin/main`, sin divergencia, y el `pre-push` hook de SDDK
sin objections (solo bloquearía por closeout pendiente o fallo del ledger,
y ninguno de los dos se da).

Detalle completo en `evidence/b1-b2-diagnosis-correction.md`.
