# Verificación WI-101 — el bundle de auditoría certificaba UATs que no ejecutaba

- **Ciclo**: `p-b7740b96d79ec013/wi101-uat-audit-false-verdict`
- **Sesión**: `wi101-20261002T224510Z`
- **Fecha**: 2026-10-02
- **Run de certificación (el que cierra)**: `3feba714-7c90-4ed8-81ce-402a7fc8c6c2`
  — 8/8 stages, 2661 passed, 0 `StepFailed`.
- **Run previo, sobre el estado ya cerrado**: `8adb8929-4a05-44e1-abdf-9faf409e51e1`
  — **falló**, y por qué importa está en §8.2.
- **SHA-256 de `.pipeline.kts`**: `d865896832f1c391344cb76a1b52b14c68915b99cefd985e976381dfe8d3ddcc`
  (idéntico al de WI-98 y WI-100: sin drift en la receta)

---

## 1. El hallazgo

`scripts/audit_bundle.sh` —el instrumento que existe **para** dar evidencia
reproducible a una auditoría independiente— invocaba:

```bash
uv run python -m tests.uat_audit
```

Sin flags. Ese es el **modo lectura**: no ejecuta un solo UAT, relee los 26
JSON de `tests/uat-evidence/` y los repite. El `PASS=16` del bundle de WI-99
se escribió mirando ficheros del commit `0ebbd58` (= `origin/main`), 111
commits por detrás de la fecha de medición.

## 2. Lo que había debajo: el exit code no significaba nada

`tests/uat_audit.py` hacía `return 0` **incondicional** en el modo lectura
(línea 1949 en el árbol previo). El exit code estaba estructuralmente
desacoplado del veredicto.

La guarda del bundle es:

```bash
if [ "$UAT_RC" -ne 0 ]; then
    echo "[audit_bundle] ERROR: uat_audit fallo; bundle NO certificable" >&2
    exit "$UAT_RC"
fi
```

Que compara contra ese código. **No podía dispararse jamás por el estado de la
evidencia.**

### Medición, con el comando exacto del bundle

Script autocontrolado (`.pipelinek/wi101_measure.sh`): backup byte a byte,
trap, y verificación `sha256` al salir. Sin `mktemp`.

| variante | evidencia en disco | salida | exit code |
|---|---|---|---|
| baseline | intacta | `PASS=16 FAIL=0` | 0 |
| A — inyectada | `UAT-01.json` con `status: FAIL` | `PASS=15 FAIL=1` | **0** |
| B — ausente | `tests/uat-evidence/` movido fuera | `PASS=0 FAIL=0` | **0** |

Restauración verificada byte a byte en ambos casos; `git status --porcelain`
vacío al terminar.

Un bundle con un `FAIL` a la vista y un bundle sin una sola evidencia eran
**indistinguibles** de uno sano. Un exit code fijo no es un guard: es un
mensaje con código de salida.

## 3. Un segundo defecto que solo apareció al escribir su propio test

El primero de los tests de WI-101 puso `status: "passed"` (typo deliberado) y
falló. No por lo que esperaba.

El resumen imprimía:

```
  FAIL UAT-07: passed
PASS=15  FAIL=0  BLOCKED=0
```

`PASS=15 FAIL=0 BLOCKED=0` sobre **16 filas leídas**. El número era cierto
letra a letra y estaba mal: 15+0+0 ≠ 16, y la diferencia no aparecía en
ninguna parte de la salida. El recuento solo miraba las tres etiquetas
conocidas y se tragaba el resto.

De ahí la decisión de **lista blanca** (`PASS`, `BLOCKED`) en vez de negra
(`FAIL`, `MISSING`, `READ_ERROR`, `UNKNOWN`): una lista negra tiene que
enumerar cada cosa mala, y ese conjunto no tiene fin. Un `status: "passed"`
pasaba el guard en silencio.

## 4. Los tres cambios

1. **El exit code sale de `_verdict`**, compartido por los tres modos (lectura,
   `--dry-run`/`--write`, `--verify`) para que no puedan divergir entre sí.
   Lista blanca de estados certificables.
2. **`--verify`**: ejecuta los UATs, no persiste, y **confronta** cada
   veredicto con la evidencia persistida. Sin ese contraste la evidencia era
   la única fuente del veredicto y no se contrastaba con nada: podía afirmar
   `PASS` para un UAT que hoy falla sin que nadie se entere.
3. **El resumen cuenta lo que no conoce**: `FUERA DE DOMINIO=n` cuando hay
   veredictos fuera del dominio cerrado.

`scripts/audit_bundle.sh` pasa a invocar `--verify`.

## 5. Verificación después del arreglo, no antes

Mismo script, misma inyección:

```
== 3. comando exacto del bundle con evidencia en FAIL ==
exit code = 1
=== Modo VERIFY (16 UATs; no persiste) ===
PASS=16  FAIL=0  BLOCKED=0
```

