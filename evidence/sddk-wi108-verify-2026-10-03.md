# WI-108 — la regla de cero skips, y el criterio que la vigila nunca la preguntó

**Fecha**: 2026-10-03
**Ciclo**: `p-b7740b96d79ec013/wi108-cero-skips` (workflow `A-full`)
**Último tag**: `v0.21.2` (anotado, sobre `841a075`)
**Versión activa**: `0.21.2.dev0`
**Serie**: «¿qué declara el repo que nada comprueba?» — décima vía
**Release**: PATCH, derivado con `scripts/derive_semver.py` (`0/0/1/4/0`)

---

## 1. El defecto

`AGENTS.md §6.2` dice, con las dos líneas que la serie viene defendiendo:

> **NO usar `pytest.skip` para esconder fallos: o arreglas el test o lo
> borras.**
> **Un `skip` por falta de artefacto es el mismo defecto, con otra forma.**

La segunda la escribió WI-103 después de medir un gate que se saltaba por
falta de informe. Es una prohibición **razonada**.

Y no había nada que la comprobara:

```
instrumentos que miran skips (scripts/, src/): 0
etapas de la receta que los miran:               0
```

La primera versión de esa medición buscaba la palabra `skip` y devolvió
cinco menciones en `src/`: `should_skip_adapter`, que es una función de
dominio, y un docstring de `runtime/locks.py` que **cita** el decorador.
Buscó la cadena, no la propiedad. La medición se corrigió antes de
escribir una línea, y es la segunda vez en dos semanas que esa confusión
aparece en este repositorio.

## 2. Medición previa (antes de tocar nada)

Con un run sintético cuyo único cambio es la línea de resumen del journal:

```
run sin skips:   0 problemas []
run con 3 skips: 0 problemas []
veredicto: «OK: el run cumple los criterios que declara AGENTS.md»
```

El regex del criterio 2:

```
RESUMEN_PYTEST = r"\b\d+\s+(?:passed|failed|error)\b"

sin skips  casa=True   pytest: 2718 passed in 240.06s (0:04:00)
3 skips    casa=True   pytest: 2715 passed, 3 skipped in 240.06s (0:04:00)
todos skip casa=False  pytest: 2718 skipped in 240.06s (0:04:00)
xfailed    casa=True   pytest: 2700 passed, 18 xfailed in 240.06s (0:04:00)
roto       casa=True   pytest: 5 failed, 2713 passed in 240.06s
```

**El detalle que hace el defecto grave no es el regex.** El criterio 2 pide
«el resumen de pytest del journal», y un resumen con `5 failed` también lo
es: el regex hace bien su trabajo. Lo que no hay es un criterio que pregunte
por los skips. Que `3 skipped` case con el regex no es un bug del regex: es
que **la pregunta no existe**, así que nadie la respondió nunca.

Una regla y el criterio que la vigila no se contradicen cuando nunca se
cruzan.

## 3. Los skips que había, y por qué no son todos lo mismo

```
plataforma  tests/test_evidence_lock.py:214   not _HAS_FCNTL
plataforma  tests/test_locks.py:196           os.name == "nt"
artefacto   tests/test_wi105_pipeline_receipt.py:228   sin journal: clon nuevo, no hay run que verificar
artefacto   tests/test_wi105_pipeline_receipt.py:244   sin journal: clon nuevo
artefacto   tests/test_wi105_pipeline_receipt.py:258   sin journal: clon nuevo
total 5: {'plataforma': 2, 'artefacto': 3}
```

Los de plataforma son legítimos: `fcntl` no existir en Windows no es un
fallo escondido, es una diferencia real entre máquinas.

Los de artefacto son **justo lo que la segunda línea de §6.2 prohíbe por su
nombre** — y los escribió el autor de esa línea, dos bloques más abajo, en
el guard que construyó para no esconder nada.

En esta máquina no se saltan: el journal existe. El skip es **latente** y se
activa donde el artefacto no está, que es un clon nuevo. Y ahí la suite
pasaría en verde con skips, que es la forma exacta que la regla prohíbe.

