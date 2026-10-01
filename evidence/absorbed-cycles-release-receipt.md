# release-receipt — absorbed cycles (wi-45, stored-claim, wi-40)

Fecha: 2026-09-29

## Qué es (y qué no es) este recibo

La release que respalda a estos tres ciclos es **v0.16.8**. No hay una
publicación nueva: los tres trabajos ya estaban dentro de ese rango y
salieron con él.

| Campo | Valor |
|---|---|
| Tag que respalda a los tres ciclos | `v0.16.8` |
| Objeto de etiqueta remoto | `2afe78ea93afdae4b499e414fe0aa2ecb22aef82` |
| Peel remoto | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| `origin/main` | `df72bcc00bd5f3666f107a29cbe2c3300269a74f` |
| Tipo de release | PATCH (0 `feat`, 0 `fix`, 0 breaking en `v0.16.7..df72bcc`) |
| Verificación | 1754 passed, ruff limpio, release governance gate 2 passed |

## Por qué estos tres ciclos se cierran ahora

Los tres estaban bloqueados por el mismo motivo: el release planner de
SDDK (`sddk release plan`) lee la versión de un `Cargo.toml`, y este
proyecto es Python con su versión en
`src/skillgraph/__init__.py:__version__`. Sin `Cargo.toml` no hay
release plan, y sin release plan no había receipts.

La release v0.16.8 se resolvió por el camino manual documentado. Al
existir una release publicada y verificada que contiene el trabajo de
los tres, sus receipts pueden apuntarse a esa release real en lugar de
a una afirmación.

Evidencia de pertenencia, commit por commit:

```bash
$ for c in 8ec0645 3237a94 dd4872a ca96613; do
    git merge-base --is-ancestor $c HEAD && echo "$c dentro de v0.16.8"
  done
8ec0645 dentro de v0.16.8      # WI-45: boundary de UoW
3237a94 dentro de v0.16.8      # WI-45: segundo commit
dd4872a dentro de v0.16.8      # stored-claim-evidence-boundary
ca96613 dentro de v0.16.8      # WI-40: fixtures de cierre de conexión
```

## Estado de la evidencia por ciclo

### `wi-45-uow-coverage`

Trabajo: cobertura de `platform/uow.py` al 100%, con
`tests/test_wi45_uow_delegation.py` (37 tests) que ejercita la
delegación real contra `Connection` en memoria, sin mocks. Verificado
en su día: 1455 passed en la base v0.16.5.

Complicación registrada: el ledger de este ciclo referencia la rama
`feat/wi-45-uow-coverage`, que nunca existió en el evento inmutable
`cycle.created`. El ledger es append-only, así que **no se corrige**
(sigue siendo B3). La transición que se registra ahora no depende de
esa rama.

### `stored-claim-evidence-boundary`

Trabajo: cierre del límite DTO de claims y evidences. Además de estar
incluido, **continuó** en `9992564`, así que no quedó a medias.

### `wi-40-test-connection-lifecycle`

Trabajo: `storage_cleanup` y `sqlite_cleanup` como fixtures `autouse`
en `tests/conftest.py`, para que el cierre de conexiones sea propiedad
de la suite y no disciplina por fichero, más 8 tests guardianes en
`tests/test_wi40_storage_leak.py`.

Este ciclo estaba en `OPEN`/`build`, no en release, y su receipt de
implementación citaba un `pipelinek SUCCESS`. Ese verde **no se cita
aquí como evidencia**: por la regla que este mismo repositorio fijó en
v0.16.5, un `SUCCESS` sin `StepStarted` en el journal es un cache hit
que no ejecutó tests. La evidencia que se usa es la del run genuino de
la release v0.16.8.

## Honestidad del cierre

Estos ciclos se cierran **absorbidos** en una release posterior, no
liberados en su momento. La diferencia importa:

- Su trabajo no se perdió: está en el árbol, en el historial y en el
  remoto.
- Sus receipts de release se emiten hoy, no se emitieron entonces.
- El ledger conserva los eventos antiguos que registran el bloqueo,
  incluida la rama inexistente de B3.
