# WI-82 — la evidencia UAT no puede ensuciar `git status`

- **Ciclo SDDK:** `p-b7740b96d79ec013/wi-82-evidence-write-idempotence`
- **Fecha:** 2026-10-02
- **BASE:** `6edd27f` (post-release `v0.16.11.dev0`)
- **Tipo:** `fix` → PATCH
- **Origen:** punto (e) de `STATE.yaml.roadmap.next_workitem`, medido en la
  sesión anterior y no ejecutado

## El síntoma

```
$ git checkout -- tests/uat-evidence/       # árbol limpio
$ mise exec -- uv run pytest tests/test_h4_expansion_cli.py -q
......                                        [100%]
6 passed in 4.42s
$ git status --porcelain
 M tests/uat-evidence/UAT-08.json
 M tests/uat-evidence/UAT-09.json
```

6 tests verdes y el árbol sucio. Repetido en cada commit del proyecto.

## El diagnóstico correcto

El diagnóstico de la sesión anterior («evidencia UAT autorreferencial:
`revision` no puede converger») era cierto pero **no era el defecto**. Era
una propiedad del dato, no un bug.

El defecto es otro: **`save_with_lock` escribe incondicionalmente**, así
que la suite reescribe dos ficheros versionados aunque su contenido sea
semánticamente idéntico. Todo el ruido viene de una sola línea volátil
en un payload determinista.

Medido sobre el diff real:

```diff
 {
   "uat_id": "UAT-08",
-  "revision": "b5446cd80fcaab8ae0ec9938b35819272f1c7633",
+  "revision": "6edd27f2c4245cb50bb504c76430dd0e72b8e3f6",
   "timestamp": "2026-09-23T11:00:00Z",
```

`timestamp` es fijo, `steps` es fijo, `status` es fijo, `notes` es fijo.

## Por qué `revision` no es un contrato

Medido, no supuesto:

1. **Ningún test comprueba `revision == HEAD`.** Todas las apariciones en
   `tests/` o bien monkeypatchean el valor, o bien lo usan como cadena
   opaca, o bien afirman que *sobrevive*.
2. `tests/test_uat_audit.py:143` afirma explícitamente lo contrario de lo
   que hacía el producto:
   ```python
   assert survived["revision"] == "must-survive", (
       f"--write UAT-08 sin --yes piso la evidencia: {survived}"
   )
   ```
   La evidencia persistida debe sobrevivir a una re-emisión sin cambio
   semántico. El producto hacía lo contrario.
3. `tests/uat_audit.py:1890` solo lo imprime (`rev = data.get("revision")
   [:12]`), en modo lectura.

**Y no puede converger por construcción**: un fichero versionado nunca
puede contener el SHA del commit que lo versiona. Siempre quedaría un
commit por detrás. Ese desfase no es información; es ruido.

## El fix

`tests/_evidence_lock.py`: `save_with_lock` acepta `volatile_keys`.

- Si el fichero existe y coincide con el payload **en todas las claves
  restantes**, no se reescribe.
- La comparación es sobre el **JSON parseado**, no sobre bytes: el orden de
  claves de un dict no es información; el de una lista sí, y por eso las
  listas se comparan tal cual.
- **Fail-open deliberado**: si el fichero no existe, no se puede leer o no
  es un objeto JSON, se escribe. Tragarse evidencia por una lectura fallida
  sería peor que el ruido que evita — el mismo criterio de
  `knowledge/git_source.py:365` («un dato plausible y falso es peor que un
  error»).
- `history_keep=True` **no cambia**: ahí el registro de cada ejecución es el
  propósito. La guarda solo aplica cuando no se pide historial, lo que deja
  intacto `uat_audit.py::_save_evidence`.

`tests/test_h4_expansion_cli.py`: los dos emisores declaran
`volatile_keys=("revision",)`.

## La red

`tests/test_wi82_evidence_write_idempotence.py` — 12 tests.

| Nivel | Test | Qué fija |
|---|---|---|
| unitario | `test_identical_payload_modulo_revision_does_not_rewrite` | el defecto exacto |
| unitario | `test_no_rewrite_preserves_mtime` | *no reescribir* ≠ *reescribir lo mismo*; la mtime lo distingue |
| unitario | `test_changed_payload_is_still_written` | la contraparte: un helper «idempotente» que se traga cambios reales sería peor que el defecto |
| unitario | `test_default_still_rewrites` | `uat_audit.py` no cambia de comportamiento |
| unitario | `test_volatile_keys_absent_from_existing_file` | fichero previo sin la clave |
| unitario | `test_volatile_keys_absent_from_new_payload` | clave volátil ausente en el payload no se introduce |
| unitario | `test_unreadable_existing_file_does_not_lose_evidence` | fail-open |
| e2e | `test_emitter_does_not_dirty_tracked_evidence[_emit_08/_09]` | el emisor real, con HEAD distinto, no toca el fichero |
| e2e | `test_emitter_writes_when_content_actually_changes[_emit_08/_09]` | si el contenido cambia de verdad, escribe |
| bloque | `test_suite_run_leaves_tree_clean` | delata el ruido antes de que llegue a un commit |