La ejecución da `PASS=16` mientras la evidencia persistida decía `FAIL`:
sale con 1 **por la divergencia**, no porque un UAT falle.

Y sobre el repo tal como está, sin tocar nada:

```
PASS=16  FAIL=0  BLOCKED=0
Convergencia: la ejecucion coincide con la evidencia persistida.
EXIT=0
```

**Los 16 UAT se ejecutan de verdad y convergen con la evidencia versionada.**
La evidencia era cierta; lo que faltaba era comprobarlo.

## 6. Mutaciones — 9/9 en rojo

`.pipelinek/wi101_mutate.sh`. Backup byte a byte, `restaurar()` **nunca**
borra el backup (borrar es trabajo del trap, y solo al final), `sha256`
verificado al salir.

| # | mutación | guard vigilado | resultado |
|---|---|---|---|
| M1 | `_verdict` → `return 0` incondicional | `…_la_evidencia_dice_fail` | ROJO |
| M2 | lista blanca → solo `== "FAIL"` | `…_el_estado_es_desconocido` | ROJO |
| M3 | evidencia ausente → `[]` | `…_si_falta_evidencia` | ROJO |
| M3b | JSON ilegible se disfraza de `PASS` | `…_la_evidencia_es_ilegible` | ROJO |
| M4 | `_divergencias` → `return ()` | `…_anticipa_un_fallo_que_ya_no_ocurre` | ROJO |
| M5 | `--verify` cae al modo lectura | `…verify_ejecuta_los_uats` | ROJO |
| M6 | resumen vuelve a tragarse fuera-de-dominio | `…_no_se_traga_los_estados…` | ROJO |
| M7 | bundle sin `--verify` | `…bundle_de_auditoria_ejecuta…` | ROJO |
| M8 | `--verify` **solo en un comentario** | `…bundle_de_auditoria_ejecuta…` | ROJO |

**M8 es el contraejemplo de la serie.** Quita el flag de la orden real y lo
deja solo en un comentario: el guard tiene que seguir viendo el modo lectura.
Un guard que se dejara engañar por una mención pasaría en verde — es
exactamente lo que Confirmó M7 de WI-100 (un `echo` de diagnóstico con
`pytest` contó como invocación durante dos commits).

**M4 encontró un test confundido.** Apuntaba al test espejo
(`evidencia PASS` / `ejecución FAIL`), y se quedaba **verde**: con la
ejecución en `FAIL` el veredicto ya es 1, así que el `rc != 0` podía venir del
veredicto y no de la divergencia. El test no podía fallar por la razón que
decía. Añadido el caso no confundido (`evidencia FAIL` / `ejecución PASS`),
que es el que aparece en la medición real de la sección 5.

## 7. Un fallo de autocontrol, registrado

La primera versión de `wi101_mutate.sh` tenía `rm -rf "$BAK"` **dentro** de
`restaurar()`. La primera restauración se llevó el backup y las seis
siguientes se quedaron sin nada que restaurar: las mutaciones se acumularon
sobre el árbol de trabajo y hubo que revertirlas a mano (6 en
`tests/uat_audit.py`, 2 en `scripts/audit_bundle.sh`; `tests/test_uat_audit.py`
intacto, ninguna mutación lo apuntaba). Verificado tras revertir: 28 tests
verdes, `ruff` limpio, y las 9 mutaciones de nuevo en rojo sobre el fichero
restaurado.

**Autocontrol que se degrada en silencio no es autocontrol**: el script
anunciaba `RESTAURADO OK` mientras seis restauraciones no restauraban nada.
La lección quedó escrita en la cabecera del script.
También falló un intento de dividir el cambio en dos commits cortando el
fichero de tests por números de línea: la cadena de anclaje aparecía
también dentro de un *docstring*, el corte dejó un docstring colgando y el
fichero no parseaba. Restaurado reinsertando el bloque. El cambio quedó en
un solo commit, que además es lo correcto: el arreglo del exit code y el
cambio del bundle son la misma propiedad y separarlos deja un estado
intermedio inerte.

## 8. Certificación

```
mise exec -- pipelinek run --rerun \
  --db .pipelinek/db.sqlite --control-root .pipelinek/control .pipeline.kts
```

### 8.1 Run del código — `e5d046af-07e6-4cdf-910c-8bbd7c8f36b1`

| stage | outcome |
|---|---|
| `discover-repo` | success |
| `sync-deps` | success |
| `unit-tests` | success — **2661 passed in 227.23s** |
| `coverage-floors` | success — global 95,22 % (suelo 80 %), CLI 86,91 % (70 %), runtime 97,98 % (90 %) |
| `package-build` | success |
| `ci-parity` | success |
| `lint` | success |
| `evidence` | success |

`Pipeline finished with SUCCESS`. **0 `StepFailed`**. 8/8 stages.

### 8.2 Run del estado final — `8adb8929-4a05-44e1-abdf-9faf409e51e1`: **FALLÓ**

