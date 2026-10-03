# WI-110 — la etapa `evidence` se exculpa a sí misma y la cadena vuelve

- **Fecha**: 2026-10-03
- **Ciclo SDDK**: `p-b7740b96d79ec013/wi110-evidence-recuperable` (path `A-full`)
- **Release**: `v0.22.1` (PATCH)
- **Serie**: «¿qué declara el repo que nada comprueba?», duodécima vía
- **Commits**: `eae8e59` (código), `ccfb182` (trazabilidad),
  `7b2068f` (release + tag), `ac92bde` (post-release)

---

## 1. Por qué esta vía es distinta de las once anteriores

Las once anteriores cerraron una propiedad que el repo declaraba y nada
comprobaba. Esta cierra **el aparato que comprueba**. La etapa `evidence`
de `.pipeline.kts` se verificaba a sí misma, y una vez fallada ningún
run volvía a terminar en `Pipeline finished with SUCCESS`.

Un instrumento que no puede volver a dar verde no mide nada a partir del
momento en que se pone rojo.

## 2. La medición, antes de tocar nada

Instrumento: `.pipelinek/wi110_measure.py`. **No muta el árbol**, porque
`evaluar()` es pura sobre `InformeRun` y su docstring lo declara.

### M1 — la propiedad del deadlock, con sonda

```
run sano                        -> []
run con 1 StepFailed            -> ['sg_pipeline_run_failure',
                                     'sg_pipeline_step_failed']
sonda: los dos informes (fallo-de-evidencia y fallo-de-codigo)
       son indistinguibles para la funcion: True
```

**CAZADA.** Un run que falló solo en su etapa de evidencia es rechazado
por el **mismo** criterio que rechaza un fallo de código.

### M2 — por qué no podía distinguirlos

```
campos que mira: outcome, step_failed, steps_iniciados,
                resumen_pytest, digest
¿mira el NOMBRE del paso que fallo?: False
```

`step_failed` es un **contador**, y un contador no sabe quién falló.

### M3 — la consecuencia, sobre el journal REAL

```
fecha     run       etapas codigo   veredicto
03:48:17  8d6a9594  7/7 OK  success   evidence=success   <- último verde
04:26:49  e722fe84  2/2     failure
04:35:23  16251236  7/7 OK  failure
04:40:51  da0203d9  2/2     failure
04:49:20  a6c81d08  7/7 OK  failure
05:26:52  234d7817  7/7 OK  failure
05:31:46  b774ad14  7/7 OK  failure
05:37:28  bf2a8e23  7/7 OK  failure
```

**Cinco runs consecutivos** con las siete etapas de código en `success`
y ninguno se recuperó. Un fallo ya corregido —el `package_version` que
el post-release dejó atrás— no devolvía la cadena a verde: dejaba de
estar en el código pero seguía en el veredicto.

## 3. La medición desmintió el diagnóstico del bloque anterior

WI-109 escribió que arreglar esto exigía tocar `.pipeline.kts` y lo
descartó por eso, nombrándolo como la única vía. **Era medio verdad.**

El criterio no vive en la receta. La etapa se limita a invocar
`scripts/check_pipeline_receipt.py` y a propagar su exit code
(`.pipeline.kts:135`); la decisión —qué es «este run cumple»— está
entera en `evaluar()`.

Por tanto el arreglo **no toca un byte de la receta**, y por tanto:

- el SHA-256 de `.pipeline.kts` **no cambia** (`7541ced5…`),
- las certificaciones de WI-101 a WI-109 **siguen valiendo**: cada run
  se certificó con el verificador de su momento,
- el cambio es testeable sin lanzar un pipelinek entero.

Menos superficie, más barato de verificar. Y
`test_la_receta_no_cambio` fija el digest para que nadie lo mueva sin
querer.

## 4. Qué cambió

### 4.1 `InformeRun.paso_fallido` — el nombre, que es el cambio de fondo

El acumulador leía `StepFailed` como un contador. Ahora guarda el
**nombre** del paso, leyendo `stepName` del evento, que es donde está la
propiedad en el journal.

Valor por defecto `None` a propósito: el guard de WI-108 construye
`InformeRun` con campos sueltos, y un campo nuevo sin defecto le
revienta sus nueve tests. **Eso pasó** y se resolvió con el defecto, no
tocando el guard anterior.