## 4. El arreglo

* **`sg_pipeline_tests_skipped`** en `scripts/check_pipeline_receipt.py`,
  que la etapa `evidence` mide porque es donde ya se comprueban los
  criterios. Cuenta `skipped` **y** `xfailed`, que son la misma propiedad
  con dos nombres.
* **`resumen_sin_skips()`** como predicado puro y separado, por la misma
  razón que `_bump_valido` en WI-106: un predicado que solo se llama con
  el valor de hoy no comprueba un dominio, comprueba una coincidencia. Se
  le llama con `3 skipped`, `2718 skipped`, `18 xfailed`, `3 SKIPPED`,
  `0 skipped` y `""`.
* **Pregunta por el valor, no por la presencia.** `2718 passed, 0 skipped`
  declara cero tests sin ejecutar y es un run limpio. pytest no imprime el
  cero, así que un guard que mirara «hay skipped» trataría una línea buena
  como un incumplimiento — un falso positivo que entrena a su lector a
  ignorar sus avisos. El primer predicado que escribí tenía ese defecto y
  su propio test lo cazó.
* **Los 3 skips de artefacto se van, sin sustituto.** Medían el
  **entorno** —qué pasó en esta máquina— y no el **entregable** —qué
  garantiza el guard—. El journal no está versionado (`.pipelinek/` solo
  versiona su `.gitkeep`), así que en un clon nuevo se saltaban en
  silencio. Sus tres propiedades ya tienen sitio:

  | test que se fue | qué comprobaba | dónde vive ahora |
  |---|---|---|
  | `..._cumple_los_criterios` | el último run real cumple | la etapa `evidence`, en cada run |
  | `..._no_es_una_mediacion_vacia` | el run verificado tuvo pasos | `TestUnRunVerdeQueNoEjecutoNadaNoVale`, sintético |
  | `..._registra_runs_que_este_guard_rechazaria` | el journal tiene historia variada | la certificación de cada bloque, leyendo el journal |

* **`SKIPS_PLATAFORMA`** declara los 2 legítimos y se vigila en las **dos**
  direcciones: un skip nuevo sin declarar es un incumplimiento, y uno
  declarado que se borre deja la regla sin suelo. Vigilar solo en una
  dirección deja de ser vigilar — el mismo caso que una desviación de
  cobertura que apunta a un fichero borrado (WI-107).
* **El guard que mira el código mira el AST, no el texto.** La primera
  versión buscaba `pytest.skip(` con un regex y **se puso roja por su propia
  documentación**: este fichero cita el patrón para explicar que lo
  prohibe, y una cita es indistinguible de una llamada. La propiedad es
  «este código *llama* a `pytest.skip`», y eso lo responde el árbol
  sintáctico, donde un docstring es una constante. Dos tests fijan la
  distinción con los dos lados.
* **`§6.2` dice ahora cómo se comprueba y dónde**, en una tabla con las dos
  propiedades y los dos sitios. Una prohibición sin verificador es una
  declaración.

## 5. Límite declarado

`from pytest import skip` seguido de `skip(...)` no lo ve el AST, porque el
nombre ya no es `pytest.skip`. Es un alias, no la forma que pytest
documenta, y queda escrito en `§6.2` y en un test, en vez de descubrirse.

## 6. Mutaciones

| | qué rompe | sonda antes → después | resultado |
|---|---|---|---|
| m1 | el guard emite `sg_skipped` en vez de `sg_pipeline_tests_skipped` | `['sg_pipeline_tests_skipped']` → `['sg_skipped']` | cazada |
| m2 | el regex deja de mirar `xfailed` | `False` → `True` | cazada |
| m3 | el predicado pregunta por presencia en vez de por valor | `True` → `False` | cazada |
| m4 | la cuenta se anula | `['sg_pipeline_tests_skipped']` → `[]` | cazada |
| m5 | el guard de AST devuelve la forma equivocada | `(Skip(...),)` → `()` | cazada |
| m6 | `_nombre_dotted` deja de resolver | `1` → `0` | cazada |
| m7 | la lista declarada del test pierde una entrada | `0` → `1` | cazada |
| m9 | la lista del guard pierde la que la del test conserva | `0` → `1` | cazada |
| m8 | `§6.2` real pierde la referencia al verificador | `True` → `False` | cazada |

