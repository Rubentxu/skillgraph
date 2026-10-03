# WI-107 — la lista de paquetes con suelo, y por qué cambiarle el eje no la deshace

**Fecha**: 2026-10-03
**Ciclo**: `p-b7740b96d79ec013/wi107-suelo-por-defecto` (workflow `A-full`)
**HEAD al certificar**: `91f901d`
**Último tag**: `v0.21.1` (anotado, sobre `3f28ba0`)
**Versión activa**: `0.21.1.dev0`
**Serie**: «¿qué declara el repo que nada comprueba?» — novena vía
**Release**: PATCH, derivado con `scripts/derive_semver.py` (`0/0/2/10/0`)

---

## 1. El defecto

`AGENTS.md §6.3` declara suelos de cobertura por módulo. El guard que los
comprueba, `scripts/check_coverage_floors.py`, ha tenido tres versiones, cada
una creyendo que era la última:

| | la lista | lo que dejaba fuera |
|---|---|---|
| WI-93 | 21 módulos escritos a mano | todo menos `runtime/` |
| WI-94 | 8 prefijos de paquete escritos a mano | un paquete **nuevo** |
| WI-107 | ninguna | — |

El docstring de WI-94 afirmaba:

> «Una sola fuente, sin lista que mantener, y por eso no se puede olvidar
> uno.»

Es falso. El suelo pasó a declararse por paquete, y el **conjunto de
paquetes** seguía siendo `SUELOS_POR_PAQUETE`, un diccionario escrito a mano
de ocho entradas. Un paquete que no estuviera en él no heredaba nada:
`suelo_de()` devolvía `None` y `evaluar()` hacía `continue` sin mirar el
módulo.

## 2. Medición previa (antes de tocar nada)

`src/skillgraph/telepatia/` — un paquete nuevo con código que nadie importa,
**versionado en el índice de git** (`git ls-files` es lo que lee el guard de
WI-97).

```
tests colectados, árbol limpio: 2703
tests colectados, con el paquete: 2709   (+6)

M1  suelo_de('src/skillgraph/telepatia/oracular.py')   = None   <- sin suelo
    suelo_de('src/skillgraph/governance/control.py')   = 90.0   <- con suelo

M2  evaluar() con ese módulo al 0 %
    paquete NO declarado -> 0 fallo(s): []
    paquete    declarado -> 1 fallo(s): ['...oracular.py mide 0.00 %,
                                          por debajo de su suelo del 90 %']

M3  el guard de WI-94 (test_cada_paquete_declarado_tiene_modulos_de_verdad)
    exit=0  8 passed — el guard recorre SUELOS_POR_PAQUETE, así que un
    paquete que no esté en la lista le es invisible

M4  forma del fixture contrastada contra el informe real: idéntica

M5bis  INSTRUMENTO DE PRODUCCIÓN
    pytest                    2709 passed in 234.75s
    check_coverage_floors.py  exit 0, «todos los suelos se cumplen»
    cobertura de oracular.py  0 %  (18 sentencias, 10 ramas, 0 cubiertas)
    suelo global              94.85 %   (fail_under = 80)
```

### Por qué se midió dos veces

La primera medición, con el paquete **sin** versionar, dio `1 failed, 2708
passed`. El rojo era `sg_build_sdist_no_versionado` (WI-97): un sdist no
puede llevar lo que git no versiona.

Ese resultado era más fuerte y **falso** para la afirmación que se iba a
escribir. Ese guard lo ve, pero por **otra** propiedad y con **otro** mensaje,
y un paquete nuevo se versiona: no es el contrato de §6.3, es otra puerta que
se abre por casualidad. Escribir solo la primera habría producido «el repo
entero es ciego ante un paquete sin suelo», y esa es la afirmación que no se
escribe.

### El `+6`, medido y no estimado

Diferencia de la lista de tests colectados, línea a línea:

```
tests/test_wi47_broad_except_guard.py::test_broad_except_does_not_silently_discard[__init__.py11]
tests/test_wi47_broad_except_guard.py::test_broad_except_does_not_silently_discard[oracular.py]
tests/test_wi47_broad_except_guard.py::test_broad_except_is_documented[__init__.py11]
tests/test_wi47_broad_except_guard.py::test_broad_except_is_documented[oracular.py]
tests/test_wi47_broad_except_guard.py::test_no_message_sniffing_to_classify_errors[__init__.py11]
tests/test_wi47_broad_except_guard.py::test_no_message_sniffing_to_classify_errors[oracular.py]
```

Son los seis tests parametrizados de un guard que **sí** deriva del árbol. El
repo ya tenía guards que descubren ficheros nuevos; este era uno de los que
no.

## 3. El arreglo

* `SUELO_POR_DEFECTO = 90` alcanza a todo módulo que cuelgue de un
  subdirectorio de `src/skillgraph/`, paquete nuevo incluido, sin que nadie lo
  declare.
* Lo escrito son las **desviaciones**, que son datos y no se deducen del
  árbol: `SUELOS_ESPECIALES = {cli/: 70}`, `EXCEPCIONES = {platform/paths.py:
  60}`. De ocho entradas a dos.
* `_cuelga_de_paquete()` separa «cuelga de un subdirectorio» de «está bajo
  `src/skillgraph/`», para que `__init__.py` y `__main__.py` (que están en
  `omit` de `pyproject.toml`) sigan sin gobernarse, y para que la
  distinción se pueda probar sola.
* La aserción que vigilaba que los ocho paquetes declarados tuvieran módulos
  **cambia de objeto**: con suelo por defecto eso es tautológico, porque los
  paquetes se derivan del árbol. Ahora vigila que lo **declarado a mano**
  exista, que es lo único que puede quedarse viejo al borrar o renombrar lo
  que nombra.
* `AGENTS.md §6.3` deja de enumerar módulos. La enumeración era una fuente de
  verdad más y ya estaba vieja: `runtime` no es un módulo sino un paquete,
  `runtime.py` no existe, y nueve de los diez vivían fuera de `core/`.

## 4. El mismo dato, el otro veredicto

Con el mismo paquete y el mismo módulo al 0 %, con el arreglo puesto:

```
== AGENTS §6.3, por modulo (suelo por defecto; el paquete no se declara) ==
  BAJO   0.00 %  (suelo  90.0 %)  src/skillgraph/telepatia/oracular.py
VEREDICTO: 1 incumplimiento(s) del contrato declarado
  - src/skillgraph/telepatia/oracular.py mide 0.00 %, por debajo de su suelo del 90 %
exit=1
```

Mismo dato, distinto veredicto: lo que cambió fue el instrumento, no la
medición.

## 5. Dos hallazgos que salieron de las mediciones, no de un test

### 5.1 Un guard que pasaba por la rama equivocada

El primer `test_la_seccion_63_no_nombra_ficheros_que_no_existen` buscaba
`[A-Za-z_]+\.py` en `§6.3` y **pasó en verde**. Motivo: `§6.3` escribe los
módulos **sin** extensión —«errors, bricks, parser, …»— y el único con punto
es `paths.py`, que se excluía a propósito. El extractor no encontraba nada, y
un test que no encuentra lo que busca no mide nada.

Es la trampa de WI-104 del revés: allí tres contraejemplos pasaron por la
rama incorrecta; aquí el test entero pasaba por ella. Se sustituyó por dos
predicados puros probados **antes** de aplicarse al documento:
`_modulos_enumerados()` contra un texto escrito en la forma real de `§6.3`, y
`_existe_como_fichero()` para distinguir un módulo de un paquete.

### 5.2 Un contraejemplo que dependía del árbol sin decirlo