`None` significa «no se sabe», y con `None` **no se exculpa nada**.

### 4.2 `ETAPA_AUTOEVALUADA`, declarado y no escrito dentro

```python
ETAPA_AUTOEVALUADA: Final[str] = "evidence"
```

Vive como constante para que un test pueda exigir que las dos copias no
diverjan. Mismo patrón que `SKIPS_PLATAFORMA` de WI-108.

### 4.3 La exculpación: tres condiciones, no una

```python
solo_autoevaluada = (
    informe.step_failed == 1
    and paso is not None
    and paso.startswith(f"{ETAPA_AUTOEVALUADA}/")
)
```

1. **Un solo** `StepFailed`. Con dos hay un fallo de código más allá de
   la etapa, y perdonar la mitad de un fallo es dejar de vigilar.
2. **El nombre se conoce**. Sin nombre no hay base: se falla por
   defecto, que es lo seguro.
3. **El nombre es `evidence/`**, con barra. La barra separa la etapa de
   un nombre que sólo se le parece.

Y lo que **nunca** se exculpa: **el veredicto del run**. Un run abortado
sin un solo `StepFailed` se rechaza igual.

## 5. Dos defectos que encontraron las propias pruebas

### 5.1 `startswith` sin la barra

MEDIDO: con `startswith(ETAPA_AUTOEVALUADA)` —sin la barra— una etapa
llamada **`evidence-hack/sh-0`** también pasaba. Lo cazaron las ocho
etapas del parametrize.

La primera versión de mi propio comentario daba el `startswith` por
bueno y describía el hueco como aceptable, con las palabras «sin el
prefijo, una etapa llamada `evidence-hack` también pasaría». No lo era.

> Un comentario que describe un hueco sin cerrarlo es una promesa que el
> código no cumple. Documentar primero y cerrar después es exactamente el
> reflejo que hace que el hueco exista.

### 5.2 Cuatro sondas del harness que no sondeaban

M2, M5, M5b y M6 apuntaban a tests cuyo nombre estaba mal escrito
(`test_..._sin_pasar` en vez de `test_..._sigue_sin_pasar`). Pytest
respondía **`no tests ran`**, salía con código **5**, y el harness leía
«returncode distinto de cero» como «el guard falló».

**Cuatro CAZADAS que no eran ninguna**: el guard no llegó a opinar.

El harness ahora distingue **cuatro** salidas con nombre —`CAZADA`,
`NO_DETECTADA`, `SIN_SONDA`, `INVALIDA`— y las sondas se verifican una
a una antes de contar. El detalle que lo hace peor: estaban en el
fichero que escribí para **probar** que el guard muerde, así que el
fallo del instrumento era invisible justo en el sitio que existe para
detectorlo.

## 6. Mutaciones: 11/11

| | mutación | veredicto |
|---|---|---|
| M1 | se vuelve a rechazar cualquier `outcome != success` | CAZADA |
| M2 | perdona cualquier etapa con un solo `StepFailed` | CAZADA |
| M3 | perdona también con dos pasos rotos | CAZADA |
| M4 | perdona aunque no sepa el nombre | CAZADA |
| M5 | prefijo sin la barra (`evidence-hack` pasa) | CAZADA |
| M5b | prefijo contra una letra (`'e'`) | CAZADA |
| M6 | perdona también el veredicto del run | CAZADA |
| M7 | el acumulador descarta el nombre | CAZADA |
| M8 | se lee una clave que no existe | CAZADA |
| M9 | la etapa autoevaluada deja de ser la correcta | CAZADA |
| M10 | se desactiva un criterio que ya existía | CAZADA |

```
11/11 cazadas, 0 invalidas, 0 no detectadas, 0 sin sonda
restore scripts/check_pipeline_receipt.py: OK
```

M2 y M5 son lasinformativas: cazan **2 de 8** casos del parametrize,
exactamente los que no deberían pasar. Las sondas muestran trabajo real.

## 7. El guard: 22 tests

`tests/test_wi110_evidence_recoverable.py`.

| mitad | tests |
|---|---|
| **la que arregla** | 1 (el caso que envenenaba la cadena) |
| **la que perdona de más** | 8 etapas en el parametrize, 2 pasos rotos, 1 sin nombre, 1 run abortado, 1 por aritmética de etapas, 1 contraejemplo del propio guard |
| **la frontera** | el nombre llega desde un journal SQLite real; sin `stepName` queda `None` |
| **la regla** | la receta no cambió (digest); la exculpación está declarada y escrita |

