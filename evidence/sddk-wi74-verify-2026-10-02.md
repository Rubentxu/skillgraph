# WI-74 — Informe de verificación

> Ciclo `p-b7740b96d79ec013/wi-74-state-release-drift`, fase Verify.
> Implementación en `b5446cd`. Base: `da1d7a5`.

## 1. Requisitos uno a uno

| Requisito | Verificación | Resultado |
|---|---|---|
| REQ-1 reconciliar | `test_every_listed_sha_resolves_to_a_real_commit`, `test_every_listed_sha_matches_its_tag` | PASS, 35 SHA corregidos |
| REQ-2 sin perder el pasado | `test_unresolvable_old_shas_are_recorded_as_such` | PASS, 4 constancias |
| REQ-3 prosa fuera de `sha` | `test_sha_field_never_holds_prose` | PASS, 3 mudadas a `nota` |
| REQ-4 exhaustividad | `test_release_tag_is_the_latest_semver_tag`, `test_every_semver_tag_is_listed_exactly_once`, `test_no_invented_tags` | PASS, 37/37 |
| REQ-5 la red | §3 | PASS, 8 tests |

## 2. Estado después del corte

| Métrica | Antes | Después |
|---|---:|---:|
| `release.tag` declarado | `v0.16.8` | **`v0.16.10`** |
| releases listadas | 35 | **37** |
| tags ausentes | 2 | **0** |
| tags inventados | 0 | **0** |
| tags duplicados | (no medido: el probe usaba un dict) | **0** |
| SHA que no resuelven | **4** | **0** |
| SHA que no coinciden con su tag | 9 | **0** |
| prosa en el campo `sha` | 3 | **0** |
| líneas del documento | 1288 | 1311 |
| comentarios conservados | 156 | **156** |

## 3. La red, y por qué es la parte que importa

Ocho tests que atan `STATE.yaml` a `git tag` con **igualdad exacta**.
Es el análogo de `tests/test_audit_debt_accuracy.py`, que ya hace esto
por la prosa del audit de deuda; el estado no tenía nada equivalente.

La diferencia entre una foto y una red se ve en el caso normal: si mañana
se publica `v0.16.11` y no se registra, falla **solo**, sin que nadie
tenga que acordarse de mirar.

Cinco mutaciones, cada una detectada por su test:

| # | Mutación | Test que la caza |
|---|---|---|
| M1 | `release.tag` bajado a `v0.16.8` | `test_release_tag_is_the_latest_semver_tag` |
| M2 | entrada de `v0.16.10` borrada | `test_every_semver_tag_is_listed_exactly_once` |
| M3 | SHA inventado | `test_every_listed_sha_matches_its_tag` |
| M4 | prosa en `sha` | `test_sha_field_never_holds_prose` |
| M5 | borrada la constancia del pasado | `test_unresolvable_old_shas_are_recorded_as_such` |

M5 es la que no es obvia: impide la forma más silenciosa de "arreglar"
el estado, que es sustituir los SHA rotos por los correctos y borrar el
rastro. El documento quedaría más limpio y más falso.

## 4. Método: quirúrgico, y por qué el round-trip se abandonó

El primer intento serializaba `STATE.yaml` con `yaml.safe_dump`. Se
abandonó **sin ejecutarlo**: el documento son 1288 líneas con 156
comentarios que explican el *por* de cada decisión, y un round-trip por
el parser los habría destruido todos, además de reformatear el fichero
entero. La reconciliación final es a nivel de texto, con
`git rev-list -n 1 <tag>` como única fuente.

El diff resultante toca `tag`, `sha`, las tres prosa, las cuatro
constancias y las dos releases nuevas. Nada más.

## 5. Dos errores míos, los dos cazados por la red

1. **La primera reconciliación cayó en mitad de una entrada.** Buscaba
   "el final de la lista" retrocediendo desde la última línea `- tag:`,
   que no es un ancla fiable. Dejó campos huérfanos y un test falló con
   un SHA que no era el de la etiqueta. El ancla correcta es
   `capacidades_entregadas:`, una clave de nivel superior.
2. **El primer probe de drift usaba un `dict` indexado por tag.** Una
   entrada duplicada se sobrescribía en silencio (last-writer-wins), así
   que el probe reporting "0 inventadas" no veía el problema. El test
   de duplicados cuenta sobre la lista, no sobre el dict.

## 6. Lo que este workitem NO hace

- No reescribe historia. Los cuatro SHA irrecuperables se sustituyen
  por el real y se conserva la constancia; no se "arreglan" inventando.
- No toca la divergencia de `v0.7.1` (prohibido `tag --force`).
- No audita el resto de `STATE.yaml`. El objetivo era cerrar el gap
  documentado, no rehacer el documento entero.
- Sin código de producto, luego **sin ADR** y commit `fix(state)`.

## 7. Deuda restante

El frente P3 está agotado: 4 candidatas, ninguna con cc alto. Queda
pendiente de decisión del operador (a) si se abre frente para el punto
ciego del audit (`list_file_signatures_for_source`, cc 10 con 58 LoC) y
(b) la aprobación de cierre de los tres ciclos SDDK abiertos.

## 8. Verificación de gobernanza

`Pipeline finished with SUCCESS`, runId `7d13676d`, 7 `StepStarted`,
7 `StepFinished`, 5/5 `StageFinished` en `success`, 0 `StepFailed`,
`2223 passed in 90.67s` capturado en `EchoOutputCaptured`. Binario
`0.39.0`. `.pipeline.kts` sin drift.
