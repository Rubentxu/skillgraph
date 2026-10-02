# WI-74 — Especificación y diseño: `STATE.yaml` no puede volver a mentir

> Ciclo `p-b7740b96d79ec013/wi-74-state-release-drift`, fases Specify,
> Design y Plan. Explorado en `evidence/sddk-wi74-exploration-2026-10-02.md`.
> Base: `da1d7a5`.

## El problema, en una frase

`STATE.yaml` es el punto de recuperación durable del proyecto y su
sección de releases contiene **cuatro SHA que no existen en el repo**,
dos que apuntan al commit equivocado, tres entradas con prosa en un
campo `sha`, dos releases sin registrar y un `release.tag` dos versiones
atrás. Y no hay ninguna red que lo detecte.

## Requisitos

- **REQ-WI74-1** (reconciliar): tras el corte, cada entrada de
  `release.releases` tiene el SHA que git dice para esa etiqueta, y cada
  SHA resuelve a un commit real (`git cat-file -e <sha>^{commit}`).
- **REQ-WI74-2** (sin perder el pasado): donde el valor antiguo **no
  resolvía**, se conserva la constancia de que no resolvía, separada del
  campo `sha`. No se borra el dato histórico ni se inventa uno nuevo.
- **REQ-WI74-3** (prosa fuera del campo `sha`): las tres entradas con
  texto descriptivo lo llevan en un campo aparte; `sha` contiene un SHA
  o nada.
- **REQ-WI74-4** (exhaustividad): `release.releases` lista **todas** las
  etiquetas SemVer de git, sin inventar ninguna, y `release.tag` es la
  más reciente.
- **REQ-WI74-5** (la red, que es la parte durable): un test ata
  `STATE.yaml` a `git tag` con **igualdad exacta**, sin márgenes ni
  tolerancias. Es el análogo de `tests/test_audit_debt_accuracy.py`,
  que ya hace esto para la prosa del audit de deuda.

## No objetivos

- No se reescribe historia ni se recrea ninguna etiqueta. AGENTS.md §12
  prohíbe `tag --force` sobre etiqueta publicada, y esa prohibición se
  extiende a "arreglar" el pasado.
- No se toca la divergencia de `v0.7.1` (local `8b63db6` vs remoto
  `b0476c2`): es histórica, ya reportada, y requiere `tag --force`.
- No se cambia `__version__` (ya correcto) ni el gate de release.
- No se audita el resto de `STATE.yaml` más allá de la sección de
  releases: el objetivo es cerrar el gap documentado, no rehacer el
  documento entero.

## Diseño de la red

`tests/test_state_release_integrity.py`, con:

| Test | Qué ata |
|---|---|
| `test_release_tag_is_the_latest_semver_tag` | REQ-4, primera mitad |
| `test_every_semver_tag_is_listed_exactly_once` | REQ-4, exhaustividad y no duplicados |
| `test_no_invented_tags` | REQ-4, no hay entradas fantasma |
| `test_every_listed_sha_resolves_to_a_real_commit` | REQ-1, el hallazgo grave |
| `test_every_listed_sha_matches_its_tag` | REQ-1, el valor correcto |
| `test_sha_field_never_holds_prose` | REQ-3 |
| `test_unresolvable_old_shas_are_recorded_as_such` | REQ-2, el pasado no se pierde ni se disimula |

El test compara con git, no con un fichero de constantes: si mañana se
publica `v0.16.11` sin registrarlo, `test_every_semver_tag_is_listed_exactly_once`
falla solo. Esa es la diferencia entre una foto y una red.

### Verificación en ambos sentidos

- Bajar `release.tag` a `v0.16.8` → falla el test de la última etiqueta.
- Borrar la entrada de `v0.16.10` → falla el de exhaustividad.
- Poner un SHA inventado en cualquier entrada → falla el de resolución.
- Poner `"nota descriptiva"` en `sha` → falla el de prosa.
- Quitar la constancia de los SHA antiguos que no resolvían → falla
  REQ-2, y ese test es el que impide "limpiar" el pasado en silencio.

## Plan

1. Red en rojo (los siete tests de la tabla).
2. Reconciliar `STATE.yaml`: `release.tag`, las dos releases ausentes,
   los nueve SHA, las tres prosa, y la constancia de los cuatro
   irrecuperables.
3. Verde, las cinco mutaciones de la tabla, suite completa.
4. `fix(state)` + `test`, CI canónica, cierre del ciclo.
