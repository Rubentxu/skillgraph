# merge-receipt — absorbed cycles (wi-45, stored-claim, wi-40)

Cycle: multiple, see table below
Fecha: 2026-09-29

## Qué acredita este recibo

Tres ciclos quedaron en `RELEASE_PENDING` / `OPEN` porque en su
momento el release planner de SDDK exigía un `Cargo.toml` que este
proyecto Python no tiene (B1). Ninguno pudo producir sus receipts de
release en su día.

Lo que cambió no fue el runtime, sino que **su trabajo ya está
dentro de la release v0.16.8**, publicada y verificada. Este recibo
acredita esa pertenencia, no una publicación nueva: los tres commits
base son ancestros de `df72bcc`, que es el commit etiquetado y el que
está en `origin/main`.

| Ciclo | Estado previo | Commit base | ¿Base ancestro de `df72bcc`? |
|---|---|---|---|
| `wi-45-uow-coverage` | `RELEASE_PENDING` / release | `8ec0645`, `3237a94` | **sí, ambos** |
| `stored-claim-evidence-boundary` | `RELEASE_PENDING` / release | `dd4872a` | **sí** |
| `wi-40-test-connection-lifecycle` | `OPEN` / build | `ca96613` | **sí** |

## Verificación

```bash
$ git merge-base --is-ancestor 8ec0645 HEAD   && echo SI
SI
$ git merge-base --is-ancestor 3237a94 HEAD   && echo SI
SI
$ git merge-base --is-ancestor dd4872a HEAD   && echo SI
SI
$ git merge-base --is-ancestor ca96613 HEAD   && echo SI
SI
$ git rev-parse HEAD
df72bcc00bd5f3666f107a29cbe2c3300269a74f
$ git ls-remote origin refs/heads/main
df72bcc00bd5f3666f107a29cbe2c3300269a74f
```

Coherencia con la release: el work de `stored-claim-evidence-boundary`
no solo está incluido, sino que continuó después en `9992564`
(`refactor(storage): close claim and evidence dto boundary`), así que
el trabajo no quedó abandonado a medias.

## Lo que este recibo NO dice

- No dice que estos ciclos se liberaran por su cuenta el 2026-09-27 o
  el 2026-09-28. No lo hicieron: estaban bloqueados.
- No dice que el release planner de SDDK funcione para este proyecto.
  No funciona (B1), y este recibo existe precisamente porque se hizo
  la release por el camino manual.
- No reescribe el ledger. Los eventos históricos de estos ciclos
  siguen diciendo lo que dicen; lo que se añade es una transición
  nueva, gobernada, con su evidencia.