### Un error propio, encontrado y corregido en el rojo

La primera versión del test e2e usaba fixtures sintéticos y comparaba
contra el fichero versionado. **Pasaba por el motivo equivocado**: el
payload real del emisor depende de datos que solo existen en la corrida de
producción (los nombres de fichero del scratch de pytest, el `nodes_after`
real), así que el payload difería de verdad y el fichero se escribía — que
es el comportamiento correcto, no un fallo. Peor: `test_emitter_writes_when
_content_actually_changes[_emit_08]` pasaba porque cambiar solo `returncode`
**no** cambia el payload de UAT-08 (su `observed` fija `apply_rc=0`; usa
`apply.stderr`), de modo que el test no comprobaba nada.

Corregido en las dos direcciones: el e2e siembra en disco el payload que
el propio emidor produce con `revision` distinto (fase 1 → 2 → 3), y el
caso de «cambió de verdad» mueve los tres campos que ambos emisores usan
(`rc`, `stdout`, `stderr`).

## Mutaciones

`.pipelinek/wi82_mutate.sh` — 3/3 cazadas:

| # | Mutación | Resultado |
|---|---|---|
| M1 | `save_with_lock` vuelve a escribir siempre (se pierde la guarda) | 4 failed, 34 passed |
| M2 | los emisores dejan de declarar `revision` volátil | 2 failed, 36 passed |
| M3 | guarda presente pero decorativa (`return False` antes de comparar) | 4 failed, 34 passed |

M3 es la que importa: una guarda que se puede dejar sin que compare es
código muerto que aparenta proteger.

El script backing up y restaura con `cp`, y verifica con `diff -q` contra
el backup. **No** usa `git checkout --`, que restauraría HEAD y destruiría
el fix sin commitear — la lección de WI-81, que se llevó el fix por delante
en silencio.

## Verificación

```
$ mise exec -- uv run pytest -q
2388 passed in 100.25s (0:01:40)
$ git status --porcelain
(sin salida — solo los cambios intencionados)
```

Baseline 2376 + 12 nuevos = 2388. `ruff check` limpio, `ruff format`
limpio (242 ficheros).

## Criterios de aceptación

| # | Criterio | Estado |
|---|---|---|
| 1 | La suite no ensucia `git status` | **CUMPLIDO** — verificado sobre la suite completa, no solo el fichero afectado |
| 2 | Re-verificación idéntica no reescribe; distinta sí | **CUMPLIDO** — 12 tests, incluidas las dos contrapartes |
| 3 | La reintroducción de la escritura incondicional pone la red en rojo | **CUMPLIDO** — 3/3 mutaciones |
| 4 | Formato y lint | **CUMPLIDO** |
| 5 | Sin cambio de contrato de `uat_audit.py` | **CUMPLIDO** — `history_keep` intacto |

## Lo que este work item NO hace

- No elimina `revision` del esquema. Es parte del contrato de `Evidence` y
  la evidencia UAT sigue siendo legible por humanos.
- No toca `uat_audit.py::uat_08()` / `uat_09()`, que son los *stubs* BLOCKED
  deliberados (su evidencia real vive en los emisores de
  `test_h4_expansion_cli.py`).
- No introduce el fichero de evidencia UAT fuera de git. Es la decisión de
  diseño de STATE.yaml y no este work item el sitio para revisarla.

## Conocimiento negativo

- **`sddk release plan --tag v0.16.11` falla con `VERSION LOCKSTEP ERROR:
  could not read …/Cargo.toml`.** El plano de release de SDDK asume
  versionado Rust en lockstep. Por tanto **la ruta `release.complete` es
  estructuralmente inalcanzable** en este proyecto: exige `release-receipt`
  y `merge-receipt`, y el receipt solo lo emite `sddk release apply`. No es
  un gate pendiente de aprobación; es una ruta que no aplica a Python.
- **`sddk release apply --route local` pushea** trunk y tag. Queda fuera de
  lo que la consigna del operador pre-aprobó.
- Se corrige un recuento caducado en `STATE.yaml.next_workitem`: decía
  «6 ciclos en `RELEASE_PENDING`» y el ledger tiene **10** (`wi-72`..`wi-81`).