**9/9 en tres pasadas consecutivas**, con el árbol restaurado byte a byte en
las tres (`git diff` vacío al final de cada una).

**La primera vez que la sonda evitó una acusación falsa.** La primera sonda
de m5 —cambiar el código del error a uno que nadie espera— no la cazó, y el
harness la clasificó como **MUTACIÓN INVALIDA**, no como fallo del guard: la
sonda medía la forma de retorno de un árbol **sin llamadas**, donde esa
forma nunca se ejerce. Sin la clasificacion por sonda, ese 8/9 habria sido «al guard
se le escapó una mutación», que es exactamente la mentira que este patrón
existe para no contar.

## 7. Certificación

**Run** — `2387c4cc-c624-4793-a8ef-1a83f3df72ea`

```
pytest: 2735 passed in 241.57s (0:04:01)
== suelos declarados a mano, y si lo que nombran existe ==
  OK   todo suelo declarado a mano nombra algo que existe
  OK    95.22 %  (fail_under = 80 %)
VEREDICTO: todo modulo gobernado por §6.3 cumple su suelo
Pipeline finished with SUCCESS
```

El resumen es `2735 passed in 241.57s` **sin la palabra `skipped`**, que es
lo que el criterio nuevo exige. La etapa `evidence` verificó el run
anterior `fdb35d26`:

```
$ mise exec -- uv run python scripts/check_pipeline_receipt.py --run-id 2387c4cc-...
OK: el run cumple los criterios que declara AGENTS.md. run 2387c4cc-...:
8/8 etapas, 9 pasos, veredicto 'success'.
```

**Criterio 6**, registrado en la sesión y no automatizado a propósito:

```
sha256(.pipeline.kts) = 7541ced56193c9f2c846de84c7e96abff61dac7de2ed363b778a721738c2dd42
```

Sin drift desde `283da96` (WI-105).

**Tests**: 2735 passed, 0 skipped. La aritmética coincide con el run por
primera vez en tres bloques: `2718 + 20 − 3 = 2735`. La cuenta anterior
(`2703 + 22`) daba 2725 contra 2718 real, y la de WI-106 daba 2702 contra
2703.

**Cobertura**: global 95.22 %, `cli/` 86.91 %, `runtime/` 97.98 %.

## 8. Lo que NO se arregla, y se declara

* `from pytest import skip` no lo cubre el guard (ver §5).
* Los 2 skips de plataforma son legítimos en Linux, donde no se activan, y
  en Windows producirían `2 skipped` en el resumen. El criterio del CI es
  `0 skipped` sin excepciones, así que **en Windows el CI fallaría** con
  los dos skips de plataforma. Es el comportamiento correcto —el CI no se
  puede exceptuarse a si mismo— pero significa que el repo no es
  certificable en Windows hasta que esa plataforma se declare, y eso no
  está escrito en ninguna parte. Deuda tangencial, registrada aquí.
* `scripts/coverage.sh` sigue siendo una instrumentación de la suite, y el
  criterio de skips se lee de una medición que el propio CI produce.

## 9. Reproducir

```bash
# Medición previa (solo lectura)
mise exec -- uv run python .pipelinek/wi108_measure.py

# Mutaciones (exige árbol quieto y commiteado)
bash .pipelinek/wi108_mutate.sh

# Certificación
mise exec -- pipelinek run --rerun --db .pipelinek/db.sqlite \
    --control-root .pipelinek/control .pipeline.kts
mise exec -- uv run python scripts/check_pipeline_receipt.py --run-id <run_id>
```
