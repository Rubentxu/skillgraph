# Verificación WI-105 — los criterios de éxito del CI dejan de ser texto

- **Ciclo**: `p-b7740b96d79ec013/wi105-la-etapa-evidence-declara-y-no-comprueba`
- **Sesión**: `wi105-20261003T031000Z`
- **Fecha**: 2026-10-03
- **Release**: `v0.21.0` (MINOR, derivado con `scripts/derive_semver.py`)
- **Run que cierra**: `cd5124bb-d040-47dd-a617-cf06fff0b9ff`
  — 8/8 stages `success`, **2699 passed, 0 skipped**, 0 `StepFailed`,
  `VEREDICTO: todos los suelos declarados se cumplen`, árbol quieto.
- **SHA-256 de `.pipeline.kts`**: `7541ced5…dd42`. **Cambió respecto a
  WI-104** (`d8658968…3ddcc`), a propósito: es la etapa `evidence`.

---

## 1. El defecto, medido antes de tocar nada

`AGENTS.md` («CI Local Obligatorio») enumera **seis** criterios que un run
«debe cumplir». No los comprobaba ninguna herramienta.

La etapa `evidence` era el único sitio de la receta que tocaba
`.pipelinek/`, y eran tres comandos:

```
ls -la .pipelinek/db.sqlite
test -d .pipelinek/control/last-run  && echo 'last-run present'
test -d .pipelinek/control/workspace && echo 'workspace tracking present'
```

Los tres operandos los crea el motor **antes** de la etapa, así que los tres
pueden imprimir `present` y ninguno puede fallar. Medido contra el journal
real de este repo:

```
runs por veredicto: {'failure': 3, 'success': 12}
runs con StepFailed: [('9dd18e16', 1), ('8adb8929', 1), ('7d68ca93', 1)]
```

Las tres comprobaciones de la etapa dicen exactamente lo mismo en los
**quince** runs, incluidos los tres que terminaron en `failure`. Es la forma
de WI-101 —una etapa que certifica sin ejecutar la comprobación— aplicada al
registro del propio CI.

El alcance era mayor: el único criterio citado en algún sitio era el 1, con
un `grep` sobre el stdout en `scripts/hooks/pre-push:89` — hook no
instalado, y cuyo `grep` ya se comió esa cadena exacta una vez en la historia
del repo.

## 2. Lo que se comprueba, y lo que se declara que no

`scripts/check_pipeline_receipt.py` verifica los criterios **1 a 5**, que son
propiedades del journal y del árbol. El **6 no se automatiza** y se declara:
es el SHA-256 «registrado en la sesión», y una sesión es del agente, no del
repo. Meterlo en el script habría sido la misma mentira que el script viene a
arreglar.

## 3. El contraejemplo que manda

No es el run rojo. Es el run **verde que no ejecutó nada**. `AGENTS.md` lo
describe con sus palabras —«sin `--rerun`, un run cuyo script no ha cambiado
reutiliza el veredicto previo y termina en `Pipeline finished with SUCCESS`
sin ejecutar un solo step»— y el criterio 2 existe para separarlo de una
verificación real. Era el único modo de fallo que nada distinguía.

Las dos mitades del criterio 2 tienen **códigos distintos** a propósito: un
run sin pasos no es lo mismo que un run que ejecutó pasos pero no emitió el
resumen de pytest. Con un solo código, el segundo diría «veredicto
cacheado», que es mentira (mutación M6).

## 4. El huevo y la gallina, y cómo lo resuelve el motor

La receta no puede verificar su propio run: cuando la etapa `evidence` corre,
el run en curso todavía no tiene `RunFinished`. La propiedad es real, no una
excusa. El motor la resuelve solo: **`RunFinished` más reciente es, durante un
run, el run anterior**.

Comprobado en la certificación: la etapa ejecutada dentro de
`cd5124bb` dijo

```
OK: el run cumple los criterios que declara AGENTS.md.
    run 4f407df9-c8f5-40df-a700-82f3739bb858: 8/8 etapas, 11 pasos, veredicto 'success'.
```

`4f407df9` es el run de cierre de WI-104, no el propio. El mismo script con
`--run-id` verifica uno concreto.

## 5. Un detalle de instrumento costó una medición entera

El `payload` del journal es una **lista JSON con un dict dentro**, no un
objeto. `json_extract(payload, '$.outcome')` devuelve `NULL` sobre ese
schema, y leerlo por la ruta de objeto daba `None` en los **15**
`RunFinished`: el run más sano del repo habría salido como `failure`.

El síntoma —un `None` silencioso en 15 filas— parece un dato, no un fallo. Un
instrumento que no abre el contenedor no mide lo que cree medir.

## 6. Mutaciones: 7/7 a la primera

`.pipelinek/wi105_mutate.sh` + `wi105_muts/m1..m7.py`, autocontrolado (backup
byte a byte, trap, sha256 verificado al salir).

| mutación | degradación | quién la detectó |
|---|---|---|
| M1 | el verificador devuelve siempre `()` | el contraejemplo del run cacheado |
| M2 | desaparece la comprobación del run cacheado | el contraejemplo del run cacheado |
| M3 | desaparece la de `StepFailed` | `test_un_step_failed_falla_aunque_el_run_diga_success` |
| M4 | el control root deja de comprobarse | `test_falta_uno_de_los_cuatro` |
| M5 | el error no dice qué path falta | `test_nombra_cual_falta` |
| M6 | las dos mitades del criterio 2 se funden | `test_el_verde_sin_pasos_y_el_verde_sin_resumen_se_distinguen` |
| M7 | la receta deja de invocar el checker | **C5 de WI-102**, sobre el fichero real |

**No hizo falta la segunda pasada de WI-104.** La diferencia está en cómo
están escritos los tests: cada uno exige el **código** del problema, no solo
que la lista no esté vacía. Exigir solo «hay problemas» es exactamente lo que
dejó pasar a tres contraejemplos en WI-104, que pasaban por la rama
equivocada.

M7 es la contrapueba que hace este bloque distinto: degrada la **conexión**
sobre el `.pipeline.kts` real, y lo que debe morder ahí es C5 de WI-102, no
un test de este bloque.

## 7. El orden del release, que WI-104 cobro al revés

`release.releases[0].sha` va **vacío** en el commit de release y se rellena en
el post-release, porque **en el commit de release la etiqueta todavía no
existe**. En WI-104 la etiqueta se registró después del commit y
`test_every_semver_tag_is_listed_exactly_once` la atrapó: `1 failed, 2683
passed`.

El campo `sha` admite un SHA o vacío y **nunca prosa**: `PENDIENTE` lo
rechaza `test_sha_field_never_holds_prose`.

## 8. Cifras finales

- **2699 passed, 0 skipped** (+15 sobre 2684).
- Cobertura global **95.22 %**; `cli/` 86.91 %; `runtime/` 97.98 %.
- SemVer **MINOR** derivado: `derive_semver.py` → «la regla pide MINOR ->
  v0.21.0» (1 `feat`, 1 `docs`, 0 `fix`, 0 breaking).
- `ruff check src tests scripts` y `format --check` verdes.

## 9. Lo que NO se comprueba, declarado

El **criterio 6**: el SHA-256 del `.pipeline.kts` «registrado en la sesión».
Es una acción del agente, no una propiedad del journal. Sigue siendo del
agente, y ahora está dicho en el propio `AGENTS.md` y en la salida del script.

Sin push: 138 commits sin publicar, `origin/main` en `0ebbd58`. Push no
autorizado.