El guard que mira los criterios de `evaluar()` mira el **AST**: la
primera versión buscaba `informe.step_failed` como cadena y la mutación
M10 —cambiar el `if` por `if False:`— la sobrevivió, porque la cadena
seguía ahí, en el cuerpo del `if` muerto. Tercera vez en tres semanas
por el mismo motivo.

## 8. Release

`scripts/derive_semver.py` desde `v0.22.0`:

```
b/f/x/n/d: 0/0/1/4/0
la regla pide PATCH -> v0.22.1
```

`.pipeline.kts` **no se toca** (criterio C6 del PRE-FLIGHT, verificado y
fijado por test).

## 9. Lo que NO arregla

Un run con las siete etapas de código verdes y `evidence` en rojo sigue
terminando en `FAILURE` por construcción: la etapa que lo evalúa es una
de las ocho. Lo que cambia es que **el siguiente run ya no hereda el
fallo**. El primer run verde tras el arreglo llega **uno después**, no en
el mismo.

## 10. Certificación

**Run canónico**: `be32259e-f012-47f7-b146-1490343ada10`, terminado a las
`2026-10-03T06:10:30.751893188Z`, `exit=0`.

Leído del journal **después** de terminar, por `run_id` **y** `occurred_at`
— nunca por la línea de salida. 48 eventos, 9 pasos ejecutados:

| # | etapa | outcome |
|---|---|---|
| 0 | `discover-repo` | success |
| 1 | `sync-deps` | success |
| 2 | `unit-tests` | success |
| 3 | `coverage-floors` | success |
| 4 | `package-build` | success |
| 5 | `ci-parity` | success |
| 6 | `lint` | success |
| 7 | `evidence` | **success** |

`RunFinished` → `outcome: success`, `diagnostics: []`. **8/8 etapas en
`success`** (criterio C7).

**La línea que prueba el arreglo**, tal cual la escribió la propia etapa
`evidence` en su `EchoOutputCaptured`:

```
OK: el run cumple los criterios que declara AGENTS.md.
run bf2a8e23-c07d-46f9-89f2-9ac939be3ea5: 7/7 etapas, 9 pasos, veredicto 'failure'.
```

La etapa **`evidence` pasó evaluando un run en `failure`**. Eso es
exactamente lo que antes era imposible: la condición de exculpación
(`un solo StepFailed` + nombre `evidence/`) se cumple y el veredicto del
run no se toca. El run en `failure` es `bf2a8e23`, el inmediatamente
anterior, cuyo único `StepFailed` era el propio fallo de `evidence`. El
deadlock se había exculpado a sí mismo.

**Verificación independiente**, invocar el verificador a mano sobre el
mismo run, sin pasar por la receta:

```
$ python scripts/check_pipeline_receipt.py --run-id be32259e-...
OK: el run cumple los criterios que declara AGENTS.md.
run be32259e-...: 8/8 etapas, 9 pasos, veredicto 'success'.
rc=0
```

**Resto de criterios del PRE-FLIGHT, en el estado final:**

| criterio | verificado |
|---|---|
| C1 árbol limpio al lanzar | `git status --porcelain` → sólo la evidencia sin versionar |
| C2 SHA-256 de `.pipeline.kts` | `7541ced5…2dd42`, sin drift |
| C3 | `.pipeline.kts` intacto; el arreglo vive en `scripts/` |
| C4 | guard de 22 tests verde |
| C5 | 11/11 mutaciones cazadas con sonda |
| C6 | recipe SHA fijado por test |
| C7 | **8/8 etapas en `success`** |

**Qué queda sin certificar aquí:** el run evaluates a un run que ya no
era verde. La propiedad «un run con las siete etapas de código verdes y
`evidence` en rojo sigue terminando en `FAILURE` por construcción» (§9) no
la contradice: aquí las ocho estaban verdes. Lo que se ha medido es lo
otro — que la cadena **deja de envenenarse**.

## 11. Push

**170 commits** sin publicar al abrir este bloque. El operador autorizó
el push explícitamente. Se ejecuta tras el cierre del ciclo SDDK, para
que el remoto reciba el bloque cerrado y no a medias.
