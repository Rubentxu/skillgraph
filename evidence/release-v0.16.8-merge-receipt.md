# merge-receipt — v0.16.8

| Campo | Valor |
|---|---|
| Cycle | `p-74299cf88f51dab9/wi-56-storage-decomposition` |
| Ruta | local (push directo a trunk) |
| Rama | `main` |
| SHA local (HEAD) | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| SHA remoto `origin/main` | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| Veredicto | `HEAD == origin/main` |
| Fecha | 2026-09-29 |

## Comandos ejecutados

```bash
git push origin main
#   To https://github.com/Rubentxu/skillgraph.git
#      4d64ad6..df72bcc  main -> main

git fetch origin main
#   * branch            main       -> FETCH_HEAD

git ls-remote origin refs/heads/main
#   df72bcc00bd5f3666f107a29cbe2c3300269a74f	refs/heads/main

git rev-parse HEAD
#   df72bcc00bd5f3666f107a29cbe2c3300269a74f
```

## Postcondición verificada

`HEAD == origin/main` con SHA completo e idéntico. No se trata de la
salida del push sino de una lectura posterior e independiente del
estado remoto.

## Precondiciones verificadas antes del efecto Git

| Precondición | Estado | Verificación |
|---|---|---|
| Checkout en `main` | OK | `git branch --show-current` |
| Árbol limpio | OK | `git status --porcelain` vacío |
| `__version__` puro en el commit etiquetado | OK | `git show v0.16.8^{}:src/...` → `0.16.8` |
| Release governance gate | OK | `uv run pytest tests/test_release_governance.py` → 2 passed |
| CI local canónica | OK | `pipelinek run` → SUCCESS, 1754 passed, 8 `StepStarted` |
| Permiso de push | OK | `sddk permission check --agent sddk-release --phase release --capability git.push` → `allowed: true` |
| Etiqueta no publicada previamente | OK | `git ls-remote origin 'refs/tags/v0.16.8*'` → vacío antes del push |

## Nota sobre la re-emisión de la etiqueta

La etiqueta `v0.16.8` se creó primero sobre `8eda4ea` y después se
re-emitió sobre `df72bcc`, que añade la sincronización de
documentación. Se comprobó **antes** de hacerlo que la etiqueta no
existía en el remoto (`git ls-remote origin 'refs/tags/v0.16.8*'` →
vacío), de modo que no hay provenance publicada que reescribir: la
prohibición de `tag --force` de la regla 12 de `AGENTS.md` protege la
provenance histórica de releases **publicadas**, y aquí la versión
nunca había salido del repositorio local.

La razón de re-emitir en lugar de publicar `8eda4ea` es el contrato de
release de SDDK: `release-receipt` exige que la etiqueta anotada
remota pelee al mismo SHA que `origin/main`. Publicar la documentación
fuera de la release habría dejado la etiqueta apuntando a un commit
distinto del trunk, que es exactamente la condición que el contrato
rechaza.