WI-100 dejó escrito que **la reproducibilidad hay que certificarla después de
escribir la certificación**, y el release escribe la certificación. Así que se
lanza una segunda corrida sobre el estado ya cerrado (commit `e58b783`, con el
tag, el `STATE.yaml` y el `CURRENT.md` definitivos).

**Falló**: 2/3 stages, `RunFinished=failure`, 1 `StepFailed`,
`pytest: 1 failed, 2660 passed in 230.40s`.

El fallo:

```
tests/test_wi92_measured_claims.py::TestBlockCitationsDelCurrentVivoResuelven::
    test_el_bloque_vivo_tiene_al_una_cita_que_verificar
AssertionError: el bloque vivo de CURRENT.md no cita ninguna linea
```

**El bloque vivo de `CURRENT.md` que escribí no tenía ninguna cita
`fichero.py:línea` verificable.** Es exactamente el mismo modo de fallo que
WI-100 ya había corregido una vez (`86d4a41`): el guard
`test_el_bloque_vivo_tiene_al_una_cita_que_verificar` existe precisamente
porque *un guard sobre cero citas no vigila nada*, y yo escribí un bloque que
no le daba nada que vigilar.

Corregido con cuatro citas que resuelven y que son ciertas:

| cita | qué es |
|---|---|
| `tests/uat_audit.py:1854` | `_ESTADOS_CERTIFICABLES`, la lista blanca |
| `tests/uat_audit.py:1962` | el `return` de `_verdict` |
| `tests/uat_audit.py:1965` | `_divergencias` |
| `tests/uat_audit.py:2088` | la rama `if args.verify:` de `main` |

**La lección no es «añadir la cita».** Es que el fallo estaba en el
*documento de certificación*, no en el código: el código llevaba tres
certificaciones verdes y el bloque que lo describía era inverificable. Un
documento que no se puede comprobar no certifica el documento que certifica.

### 8.3 Run de cierre — `3feba714-7c90-4ed8-81ce-402a7fc8c6c2`

Sobre el estado ya corregido (`b556649`):

- **8/8 stages** `success`
- **2661 passed in 229.56 s**
- cobertura: global **95,22 %** (suelo 80 %), CLI 86,91 % (70 %), runtime 97,98 % (90 %)
- **0 `StepFailed`**, `RunFinished=success`
- SHA-256 de `.pipeline.kts` = `d8658968…3ddcc`, sin drift

### 8.4 Los tres runs, leídos del journal

Leyéndolos por `run_id` y no por la línea de salida, que es donde se me
escapó el segundo:

| run | qué mide | stages | `StepFailed` | `RunFinished` |
|---|---|---|---|---|
| `e5d046af` | el código | 8/8 | 0 | success |
| `8adb8929` | estado final, 1.ª vez | **2/3** | **1** | **failure** |
| `3feba714` | estado final, ya corregido | 8/8 | 0 | success |

El intermedio no sobra: es el que encontró el fallo, y sin él este bloque
habría terminado con una certificación verde sobre un documento de
certificación inverificable.

## 9. Criterios de aceptación

| # | criterio | estado |
|---|---|---|
| 1 | modo lectura devuelve exit ≠ 0 con evidencia en `FAIL` | verificado (M1) |
| 2 | modo lectura devuelve exit ≠ 0 si falta evidencia | verificado (M3) |
| 3 | el modo lectura sigue sin escribir en disco | verificado (`test_main_default_is_readonly`) |
| 4 | el bundle ejecuta los UAT de verdad | verificado (M7, M8) |
| 5 | si la ejecución contradice la evidencia, el bundle falla | verificado (M4, sección 5) |
| 6 | mutaciones | **9/9 en rojo** |
| 7 | `ruff check src tests scripts` + `ruff format --check src tests` | verdes |
| 8 | receta canónica 8/8 con `Pipeline finished with SUCCESS` | run `e5d046af` |

## 10. Lo que este bloque NO arregla

- **No se regenera la evidencia persistida.** Los 26 JSON siguen llevando
  `revision: cb7e348…` y `timestamp: 2026-09-23`. Son *provenance*: registran
  lo que pasó entonces. Lo que faltaba era contrastarlos, y `--verify` los
  contrasta sin reescribirlos. Regenerarlos convertiría un registro en una
  copia del presente, que es otra cosa y tiene otros requisitos.
- **No se toca `.gitignore`**, ni los 4 informes de `sddk lint` de perfil
  *autor de pack*, ni las líneas CJK preexistentes.
- **No hay push.** 112 commits sin publicar, `origin/main` en `0ebbd58`.
  Sin autorización del operador.
- **Los hooks siguen sin instalar** en `.git/hooks/`. El `pre-commit` que
  hay es la copia anterior a WI-100: este commit lo pagó otra vez, **120,27 s
  por la suite entera** (2661 passed). Es la medición de WI-100
  reproducida sin haber instalado el hook nuevo. Instalar es decisión del
  operador: `bash scripts/install-hooks.sh`.