`test_un_prefijo_declarado_sin_modulo_es_fallo` usaba como «paquete que no
existe» el nombre del paquete de la medición. Con el paquete ausente del
árbol mide lo que dice; con él presente, `_base()` lo recoge —porque
`_paquetes_del_arbol()` deriva del árbol—, el prefijo declarado aporta un
módulo, no hay fallo, y el test se pone rojo: `1 failed, 2724 passed`.

Un guard que depende del árbol sin decirlo es una coincidencia, y un
contraejemplo tiene que ser **incapaz de aparecer por sí solo**. El nombre
pasó a `src/skillgraph/paquete_que_no_existe/`.

Lo destapó la medición post-arreglo, que es la mejor forma que tiene de
aparecer un defecto así. En esa misma corrida, el parametrize
`test_todo_paquete_del_arbol_tiene_suelo[src/skillgraph/telepatia/]` apareció
y **pasó**: el guard nuevo funcionando sobre el árbol real, y la primera vez
que se ve en una suite completa y no en un informe sintético.

## 6. Mutaciones

Primera pasada del harness: **6/8**, con `m2` sobrevivida. Segunda pasada del
**mismo** código: **7/8**, con `m2` cazada.

Una mutación que a veces sobrevive no es un guard que no muerde: es un
experimento que no sabe qué midió. Con `PYTHONDONTWRITEBYTECODE=1` y una
**sonda por mutación** —una expresión que tiene que cambiar de valor con el
código ya mutado— las tres salidas tienen nombre:

* **cazada** — el código cambió, la sonda lo vio, los tests rojo.
* **inválida** — la sonda no cambió: la mutación no degrada la propiedad. M5
  en su primera versión quitaba una cabecera de texto y no la aserción, y el
  harness viejo la contaba como «el guard no muerde», que es una acusación
  falsa.
* **el entorno no vio la mutación** — la sonda se evalúa sobre el código viejo.
  Sin esta categoría, un `.pyc` con el segundo equivocado hace que el harness
  acuse al guard de lo que hizo el entorno.

| | qué rompe | sonda antes → después | resultado |
|---|---|---|---|
| m1 | el suelo por defecto deja de aplicarse | `90.0` → `None` | cazada |
| m2 | `_cuelga_de_paquete` devuelve `True` siempre | `None` → `90.0` | cazada |
| m3 | desaparece la precedencia de `EXCEPCIONES` | `60.0` → `90.0` | cazada |
| m4 | desaparece la precedencia de `SUELOS_ESPECIALES` | `70.0` → `90.0` | cazada |
| m5 | la desviación sin módulo avisa y no falla | `1` → `0` | cazada |
| m6 | `§6.3` real recupera la enumeración | `0` → `10` | cazada |
| m7 | `_modulos_enumerados` deja de detectar enumeraciones | `('a','b','c','d')` → `()` | cazada |
| m8 | `_existe_como_fichero` acepta un paquete | `False` → `True` | cazada |

**8/8 en tres pasadas consecutivas**, con el árbol restaurado byte a byte en
las tres (`git diff` vacío al final de cada una) y el paquete de la medición
fuera del índice y del árbol.

## 7. Certificación

**Run del código** — `332e09e6-ba0b-449e-908e-9686dd35a898`

```
pytest: 2718 passed in 238.86s (0:03:58)
== AGENTS §6.3, por modulo (suelo por defecto; el paquete no se declara) ==
== suelos declarados a mano, y si lo que nombran existe ==
  OK   todo suelo declarado a mano nombra algo que existe
  OK    86.91 %  (suelo  70.0 %)  src/skillgraph/cli/ = 11 modulos
  OK    97.98 %  (suelo  90.0 %)  src/skillgraph/runtime/ = 11 modulos
  OK    95.22 %  (fail_under = 80 %)
VEREDICTO: todo modulo gobernado por §6.3 cumple su suelo
Pipeline finished with SUCCESS
```

Verificado por `run_id`, no por la línea de salida:

```
$ mise exec -- uv run python scripts/check_pipeline_receipt.py --run-id 332e09e6-...
OK: el run cumple los criterios que declara AGENTS.md. run 332e09e6-...:
8/8 etapas, 9 pasos, veredicto 'success'. Criterio 6 (SHA-256 del
.pipeline.kts) NO se comprueba aqui: es una accion del agente, no una
propiedad del journal.
```

**Criterio 6**, registrado en la sesión y no automatizado a propósito:

```
sha256(.pipeline.kts) = 7541ced56193c9f2c846de84c7e96abff61dac7de2ed363b778a721738c2dd42
```

Sin drift: el último commit que lo tocó es `283da96` (WI-105).

**Tests**: 2718 passed, 0 skipped. La cuenta es `2703 + 22 − 7`: los 22 tests
nuevos de WI-107 menos los 7 que pierde el parametrize de WI-94, que pasa de
ocho paquetes declarados a uno declarado a mano. **La cifra mandada es la del
run, no la cuenta**: `2703 + 22` serían 2725, y el run dio 2718.

**Cobertura**: global 95.22 %, `cli/` 86.91 %, `runtime/` 97.98 %.

## 7.bis Certificación del ESTADO final

**Run** — `fdb35d26-0836-49e1-b923-4b55e6441a7e`, sobre el árbol con la
trazabilidad, el release y esta evidencia ya escritos.

```
pytest: 2718 passed in 240.06s (0:04:00)
== suelos declarados a mano, y si lo que nombran existe ==
  OK   todo suelo declarado a mano nombra algo que existe
  OK    95.22 %  (fail_under = 80 %)
VEREDICTO: todo modulo gobernado por §6.3 cumple su suelo
Pipeline finished with SUCCESS
```

Verificado por `run_id`:

```
$ mise exec -- uv run python scripts/check_pipeline_receipt.py --run-id fdb35d26-...
OK: el run cumple los criterios que declara AGENTS.md. run fdb35d26-...:
8/8 etapas, 9 pasos, veredicto 'success'.
```

Dos runs, dos objetos distintos: `332e09e6` certifica el **código**,
`fdb35d26` certifica el **estado final**. La reproducibilidad hay que
certificarla después de escribir la certificación, porque escribirla cambia
el árbol — es la lección de WI-99, y la razón de que este bloque tenga dos.

## 8. Lo que NO se arregla, y se declara

* `scripts/coverage.sh` sigue siendo una instrumentación de la suite, y
  `.pipeline.kts` la corre en el stage `unit-tests`. El suelo se comprueba
  sobre una medición que el propio CI produce: si la instrumentación se
  rompe, el suelo se relaja con ella.
* La lista de desviaciones (`SUELOS_ESPECIALES`, `EXCEPCIONES`) sigue siendo
  escrita a mano. Es deliberado: un suelo distinto del 90 % **no se deduce**
  del árbol, es un dato. Lo que se añadió es que declararlo implica vigilar
  que lo declarado exista.
* El criterio 6 del CI sigue sin automatizar, por la razón de WI-105: es una
  acción del agente, no una propiedad del journal.

## 9. Reproducir

```bash
# Medición previa y posterior, con el paquete nuevo versionado
bash .pipelinek/wi107_measure.sh          # M1-M4, ~30 s
bash .pipelinek/wi107_measure_m5bis.sh   # M5bis, suite completa, ~4 min
bash .pipelinek/wi107_measure_after.sh   # post-arreglo, exit 1 esperado

# Mutaciones (exige árbol quieto y commiteado)
bash .pipelinek/wi107_mutate.sh

# Certificación
mise exec -- pipelinek run --rerun --db .pipelinek/db.sqlite \
    --control-root .pipelinek/control .pipeline.kts
mise exec -- uv run python scripts/check_pipeline_receipt.py --run-id <run_id>
```

Los guiones viven en `.pipelinek/`, que no se versiona: son el instrumento de
la medición, no el código que sobrevive. Lo que sobrevive está en
`scripts/check_coverage_floors.py` y en
`tests/test_wi107_coverage_package_symmetry.py`.
