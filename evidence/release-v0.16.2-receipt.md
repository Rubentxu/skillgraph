# Release receipt — v0.16.2

| Campo | Valor |
|---|---|
| Tag | `v0.16.2` (anotada) |
| SHA | `92e06f3e3c78e727de057d965f09305636e58762` |
| `__version__` | `0.16.2` (SemVer puro) |
| Tag anterior | `v0.16.1` |
| Commits incluidos | 18 |
| Suite completa | 1375 passed |
| ruff check / format | limpios |
| Fecha | 2026-09-27 |

## SemVer derivado del historial (no decidido a mano)

| Tipo | Conteo | Efecto en SemVer |
|---|---|---|
| `fix` | 5 | PATCH |
| `refactor` | 4 | ninguno (sin cambio de contrato) |
| `docs` | 3 | ninguno |
| `chore` | 3 | ninguno |
| `feat` | 0 | — |
| breaking | 0 | — |

PATCH por `fix`; MINOR y MAJOR descartados por no haber `feat` ni
breaking change.

## Contenido

- **WI-45** — las 7 delegaciones de `SqliteUnitOfWork` estaban rotas: cada
  una era un método inexistente o una keyword incompatible con la firma
  real de `Storage`. Dos guardas AST lo impiden de regresión.
  `platform/uow.py` 71% → 100% (94/94 statements).
- **WI-46** — un `bool` atravesaba la validación `integer`/`number`
  (`isinstance(True, int)` es `True`). `_check_list` no validaba ningún
  elemento cuando `elem_type` no era `string`.
- **WI-47** — las excepciones se clasifican por tipo. Un error de dominio
  con `FOREIGN KEY` en el mensaje ya no se reporta como `UnknownSourceError`.
  Los fallos de I/O ya no se disfrazan de "no hay datos", y un repo git roto
  ya no se reporta como working tree limpio. Tres guardas AST, dos de ellas
  falsificadas contra los bugs que persiguen.
- **CI** — `.pipeline.kts` estaba sin trackear en `.gitignore` y usaba
  `$REPO_ROOT`, que `pipelinek` v0.39.0 no define.

## Blockers de `sddk release` y como se resolvieron HONESTAMENTE

| Id | Blocker | Estado |
|---|---|---|
| B1 | `sddk release plan` exige `Cargo.toml` (VERSION LOCKSTEP) | **VIGENTE en SDDK 2.0.1** |
| B2 | `sddk release apply` exige `permissions.yaml` | **VIGENTE en SDDK 2.0.1, pero NO es un defecto del framework** |

Ambos se verificaron **ejecutando el comando real**, no leyendo strings:

```
$ sddk release plan --tag v0.16.2
error: VERSION LOCKSTEP ERROR: could not read .../Cargo.toml: No such file or directory
```

El binario `sddk` 2.0.1 contiene 3 referencias a `Cargo.toml`, 2 a
`permissions.yaml` y **0 a `pyproject.toml`**. Son límites de un framework
escrito en Rust.

> **CORRECCIÓN 2026-09-28 (B2).** La conclusión de abajo era falsa.
> `permissions.yaml` **no lo provee el framework**: es un archivo del
> proyecto, en la raíz del repositorio. El propio binario lo dice
> (`create permissions.yaml at the repository root with an 'agents'
> mapping`) y la ruta del error es el cwd del repo, no `$FRAMEWORK`.
> Buscarlo dentro del framework no podía encontrarlo. La tabla de arriba
> decía "VIGENTE", y es cierto que el comando falla, pero la clasificación
> como límite del framework no lo es: se arregla declarando el registro en
> este repositorio. Ver `evidence/b1-b2-diagnosis-correction.md`.

**No se fabricó ningún artefacto** (ni `Cargo.toml`, ni `permissions.yaml`,
ni receipts, ni manifiestos) para sortearlos. En su lugar se usó la
superficie gobernada `sddk git tag`, que **no** exige lockstep de versión:

```
$ sddk git tag --name v0.16.2
capability: git.tag
status: succeeded
result: {"tag":"v0.16.2"}
```

La etiqueta se recreó después como **anotada**, para respetar la convención
de las etiquetas previas del repo (`v0.15.0`..`v0.16.1` son todas `tag`,
ninguna ligera). Fue una etiqueta **local y nunca publicada**, así que
borrarla y recrearla no reescribe provenance: el SHA es el mismo antes y
después, y no se usó `--force` sobre ninguna etiqueta publicada.

## Estado del release gate

`tests/test_release_governance.py` es el admission gate (AGENTS.md 12).
Traza observada, en orden:

1. Con `0.16.1.dev0` sobre `v0.16.1`: **2 passed** (rama 2, trabajo entre
   releases).
2. Tras el bump a `0.16.2` sin etiqueta: **1 failed** — `__version__` puro
   con HEAD no etiquetado. El gate bloquea correctamente.
3. Creada la etiqueta `v0.16.2`: **2 passed** (rama 1, release limpia).

## Pendiente de decisión del operador (regla 5)

Push al remote. La rama acumula 19 commits sin publicar y el tag `v0.16.2`
es local. No se hizo push.
