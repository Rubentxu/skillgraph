# Changelog

All notable changes to SkillGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
derived from the commit history via Conventional Commits.

Tipos: la regla de derivación **vive en `AGENTS.md §12` («Derivar la
versión»)**, que es su dueño. Hasta WI-96 (2026-10-02) este fichero era el
*único* enunciado de la regla, en un fichero que no es el dueño de la
gobernanza de releases, y nadie la comprobaba: con 47 etiquetas y seis bloques
de trabajo después, la regla se mudó allí, se añadió la salvedad **0.x** que
el proyecto viene aplicando desde `v0.7.0`, y ahora se calcula con
`scripts/derive_semver.py`.

## [0.32.6] - 2026-10-05 — Lo que salió al publicar: la verdad ilegible, y la release que no se contaba a sí misma

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.32.5`:
`b/f/x/n 0/0/5/2`, la regla pide **PATCH -> v0.32.6**.

Publicar es certificar. El `pre-push` corre la receta, y su `unit-tests` dio
`2 failed` sobre un árbol que la suite entera daba verde. Uno era el par de
versión de WI-109. El otro se atribuyó a un «fallo dependiente del orden» que
**no se reproduce**, y eso se nombra como no establecido, no como causa.

**LO QUE SÍ ES CIERTO, Y MEDIDO, ES ESTE.** `project_truth.py` tiene **dos**
salidas, no una, y las dos son JSON válido. La de `Estado` trae las cinco
verdades y sale con `rc` 0/1; la de `VerdadNoLegible` trae `coherente: false` e
`ilegible`, y **ninguna** de las cinco, y sale con `rc` 2. Son dos contratos, no
uno con un campo a veces ausente.

De sus consumidores, **uno** conocía la segunda forma
(`measure_b14_truth_single_reader.py`, que lee `ilegible`) y los otros dos no:

- `tests/test_b0_truth_convergence.py` hacía `carga["bloque"]` sobre las dos, y
  sobre la segunda reventaba con `KeyError: 'bloque'`. El guard que existe para
  explicar por qué el proyecto no está bien **era el que no lo explicaba**, y la
  causa estaba a mano en la misma carga.
- `measure_b9_gate_1_0.py` caía en la rama de contradicciones y devolvía
  `OPEN` con la lista **vacía**. No es que no dijera nada: **orienta mal**,
  porque `OPEN` dice «arregla el proyecto» y aquí lo que hay que arreglar es una
  verdad rota. Es el defecto de B19 entrando por otra puerta.

El veredicto nuevo es `NO_MEASURABLE`, que el vocabulario de la cabecera del
gate ya definía para esto: «no hay forma de decidirla con este entorno, y se
dice por qué». Las dos dejan 1.0 lejos —declarar `PASS` sería la única forma de
mentir—, así que no baja el veredicto: baja la **afirmación** de que el
proyecto tiene un defecto que no se ha comprobado que tenga.

**Y LA RELEASE QUE ESTE BLOQUE ACABABA DE HACER NO SE CONTABA A SÍ MISMA.**
`v0.32.5` estaba en git y fuera de `release.releases`. No era un *forgot* en una
tabla: el inventario es lo que **decide qué releases se contrastan**, y una que
no está en la lista se escapa de `test_every_listed_sha_matches_its_tag`. Una
release no listada es una release cuya provenance no mira nadie. MEDIDO, con el
sha que estaba escrito a mano en la prosa:

```
FAILED v0.32.5: dice a8c1ffaab559, git dice f3948feda480
```

El guard estaba bien; lo que faltaba era la entrada. Y con ella caían tres
afirmaciones caducadas en el mismo registro: la fila de SemVer de `v0.32.4`
citada como si fuera la de `v0.32.5`, un `tests.total` que no cuadraba con su
campo, y un comentario que afirmaba que «el guard que la lista no puede mirarlo»
—falso, y una afirmación falsa en un comentario de provenance es justo lo que
hace que nadie lo compruebe.

**Certificado** con la receta canónica, 9/9 etapas, run
`52b22437-d2ba-4654-9a16-f02ef745e9b8` verificado por su receipt:
`3416 passed + 3 skipped = 3419`. Cobertura global 95,87 % y todo módulo
gobernado por §6.3 sobre su suelo. `tests.total` 3412 -> 3419, +7.

**Harness 4/4 con 4 causas**, dos sondas sobre el guard de B0 y dos sobre el del
gate. Y con un **fallo propio del arnés**, el segundo en dos bloques: la
primera versión contaba como CAZADA cualquier `rc != 0`, y los selectores de las
dos sondas del gate estaban mal —les faltaba el `tests/`—, luego pytest salía
con 4, que es **error de uso**, y el arnés lo leía como «la sonda cayó». Un
arnés que cuenta su propio error como acierto es peor que no tener arnés: da el
número que el bloque quiere mostrar y no midió nada.

## [0.32.5] - 2026-10-05 — El gate se contradecía a sí mismo, y la razón era un sufijo

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.32.4`:
`b/f/x/n 0/0/5/12`, la regla pide **PATCH -> v0.32.5**.

**Es el hallazgo más incómodo de la serie, y no es un `PASS` falso ni un
`OPEN` falso.** B16 abrió propiedades que daban verde con el defecto presente.
B18 endureció una que ya era cierta. B19 arregló un veredicto que afirmaba más
de lo que podía sostener. B20 es otra cosa: **el gate se contradice a sí mismo.**

`ontology extensible` y `core sin dependencias de impl. externa` son dos
propiedades del mismo gate sobre la **misma frontera**. Con un solo import en
`core/` la primera daba `PASS` («no nombra ningún tipo de recurso») y la segunda
`OPEN` («depende de fuera de sí mismo»). MEDIDO sobre la superficie real, no
sobre casos inventados: **7 contradicciones de 9**.

La causa tenía las dos caras. El predicado era
`_TIPO_DE_RECURSO = ^[A-Z][A-Za-z]*Pack$`: un patrón por **forma**. No veía lo
que importa —de los ocho tipos que el proyecto *declara de verdad*, el patrón
veía **cero**, y `PackManifest` es el manifiesto de un pack, el tipo central
del proyecto— y veía lo que no importa, que era `FilaDePack`, una **fila** de
la tabla de packs. **Un patrón por forma es una lista**, más corta y peor:
decide cómo se escribe un nombre en vez de a qué conjunto pertenece.

### Fixed

- **El conjunto de tipos de recurso se deriva del árbol**, de los paquetes que
  el proyecto llama recursos, y la evidencia publica cuántos son y de dónde
  salen. Los docstrings que nombran un recurso se **dicen** sin abrir veredicto:
  documentar la frontera es lo contrario de depender de ella.
- **El techo se nombra, no se cuenta.** Tres contradicciones quedan en
  `PENDIENTES_POR_DECLARAR`, porque «qué es un recurso» no es un concepto que
  el código contenga. Antes se comprobaba `len(rotas) <= 3`, que no era
  rompible: con la implicación invertida la lista queda vacía y cero caben en
  tres.
- **Dos defectos del clasificador de docstrings**, que son el mismo defecto dos
  veces: `id(ast.get_docstring(nodo))` es el id de un *string* y no del nodo, y
  mirar solo `body[0]` pierde la documentación de los `NewType` —con lo cual el
  veredicto daba `OPEN` sobre un árbol **sano**.
- **`STATE.yaml` seguía declarando B19 mientras `CURRENT.md` declaraba B20**,
  lo que rompía la autoridad de coherencia en dos tests de la suite.
- **Los tests del guard de B16 deformaban la frontera con código que no existe.**
  `skillgraph.resources.packs` no es un módulo y `DomainPack` no es un símbolo:
  es el `kind` de un recurso escrito como cadena, un **dato de disco** tratado
  como tipo de Python. Endurecer el predicado no rompió el guard: lo destapó.
- **El hook instalado en `.git/hooks/` divergía del declarado** en
  `scripts/hooks/`: el instalado corría la suite entera y el declarado corre
  pytest solo sobre los `.py` staged. El gate que se estaba usando no era el que
  el repositorio declara, y ningún guard lo ve porque todos leen la copia
  versionada.
- **El hook de pre-commit leía el código 5 de `pytest` como un fallo.** `pytest -q <fichero de producción>` no colecta nada y sale con 5, no con 0, así que un commit que stagea solo `src/` —el bump de versión, que es lo que hace toda release— decía «el smoke falló» cuando no había nada que fallar. El 5 ahora se dice con su propia línea en vez de tratarse como verde en silencio.
- **La medición de cobertura estaba contaminada**: 282 de las 376 rutas del
  fichero de datos eran de `/tmp`, y ninguna existía ya cuando llegaba el
  informe. Eso rompía `coverage report` y `coverage json` **después** de que la
  suite entera hubiera pasado. Lo que vive fuera del árbol del repo no es
  código de este repo, y no se mide.

### Changed

- **Seis módulos cumplían por debajo del suelo que su propia ubicación declara**,
  y la etapa que lo comprueba llevaba tiempo sin poder informar. Cubierto el
  código, no bajado el suelo:

  | módulo | antes | después | suelo |
  |---|---|---|---|
  | `cli/commands/pack.py` | 46,43 % | **91,07 %** | 70 % |
  | `platform/installed_packs_repository.py` | 78,57 % | **100,00 %** | 90 % |
  | `packaging/registry.py` | 77,86 % | **98,47 %** | 90 % |
  | `presentation/views.py` | 79,26 % | **98,52 %** | 90 % |
  | `governance/graph_diff.py` | 80,00 % | **99,13 %** | 90 % |
  | `resources/status.py` | 75,31 % | **92,59 %** | 90 % |

  Cobertura global **93,68 % -> 95,87 %**.

### Verified

- Receta canónica: **9/9 etapas**, `3407 passed, 3 skipped`, run
  `fa382620-ad2c-48fd-85af-42d64f1f8097` con su receipt verificado.
- `tests.total` 3318 -> 3410.
- Guard de B20 con 3 sondas y 3 causas; guard de la cobertura con 3 mutaciones
  sobre producción, todas cazadas, y un contrasalto que dio **rojo al escribirlo**
  porque el guard leía el texto del heredoc en vez de lo que el shell produce de él.

## [0.32.4] - 2026-10-04 — «NO es reproducible» y «no he podido medirlo» son la misma frase

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.32.3`:
`b/f/x/n/d 0/0/3/6/0`, la regla pide **PATCH -> v0.32.4**.

**Es el primer bloque de la serie que no es una propiedad falsa.** B16 y B17
abrieron propiedades que daban `PASS` con el defecto presente; B18 endureció una
que ya era cierta. Aquí la propiedad **es cierta** y el defecto está en el
**verbo** del veredicto.

### Fixed

- **`distribution reproducible` acusaba al proyecto de algo que no había
  hecho.** Construye dos veces y compara los bytes; si difieren, decía «la
  distribución NO es reproducible». Y hay dos razones por las que pueden
  diferir que piden **acciones opuestas**:

  | bytes distintos porque… | quién lo arregla |
  |---|---|
  | el build es irreproducible | el **build** |
  | la entrada cambió entre las dos mediciones | la **medición** |

  Nace de un `OPEN` de 1 de 8 que salió al certificar B18, con la evidencia
  guardada: *«mismo contenido y distinta fecha dan bytes distintos en 2
  artefacto(s)»*. Y **la propiedad es cierta al revés**, medido: ocho
  construcciones con la condición exacta del predicado dan **bytes iguales 8 de
  8** —cuatro sin tocar la fecha y cuatro tocándola con `os.utime` sobre
  `src/skillgraph/__init__.py`—, y dos sdists con la suite completa de `pytest`
  corriendo en paralelo tienen **contenido idéntico**: 397 ficheros, 0
  diferencias.

  Es grave aquí de un modo que no lo era en B16: `distribution reproducible` es
  la clase de propiedad **más alta de la serie**, `ejecutada`, y la única que
  alguien podría citar para decir que el build del proyecto es irreproducible
  sin comprobar nada más.

- **No se puede resolver dentro del artefacto.** Con un fichero ya versionado
  que cambia entre las dos construcciones, los dos artefactos son coherentes
  consigo mismos y aun así se construyeron con **entradas distintas**. Hace
  falta el estado del árbol, y se toma con `_huella_de_entrada` justo antes de
  cada construcción: `HEAD`, el estado del árbol y el diff contra `HEAD`, con
  separador NUL. **El diff es lo que aporta el contenido** de lo modificado; sin
  él la huella sería un `git status` que solo ve nombres, y dos ficheros con el
  mismo nombre y distinto contenido darían la misma huella.

### Notes

- **Lo que ya existía y cubre la mitad, y no se toca.**
  `sg_build_sdist_no_versionado`, en `scripts/check_package_build.py`, rechaza
  que el paquete lleve un fichero que git no versiona, con un mensaje que es
  exactamente el que haría falta: *«el artefacto depende de lo que haya en el
  árbol de trabajo, no del commit»*. Medido, con un fichero sin versionar el
  veredicto es `OPEN` y lo dice. **La hipótesis más obvia era la buena**, y hay
  un test que lo comprueba: si el arreglo degrada en la frase acusadora un guard
  que ya era correcto, se ha roto uno bueno mientras se arreglaba uno malo.

- **La decisión se saca de la medición y por eso se prueba en milisegundos.**
  `_decide_por_bytes` es pura: dos dicts de hashes y dos huellas, sin disco ni
  reloj. Medido: dejarla dentro del predicado hacía que los tests tardaran
  **cero**, porque no se puede deformar la decisión sin deformar también la
  construcción. Un guard que no se puede deformar sin disparar el sistema
  entero no vigila la decisión: vigila que el sistema entero corra.

- **Tres fallos propios, que importan más que el arreglo.** El test **midió el
  repositorio equivocado** —lanzaba el gate del árbol real con `cwd` en el clon,
  y el gate calcula su `RAIZ` desde `__file__`— y **falló**, que es como se pudo
  ver. El contrasalto de M1 **no medía lo que decía**: comparaba el árbol limpio
  contra el editado, y `git status` ya cambia entre esos dos casos, luego no
  aislaba el contenido. Y el harness **no sabía leer su propia salida**: dio
  0 de 3 sobre tres sondas que sí habían caído, porque hacía `split()[0]` sobre
  `FAILED <fichero>::<clase>::<testo>`.

- **Un fallo mío que es parte del hallazgo.** La primera vez que vi el `OPEN`
  solo leí el nombre de la propiedad en un resumen y volví a ejecutar el gate:
  **no guardé la evidencia**. El primer instrumento dio 6 de 6 `PASS` — bien
  ejecutado, midiendo la pregunta equivocada, porque sin el texto del fallo no
  se sabe qué preguntar. Guardar la evidencia del fallo es lo que convirtió un
  número raro en un diagnóstico.

- Harness **3/3 con 3 causas**, cada una cayendo solo su diagnóstico, y con los
  diagnósticos verificados contra `pytest --collect-only` y no contra una lista
  escrita en el propio harness. Gate: **18 PASS / 1 OPEN / 1 NO_MEASURABLE**.
  `tests.total` 3312 -> 3318.

## [0.32.3] - 2026-10-04 — la frontera del núcleo no miraba la mitad de la superficie, y su verdad estaba escrita a mano

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.32.2`:
`b/f/x/n/d 0/0/1/5/0`, la regla pide **PATCH -> v0.32.3**.

**Es la cuarta de las siete propiedades que B15 nombró**, y la que B17 dejó
escrita como «la primera que habría que mirar de las que quedan». El predicado
es `core sin dependencias de impl. externa`, y es el único del gate cuya
mirada está **declarada en su propia evidencia** — lo que declara no era lo que
miraba.

### Fixed

- **Los imports relativos no se miraban.** `_imports_de` exigía
  `nodo.level == 0`, y como `core/` está en `src/skillgraph/core/`, un
  `from ..platform.storage import Storage` tiene nivel 2 y **sale de `core/`
  entero**. Medido, con ese import de verdad en una copia del árbol y el repo
  real intacto, el veredicto era `PASS` con una evidencia **byte a byte
  idéntica** a la del caso limpio:

  ```
  MEDIDO A · se añade a core/ un `from ..platform.storage import Storage` (relativo, nivel 2)
    veredicto : PASS
    evidencia : core/ no depende de fuera de si mismo, MEDIDO sobre ... (5 modulos)
    — byte a byte IDÉNTICA a la del caso limpio
  ```

  Un veredicto que no puede distinguir «el núcleo está limpio» de «no he mirado
  la mitad de la superficie» no es un veredicto. Y medido también: `core/` **no
  usa hoy ningún relativo**. La superficie estaba vacía, y una superficie vacía
  no se mira porque no hay nada que mirar — el defecto era invisible no porque
  fuera difícil de ver, sino porque no había nada que lo activara.

- **La estándar eran trece renglones escritos a mano; el intérprete sabe de
  290.** Faltaban `pathlib`, `contextlib`, `abc`, `io`, `warnings` y `copy`, y
  un `import pathlib` legítimo en `core/` producía un `OPEN` sobre una frontera
  que se estaba respetando. Una propiedad que se pone roja por lo contrario
  entrena a su lector a no creerla, y eso es un fallo aunque salga del lado
  conservador. **Y la lista no contenía ni un nombre falso: era correcta y
  estaba vieja.** Una lista de trece que se queda vieja no avisa: simplemente
  empieza a dar veredictos que nadie revisó.

- **La evidencia decía «(5 modulos)» sobre un paquete de cuatro ficheros.**
  Contaba nombres de import **distintos**, no módulos, y no decía cuántos
  ficheros se habían recorrido. Una evidencia que no describe lo que recorrió
  no permite saber si el recorrido estaba completo.

  Los tres son la misma cosa escrita de tres maneras: el predicado no sabía
  qué superficie recorría ni de dónde salía su verdad. Ahora los relativos se
  resuelven a nombre **absoluto**, `_MODULOS_ESTANDAR` se **deriva** de
  `sys.stdlib_module_names`, y la evidencia dice cuántos ficheros se
  recorrieron y de dónde sale la lista. La de `core` pasa a ser:

  ```
  core/ no depende de fuera de si mismo, MEDIDO sobre 4 ficheros y 5 imports
  ABSOLUTOS Y RELATIVOS, ya resueltos a su nombre: todos son de skillgraph.core
  o de la estandar segun sys.stdlib_module_names, el conjunto que declara el
  propio interprete (Python 3.13) (193 modulos de estandar reconocidos)
  ```

### Notes

- **Lo que este predicado no hace, a propósito: no prohíbe los relativos.**
  Que `core/` escriba `from .errors import ...` es **correcto**, y obligarle a
  escribir la forma absoluta para que un predicado lo vea es *cambiar el código
  para que el guard quede bien*. Lo que faltaba era mirarlos. Un predicado que
  obliga al código a la forma que él sabe leer no vigila la frontera: la vigila
  él.

- **Dos defectos propios, cazados por el guard de este bloque al escribirlo, y
  que habrían pasado un 6/6.** El filtro de privados se llevaba `__future__` —
  un falso `OPEN` visible **solo gracias a la evidencia nueva**, que por una
  vez describía lo que había recorrido; sin ella habría sido indescifrable —, y
  `_paquete_de` devolvía el **módulo** en vez del **paquete**, con lo que el
  recuento se movía de 5 a 6 y el defecto quedaba entero, con un número que
  parecía correcto.

- **Requisito nuevo del harness: la deformación tiene que parsear.** Una
  deformación que rompe la sintaxis hace caer la suite **por no importar**, no
  por detectar — parece la sonda más fuerte y no ha detectado nada. El mismo
  error ha salido en B16, B17 y B18 con tres síntomas distintos, y el más caro
  de B18 fue silencioso. Un error que se repite tres veces con distinta
  apariencia no es un error: es una clase de error, y se cierra con un
  requisito del arnés, no con cuidado. Harness **3/3 con 3 causas**, cada una
  cayendo solo su diagnóstico.

- **La clase de la propiedad no cambia, y es lo correcto.** Sigue siendo
  `derivada`: el predicado sigue decidiendo leyendo el árbol. B18 endurece una
  medición que **ya era cierta** — `core/` no dependía de fuera de sí mismo
  hoy, con o sin estos cambios —, no una propiedad que fuera falsa como las de
  B16. Gate: **17 PASS / 2 OPEN / 1 NO_MEASURABLE**.

- `tests.total` 3306 -> 3312. Suite certificada: **3309 passed, 3 skipped** en
  281,80 s.

## [0.32.2] - 2026-10-04 — el ciclo de vida de los packs se decidía contando nombres

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.32.1`:
`b/f/x/n/d 0/0/2/6/0`, la regla pide **PATCH -> v0.32.2**.

**Es la tercera de las siete propiedades que B15 nombró**, y la más fácil de
las que quedan por una razón que no es de estilo: **el instrumento que hace el
trabajo ya estaba escrito y no se estaba usando.**

`scripts/measure_b11_pack_lifecycle.py` responde **cinco** preguntas y cada una
**ejecuta la CLI de verdad** en un proyecto temporal, con su propio código de
salida. El gate no lo llamaba. Decía

```
`sg pack` expone el ciclo completo: ['import', 'install', 'list', ...]
```

y su único trabajo era mirar si tres **cadenas** estaban en un `dict` que sale
del parser.

### Fixed

- **`pack/controller lifecycle` se decidía por los nombres de sus subcomandos.**
  Medido antes de escribir una línea, sobre copias del árbol con el repo real
  intacto, rompiendo la **decisión** y no el sitio donde se mira — el `if` que
  levanta `ValidationError` cuando `motivos_de_incompatibilidad` devuelve
  motivos, y **no** `es_compatible`, que es la verdad del dominio:

  ```
  MEDIDO A · install deja de rechazar un pack incompatible
    gate   : PASS    <- leía NOMBRES
    B11 Q1 : PASS    <- leía NOMBRES, y es LITERALMENTE el predicado del gate
    B11 Q2 : OPEN    <- EJECUTABA install con un pack incompatible
    resumen: OPEN: 1 · PASS: 4
  ```

  **El ciclo de vida estaba roto y la propiedad que lo declara estaba en
  verde.** Ahora el predicado **ejecuta** el instrumento y decide por su código
  de salida —la forma de B12 para `upgrade desde releases soportadas`—, y la
  evidencia pasa a ser el veredicto de las cinco preguntas nombrando cuál cae.
  La clase de la propiedad pasa de `derivada` a **`ejecutada`**.

- **Un defecto propio, cazado por el guard de este bloque al escribirlo.** Con
  el instrumento sin arrancar, el predicado decía *«se ha EJECUTADO para
  saberlo»* y *«Caen 0 de 0 preguntas»*. No se había ejecutado nada: `rc=2`,
  «can't open file». Publicaba una ejecución que no había ocurrido, con la
  autoridad de quien sí la hace. Ahora **«¿el ciclo se sostiene?»** y **«¿puedo
  medir si se sostiene?»** son dos veredictos distintos, que es la misma
  separación que B14 cerró en `tests_colectados()`.

### Notes

- **Y el hallazgo más incómodo no es del gate: era Q1 del propio instrumento.**
  El predicado del gate **era** Q1 de las cinco, y Q1 es la más débil, porque
  las otras cuatro ejecutan. El gate llevaba tiempo decidiendo «el ciclo de
  vida existe» con **la única de las cinco preguntas que no lo prueba**. Q1 no
  se toca en este bloque y el motivo está escrito: «¿existen los comandos?» es
  una condición necesaria y es barata; lo que no puede hacer es **bastar**, y
  con las cinco en AND deja de bastar. Cambiarla sin un instrumento que la
  reemplace sería perder cobertura.

- **M6 es la sonda que hace que las otras cinco valgan.** No deforma el gate:
  deforma el **instrumento** que el gate ejecuta, neutralizando Q2, y exige que
  el gate caiga. Si el único defecto posible fuera «el gate dejó de mirar»,
  bastaría comprobar que el gate llama al instrumento, y un guard así solo sabe
  mirar su propio teléfono. M6 cayó, luego la cadena **decisión → instrumento →
  gate** se sostiene entera y no solo el cable. Harness **6/6 con 6 causas**.

- **La autocomprobación del harness cazó dos sondas suyas.** Una **no medía lo
  que decía medir**: la primera versión de M1 añadía una comprobación de
  nombres delante de la llamada y dejaba seguir al instrumento, así que daba
  5 de 5 en verde con el defecto puesto. Y la otra **no existía**: sus anclas
  se partieron en trozos de cadena y el nombre del fichero se quedó sin
  comillas, luego el ancla no estaba en el fichero. Sin el «el ancla aparece 0
  veces» el 6/6 habría sido un número sobre seis deformaciones que no
  deformaron nada.

- `tests.total` 3301 -> 3306.

## [0.32.1] - 2026-10-04 — dos propiedades del gate daban PASS sin nada que comparar

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.32.0`:
`b/f/x/n/d 0/0/4/4/0`, la regla pide **PATCH -> v0.32.1**. Cuatro `fix` y
cero `feat`: este bloque no añade superficie, quita dos formas de dar verde
sin mirar nada, y arregla un defecto de producción que encontró al medir.

**El hallazgo.** B15 dejó nombradas siete propiedades del gate de 1.0 que se
deciden leyendo el árbol, y cuyos PASS no se pueden retirar solos. Esa lista no
era una cola de tareas: era **la medida de dónde el gate no sabe lo que dice
saber**. Esta abre las dos primeras, y no eran débiles. **Eran falsas.** Medido
antes de escribir una línea, sobre copias del árbol con el repo real intacto:

```
MEDIDO A · se renombra la constante a _CAPABILITY_VERSION en todo src/
  veredicto : PASS
  evidencia : CAPABILITY_VERSION se declara en un solo sitio: []

MEDIDO B · core/ importa DomainPack de verdad
  veredicto : PASS
  evidencia : core/ no nombra ningun tipo de recurso: se anaden sin tocarlo
```

La primera es **un PASS cuya evidencia dice una lista vacía**: un veredicto
sobre la capacidad de contar del propio instrumento, no sobre el proyecto. La
propiedad era cierta por suerte del caso —la constante existe en un sitio— y
no por lo que el gate midió.

La segunda es **la fuga de B13 con el signo cambiado**. Allí el guard leía
literales en vez de la consulta ensamblada y daba verde **con la fuga
presente**; aquí leía cadenas en vez de los imports y daba verde **con la
dependencia presente**. Y lo que se declara es una frontera arquitectónica —el
núcleo no depende de los recursos, así que añadir un recurso no obliga a
tocarlo— que **nada vigilaba**.

### Fixed

- **`capabilities deterministas` daba verde con cero declaraciones.** Su lógica
  era «si hay más de uno, `OPEN`; si no, `PASS`». Ahora cero declarantes es
  `OPEN` nombrando el hecho, y la detección pasa a ser **AST**: el `re.match`
  por línea no veía un `AnnAssign` —la forma real de hoy es
  `CAPABILITY_VERSION: Final[str] = "v1"`—, ni una declaración partida, ni una
  dentro de una clase.

- **La misma comprobación no exigía el sitio.** La propiedad dice «**el
  puerto, y solo el**», y la mitad de «y solo el» no estaba medida: bastaba con
  que no hubiera dos declarantes. Una constante que todos importan desde un
  fichero que no es el puerto sigue siendo una segunda fuente de verdad, con
  una palabra menos.

- **`ontology extensible` no veía una dependencia real de `core/`.** Buscaba
  `^[A-Z][A-Za-z]+Pack$` dentro de **constantes de cadena**, y un
  `from ... import DomainPack` es un `Name` del AST. Ahora decide sobre
  **imports**, sobre **atributos** —`packs.DomainPack`, que es la forma
  indirecta que se escribe cuando ya se sabe que el núcleo no debería saber del
  recurso— y también sobre las cadenas.

- **Un defecto de producción que no era de este bloque: ocho procesos que
  abren la misma base se mataban entre ellos.** Lo encontró `concurrencia real
  certificada` al pasar de `PASS` a `OPEN`, y no era ruido del medidor: cuatro
  corridas rojas de veinte, y un hijo muerto de treinta con

  ```
  sqlite3.IntegrityError: UNIQUE constraint failed: schema_version.version
  ```

  Ocho procesos abren la misma base nueva, los ocho leen `MAX(version) == 0`,
  los ocho deciden subir, y el segundo `INSERT` se lleva un `UNIQUE` sobre la
  PRIMARY KEY y **muere antes de escribir un solo evento**. El `timeout` que
  arregló el `PRAGMA journal_mode` en B2 no lo puede arreglar, y conviene decir
  por qué: no es un candado esperando, es un `SELECT` seguido de un `INSERT`, y
  entre los dos cabe otro proceso. La respuesta era la que ya estaba quince
  líneas más arriba del mismo archivo, en las migraciones: **`INSERT OR
  IGNORE`**, una sola sentencia idempotente y sin el `DELETE` que abría la
  ventana. Tasa del test concurrente: **4/20 -> 0/25**.

- **El hijo de la concurrencia no encontraba su propio código.** Calculaba
  `RAIZ` con `.parent.parent`, correcto mientras vivía en `.pipelinek/` y
  falso desde que se movió a `tests/fixtures/`: ahí `.parent.parent` es
  `tests/`, luego metía `tests/src` en el path, que no existe. Solo podía
  importar `skillgraph` porque el paquete está instalado en el intérprete que
  lo lanza —una red de seguridad accidental—.

- **El aserto que tiraba el diagnóstico.** El test que mide el solape real
  descartaba el `stderr` del hijo y se quedaba en «rc=1». Sin él, un
  `IntegrityError` de la migración se leía como un fallo de concurrencia del
  arnés.

### Removed

- **Un test que afirmaba reproducir la carrera y no la reproducía.** Se
  construyó con dos conexiones y con un `set_trace_callback` que mete al
  hermano entre el `DELETE` y el `INSERT`, y **pasaba con el defecto presente**
  en los dos casos: con el método simple porque el `DELETE` de este proceso se
  llevaba la fila del hermano, y con el `trace_callback` porque SQLite
  **serializa a los escritores** y lo bloquea hasta agotar el `busy_timeout`
  —medido, 5,07 s frente a 0,15 s—. La carrera es real y **no es alcanzable de
  forma determinista desde Python**. Un guard que solo sabe dar verde fabrica
  confianza justo donde no la hay, así que el test se retiró y lo que queda es
  el guard de **forma**, que sí cae con el defecto puesto.

### Notes

- **El harness del bloque cazó dos sondas suyas que no median**, y las dos son
  la misma clase de fallo que B13 y B14 cerraron: leer un recuento de una
  colecta que no terminó —el módulo de test **importa** el hijo, luego el
  `assert` del hijo tumba la colecta entera y pytest lo reporta como `ERROR`,
  no como `FAILED`, y un arnés que solo mira `FAILED` convierte «todo ha caído»
  en «no ha medido nada»— y agrupar las suites como cadenas en vez de como
  tuplas. Se cuentan porque el número 6/6 no significa nada si el instrumento
  que lo produce ya se sabe que miente en dos sitios.

- **El estado del gate no cambia de veredicto.** Las dos propiedades reales
  siguen en `PASS` —con evidencia que ahora sí dice lo que comprueba— y
  `concurrencia real certificada` pasa a **5 de 5**. Lo que queda abierto es lo
  de siempre: `runtime real certificado` exige `SG_UAT_REAL_PROVIDER=1` y una
  credencial real, y `TUI operacional` exige una persona.

- `tests.total` 3294 -> 3301.

## [0.32.0] - 2026-10-04 — un predicado que se declara leyendo código no sabe cuándo deja de medir

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.31.2`:
`b/f/x/n/d 0/2/1/7`, la regla pide **MINOR → v0.32.0**. Dos `feat`: el gate
declara la clase de su propia evidencia, y existe el medidor que la mide.

**El hallazgo.** El gate de 1.0 declara veinte propiedades, y sus veinte PASS
salían en la misma lista y con la misma tipografía. **No había manera de saber
cuáles estaban respaldados por algo que se ejecuta y cuáles por una lectura del
árbol.** La diferencia no es estética: es si el veredicto **puede volverse falso
sin que nadie vuelva a mirarlo**. Medido, derivado del AST del propio gate:

```
ejecutada  13      derivada  7
```

### Fixed

- **`distribution reproducible` decía PASS sin comprobar que fuera
  reproducible.** Su evidencia entera era *«el wheel y el sdist se construyen y
  llevan lo que declaran»*, y eso prueba que **se construyen**. Reproducible es
  que las mismas entradas den los mismos bytes, y un único build no puede
  distinguir «reproducible» de «esta vez salió bien».

  Medido antes de arreglar, con una prueba que tiene dientes: se construye, se
  espera a que el reloj avance, se toca el mtime de un fuente con contenido
  **idéntico** y se construye otra vez. Los sha256 coinciden —hatchling normaliza
  las fechas—. La propiedad **era cierta**; lo que no existía era nada que
  pudiera quitársela.

  Y por qué la prueba toca la fecha, que es lo que la hace no ser decoración:
  construir dos veces seguidas no prueba nada. Si el reloj no tick entre las
  dos, los timestamps coinciden aunque el build sea irreproducible.

### Added

- `Propiedad.clase_evidencia` — cada propiedad del gate declara si su evidencia
  es `ejecutada` o `derivada`, y la clase se **deriva** siguiendo el grafo de
  llamadas del módulo hasta un `subprocess`. El campo es `init=False`: no hay
  forma de declararla a mano. Veinte líneas escritas a mano serían una segunda
  fuente de verdad que divergiría en silencio — WI-106 y WI-99, dos veces más.
- `scripts/measure_b15_evidence_kind.py` — mide la línea base y deja **nombrada**
  la lista de las siete propiedades que no se pueden retirar solas, que es lo que
  permite ordenar el trabajo siguiente sin inventarlo. Con
  `--autocomprobacion`: **13 de 20 clases giran** al quitarle el `subprocess` al
  módulo entero.
- `scripts/mutate_b15_evidence_kind.py` — **6 sondas, 6/6 cazadas con 6 causas**.
- `tests/test_b15_evidence_kind.py` — **9 tests** en cuatro conjuntos disjuntos.

### Changed

- Gate de 1.0 **sin cambios de veredicto**: 18 PASS / 1 OPEN / 1 NO_MEASURABLE,
  ahora con la clase de cada una. `tests.total` 3285 → 3294, +9, fichero nuevo
  entero; lo falló el propio guard de WI-115 con el texto `tests: STATE declara
  3285, el arbol colecta 3294`, que es exactamente para lo que existe.

### Lo que el bloque encontró en su propia casa

La primera versión de la derivación devolvió **veinte de veinte `derivada`**, con
la autoridad de un `print` y sin una sola advertencia. Los predicados se
registran en `PREDICADOS` como `_` + slug, la función buscaba el slug a secas, no
lo encontraba, y **devolvía un valor por defecto** en vez de decir «no lo sé».
Seis de esos predicados sí lanzan subproceso.

> Es el mismo hallazgo que B13 cerró en el guard de SQL —que leía literales en vez
> de la consulta ensamblada— y que B14 encontró en los guards atados a un valor
> vivo y en las tres mutaciones no-op de su medidor. **Un guard que se declara
> leyendo el código no sabe cuándo deja de medir.** Y aquí apareció en el código
> del propio bloque, y lo primero que produjo fue, en su casa, el falso que venía
> a cerrar.

**Y un dato de la misma línea, medido.** Al buscar un PASS falso
—`blueprint legacy completamente probado`, que cuenta cobertura de UAT con un
`re.findall` sobre el texto de los tests— se construyeron cuatro sondeos para
comprobarlo. **Los cuatro fallaron, cada uno en una dirección distinta**, y tres
de ellos dieron `0 de 12`, `9 de 12` y `3 de 12`. El PASS era cierto:
`tests/uat_audit.py` tiene una función completa por UAT, con directorios
temporales, la CLI de verdad y aserciones. El predicado es débil; la propiedad es
cierta, y queda anotado con su debilidad, que es información y no deuda fingida.

## [0.31.2] - 2026-10-04 — la autoridad de coherencia se podía engañar, y se engañó

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.31.1`:
`b/f/x/n/d 0/0/7/11`, la regla pide **PATCH → v0.31.2**. B14 no añade
capacidad: endurece el verificador del que dependen B0..B13, y un arreglo de
integridad del instrumento es lo que un PATCH describe.

**Qué era, medido, no hipotético.** Al cerrar B13 se añadió una segunda clave
`current_workitem` en `STATE.yaml`. Seis ficheros de test leían el estado con
`yaml.safe_load` —que se queda con la clave repetida por la última— y
`scripts/project_truth.py` lo leía entero con regex —que se queda con la
primera—:

```
yaml.safe_load          -> B13_cerrado
regex de project_truth  -> B13
project_truth           -> coherente: true, contradicciones: []
```

Un verificador que dice «coherente» cuando no lo está es **peor que no tener
verificador**, porque las dos mitades de la propiedad se apoyan en él.

### Fixed

- **`STATE.yaml` tiene UNA lectura.** Se lee una vez con `yaml.safe_load`, en
  vez de con tres regex que cada una puede encontrar otra cosa. Un loader
  **rechaza claves duplicadas en el punto de lectura** —no después con un guard,
  que sería un segundo lector, que es el problema—, y comprueba el **tipo** de
  `release.tag`, `tests.total` y `roadmap.current_workitem`.

  Con el constructor retirado, el mecanismo **no lanzaba nunca**: `_construye`
  llamaba a `construct_mapping(...)` y luego miraba `Mapping.items()`, y
  `construct_mapping` ya devuelve un dict donde la clave repetida se colapsó.
  El bucle veía **una** clave, no dos.
- **Un recuento de una colecta que no terminó no se publica.** Con
  `src/skillgraph/__init__.py` mutilado, pytest imprime «2867 tests collected,
  27 errors» y sale con `rc=2`. Ese número es real —son los tests que llegó a
  ver— pero no es **el** recuento, y `tests_colectados()` lo publicaba con su
  nombre: *«tests: STATE declara 3284, el arbol colecta 2867»*. Sin 417 tests y
  sin decir por qué. Ahora se niega a leerlo.

### Added

- `tests/test_b14_truth_single_reader.py` — **14 tests** en cinco conjuntos
  disjuntos. El contrato de la clave duplicada es **ILEGIBLE nombrando la
  clave**, no «el veredicto cambia»: sin el constructor el verificador elige una
  de las dos declaraciones y la publica como la verdad, atribuuyendo la otra a
  otro fichero, y un test de «cambia el veredicto» pasa.
- `scripts/mutate_b14_truth_single_reader.py` — **6 sondas, 6/6 cazadas con 6
  causas distintas**. El harness rechaza arrancar si un diagnóstico no existe o
  si un ancla no es única, y ahora también **dice qué intérprete necesita**
  cuando se lanza con uno que no es el del proyecto.
- `scripts/measure_b14_truth_single_reader.py --autocomprobacion` — deforma el
  verificador de verdad y exige que las preguntas se caigan. **3/3 cazadas**.
  Sin esto, un 8/8 que no puede ponerse en rojo no es un 8/8.

### Changed

- **La línea base de B14 era 7 de 8 y ahora es 8 de 8**, y el instrumento que
  la produce tiene su propia contramutación.
- El gate de 1.0 queda **sin cambios: 18 PASS / 1 OPEN / 1 NO_MEASURABLE**, que
  es lo correcto: B14 endurece la autoridad de coherencia de B0, no una
  propiedad de 1.0.

### Lo que el bloque encontró en sí mismo, y que importa más que el arreglo

Cinco instrumentos se satisfacían por una causa ajena a la que decían medir, y
un instrumento dejó el verificador cojo. Ninguno de los seis salió de una
lectura del código: los manifestó el harness o la sonda.

- **Dos guards de los tests atados a `current_workitem: B13` escrito a mano.**
  Al mover el bloque vivo a B14 los dos dejaron de mutar nada. Un contrasalto
  que se desactiva al cambiar el calendario ya no es un contrasalto.
- **La medición tenía tres mutaciones no-op** e imprimía 5/8 diciendo que el
  arreglo recién hecho no funcionaba. Lo que estaba roto era el instrumento.
- **Tres de sus ocho preguntas pedían «no es coherente»**, que lo cumple un
  módulo roto igual que un módulo que dejó de mirar.
- **`RAIZ` era una ruta absoluta de esta máquina**: el instrumento mutaba
  ficheros de un árbol que podía no ser el suyo.
- **La sonda M1 no medía el guard que decía vigilar**: referenciaba una
  constante que B14 había borrado, el módulo reventaba con `NameError` y caían
  los diez tests, ninguno el diagnosticado. El harness la declaró INVÁLIDA.
- **La primera ejecución de `--autocomprobacion` reventó a mitad y dejó
  `project_truth.py` sin el constructor**, con el repo entero en
  `coherente: false`. La red que verifica por sha256 no cubría el fichero que el
  instrumento más deforma; ahora `scripts/project_truth.py` entra en `MUTABLES`.

Con la deformación puesta, la sonda 3 deja ver el defecto central a la vista:

```
"coherente": true,  "contradicciones": [],
"workitem_current": "B14",  "workitem_state": "B99"
```

El verificador publicando como coherente un estado en el que `STATE` y
`CURRENT` dicen cosas distintas. Eso, y no el arreglo del loader, es lo que B14
existía para cerrar.

## [0.31.1] - 2026-10-04 — el modelo de amenaza afirmaba que no había fuga, y había una

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.31.0`:
`b/f/x/n/d 0/0/2/0`, la regla pide **PATCH → v0.31.1**. Es la tercera y última
`OPEN` del gate de 1.0 que no depende de credencial ni de persona.

### Fixed

- **Fuga cross-tenant en `platform/knowledge_repository.py::list_resources`.**
  El filtro de `kind` se armaba como `AND api_version || '/' || kind = ? OR
  kind = ?`, sin paréntesis. En SQL `AND` liga más fuerte que `OR`, luego la
  segunda mitad del `OR` hacía opcional el `tenant_id` **y** el `project_id`.
  Medido antes de corregir: un tenant que no tiene nada pide sus `DomainPack`
  y recibe los de otro. Era alcanzable desde la CLI.

  B11 encontró este defecto y no lo arregló, porque esquivarlo era lo
  correcto para su bloque: necesitaba aislamiento fila a fila. Lo que falló es
  que la puerta se quedó abierta y el ADR-0015 la declaraba **cerrada**.

### Changed

- **ADR-0015 reescrito.** Una sección `## Superficies` con una fila por cada
  uno de los 10 paquetes de `src/skillgraph/`, cada una nombrando el fichero
  de evidencia que la sostiene. Se añaden **S9** (packs instalables) y **S10**
  (libro de migraciones), que son fronteras de confianza que el modelo no
  mencionaba. Tres contradicciones resueltas, la tercera encontrada al
  reescribirlo: el documento decía que «no introduce cambios de código», y el
  bloque que lo revisaba acababa de corregir una fuga.
- **La vigencia del gate deja de medirse con un número de tests** y pasa a
  **ejecutar** `tests/test_b13_threat_model.py`, verificado en las dos
  direcciones con causas distintas.

### Added

- `tests/test_b13_threat_model.py` — 17 tests en cinco conjuntos disjuntos.
  El guard de SQL captura la consulta **ensamblada** por
  `set_trace_callback`, no los literales: la primera versión daba verde
  **con la fuga presente**, porque `WHERE` y `OR` están en literales distintos.
- `scripts/mutate_b13_threat_model.py` — 6 sondas, **6/6 cazadas con 6 causas
  distintas**. Dos nacieron rotas y las cazó el propio harness: una declaraba
  sus diagnósticos con el nombre de la clase mal escrito (y `caidos &
  esperados` no está vacío mientras caiga *uno* de los dos), y otra usaba un
  ancla que aparece dos veces. El harness ahora rechaza arrancar si un
  diagnóstico no existe o si un ancla no es única.

### Certification

- Gate de 1.0: **17 PASS / 2 OPEN / 1 NO_MEASURABLE → 18 / 1 / 1**.
- `tests.total` 3254 → **3271** (+17, el fichero nuevo entero).
- Suite: **3268 passed, 3 skipped, 0 failed**.

## [0.31.0] - 2026-10-04 — la versión del esquema era una constante, y por eso el upgrade era imposible

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.30.0`:
`b/f/x/n/d 0/1/1/5/0`, la regla pide **MINOR → v0.31.0`.

Es la segunda de las `OPEN` del gate de 1.0 que piden **código, no
certificación**. El predicado decía, textual: *«no existe ninguna función
de upgrade o de migración de datos entre releases: no hay de dónde subir una
base creada por una versión anterior»*.

La medición dijo que el problema era más profundo que «falta la función».
`SCHEMA_VERSION` era `1` desde WI-65, con 73 releases encima; se escribía
con `INSERT OR IGNORE` y **no se leía en ningún sitio de `platform/`**. Y el
dato que resume el bloque: **borrar la tabla `schema_version` entera de una
base y abrirla no daba ningún error**, porque el código la recreaba. Una
versión que se regenera cuando falta es un `DEFAULT`, no un hecho.

**Medido antes de escribir una línea: 0 de 5 preguntas abiertas.** Al final,
**5 de 5**, con un instrumento que **ejecuta** y no mira nombres.

### La decisión de diseño: el libro registra, no gobierna

`sincroniza` ejecuta **todas** las migraciones y anota las que faltaban.
Podría haber guardado ejecutando solo las pendientes, y sería más eficiente.
Se eligió lo contrario por el caso que de verdad duele: una base restaurada
de una copia parcial tiene el libro atrasado **y** el esquema con una columna
que falta a la vez, y un libro que gobierna se creería que está bien y no
repararía nada.

El límite de la decisión está escrito en el código: una migración que
transforme **datos** en vez de comprobar una precondición sería cara de correr
en cada apertura, y cuando llegue tendrá que marcar su propio criterio de
«ya aplicada» en vez de que `sincroniza` vuelva a hacer de puerta sin avisar.

### Una regresión que este bloque introdujo y corrigió, medida

La primera versión hacía `DELETE FROM schema_version` + `INSERT` **siempre**.
Antes era `INSERT OR IGNORE`, que tras la primera apertura no escribe nada,
luego abrir una base era una *lectura*. Con el `DELETE` incondicional, ocho
procesos concurrentes se repartían mal el turno de escritura: *«se esperaban
8 autores distintos y hay 7»*. Medido antes de arreglar: tres corridas dan
verde, verde y **rojo**.

El contrasalto que lo vigila mide `total_changes`, que es **determinista** —
abrir una base al día da 0, subir una atrasada da 1 — porque contar
ejecuciones verdes de un test de concurrencia sería una tirada, no una prueba.

### Un predicado del gate que mentía en la dirección contraria

«upgrade desde releases soportadas» buscaba `def upgrade` con un regex. La
capacidad se llama `sincroniza`, luego este bloque habría entregado la
capacidad **y el gate habría seguido diciendo `OPEN`**: un falso **negativo**,
la misma clase que el falso positivo de B9 con el signo cambiado. Ahora el
predicado **ejecuta** el medidor y decide por su código de salida, y se
verificó en las dos direcciones: capacidad entera da `PASS`, libro roto da
`OPEN 3/5`.

### Lo que este bloque **no** dice que haya medido

Que una base creada por una release de hace dos años conserve su contenido. La
base «vieja» del medidor se **reconstruye** quitando lo que esa release no
conocía; no es una base real de una release real. Lo que sí se mide es que se
abre, se sube, se versiona y no pierde filas. La distancia entre «una base
vieja se abre» y «una base vieja conserva lo que tenía» es la que un upgrade
mal hecho pierde sin avisar.

**Gate de 1.0: 16 PASS / 3 OPEN / 1 NO_MEASURABLE → 17 / 2 / 1.**
`tests.total` 3254, +21 con el desglose medido por diff de ids. Harness 5/5
con 5 causas distintas, y **una sonda nació rota** — M4 apuntaba a una línea
que `ruff format` había movido, y el harness la reportó `[SIN SONDA]` en vez
de contarla como verde.

## [0.30.0] - 2026-10-04 — el ciclo de vida de los packs, que era un nombre en un gate

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.29.0`:
`b/f/x/n/d 0/1/2/5/0`, la regla pide **MINOR → v0.30.0**.

Es la primera de las cuatro `OPEN` que quedaban del gate de 1.0 y que piden
**código, no certificación**. El predicado del gate decía, textual: `sg pack`
expone `['import', 'load']` y no `['install', 'update', 'remove']`. B8 entregó
el **contrato** —`PackManifest`, `Requires`, seis tipos, tres niveles de
aislamiento, `es_compatible` con **motivos**—; faltaba la mitad: saber **qué
hay instalado**.

### Un defecto de producción, y es el que hacía el `update` imposible

`upsert_resource` **rechaza** cambiar el `spec` bajo la misma identidad con
`IdentityConflictError` —deliberado, es lo que hace un recurso inmutable—, y
un update de pack es por definición un `spec` distinto bajo la misma
identidad. Con el registro encima de `resources`, el `update` no tendría dónde
escribir.

No es un bug heredado: es que **una instalación no es un recurso**. El recurso
es el *contenido* del pack; la instalación es el *hecho* de que ese pack esté
vivo en este proyecto, y ese hecho tiene su propio ciclo. De ahí la tabla
`installed_packs` y su repositorio propio.

`retirar` **no borra: marca**. Un `DELETE` perdería la única respuesta que
existe a «¿este proyecto ha tenido alguna vez este pack?», porque el único
sitio donde vive la respuesta es la fila que se borra.

### Y un filtro que no filtra

`list_resources` construye su filtro de `kind` como
`AND api_version || '/' || kind = ? OR kind = ?`, **sin paréntesis**: el `OR`
se come el `AND` que lo precede. Delegar el aislamiento ahí habría costado una
fuga entre tenants, así que se comprueba fila a fila y hay dos guards que lo
verifican en las dos direcciones.

### Qué se entrega

- `sg pack install|update|remove|list`. `install` rechaza un pack incompatible
  **nombrando la cláusula**; `update` exige que la versión suba y la compara
  **por número** (`0.10.0` > `0.9.0` como número y `<` como texto); `remove` de
  lo que no está lo dice **con la lista de lo que sí**; `list` responde
  versión y aislamiento.
- `skillgraph.packaging.registry` con `instalar`, `actualizar` y `retirar` como
  funciones **puras** sobre un registro inmutable.
- El manifiesto de B8 viaja en `spec.manifest` del propio pack: `spec` es la
  única parte que el tipo `DomainPack` acepta, y así se unifican los dos
  contratos en vez de crear un tercero.
- 20 tests, y un harness de mutación **6/6 con 6 causas distintas**.

### El harness volvió a destructirse, y por eso lleva un guard nuevo

`MUTABLES` no incluía `installed_packs_repository.py`, así que esa sonda mutó el
fichero y no lo restauró — y el harness reportó **«árbol restaurado y ejecutando
como estaba»** porque **la suite seguía verde**. Es el fallo de B9 repetido con
otro disfraz, y la lección de allí era que comprobar la suite no basta. El
veredicto final mira ahora **las dos cosas**: que la suite pase *y* que
`git status` de los mutables esté limpio.

Dos sondas más salieron del harness, no del código: una apuntaba al filtro de
estado del SQL, que es **redundante** porque `RegistroDePacks.instalados` vuelve
a filtrar, así que no había nada que un test pudiera ver; y dos expectativas
estaban mal escritas, una nombrando la clase equivocada, lo que hace que una
sonda salga `PARCIAL` aunque el fallo esté detectado a la perfección.

### Un hueco de cobertura real

La sonda de compatibilidad destapó que el recorrido de la CLI instalaba packs
*compatibles*: el camino que ve el operador no estaba cubierto para el caso que
duele. Dos tests lo cubren ahora, exigiendo que el mensaje nombre la cláusula y
que nada quede instalado tras el rechazo.

### Lo que NO se hace aquí

La instalación **no declara los tipos** del pack: de eso se encarga
`sg pack load`, que ya existe. Uno administra la *instalación* y el otro el
*contenido*, porque dos comandos que hacen lo mismo con nombres distintos son la
trampa de «conectar no es contener».

---

## [0.29.0] - 2026-10-04 — las superficies públicas, declaradas y certificadas

SemVer **derivado** con `scripts/derive_semver.py` desde `v0.28.1`:
`b/f/x/n/d 0/1/0/4/0`, la regla pide **MINOR → v0.29.0**. El `fix(core)`
es el que aporta el valor: sin él, dos propiedades del gate de 1.0
seguían siendo IN-CERTIFICABLES, no incumplidas.

Medido con `scripts/measure_b9_gate_1_0.py`, que deriva las veinte
propiedades del propio `ROADMAP.md` y ejecuta un predicado por cada una:

```
antes (v0.28.1)  13 PASS · 6 OPEN · 1 NO_MEASURABLE
ahora (v0.29.0)  15 PASS · 4 OPEN · 1 NO_MEASURABLE
```

Durante el bloque, y con el `tests.total` todavía sin actualizar, la cuenta
intermedia fue 14/5: el `OPEN` que sobraba era
`roadmap/state/docs coherentes`, que es precisamente el `tests.total`
(estado 3176, árbol 3195). Puesta la cifra con el run ejecutado, esa
propiedad vuelve a `PASS` y quedan cuatro.

### Las dos propiedades que se cierran, y por qué estaban abiertas

`resource/controller API estable` y `CLI estable` no estaban abiertas por
falta de código: `skillgraph.core` no declaraba `__all__`, y no existía
el snapshot de la CLI. Once comandos de primer nivel podían cambiar sin
que nada lo notara.

### Lo importante: lo que se le opuso

Las dos se cerraban en **veinte segundos**. Se escribía un `__all__` y se
hacía `touch` sobre el fichero de la declaración. Los predicados de B9
comprobaban la **existencia** del fichero, y un `is_file()` es lo más
fácil de falsificar que hay: un `touch` les daba `PASS` a los dos, con el
gate de 1.0 exactamente igual de lejos.

El guard **ejecuta** la comparación en vez de mirar el fichero, y las dos
superficies se **generan desde el árbol** con `--actualizar`. Verificado
en las cuatro direcciones:

| qué se rompe | veredicto |
|---|---|
| snapshot vacío (`{}`) | `OPEN` en las dos propiedades |
| comando quitado del snapshot | `OPEN` |
| superficie real movida | `OPEN` |
| estado de verdad | `PASS` en las dos |

### Defecto del propio guard, medido al escribirlo

La primera versión comparaba los comandos de la CLI en **una sola
dirección** (`reales - declarados`). Añadir un comando *inventado* al
snapshot pasaba en verde: el guard sabía detectar que el árbol crecía y
no que la declaración miente, y la declaración es justamente lo que dice
«esto es lo que hay». Ahora compara en las dos direcciones.

### Qué se entrega

- `src/skillgraph/core/__init__.py` declara `__all__` con los **60
  símbolos** de los tres módulos del núcleo, **derivados** de sus `__all__`
  y no escritos a mano, y los reexporta **por identidad**:
  `core.ValidationError is core.errors.ValidationError`. Si el núcleo
  recreara la clase, el `except` que escribe un consumidor y el que lanza
  el núcleo serían dos clases distintas.
- `scripts/check_public_surfaces.py` — cuatro contratos, con capa pura
  (`evaluar_*`, sin disco ni imports) sobre capa de efecto (`medir`).
- `surfaces/core-surface.json` y `surfaces/cli-surface.json`, **generados**.
  Fuera de `docs/` porque `docs/*` está en `.gitignore` salvo tres
  carve-outs, y un snapshot que no viaja no declara nada — el defecto que
  B8 midió con el hijo de concurrencia. El guard lo comprueba contra
  `git ls-files`, por fichero.
- `public-surfaces` como etapa de la receta canónica. Lo decidió el propio
  guard WI-98, que exige que todo checker del repo lo invoque.
- `tests/test_b10_public_surface.py` — 19 tests en cinco conjuntos
  disjuntos, con contra-saltos en ambas direcciones. Un guard con seis
  aserciones iguales mide una sola cosa seis veces.
- `scripts/mutate_b10_public_surfaces.py` — **6/6 sondas cazadas con 6
  causas distintas**, árbol restaurado y ejecutando. Dos de las sondas
  nacieron rotas y se cuentan: envolver los 60 símbolos con
  `type('Copia', (v,), {})` revienta con `TypeError: metaclass conflict`
  en los 28 `NewType`/frozenset, el módulo no importaba, y el harness veía
  `rc=4` con cero líneas `FAILED` — que se lee como «el guard no muerde»
  cuando lo que pasa es que la sonda estaba rota. Un `rc` de colecta no
  es un test en rojo.

### Lo que NO se cierra aquí

Las cuatro `OPEN` que quedan **no dependen de certificación**: `pack/
controller lifecycle` y `upgrade desde releases soportadas` piden código
que todavía no existe; `runtime real certificado` pide
`SG_UAT_REAL_PROVIDER=1` y una credencial que este entorno no tiene; y
`security/threat model actualizado` pide reescribir un ADR que se aprobó
describiendo un proyecto de 830 tests y 17 releases.

---

## [0.28.1] - 2026-10-04 — el gate de 1.0 deja de ser una lista en prosa

Medido con `scripts/measure_b9_gate_1_0.py`, que **deriva** las veinte
propiedades del propio `ROADMAP.md` y ejecuta un predicado por cada una:

```
13 PASS · 6 OPEN · 1 NO_MEASURABLE · 0 NO_MEDIBLE
listo_para_1_0: false
```

`ROADMAP.md` decía, textual, que `v1.0.0` solo existe cuando se cumplan
*todas* sus propiedades, y listaba veinte. Era la afirmación más fuerte
del repositorio y la única sin nada que la comprobara. El conjunto se
deriva y no está escrito en el script, así que una propiedad que el
instrumento no sepa medir sale como `NO_MEDIBLE` en vez de pasar en
verde: anadir una línea al roadmap no la convierte en un PASS por olvido.

### Defecto de producción corregido — el que la medición destapó

Medir «concurrencia real certificada» salió `OPEN`. En detalle: **3 de 8
hijos muertos y 50 de 80 filas escritas**.

La causa era el defecto que B2 abrió y no cerró. `Storage.__init__`
ejecutaba `PRAGMA journal_mode = WAL` en cada apertura; el PRAGMA es
idempotente y aun así **toma un lock de escritura para averiguar que no
hace nada**. Con ocho procesos abriendo la misma base a la vez, uno moría
con `database is locked` *antes de escribir una sola fila*, y sus
escrituras se perdían sin excepción en el padre y sin log: el run
«funcionaba» y solo le faltaba un evento.

B2 lo había arreglado con un reintento. El reintento no bastaba:
`journal_mode` **no honra el `busy_timeout` del `connect`** —devuelve
`SQLITE_BUSY` de inmediato—, así que esperar era cosa del proceso y no
del driver, y dos intentos seguidos caían en la misma ventana.

`src/skillgraph/platform/journal.py` lo cierra en tres partes:

- **Preguntar antes de cambiar.** `PRAGMA journal_mode` a secas es una
  *lectura*, y una lectura no pide el lock exclusivo. Una base ya en WAL
  —el caso normal, y el único que importa con concurrencia— no toca el
  lock de escritura ni una vez.
- **Releer entre reintentos**, para que el que pierde el cambio se salga
  en vez de seguir peleando contra un modo que otro ya cambió.
- **Dormir entre reintentos** (10 ms y 20 ms), que es lo que deja ganar a
  alguien.

Medido con el mismo escenario que antes fallaba: **40 rondas de ocho
procesos abriendo una base nueva a la vez, sin un solo fallo**.

### La segunda mitad: el solape era una carrera, no una concurrencia

Lanzar ocho procesos en un bucle no los hace competir: los hace empezar,
y cada uno tarda lo que tarde en arrancar el interprete e importar
`skillgraph.platform.storage`. Medido: **4 de 20** corridas del módulo de
concurrencia fallaban, y la que caía no era la del solape sino la de
autores, porque un hijo había muerto sin que nadie se enterara —el test
descarta el resultado de `_procesos`—.

Ahora cada hijo escribe su fichero de «listo» y espera a que el padre
abra la puerta, y el padre no abre hasta tenerlos a todos. El solape pasa
a ser estructural. **0 de 20 y 0 de 25** donde antes eran 4 de 20.

### Lo que impide 1.0, y por qué cada una pide cosas distintas

| Propiedad | Por qué está abierta |
|---|---|
| resource/controller API estable | **Falta de certificación**: no hay superficie declarada contra la que comparar |
| CLI estable | Ídem: 11 comandos y ningún `docs/cli-surface.json` que los fije |
| runtime real certificado | Necesita `SG_UAT_REAL_PROVIDER=1` y una credencial; se ve en el `skip` del propio UAT |
| pack/controller lifecycle | Trabajo, no defecto: `sg pack` expone `import`/`load`, no `install`/`update`/`remove` |
| upgrade desde releases soportadas | No existe función de upgrade entre releases |
| security/threat model actualizado | El ADR-0015 se aprobó describiendo un proyecto de 830 tests; hoy colecta 3176 |
| TUI operacional | **NO_MEASURABLE**: «operacional» es una propiedad de una persona usando un terminal |

`TUI operacional` no es un `OPEN` con mejor prensa. Declararla `PASS`
sería la única forma de mentir, y no baja el veredicto igual que un
`OPEN`: el roadmap dice *todas*.

### Cuatro bugs del propio medidor, todos hacia el lado de mentir

1. La hoja de B5 escribe `[CERRADO ]` con un espacio y la de B6
   `[CERRADO]` sin él. Buscando el texto exacto, el predicado de
   provenance leía **cero** preguntas y devolvía `PASS`. Un predicado que
   pasa porque no leyó nada.
2. `_migrations_probadas` buscaba la palabra «deselected» para detectar
   que no se había ejecutado nada, y daba `OPEN` sobre un resumen que dice
   `3 passed, 20 deselected`.
3. Dos consultas al parser llamaban a `construir_parser()`, que no existe
   —es `build_parser()`—, y el `ImportError` se comía en un `return ()`.
   Dos veredictos falsos, ambos en la dirección de alarmar de más.
4. B5 declara su P6 FUERA DE ALCANCE, y por el principio de siempre no
   puede contar como abierta. El primer medidor la contaba.

### Harness: 6 de 6, y tres fallos que eran de los guards

`scripts/mutate_b9_gate_1_0.py`, 6 sondas cazadas con **6 causas
distintas**. Tres de las seis salidas fueron fallos de los *guards*, no de
las sondas: uno miraba que el proceso siguiera vivo (un hijo sin puerta lo
sigue estando 30 ms), otro hacía `join()` del hilo **antes** de
comprobar, y el tercero decía «ha salido un error» queriendo decir «ha
salido **este** error» —con el error tragado, la excepción igualmente
salía de `_migrate()`—. Los tres medían la mitad de lo que decían
medir. Un 3/6 es un número honesto; un 6/6 sobre esos tests habría sido
falso.

**El harness se destruyó a sí mismo.** Restauraba con
`git checkout --`, que restaura **del índice**, y con el arreglo sin
commitear el primer `checkout` se llevó el arreglo entero: cinco sondas
se quedaron sin texto que deformar. Lo peor es que **parecía funcionar**,
con la base verde y la primera sonda cazada. «Restaurar» y «borrar» son
la misma operación si no hay commit debajo, así que ahora se niega a
empezar si encuentra cambios sin commitear en lo que va a restaurar.

### Un incidente de release, escrito porque casi no se ve

El tag `v0.28.1` se creo sobre el commit de intencion. Despues, al
corregir el mensaje de un commit, se ejecuto `git commit --amend` **sobre
ese commit ya etiquetado**: `--amend` reescribe el commit y crea uno
nuevo con otro sha, y la etiqueta se queda apuntando al sha viejo, que
ya no es alcanzable desde `HEAD`. Un `git describe` lo delata —decía
`v0.28.0-9-...` con un `v0.28.1` a un solo commit de distancia—, pero solo
si alguien mira; `git tag -l` seguia listando `v0.28.1` como si nada, y
`git rev-list v0.28.1` resolvia a un commit huerfano sin decir que lo era.

Se detecto porque `scripts/project_truth.py` leyo `tag_vcs: 0.28.0` con
un `v0.28.1` recien declarado, que es exactamente la contradiccion que el
guard existe para ver. Se corrigio reanclando la etiqueta al commit real y
registrando su sha en `release.releases`.

La leccion cabe en una linea y es la misma que la del harness que se
destruyo a si mismo en este mismo bloque: **una etiqueta y un
`--amend` son la misma operacion, y la segunda se lleva la primera.**
Restaurar y borrar,enference y reescribir: el nombre cambia y el aviso es
el mismo.

### Una paradoja que queda escrita

El bloque entrega un módulo **nuevo** y un instrumento **nuevo**, y el
SemVer dice `PATCH`. No es que la regla falle: `journal.py` viajar en un
commit `fix(platform)` porque el cambio dominante era cerrar un defecto
de producción. El SemVer lo deriva de los **tipos** de commit, no de su
tamaño. El mismo trabajo, partido en un `feat` y un `fix`, habría salido
MINOR. Queda en `rationale_b9` para que el próximo que lea «B9 fue un
PATCH» sepa que fue consecuencia de cómo se commiteó.

## [0.28.0] - 2026-10-04 — el contrato de paquete, y lo que de él depende

**El bloque B8, cerrado y verificado.** El gate enumera siete frentes.
Siete no es un bloque: son siete, y medirlos juntos daría un veredicto
que no dice por dónde empezar. Este bloque mide y entrega **el
manifiesto**, que es la pieza de la que los otros seis cuelgan.

Medido antes de escribir nada con `scripts/measure_b8_package_contract.py`:
**5 de 5 preguntas abiertas**.

SemVer derivado con `scripts/derive_semver.py`: desde `v0.27.0`,
`b/f/x/n/d 0/1/0/5/0`, la regla pide **MINOR**. Ningún commit con
marcador de ruptura. Tag `v0.28.0` en `cdc45475c19487368e34922b448ebe334da57740`.

### El hueco no era un campo que faltara

Lo que existe es un `Brick` con `kind="DomainPack"`, que es el contrato
de **tipos**, no el de **paquete**. Un paquete tiene nombre, versión,
clase y requisitos.

### La costura ya estaba puesta desde B3

`CAPABILITY_VERSION: Final[str] = "v1"` vive en el puerto con un
docstring que dice literalmente que está ahí «para que
`requires.capabilities` de B8 tenga algo que versionar». Este bloque no
inventó el requisito: lo ejecutó.

### Tres decisiones

1. **`PACK_KINDS` se deriva por `get_args`, nunca se escribe a mano.**
   Un conjunto literal se queda corto en cuanto el `Literal` crece, y
   entonces el validador rechaza el valor nuevo que el propio tipo
   acepta.
2. **La versión de la capability la hereda del puerto.** Si viviera en
   cada adaptador, cada uno inventaría la suya.
3. **`ISOLATION_LEVELS` es una tupla ordenada, no un conjunto.** El orden
   es el contenido: es lo que convierte «progresivo» en una propiedad
   comprobable con `es_al_menos` y no en un adjetivo.

Y `es_compatible` devuelve **motivos**, no un `bool`: en un pack que se
está instalando, el «por qué» es la mitad del trabajo.

### Dos defectos reales del código

- **El parser rechazaba el formato del propio gate.** El enunciado
  escribe `">=0.30,<1"`, que **mezcla** `>=0.30` —dos componentes— y
  `<1` —uno solo—. La regex exigía `X.Y` o SemVer completo, así que
  **ningún pack encajaba** contra el formato que el gate define. Lo
  cazaron seis tests a la vez.
- **La capability larga se rompía en silencio.** Producía
  `type_name="a.b.v2@v2"` con la versión pegada, que no se puede comparar
  con un `CapabilitySpec` instalado, y cuyo síntoma es «falta la
  capability» — una respuesta creíble, que es lo que hace un fallo
  peligroso.

### Tres defectos propios, que importan más

- **Un `pytest.skip` mío** que escondía un fallo del contrato. Lo grave
  no era el skip: estaba porque la aserción de verdad nunca se escribió.
- **Un test que no podía fallar**: mutar un campo `str` en el dict de
  origen no puede cambiar un `frozen` dataclass. La sonda que lo apuntaba
  salió `NO CAZADA` —el harness diciendo la verdad en vez de contar un
  5/5 falso— y se movió a donde el alias sí es posible.
- **«Árbol restaurado byte a byte» NO es «el árbol está como estaba».** Al
  restaurar, el `mtime` puede no avanzar y Python sigue ejecutando el
  `.pyc` de la versión mutada. El harness ahora borra `__pycache__` y
  **vuelve a pasar la suite al final**.

### Verificación

- **3158 passed, 3 skipped declarados, 0 failed**.
- 66 tests, cobertura del **100 %** del paquete nuevo (suelo de §6.3: 90 %).
- Contra-saltos **5/5 con 5 conjuntos distintos** de tests.
- `tests.total` **3161**, con el desglose medido: sin el paquete
  `packaging` la suite colecta 3088, la cifra exacta que B7 declaró.

### Fuera de alcance

**P6** — que un pack se instale de verdad — depende de un registro remoto
y de una política de fijación que el CI no tiene. Y `subprocess` y
`sandbox` son campos **declarados**, no mecanismos: declararlos sin
ejecutarlos es la forma más fácil de mentir sobre seguridad.

## [0.27.0] - 2026-10-04 — las vistas que CLI y TUI compartirían

**El bloque B7, cerrado y verificado.** El gate pide diez widgets vivos
«sobre **las mismas** APIs y query models». Medido antes de escribir nada
con `scripts/measure_b7_operational_ux.py`: **3 de 3 preguntas abiertas**.

SemVer derivado con `scripts/derive_semver.py`: desde `v0.26.0`,
`b/f/x/n/d 0/1/1/2/0`, la regla pide **MINOR**. Ningún commit con
marcador de ruptura. Tag `v0.27.0` en `HEAD` de esta entrada.

### El hueco no era que faltara una TUI

Era que faltaba **la pieza de la que la TUI depende**. Medido sobre el
árbol real: cero declaraciones de `--format` o `--json` en siete módulos
de comando, y ningún símbolo en `src/` que expusiera render. La palabra
cargada del gate —«las mismas»— no tenía a qué referirse.

### Lo que se entrega

```
src/skillgraph/presentation/views.py     Column, TableView, DetailView
src/skillgraph/presentation/widgets.py   las diez proyecciones puras
src/skillgraph/cli/parser.py             --format {text,json}
src/skillgraph/cli/commands/runs.py      un único _emit
```

### Tres decisiones

1. **Las vistas no leen disco.** Se construyen desde lo que el dominio
   ya devolvió, porque una vista que consulta sería una segunda vía de
   consulta — el duplicado que este bloque existe para impedir. Se
   comprueba por AST: cero imports de `sqlite3` y de `Storage`.

2. **Una sola vista, dos representaciones, leyendo los mismos campos.**
   Y aquí se distinguirá algo que la primera versión del test confundía:
   **«mismos campos» no es «mismo renderizado»**. Un vacío se imprime
   como `-` en texto — el contrato antiguo de `runs show` — y como `[]`
   en JSON, que es lo que una máquina necesita para no tener que adivinar
   si es vacío o la cadena `-`. Exigir que coincidieran habría obligado a
   romper uno de los dos.

3. **B7 añade representaciones, no sustituye.** Sin `--format`,
   `runs show` sigue siendo `clave=valor`, porque hay callers que lo
   leen con `cut -d= -f2` y su docstring lo promete.

### Y la tercera estaba rota, medido contra

El guard que la vigila no es teórico. La primera versión de `_emit`
pasaba `vacio=` a toda vista: `TableView` lo acepta, `DetailView` no — y
`runs show`, que es el camino de **texto**, el de por defecto, el que se
usa siempre que nadie pasa `--format`, salía con `TypeError`.

**Un test que mira la vista no lo ve**: el defecto estaba en el cableado
entre el comando y la vista. Por eso `TestB7NoRompeElContratoExterno`
ejecuta el comando por `subprocess`.

### Verificación

- **3085 passed, 3 skipped declarados, 0 failed**.
- 23 tests en `tests/test_b7_operational_ux.py`.
- Contra-saltos **3/3**, cada uno con su propia causa; M3 la cazó un
  guard **nuevo** y no uno preexistente.
- `tests.total` **3088**, con el desglose **medido**: sin el paquete
  `presentation` en el árbol la suite colecta 3055 — la cifra exacta que
  B6 declaró — y al devolverlo colecta 3088.

### Hallazgo fuera del bloque, con efecto real

El ciclo `b6` llevaba dos sesiones bloqueado en `explore` por un supuesto
defecto del framework —`sddk artifact store` no vinculaba el artefacto al
ciclo— y **no lo era**. `cycle transition` acepta `--artifact kind=path`
**en la propia transición**, y con esa vía la transición se aplica.

Un `ENGINE_MISSING_ARTIFACT` que **nombra** el artefacto que falta es una
instrucción, no un veredicto de avería. Se leyó como avería porque se
escribió como avería, y una vez escrito el diagnóstico cada relectura lo
confirmaba.

### Fuera de alcance

**P4** — que la TUI sea usable de verdad — depende de un terminal y de una
interacción humana que el CI no tiene. Registrada, y por eso **no** baja
el veredicto.

## [0.26.0] - 2026-10-03 — cada afirmación dice QUIÉN la afirma

**El bloque B6, cerrado.** El gate pide que cada afirmación del Knowledge
Graph distinga `observed` · `derived-deterministically` · `agent-inferred` ·
`human-asserted`. Medido antes de escribir nada: **4 de 4 preguntas
abiertas**.

SemVer derivado con `scripts/derive_semver.py`: desde `v0.25.0`,
`b/f/x/n/d 0/1/1/4/0`, la regla pide **MINOR**. Ningún commit con
marcador de ruptura. Tag `v0.26.0` en `259d723`.

### Lo que estaba medido, y por qué el hueco era real

El hueco **no es un campo que falte**. `Claim.extraction_method` ya existía
— y no decía lo que su nombre decía. Es un `str` libre cuyos tres valores
medidos (`static_analysis`, `regex_def`, `manual`) son **métodos de
extracción**, no orígenes epistémicos. Son dos ejes ortogonales: con
`regex_def` no se sabe si lo afirmó la máquina o una persona, y escribir
`agent-inferred` ahí perdería el método. Un campo no puede decir las dos
cosas.

Y medido, en contra de lo que parece: **nadie escribe `extraction_method`
en `src/`**. Las 10 de `"manual"` y las 4 de `"regex_def"` están todas en
`tests/`; en producción sólo vive el default de la declaración. Un eje que
nadie rellena no puede ser donde nazca el origen.

### Added

- **`AssertionOrigin`** (`core/runtime_types.py`), `Literal` cerrado sobre
  los cuatro orígenes del gate, con **`ASSERTION_ORIGINS` derivado** por
  `get_args` — nunca escrito a mano, que es el error de QW-E: un conjunto
  literal se queda corto cuando alguien añade un valor al tipo, y la
  validación rechaza el valor nuevo que el tipo sí acepta.
- **`Claim.assertion_origin`**, con default `observed`. El default es una
  decisión: es el único de los cuatro que no promete autoridad, luego el
  único correcto para un valor que nadie ha declarado.
- **`InvalidAssertionOriginError`** con `code` propio
  `sg_invalid_assertion_origin`, porque un `code` compartido rompe la
  traducción a exit code (WI-109).
- **`scripts/measure_b6_provenance.py`** y
  **`scripts/mutate_b6_provenance.py`**, versionados en `scripts/` y no en
  `.pipelinek/` (backlog `bl-bl-01M41DFZEZ0003882TZNP7NPM0`).

### Changed

- **`claims.assertion_origin`** lleva `CHECK` en la DDL, y se propaga por
  `INSERT`, `SELECT`, mappers, DTO, promoción y la proyección de query.
- **`_migrate`** añade la columna si la tabla ya existía sin ella.
  `CREATE TABLE IF NOT EXISTS` **no** añade columnas a una tabla que ya
  existe: es un no-op silencioso. Medido — una base nueva funciona y una
  vieja no, y el fallo sale en producción y no en los tests, porque los
  tests construyen la base desde cero cada vez.
- **`_claim_to_payload`** extraído en `cli/commands/promotion.py`, para
  que el test verifique el código y no una copia escrita en el propio test
  (WI-106).

### Lo que el harness encontró, y no eran sondas malas

**Cuatro agujeros reales en la red**, todos del mismo tipo: una medición
que dice «falso» sin decir «dónde».

1. El guard de P6 buscaba la *mención* de los dos nombres con `ast.dump` y
   pasaba en verde con la validación gutiada, porque el mensaje del
   `raise` sigue nombrando el conjunto. Un guard que mide la prosa del
   error no mide la validación. Corregido para exigir un `not in` real.
2. El harness llevaba `-x`, y sin `-x`, **M3, M6, M7 y M8 no cazaban**:
   sus mutaciones dejaban la suite en verde. El 8/8 era un número que no
   se podía desarmar, con cuatro sondas heredando el fallo de la anterior.
   Añadidos los cuatro tests que faltaban; el recheck da **8 causas
   distintas de 8 sondas**.
3. El harness guardaba el `sha` y «restauraba» reescribiendo el fichero con
   sus propios bytes, que es no hacer nada. Ahora restaura bytes
   guardados.
4. El guard de WI-92 («un guard sobre cero citas no vigila nada») cazó el
   bloque vivo dos veces: primero porque no citaba ninguna línea, después
   porque las citas no resolvían — el formato es `fichero.py:LÍNEA::Símbolo`
   con **dos** puntos. Se corrigieron las citas, no el guard.

### Verification

23 tests en `tests/test_b6_provenance.py`; mutaciones **8/8 con 8 causas
distintas**, árbol restaurado byte a byte. `tests.total` 3053 (+23, todos
de este fichero: el bloque no creó módulos nuevos, así que el guard de
`wi47` no generó casos). Cobertura: `core/errors.py` 100 %,
`core/runtime_types.py` 98 %, `knowledge/graph.py` 96 %.

**Fuera de alcance y registrado:** P5 —si el proveedor real *puebla*
conocimiento o lo *consume*—, que depende de una credencial que este
entorno no tiene. El medidor la mantiene abierta y por eso **no** baja el
veredicto: es deuda, no un olvido.

## [0.25.0] - 2026-10-03 — el diff del grafo deja de ser un parche sin comparar

**El bloque B5, cerrado.** La secuencia del gate tenía un hueco con
nombre: `Proposal → Diff → Policy → …`, y el `Diff` no estaba.

SemVer derivado con `scripts/derive_semver.py`: desde `v0.24.0`,
`b/f/x/n/d 0/1/0/2/0`, la regla pide **MINOR**. Ningún commit con
marcador de ruptura.

### Lo que estaba medido, y por qué el hueco era real

Con `scripts/measure_b5_graph_diff.py` — **6 de 6 preguntas abiertas**.
La que resumía el bloque entero era una línea:

```
GraphExpansionProposal.operations: tuple[object, ...]
```

Un saco de operaciones sin tipar. Las tres clases ya existían
(`AddNode`, `AddTransition`, `RemoveTransition`) y el comentario del
propio código decía *«PatchOp es ADT cerrado»* desde antes de que
existiera un `PatchOp` que cerrara nada. Sin él, nada que quisiera
preguntarle al parche qué invalida tenía por dónde mirar, y el `Diff`
no podía ser una etapa del gate porque no había nada que comparar.

### Added

- **`GraphDiff` y `GraphChange`** (`governance/graph_diff.py`), frozen y
  con `slots`. `ChangeSubject` es un `Literal` **cerrado** sobre las
  siete clases de cambio del roadmap: `node`, `relation`, `capability`,
  `policy`, `budget`, `priority`, `evidence_requirement`.
- **`diff_graph(plan, proposal)`** calcula el cambio comparando el plan
  que hay con lo que la propuesta propone, y responde a las **siete
  preguntas** que el roadmap le exige a un diff.
- **`base_fingerprint`**: SHA-256 de una serialización estable del plan.
  No es adorno — ver más abajo.
- **`Storage`-equivalente del gate**: `apply_expansion` acepta el diff y
  lo **rechaza** si no es de esa aplicación, en tres capas: revisión,
  huella y recálculo.
- **`operations` pasa de `tuple[object, …]` a `tuple[PatchOp, …]`**, y
  `es_patch_op` lo comprueba en runtime, no solo lo anota.

### El hallazgo: el diff tiene que poder ver la mentira

`GraphDiff` lleva **dos** conjuntos de capacidades, y no es redundancia:

- `required_capabilities` — lo que las operaciones **producen**.
- `declared_capabilities` — lo que la propuesta **dice**.

Que discrepen no es un defecto del diff: es el resultado. Un diff que
devolviera la declaración sería un eco con mejor tipografía, y un gate
que comprueba ecos no mira nada. La sonda M1 sustituye el derivado por
el declarado y la red lo cazó.

### La huella, y por qué el diff sin ella no era un diff

La primera versión llevaba solo `base_revision`, y se rompió de una
forma que solo se ve ejecutando: **con el parche vacío el diff sale
vacío sea cual sea el plan**, así que un diff calculado sobre otro
grafo pasaba por suyo siempre que coincidiera la revisión. Y dos
estados pueden compartir revisión.

Sin la huella, *conectar ≠ contener* (WI-102) se queda en buena
intención. `base_fingerprint` es lo que ata el diff a su estado.

### Changed

- **`record_rejection` se muda** a `governance/expansion_audit.py`, y
  se reexporta desde `graph_expansion` para que su ruta de importación
  no cambie. Persistir un rechazo es escribir un registro de auditoría,
  no expandir un grafo.

  Lo decidió una medición, no un gusto: al integrar el diff,
  `graph_expansion.py` pasó de 787 a **901** LoC y el guard de god file
  lo puso rojo. La salida no fue recortar prosa — la razón por la que
  era larga es que el razonamiento no cabía allí. Queda en **785**.

### Verificación

- **28 tests** en `tests/test_b5_graph_diff.py`, uno de los cuales
  ejecuta el instrumento que abrió el bloque y exige que ya no reporte
  el hueco, y otro le inyecta un `GraphDiff` real y exige que el
  medidor se cierre — el contrasalto de un instrumento que solo sabe
  decir «abierto».
- **8/8 sondas de mutación cazadas**, 0 inválidas, árbol restaurado
  byte a byte verificado por `git diff`.

**Tres sondas encontraron agujeros reales en la red, no sondas malas:**

- **M5 no fue cazada dos veces.** La primera quitaba el `sorted()` de
  `to_dict` y no podía fallar: el constructor ya entregaba tuplas
  ordenadas, luego la propiedad era **vacua**. La segunda lo quitaba
  del constructor y tampoco — y ese es el hallazgo: la garantía está
  puesta **dos veces**, así que no se rompe quitando una. Es la misma
  clase que la M6 de B4, segunda vez en dos bloques.
- **M7** puso `reversible=True` fijo y nadie la cazó porque **ningún
  test** afirmaba que la séptima pregunta dependiera del plan de
  rollback.
- **M8** puso `esperado = diff`, con lo que la comparación se vuelve
  `diff != diff`. No la cazó nadie porque la huella salta **antes** y
  los tests de R6 usaban un diff bien calculado: la capa de recálculo
  no se ejecutaba nunca. Un guard que solo se ejercita por el camino
  bueno no sabe si el malo está cerrado.

### Fuera de alcance, y registrado como tal

Las **cuatro vistas** del roadmap (Execution, Knowledge,
Decision/Evidence, Capability/Control) siguen sin existir. El medidor
las mantiene **abiertas y visibles**, y por eso **no bajan el
veredicto**: son deuda registrada, no un olvido. Construirlas sin el
diff sería construirlas sin criterio.

## [0.24.0] - 2026-10-03 — la mitad observada de un recurso, alcanzable

**El bloque B4, cerrado.** Siete commits, un `feat` y seis sin bump. La
mitad de la separación CRD-like que B3 dejó sin tocar —la que se
*observa*— estaba declarada en el esquema y no se podía alcanzar.

SemVer derivado con `scripts/derive_semver.py`: `b/f/x/n/d 0/1/0/3/0`
desde `v0.23.0`, la regla pide **MINOR**. Ningún commit con marcador de
ruptura.

### Lo que estaba medido, y por qué el hueco era real

La tabla `resources` declara `spec_json`, `status_json`, `generation` y
`resource_version`, y el `INSERT` los rellena todos. Pero medido, antes de
escribir nada (`scripts/measure_b4_observed_state.py`):

- **1 `INSERT` y 0 `UPDATE`** en toda la tabla `resources` bajo `src/`;
- **cero** ocurrencias de `conditions` en todo `src/`;
- `generation` declarada y nunca escrita;
- y en una ejecución real: `status_json='{}'`, `generation=1`,
  `resource_version=1`.

`status_json` estaba declarada `NOT NULL DEFAULT '{}'` y nadie la
actualizaba nunca: cada recurso nacía sin observar y moría sin observar,
y el `NOT NULL` lo hacía parecer un estado. Es el mismo hueco con el que
abrió B3, en la otra mitad: lo declarado era alcanzable en el papel y
inalcanzable en ejecución.

### Added

- **`ResourceStatus` y `Condition`** (`resources/status.py`), `frozen` y
  con `slots`. `Condition.type` es un `Literal` cerrado, y **repetir un
  `type` es error**: `Ready=True` y `Ready=False` a la vez no son un
  status, son un status que ya no sabe qué observa, y se persistiría sin
  que nada fallara.
- **`Storage.update_resource_status`**, el primer `UPDATE` de la tabla
  `resources`, y **`Storage.get_resource_status`** para leerlo de vuelta.
  Antes eran unreachable: la columna existía y nadie la escribía.

### La invariante, y por qué tiene guard propio

`generation` es lo que el **spec** declara; `resource_version` es lo que
el **almacenamiento** lleva. Escribir el status sube `resource_version` y
**no** sube `generation`. La sonda M3 quita precisamente el `generation`
del `UPDATE`, y lo que se midió al cazarla es lo importante: el sistema
sigue funcionando **exactamente igual**. Nada falla, nada se rompe, la
separación desired/observed se vuelve decorativa. Es el defecto que no se
nota, y por eso necesita un guard que lo nombre en vez de confiar en que
alguien lo note.

`observed_generation` se **lee de la fila**, no se declara en el status. Si
lo declarara, mentiría en cuanto el spec cambiara por debajo — y sin
ningún error: sería el status más fiable del mundo y el menos cierto.

### Lo que NO se hizo, y por qué está en un guard

**`status` no vive en `Brick`.** Es la decisión que el bloque entero
sostiene, y R5 la fija por AST porque *«Brick no gana status»* no se
deduce de un valor: se deduce de la forma. Si el tipo declarado llevara el
status, un pack declararía el estado de su propio recurso, y la mitad
observada dejaría de estar observada: no habría forma de distinguir
`observed` de `human-asserted`. La separación es de **tipo**, no de
convención — y una convención es exactamente lo que el próximo fichero salta por encima.

### Changed

- Guardas de superficie de `Storage`: 65 → 67 métodos de delegación y
  72 → 74 públicos, con el motivo al lado de cada número. Documentado
  también **lo que no miden**: una cuenta ve *cuántos* métodos hay, no
  *cuáles*. Renombrar `get_resource_status` deja las tres guardas en
  verde — medido — y lo cazan los tests que lo llaman por nombre.

### Fixed

- Un docstring sin cerrar en `tests/test_wi65_storage_facade_delegations.py`
  se había comido el cuerpo de un test y lo dejaba vacío. Un guard que no
  se ejecuta no falla nunca, y por eso pasa en verde.

### Verificación

- **19 tests** nuevos en `tests/test_b4_observed_state.py`, uno de los
  cuales ejecuta el instrumento que abrió el bloque y exige que ya no
  reporte el hueco.
- **8/8 sondas de mutación cazadas**, 0 sondas inválidas, árbol
  restaurado byte a byte verificado por `git diff`.
- **Certificación**: 2991 passed, 3 skipped (los declarados), 2 failed —
  y los 2 fallos eran `tests.total` desactualizado y su gemelo de
  convergencia, los dos diciendo lo mismo. Se corrigieron con la cifra
  medida, no estimada.

## [0.23.0] - 2026-10-03 — el puerto de capabilities, alcanzable y con un adapter real

**El bloque B3, cerrado.** Siete entregas. Las seis dejaron el contrato,
los invariantes y la procedencia; la séptima cierra los dos huecos que
quedaban, y eran el mismo hueco un nivel más arriba.

SemVer derivado con `scripts/derive_semver.py`: `b/f/x/n/d 0/5/2/20/0`, la
regla pide **MINOR**. Ningún commit con marcador de ruptura.

### Lo que estaba medido, y por qué el gate se cumplía en vacío

El gate anterior demostraba que el **contrato** se puede cumplir: una
capability inventada dentro de un test se registraba, se resolví­a y se
invocaba. No demostraba que el **runtime lo pudiera alcanzar**. Y medido,
antes de escribir nada:

- dieciséis construcciones de `CapabilityRegistry` en el árbol;
- **las dieciséis en tests**;
- cero módulos bajo `src/` que importaran el puerto.

Veredicto: `INALCANZABLE_DESDE_PRODUCCION`. El criterio del roadmap —«añadir
una capability sin modificar `RunController`, el storage base ni el motor
del workflow»— se cumplía de forma **vacía**: se podía añadir una
capability sin tocar el core porque el core no la veía nunca.

### Added

- **`sg.knowledge.query`** (`knowledge/knowledge_query.py`), el primer
  adapter de **producción** del repo. Depende del `Protocol`
  `KnowledgeRepository`, no de `Storage`. Es la capability elegida por una
  razón concreta: el roadmap lista siete candidatas, seis de productos
  externos —que SkillGraph no debe reconstruir— y la séptima es dominio
  propio, con su acceso ya declarado como puerto y sin usar como
  capability.
- **`CapabilityController`** y **`CapabilityOutcome`**
  (`runtime/capability_controller.py`), el kernel que B3 nombraba y que no
  existía. Recibe **nombres**, los resuelve contra el registro inyectado y
  devuelve procedencia. `CapabilityOutcome` une el tipo **pedido** con el
  `spec` que **respondió**: son dos cosas, y sin el par no se puede auditar
  «este nodo pidió X y alguien entregó Y».
- **`scripts/mutate_b3_production_gate.py`**, sonda de mutación del gate,
  **versionada** y no en `.pipelinek/`. La razón está abajo.

### Changed

- **`RunController` acepta `capabilities=`**, un `CapabilityRegistry`
  **opcional**, cuya ausencia **es** la política. Sin registro —el
  default— un plan que declara `'stale'` sigue ejecutándose igual, porque
  `'stale'` es un `FreshnessState` y no una capability: cero ruptura, y por
  eso esto se puede aterrizar sin migrar nada. Con registro, lo que el plan
  declara tiene que existir, o el nodo queda `FAILED` con
  `CapabilityNotFound` —un `SkillGraphError` con `code`, traducible a exit
  code— **sin gastar una llamada al adapter**: la verificación va dentro
  del `try` de `_compile_node_handoff`, que corre antes de
  `_invoke_node_adapter`. Esa propiedad no se ve en la fila del nodo, y un
  plan que paga una llamada de red y luego falla **parece funcional**.

### La procedencia, por elemento y no por resultado

`CapabilityResult.adapter` responde «¿quién ejecutó esto?», que no es «¿de
dónde salió **esto**?». B6 quiere distinguir `observed` de lo que afirmó
un agente, así que cada elemento lleva su `source_id` y su
`checked_at_revision`.

### Lo que NO se hace, y es una decisión

Las capabilities **no se invocan** durante la ejecución del nodo: solo se
verifican. `Handoff.capabilities` sigue siendo `tuple[str, ...]` porque
`runtime/handoff.py:195::Handoff.to_dict` lo mete en el **hash firmado**, y
cambiar la forma es ruptura de datos: materia de **B8**.

### El guard, y por qué es AST

La propiedad del roadmap es **estructural**: el núcleo no debe saber qué
adapters existen. Un test de comportamiento pasaría igual con un
`if tipo == "sg.knowledge.query"` dentro del kernel, porque el resultado
sería idéntico. Lleva **dos contrasaltos**, porque cada uno tapa un
agujero distinto: que el rastreo encuentre el núcleo, y que el rastreo
**detecte**.

### Fixed

- `STATE.yaml` declaraba un `project_id` y un `workspace_id` **que no
  existen**, y las cuatro líneas siguientes ya usaban el prefijo correcto:
  el fichero se contradecía a sí mismo y el id equivocado no lo comprobaba
  nadie. Es la campaña «qué declara el repo que nada comprueba», con una
  forma que no se había visto: no era una afirmación demasiado optimista,
  era un id que apunta a otro proyecto.

### Verificación

Suite completa verde; mutaciones **6/6** cazadas, 0 sondas inválidas, árbol
restaurado y verificado por `git diff` de salida idéntico al de entrada.
`tests.total: 2974`, medido con `pytest --collect-only` **después** del run.

---

## Sin release — WI-115 (2026-10-03) — el estado declara una cifra y nadie la comprueba
**SIN RELEASE, Y POR REGLA.** Desde `v0.22.5` hasta HEAD hay
`b/f/x/n/d 0/0/0/4/4`: la herramienta dice literalmente *«la regla dice
SIN BUMP: no hay release que emitir, se acumula»*, y `AGENTS.md §12` es
explícito en que si la regla dice sin bump **no se emite etiqueta**.

Es el **segundo** bloque de la serie que no libera, después de WI-106, y
es la regla siguiendo, no la regla saltándose. `release.tag` sigue en
`v0.22.5` porque ese par describe la última release real, no el workitem
en curso.

**Decimoséptima** vía de la serie «qué declara el repo que nada
comprueba», y la más autoconsciente: el workitem salió de una línea que
el autor de WI-113 escribió él mismo al registrar un descarte.

### Lo medido, en las dos direcciones

```
STATE.yaml tests.total : 2834
tests colectados       : 2834
hoy coinciden: True

M1  tests.total = 2834 -> 2971:  governance rc=0  VERDE (NO LO VE)
M2  añadido 1 test (2835 colectados, estado en 2834):  rc=0  VERDE
```

Que hoy coincidan **no es la propiedad**. La propiedad es: si dejaran de
coincidir, ¿algo se pone rojo? La respuesta era no, por exceso y por
defecto.

### Lo que le da gravedad también está medido

En WI-109 la primera certificación dio `2753 passed + 1 failed`, y **el
fallo era este campo**: el post-release bumpeaba `__init__.py` y dejó
`tests.package_version` viejo. El hermano pequeño quedó vigilado desde
entonces. El grande no.

### El arreglo

El recuento se deriva del árbol con `pytest --collect-only` en un
subproceso, nunca del estado. Un guard que comparase contra una copia
escrita en el propio test sería el de WI-106: hoy acierta y el día que la
verdad se mueva dirá lo contrario con toda la autoridad de un test.

| | |
|---|---|
| forma | **test de pytest**, no etapa de la receta: `.pipeline.kts` tiene un SHA invariante desde WI-110 |
| tests | 4, de los que **3 son contrasaltos** |
| el contrasalto que importa | que el recuento real se pueda leer: sin él, el guard compararía contra un **cero silencioso** si pytest cambia una cadena |
| mutaciones | **3/3**, y M2 mide justo ese cero |
| cache | por sesión: 4,10 s → 2,34 s |

## [0.22.5] - 2026-10-03 — la frontera la sostenían cinco personas distintas

**PATCH**: derivado con `scripts/derive_semver.py` sobre el historial.

Decimosexta vía de la serie «qué declara el repo que nada comprueba»,
y la primera **elegida por medición entre varias**: antes de abrirla se
rastrearon ocho viñetas declaradas de `AGENTS.md` y cuatro dieron
cero —`lru_cache`, `time.time()`, `Optional[T]`, ORM—, que se
sostienen hoy y que no se abren, porque instrumentar una verdad que
nadie puede romper es la peor versión de un guard. La quinta dio un
cero **sospechoso**: cero `ON CONFLICT` en todo el repo, con un
`UNIQUE(event_id)` que sí existe.

### El defecto

`storage._atomic_state_and_event` tenía un docstring que decía
literalmente *«Re-raise como `IdempotencyError` cuando el UNIQUE sobre
`runtime_events.event_id` se viola (UAT-07, replay-safe)»*, y su cuerpo
hacía `except BaseException: raise`. La traducción no la hacía ese
método: **la hacían los cinco llamadores, cada uno por su cuenta, y
nada lo comprobaba.**

```
6 sitios escriben eventos. 5 traducen, 1 no.
```

Lo grave no es que hoy falle. Es que `sqlite3.IntegrityError` no es
`SkillGraphError`, luego atraviesa el `except` que traduce a exit code
—el de WI-109— y sale como **Traceback al usuario**. Un camino de
escritura nuevo sin `try` abría la frontera, y no tendría ni a quién
preguntarle.

### El arreglo

La traducción baja a `_insert_event_in_tx`, que es donde ocurre el
INSERT y por donde pasan los seis caminos. Los cinco llamadores capturan
ahora el error **del dominio** para enriquecer el mensaje con su nombre
de función; su `except sqlite3.IntegrityError` era código muerto que
además parecía vivo.

| | |
|---|---|
| el conjunto de caminos | **derivado del árbol**, no una lista en el test |
| contrasaltos | que la derivación encuentre ≥6 caminos, y que el helper no quede muerto |
| el instrumento | cambió: medía la convención que este bloque elimina |

7 tests · mutaciones 4/4 con sonda verificada tras `ruff format` ·
1214 tests afectados verdes · cero CJK añadido.

## [0.22.4] - 2026-10-03 — el `AgentResult` del Adapter era un alias

**PATCH**: derivado con `scripts/derive_semver.py` sobre el historial
(b/f/x/n/d 0/0/1/2/0).

Decimoquinta vía de la serie «qué declara el repo que nada comprueba»,
y la que vuelve a `AGENTS.md §1.1` después de que **WI-111** dejara
constancia de lo que faltaba allí.

Esa lista de once campos `dict`/`list`/`set` dentro de dataclasses
`frozen` se registró con el criterio de que no participaban en el hash
firmado. El criterio era correcto **para el hash** y equivocado
**para el resto**: uno de los once no tenía un dict mutable, tenía un
**alias**.

```python
# antes
result = payload["result"]
return AgentResult(outcome=outcome_raw, result=result, ...)
```

Medido con ejecución real: mutar el dict de origen cambiaba el
`AgentResult`, y `node_execution_delegations.py:443::_finalize_node_success` serializa ese
dict a disco — lo persistido era el del Adapter.

| | |
|---|---|
| arreglo | `deepcopy` del payload, no `dict()`: tiene niveles anidados |
| por qué **no** `MappingProxyType` | el motor serializa el resultado y `json.dumps` no acepta un `mappingproxy` |
| qué aporta la inmutabilidad aquí | que el Core ya no comparte memoria con el exterior |
| los otros diez dicts | **no se abren**: cero sitios que los muten |

Un criterio del guard se reformuló sobre la marcha: el test que exigía
`MappingProxyType` pasó a exigir dict plano y serializable, porque
exigir el tipo habría roto la frontera que el arreglo respeta.

15 tests · 3/3 mutaciones con sonda verificada antes de contar ·
cero CJK añadido.

## [0.22.3] - 2026-10-03 — el reloj tenía diez puntos de definición

**PATCH**: derivado con `scripts/derive_semver.py` sobre el historial.

Decimocuarta vía de la serie «qué declara el repo que nada comprueba»,
y la primera que toca cómo el repo **mide el paso del tiempo**.

`AGENTS.md §1.3` decía que el reloj «se inyecta (default factory con
`datetime.now(UTC)`) y se puede mockear», y `runtime/engine.py`
declaraba que `now_iso()` era el **«único punto de definición»**.
Ninguna se sostenía.

Medido por AST antes de tocar nada: **10** llamadas a `datetime.now`
en el núcleo, en **tres** formatos.

| formato | nº | ejemplo |
|---|---|---|
| `isoformat()` | 5 | `2026-10-03T09:00:00.123456+00:00` |
| `replace(microsecond=0)` | 2 | `2026-10-03T09:00:00+00:00` |
| `strftime(...)` | 3 | `2026-10-03T09:00:00Z` |

Y `RuntimeEvent` traía su propia copia:
`field(default_factory=lambda: datetime.now(UTC).isoformat())`. Una
lambda que captura el reloj real **no tiene por dónde inyectarle
otro**.

### Cambios

- **`now_iso(clock=None)`** es la única lectura del reloj del núcleo, y
  acepta un reloj inyectado. Se pasa explícito y no por un global porque
  `AGENTS.md §1.4` prohíbe el estado global mutable.
- **`RuntimeEvent.timestamp`** usa `default_factory=now_iso` y hereda el
  formato único.
- **`event_store`, `catalog`, `expansion`, `promotion` y `backups`**
  delegan en el helper.

**`strftime` se queda** en `backups`, `improvement` y `receipts`:
producen `2026-10-03T09:00:00Z`, que es un **nombre de fichero**, no un
instante de evento. La lista está en el guard, no en producción, porque
es una excepción y no una regla, y se vigila en las dos direcciones.

**El default factory se queda**: `AGENTS.md §1.3` lo pide, y hacerlo
obligatorio rompía 37 tests sin añadir capacidad.

### El guard mide la propiedad, no el nombre

«No hay una segunda lectura del reloj», no «existe una función llamada
`now_iso`». RASTREA POR AST porque el docstring del propio `now_iso`
menciona `datetime.now`, y un rastreo por cadena contaría la prosa.

### Dos cosas que el bloque encontró por el camino

Un `Disk quota exceeded` de `/tmp` — 38 GB de un tmpfs con cuota de
38,5, ocupado en 26 GB por trabajo ajeno. Y al esquivarlo poniendo el
sandbox **dentro** del repo, el guard de **WI-89** falló diciendo que
el sandbox escribía dentro del repositorio: **tenía razón**. Se movió
fuera, sin tocar el guard.

Y una **prueba intermitente** destapada por el formato único:
`test_wi56` comparaba dos llamadas al reloj real y falló 2 de 22 veces.
Medido: **4 de cada 2000** pares de `now_iso` separados por 2 ms cruzan
un segundo. Con microsegundos nunca habría pasado — la unificación
cambió la **probabilidad**, no la extensión.

17 tests, **5/5 mutaciones** con sonda por mutación, mypy 143 antes y
143 después.

## [0.22.2] - 2026-10-03 — la inmutabilidad que era de fachada

**PATCH**: derivado con `scripts/derive_semver.py` sobre el historial.

Decimotercera vía de la serie «qué declara el repo que nada comprueba»,
y la primera que encuentra el defecto en la estructura central del
sistema: lo que el agente ve.

`AGENTS.md §8` declaraba tres cosas del Handoff. **Ninguna se
sostenía**, y las tres tenían la misma causa:

> **Handoff**: inmutable + SHA-256 sobre serialización estable
> (capacidades y budget ordenados). El Adapter recibe el hash
> firmado; nunca lo recalcula.

`frozen=True` congela el **enlace** del atributo, no su **valor**.
`HandoffExecution.budget` era `dict[str, int]`, así que la estructura
era mutable por dentro y la firma seguía diciendo «inmutable».

### La segunda mitad es la grave

El budget está **dentro del hash**, y el motor lo usaba en dos
momentos distintos: lo persistía **antes** de invocar al Adapter
(`node_execution_delegations.py:219`) y lo **recalculaba después**
(`:144`). La línea 144 hacía exactamente lo que la viñeta prohíbe.

Medido antes de tocar nada, ejecutando un nodo real contra un
`Storage` real y leyendo de disco:

```
fila node_executions.context_hash : 0063e7dfd167afc6...
evento NodeCompleted               : 951a2d3a16cf7ea8...
evento EvidenceProduced            : 951a2d3a16cf7ea8...
hash que el Adapter vio AL ENTRAR  : 0063e7dfd167afc6...
budget en handoff_json persistido  : {'max_nodes': 1}
```

La fila describe el handoff de **antes**; los eventos, el de
**después**. Los dos son la misma `node_execution`.

### Cambios

- **`HandoffExecution.budget`**: `dict[str, int]` → `Mapping[str, int]`,
  envuelto en `MappingProxyType` sobre una **copia defensiva**. Escribir
  lanza `TypeError`; mutar el dict que conserva el llamante no toca el
  handoff. El `isinstance(budget, Mapping)` se mantiene: sin él, un
  `str` pasaba como budget y el handoff quedaba corrupto.
- **`_compile_node_handoff`** devuelve `(handoff, context_hash)`. El
  Core calcula el hash **una vez**, al firmarlo, y de ahí en adelante
  solo viaja.
- **`_open_running_node`** extraído de `_execute_one`.

**El guard no lee el código: ejecuta un nodo.** Un guard por AST habría
medido la regla, no el defecto — el defecto estaba en la distancia
temporal entre firmar y entregar, que no está en el texto de ningún
fichero.

### Tres defectos del propio guard

Las mutaciones los dejaron ver, y quedan escritos en `AGENTS.md §8`:

1. Un test comparaba contra una llamada **nueva** de `_handoff()` en vez
   de releer el handoff mutado: no podía fallar nunca.
2. `MappingProxyType == dict` es `True`. Un test que exigía un dict
   plano comparando con `==` pasaba con el mapping vivo devuelto.
3. Contar llamadas a `context_hash` sin distinguir el origen contaba la
   lectura del propio Adapter como una recalculación del motor.

M5 se reescribió **dos veces**: la primera mutación quitaba el
`sorted()`, que resultó **inocua** — quitar el orden no rompe la
copia— y su sonda apuntaba al test tautológico.

### Dos guards rotos por el propio cambio

Resueltos cambiando el código, no la regla:

- **WI-66**, umbral de 80 LoC: 74 → 83 → **76** extrayendo
  `_open_running_node`. El umbral no se sube.
- **WI-67**, lista de métodos movidos: 22 → **23**.

Un umbral que se sube para que el código pase no comprueba nada.

19 tests, **5/5 mutaciones** con sonda por mutación. 2795 passed,
0 skipped.

## [0.22.1] - 2026-10-03 — la etapa que se verificaba a sí misma

**PATCH**: `git log v0.22.0..HEAD` = 1 `fix`, 4 `docs`, 0 breaking.
Derivado con `scripts/derive_semver.py` (`b/f/x/n/d 0/0/1/4/0`).

Duodécima vía de la serie «qué declara el repo que nada comprueba»,
y la primera que no cierra un hueco del **código** sino del
**instrumento**.

La etapa `evidence` mide el run **anterior** —cuando corre, el run
en curso aún no tiene `RunFinished`—, así que su propio paso aparece
como `StepFailed` dentro del run que falló por ella. `evaluar()` lo
rechazaba por el mismo criterio con el que rechaza un fallo de
código, porque `step_failed` es un **contador** y un contador no
sabe quién falló.

**Medido sobre el journal real**: `8d6a9594` fue el último run con
las 8 etapas en `success`. Los cinco siguientes tuvieron las siete
etapas de código en `success` y todos terminaron en `failure`. Un fallo
ya corregido no devolvía la cadena a verde.

### Cambios

- **`InformeRun.paso_fallido`**: el **nombre** del paso, leído de
  `stepName`. Es el cambio de fondo: sin él no hay base para
  exculpar. Con valor por defecto `None` a propósito, que es lo
  que evita romper el guard de WI-108.
- **`ETAPA_AUTOEVALUADA`** declarado como constante, para que un
  test pueda exigir que las dos copias no diverjan.
- **`evaluar()` exculpa con TRES condiciones**: un solo
  `StepFailed`, con el nombre conocido, y que el nombre sea
  `evidence/`. El veredicto del run **nunca** se exculpa.
- **`.pipeline.kts` NO se toca**: su SHA-256 sigue siendo
  `7541ced5…` y las once certificaciones anteriores siguen
  valiendo. Un test lo fija.

**La medición desmintió el diagnóstico de WI-109**, que descartó
el arreglo por «toca la receta». El criterio vive en `evaluar()`,
no en la receta.

Guard: 22 tests, con más tests para la mitad peligrosa —la que
perdona de más— que para la que arregla. **11/11 mutaciones** con
sonda por mutación, y el harness distingue **cuatro** salidas porque
cuatro sondas apuntaban mal y las contaba como victorias sin que el
guard hubiera opinado.

## [0.22.0] - 2026-10-03 — la viñeta que sí era cierta y nadie ejecutaba

**MINOR**: `git log v0.21.2..HEAD` = 1 `feat`, 0 `fix`, 3 `docs`, 0 breaking.
Derivado con `scripts/derive_semver.py` (`b/f/x/n/d 0/1/0/3/0`).

Undécima vía de la serie «qué declara el repo que nada comprueba», y la
primera cuya regla resultó **menos** violada de lo que la alerta suponía.

La consigna era `AGENTS.md §1.2`: *prohibido `raise ValueError` /
`raise Exception` en código de dominio*. **Medida antes de tocar nada**:

```
grep -rn 'raise ValueError\|raise Exception' src/   ->  0
```

La prohibición literal **se cumple**. Instrumentarla habría sido vigilar
una verdad que nadie puede romper, que es la peor versión de un guard.
Lo que el dominio lanza de verdad son otros builtins —`TypeError` ×6,
`KeyError` ×5, `RuntimeError` ×2, `NotImplementedError` ×1, medido por
AST— y todos en invariantes internas de adaptadores (`unwrap()`,
`dto.py`), ninguno en el camino de error que ve el usuario.

**El defecto estaba en la tercera viñeta**, que sí era cierta y no
estaba instrumentada:

> Cada excepción lleva un `code` estable (`sg_*`) usado por la CLI para
> traducir a exit codes.

Medido en tres partes:

1. **La traducción no existía.** `runner.main` hacía
   `except SkillGraphError -> return EXIT_DOMAIN` (10) para todo. Los
   códigos 11 y 12 solo se alcanzaban porque cada comando repetía su
   propio `except ParseError`: la decisión la tomaba el *tipo* en el
   sitio de la llamada, y el `code` se imprimía sin decidir nada.
2. **Entrada de usuario malformada salía como traceback.**
   `knowledge compile <p> '{"obligatory": ['` devolvía **rc=1** con el
   `Traceback` entero de `json.JSONDecodeError`: el `json.loads` estaba
   fuera del `try` y `JSONDecodeError` no es `SkillGraphError`.
3. **Tres clases compartían `sg_error`** y **dos
   `sg_invalid_expansion`**. Un `code` compartido no puede mapear a dos
   exit codes distintos, y entonces el `code` deja de ser la clave: la
   traducción prometida no se podía construir encima de él.

### Cambios

- **`exit_para(exc)`** en `src/skillgraph/cli/exit_codes.py`: pura sobre
  `exc.code`, con la tabla `code -> exit`. Vive en el **módulo hoja que
  sigue sin importar nada** porque ADR-0016 lo movió allí para que
  `parser.py` consuma el contrato sin arrastrar `Storage`; una traducción
  en `runner.py` sería inalcanzable desde ahí.
- **`main()`** cablea la traducción. Un `code` desconocido cae en
  `EXIT_DOMAIN`, **nunca** en `EXIT_OK`: 0 significa éxito, y un error de
  dominio que sale con 0 es peor que uno que sale con 10.
- Los **dos** `json.loads` de entrada de usuario protegidos,
  convirtiendo la excepción de la stdlib en `ParseError` con su `code`.
- Los **tres** `code` colisionados, con `code` propio.
- Las tres ramas de `cmd_knowledge_compile` que devolvían `EXIT_DOMAIN`
  las tres: no distinguían nada, solo parecían distinguir.

**Medido con el binario**: `rc=1 + Traceback` → `rc=11 + ERROR (sg_parse)`.
Los errores de dominio no distinguibles **siguen en 10**, que es lo que
afirman 16 tests que ya existían: cambiarlo habría roto un contrato
as-built bien observado.

### Guard

`tests/test_wi109_code_to_exit.py`, 19 tests. El que mira el cableado
mira el **AST**: la primera versión buscaba la cadena
`return EXIT_DOMAIN` y se puso roja **por su propio comentario**, que
explica por qué se sustituyó. Tercera vez en tres semanas por el mismo
motivo (WI-98 con rutas absolutas, WI-108 con el patrón de
`pytest.skip`): un guard que busca una cadena busca la cadena.

**Mutaciones 11/11 con sonda.** Una no la cazó la sonda, y la señal fue
que **M6 no la cazó**, no que el guard estuviera roto: `code = "sg_error"`
es una *colisión* (la clase declara code, el mismo que otra), no una
*herencia* (no tenerlo en `__dict__`). Son dos propiedades con dos tests.

Sin push.

## [0.21.2] - 2026-10-03 — la regla que se escribe con tu letra y no se comprueba con ninguna

**PATCH**: `git log v0.21.1..HEAD` = 0 `feat`, 2 `fix`, 4 `docs`, 0 breaking.
**2735 passed, 0 skipped** (+17).

Décima vía de la serie «qué declara el repo que nada comprueba», y la más
pequeña en código: una prohibición de siete palabras con su «por qué»
escrito al lado.

`AGENTS.md §6.2`:

> **NO usar `pytest.skip` para esconder fallos: o arreglas el test o lo
> borras.**
> **Un `skip` por falta de artefacto es el mismo defecto, con otra forma.**

La segunda la escribió WI-103 después de medir un gate que se saltaba por
falta de informe. Y de todo el repo:

```
instrumentos que miran skips (scripts/, src/): 0
etapas de la receta que los miran:               0
```

Medido antes de escribir una línea, con un run sintético cuyo único cambio
es la línea de resumen del journal:

```
run sin skips:   0 problemas []
run con 3 skips: 0 problemas []
veredicto: «OK: el run cumple los criterios que declara AGENTS.md»
```

**El detalle que lo hace grave no es el regex.** Es que el **criterio 2** —
el que existe para distinguir un run real de un veredicto cacheado— acepta
un resumen con skips: `2715 passed, 3 skipped` casa con su regex igual que
`2718 passed`. No es un bug del regex: es que la pregunta por los skips **no
se había hecho**. Una regla y el criterio que la vigila no se contradicen
cuando nunca se cruzan.

**Y la regla la incumplía el autor de la regla.** De los cinco skips que
había, dos son de plataforma (`fcntl` no existe en Windows: no esconden un
fallo, describen una diferencia real entre máquinas) y **tres son de
artefacto** —«sin journal: clon nuevo»—, que es literalmente lo que la
segunda línea prohíbe. Los escribí yo en WI-105, en el guard que construí
precisamente para no esconder nada.

Los tres se fueron, y **no se sustituyeron por nada**, que es la decisión
que hay que defender: los tres medían el **entorno** —qué pasó en esta
máquina— y no el **entregable** —qué garantiza el guard—. El journal no
está versionado, así que en un clon nuevo se saltaban en silencio y la
suite pasaba en verde con skips. Sus tres propiedades ya tienen sitio: dos
en la etapa `evidence` en cada run, una sintética desde WI-105.

**El guard que mira el código mira el AST, no el texto.** La primera
versión buscaba `pytest.skip(` con un regex y se puso roja **por su propia
documentación**: un docstring que cita el patrón es indistinguible de una
llamada. Es la segunda vez en dos semanas y en el mismo repositorio, y por
eso la propiedad «este código *llama* a `pytest.skip`» se responde con el
árbol sintáctico.

**Límite declarado:** `from pytest import skip` seguido de `skip(...)` no
lo ve el AST, porque el nombre ya no es `pytest.skip`. Es un alias, no la
forma que pytest documenta, y queda escrito en vez de descubrirse.

**Mutaciones 9/9 en tres pasadas**, con sonda por mutación: el patrón que
WI-107 dejó montado, aplicado desde el principio. Una de las nueve no la
cazó la primera sonda porque medía la forma de retorno de un árbol sin
llamadas, donde esa forma nunca se ejerce: la mutación era inválida, y el
harness lo dijo en vez de acusar al guard.

## [0.21.1] - 2026-10-03 — la lista de paquetes, y por qué cambiarle el eje no la deshace

**PATCH**: `git log v0.21.0..HEAD` = 0 `feat`, 2 `fix`, 10 `docs`, 0 breaking.
**2718 passed, 0 skipped** (+15).

Novena vía de la serie «qué declara el repo que nada comprueba», y la tercera
vez que la misma idea se salva a sí misma cambiando de forma.

`AGENTS.md §6.3` declara suelos de cobertura por módulo. El guard que los
comprueba ha tenido tres versiones, cada una creyendo que era la última:

| | la lista | lo que dejaba fuera |
|---|---|---|
| WI-93 | 21 módulos escritos a mano | todo menos `runtime/` |
| WI-94 | 8 prefijos de paquete escritos a mano | un paquete **nuevo** |
| WI-107 | ninguna | — |

El docstring de WI-94 afirmaba, con la razon que da un docstring recién
escrito, que con una sola fuente «no se puede olvidar uno». Es falso: el suelo
pasó a declararse por paquete, y el **conjunto de paquetes** seguía siendo un
diccionario escrito a mano.

**Medido antes de tocar nada**, con un paquete nuevo cuyo módulo nadie importa
y que ya está versionado en git:

```
pytest                    2709 passed in 234.75s
check_coverage_floors.py  exit 0, «todos los suelos se cumplen»
cobertura de oracular.py  0 %  (18 sentencias, 10 ramas, 0 cubiertas)
suelo global              94.85 %   (fail_under = 80)
```

Se midió dos veces, y la segunda es la que se cita. Con el paquete **sin**
versionar la suite daba `1 failed`, y el rojo era `sg_build_sdist_no_versionado`
(WI-97): un sdist no puede llevar lo que git no versiona. Ese guard lo ve,
pero por otra propiedad y con otro mensaje, y un paquete nuevo se versiona.
Escribir solo la primera medición habría producido una afirmación más fuerte
y falsa.

**El arreglo.** `SUELO_POR_DEFECTO = 90` alcanza a todo módulo que cuelgue de
un subdirectorio de `src/skillgraph/`, paquete nuevo incluido, sin que nadie
lo declare. Lo escrito son las **desviaciones**, que son datos y no se deducen
del árbol: `cli/` al 70 % y `platform/paths.py` al 60 %. De ocho entradas, dos.
`§6.3` deja de enumerar módulos, porque esa enumeración era una fuente de
verdad más y ya estaba vieja: `runtime` no es un módulo sino un paquete.

**Dos hallazgos que salieron de las mediciones**, no de un test. El primer
guard de `§6.3` pasaba por la rama equivocada: buscaba `nombre.py` y `§6.3`
escribe los módulos sin extensión, así que no encontraba nada. Y un
contraejemplo mío usaba como «paquete que no existe» el nombre del paquete
de la medición, así que con él presente el test se ponía rojo: un guard que
depende del árbol sin decirlo es una coincidencia.

**El harness de mutaciones cambió** por una flake con nombre. Primera pasada
6/8 con `m2` sobrevivida; segunda, del mismo código, 7/8 con `m2` cazada. Una
mutación que a veces sobrevive no es un guard que no muerde: es un
experimento que no sabe qué midió. Con una **sonda por mutación** las tres
salidas tienen nombre. 8/8 en tres pasadas consecutivas.

## [0.21.0] - 2026-10-03 — los criterios de éxito del CI eran una declaración

**MINOR**: `git log v0.20.5..HEAD` = 1 `feat`, 0 `fix`, 1 `docs`, 0 breaking.
**2699 passed, 0 skipped** (+15).

Séptima vía de la serie «qué declara el repo que nada comprueba». A diferencia
de las otras seis, el defecto no es un instrumento mal construido: son **seis
criterios escritos que nadie comprobaba**.

### El defecto

`AGENTS.md` («CI Local Obligatorio») enumera seis criterios que un run «debe
cumplir». La etapa `evidence` de `.pipeline.kts` era el único sitio de la receta
que tocaba `.pipelinek/`, y sus tres comandos **no podían fallar**: un `ls` del
journal y dos `test -d` sobre directorios que el motor crea **antes** de la
etapa.

Medido contra el journal real de este repo —15 runs, 3 de ellos
`RunFinished/failure`—: la etapa imprime `last-run present` y
`workspace tracking present` **en los quince**, indistinguibles. Es la forma de
WI-101 —una etapa que certifica sin ejecutar la comprobación— aplicada al
registro del propio CI.

El alcance era mayor: el único criterio citado en algún sitio era el 1, con un
`grep` sobre el stdout dentro de `scripts/hooks/pre-push`, hook que no está
instalado y cuyo `grep` ya se comió esa cadena exacta una vez en la historia
del repo.

### Lo que se comprueba

`scripts/check_pipeline_receipt.py` verifica los criterios **1 a 5** desde el
journal y el árbol. El **6 no se automatiza**, y se declara: es el SHA-256
«registrado en la sesión», y una sesión es del agente, no del repo. Meterlo en
el script habría sido la misma mentira que el script viene a arreglar.

### El contraejemplo que manda

No es el run rojo. Es el run **verde que no ejecutó nada**: un veredicto
cacheado y una verificación real dicen los dos `Pipeline finished with
SUCCESS`. `AGENTS.md` describe el caso con sus palabras —«sin `--rerun`, un run
cuyo script no ha cambiado reutiliza el veredicto previo y termina en
`Pipeline finished with SUCCESS` sin ejecutar un solo step»— y el criterio 2
existe para separarlos. Era el único modo de fallo que nada distinguía.

### Por qué verifica el run anterior

La receta no puede verificar su propio run: cuando la etapa corre, el run en
curso todavía no tiene `RunFinished`. El huevo y la gallina es real, y lo
resuelve el propio motor: **el `RunFinished` más reciente es, durante un run, el
run anterior**. El mismo script con `--run-id` verifica uno concreto, que es lo
que hace la certificación.

### Un detalle de instrumento costó una medición entera

El `payload` del journal es una **lista JSON con un dict dentro**, no un objeto.
`json_extract(payload, '$.outcome')` devuelve `NULL` sobre ese schema, y leerlo
por la ruta de objeto salía con `None` en los 15 `RunFinished`: el run más sano
del repo habría salido como `failure`. Un instrumento que no abre el
contenedor no mide lo que cree medir, y el síntoma —un `None` silencioso en 15
filas— parece un dato, no un fallo.

### Mutaciones 7/7 a la primera

`.pipelinek/wi105_mutate.sh`, incluida M7, que degrada la **conexión** sobre el
`.pipeline.kts` real: lo que debe morder ahí es C5 de WI-102, no un test de
este bloque. M6 funde las dos mitades del criterio 2 en un código, porque un
solo código haría decir «veredicto cacheado» a un run que sí ejecutó pasos: un
guard que señala de más entrena a su lector a ignorar sus avisos.

No hizo falta la segunda pasada de WI-104 porque cada test exige el **código**
del problema, no solo que la lista no esté vacía. Exigir solo «hay problemas» es
justo lo que dejó pasar a tres contraejemplos allí.

---
## [0.20.5] - 2026-10-03 — una cita que no dice a qué apunta no es una cita

**PATCH**: `git log v0.20.4..HEAD` = 0 `feat`, 1 `fix`, 1 `docs`, 0 breaking.
**2684 passed, 0 skipped** (+7).

Sexta vía de la serie «qué declara el repo que nada comprueba». A diferencia
de las otras cinco, el defecto es **propio** y estaba anotado desde WI-102
como «medido, no arreglado».

### El defecto

`test_toda_cita_del_bloque_vivo_resuelve` daba por buena cualquier cita
`fichero.py:N` de la que existiera la línea N. Eso es **resolubilidad, no
verdad**, y se notó porque yo escribí en `CURRENT.md` las líneas 352 y 479
de `scripts/check_ci_recipe_parity.py` cuando las reales eran la 421 y la
589. Las cuatro líneas existen hoy. El guard dio las cuatro por buenas.

### Medido

`.pipelinek/wi104_measure.py` (solo lectura, cinco casos con la verdad al
lado): el predicado actual acepta las dos citas falsas; el de sitio de
definición las separa con **cero** errores. La razón es concreta: 352 y 479
son **prosa dentro de un docstring**; 421 y 589 son líneas `def`.

### El arreglo

El formato de cita pasa a `ruta/fichero.py:LINEA::simbolo`.

El símbolo no es decoración: es lo que hace la afirmación *falsable*. Con
sólo el número no hay manera de distinguir «he abierto el fichero» de «he
escrito un número que me sonaba», y por eso el error se colaba sin que nada
lo notara. Se resuelve en el AST del fichero que la cita nombra —no en
cualquiera del repo, que es el fallo de resolver por basename— y `LINEA`
tiene que caer dentro de su definición. Cuando una cita se queda vieja, el
error **dice dónde está el símbolo ahora**.

Lo que el guard **no** comprueba, y se declara: que la prosa describa de
verdad el símbolo. Eso no es machine-checkable.

### El contraejemplo hubo que arreglarlo dos veces

Seis mutaciones, todas en rojo. Pero la primera pasada dio **3/6**, y las tres
que sobrevivieron no eran contraejemplos débiles: **pasaban por el motivo
equivocado**.

1. La prueba de desalineación usaba `cargar_auditor`, que no es un símbolo —
   se llama `_cargar_auditor`—, así que medía la rama de «no lo define» y la
   mutación que apaga la comprobación de línea pasaba verde.
2. La regla del ancla se comprobaba sobre el *parser*, que nunca produce una
   cita sin ancla, así que **relajarla por dentro** pasaba sin que nada lo
   notara. Se extrajo `_problemas_del_bloque`, que verifica una lista de
   citas cualquiera.
3. Resolver el símbolo en todo el repo daba el error equivocado sin que
   ninguna prueba lo notara. Ahora el test exige que el error señale **el
   fichero** que debería definirlo.

### El guard atrapó al autor

Al escribir el bloque vivo de `CURRENT.md` conté el fallo anterior usando el
patrón `fichero.py:352`, y el guard lo leyó como una afirmación y lo rechazó.
Es lo correcto: un bloque que cuenta un error usando el formato del error se
contradice a sí mismo. La regla queda escrita: el bloque vivo cita el código
de hoy; la arqueología va aquí.

---

## [0.20.4] - 2026-10-03 — el gate de `main` solo existía los días con informe

**PATCH**: `git log v0.20.3..HEAD` = 0 `feat`, 1 `fix`, 0 `test`/`docs`, 0 breaking.
**2677 passed, 0 skipped** (2672 passed + 1 skipped antes; +4).

Apareció por la re-certificación de WI-102, que dio `2672 passed, 1 skipped`
donde el código había dado 2673 sin skips. La fecha rolloveró a `2026-10-03`
durante la sesión y el informe de ese día no existía.

### Medido

`TestAuditGateForMain` declara una propiedad sobre el **código** —«`main` no
debe listarse como hotspot público, cc≥20»— y la comprobaba leyendo
`audits/architecture-debt-<HOY>.md`, con `pytest.skip` si no existía.

| situación | resultado |
|---|---|
| sin informe de hoy | **SKIPPED, exit 0** |
| informe de hoy generado | 1 passed |
| informe de hoy con `main` inyectado | 1 **failed, exit 1** |

**La propiedad es real y el gate muerde cuando el artefacto está. El defecto
es la existencia del artefacto:** 6 informes `architecture-debt-*` en 7 días
(falta el `2026-09-30`) y hoy no hay ninguno.

`AGENTS.md §6.2`: «NO usar `pytest.skip` para esconder fallos».

### El arreglo: que el gate mida

`hotspots_publicos(arbol, *, out_dir)` ejecuta `audits/audit_debt.py` con
`--src-root` sobre el árbol que se le pase y `--out-dir` a un temporal —ambos
parámetros desde WI-89, que los hizo parámetros para que un test pudiera
auditar sin mutar `audits/`, que tiene 51 ficheros versionados. El análisis usa
el propio auditor, no una cuenta propia: reimplementar la métrica sería tener
dos verdades sobre qué es un hotspot.

Gana tres cosas: **siempre activo** (no depende de la fecha), **siempre
fresco** (antes validaba un snapshot de la última vez que se corrió) y **sin
efectos secundarios**.

### El contraejemplo es parte del arreglo

Sin un test que ponga un `main` real de `cc>=20` en un árbol y exija que la
medición lo vea, **una medición que devolviera siempre `()` habría pasado todo
verde**. Un gate que solo sabe pasar no está probado. M2 es esa degradación.

Mutaciones 5/5, y dos de ellas son degradaciones por *incapacidad* —el guard
sigue leyendo ficheros y su veredicto es correcto para un umbral que nadie
alcanza—, que es más difícil de ver que una desactivación.

## [0.20.3] - 2026-10-03 — la receta canónica puede perder un contrato y seguir verde

**PATCH**: `git log v0.20.2..HEAD` = 0 `feat`, 2 `fix`, 0 `test`/`docs`, 0 breaking.
**2673 passed** (2661 antes; +12).

C3 leía las etapas del script, y lo hacía bien: leer del script es lo que evita
un guard que vigila una lista paralela. Pero comprobaba que la lista fuera
**legible**, y una lista de etapas vacía por legibilidad es tan válida como
una completa.

### Medido con el comando canónico de verdad

Se borró el bloque entero de la etapa `coverage-floors` de `.pipeline.kts` —la
que impone los suelos que `AGENTS.md §6.3` declara exigibles— y:

| quién debía enterarse | resultado |
|---|---|
| `scripts/check_ci_recipe_parity.py` | **exit 0** — «OK: …» |
| `pytest tests/test_wi98_ci_recipe_parity.py` | **37 passed** |
| la receta, ejecutada de verdad | **`Pipeline finished with SUCCESS`** |

Cero menciones de la etapa en su salida, y cero de su `VEREDICTO`. Una receta
que ejecuta menos se ejecuta igual de bien. C4 exigía que quien ejecuta
`pytest` esté **conectado** a la receta; nadie exigía que la receta
**contenga** los contratos.

### C5 — sin lista

```
C5  todo `scripts/check_*.py` lo invoca la receta canónica
```

El conjunto sale del repo, no de una constante. Una lista de contratos
obligatorios dentro del guard es la misma trampa que `DIRECTORIOS_NO_RECETA`
en WI-99: obliga a mantener enumerado lo que el guard debería comprobar solo.
Así un checker nuevo entra en el contrato el día que se escribe, y borrar una
etapa se detecta porque el checker que invocaba deja de estar invocado.

Cubre también el caso inverso, hasta ahora invisible: **escribir un checker
y no enchufarlo en la receta**.

### Después del arreglo

| quién debía enterarse | antes | ahora |
|---|---|---|
| `check_ci_recipe_parity.py` | exit 0 | **exit 1** + `sg_ci_contrato_huerfano` |
| `pytest test_wi98_ci_recipe_parity.py` | 37 passed | **3 failed** |
| la receta, ejecutada de verdad | `SUCCESS` | **`Pipeline finished with FAILURE`** |

La tercera fila es la importante: **la receta se detecta a sí misma**. Mutaciones
6/6, y la sexta vuelve a borrar la etapa en el fichero real — un invariante que
solo sabe fallar con informes sintéticos no ha medido nada.

## [0.20.2] - 2026-10-02 — el bundle de auditoría certificaba UATs que no ejecutaba

**PATCH**: `git log v0.20.1..HEAD` = 0 `feat`, 1 `fix`, 1 `docs`, 0 breaking.
**2661 passed** (2647 antes; +14).

Delegar en la receta canónica no basta si el paso que viene después no mide
nada. `scripts/audit_bundle.sh` es el instrumento que existe *para* dar
evidencia reproducible a una auditoría independiente, e invocaba
`python -m tests.uat_audit` sin flags: el modo lectura, que no ejecuta un
solo UAT y relee los 26 JSON de `tests/uat-evidence/`. El `PASS=16` del
bundle de WI-99 se escribió mirando ficheros del commit `0ebbd58`, 111
commits por detrás.

### El exit code no significaba nada

El modo lectura hacía `return 0` **incondicional**. La guarda del bundle
(`if [ "$UAT_RC" -ne 0 ]`) compara contra ese código, así que no podía
dispararse jamás por el estado de la evidencia. Medido con el comando
exacto del bundle:

| evidencia en disco | salida | exit code |
|---|---|---|
| `UAT-01.json` inyectada en `FAIL` | `PASS=15 FAIL=1` | **0** |
| `tests/uat-evidence/` ausente | `PASS=0 FAIL=0` | **0** |

Un bundle con un `FAIL` a la vista y otro sin una sola evidencia eran
indistinguibles de uno sano.

### Un total que no suma las filas no es un total

El primer test del bloque puso `status: "passed"` y falló por lo que menos
se esperaba: el resumen imprimía `PASS=15 FAIL=0 BLOCKED=0` sobre **16 filas
leídas**, porque el recuento solo miraba las tres etiquetas conocidas. El
número era cierto letra a letra y estaba mal. De ahí la lista **blanca**
(`PASS`, `BLOCKED`) en vez de negra: el conjunto de cosas malas no tiene fin.

### Lo que se arregla

- El exit code sale de `_verdict`, compartido por los tres modos, para que no
  puedan divergir entre sí.
- `--verify` (nuevo) ejecuta los UATs, no persiste, y **confronta** cada
  veredicto con la evidencia persistida. Sin ese contraste la evidencia era
  la única fuente del veredicto y no se contrastaba con nada.
- El resumen cuenta los veredictos fuera de dominio en vez de tragárselos.

Verificado después del arreglo, no antes: los 16 UAT se ejecutan de verdad y
**convergen** con la evidencia versionada. La evidencia era cierta; lo que
faltaba era comprobarlo. Mutaciones 9/9 en rojo.

## [0.20.1] - 2026-10-02 — los hooks de git decían una cosa y hacían otra

**PATCH**: `git log v0.20.0..HEAD` = 0 `feat`, 3 `fix`, 3 `test`/`docs`, 0 breaking.
**2647 passed** (2636 antes; +11).

WI-99 dejó escrito, en dos sitios, que `scripts/hooks/pre-push` era deuda
medida. Una deuda con dueño escrito es una promesa.

### La medición, mismo commit y mismo `.coverage.rc`

Única variable: el hook `.pth` que `scripts/coverage.sh` instala para que
los subprocesos se midan.

| módulo | hooks | `coverage.sh` | Δ |
|---|---|---|---|
| `cli/commands/runs.py` | **39 %** | **88 %** | **−49** |
| `cli/runner.py` | 55 % | 79 % | −24 |
| `cli/support.py` | **69 %** | 86 % | **−17** |
| TOTAL | 90,79 % | 95,22 % | −4,4 |

`cli/support.py` mide **69 %** con el instrumento del pre-push, y el suelo
que declara el propio `AGENTS.md §6.3` para la CLI es **70 %**. El gate más
cercano al push podía dar **verde un paquete que no cumplía el suelo
declarado**, y no ejecutaba ninguno de los cuatro contratos exigibles.

### Changed

- `scripts/hooks/pre-push` **delega** en `scripts/ci.sh`, que es el dueño de
  cómo se llega a la receta canónica. No la reimplementa: la pide.
- `scripts/hooks/pre-commit` hace el smoke que decía hacer: pasa `$STAGED_PY`
  a pytest. **124,29 s → 0,83 s.** Antes seleccionaba los `.py` staged y no
  se los pasaba: corría la suite entera anunciando «smoke, ~10 s».
- **C4 se afina** a «pytest **sobre el repo entero**», y
  `DIRECTORIOS_NO_RECETA` **desaparece**. Una propiedad que hay que mantener
  al día no es una propiedad, es una suscripción.
- `scripts/check_ci_recipe_parity.py` descubre scripts por **shebang**, no
  solo por extensión: `pre-commit` y `pre-push` no tienen extensión, y el
  invariante daba verde sin haberlos mirado nunca.

### Fixed

- Un `echo` de diagnóstico con `pytest` y `$N_STAGED` contaba como
  invocación, y **C4 llevaba dos commits dando verde por el motivo
  equivocado**. La regla correcta es *qué comando lanza la línea* —ver
  `_VERBOS_DE_MENCION`—, que se decide por el primer token no estructural.
  Es una lista de **palabras del lenguaje**, no de ficheros del repo: a
  diferencia de la lista de excepciones de WI-99, no se desactualiza cuando
  el repo crece.
- `pytest src/` —un directorio— también cuenta como filtrado. Reconocer solo
  ficheros `.py` habría hecho que un directorio se contara como suite entera.

### Tests

Siete guards de **cadena** sobre el `pre-push` pasan a medir **propiedad**.
Dos de ellos **ejecutan** el hook sobre un repo de prueba con un
`scripts/ci.sh` stub que falla si se invoca: es la primera vez que
`tests/test_hooks_system.py` comprueba comportamiento y no forma. «El hook
menciona el bypass» era indistinguible de «el bypass funciona».

**Mutaciones 10/10.** M7 —degradar el `pre-commit` a la forma que corre la
suite entera— es la que encontró el falso positivo del `echo`: sin ella, el
invariante habría dado verde indefinidamente por el motivo equivocado.

### Lo que este bloque NO resolvió

El `pre-push` **no estaba instalado** en la máquina donde se operaba
(medido), y el `pre-commit` instalado es la copia anterior: hasta que alguien
corra `bash scripts/install-hooks.sh`, cada commit sigue pagando 124 s.
Instalar el git local del operador es suyo.

Evidencia completa: `evidence/sddk-wi100-verify-2026-10-02.md`.

## [0.20.0] - 2026-10-02 — la evidencia de auditoría no era reproducible

**MINOR**: `git log v0.19.0..HEAD` = 1 `feat`, 3 `fix`, 3 `test`/`docs`/`chore`, 0 breaking.
**2636 passed** (2625 antes; +11).

`scripts/audit_bundle.sh` existe para dar evidencia reproducible a una
auditoría independiente. La primera medición usó la respuesta, y no era la
esperada.

**Mismo commit `504b65d`, dos árboles:**

| | resultado |
|---|---|
| árbol de trabajo (donde se construyó) | `2625 passed` |
| **clon limpio del mismo commit** | **`2 failed, 2623 passed`** |

Un guard que decía la verdad —su mensaje literal era *«afirmación sin
respaldo»*— y fallaba justo en el sitio donde se audita. Eso no es un test
rojo: es un entregable declarado cumplido cuya evidencia no viaja en el
repo.

### Causa raíz 1 — `.gitignore` tapaba la evidencia

`STATE.yaml` declaraba dos entregables de H9 (E2 y E4) como cumplidos, con
`docs/architecture/ADR-0015-threat-model-stride.md` y
`docs/observability-runbook.md` como evidencia. **Ninguno versionado**: el
patrón `docs/*` los cubría. De 150 referencias con forma de fichero, 3 no
estaban versionadas, 1 no existía, 3 estaban bajo `external/` (correcto) y
1 era una plantilla.

El `.gitignore` se reescribió separando las dos categorías que `docs/*`
trataba como una —evidencia que el código referencia frente a material de
trabajo— y se versionaron los tres documentos. La referencia inexistente
queda anotada como irrecuperable: **no se inventó el testigo**.

### Causa raíz 2 — `scripts/ci.sh` era una cuarta receta

| | receta canónica | `scripts/ci.sh` |
|---|---|---|
| stages | 8/8 | 3 |
| contratos exigibles | 4/4 | **0** |
| `cli/commands/runs.py` | 87,96 % | **39 %** |

Y `audit_bundle.sh` lo invocaba: **el instrumento que existe para medir
medía con el que no ve**. `ci.sh` pasa a **delegar** en `.pipeline.kts`;
arreglar una vez arregla las dos cosas.

### Causa raíz 3 — el comando canónico no arrancaba en un clon nuevo

```
mise: Trust them with `mise trust`
java.sql.SQLException: path to '.pipelinek/db.sqlite': ... does not exist
```

`mise` no ejecuta las herramientas de un checkout en el que no confía, y
`pipelinek` **abre el fichero SQLite, no el directorio que lo contiene**. Es
el mismo patrón que WI-98 eliminó de `.pipeline.kts`: una regla que no se
puede cumplir fuera de esta máquina no es un contrato, es una costumbre.
Arreglo: `.pipelinek/.gitkeep` versionado y `ci.sh` resuelve ambas.

### Added

- `feat(ci)`: invariante **C4** en `check_ci_recipe_parity.py` — *un script
  que ejecuta `pytest` tiene que ser un fragmento de la receta canónica o
  delegar en ella*. Disyuntiva a propósito: la versión restrictiva hace del
  propio fichero de cobertura una infracción y sólo admite una lista de
  excepciones que el guard mantiene.
- 11 tests (30 en el fichero del checker). **Mutaciones 6/6**, una de ellas
  restaurando el `ci.sh` real de antes de WI-99, sacado de git.

### Fixed

- `fix(governance)`: tres documentos de `docs/` versionados; dos entregables
  de H9 dejaban de declarar evidencia que git no llevaba.
- `fix(ci)`: `scripts/ci.sh` delega en la receta canónica. `--quick` queda
  como modo de iteración explícitamente **no certificante**.
- `fix(ci)`: `.pipelinek/.gitkeep` versionado; el comando canónico
  documentado es ejecutable en un clon nuevo.

### Cierre medido

`bash scripts/audit_bundle.sh 984289d` sobre un **clon limpio**:
`Pipeline finished with SUCCESS`, **8/8 stages**, **2636 passed in 239.26s**,
cobertura 95,22 %, `PASS=16 FAIL=0 BLOCKED=0` en UAT. **Divergencia 0 en
ese commit** — 2636 en el árbol, 2636 en el clon. Antes: 2625 y
2623+2 failed.

### Y una corrección que esa medición no cubría

La primera CI canónica **sobre el estado final** dio `2 failed, 2634
passed`. Los dos fallos eran de la trazabilidad escrita **después** de
medir: el tag `v0.20.0` no estaba registrado en `STATE.yaml`, y el bloque
vivo de `CURRENT.md` no citaba ninguna línea verificable. Dos guards que
ya existían —`test_state_release_integrity` y
`test_wi92_measured_claims`— los atraparon sin ayuda.

La divergencia 0 estaba medida **para `984289d`**, que es anterior a la
trazabilidad. Escribirla como propiedad del estado final era una
afirmación que nadie había medido, y el documento que la hacía falsa era
precisamente el que la afirmaba. Corregido y re-medido.

**La reproducibilidad hay que certificarla después de escribir la
certificación, no antes.**

Evidencia completa: `evidence/sddk-wi99-verify-2026-10-02.md`.

### Lo que este bloque NO resolvió

97+ commits sin publicar (push no autorizado); credenciales Anthropic/OpenAI
ausentes, que bloquean el criterio de salida de H9 desde WI-91;
`release.complete` inalcanzable (se cierra con `cycle supersede`);
`scripts/hooks/pre-push` sigue midiendo con el instrumento ciego y queda
**excluido de C4 por escrito, con la exclusión fijada por un test**; los
4 errores de `sddk lint` son checks de perfil **autor de pack** y este repo
es perfil **consumidor**, así que adoptarlos sería cargo-culting. La deuda
reportada de `raise ValueError`/`Exception` en el dominio se midió en **0**.

## [0.19.0] - 2026-10-02 — el remoto ejecutaba otra receta, y el guard buscaba cadenas

**MINOR**: `git log v0.18.0..HEAD` = 1 `feat`, 2 `fix`, 3 `test`/`docs`, 0 breaking.
**2625 passed** (2605 antes; +20).

`AGENTS.md` dice, en una línea: *«GitHub Actions, GitLab CI, Jenkins o
cualquier otro runner remoto **debe** invocar el mismo `.pipeline.kts`»*.
No lo hacía, y no podía.

### La divergencia, medida con el mismo instrumento

| | receta local | `ci.yml` antes |
|---|---|---|
| stages ejecutados | **8** | **1** (`lint`) |
| contratos exigibles | 4 | **0** |
| `cli/commands/runs.py` | 87,96 % | **39 %** |
| `cli/commands/run.py` | 96,09 % | 81 % |
| `cli/support.py` | 85,71 % | **69 %** ← suelo declarado: 70 % |

El remoto podía dar **verde** un paquete que no cumplía el suelo que el
propio `AGENTS.md §6.3` declara. El contraste usa el **mismo** checker en
las dos recetas: comparar el remoto, medido sin el hook `.pth`, contra un
94 % de la instrumentada habría sido comparar dos cosas distintas y
llamarles divergencia.

### Added

- `feat(ci)`: **`scripts/check_ci_recipe_parity.py`**, stage `ci-parity` —
  el **cuarto** contrato exigible y el primero que vigila a los otros tres.
  Comprueba que todo runner remoto invoque la receta canónica **en un paso
  que se ejecuta** y que la receta se pueda ejecutar fuera de esta máquina.

### Fixed

- `fix(ci)`: **`.pipeline.kts` no era portable.** Llevaba diez rutas
  absolutas a `/var/mnt/DiscoChino2-fast/...`, lo que arreglaba el síntoma
  local y dejaba la receta **inejecutable en cualquier otra máquina**: la
  regla de runners era una promesa que no se podía cumplir ni con el mejor
  workflow. Ahora la raíz se resuelve con
  `System.getenv("GITHUB_WORKSPACE") ?: System.getProperty("user.dir")` —
  medido antes de escribir el código: el motor **sí** propaga el entorno a
  los `sh()`.

- `fix(ci)`: **`ci.yml` invoca la receta canónica** con un solo paso, con
  `--rerun` y con token para `mise` (sin él, `pipelinek` resuelve el shim de
  asdf, que es otro binario con la misma ruta de nombre). Se conserva la
  subida de `coverage.xml`, que era una capacidad real y no un *string*,
  exportándola del `.coverage` combinado e instrumentado.

- `test(hooks)`: los **nueve** tests que buscaban cadenas en `ci.yml`
  quedan sustituidos por ocho que miden propiedades. Uno de ellos aceptaba
  `assert "pytest" in content or "test" in content.lower()`, que un
  fichero con la palabra *test* en un comentario satisfacía.

### El guard cayó en la trampa que viene a cerrar

Las cinco primeras mutaciones dieron `rc=0`. El defecto no estaba en los
tests: estaba en el diseño del invariante, y era el mismo defecto que el
bloque viene a sustituir.

- **C1** buscaba `.pipeline.kts` en el contenido entero del workflow. El
  workflow menciona la receta en un comentario que explica que se usa, y
  el guard encontraba la cadena ahí y aprobaba un workflow que ejecutaba
  otra cosa. Ahora mira los **pasos ejecutables**.
- **C2** buscaba rutas absolutas *dentro* de `sh(...)` y no veía nada
  cuando la ruta estaba en una `val` de Kotlin — que es justo donde se
  mueve una para arreglar el problema. **Un invariante que solo mira una
  sintaxis concreta se esquiva cambiando de sintaxis.** Ahora son dos
  condiciones verificables sin heurística: el script resuelve la raíz y no
  contiene la raíz de este árbol.

El script de mutaciones también estaba mal, por dos motivos que quedan
escritos: `mktemp` pasa por un wrapper que manda el fichero recién creado a
la papelera (los respaldos no existían), y las mutaciones sustituían una
línea de un bloque `run: >` dejando las siguientes, con lo cual la receta
seguía presente. **Un contraejemplo que no degrada nada no prueba que el
guard funcione: prueba que el script de mutaciones está mal.**

### Mutaciones

**5/5**, con restauración byte a byte de los dos ficheros.

## [0.18.0] - 2026-10-02 — el paquete se construye, y alguien lo comprueba

**MINOR**: `git log v0.17.0..HEAD` = 1 `feat`, 3 `fix`, 4 `test`/`docs`, 0 breaking.
**2605 passed** (2567 antes; +38).

La cadena de release `git → __version__ → pyproject → wheel` se detenía
antes de su último eslabón. Medido: **el build no estaba roto**. `uv build`
termina en 1,7 s, produce un wheel de 248 KB con los 80 módulos, instala en un
venv limpio y `skillgraph --help` responde. El hueco no era que nada
funcionara: es que **nadie lo miraba nunca**. Cero tests referenciaban
`hatchling`, `uv build` o `entry_points`, y ningún stage de `.pipeline.kts`
construía el paquete.

### Added

- `feat(build)`: **`scripts/check_package_build.py`** construye wheel y sdist
  reales y verifica siete invariantes. Stage propio `package-build`: **siete
  stages**. Coste medido, 1,7 s — el más barato de los que miden algo.

  La capa pura (`evaluar_*` sobre un `InformeBuild`) está separada de la de
  efecto. Esa separación es lo que permite construir los contraejemplos con
  informes sintéticos: sin ella, probar que el checker detecta un módulo
  ausente exigiría mutar el árbol de trabajo.

- `test(build)`: 38 tests. Cinco construyen el paquete de verdad; el resto
  comprueban las invariantes con los informes sintéticos. **Mutaciones 7/7.**

- `docs(agents)`: `AGENTS.md §12` documenta el tramo que faltaba —que el
  número tiene que llegar al artefacto— con la tabla de invariantes, y §9 ata
  el contrato al cambio concreto que puede romperlo. Va en §12 porque ése es
  el dueño de la regla de release: dos enunciados son dos fuentes que se
  desincronizan, el error que WI-96 ya corrigió con la regla de SemVer.

### Fixed

- `fix(build)`: **el sdist declaraba nueve rutas y llevaba catorce.** El
  `include` de hatchling es un filtro, no una lista blanca: lo que no nombra
  entra si el `.gitignore` no lo detiene. `bench/` y `docs/` viajaban sin
  estar declaradas, y cambiando un solo patrón se colaba también `audits/`.
  Ahora es `only-include`, que sí es lista blanca. El conjunto que viaja no
  cambia; lo que cambia es que el artefacto queda determinado por la lista y
  no por lo que el backend decida colar.

- `fix(build)`: **dos invariantes que las mutaciones destaparon.** La primera
  pasada cazó 5 de 7:

  - Comparar «lo declarado» con «lo publicado» es tautología a medias,
    porque lo publicado **se deriva** de lo declarado. Un target equivocado
    sale idéntico en los dos lados mientras el comando no existe. La
    invariante nueva importa el módulo.
  - Una lista más corta no contradice a nada: no es una promesa rota, es una
    promesa **retirada**. Quitar `tests` del `only-include` reducía el sdist y
    ningún check de git lo notaba. `src/skillgraph`, `tests` y
    `docs/blueprint` se exigen ahora **en el artefacto**, no en la
    declaración.

- `fix(uat)`: el skip del snapshot del blueprint era una rama que nunca se
  tomaba — el fichero está versionado — y llevaba `pragma: no cover`, que lo
  hacía invisible al informe de cobertura. `AGENTS.md §6.2` prohíbe
  `pytest.skip` para esconder fallos. Verificado con un contraejemplo real:
  moviendo el fichero, el test pasa de saltarse a **fallar**.

### La invariante que más importa

`sg_build_sdist_no_versionado`: **el artefacto no puede llevar nada que git
no versione**. Un sdist que hereda del árbol de trabajo hace que dos árboles
con el mismo commit produzcan dos artefactos distintos, y a partir de ahí
`git` deja de poder decir qué se publicó. Es lo que convierte el build en un
eslabón verificable en vez de en un ritual.

### Deuda registrada, no abierta

- `tests/test_wi41_cli_dispatch.py` tiene un `pytest.skip("auditoria del dia
  no generada todavia")`: el gate D1 lee
  `audits/architecture-debt-<hoy>.md`, y el último informe versionado es del
  `2026-10-01`. El gate sólo se ejecuta el día exacto en que se genera el
  informe; el resto del tiempo es un skip perpetuo, indistinguible de un test
  que no vigila. **Mismo patrón que el skip que este bloque arregla**, pero
  fuera de la superficie: se registra, no se abre.
- `src/skillgraph.egg-info/` (rescoldo de un `setup.py` del 2026-09-23) sigue
  en el árbol de trabajo. No está versionado, `.gitignore` lo tapa, y el
  contrato nuevo lo excluiría si colara en un artefacto. No es deuda.

## [0.17.0] - 2026-10-02 — la versión se deriva, no se recuerda

**MINOR**: `git log v0.16.20..HEAD` = 1 `feat`, 1 `fix`, 0 breaking.
**2567 passed** (2559 antes; +8).

Y el número no lo decidió nadie: lo calculó
`scripts/derive_semver.py` sobre el historial.

```
== desde v0.16.20 hasta HEAD ==
  b/f/x/n/d: 0/1/1/2/0
  la regla pide MINOR -> v0.17.0
```

### Added

- `feat(release)`: **`scripts/derive_semver.py`** recorre el historial y dice
  cuál es el bump de cada etiqueta **y de HEAD**, además de las divergencias
  y de los cambios rompedores sin marcar.
  `test_release_governance` ata la etiqueta a `__version__` —comprueba que el
  número sea coherente consigo mismo—; esto ata el número **al historial**.
  Durante 47 releases ese cálculo se hizo a mano.

- `test(governance)`: 8 tests sobre tres garantías — la regla tiene **un**
  dueño, la salvedad 0.x está escrita donde se lee, y el bump se calcula.
  Mutaciones **3/3**, y las dos primeras las encontró el propio guard.

### Fixed

- `fix(governance)`: **la regla de SemVer estaba en el fichero equivocado.**
  `AGENTS.md §12` se titula «Regla de release» y no la contenía; el único
  enunciado estaba en la cabecera del CHANGELOG, que no es el dueño de la
  gobernanza de releases. Medido sobre 47 etiquetas con la regla tal como
  estaba escrita: **9 releases cuyo SemVer no se deduce de ella**, 9 que la
  regla dice que no deberían existir, y **3 con un cambio rompedor real que no
  llegaron a 1.0.0**.

  - La tabla se muda a `§12` («Derivar la versión») con la **salvedad 0.x** y
    sus tres precedentes nombrados.
  - El CHANGELOG pasa a **referenciar** §12: dos enunciados de la misma regla
    son dos fuentes que se desincronizan, y una ya se ha desincronizado.
  - **Las trece divergencias se registran y NO se corrigen**: son etiquetas
    publicadas y su número es provenance.

### El giro del bloque: los tres precedentes no llevan el marcador

Al escribir el detector resultó que `v0.7.0`, `v0.15.0` y `v0.16.2` **no
llevan el marcador de la convención**: no hay `!` ni un footer
`BREAKING CHANGE:` al principio de una línea, sino una **viñeta de prosa**.

Eso no es un detalle, es el problema entero: *con el marcador ninguna
herramienta puede verlos; sin él, el bump se deduce mal y la exención queda
sin justificación visible.*

El primer clasificador buscaba la cadena `BREAKING CHANGE` en el cuerpo, y por
eso contaba como breaking el propio commit que estaba describiendo la
cláusula. Al exigir la forma de footer, los tres desaparecieron del recuento.
La conclusión correcta no es «no eran breaking», sino **«fueron breaking y no
estaban marcados»**. Se reporta aparte, **sin que cuente** para el bump:
ensanchar la convención después de ver los datos sería rehacer la regla.

### Conocimiento negativo

- **Un guard que busca una cadena comprueba que la cadena exista, no la
  propiedad.** Dos veces aquí: M1 vaciaba la cláusula 0.x conservando el
  texto `0.x`, y el patrón de WI-95 buscaba `->` en un fichero que usa `→` y
  pasaba en verde **con la tabla presente**.
- **La decisión correcta puede seguir siendo invisible.** Las tres veces que
  no se subió a 1.0.0 se decidió bien; faltó el marcador que la haría
  citable por una máquina. **Marcar cuesta un carácter y no obliga a nada**
  mientras se esté en 0.x, porque la cláusula lo exonera.
- **La herramienta se corrigió usándola.** Los dos fallos del clasificador no
  salieron leyendo el código, sino ejecutándolo.
- **Un guard que exige algo que el propio repo no cumple se aprende a
  ignorar.** La exigencia de coincidencia empieza en `v0.16.3` —donde la
  regla se cumple 18/18— y las divergencias se comparan **bidireccionalmente**.

- Evidencia: `evidence/sddk-wi96-verify-2026-10-02.md`.

## [0.16.20] - 2026-10-02 — el CHANGELOG deja de anunciar como pendiente lo ya publicado

PATCH: `git log v0.16.19..HEAD` = 0 feat, 0 breaking, **2 fix**, 1 test, 2 docs,
1 chore. 2559 passed (2551 antes; +8).

Los dos `fix` son el de este bloque y el que WI-94 dejó pendiente a propósito
(`cbc8c04`, la dependencia circular). Agruparlos es exactamente lo que pedía
la regla de cadencia: en WI-94 resisted la tentación de abrir una etiqueta
para un `fix` de tests, y una release mas tarde salió con contenido de verdad.

### Fixed

- `fix(docs)`: **`CHANGELOG.md` declaraba `[Unreleased]` para tres bloques que
  se publicaron hace dos releases.** Medido antes de tocar nada:

  | | |
  |---|---|
  | tags SemVer en git | 46 |
  | versiones distintas en el CHANGELOG | 44 |
  | tags **sin sección** | 2 (`v0.16.14`, `v0.16.15`) |
  | cabeceras `[Unreleased]` falsas | 3 (WI-87, WI-88, WI-89) |
  | tests que parseen el CHANGELOG | **0** |

  `STATE.yaml` tiene una red que lo ata a `git tag` con igualdad exacta desde
  WI-74. **El CHANGELOG no tenía ninguna**, y por eso llevaba dos releases
  desfasado sin que nada lo notara.

  Lo más incómodo era que el fichero se contradecía a sí mismo: la sección de
  WI-88 decía, en dos líneas consecutivas, «Sin bump todavía» y «la release
  que lo contiene es `v0.16.14`». La cabecera ya sabía la verdad y el cuerpo
  no.

  | Antes | Ahora | Tag |
  |---|---|---|
  | `## [Unreleased] — WI-89` | `## [0.16.15]` | `6819f99` |
  | `## [Unreleased] — WI-88` | `## [0.16.14]` | `3cfce09` |
  | `## [Unreleased] — WI-87` | `## [0.16.14] (cont.)` | — |

  Cada sección lleva una nota `CORREGIDA` que dice que lo estaba y por qué, en
  la línea de lo que hizo WI-91 con las afirmaciones propagadas: la corrección
  se escribe en el documento, no se aplica en silencio.

- `fix(test)`: la cola de WI-94. Los tests de WI-94 leían el informe de
  cobertura que `scripts/coverage.sh` sólo combina **después** de pytest, así
  que la CI los daba por buenos mientras en local pasaban. *Pendiente desde
  WI-94 a propósito; entra aquí.*

### Added

- `test(governance)`: 8 tests que atan `CHANGELOG.md` a `git tag` — todo tag
  tiene sección, toda sección tiene tag, nada publicado se anuncia como
  `[Unreleased]`, y una `(cont.)` tiene su versión padre justo antes. Mutaciones
  **3/3**.

### Conocimiento negativo

- **La primera versión del guard tenía un agujero y lo encontró la mutación M3
  al primer intento.** La aserción sobre `(cont.)` solo miraba el número de
  repeticiones, y dos secciones no son «más de dos», así que convertir un
  `(cont.)` en una sección de versión más pasaba desapercibido. El invariante
  correcto no es contar: es que **sólo la primera aparición de una versión
  puede no ser continuación**. Sin eso, la convención `(cont.)` es decorativa,
  porque nada obliga a marcarla.
- **Un guard que exige un orden que el propio fichero no cumple se aprende a
  ignorar.** El tramo antiguo (`0.14.1 → 0.7.0 → … → 0.3.0 → 0.8.1 → … →
  0.14.0`) está desordenado desde antes. Exigir orden global habría hecho fallar
  el guard en el primer run por 20 secciones de 2026-09. Lo que se vigila es
  que **la zona que se escribe hoy** siga en orden descendente; lo antiguo queda
  medido y documentado, **no arreglado**: es cosmético, y mover texto
  histórico es el riesgo que este proyecto lleva cuatro bloques evitando.
- **Un regex que se queda en el primer `]` no ve el `(cont.)`**, porque va
  fuera de los corchetes: `## [0.16.19] (cont.)`. Un test que cuenta
  continuaciones con ese regex cuenta cero, y da verde sin comprobar nada.
- **Un documento puede contradecirse a sí mismo línea a línea.** «Sin bump
  todavía» y «la release que lo contiene es v0.16.14» convivían en el mismo
  párrafo. La contradicción interna es más fácil de detectar que la falsa
  afirmación aislada, y aquí estaba debajo de la vista.

- Evidencia: `evidence/sddk-wi95-verify-2026-10-02.md`.

## [0.16.19] - 2026-10-02 — los dos `fix` de la cola de WI-93 salen en release

PATCH: `git log v0.16.18..HEAD` = 0 feat, 0 breaking, **2 fix**, 1 refactor,
1 test, 1 chore, 1 docs. 2552 passed (2529 antes; +23).

Lo que dispara esta etiqueta **no es WI-94**: es que los dos `fix` de la cola
de WI-93 se emitieron **después** del tag `v0.16.18` y quedaban sin publicar
en ninguna release. Un tag que se emite en medio del trabajo deja commits
fuera, y el SemVer derivado hay que leerlo sobre `v0.16.18..HEAD`, no sobre
«lo que hizo este bloque».

### Fixed

- `fix(ci)`: **la línea de resumen de pytest no llegaba al journal de la
  pipeline.** `EchoOutputCaptured` conserva sólo los últimos ~1,2 KB de la
  salida de cada step, y con `pytest -q` la línea `N passed in Xs` cae a
  media stream y se truncaba. AGENTS.md la exige porque es lo que separa una
  ejecución real de un veredicto cacheado: sin ella, la run era real y su
  prueba había quedado fuera del recorte. `scripts/coverage.sh` hace `tee` a
  `.pipelinek/unit-tests.log` y reimprime el resumen al final, y toma el exit
  code de pytest con `${PIPESTATUS[0]}` y no del pipeline.

- `fix(state)`: **`v0.16.18` estaba etiquetada en git pero no en el registro.**
  `release.releases` no la listaba y `release.tag` se había quedado en
  `v0.16.17`, dos versiones atrás. Lo detectaron los dos tests de
  `test_state_release_integrity`, que existen justo para eso. El defecto fue
  de **secuencia**: el commit de trazabilidad se cerró antes de emitir el tag.

## [0.16.19] (cont.) — WI-94: el contrato de cobertura que escribí en WI-93 sólo se cumplía donde yo miré

Sin bump propio: el bloque entrega 1 `refactor` + 1 `test`, y ninguno bumpea
SemVer. Viaja dentro de v0.16.19 por los `fix` de arriba, como WI-92 viajaba
en v0.16.18.

### Changed

- `refactor(ci)`: **el contrato de AGENTS §6.3 se mide por paquete, no por una
  lista de módulos escrita a mano.** WI-93 lo implementó con 21 entradas y
  aplicó la regla de «todo módulo tiene suelo» **sólo a `runtime/`**. Medido:

  - Siete de los ocho paquetes que gobierna §6.3 no tenían ninguna regla. Un
    módulo nuevo al 40 % en `governance/` no lo habría visto nadie: **el mismo
    fallo que WI-93 cerraba, sin cerrar en el resto.**
  - `cli/` se medía **sólo en agregado** (70 % sobre un paquete que mide
    86,91 %): 16,91 puntos de holgura, y un módulo de `cli/` podía caer al
    0 % sin romper el contrato. La evidencia de WI-93 ya advertía de que «la
    cobertura agregada puede tapar un módulo débil» — se aplicó a `runtime/`
    y se pasó por alto en la otra mitad del contrato.

  `SUELOS_POR_PAQUETE` (8 prefijos) + `EXCEPCIONES` (`paths.py` al 60 %, que es
  el suelo que §6.3 le da explícitamente). Un módulo nuevo en cualquier paquete
  cubierto queda vigilado al aparecer. Los agregados se conservan como
  comprobación **adicional**, nunca en lugar de la por módulo.

  `evaluar()` pasa a ser **pura** (informe → líneas, fallos), separada de
  `main()`: es lo que permite probar el contrato con informes sintéticos sin
  disco ni subprocess.

  Con la lista fuera desaparece la detección de «módulo fantasma» que hacía la
  lista, y la sustituye una aserción mejor: un paquete declarado que no aporta
  ningún módulo es un fallo, porque o se borró o se renombró.

- `test(governance)`: 23 tests que fijan la **propiedad** del contrato sobre
  informes sintéticos, no el número de hoy. Mutaciones **4/4** con baseline y
  control final byte-idéntico.

### Conocimiento negativo

- **Un guard que vigila el árbol real sólo detecta lo que ya está roto.**
  La mutación M3 —reintroducir la asimetría exacta de WI-93— no produce ningún
  fallo en el script, porque el código cumple y luego todo verde. El defecto
  era invisible para el propio guard que lo dejaba pasar: sólo un test que
  construye el contraejemplo a mano lo detecta.
- **Aplicar un principio a media mitad de su propio contrato es la forma más
  difícil de detectar el defecto**, porque la mitad donde sí se aplica
  funciona y da credibilidad al conjunto.
- **Un `assert fallos` a secas puede pasar por un ruido ajeno.** El helper
  exige que el fallo **nombre** al módulo bajo prueba.
- **Un test que necesita un artefacto que pytest produce *después* no puede
  vivir dentro de pytest.** Los tests de este bloque leían el informe de
  cobertura para afirmar sobre él, y `scripts/coverage.sh` sólo lo combina
  cuando pytest ha terminado. En la CI fallaron 9; `pytest` a pelo pasaban,
  porque en local ya había una medición anterior. *Un número cierto medido
  en unas condiciones no es un número válido si se aplica a otras.* Que un
  paquete tenga módulos se pregunta al **árbol**, no al informe. La
  comprobación «el árbol real cumple el contrato» vive en el
  stage `coverage-floors`, que corre después de la medición: el sitio
  correcto para comprobar una propiedad de la medición es después de medir.
- **Ninguno de los ocho paquetes tenía hoy un módulo por debajo de su suelo.**
  El defecto era del guard, no del código: el margen más estrecho es
  `runtime/locks.py` al 90,62 % sobre un suelo del 90 %.

- Evidencia: `evidence/sddk-wi94-verify-2026-10-02.md`.

## [0.16.18] - 2026-10-02 — WI-93: el contrato de cobertura que el repo declaraba y no exigía

PATCH: `git log v0.16.17..HEAD` = 0 feat, 0 breaking, 1 fix, 2 test, 3 docs, 1 chore. 2529 passed
(2499 antes).

Este tramo contiene también WI-92, que **no tuvo etiqueta propia** porque su SemVer
derived fue 0 (1 `test` + 1 `docs`). Sus commits viajan dentro de v0.16.18 y su
sección queda como `(cont.)` más abajo, igual que WI-86 hizo en v0.16.13.

### Fixed

- `fix(ci)`: **AGENTS §6.3 declaraba suelos de cobertura por módulo y nada los
  comprobaba.** El repo tenía dos contratos sobre cobertura y la CI canónica no
  ejecutaba ninguno:

  | # | Dónde | Qué declara | ¿Quién lo comprueba? |
  |---|---|---|---|
  | 1 | `pyproject.toml` `[tool.coverage.report]` | `fail_under = 80` (global) | `coverage report`, sólo si alguien invoca el script a mano |
  | 2 | `AGENTS.md §6.3` | suelos **por módulo**: core ≥90 %, CLI ≥70 %, `paths.py` ≥60 % | **nadie** |

  El segundo contrato **no lo podía expresar ninguna herramienta del repo**:
  `coverage report` sólo admite un umbral global. Una cifra declarada y no
  verificable no es un contrato.

  - `scripts/check_coverage_floors.py` (nuevo, versionado en `scripts/`) exige
    suelo **por módulo** y además exige que **todo módulo de `runtime/` con código
    tenga suelo declarado**, para que añadir uno nuevo no pase inadvertido. Un
    guard que sólo vigila la lista que él mismo mantiene no vigila nada.
  - `.pipeline.kts` pasa a 6 stages: `unit-tests` corre la receta de cobertura y
    un stage nuevo `coverage-floors` corre el checker. **Una sola pasada** para
    tests y cobertura: correr pytest dos veces costaría 110 s + 203 s.

  **Agrega recuentos, no porcentajes.** Con `branch = true` una rama parcial cuenta
  como media; promediar porcentajes da más de lo que hay — un paquete al 95 % de
  media puede esconder un módulo al 60 %.

  **Un suelo sobre un módulo fantasma es un fallo**, no un silencio: si la ruta no
  aparece en el informe, el checker aborta. Los módulos vacíos (los `__init__.py`
  de reexport, 0 sentencias) quedan excluidos: exigirles un suelo es exigir medir
  un fichero vacío, y revienta con división por cero.

### La premisa heredada, medida

`scripts/coverage.sh` llevaba en su cabecera una decisión documentada de **no**
usarlo como gate, con el motivo de que «la instrumentación de subproceso
multiplica el tiempo de suite». Era una afirmación sin dato. El dato:

| | Wall clock |
|---|---|
| `pytest` a pelo (lo que hacía la CI) | ~110 s |
| `scripts/coverage.sh` completa | 203 s |
| **Delta** | **+93 s (~1,85× el stage)** |

No multiplica: cuesta un minuto y medio más. El párrafo queda **retirado y
marcado como SUPERSEDIDO**, conservado como historia.

### Added

- `test(knowledge)`: `tests/test_wi93_http_adapter_gaps.py` (30 tests) cubre las 19
  ramas sin cubrir de `runtime/http_adapter.py`. El módulo ya traía failpoints y un
  `client` inyectable **precisamente** para probarlas sin red; los tests de red
  existentes usan `respx` con cliente inyectado, y por eso la rama de producción
  que construye su propio `httpx.Timeout` no la tocaba nadie.

  | | Antes | Después |
  |---|---|---|
  | `http_adapter.py` | 88,04 % | **99 %** |
  | `runtime/` agregado | 95,11 % | **97,98 %** |
  | global | 94,75 % | **95,22 %** |

  Sólo queda sin cubrir la línea 424, un `defensive: should not reach here`
  inalcanzable por construcción.

- `scripts/check_coverage_floors.py` con 4 mutaciones cazadas 3/3 (subir un suelo
  por encima de la cobertura real, apuntar un suelo a un módulo inexistente,
  borrar el suelo de un módulo de `runtime/` con código) y control final
  byte-idéntico.

### Conocimiento negativo

- **La cobertura agregada puede tapar un módulo débil.** `runtime/` estaba al
  95,11 % — muy por encima de 90 — y contenía un módulo al 88 %. «El paquete
  llega al 90 %» y «cada módulo llega al 90 %» son contratos distintos, y sólo el
  segundo encuentra el hueco.
- **La instrumentación de subproceso no es un lujo: es lo que hace verdadera la
  medición.** Sin el hook `.pth`, el CLI que la suite lanza por subproceso mide
  65,86 % en vez de 94 %. No instrumentar produce un número que parece un
  incumplimiento y es ceguera del instrumento.
- **La cobertura es un techo, no una puerta.** Subir un módulo del 88 al 99 % no
  demuestra que el adaptador funcione contra Anthropic: demuestra que rechaza
  bien lo que no debería aceptar.

### Lo que sigue sin probarse

Este tramo **no** prueba que Anthropic ni OpenAI respondan: requiere credenciales
que este entorno no tiene, y el registro de conformidad de H9 lo declara como
hueco abierto. Lo que sí queda probado es la mitad local del contrato.

- Evidencia: `evidence/sddk-wi93-verify-2026-10-02.md`.

## [0.16.18] (cont.) — WI-92: lo que WI-90 registró como deuda, medido: era falso

**Sin release propio, y es la decisión correcta**: el bloque entrega 1 `test` + 1
`docs`, y por la regla de este fichero (`refactor`/`test`/`docs`/`chore` no bumpean
SemVer) no había etiqueta que emitir. Forzar una por un `test` inflaría el
historial. Sus commits viajan igualmente dentro de **v0.16.18**, etiquetada por
WI-93. 2499 passed (2493 antes).

### Measured

- **La hipótesis que WI-90 dejó abierta era FALSA en los dos sitios.** No es un
  `fix`: es una **retractación**, y retractar es el resultado correcto cuando la
  medición dice que no hay nada que arreglar.

  - `runtime/agent.py` `AgentResult.from_fixture` **no** es un inverso de un
    `to_dict`. Su primera instrucción valida que el payload es un `dict`, las
    siguientes comprueban `outcome`, `result` y `evidence_ref`, y los errores son
    **tipados** (`ValidationError`, `OutcomeInvalidError`).
  - `governance/receipts.py` sí tiene un par asimétrico —el escritor
    `to_payload()` es público y el lector `_payload_to_receipt` es privado y
    escrito a mano— pero **las tres listas cuadran**: 11 campos del dataclass, 11
    claves emitidas, 11 leídas. Y el caller captura
    `(KeyError, ValueError, TypeError)` y hace `continue`, que es lo que promete
    el docstring.

### Added

- `tests/test_wi92_measured_claims.py` cierra el **riesgo latente** que sí
  quedaba: nada verificaba que esas tres listas siguieran siendo la misma. Con
  una clave de más el campo se pierde en silencio; con una de menos el lector
  lanza `KeyError`, el caller descarta la fila, y **el receipt que debería
  aplicarse no aplica sin dejar rastro**. El guard lee las tres listas del AST y
  exige que coincidan.
- Segundo guard: las citas `fichero.py:NNN` **del bloque vivo** de `CURRENT.md`
  tienen que resolver. Ese bloque es el puntero que lee primero la próxima
  sesión.

### Contradicciones

- **Las 3 citas rotas de la fuente de verdad no se corrigen, y esa es la
  decisión.** De 57 citas, 52 resuelven; las 3 rotas están en registros
  históricos que describen código ya refactorizado (`platform/storage.py` pasó
  de 1807 a 600 líneas en WI-65/68). Corregirlas habría sido **falsificar la
  historia**: afirmar que una auditoría de 2026-09-25 encontró problemas en
  líneas que no existían entonces. El guard cubre el bloque vivo y deja los
  anteriores como la foto que son.
- **El resolver estaba mal y el dato parecía una catástrofe.** La primera
  versión del script resolvió `run_repository.py` contra
  `src/skillgraph/run_repository.py` —el fichero está en `platform/`— y reportó
  19 referencias «sin fichero» en `STATE.yaml`. El resultado era alarmantemente
  malo por un resolver roto, no por los datos.
- **Un assert sobre una subcadena no comprueba una propiedad.** El primer guard
  de `from_fixture` pedía «`isinstance` aparece en el cuerpo» y la mutación M4 lo
  esquivó: hay **cuatro** comprobaciones `isinstance` en esa función, borrar una
  deja tres y la palabra sigue ahí. Reescrito sobre el AST para exigir que la
  **primera instrucción** valide el `dict`.

### Verificación

- **2499 passed** (2493 antes; +6).
- Mutaciones **6/6**. M6 no se aplicó en la primera pasada (el patrón omitía el
  rango `473-480`) y el autocontrol lo reportó como `MUTACION NO APLICO`, no
  como «no cazada». **Quinta vez en tres bloques que una medición necesita
  autocontrol.**
- Evidencia: `evidence/sddk-wi92-verify-2026-10-02.md`.

## [0.16.17] - 2026-10-02 — WI-91: el registro de conformidad H9 afirmaba cuatro cosas falsas

PATCH: `git log v0.16.16..HEAD` = 0 feat, 0 breaking, 2 fix, 2 docs, 1 chore. 2493 passed
(2479 antes).

### Fixed

- `fix(state)`: **`goal.h9_addendum_2026_09_25` decidía si el hito H9 del blueprint
  estaba cumplido, y cuatro de sus cinco afirmaciones sobre el código eran falsas.**
  Se escribió el 2026-09-25; el 2026-09-26, `v0.14.7` entregó los cuatro
  entregables que daba por incompletos (WI-12 a WI-17) y el registro no se
  revalidó. Nada lo comprobaba.

  | E | Afirmaba | Realidad medida |
  |---|---|---|
  | E1 | `PENDIENTE`; «no hay adapter HTTP/LLM/anthropic/openai» | `runtime/http_adapter.py:330` `HttpAgentAdapter` (Anthropic + OpenAI); CLI acepta `--adapter=http` (`run.py:265`) |
  | E2 | «Threat model (T3) NO ejecutado» | `docs/architecture/ADR-0015-threat-model-stride.md` + `tests/test_t3_threat_model_attestation.py` |
  | E3 | «grieta `workflow_runs ↔ runtime_events` abierta, 300-800 LoC» | `create_run_atomically` (`run_repository.py:641`) hace ambas escrituras en **una** transacción, viva vía `RunController.create_run` |
  | E4 | «No hay runbook formal (T6)» | `docs/observability-runbook.md` |
  | E5 | 16/16 UAT | **Cierto** — `PASS=16 FAIL=0 BLOCKED=0` |

  Los 23 tests que respaldan E1/E2/E3 estaban verdes todo el tiempo que el
  registro afirmaba lo contrario.

  Cada entregable lleva ahora `evidencia_paths` y el guard exige que **estado y
  evidencia sean verdad A LA VEZ, en las dos direcciones**: sin eso, un guard de
  una sola vía deja pasar justo la mitad de los fallos, que es la mitad que se
  cuela en un documento.

### Lo que NO se corrige

**H9 no se declara cerrada.** Los cinco entregables están entregados y verificados,
pero el criterio de salida exige «escenarios reales con trazabilidad, aislamiento y
recuperación», y eso sólo se demuestra ejecutando contra un proveedor real, que
necesita credenciales. Declararla cerrada sería **el mismo defecto en la dirección
contraria**: sustituir una afirmación falsa por otra que nadie ha medido. El hueco
queda escrito y un test lo vigila.

### Contradicciones

- **Reescribir un registro histórico no es corregirlo, es borrarlo.**
  `stewardship_backlog…Opcion A.implementacion` describe lo que el addendum
  afirmaba el 2026-09-25, y eso fue cierto. Se conserva y se marca
  `SUPERSEDIDO por WI-91`.
- **Un fallo en la función de restauración no es ruido: es el que puede medir
  mal.** La primera versión del script de mutaciones borraba su propio directorio
  de respaldo dentro de `restore()`; la segunda llamada no encontró con qué
  restaurar y la corrida terminó con `STATE.yaml` en el estado de la quinta
  mutación. **El control de baseline —«el guard debe estar verde antes de
  mutar»— lo detectó y se negó a medir.** Sin él, el script habría reportado
  6/6 sobre un árbol que ya no era el que se quería medir.
- `accion_requerida` decía «operador elige entre A/B/C/D». Medido: A y D cerradas
  desde 2026-09-25 y **B quedó inútil**, porque sus tres componentes duros
  (T1 adapter, T3 threat model, T6 observabilidad) se entregaron en `v0.14.7`.

### Verificación

- **2493 passed** (2479 antes; +14). `ruff check` y `ruff format --check` limpios.
- Mutaciones **6/6**, incluidas dos que borran el **código** (`http_adapter.py`,
  `docs/observability-runbook.md`) y no sólo el registro: el guard vigila la
  realidad, no una copia de sí mismo.
- Evidencia: `evidence/sddk-wi91-verify-2026-10-02.md`.

### Deuda tangencial registrada, no medida

Colisión de numeración de ADR: `ADR-0015` designa dos documentos distintos
(`external/blueprint-v1/adr/ADR-0015-vocabulario-de-estados-como-fuente-unica.md`
y `docs/architecture/ADR-0015-threat-model-stride.md`). Ya existía una colisión
previa en la serie del blueprint con `ADR-0013`. Renombrar exige actualizar ~8
referencias cruzadas; es una decisión del mantenedor, no del agente.

## [0.16.16] - 2026-10-02 — WI-90: `FileSignature` tiene round-trip y el lector deja de deserializar a mano

PATCH: `git log v0.16.15..HEAD` = 0 feat, 0 breaking, 1 fix, 1 docs, 1 chore. 2479 passed
(2463 antes).

### Fixed

- `fix(knowledge)` `e4fefb0`: **`FileSignature` tenía `to_dict()` pero no `from_dict()`.**
  El inverso estaba escrito a mano dentro de `list_file_signatures_for_source`
  (`knowledge/knowledge_controller.py:329-336`) con subíndices crudos: el inverso de un
  método público reimplementado a mano en uno de sus consumidores.

  Tres fallos, **medidos y no supuestos**:
  1. una clave de más en el payload → el campo **se pierde en silencio**, sin aviso;
  2. falta una clave → `KeyError` crudo;
  3. `procedencia` incompleta → `TypeError` crudo.

  Los tres explotan sin protección en los tres puntos que consumen el resultado
  (`governance/improvement.py:208, 268, 324`), que es otra capa y otro vocabulario de
  errores: el fallo cruzaba la frontera de bounded context como `ValueError`/`KeyError` de
  Python, no como `SkillGraphError`.

  `from_dict` en `SignatureProcedencia`, `SignatureVigencia` y `FileSignature`, con la
  validación concentrada en seis helpers (`_require_mapping`, `_require_keys`,
  `_require_str`, `_require_int`, `_require_bool`, `_require_optional_mapping`).
  `ParseError` (`sg_parse`) para la **forma** del payload; los valores fuera de política
  siguen lanzando el `ValidationError` que ya lanza `__post_init__`.

### Contradicciones

- **`SignatureVigencia.from_dict` no comprueba `state` contra `EXTRACTION_STATES`, a
  propósito.** Esa validación ya vive en `__post_init__` de la clase. Duplicarla aquí
  crearía un segundo sitio desincronizable — exactamente el defecto que cerró WI-87 con
  ADR-0015, donde un conjunto de vocabulario duplicado a mano hacía que añadir un estado
  produjera runs duplicados en silencio.
- **La medición de la decisión (a) de WI-87 era correcta pero estaba incompleta.** Decía
  que la función no estaba muerta ni era un punto ciego de uso, y era cierto: 4
  consumidores reales. Lo que no se midió fue **dónde** estaba su complejidad. De las 58
  líneas con cc 10, ocho eran el deserializador duplicado. Ese bloque desaparece y el resto
  queda por debajo del umbral. **No se refactorizó la función entera**: la medición no lo
  respaldaba.
- **La tercera medición del bloque que daba bien sin medir nada.** El script de
  mutaciones contaba M3 como «no cazada» sin haber modificado nada: el `replace` no
  aplicaba porque el texto no coincidía con el formato que deja `ruff format`. Se añadió
  **autocontrol de aplicación** al script — si un `replace` no cambia el fichero, se
  reporta `MUTACION NO APLICO`, no «no cazada». Una mutación que no se aplica no es una
  mutación sobrevivida: es una ausência de medición, y las dos se reportan igual si no se
  distingue el caso.

### Deuda tangencial registrada, no medida

`governance/receipts.py:473-480` y `runtime/agent.py:57-64` replican el mismo patrón de
inverso escrito a mano. **No se afirma que estén mal** y no se ha abierto frente sobre
ellos: son una hipótesis sin dato detrás.

### Verificación

- **2479 passed** (2463 antes; +16). `ruff check` y `ruff format --check` limpios.
- Mutaciones **5/5** cazadas tras corregir M3.
- Evidencia: `evidence/sddk-wi90-verify-2026-10-02.md`.

## [0.16.15] - 2026-10-02 — WI-89: la auditoría no escribe dentro del repositorio que audita

PATCH: `git log v0.16.14..HEAD` = 1 fix. 2463 passed (2451 antes).

> **Cabecera CORREGIDA en WI-95.** Decía `[Unreleased]` y era falso: este
> bloque se publicó como **v0.16.15** (`6819f99`). El cuerpo decía «Sin bump
> todavía», que era cierto al escribirlo y dejó de serlo al etiquetar. Medido:
> el CHANGELOG declaraba sin publicar tres bloques que ya habían salido, y
> `v0.16.14` y `v0.16.15` no tenían sección propia. Nada lo comprobaba —
> `tests/test_wi95_changelog_release_claims.py` ahora sí.

### Fixed

- `fix(audit)` `64a28a8`: **`audit_debt.py` escribía su informe dentro del repositorio
  que audita.** El destino era `AUDITS_DIR = pathlib.Path("audits")`, relativo al cwd, y
  los tests lo lanzaban como subproceso desde la raíz. Como `audits/` está **trackeado**
  (63 ficheros; sólo `*-audit-bundle.tar.gz` está en `.gitignore`) y el nombre lleva la
  fecha de ejecución, había dos modos de fallo:
  1. el código cambió desde la última generación → `M audits/architecture-debt-<hoy>.md`;
  2. no hay informe para hoy, primera corrida del día → `?? audits/…`, un fichero
     **nuevo sin trackear**. Este modo no requiere que cambie nada.

  `--src-root` y `--out-dir` parametrizan origen y destino; los defaults siguen siendo
  cwd-relativos, así que el comportamiento por defecto no se mueve. El
  `AUDITS_DIR.mkdir(exist_ok=True)` que estaba a nivel de módulo —y creaba un directorio
  al *importar* el script— pasa a estar en `main()`.

  `test_audit_debt_accuracy.py` no puede usar un sandbox completo: su `_measure` recorre
  `_PROJECT_ROOT/src` y compara la cc medida con las cifras citadas en el informe. Se
  mueve el destino, no el origen, y una red nueva lo verifica comparando el recuento de
  módulos del informe con el de `src/`.

### Contradicciones

- **La premisa del seguimiento registrado en WI-87 era condicional.** Decía, con md5
  como prueba, que «9 tests verdes cambian el fichero». Re-medido en un árbol limpio **no
  se reproduce**: el informe commiteado está al día y regenerarlo da bytes idénticos. Mi
  redacción presentó como incondicional algo que sólo ocurre cuando el informe está
  caducado. El defecto real era otro, y tenía un segundo modo que no se había medido.
- **La primera red no vigilaba nada.** Invocaba el auditor *con* `--out-dir` y comparaba
  `git status`; si alguien revierte los helpers, esa invocación no es la que se revirtió.
  Dos mutaciones lo demostraron: `--src-root` ignorado no se cazaba porque el test usaba
  un `cwd` cuyo `src/` de juguete coincidía con el default, y el helper revertido tampoco
  porque, con el informe al día, escribir dentro del repo no cambia nada. La red final
  ejecuta los `_run_audit()` **de verdad** de los dos ficheros de test y comprueba a dónde
  apuntan.
- **`ruff format audits/` reescribe recibos históricos.** Formatear el directorio
  reescribió bloques Python embebidos en `audits/release-v0.15.0-receipt.md` y
  `release-v0.16.0-receipt.md`. Son evidencia congelada de releases pasadas, así que se
  revirtieron. El alcance canónico es `ruff format src tests`.

### Verificación

- **2463 passed** (2451 antes; +12). `ruff check` y `ruff format --check` limpios.
- Mutaciones **5/5**: `--out-dir` ignorado, `mkdir` de vuelta al import, stdout distinto
  de la ruta escrita, `--src-root` ignorado, y el helper al camino viejo con el informe
  caducado (compuesta, porque el guard sólo dispara si se recrea la precondición).
- **El hook de pre-commit, que antes dejaba `M audits/architecture-debt-<hoy>.md`, deja
  ahora el árbol limpio.** Es la comprobación que importa: el defecto era visible en cada
  commit desde el propio hook.
- Evidencia: `evidence/sddk-wi89-verify-2026-10-02.md`.

## [0.16.14] - 2026-10-02 — WI-88: los errores de uso devuelven EXIT_USAGE y el 2 queda libre

PATCH: `git log v0.16.13..HEAD` = 1 fix. 2451 passed (2430 antes).

> **Cabecera CORREGIDA en WI-95.** Decía `[Unreleased]`, y su propio cuerpo
> decía ya «la release que lo contiene es `v0.16.14`»: el fichero se
> contradecía a sí mismo en dos líneas. Lo que sigue sustituye a «Sin bump
> todavía», que era una frase escrita antes de emitir el tag y que nunca se
> volvió a revisar.

### Fixed

- `fix(cli)` `1a0c38b`: **`argparse` abortaba los errores de uso con 2, y 2 ya
  significaba `EXIT_BAD_NAME`**. `runner.py:131` lo devuelve vivo, así que tres fallos
  sin relación —un nombre de proyecto inválido, un comando inexistente y un
  subcomando sin argumentos— devolvían el mismo número. Un script que comprobara
  `rc == 2` para detectar un nombre inválido recibía un falso positivo ante cualquier
  error de uso, y `EXIT_USAGE` (1), que el contrato declaraba, no se producía nunca.
  La taxonomía de errores era inservible para scripting.

  `parser.py` usa ahora `_UsageParser`, que sobrescribe `error()` para salir con
  `EXIT_USAGE`. No se envuelve `main` en un `except SystemExit` a propósito: no
  distinguiría el 2 de `argparse` del 2 de un handler, que es la ambigüedad que se
  quiere eliminar, y no se puede eliminar *después* del hecho.

  La tabla de exit codes se mueve a `cli/exit_codes.py`, un módulo hoja sin imports.
  `support.py` la reexporta con la forma `X as X`, que es la que ruff respeta como
  reexport intencional: sin ella, F401 borró ocho de los doce nombres — medido,
  `EXIT_DOMAIN` dejó de exportarse y `cli/commands/expansion.py` dejó de importar.

### Changed

- `style(lint)` `0a3fd1a`: `combine-as-imports = true`. Sin ella, ruff parte un bloque
  `X as X` en una sentencia por nombre, y la señal de «esto es un reexport
  intencional» desaparece entre doce líneas. Va en commit aparte porque toca tres
  módulos sin relación con WI-88.

### Contradicciones

- **La medición de la premisa (f) fue errónea y pasó inadvertida.** La primera
  ejecución dio exit 1 en los tres casos, lo que habría permitido cerrar (f) como
  «la premisa estaba caducada». Era falso: `shutil.which('sg')` devuelve `/usr/bin/sg`,
  la herramienta Unix de grupos, no la CLI de SkillGraph, cuyo console script es
  `skillgraph` (`pyproject.toml:39`). Los tres `1` medidos eran de otro programa, y sus
  mensajes de stderr lo decían (`sg: el grupo «no-existe-comando» no existe`).
- **Dos docstrings llamaban «dead code» a `EXIT_USAGE`.** No era código muerto: era
  **código secuestrado**. Un número que nunca se produce no se parece a código muerto,
  se parece a código inalcanzable, y la diferencia importa porque el primero es inocuo
  y el segundo esconde un defecto.
- **La consignación de WI-79 era correcta sobre la contradicción e incompleta sobre
  el diagnóstico.** Fijar el 2 a propósito era inocuo mientras 2 no significara nada
  para nadie; dejó de serlo cuando `EXIT_BAD_NAME` empezó a devolverlo. El propio test
  que consagra el comportamiento fue el que dejó pasar la colisión.
- **Ocho tests cambian de 2 a 1, a propósito.** Dos de ellos tenían el nombre diciendo
  una cosa y el cuerpo la otra: `test_wi41_cli_dispatch.py` se llamaba
  `test_comando_desconocido_devuelve_usage` y `test_wi57_dispatch_coverage.py`
  `..._is_argparse_usage`. Los dos nombres eran correctos y los dos cuerpos mentían. De
  los que se quedan, `test_cli_uat.py::test_main_returns_2_for_invalid_name` pasa a
  ser el guardián del 2, y `test_uat_audit.py` es otra herramienta con sus propios
  códigos, fuera de alcance.
- **La primera red afirmaba que `--version` lanzaba `SystemExit`.** Es
  `action="store_true"` (`parser.py:37-39`) y no aborta; lo atiende el runner. El test
  describía mal el programa.
- **Una mutación contaminó el staging.** La primera versión de M5 editaba
  `support.py` buscando un `return` que vive en `runner.py`; el `replace` no aplicó y
  el `# noqa` que dejó no se restauró, porque el script respaldaba dos ficheros y esa
  mutación tocaba un tercero. El commit se paró en el hook. `support.py` entró en el
  conjunto de respaldo.
- **Un recuento sobre una salida truncada es una suposición con formato de dato.** La
  primera lista de tests afectados decía «medidos uno a uno, no contados» y contaba 6;
  eran 10, porque el `grep` que los localizó estaba limitado a 20 resultados y se leyó
  como lista completa. Cuatro de los ocho reales están en un solo fichero.

### Verificación

- **2451 passed** (2430 antes; neto +21, desglose medido con un worktree en `d47b7af`:
  26 nuevos y 5 renombrados). `ruff check` y `ruff format --check` limpios.
- Mutaciones **5/5**: volver a `argparse.ArgumentParser`, salir con 2, tragarse el
  diagnóstico, no propagar la clase a los subparsers, y mover `EXIT_BAD_NAME` de número.
  M4 es la importante: una corrección aplicada sólo a la raíz deja los niveles internos
  devolviendo 2 sin que nada lo note.
- 18 tests nuevos. ADR-0016. Evidencia: `evidence/sddk-wi88-verify-2026-10-02.md`.

## [0.16.14] (cont.) — WI-87: el vocabulario de estados pasa a derivarse de su ADT

> **Cabecera CORREGIDA en WI-95.** Decía `[Unreleased]` y es la continuación
> de **v0.16.14**, que también contiene WI-88. El cuerpo de este bloque sigue
> diciendo «Sin bump», y es cierto: `refactor` + `docs` no mueven versión, y
> el PATCH de v0.16.14 lo dispara el `fix(cli)` de WI-88.

**Sin bump**: `refactor` + `docs`, que según la regla de este CHANGELOG no mueven
versión. No hay capacidad observable nueva: hoy el `CHECK` y la constante ya
coincidían. Lo que cambia es que ya **no pueden** dejar de coincidir.

### Fixed

- `refactor(core)` `d47b7af`: **el vocabulario de estados tenía dos fuentes de verdad y
  el test que lo cubría verificaba una copia de sí mismo**.

  `core/runtime_types.py:142` ya definía `TERMINAL_RUN_STATES` (con su helper
  `is_terminal_run_state`), y `platform/storage.py:123` reimplementaba **su
  complemento** a mano, sin relación verificada. Del mismo modo, el `CHECK` de
  `promotion_outbox` en `schema.py:262` y `PROMOTION_STATUSES` en `storage.py:117`
  eran dos listas escritas a mano sin ninguna ligadura.

  El único test que declaraba cubrir esa ligadura
  (`tests/test_h9_storage_promo_list.py:114-116`) comparaba el `frozenset` contra un
  literal repetido en el propio test, **sin leer `schema.py`**. Habría seguido en
  verde con el `CHECK` cambiado, que es justo lo que su nombre y su docstring
  declaran proteger.

  **Fallo concreto que esto habilitaba**: añadir un estado a `RunState` sin tocar
  `storage.py` lo hacía terminal, `find_active_run()` no lo encontraba, y el CLI
  creaba **un segundo run** para el mismo trabajo lógico — duplicación silenciosa, sin
  log, sin error y sin test rojo. UAT-06 (reanudar tras crash) era el que se
  incumplía.

  Es la misma clase que QW-E, donde la validación rechazaba `skill_pack` por
  divergencia, pero con consecuencia peor: allí se rechazaba un valor, aquí se
  duplica trabajo. El repositorio ya había resuelto este antipatrón dos veces
  (QW-D para `EVENT_KINDS`, QW-E para `SOURCE_KINDS`); aquí se les había escapado.

### Changed

- `NON_TERMINAL_RUN_STATES` se **deriva** por complemento de `TERMINAL_RUN_STATES`
  sobre `get_args(RunState)`: la partición es exacta por construcción.
- `PROMOTION_STATUSES` se **deriva** de la nueva Literal `PromotionStatus`, y
  `platform/schema.py` genera el `CHECK` de SQLite desde ese conjunto. Base de datos
  y validador de entrada no pueden divergir porque salen de la misma expresión.
- **Polaridad invertida**: se declara lo *terminal* y lo demás queda vivo. Un estado
  nuevo es reanudable salvo que se declare terminal; antes, olvidar el segundo
  fichero mataba el run. La dirección del fallo por omisión pasa de «perder trabajo»
  a «reanudar de más», y sólo en estados que nadie ha visto todavía.
- `promotion_repository` y `run_repository` toman las constantes de la hoja
  `core.runtime_types` en vez de la fachada `storage.py`.
- `SCHEMA_VERSION` sigue en **1**: el conjunto de valores aceptados no cambia, no hay
  migración.

### Contradicciones

- Una primera versión de la red de tests, y el docstring de un helper que añadí,
  afirmaban que «un estado desconocido cuenta como no terminal». Es **falso**:
  `RunState` es una ADT cerrada, y un valor que no está en el Literal no pertenece al
  vocabulario en ninguno de los dos sentidos. Se corrigió la afirmación, no el
  criterio. El intento de probarlo con `PAUSED` fue lo que lo reveló.
- `is_non_terminal_run_state()` se añadió y se retiró en el mismo bloque: cero
  consumidores. WI-81 borró alias muertos y WI-86 la capa de re-export muerta;
  introducir un tercero contradice las dos.
- `tests/test_wi82_evidence_write_idempotence.py:179` limita su `git status --porcelain`
  a `-- tests/uat-evidence/`, así que no puede ver que **`audits/architecture-debt-*.md`
  sigue ensuciando el árbol** en cada corrida: `test_audit_debt_smoke.py:25` y
  `test_audit_debt_accuracy.py:43` lanzan `audit_debt.py` desde la raíz del repo. Es
  una instancia distinta de la clase que corrigió WI-82, no un descuido de aquel
  arreglo. Registrado como seguimiento, no corregido aquí por ser de otra superficie.
  El informe regenerado se incluye en este bloque porque es una medición real del
  árbol (20779 → 20829 LoC).

### Verificación

- **2430 passed** (2416 antes; +14 = los tests nuevos). `ruff check` y
  `ruff format --check` limpios.
- Mutaciones: **4 cazadas**, **2 imposibles por construcción**, 0 sin cazar. Las dos
  imposibles (reescribir `NON_TERMINAL_RUN_STATES` a mano con el mismo valor; romper
  la disyunción) son la demostración de que la derivación hace el fallo imposible, y
  una mutación acompañante prueba que la red de seguridad detecta el olvido en cuanto
  `RunState` cambia.
- ADR-0015. Evidencia: `evidence/sddk-wi87-verify-2026-10-02.md`.

## [0.16.13] - 2026-10-02 — WI-86 y WI-80: la capa de re-export y el rechazo ilegible
**Resumen**: 2 commits de trabajo desde `v0.16.12` (`cf6539b`, `eb19942`). SemVer derivado del
historial: **0 `feat`, 1 `fix`, 1 `refactor`, 1 `docs`, 1 `chore`** → **PATCH**. Sin capacidad
observable nueva ni cambio de API pública. **2416 passed** (2394 en `v0.16.12`), ruff y format
limpios, CI canónica `Pipeline finished with SUCCESS`.

### Fixed

- `fix(cli)` `eb19942`: **`expansion list` afirmaba `stage=PROPOSED`, con
  exit 0 y sin aviso, para una propuesta que SÍ había sido rechazada**.
  `_collect_rejection_ids` se saltaba con `continue` un
  `expansion_rejections/*.json` ilegible; el `proposal_id` se perdía y
  `_infer_proposal_stage` caía a `PROPOSED`. Consecuencia medida:
  `--stage REJECTED` hacía desaparecer la propuesta. No era un falso éxito
  de escritura —`apply` es idempotente por re-validación—; el alcance era
  de visualización. **El fix no adivina**: `record_rejection` escribe
  siempre `<proposal_id>.json`, luego el stem *es* el `proposal_id` por
  construcción. Además avisa en stderr, porque sin el aviso la corrección
  habría sustituido una mentira silenciosa por otra más pequeña. Listing
  sigue con exit 0 y el fichero corrupto **no se borra**.

### Contradicciones

- El bloque anterior decidió **no** corregirlo, con el criterio de que
  cambiar la salida de `expansion list` es contrato externo (AGENTS §6.4).
  El criterio era correcto en general y **estaba mal aplicado aquí**:
  confundía **cambiar un contrato** con **corregir una afirmación falsa**.
  El contrato de `--stage REJECTED` nunca fue «oculta las rechazadas cuyo
  fichero está roto», y ningún consumidor razonable depende de que se
  imprima `stage=PROPOSED` para algo que sí fue rechazado.

## [0.16.13] (cont.) — WI-86: los mappers se importan de la hoja, no a través del facade

> Esta sección se rotuló `Unreleased` por error: el trabajo de WI-86 salió en
> `v0.16.13` (`cf6539b`). No es un release pendiente.

**Sin bump**: `refactor` + `test`, que según la regla de este CHANGELOG
no mueven versión. 2414 passed (2394 en `v0.16.12`).

### Refactor

- `refactor(platform)` `cf6539b`: **los 5 consumidores de mappers dejan de
  pasar por `platform.storage`**. Cierra el punto (a) de
  `STATE.yaml.next_workitem`, que llevaba dos bloques abierto con «requiere
  ADR NUEVO». Resuelto por medición: los 7 símbolos que `storage.py`
  importaba y reexportaba aparecían **exactamente dos veces** cada uno —el
  `import` y `__all__`— y **cero** en código dentro del fichero, así que la
  capa entera existía para servir a hermanos. Y eran **cinco** hermanos, no
  los dos que nombraba el comentario del propio bloque. `row_mappers` es una
  hoja, de modo que el rodeo no evitaba ningún ciclo. Los 5 importan ahora de
  la hoja; `storage` retira el bloque y las 7 entradas de `__all__`. Cero
  cambios de comportamiento — la red comprueba **identidad**, no el nombre
  del símbolo. `PROMOTION_STATUSES` y `NON_TERMINAL_RUN_STATES` **no** se
  tocan: están *definidos* en `storage.py`, no son re-exports, y su
  propiedad de dominio sí merece ADR.

### Fixed

- **Registro falso corregido.** El bloque anterior anotó `WI-65-fase-1` como
  siguiente trabajo sin verificar su premisa. Medido contra el árbol:
  `platform/storage.py` son **613 LoC con 15 métodos** (no 1807/80) y los 5
  mixins existen y son live con 31/19/7/4/4 = 65 métodos. **WI-65 ya lo
  entregó ADR-0022** y WI-68 lo remató: el informe de exploración se
  commiteó 81 minutos **antes** de la release que lo implementó. El ciclo
  `wi65-storage-facade-decomposition` se cerró con `goal-replaced` — su
  objetivo fue entregado, por otro bloque. **27 ciclos CLOSED, 0 abiertos.**

### Conocimiento negativo

- Un informe de exploración puede ser **excelente y aun así estar vencido**.
  Este acertaba en cada predicción (5 mixins, 31/19/7/4/4, cero ediciones
  en callers) y aun así describía un árbol que ya no existía. La calidad
  del análisis no dice nada sobre si su premisa sigue en pie.
- **Para objetos función, `==` e `is` son la misma operación.** El script de
  mutaciones llevaba una comprobación que relajaba `is` a `==` esperando
  demostrar que el `is` era «load-bearing». Falla. El `is` sigue siendo lo
  correcto de escribir, pero no protege nada que `==` no protegiera. Se
  retiró en vez de dejar una comprobación que afirmara algo falso.
- Un test cuyo objeto desaparece **no se adapta, se borra**; pero un test
  cuyo *contrato* cambia deliberadamente **se actualiza**. Los 4 tests de
  WI-65/WI-81 que afirmaban que los mappers se reexportaban estaban bien
  sobre el contrato viejo: se actualizaron a fijar el nuevo, más fuerte.

## [0.16.12] - 2026-10-02 — WI-82..WI-84: el árbol de git deja de ensuciarse y el estado SDDK deja de mentir

**Resumen**: publica el bloque de 2 commits desde `6edd27f` (WI-82 y WI-83/84).
SemVer derivado del historial: **0 `feat`, 2 `fix`** → **PATCH**. No hay
capacidad observable nueva ni cambio de API pública. **2388 passed** (2376
antes del bloque), ruff y format limpios.

El bloque tiene dos mitades. Una es un defecto real de higiene: la suite
reescribía dos ficheros versionados en cada corrida. La otra es el estado
operativo, que, resultado de medirlo, no era el que el propio repositorio
decía.

### Fixed

- `fix(test)` `6db1000`: **la suite ensuciaba `git status` en cada ejecución**.
  `tests/test_h4_expansion_cli.py` emite `tests/uat-evidence/UAT-08.json` y
  `UAT-09.json`, ambos versionados. El único campo que cambiaba entre
  corridas era `revision` (`git rev-parse HEAD`) sobre un payload por lo
  demás determinista, y `save_with_lock` escribía incondicionalmente.
  Cada commit arrastraba dos ficheros de ruido que había que revisar a mano.
  Y el desfase **no puede converger por construcción**: un fichero versionado
  nunca puede contener el SHA del commit que lo versiona.
  `revision` resultó ser un sello informativo, no un contrato: **ningún
  test comprueba `revision == HEAD`**, y `tests/test_uat_audit.py:143` afirma
  exactamente lo contrario de lo que hacía el producto
  (`assert survived["revision"] == "must-survive"` — la evidencia persistida
  debe sobrevivir a una re-emisión sin cambio semántico).
  `save_with_lock` acepta ahora `volatile_keys`: si el fichero existe y
  coincide con el payload en todas las demás claves, no se reescribe. La
  comparación es sobre el JSON parseado (el orden de un dict no es
  información; el de una lista sí) y es *fail-open* explícito si el fichero
  previo no se puede leer — tragarse evidencia por una lectura fallida sería
  peor que el ruido que evita. `history_keep=True` queda intacto, porque ahí
  el registro de cada corrida **es** el propósito.
  Red: `tests/test_wi82_evidence_write_idempotence.py`, 12 tests, incluidas
  las dos contrapartes que hacen el contrato honesto: si el contenido cambia
  de verdad se escribe, y si no cambia ni la mtime se toca. 3/3 mutaciones
  cazadas.
- `fix(scripts)` `2bd64da`: **`scripts/audit_bundle.sh` podía emitir un
  bundle con un informe UAT fallido y salir con éxito**. Dos fallos
  encadenados. (1) Ejecutaba el audit como
  `uv run python tests/uat_audit.py`, forma en la que `sys.path[0]` es
  `tests/` y el `from tests._evidence_lock import …` de nivel de módulo
  falla con `ModuleNotFoundError` (exit 1); la forma correcta es
  `python -m tests.uat_audit` (exit 0, `PASS=16 FAIL=0 BLOCKED=0`). (2) El
  comando estaba en un pipe a `tee`, que se come el exit code: el script
  seguía, empaquetaba y salía con 0 con un `uat-audit-cleanroom.txt` que
  contenía un traceback. La herramienta cuya razón de ser es producir
  evidencia reproducible para una auditoría externa podía producir un
  bundle no certificable con apariencia de certificado. Se captura
  `PIPESTATUS[0]` y se aborta con el código real.
- `fix(state)` **WI-85**: **`STATE.yaml` descartaba 7 claves YAML en
  silencio.** `yaml.safe_load` no avisa: por especificación, una clave
  repetida se descarta y queda la última. El daño no era académico —
  `tests.total` **parseaba como `85%`**, el porcentaje de cobertura de un
  snapshot que había quedado anidado por error dentro de `tests:`, en vez
  del número de tests. Un humano leyendo el fichero veía `1431`;
  cualquier cosa que lo parseara veía `85%`. Es el modo de fallo que este
  proyecto rechaza en el código, apareciéndole en su propio registro de
  estado. Las 7: `delta_wi12` ×2, `total` ×3, `refactor_v070_summary` ×2 y
  `nota` ×3 (una por release en la lista). Arreglo por **renombrado**, no
  por reestructuración: en cada par se renombra la entrada que quedaba
  tapada, de modo que el nombre canónico lo conserva la que el parser ya
  leía y **no se pierde ni un dato**. `tests.total` vuelve a ser un
  entero. No se reestructuran los ~130 LoC de snapshots de cobertura
  mal anidados: eso es cirugía sobre el único registro durable del
  proyecto y no corresponde a este bloque. Red:
  `tests/test_wi85_state_yaml_integrity.py`, 6 tests, **6/6 en rojo contra
  el estado previo y 6/6 en verde después**.

### Conocimiento negativo

- **`sddk release plan` no aplica a este proyecto.** Falla con
  `VERSION LOCKSTEP ERROR: could not read …/Cargo.toml`: el plano de release
  de SDDK deriva la versión de un `Cargo.toml`. SkillGraph es un paquete
  Python con `[tool.hatch.version] path`. Por tanto **`release.complete` es
  estructuralmente inalcanzable** para cualquier ciclo: exige
  `release-receipt`, y el receipt solo lo emite `sddk release apply`, que a
  su vez exige ese `Cargo.toml`. No es un gate pendiente de aprobación.
- **`sddk release apply --route local` hace push** de trunk y tag. Queda
  fuera de lo pre-aprobado por la consigna del operador.
- **Los gates del plano de release sí se pueden pasar** y se pasaron
  (`release-uat-approved` y `no-pending-effects` con evidencia real: exigen
  `argv`, `exit_code` y `output_digest`, no un sello en blanco). Los dos
  requisitos que faltan no son gates: los emite el paso de release.
- **`sddk cycle supersede` necesita tres pasos que el `--help` no
  documenta**: el intento que falla por falta de aprobación *registra* la
  petición (es el paso 1, no un rodeo), luego `approval grant`, y luego
  `cycle lock acquire` explícito para conocer el `fencing_token` real —sin
  él responde `lease conflict` aunque no haya fila en `cycle_leases`.
- `sddk cycle supersede --help` documenta mal el enum: el texto dice
  `scope_invalid | goal_replaced | external_obsolete` (guiones bajos) y los
  valores reales llevan **guiones**.

### Estado operativo (WI-83/WI-84)

- **El recuento de ciclos en `STATE.yaml` estaba caducado.** Decía «6 ciclos
  en `RELEASE_PENDING`»; el ledger tiene **10** (`wi-72`..`wi-81`). El texto
  quedó desfasado por dos razones a la vez: `wi-81` se creó después de
  escribirlo, y `wi-72/73/74` nunca se contaron.
- **Los 10 se cerraron** por `cycle supersede --reason external-obsolete`
  con `evidence/sddk-wi84-sddk-state-resolution-2026-10-02.md` como
  referencia. El enum ofrece tres razones y **ninguna describe el caso
  real** («trabajo terminado y publicado, pero el terminal del framework no
  aplica a un proyecto Python»); se eligió la más cercana y la evidencia
  deja constancia de que la clasificación es aproximada. La razón es una
  etiqueta; el fichero es el registro.
- **`wi-65-subprocess-coverage-file` cerrado** (`goal-replaced`): una
  cáscara de 1 evento y 0 artefactos. El cierre se apoya en el nombre del
  ciclo y en que WI-75 (`b3b2ef7`) produjo `scripts/coverage.sh`, que es
  literalmente ese asunto. **La premisa es una inferencia, no un hecho del
  ledger**, y así queda anotada.
- **`wi65-storage-facade-decomposition` NO se cierra, a propósito.** Contiene
  un informe de exploración real, medido y no ejecutado: 759 de 1807 LoC de
  `storage.py` son delegación pura, agrupables en 5 mixins disyuntos con
  cero ediciones en callers. Cerrarlo sería tirar trabajo válido para dejar
  el tablero limpio. Pasa a ser el siguiente bloque.

### Contradicciones

- El diagnóstico anterior de este punto era «evidencia UAT autorreferencial:
  `revision` no puede converger». Es cierto y **no era el defecto**: es una
  propiedad del dato. El defecto era la escritura incondicional. Se corrigió
  el segundo; el primero era irresoluble y no había que tocarlo.

## [0.16.11] - 2026-10-02 — WI-72..WI-81: investigación retrospectiva, falsos éxitos y alias muertos

**Resumen**: publica el bloque de 9 commits acumulado desde `2ee6d77` (WI-72
a WI-81): una investigación retrospectiva del ciclo de desarrollo anterior,
con la consigna de buscar **falsos éxitos** —operaciones que devuelven OK
sin cumplir su objetivo—. El número sale de la regla del propio CHANGELOG
aplicada al historial: **0 `feat`, 1 `fix`, 1 `refactor`, 6 `test`, 1
`docs`** → **PATCH**. No hay capacidad observable nueva ni cambio de API
pública. **2376 passed** (2368 antes del bloque), ruff y format limpios, CI
canónica con `Pipeline finished with SUCCESS` (run `6d5e68a5`).

La mayor parte del bloque son redes de contrato, no cambios de
comportamiento: el código ya cumplía lo que se ahora verifica. Cuatro
falsos éxitos confirmados y uno refutado con instrumentación.

### Fixed

- `fix(coverage)` `b3b2ef7`: **`pytest --cov` era ciego al CLI entero**.
  Mide solo el proceso principal, y la suite ejercita la frontera CLI por
  subproceso. El CLI marcaba **65,86 %** contra el contrato de AGENTS §6.3
  (≥70 %) — un incumplimiento aparente que era **ceguera del
  instrumento, no deuda de tests**. `scripts/coverage.sh` arregla las tres
  piezas (hook `.pth` que llama a `coverage.process_startup()`,
  `parallel = true` y `data_file` absoluto) y el mismo código mide **94 %**;
  `cmd_expansion_apply` pasa de 0 % a cobertura real. Sin tocar `.pipeline.kts`
  porque la instrumentación duplica el tiempo de suite.
- `test(platform)` `073d52d` + `refactor(platform)` `90d2e46`: **siete alias
  de WI-56 (corte 3) en `row_mappers.py` sin callers**, que `MAPPER_NAMES` y
  `storage.__all__` seguían contando como mappers. Sus docstrings decían
  «el corte 5 reubicará los callers»; el corte 5 ocurrió (ADR-0020) y los
  alias se quedaron. Inercia medida **en runtime**: los símbolos que usa
  `knowledge_repository` son aliases *locales* suyos
  (`knowledge_repository.py:696-702`) que apuntan a `knowledge_mappers`, no
  a estos — un barrido textual habría dado un falso positivo. `MAPPER_NAMES`
  pasa de 12 a 5; segunda tanda de ADR-0014, cuyo addendum queda en disco
  porque `external/` está en `.gitignore`.
- `test(runtime)` `2a1a737`: el guard de `_fail_node_with` leía que la última
  línea fuese `return False` con `getsource`, con lo que un `return None`
  temprano pasaba. Ahora invoca la función.

### Regresiones evitadas por la red (contexto)

- `test(cli)` `d69879f`: la rama `except FileNotFoundError` de `main`
  (`runner.py:250-254`) **no la ejercitaba nadie**. Con su
  `return EXIT_PROJECT_NOT_FOUND` cambiado por `return EXIT_OK`, los 2260
  tests de la suite se quedaban verdes. El oráculo conductual no la
  alcanzaba porque `runs budget` resuelve el proyecto antes. La cobertura
  de líneas no lo habría dicho: la línea se ejecuta, lo que faltaba era la
  **aserción** sobre su valor.
- `test(cli)` `2b68bfd`: un `expansion_rejections/*.json` ilegible degrada a
  `stage=PROPOSED` con exit 0 y sin aviso, y desaparece del filtro
  `--stage REJECTED`. **No** es un falso éxito de escritura —`apply` es
  idempotente por re-validación— sino de visualización. Fijado con test; la
  corrección es decisión de producto porque cambia la salida de un comando
  publicado.
- `test(runtime)` `3ce7b2e`: el límite `max_events` del Run, un control de
  gobernanza cuyo evento `BudgetExceeded(kind="events")` es lo que el
  operador lee para saber **por qué** se abortó un run, no tenía un solo
  test. `run_budget_delegations.py` de 83 % a 100 %.
- `test(platform)` `40d78ae`: la serialización legacy de 4 de 9 DTO
  (`StoredClaim`, `StoredEvidence`, `StoredPromotion`, `StoredBudget`) sin
  test. `dto.py` de 89 % a 97 %.

### Conocimiento negativo (lo que se buscó y NO se encontró)

Registrado porque absence de evidencia no es evidencia de ausencia, y
porque confirmar que algo está bien es un resultado:

- **No hay handler de excepción vacío ni `pass`** en `src/`: de 66
  handlers, 59 tienen cuerpo efectivo y 7 son `continue` de tolerancia a
  dato corrupto, todos documentados. Los 4 `except Exception` anchos están
  justificados en el código y los 3 `except BaseException` relanzan con
  `raise`.
- **Ningún handler de `_DISPATCH` (31) puede devolver `None`**, o sea que
  `sys.exit(main())` no puede dar exit 0 por silencio. Hipótesis refutada
  con un escáner validado por mutación en ambas direcciones.
- **La pérdida de la causa de una promoción FAILED** (`promotion.py:116`)
  es deuda declarada en el propio código y fijada por test, no un hallazgo.
- **`_load_registry` con registro incompleto es fail-closed**: el registry
  es un allowlist de existencia (I3/I4), no un detector de colisiones.
- **El patrón `getsource`/AST con `assert` no es sistémico**: de 40 tests
  que lo combinan, ~37 son contratos estructurales legítimos.
- **No hay deuda registrada para este proyecto**: `sddk debt incs`
  devuelve 50 INCs que pertenecen a `sddk-framework/` y a otro proyecto
  (`p-733fb505b5a6bd2d`); el vault de `p-b7740b96d79ec013` tiene 0 entradas.
- **`sddk lint` falla con 4 errores que son opt-ins no adoptados**
  (`schemas/`, `docs/generated/`, `manifest.toml` nunca existieron en el
  historial de git), no contratos violados ni drift.

### Contradicciones reportadas, no corregidas

Decisiones de producto, con el comportamiento real fijado por test para
que no se resuelvan en silencio:

- `StoredBudget.to_dict` promete en su docstring "preservando todas las
  columnas" y devuelve 3 de 6: omite `tenant_id`, `project_id`, `run_id`.
  Ningún consumidor determina cuál de las dos cosas es correcta.
- `argparse` sale con código **2** mientras el `EXIT_USAGE` canónico es
  **1** (`support.py:47`): un operador que clasifique por `EXIT_USAGE` no ve
  los errores de invocación.
- Un rechazo ilegible se presenta como `PROPOSED` (§ Regresiones).

## [0.16.10] - 2026-10-02 — WI-65..WI-71: cierre de H-01 y god modules 3 → 0

**Resumen**: publica el bloque de 57 commits acumulado desde `e680b72`. El
número sale de la regla del propio CHANGELOG aplicada al historial: **0
`feat`, 6 `fix`, 13 `refactor`, 3 `test`, 23 `docs`, 12 `chore`** → **PATCH**.
Se propuso un MINOR y se descartó: el bloque no añade ninguna capacidad
observable y la API pública se conserva idéntica. Contiene tres defectos
reales de gobernanza de CI, el cierre de la god class `Storage` (H-01), tres
cortes estranguladores que llevan god modules 3 → 0, y siete redes de
contrato nuevas. **2181 passed** (2154 antes del bloque), ruff y format
limpios, CI canónica con `Pipeline finished with SUCCESS`.

### Fixed

- `fix(ci)` `3665262`: **SUCCESS cacheado**. El comando canónico sin
  `--rerun` reutilizaba el veredicto por `cacheKey` de compilación del
  script: 72 ms, cinco stages "success", cero `StepStarted`. Un run que no
  ejecutaba nada se declaraba verde. `--rerun` pasa a ser obligatorio y
  AGENTS.md gana un criterio nuevo (el journal debe contener `StepStarted`
  y un `EchoOutputCaptured` con la línea de resumen de pytest). El criterio
  de "cero `StepFailed`" pasa a filtrar por `occurred_at` porque el
  `run_id` se reutiliza entre replays.
- `fix(ci)` `1bb545d` + `9dff66c`: la causa del "bake-off" entre versiones
  de `pipelinek` era la **ambigüedad de PATH entre asdf y mise**, no una
  versión defectuosa. Tres runs controlados (0.39.0 mise / 0.43.0 asdf /
  0.46.0 asdf) dieron los tres `1880 passed` + SUCCESS. Se fija 0.39.0 en
  `mise.toml` y se corrige la evidencia durable.
- `fix(ci)` `2cbc6c9`: el hook pre-commit decidía sobre el exit de `tail`, no
  el de `pytest`, y enmascaraba cualquier fallo de la suite (misma clase de
  trampa que `PIPESTATUS`).
- `fix(cli)` `c3444a7`: se restaura `@contextmanager` en
  `support._open_project_storage`.
- `fix(tests)` `ff5d246`, `229c542`: repara imports de símbolos movidos por
  los cortes estranguladores y actualiza cuatro contratos a la realidad
  post-estrangulamiento.

### Changed (sin cambio de comportamiento observable)

- `refactor(platform)` `9c104ac`, `2f5f7e4`, `405f49e` — **ADR-0022, cierra
  H-01**: la god class `Storage` (1807 LoC, 80 métodos) deja de figurar como
  god module. `storage.py` queda en **623 LoC**: 65 métodos de delegación a
  cinco mixin por componente, 12 mappers fila→DTO y el DDL a `row_mappers.py`
  y `schema.py`. Los atómicos H9/H10 (`_tx`, `_atomic`, `_migrate`) **no se
  mueven**: ADR-0016 exige que compartan `self._conn` sin duplicarlo.
- `refactor(runtime)` `e07413b` — **ADR-0023**: `_execute_one` 143 → 74 LoC
  en cuatro fases nombradas (`_node_guard`, `_compile_node_handoff`,
  `_invoke_node_adapter`, `_settle_node_outcome`).
- `refactor(runtime)` `57121ed` — **ADR-0024**, completa ADR-0019 fase 2:
  `RunController` 1421 → 665 LoC en tres mixin de dominio, en **módulos
  separados** (uno único habría salido en 845 LoC: reubicar el problema).
- `refactor(platform)` `c29a848`: `ports/__init__.py` 927 → `dto.py` (448) +
  `repositories.py` (442) + índice de 55. **God modules 3 → 0.**
- `refactor(knowledge)` `a16cd10` y `b6741bf`: `extract_file_signatures` 116
  → 55 LoC y `analyze_skill` 101 → 30 LoC (cc 11 → 1). Ambas candidatas
  elegidas por **medición AST, no por tamaño**: son las de mayor cc real
  entre las que quedaban; las lineales (`compile_handoff` cc 3,
  `compile_handoff_from_scopes` cc 1) se dejan intactas a proposito.

### Regresiones evitadas por la red (contexto)

Cuatro apariciones del mismo bug: `ruff --fix` borra por F401 los DTO
re-exportados en cuanto el facade deja de referenciarlos (61, 133 y 1 test
caídos en WI-65, WI-66 y WI-67). Guardas permanentes añadidas: lista
explícita de re-exports consumidos desde fuera y superficie pública
afirmada con `inspect.getmembers` (un `vars(cls)` no ve la herencia).
`ClassDef.lineno` no apunta al decorador, así que un corte de dataclasses
puede dejar los `@dataclass` atrás (41 tests, dos veces).

### Contexto

- Dos rarezas preexistentes de la importación de skills quedan **fijadas con
  test, no corregidas**: importar un fichero suelto lo nombra `"."` (porque
  `Path(f).relative_to(f)` es `"."`) y el mensaje de ruta inexistente usa la
  raíz ya resuelta. La primera cambia el payload que consumen UAT e informe:
  es decisión de producto.
- Nudo estructural del release governance: el admission gate exige que
  `__version__` puro coincida con una etiqueta en HEAD, así que el commit de
  release no puede pasar el gate antes de que exista la etiqueta. Se
  commitea con `HOOK_SKIP_TESTS=1` (ruff sigue corriendo) y la suite
  completa se ejecuta **después** de crear el tag, que es la condición en la
  que el gate debe pasar de verdad.

## [0.16.9] - 2026-10-01 — WI-49: rechazo de bool en enteros declarados

**Resumen**: ciclo SDDK `wi-49-bool-int-declared-coercions` (identidad `p-b7740b96d79ec013`). Cierra la clase de defecto que wi-46 dejó abierta (`isinstance(True, int)` es `True`, así que `int(True)` = 1 y un booleano declarado donde se espera un entero pasaba en silencio): tres superficies más donde la coerción ciega aceptaba `bool` — **plan** (`resourceRevision: true` → revisión 1 que nadie declaró), **backups** (manifest con `size_bytes: true` → tamaño 1 en restore) y **receipts** (`tests_run=True`/`tests_passed=True` aceptados por la dataclass pese al docstring que los "preservaba"; solo el cross-check `tests_passed > tests_run` mordía en una dirección, y el lector defensivo `_payload_to_receipt` coercaba antes de validar). 3 `fix`, 0 `feat`, 0 breaking → **PATCH**.

### Fixed

- `fix(plan)` `8ba12f3`: `_resource_revision` rechaza `bool` con `ParseError` que nombra el `source`; se preservan las coercions fijadas por test (`int('3')` acepta, `int(2.9)` trunca, ausencia → 0). Mismo patrón que `recipe._coerce_int`.
- `fix(backups)` `e95c5e9`: `BackupManifest.from_dict` usa `_declared_int` (rechazo explícito de `bool` con mensaje que nombra el campo) para `size_bytes`, `tenant_count` y `project_count`; elimina tres `# type: ignore[arg-type]`.
- `fix(receipts)` `6160ed5`: `ValidationReceipt._validate_counters` rechaza `bool` en `tests_run`/`tests_passed` (revierte la decisión de "preservar" la coerción, que el cross-check no cubría) y `_payload_to_receipt` valida antes de coercer, cumpliendo su propio contrato defensivo (fila corrupta → excepción → fila omitida).

### Contexto

- La sesión abrió con recuperación de contexto SDDK tras cambio de identidad (`p-74299cf88f51dab9` → `p-b7740b96d79ec013`, remote normalizado); detalle y cierre documental de los ciclos archivados en `evidence/sddk-context-recovery-2026-10-01.md`.
- Deuda registrada como P2 en el ledger anterior (`cmd_promotion_reconcile` cc=14, `_make_schema_validator` cc=13/anidamiento 5) verificada **caducada**: miden cc=7/1 y cc=3/2 tras los refactors posteriores.
- push pendiente de aprobación del operador.

## [0.16.8] - 2026-09-28 — WI-56: descomposición de Storage en repositorios reales (ADR-0016)

**Resumen**: ciclo SDDK `wi-56-storage-decomposition` (path A-lite). Patrón strangler en 5 cortes sobre el god-module `platform/storage.py` (2837 → 1807 LoC, −36%): cada cluster de SQL sale a un componente real con conexión compartida y su red de contrato escrita ANTES (RED honesto: solo fallaba la identidad del facade). **Cero ediciones en callers** (REQ-WI56-1/I1): los delegados del facade conservan firma explícita y forwarding idéntico (guard WI-45). Solo forma: 0 `feat`, 0 `fix`, 0 breaking → **PATCH**. Total: **1754/1754 tests no-UAT PASS**, ruff limpio.

### Changed

- **`SqliteRunRepository`** (`platform/run_repository.py`, corte 1 `ce0f291`): runs, node_executions y `list_events_for_run`. Net: `test_wi56_run_repository_contracts.py`.
- **`SqlitePolicyStore`** (`platform/policy_store.py`, corte 2 `7001479`): tenant_policies y run_budgets. Net: `test_wi56_policy_store_contracts.py`.
- **`SqliteKnowledgeRepository`** (`platform/knowledge_repository.py`, corte 3 `c125715`): 31 métodos del cluster knowledge (resources/relations, sources, entities, claims, evidences, findings, traces). Net: `test_wi56_knowledge_repository_contracts.py` (36 tests).
- **`SqliteEventStore`** (`platform/event_store.py`, corte 4 `6895725`): record/list/fetch/ensure_schema. `list_events_for_run` se puentea desde run_repository (ya migrado en corte 1) para satisfacer el Protocol completo. Net: `test_wi56_event_store_contracts.py` (15 tests).
- **`SqlitePromotionRepository`** (`platform/promotion_repository.py`, corte 5 `f439c74`): outbox H7 (register/get/list + 3 transiciones). Net: `test_wi56_promotion_repository_contracts.py` (13 tests).
- `Storage.run_repository()/policy_store()/knowledge_repository()/event_store()/promotion_repository()`: accessors cacheados que devuelven el componente REAL (antes: shim `-> self` por structural subtyping, WI-31).
- SQL vivo restante en `storage.py`: únicamente DDL (`_SCHEMA_SQL`), `_migrate` y los helpers atómicos `_insert_event_in_tx`/`_atomic_state_and_event`.

### Migration notes

- Los componentes comparten la conexión vía `Storage._conn` (decisión ADR-0016) y resuelven `_tx`/`_atomic` del dueño del schema en tiempo de llamada: el monkeypatching de H9/H10 sobre `storage._insert_event_in_tx` sigue funcionando (helpers atómicos permanecen en `Storage` por decisión del ciclo).
- `PromotionRepository` NO es `runtime_checkable`: la verificación estructural se hace por presencia de métodos.
- `Storage.list_promotions` sigue sin aceptar `limit`; el adapter del UoW recorta en memoria (contrato de puerto preservado).

### Tests

- +64 tests nuevos en las 5 redes de contrato WI-56 (dos bases idénticas sembradas, dump semántico sin columnas de reloj, UUIDs normalizados, spy de ruta atómica, guard de firmas explícitas).
- Suite no-UAT: 1720 (post-corte 3) → 1754 (post-corte 5).

### Audit debt

- `architecture-debt-2026-09-28.md` regenerado: 53 módulos / 19442 LoC; `storage.py` sale del top-3 de god modules; `knowledge_repository.py` (986 LoC) entra en la lista como componente extraído (no deuda nueva del ciclo).
- 1 finding `low` persistido en el debt-report del ciclo: flake preexistente de orden aleatorio en `test_wi56_knowledge_repository_contracts.py::list_resources` (no reproducible en 2 tiradas ni con orden fijo; seguimiento aparte).

### Fixed

- **`.jcode-scratch/` no estaba ignorado** (`8eda4ea`). Es el directorio de scratch del agente, donde se escriben los journals de `pipelinek` con journal fresco y los recibos en curso. Al no estar ignorado, cada verificación dejaba entradas no versionadas en `git status --porcelain`, y ese árbol limpio es requisito explícito del paso 1 del checklist de release de SDDK (`prompts/sddk/phases/release.md`). Es decir: el propio acto de verificar bloqueaba la release que estaba verificando. Verificado con `git check-ignore -v`.

### Housekeeping

- `STATE.yaml` declaraba 27 releases pero su lista terminaba en v0.16.0: siete releases ya publicadas (v0.16.1 a v0.16.7) no estaban registradas. Rehechas con SHA, fecha y nota reales, cada SHA verificado contra `git rev-list -1 <tag>` y `git rev-parse <tag>`. El bloque `release:` cabecera pasa de v0.16.0 a v0.16.8 con el SemVer derivado del historial.

## [0.16.7] - 2026-09-28 — complejidad de `detect_changes` y `reconcile_run`

**PATCH**. Sin `feat`, sin `fix` de contrato, sin breaking.

### Fixed

- Rechazo de `bool` en `Recipe.token_budget` y `Recipe.revision`: un booleano se colaba como número por el camino de la subclase de `int` en Python.

### Changed

- `GitSource.detect_changes`: cc 11 → 5.
- `_reconcile_run_locked`: cc 11 → 5.

Ambos refactors con red de contrato escrita antes del cambio, y la auditoría de deuda regenerada después.

## [0.16.6] - 2026-09-28 — cadenas de guardas de plan y recibo

**PATCH**.

### Changed

- Las dos cadenas de guardas restantes (`_make_schema_validator` y la validación de recibo) bajan de complejidad ciclomática, cada una con su test de contrato fijado antes del refactor.
- Fix del límite `max_visits`.
- Receipts de CI publicados por cada refactor, con el journal de `pipelinek` que demuestra que los tests se ejecutaron.

## [0.16.5] - 2026-09-28 — cierre de los dos hotspots reales de la auditoría

**PATCH**. 1455 tests PASS.

### Changed

- `cmd_promotion_reconcile` (CLI): cc 14 → 7, con `_select_promotion_failpoint`, `_abort_with_failpoint`, `_apply_pending_promotions` y `_reconcile_summaries` extraídas.
- `_make_schema_validator` (dominio): cc 13 → 3, anidamiento 5 → 0. Las reglas pasan a funciones de módulo con contexto explícito y el despacho a `match`/`case`, que es lo que corresponde a un dominio cerrado (regla 2.1 de `AGENTS.md`).

### Added

- Failpoint `after_apply_first`, que estaba **documentado pero no existía**. No es cosmético: simula la caída en el punto más peligroso de la promoción (la claim ya está en el destino pero el outbox aún no está `PUBLISHED`), y con él hay un test de subprocess que prueba el estado de split real y que la reconciliación lo reanuda de forma idempotente.

### Fixed

- La CI verde ya no se acepta como evidencia sin comprobar el journal: un run con `StageFinished` y cero `StepStarted` es un cache hit que no ejecutó un solo test. Se fija la regla operativa de que un verde no es evidencia hasta que el journal muestra `StepStarted` + `EchoOutputCaptured` en el stage de tests.

## [0.16.4] - 2026-09-28 — correctivo de v0.16.3

**PATCH**.

- Release correctiva: `v0.16.3` se publicó con package metadata defectuosa. La provenance no se reescribe; la versión buena es esta.
- `governance/backups.py`: la política de recolección se aísla del resto de la función (cc 14 → 3).
- `audits/audit_debt.py`: las recomendaciones se derivan de la medición, no de prosa congelada en el informe.
- Primera release hecha por el camino manual documentado, tras confirmarse que `sddk release plan` exige un `Cargo.toml` que este proyecto (Python) no tiene ni debe tener.

## [0.16.3] - 2026-09-28 — snapshot consistente en WAL y criterio de CI verde

**PATCH**.

### Fixed

- `sg backup create` hacía una copia cruda del fichero SQLite. Con el WAL activo, esa copia puede no contener transacciones ya confirmadas. Ahora usa el snapshot consistente de la API `Connection.backup()`.

### Documentation

- «Un pipeline en verde no prueba que los tests hayan pasado»: el cache hit de `pipelinek` producía `Pipeline finished with SUCCESS` sin ejecutar un solo test. Con la base de v0.16.2 eran 1413 tests los realmente ejecutados frente a 1455 existentes.
- Corrección de B2: `permissions.yaml` ausente **no** es una carencia del framework. Es un archivo del proyecto, en la raíz del repositorio, y el binario lo dice literalmente. El `find $FRAMEWORK` de la sesión anterior buscó en el sitio equivocado.
- Errata del mensaje de `9c0985e` (un carácter chino en mitad de una frase), registrada en vez de reescribir historia.

## [0.16.2] - 2026-09-27 — clasificación de errores por tipo y CI con rutas absolutas

**PATCH**.

### Fixed

- Los errores de `knowledge` se clasificaban por texto del mensaje en vez de por tipo. Un cambio de redacción rompía la clasificación en silencio.
- `bool` se aceptaba donde el esquema declara `integer`/`number`, porque en Python `bool` es subclase de `int`.
- `bare except` estrecho a los tipos que realmente puede lanzar.
- 7 delegaciones de `Storage` rotas dentro de `SqliteUnitOfWork`.
- CI: `.pipeline.kts` pasa a estar versionado (AGENTS.md exige que el gate de CI local canónico esté en control de versiones) y sus `sh(...)` usan rutas absolutas. El motor no resuelve el cwd del script, así que las rutas relativas se ejecutaban contra `/`.

## [0.16.1] - 2026-09-27 — cierre de conexiones en el CLI y límite estricto de DTO

**PATCH**.

### Fixed

- Los handlers del CLI no cerraban las conexiones SQLite de las que eran propietarios: se acumulaban hasta el final del proceso.
- `NameError` en `agents_root` dentro de `sg run`, detectado por un test E2E y no por la suite unitaria.

### Changed

- WI-38, R1: límite estricto de DTO en `list_promotions`, `get_promotion` y `get_budget`.

## [0.16.0] - 2026-09-27 — R1+R2 persistence boundary (WI-32.4+32.5+33)

**Resumen**: sprint completo sobre el audit externo del 2026-09-27 (HEAD pre-v0.15.0 `974055c`), cerrando los hallazgos R1 (dict[str,Any] fuga de persistencia) y R2 (Connection lifecycle). **MINOR bump** sin BREAKING CHANGE: 4 DTOs inmutables nuevos + SqliteUnitOfWork como single owner de la `sqlite3.Connection`. Total: **1109/1109 tests PASS** (+31 desde 1078, medido via `pytest --no-header -q` en HEAD `b42a2a8` en 184s), ruff check+format limpios, release_governance 2/2 PASS.

### Added

- **`StoredRun`** (8 campos, `frozen=True, slots=True`) en `platform/ports`: DTO inmutable para `workflow_runs`. Sustituye `dict[str, Any]` y `sqlite3.Row` en `Storage.list_runs/get_run/load_run` y RunController (consumo via atributos).
- **`StoredNodeExecution`** (14 campos): DTO inmutable para `node_executions`. Sustituye `dict[str, Any]` en `Storage.list_node_executions`.
- **`StoredResource`** (12 campos): DTO inmutable para `resources`. Cierra fuga en `Storage.get_resource/list_resources`.
- **`StoredRelation`** (7 campos): DTO inmutable para `relations`. Cierra fuga en `Storage.dependencies_of/dependents_of`.
- **`SqliteUnitOfWork`** (`frozen=True, slots=True`) en `platform/uow.py`: fachada que owns la `sqlite3.Connection` y expone 5 bounded-context adapters que la comparten (`SqliteRunAdapter`, `SqliteEventAdapter`, `SqliteKnowledgeAdapter`, `SqliteGovernanceAdapter`, `SqlitePolicyAdapter`). Acceso via `storage.uow.{runs,events,knowledge,governance,policy}`. Cierra el hallazgo "Connection lifecycle" del audit externo (R2).

### Changed

- **`Storage.list_runs`** ahora devuelve `list[StoredRun]` (antes `list[dict[str, Any]]`).
- **`Storage.get_run`** ahora devuelve `StoredRun` (antes `dict[str, Any]`).
- **`Storage.load_run`** ahora devuelve `StoredRun` (antes `dict[str, Any]`).
- **`Storage.list_node_executions`** ahora devuelve `list[StoredNodeExecution]`.
- **`Storage.get_resource/list_resources`** ahora devuelven `StoredResource` (no `dict`).
- **`Storage.dependencies_of/dependents_of`** ahora devuelven `list[StoredRelation]`.
- **`RunController._load_run` y `_node_executions_for`** ahora devuelven DTOs (consumo via atributos). 13 accesos `dict[key]` convertidos.
- **`Storage.__init__`** ahora crea una `SqliteUnitOfWork` interna; `storage.uow` es property pública.
- **CLI `runner.py`**: 3 consumers de `list_resources` (`_count_resources`, `_load_registry`, `declare_types_from_pack`) usan atributos del DTO.
- Cada DTO expone `to_dict()` para compatibilidad con consumers/tests legacy que esperan API dict-based.

### Migration notes

- Consumers de `Storage.list_runs` etc. deben migrar de `row["key"]` a `row.key` (atributo del DTO). Compatibilidad legacy: `row.to_dict()` preserva el dict histórico.
- `Storage.uow` es la nueva API para acceder a los bounded-context adapters. La API facade (`storage.list_runs`) sigue funcionando sin cambio.
- `isinstance(storage.uow.runs, RunRepository)` puede NO funcionar porque los adapters no implementan TODOS los metodos del Protocol (algunos delegan via `**kwargs`). Usar `callable(getattr(uow.runs, name))` para verificar presencia de metodos clave.

### Tests

- 13 tests nuevos: `test_run_dto.py` (7) + `test_resource_dto.py` (6).
- 5 tests existentes adaptados de subscript a atributo: `test_h9_storage_run_reads.py`, `test_h9_runcontroller_characterization.py`, `test_registry_branches.py`, `test_s1_sqlite.py`.
- 6 tests nuevos para UoW: `test_uow.py` (5 adapters, shared connection, lifecycle, identity stability, facade/adapter equivalence).

### Audit debt (post-WI-32.4+32.5+33)

- `Storage` `dict[str, Any]` returns: **5 → 2** (los 2 restantes son `get_promotion` + 1 governance, fuera del scope del sprint).
- `Storage` LoC: 2499 → 2716 (+217 por UoW + property `uow` + aliases; refactor pendiente WI-34 para bajar facade a <500 LoC).
- 47 modulos Python, 17163 LoC, 607 funciones (vs 46/16279/565 pre-WI-32).

## [0.15.0] - 2026-09-27 — R0 housekeeping + WI-31 (cast Storage Protocol) + WI-35 (docs) (BREAKING)

**Resumen**: cierre de la ronda de housekeeping + refactors sobre la base post-v0.14.8, en modo SDDK autónomo. **MINOR bump** por **1 BREAKING** (QW-B: redaction default `none`→`metadata`, secure-by-default) + **3 feat** (QW-C: `Storage` context manager, WI-31: factor `Storage.knowledge_repository()`, QW-I: snapshot `docs/blueprint/` versionado) + **1 fix** (QW-A: Anthropic default migrated retired model `claude-3-5-sonnet-20241022` → `claude-sonnet-4-6`). WI-31 cubre un code path del `RunController._compile_knowledge` con **0 tests** previos, anade 7 tests nuevos y elimina un `cast(Storage, self._runs)` que era un workaround del type checker. WI-35 documenta el patron SDDK end-to-end para futuras sesiones. Total: **1078/1078 tests PASS** (+30 desde 1048, +10 vs mi memoria previa de 1068; medido via `pytest --collect-only` y `--no-header -q` en HEAD `7e5566e` en 527.95s), ruff check+format limpios, cobertura **95.25%** lines / **90.54%** branches.

### BREAKING CHANGE

- **QW-B `fix(redaction)`**: default policy del EventLog paso de `"none"` a `"metadata"`. Antes (`v0.14.8.dev0` y todos los ancestros), un tenant sin policy explícita devolvia payloads sin redaccion: claves `api_key`, `password`, `token` se emitian en el `runtime_events` con su valor original. Ahora un EventLog sin policy explícita redacta todo metadata antes de emitirlos como evento. Migracion opt-in: los callers que necesiten el comportamiento anterior deben pasar `EventLog(..., policy_resolver=lambda _t: "none")` o setear `policy_resolver` a nivel tenant. Tests: `test_eventlog_default_policy_is_metadata` (re-named de `test_eventlog_passes_through_by_default`) + `test_eventlog_explicit_none_passes_through` documentan el cambio. **Impacto**: tenants que ya tenian un `policy_resolver` explicito no se ven afectados.

### Added (feat)

- **QW-C `feat(storage)`**: `Storage` como context manager — `with Storage(path) as s: ...` cierra la conexion sqlite determinísticamente via `__exit__`. Antes (`v0.14.8.dev0` y todos los ancestros), abrir una `Storage` sin `close()` emitia `ResourceWarning: unclosed database`. El metodo `close()` es idempotente. Nuevo modulo `tests/test_storage_context_manager.py` con 6 tests. Migracion opt-in: callers existentes con `storage.close()` siguen funcionando igual.

- **WI-31 `refactor(runcontroller)`** (`Storage.knowledge_repository()` factor): introduce una tercera factoria `Storage.knowledge_repository()` paralela a `Storage.run_repository()` y `Storage.event_store()`, devolviendo el propio `Storage` (sin implementar otras vistas). Como los dos Protocols `RunRepository` + `KnowledgeRepository` los implementa `Storage` por structural subtyping, este factor se reduce a sinonimo de `self`. Habilita la migracion futura a `RunStorage`/`KnowledgeStorage` separadas (WI-02b) sin tocar `RunController`. Tambien: nuevo kwarg opcional `knowledge: KnowledgeRepository | None` en `RunController.__init__` que elimina el antiguo `cast(Storage, self._runs)` en `_compile_knowledge`. 4 callers legacy en `tests/test_h9_context_in_run.py` migrados con `knowledge=s` explicito. 7 tests nuevos en `tests/test_runcontroller_compile_knowledge.py`. Tambien: `Storage.close()` cambia `try/except pass` por `contextlib.suppress(ProgrammingError)` (ruff SIM105).

- **QW-I `docs(blueprint)`**: snapshot versionado del blueprint en `docs/blueprint/` (12 capitulos + README + adr/ 13 ADR + plan/ 6 plans + references/). Antes el test `test_uats_can_be_loaded_as_documentation` leia de `external/blueprint-v1/` que esta gitignored y saltaba con `pytest.skip`. Ahora lo lee del snapshot versionado. `.gitignore` permite unicamente `docs/blueprint/` (no `docs/*` blanket). Script `scripts/sync_blueprint.sh` idempotente; `--check` detecta drift entre el origen y el snapshot via SHA256. Documento `docs/blueprint/SYNC.md` con la politica on-demand.

### Fixed

- **QW-A `fix(http_adapter)`**: el default Anthropic para `HttpAgentAdapter` migraba a `claude-sonnet-4-6` desde el model `claude-3-5-sonnet-20241022` que Anthropic retiro el 2025-10-28. Antes, una llamada HTTP sin header explicito `x-llm-model` enviaba una peticion que el proveedor rechazaba con 404 Not Found. Tambien: blacklist de modelos retirados en tests (`claude-3-5-sonnet-20240620`, `claude-3-opus-20240229`). Test nuevo: `test_default_model_anthropic_not_deprecated`.

### Changed (refactor, sin bump)

- **QW-D `refactor(runtime_types)`**: `EVENT_KINDS` ahora se deriva del Literal `EventType` via `frozenset(get_args(EventType))` (no mas frozenset paralelo). Antes `EventType` (Literal 8 valores) y `EVENT_KINDS` (frozenset 14 valores) eran DOS conjuntos con solo 3 valores comunes. Despues: 19 valores unicos. 2 tests nuevos (`TestEventKindSingleSource`) verifican single-source-of-truth.

- **QW-E `refactor(runtime_types)`**: `SOURCE_KINDS` ahora derivado del Literal `SourceKind` via `frozenset(get_args(SourceKind))` (5 valores; `skill_pack` ahora valido). Antes el frozenset omitia `skill_pack` y lo rechazaba runtime aunque el Literal lo declaraba. 2 tests nuevos (`TestSourceKindSingleSource`).

- **QW-F + QW-G `chore(coverage)`**: `fail_under` 60→80 + omit de `__init__.py`, `__main__.py`, `cli/runner.py` en `[tool.coverage.run]`. Tambien: `tests/uat_audit.py` y `tests/test_cli_uat.py` propagan `PYTHONPATH` al subprocess cuando el padre corre dentro del venv (QW-G fix que evita `No module named skillgraph` en tmpdir).

- **QW-H `refactor(uat_audit)`**: `uat_audit.uat_08()` y `uat_audit.uat_09()` ahora leen la evidencia existente en `tests/uat-evidence/UAT-XX.json` en vez de pisarla con un stub BLOCKED. Antes el test E2E `test_h4_expansion_cli.py` escribia evidencia PASS real, y `uat_audit` lo sobrescribia con BLOCKED en cada corrida. 5 tests nuevos verifican ambos caminos.

### Chore (no bump)

- **`pytest` + coerencia release governance**: el conjunto de stewardship (STATE.yaml + CURRENT.md + CHANGELOG.md) ahora cubre la timeline completa del repo en una sola fuente. `current_workitem` en STATE.yaml pasa de `WI-30` a `WI-31` (primera vez que cambia despues de WI-30).

- **`scripts/sync_blueprint.sh`** (QW-I): idempotente; modo `--check` detecta drift sin tocar archivos.

- **WI-35 `docs(state)`**: prioridad_6 en `STATE.yaml.stewardship_backlog` documenta el patron operacional aplicado en WI-31 (cycle start → backlog capture → TDD → commit atomico → smoke → triage → promote). Entrada en SESSION-JOURNAL.md con SHA del commit y bl_item_id. Sin cambio de contrato.

## [0.14.8] - 2026-09-26 — WI-21..WI-30 (debt-reduction H-03: 8 hotspots cc→low single-digits)

**Resumen**: ciclo de deuda tecnica quirurgica cerrando 8 hotspots publicos identificados en el catalogo H-03 (cyclomatic complexity > 15 en `src/`). Patron consistente: extraer helpers privados puros + module-level utilities, manteniendo 100% backward-compat. WI-28 anade auditor reproducible `audits/audit_debt.py`. **Politica D-66 satisfecha**: cero hotspots publicos cc≥20 en `src/` (unico cc≥15 restante: `main()` cc=50, excluido por D-64 al ser CLI entry point / H-02 god module). Tests: **1048/1048 PASS** preservados, ruff check+format limpios, auditor reproducible.

### Changed (debt-reduction H-03, refactor surgical)

- **WI-21**: `graph_expansion.validate` cc 24→4 (D-52). Helpers puros.
- **WI-22**: `parser.parse_markdown` cc 17→2 (D-53/D-54). Helpers + bug descubierto por TDD: gender mismatch "revision vacia" vs helper default "vacio".
- **WI-23**: `locks.take` cc 16→5 (D-55). 4 helpers privados.
- **WI-24**: `record_validation_receipt` cc 14→5 (D-56/D-57). 4 helpers; kwarg `empty_msg` preservado verbatim.
- **WI-25**: `traverse_invalidations` cc 13→5 (D-58). 3 helpers (seed/expand/warn); TDD catcho bug de kwarg unused `hop` que se quedaba en helper.
- **WI-26**: `HttpAgentAdapter.invoke` cc 12→7 (D-59). Sentinel `RetryableHttpStatus` + helper `_dispatch_response`.
- **WI-27**: `compile_handoff_from_scopes` cc 12→1 (D-60). Triada `validate_inputs` + `enforce_*_or_raise` + `build_synth_recipe`. TYPE_CHECKING imports block + `Sequence` from `collections.abc` para F821/UP035/UP037 simultaneos.
- **WI-29**: `cli.runner.cmd_run` cc 22→5 (D-67). Patron `_resolve_run_inputs` + `_reconcile_until_terminal` + `_resolve_fixtures_root`. Lazy imports para evitar coste arranque CLI.
- **WI-30**: `knowledge.git_source.detect_changes` cc 18→8 (D-68). 3 helpers (1 metodo privado + 2 module-level).

### Added (audit infrastructure)

- **WI-28**: `audits/audit_debt.py` (~215 LoC) reproducible CLI. Reporta cc, loc, nesting, god modules, hotspots publicos/privados, funciones largas. Emite `audits/architecture-debt-YYYY-MM-DD.md`. Smoke tests `tests/test_audit_debt_smoke.py` (4/4 PASS).
- **D-61..D-66**: decisiones arquitectonicas formales (god modules thresholds, exclusion de `main()`, politica D-66 "cero hotspots publicos cc≥20 en cada release o documentar la excepcion").
- **D-67/D-68**: patrones estructurales post-WI-28.

### Notes

- **MINOR bump** (regla WI-01 + AGENTS §7 SEMVER): los 8 `refactor` no son breaking, pero la campana debt-reduction es estructural y merece release visible. 0.14.7 → 0.14.8.
- Mantiene regla WI-01 "release sin --force sobre published tags": v0.14.1..v0.14.7 intactos, este release es nueva v0.14.8.
- Migracion Pattern transitorio `.dev0`: post-tag housekeeping mantiene `__version__ = "0.14.8.dev0"` para cumplir release_governance (`HEAD > last-tag` exige `.devN`).
- Backlog post-WI-30: P1 god modules (H-01 storage 2407 LoC, H-02 cli/runner 2477 LoC, runcontroller 1357 LoC) requieren ADR — fuera del scope surgical. Formal `prioridad_1_spec_s7plus` y `prioridad_5_s7plus_ejecucion` siguen abiertos esperando decision de operador sobre S7+ scope.

## [0.14.7] - 2026-09-26 — WI-12..WI-17 (FEAT+DOC: sg backup + threat model + observability)

**Resumen**: ciclo mixto feat+debt que cierra H-06 (cmd_knowledge_compile import redundante), anade backups ZIP con SHA-256 (`sg backup create|list|restore`), publica Threat Model S8 surface HTTP + `repr` redact de `api_key`, y corre runbook T6 de observability (9 secciones verificadas). Tests: 1024/1024 PASS, ruff check+format limpios. MINOR bump por nueva capacidad observable (`sg backup`). **Nota**: esta entrada se reescribe retroactivamente en el release v0.14.8 — el tag v0.14.7 existia pero CHANGELOG fue omitido en el ciclo original.

### Added (FEAT)

- **WI-15**: `sg backup create|list|restore` con ZIP + SHA-256 (22 tests en `tests/test_backup.py`). Comandos nuevos del CLI para backup/restore del SQLite state.
- **WI-14 (T3)**: Threat model S8 surface HTTP documentado en `docs/observability-runbook.md`. `HttpAgentAdapter` ahora redacta `api_key` en `repr()` para evitar leak en logs/traces.

### Changed (DOC)

- **WI-16**: runbook T6 ampliado a 9 secciones (alerts, dashboards, SLOs, incident response, etc.) con claims verificados.
- **WI-17**: H-06 cierre, `cmd_knowledge_compile` pierde `import json` redundante.

### Notes

- **MINOR bump**: nuevo subcommand `sg backup` es capacidad observable nueva. 0.14.6 → 0.14.7.

## [0.14.6] - 2026-09-26 — WI-06..WI-10 (housekeeping: coverage hardening H-14 + docs sync)

**Resumen**: cierre de los 3 unicos gaps materiales de cobertura reconocidos en `CURRENT.md` para el nucleo evolution-v2 (H11..H15): `governance/receipts.py` 73%→99% (WI-06), `file_handoff.py` 85%→93% (WI-07), `governance/improvement.py` 84%→100% (WI-08). Adicionalmente se sincroniza la prosa de `CURRENT.md` y `README.md` con la realidad post-stewardship créatif (WI-09, WI-10), incluyendo badges `984/984 tests` y `evolution_v2 100% (H11..H15)`. Sin cambio de codigo de produccion (WI-06/07/08 son solo tests). Tests: 984/984 PASS preservados en CI local (`pipelinek`) y `ruff format` + `ruff check` limpios.

### Added (test coverage)

- **`tests/test_h14_validation_receipts.py`** (WI-06): +28 tests en 5 clases nuevas. Cubre `ValidationReceipt.__post_init__`, `is_receipt_applicable` con deps, `record_validation_receipt` early returns, `list_applicable_receipts` paths defensivos, constante `RECEIPT_VERDICTS`.
- **`tests/test_h13_handoff_expert.py`** (WI-07): +17 tests en 5 clases nuevas. Cubre mensajes `HandoffBlockedError`, `build_coverage_manifest` con focos, `should_skip_adapter` con payloads vacios, `ScopeAwareRecipe` validation, type-checks defensivos.
- **`tests/test_h15_improvement.py`** (WI-08): +14 tests en 7 clases nuevas. Cubre `ImprovementCandidate.__post_init__`, `PromotionDecision.__post_init__`, `promote_candidate` approver required, `rollback_candidate` policy="blocked", `detect_redundant_extraction` empty sigs, `localize_omission` defensive branches, `compare_recipes` correction=False.

### Changed (docs sync)

- **`CURRENT.md`** (WI-09): limpieza de 4 stale markers pre-WI-06 (L50 "HEAD pendiente", L57 "working tree staged", L59 "HEAD == origin/main"); adicion de seccion cronologica `## Reactivacion 2026-09-26 — WI-06/07/08 cerrado`; actualizacion del modo de espera con el estado real post-stewardship.
- **`README.md`** (WI-10): badge `tests-405/405` → `tests-984/984`; nuevo badge `evolution_v2 100% (H11..H15)`; parrafo explicativo y filas tabla en EN y ES para evolution-v2 (H11..H15).
- **`STATE.yaml`**: `tests.total` 957→984, `delta_wi06/07/08` documentados, `current_workitem` actualizado WI-08→WI-11.

### Notes

- PATCH bump: housekeeping puro (test coverage + docs), sin cambio de API observable.
- Mantiene regla AGENTS §7 "release sin --force sobre published tags": los tags `v0.14.1..v0.14.5` quedan intactos, este release es nueva `v0.14.6`.
- Migracion Pattern transitorio `.dev0`: post-tag housekeeping mantiene `__version__ = "0.14.6.dev0"` para cumplir release_governance (`HEAD > last-tag` exige `.devN`).
- Stewardship créatif ejecutado bajo autorizacion operador ("continuamos completando, deuda tecnica primero") — D-17..D-34 documentadas.

## [0.14.5] - 2026-09-26 — WI-04/05 (housekeeping trazabilidad: journal retroactivo + cleanup drifts)

**Resumen**: cierre de drift de trazabilidad canonica detectado por audit transversal post-WI-03. Las entradas cronológicas de WI-02b y WI-03 faltaban en `SESSION-JOURNAL.md`; se añaden retroactivamente desde observables (commits, tags, CHANGELOG, specs). Adicionalmente se cierra drift menor en `CURRENT.md` (baseline tests 927→929; cuenta de releases 17→18) y bump `.dev0` requerido por `release_governance` (`HEAD > last-tag` exige `.devN`). Sin cambio de codigo de produccion. Tests: 929/929 PASS preservados en CI local (`pipelinek`) sin ejecutarse code paths nuevos.

### Changed (housekeeping)

- **`SESSION-JOURNAL.md`**: 2 entradas retroactivas (WI-02b, WI-03) + 1 entrada del propio WI-04. Tono consistente con entradas existentes; hechos verificables contra git log + CHANGELOG; sin reinterpretacion.
- **`CURRENT.md`**:
  - `Tests: 927/927 PASS` → `929/929 PASS` (post-WI-03).
  - `17 releases` → `18 releases` (contaban v0.14.3 y v0.14.4; ahora 18 antes del bump final).
- **`STATE.yaml`** + `__init__.py`: bump `0.14.4.dev0` → `0.14.5` (release).
- **`specs/wi-04-journal-traceability.md`**: spec del WI (D-16, 73 LoC).

### Notes

- PATCH bump: housekeeping puro (documentacion + bumps de gobernanza), sin cambio de API observable.
- Mantiene regla AGENTS §7 "release sin --force sobre published tags": el tag `v0.14.4` queda intacto, este release es nueva `v0.14.5`.
- Migración Pattern transitorio `.dev0`: solo si housekeeping post-tag requiere `.devN` para release_governance y el operador autoriza release inmediato (v0.14.5 PATCH). Alternativa habitual es acumularlo en un WI posterior.

## [0.14.4] - 2026-09-26 — WI-03 (governance/receipts migra a KnowledgeRepository)

**Resumen**: cierre del último escape hatch `_conn.execute` en código de dominio (fuera de Storage.py, que es donde debe estar, y catalog.py, que usa un SQLite propio distinto del Storage de proyecto). Sin cambio de API observable. Tests: 929/929 PASS (de 927 en v0.14.3; +2 tests nuevos de Storage.list_sources).

### Changed (interno, sin API change)

- **`KnowledgeRepository` Protocol** añade `list_sources(*, tenant_id, project_id) -> tuple[Source, ...]` (duck typing).
- **`Storage.list_sources`** nueva: SELECT * FROM sources WHERE tenant_id = ? AND project_id = ? ORDER BY source_id. Read-only, tupla inmutable.
- **`receipts.list_applicable_receipts`**: itera `storage.list_sources(...)` en vez de `storage._conn.execute('SELECT source_id FROM sources ...')`. Semántica idéntica (mismos source_ids visitados; el nuevo método devuelve además el ADT completo por si futuro).
- **Audit transversal post-WI-02b**: `grep "_conn" src/skillgraph/governance/` → 0 sitios activos (solo aparece en comentario histórico del WI-03). `grep "_conn" src/skillgraph/ --include="*.py" | grep -v "platform/storage.py\|resources/catalog.py"` → 0 sitios.

### Notes

- `catalog.py` queda con acceso directo a `_conn`: usa un SQLite propio en `data_root/catalog.sqlite`, no es Storage de proyecto (no viola la regla "Storage encapsula SQL", que se aplica a la tabla de proyecto). Fuera de scope.
- WI-02b AC-5 extendido ahora a `governance/`: regla "Storage encapsula SQL" completa en KC, KI, ContextController, receipts.
- PATCH bump (sin breaking change, sin nuevos comandos CLI).

## [0.14.3] - 2026-09-26 — Refactor WI-02b (EventLog + KnowledgeController + escape hatch removal)

**Resumen**: segunda mitad del refactor de puertos de persistencia (WI-02b). Cierra los últimos 2 ACs abiertos en 0.14.2: AC-3 (EventLog/KnowledgeController aceptan Protocols en vez de Storage) y AC-4 (eliminación del escape hatch `Storage.conn`). Sin cambio de API observable para el usuario. Tests: 926/926 PASS (sin regresión) en CI local canónico (`pipelinek`).

### Changed (interno, sin API change)

- **`EventLog`** ya no se construye con `sqlite3.Connection`; ahora acepta directamente el `EventStore` Protocol (que `Storage` cumple por duck typing). Wrappers `event_store()` y `record_event()` añadidos a `Storage` para que siga siendo fachada compatible.

- **`KnowledgeController`** ya no se construye con `storage=Storage`; ahora recibe `knowledge=KnowledgeRepository`. `KnowledgeInvalidator` deja de acceder a `controller.storage._conn` (5 sitios SQL → 0). `ContextController` interno deja de acceder a `ctrl.storage.*` (4 sitios SQL → 0).

- **`Storage.conn`** (`@property` público introducido en H9-BSlice3-S8) **eliminado**. Era escape hatch que rompía la regla "Storage encapsula SQL" — los call sites que aún lo necesitaban (3 tests internos + 1 caso de test_h9_storage_run_controller_no_conn) migran a `Storage._conn` (privado por convención, sigue permitido). `TestStorageConnPublic` borrado (validaba un artefacto que ya no existe).

- **Protocols ampliados**: `EventStore` recibe `fetch_event_raw()` y `ensure_schema()`; `KnowledgeRepository` recibe `find_entity()`, `source_exists_anywhere()`, `list_claims_for_subject()`, `list_claims_using_evidence()`, `mark_claims_stale()`, `reactivate_claims_with_revision()`, `list_stale_claims()`, `record_event()` (para emisión de `KnowledgeInvalidated` por KI).

- **Tests**: 4 archivos migrados a `SqliteEventStoreForTest` (helper de tests que aún necesitan `sqlite3.Connection` directo: `test_runtime_events.py`, `test_redaction.py`, `test_runcontroller.py`, `test_h9_runcontroller_characterization.py`).

### Notes

- AC-3 (RC/KC/KI reciben Protocols, sin `storage=` ni `conn=`): **PASS**.
- AC-4 (`Storage.conn` eliminado, escape hatch cerrado): **PASS**.
- AC-5 (KC/KI independientes de `_conn`, regla "Storage encapsula SQL" completa): **PASS** (verificación: `grep "_conn" src/skillgraph/knowledge/knowledge_controller.py` → exit 1).
- AC-11 (`Storage` sigue siendo fachada compatible): **PASS** (los 3 métodos añadidos son del Protocol; la API pública no rompe).
- `tests/uat-evidence/UAT-{08,09}.json` drift explícitamente fuera de alcance del WI-02b.
- Sin bump adicional al SemVer: API externa sin cambio (PATCH).

## [0.14.2] - 2026-09-26 — Refactor B+C (persistence ports + RunController) (WI-02a)

**Resumen**: refactor interno de la capa de persistencia. Introduce
puertos de capacidad (Protocols estructurales) sin cambio de API
observables para el usuario. Tests: 927/927 PASS (155.73s) en CI
local canónico (`pipelinek`).

### Added

- `src/skillgraph/platform/ports/__init__.py`: cinco `Protocol`s
  estructurales de capacidad (duck typing sin `runtime_checkable`
  salvo `EventStore`):
  - `RunRepository`: ciclo de vida de runs.
  - `EventStore`: append-only de eventos con `UNIQUE(event_id)`.
  - `KnowledgeRepository`: lectura/escritura de documentos.
  - `PromotionRepository`: snapshots de promoción policy→production.
  - `PolicyStore`: versionado de políticas.
- `tests/test_persistence_ports.py`: 7 tests (5 structural +
  2 `runtime_checkable` sobre `EventStore`).
- Factorías en `Storage`: `run_repository()`, `event_store()`,
  `policy_store()` (compatibilidad — devuelven `self`).

### Changed

- `RunController.__init__`: sustituye `storage: Storage` por
  tres puertos explícitos: `runs: RunRepository`,
  `events: EventStore`, `policy: PolicyStore`. La inyección
  por Protocol elimina el acoplamiento a la implementación.
- Migración masiva de call sites: 16 ficheros de test +
  `src/skillgraph/cli/runner.py` actualizados a la nueva firma.
- Verificado: `Storage` implementa estructuralmente los cinco
  Protocols (19/3/4/23/3 métodos coinciden).

### Deferred (WI-02b)

- `EventLog`: migración de `sqlite3.Connection` directo a `EventStore`.
- `KnowledgeController`: dejar de acceder a `storage._conn`.
- Eliminación de `Storage.conn` como propiedad pública (romper API).

---

## [0.14.1] - 2026-09-26 — Release & integration readiness (WI-01)

**Resumen**: release correctiva que cierra la grieta de provenance
entre `__version__` y las etiquetas git. CI local canónico = `pipelinek`.
Sin cambio de capacidad observable a nivel de API; todos los items son
de empaquetado, admisión y reconciliación documental.

### Added

- `tests/test_release_governance.py`: admission gate de release. Tres
  ramas válidas (HEAD en etiqueta, HEAD posterior con `.devN`, sin
  etiqueta reachable) y dos derivas reales rechazadas (`__version__`
  puro sin etiqueta; `.devN` con base contradictoria).
- `SECURITY.md`: proceso de divulgación coordinada (GHSA,
  ventana High = 90 días).
- Regla `§12 Regla de release` en AGENTS.md: fuente única de
  SemVer = `src/skillgraph/__init__.py:__version__`; prohibido
  `--force` sobre etiquetas publicadas; release gate = test pytest.

### Changed

- `mise.toml`: `tasks.sync` migra de `--extra dev` (roto en PEP 735)
  a `--group dev`. Nueva `tasks.release-gate`.
- `pyproject.toml`: `license` pasa de `Proprietary` (text) a
  `"Apache-2.0"` (SPDX), alineado con `LICENSE` real.
- `pyproject.toml`: `[tool.coverage.report] fail_under` sube de 0
  a 60 (gate global mínimo; focales por módulo siguen en WI-02).
- `src/skillgraph/__init__.py:__version__` = `"0.14.1.dev0"` durante
  el trabajo; `"0.14.1"` tras CI verde.
- Documentación reconciliada: CURRENT.md, STATE.yaml, JOURNAL y
  CHANGELOG convergen en baseline real (918 tests, 160.74s).

### Erratum: `v0.14.0`

La etiqueta `v0.14.0` queda como **evidencia histórica de una release
defectuosa** (HEAD `d50f666`, package metadata declaraba `0.7.0.dev0`).
**NO se reescribe**. La release correctiva es `v0.14.1`. SemVer no
contempla reescritura retroactiva de versiones publicadas.

## [Unreleased — evolution-v2 (H0..H15)] — 2026-09-25

**Resumen**: roadmap `external/evolution-v2/plan/ROADMAP.md` cerrado al 100%. 5 nuevos modulos, 58 tests UAT-EVO nuevos (suite 830/830 PASS). NO bump de release: los workitems añaden superficie de conocimiento/governance sin capacidad observable nueva a nivel de API CLI (no hay comandos ni flags nuevos).

### Added (evolution-v2)

- **H0–H1 (foundation)**: cobertura del recorrido real y caracterización de gates (audits/h10-recorrido-real-2026-09-25.md).
- **H11 — Conocimiento tipado reutilizable** (`skillgraph.knowledge.file_signature`): `FileSignature`, `SignatureProcedencia`, `SignatureVigencia`, `ExtractionState`. Pure extractor regex_def. Persistencia via `Evidence(kind='file_signature')` reusando tabla existente.
- **H12 — Scopes y consultas composables** (`skillgraph.knowledge.file_scope`): `FileScope` Literal, `ScopeQuery`, `ScopeResolution`, `AggregatedSignatures`, `aggregate_signatures()` puro. Aislamiento E2E-08 estricto.
- **H13 — Handoff experto desde consultas** (`skillgraph.knowledge.file_handoff`): `ScopeAwareRecipe` (composicion sobre `ContextRecipe`), `CoverageManifest`, `HandoffBlockedError`, `compile_handoff_from_scopes()`. Manifest como representación canónica; handoff compila OK con `obligatory=()`.
- **H14 — Evidencia operativa temporal** (`skillgraph.governance.receipts`): `ValidationReceipt` (frozen, verdict Literal), `is_receipt_applicable()` puro, `record_validation_receipt()`, `list_applicable_receipts()`. Persistencia via `Evidence(kind='validation_receipt')`.
- **H15 — Evaluación y automejora acotada** (`skillgraph.governance.improvement`): `ImprovementCandidate` + `ImprovementKind` Literal cerrada, `detect_redundant_extraction()`, `localize_omission()`, `compare_recipes()`, `promote_candidate()` exige `human_approved=True` (UAT-EVO-18 sin autocertificacion, `SelfCertificationBlockedError` tipado), `rollback_candidate()` con `RollbackPolicy` Literal.

### Notes

- Persistencia H11–H15: ninguna tabla nueva. Todos los nuevos tipos se almacenan via `Evidence(kind=...)` reusando la tabla `evidence` existente (regla AGENTS §1.5).
- ADT cerradas: `ExtractionState`, `FileScope`, `ImprovementKind`, `RollbackPolicy`, `ReceiptVerdict` via `Literal[...]` (regla AGENTS §2.1).
- Errores tipados: `HandoffBlockedError`, `SelfCertificationBlockedError` (subclases de `SkillGraphError`, regla AGENTS §1.2).
- Tests UAT-EVO: 4 + 12 + 8 + 8 + 9 + 9 = 50 nuevos (H0–H1 + H11–H15).

## [0.7.0] — 2026-09-24

**Resumen**: refactor arquitectónico con **BREAKING CHANGE** en la
estructura de imports. La capa de compat layer en la raíz de
`src/skillgraph/` se elimina: los 20 módulos que eran re-exports
puros hacia bounded contexts (`catalog`, `recipe`, `runtime_types`,
`dsl`, `errors`, `graph_expansion`, `handoff`, `storage`, `workflow`,
`bricks`, `git_source`, `pack_loader`, `promotion`, `runcontroller`,
`skill_importer`, `paths`, `agent`, `context_controller`,
`knowledge_controller`, `knowledge_invalidator`) desaparecen.

Adicionalmente, `knowledge/context_controller.py` deja de acceder a
`storage._conn` directamente; ahora delega en 3 APIs públicas nuevas
del Storage (`list_claims_by_predicate`, `list_evidences_for_source`,
`list_resource_refs_for_run`). Cumplimiento completo de la regla
arquitectónica "Storage encapsula SQL" introducida en 0.6.0.

**Resultado neto**: 619/619 tests PASS (de 604 en 0.6.0, +15). 16/16
UAT PASS, 0 FAIL, 0 BLOCKED. Cobertura 85% branch.

### SemVer decision

El refactor 2 introduce cambios incompatibles de import paths
(un importador externo que usaba `from skillgraph import Storage`
queda roto). SemVer estricto promovería esto a **MAJOR** (1.0.0).

Sin embargo, este proyecto **no tiene importadores externos**
(repo local-only, sin `git push`, sin dependencias aguas abajo).
Por tanto el impacto real de la rotura es CERO: la test suite
integrada se reescribió en el mismo commit.

Se etiqueta como **MINOR** (0.7.0) por:
1. Decisión explícita del operador ("tag MINOR tras el refactor
   combinado") registrada en SESSION-JOURNAL 2026-09-24 06:46.
2. La regla de la introducción del CHANGELOG ("BREAKING CHANGE / `!`
   → MAJOR") se respeta en el sentido de que es BREAKING y se
   documenta como tal. La decisión de no promover a MAJOR se basa
   en la **excepción documentada de "sin importadores externos"**.

Si el proyecto adquiere importadores externos en el futuro, el
próximo cambio incompatible debe promover a 1.0.0 sin excepciones.

### BREAKING CHANGES (MAJOR por semver estricto)

- `from skillgraph.storage import Storage` ya **no funciona**;
  debe ser `from skillgraph.platform.storage import Storage`.
- Análogamente para todos los 19 shims restantes:
  - `skillgraph.errors` → `skillgraph.core.errors`
  - `skillgraph.recipe` → `skillgraph.core.recipe`
  - `skillgraph.runtime_types` → `skillgraph.core.runtime_types`
  - `skillgraph.dsl` → `skillgraph.domain.dsl`
  - `skillgraph.pack_loader` → `skillgraph.domain.pack_loader`
  - `skillgraph.skill_importer` → `skillgraph.domain.skill_importer`
  - `skillgraph.graph_expansion` → `skillgraph.governance.graph_expansion`
  - `skillgraph.promotion` → `skillgraph.governance.promotion`
  - `skillgraph.context_controller` → `skillgraph.knowledge.context_controller`
  - `skillgraph.git_source` → `skillgraph.knowledge.git_source`
  - `skillgraph.knowledge_controller` → `skillgraph.knowledge.knowledge_controller`
  - `skillgraph.knowledge_invalidator` → `skillgraph.knowledge.knowledge_invalidator`
  - `skillgraph.paths` → `skillgraph.platform.paths`
  - `skillgraph.bricks` → `skillgraph.resources.bricks`
  - `skillgraph.catalog` → `skillgraph.resources.catalog`
  - `skillgraph.workflow` → `skillgraph.resources.workflow`
  - `skillgraph.agent` → `skillgraph.runtime.agent`
  - `skillgraph.handoff` → `skillgraph.runtime.handoff`
  - `skillgraph.runcontroller` → `skillgraph.runtime.runcontroller`

Este es un **MINOR** y no MAJOR porque no hay importadores
externos (proyecto local-only, sin `git push`). Se documenta
como BREAKING por honestidad pero el impacto real es CERO
(test suite integrada reescrita en el mismo commit).

### Refactors (sin bump adicional)

- **`Storage` — 3 métodos nuevos (lectura pura)**:
  - `list_claims_by_predicate(*, project_id, predicate, claim_target)`
    — devuelve claims que matchean el predicado (line_count,
    function_count, imports_module, defines_symbol, test_passes,
    file_exists, spec_revision).
  - `list_evidences_for_source(*, source_id)` — evidences ligadas
    a un source.
  - `list_resource_refs_for_run(*, run_id, kind="claim"|"evidence")` —
    refs únicas, DISTINCT + ORDER, con validación de kind.

- **`context_controller.py` — 4 sitios SQL eliminados**: el código
  ahora delega en las 3 APIs nuevas, no accede a `_conn`. La regla
  "Storage encapsula SQL" se cumple completa en este módulo.

### Cambios estructurales (borrado)

- 20 shims eliminados de `src/skillgraph/*.py` (1-9 LoC cada
  uno, re-exports puros).
- 37 ficheros de tests reescritos: ~118 imports de shim a
  bounded context directo (mecánico via script Python con
  mapping 1:1 por shim).
- 2 tests en `tests/test_uat_blocked.py` actualizados
  (`test_h6_pack_loader_module_exists` ahora importa desde
  `skillgraph.domain.pack_loader`; `test_h7_promotion_module_exists`
  importa desde `skillgraph.governance.promotion`).

### Tests (sin bump adicional)

- +15 tests de contrato observable en
  `tests/test_h9_storage_context_controller_reads.py`:
  - 4 tests `list_claims_by_predicate` (contrato, aislamiento,
    no-match, columnas).
  - 3 tests `list_evidences_for_source` (contrato, no-match,
    columnas).
  - 6 tests `list_resource_refs_for_run` (kind=claim,
    kind=evidence, DISTINCT+ORDER, aislamiento run_id, no-events,
    kind inválido → ValidationError).
  - 2 tests de no-regresión por introspección
    (ContextController sin `_conn.execute`; uso de los 3 métodos
    públicos).

### Limitaciones NO ocultas

- Cobertura de `context_controller` sigue 82% (subir a 90%+
  requeriría +6..10 tests de ramas defensivas de las 3 APIs
  nuevas — **NO incluidos** en este release porque son tests
  de cobertura, no tests de refactor). Documentado en
  CURRENT.md 2026-09-24 06:46.

### Reversibilidad

`git revert f2cbb2f` revierte el refactor 2 completo.
`git revert 2751bc8` revierte el refactor 1.
Tests con asserts explícitos sobre los shims se reescribieron
en el mismo commit (no quedan referencias explícitas).

## [0.7.1] — 2026-09-24

**Tag**: `v0.7.1` (965446fadd1ca4cb11d8dfb5ddd8e56b090f1eb0).

**Resumen**: introduce 3 APIs atómicas nuevas en `Storage` para
escribir mutaciones de `node_executions` y su(s) evento(s)
correspondiente(s) en una sola transacción:

- `start_node_execution_atomically(event=..., ...)`:
  1 INSERT (RUNNING) + 1 evento (NodeScheduled).
- `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)`:
  1 UPDATE (SUCCEEDED) + 2 eventos (NodeCompleted + EvidenceProduced).
- `mark_node_failed_atomically(event=..., ...)`:
  1 UPDATE (FAILED) + 1 evento (NodeFailed).

Cada llamada ejecuta una transacción compartida
(BEGIN/COMMIT/ROLLBACK explícito sobre `_conn`). Si el INSERT del
evento falla, la mutación de estado rollbackea como una sola
unidad. Esto cierra las grietas atómicas B, C y D del documento
de caracterización de Plan B.

**Idempotencia**: `UNIQUE(event_id)` sobre `runtime_events` se
traduce a `IdempotencyError` via `try/except sqlite3.IntegrityError`.
Replay con el mismo `event_id` lanza `IdempotencyError`, nunca un
duplicado. Cumplimiento UAT-07.

**Importante**: las 3 APIs `*_atomically` corrigieron el **camino público**
de `Storage` (las firmas que invocaba el runtime antes del refactor),
pero el `with self._conn:` preexistente y los APIs NO-atómicas legacy
del Storage siguen sin rollbackear en `isolation_level=None`. Esta
grieta queda documentada como **LIMITACIÓN-7** (no resuelta en este
release; huérfana hasta v0.7.3 con un fix parcial sobre V4).

### Compatibilidad

- `629 passed, 1 skipped in 143.06s` (cifra del log
  `audits/cleanroom-evidence/ci-output-v0.7.1.txt`; skip en
  `test_cli_uat.py:363`, preexistente). Sin tests nuevos propios:
  este slice prepara el terreno para v0.7.2.
- 16/16 UAT PASS, 0 FAIL, 0 BLOCKED.
- 0 breaking changes: APIs legacy siguen vigentes.

### Evidencia

- `audits/release-v0.7.1-summary.md` (ya generado, link al bundle).
- `audits/cleanroom-evidence/skillgraph-v0.7.1-audit-bundle.tar.gz`.
- `audits/cleanroom-evidence/ci-output-v0.7.1.txt`.
- `audits/cleanroom-evidence/uat-audit-v0.7.1.txt`.

## [0.7.2] — 2026-09-24

**Tag**: `v0.7.2` (338fcc2eed72eb0a0f24f54532032461bded83f3).

**Resumen**: cierra el **defecto de integración** detectado por la
auditoría externa de `v0.7.1`. El release anterior ofreció 3 APIs
atómicas nuevas en `Storage` (`start/complete/fail *atomically`),
pero `RunController._execute_one` seguía invocando las APIs
no-atómicas y emitiendo eventos con llamadas separadas a
`EventLog.append`. Esto significaba que **el recorrido real del
runtime nunca obtuvo la garantía transaccional**.

`v0.7.2` sustituye los pares modificar-estado → emitir-evento en
`RunController` por las APIs atómicas. La garantía se acredita en
el camino público del runtime, no solo en el Storage aislado.

### `RunController._execute_one`

| Momento | Antes (v0.7.1) | Después (v0.7.2) |
|---|---|---|
| Start | `start_node_execution(...)` + `EventLog.append(NodeStarted)` | `start_node_execution_atomically(event=..., ...)` |
| Complete | `complete_node_execution(...)` + `EventLog.append(NodeCompleted)` + `EventLog.append(EvidenceProduced)` | `complete_node_execution_atomically(event_completed=..., event_evidence=..., ...)` |
| Fail | `mark_node_failed(...)` + `EventLog.append(NodeFailed)` | `mark_node_failed_atomically(event=..., ...)` |

### Tests nuevos

- `tests/test_h10_runcontroller_atomic_integration.py`: 3 tests con
  fault injection sobre `Storage._insert_event_in_tx`. Verifican que
  al fallar el INSERT del evento, la mutación de estado rollbackea.

### Compatibilidad

- `632 passed, 1 skipped in 134.17s` (cifra del log
  `audits/cleanroom-evidence/ci-output-v0.7.2.txt`; skip en
  `test_cli_uat.py:363`, preexistente). Aritmética aproximada del
  slice: 630 originales + 2-3 nuevos de integración
  (`test_h10_runcontroller_atomic_integration.py` aporta 3).
- 16/16 UAT PASS reproducible.
- 0 breaking changes: APIs públicas no cambian.

### Evidencia

- `audits/release-v0.7.2-summary.md` (ya generado, link al bundle).
- `audits/cleanroom-evidence/skillgraph-v0.7.2-audit-bundle.tar.gz`.
- `audits/cleanroom-evidence/ci-output-v0.7.2.txt`.
- `audits/cleanroom-evidence/uat-audit-v0.7.2.txt`.

### Lo que sigue abierto al cerrar v0.7.2

- **LIMITACIÓN-7**: el `with self._conn:` del Storage y las APIs
  no-atómicas legacy siguen sin rollbackear en
  `isolation_level=None`. v0.7.2 NO introduce un fix para esa
  grieta; solo acredita la integración del runtime con las APIs
  atómicas ya introducidas en v0.7.1.

## [0.8.0] — 2026-09-24 (sin tag, sin push; pendiente de autorización)

**Tag**: no asignado (espera autorización del operador).
**Código efectivo**: commit `528940297ec5ff981f0f59401fdb1e3f563236ab`
("feat(runtime): contexto de run accesible en Handoff (slice H9)").

**Resumen**: el `RunController` inyecta ahora el contexto del run
(tenant/project/run_id y metadatos vigentes) en cada `Handoff`
construido, persistido y recuperado vía `platform/storage`. El
contrato de la API pública de `RunController.__init__` se amplía
con un parámetro opcional `recipe_resolver: Callable[[str],
ContextRecipe | None] | None` (default `None`). Cuando se
proporciona, el resolver reemplaza el stub histórico
`default-empty-recipe/v1`; cuando es `None`, el comportamiento
previo se preserva (cambio backward-compatible).

**SemVer**: `feat` con cambio **compatible hacia atrás** (nuevo
parámetro opcional) → MINOR (v0.8.0).

**Resultado**: 6 tests nuevos en `tests/test_h9_context_in_run.py`
PASS. Batería completa previa: 652 passed. 16/16 UAT PASS, 0 FAIL.
Cobertura mantenida.

### Cambios funcionales

- `RunController.__init__` acepta `recipe_resolver` opcional.
- `RunController._execute_one` resuelve la receta de contexto del
  nodo vía el resolver y la inyecta en `Handoff.context`.
- `Storage` añade 1 método de lectura pura:
  `fetch_run_context(*, run_id)` (devuelve metadatos vigentes del
  run para poblar Handoff en relectura).
- `Handoff` ahora carga `run_context` automáticamente desde
  Storage cuando se recupera un handoff persistido.

### Tests

- 6 tests en `tests/test_h9_context_in_run.py` (parámetro opcional,
  propagación, recuperación, persistencia, default-empty-recipe
  preservado cuando no se inyecta resolver).

## [0.7.3] — 2026-09-24

**Tag**: `v0.7.3` (987be068c7f2b6d17aa6c209489906f94a542568).

**Código efectivo**: el tag apunta al commit `6a536ac` ("T19 cubre
rollback path del _atomic REAL"), que es el último commit con
cambios de código en el camino del fix. El SHA documental
987be068 puede incluir archivos posteriores con ajustes de SHA o
cierre de lagunas procedimentales; eso no afecta el código
ejecutado.

**Resumen**: cierra **un solo caso** de la grieta transaccional de
LIMITACIÓN-7: `Storage.record_trace()`. La función realizaba 1
INSERT en `outcome_traces` + N INSERTs en `outcome_trace_links`,
pero usaba `with self._tx()` que con `isolation_level=None` NO
abría transacción real. Un fallo durante el enlace dejaba un
trace huérfano en disco sin sus enlaces.

`v0.7.3` migra `record_trace()` a `Storage._atomic()`
(BEGIN/COMMIT/ROLLBACK explícitos), garantizando que un fallo a
mitad de las 1+N sentencias rollbackea el conjunto completo.
Esto es análogo al patrón ya usado por las APIs `*_atomically`
de v0.7.1 (que cubren `node_executions` + eventos).

El inventario del slice 1 también caracterizó otras 4 funciones
multi-statement de Storage (`_migrate`, `upsert_resource`,
`add_relation`, `register_promotion`). Todas se excluyeron del
alcance del fix por idempotencia natural o porque el fallo
impide la escritura — **v0.7.3 NO las modifica**.

### Cambios funcionales

- `Storage._atomic`: helper nuevo que usa `BEGIN`/`COMMIT`/`ROLLBACK`
  explícitos sobre `_conn` (alineado con el patrón de las APIs
  `*_atomically`). El rollback se ejecuta con `contextlib.suppress`
  para no enmascarar la excepción original.
- `Storage.record_trace`: cambia `with self._tx()` por
  `with self._atomic()` y actualiza su docstring para documentar
  la garantía transaccional y la referencia al slice V4.

### Tests

- `tests/test_h9_limitacion_7_slice1.py` con 4 tests (T15-T18):
  caracterización de V1, V2, V3, V5 y demostración del bug V4.
- `tests/test_h9_limitacion_7_slice1.py::TestT19AtomicRealRollbackPath`:
  cubre el path real de rollback del `_atomic`, no solo el override
  de los tests de caracterización. (Líneas 387-393 de storage.py
  antes en Missing; pasan a estar cubiertas con cobertura de
  storage.py subiendo de 95% a 96%.)

### Compatibilidad

**Resultados observados en el clon del SHA `6a536ac`** (no en
HEAD del main, que ya incluye el fix V6 en `a6bb5ab`):

- **Pytest contra el código del tag**: `637 passed, 1 skipped`
  en 122 s. (Skip preexistente: `tests/test_cli_uat.py:363`,
  blueprint no versionado.)
- **`bash scripts/ci.sh` completo**: EXIT 1. Aborta en el
  **gate 1 (ruff format --check)** sobre `tests/test_h9_limitacion_7_slice1.py`
  (archivo con T19, mezcla `with pytest.raises(...)` con `with s._atomic()...`).
  `ruff check src tests` reporta además 1 error **SIM117** en
  el mismo T19. Estado heredado del árbol del tag, no regresión
  del fix V4.
- **`python tests/uat_audit.py`** (modo lectura):
  `PASS=16 FAIL=0 BLOCKED=0`.
- 7 de 16 UATs se reejecutan contra el código del tag
  (UAT-05/08/09/10/11/15/16). Los 9 restantes son anclas estables
  cuyo PASS refleja commits previos.
- Cobertura `storage.py`: 96% (subió de 95% al añadir T19).
- 0 breaking changes: APIs públicas no cambian.

**Lo que este release NO certifica para el run de CI**:

El gate oficial `bash scripts/ci.sh` falla por formato/lint en
T19 en el código del tag. Esto es una característica del propio
árbol del tag. Si se requiere CI verde para una revisión posterior
que contenga V6 (commit `a6bb5ab`), hay que arreglar formato y
lint en un commit `chore(...)` separado, no modificar el SHA del
tag v0.7.3.

### Evidencia

- `audits/release-v0.7.3-summary.md` (entregado en este slice).
- `audits/cleanroom-evidence/skillgraph-v0.7.3-audit-bundle.tar.gz`
  (pendiente, ver matriz de cierre).
- `audits/cleanroom-evidence/ci-output-v0.7.3.txt` (pendiente).
- `audits/cleanroom-evidence/uat-audit-v0.7.3.txt` (pendiente).

### Lo que v0.7.3 NO cierra (sigue abierto)

- **LIMITACIÓN-7 V6**: `Storage.record_claim()` con `evidence_ids`
  pobladas presenta la misma clase de confirmación parcial que V4
  antes del fix. La corrección se ejecuta en commit posterior al
  tag (`a6bb5ab fix(storage): make record_claim evidence links
  atomic`), con su prueba focal T20
  (`tests/test_h9_limitacion_7_v6_record_claim.py`).
  Esta corrección NO está incluida en `v0.7.3` ni será parte de
  ese tag. La version que la incluya se decidirá después del
  cierre del slice documental.

- **`workflow_runs` ↔ `RunCreated` / `RunCompleted`**: las
  mutaciones de `workflow_runs` siguen usando APIs no-atómicas.
  Fuera del alcance de LIMITACIÓN-7; pertenece al Plan C.

- **APIs legacy no-atómicas de Storage** (`upsert_resource`,
  `start_node_execution` sin sufijo, `complete_node_execution`
  sin sufijo, `mark_node_failed` sin sufijo): siguen sin
  rollbackear en `isolation_level=None`. Cualquier llamada a esas
  APIs desde un caller distinto al runtime verificado en v0.7.2
  es responsabilidad del caller asegurar atomicidad externa.

## [0.6.0] — 2026-09-23

**Resumen**: cierra los dos únicos gaps restantes del blueprint v1.
**H6 multiprosito** aníade declaracion de tipos extensibles via Domain
Pack (Character/StoryArc como ejemplo narrativo) SIN tocar el nucleo.
**H7 promocion entre bases** aníade outbox persistente con aplicacion
idempotente y reconciliacion tras interrupcion.

**Resultado neto**: 16/16 UAT PASS, 0 FAIL, 0 BLOCKED. El blueprint
queda COMPLETO al 100% segun contrato.

Sin cambios en la API publica existente. Registry/bricks/parser
intactos (0 LoC modificados). Storage.py solo EXTENSION (anade tabla
promotion_outbox + 6 metodos; nada existente modificado).

### Features (MINOR bump)

- `1722fa5` **feat(h6): multiprosito - Domain Pack declara tipos extensibles**.
  - Modulo nuevo `src/skillgraph/pack_loader.py` (215 LoC):
    - `declare_types_from_pack(pack_text)`: parsea un Domain Pack
      Markdown+frontmatter y emite tipos en RuntimeType registry.
      **NO ejecuta codigo del pack**: la seguridad viene del schema
      declarativo (required + fields + refs), no de imports dinamicos.
    - `validate_instance_against_registry(instance)`: valida una
      instancia contra los tipos declarados del Domain Pack.
    - `_make_schema_validator()`: helper que construye un
      SpecValidator desde un schema declarativo.
  - Fixture `tests/fixtures/packs/narrative-core.md`: Domain Pack
    narrativo con `Character` (name, archetype, backstory, relations)
    y `StoryArc` (title, premise, acts, characters).
  - Proteccion contra shadowing:
    - Tipos core (`DecisionNode`, `ActionNode`, `DomainPack`) no se
      pueden redefinir desde un pack.
    - Namespaces reservados (`core`, `skillgraph`) se rechazan.
  - **Kernel intacto**: 0 LoC modificados en `registry.py`/`bricks.py`/`parser.py`.
- `95a0ca9` **feat(h7): promocion entre bases - outbox + reconciliacion idempotente**.
  - Modulo nuevo `src/skillgraph/promotion.py` (160 LoC):
    - `submit_proposal()`: inserta propuesta en outbox origen con
      `idempotency_key`. Duplicado -> `IdentityConflictError`.
    - `apply_proposal(proposal_id, apply_fn)`: transiciona
      PENDING/IN_PROGRESS -> PUBLISHED. **Idempotente**: si ya
      PUBLISHED, NO reaplica. Si FAILED, NO reintenta (segun contrato:
      requiere inspeccion manual).
    - `reconcile_pending()`: procesa TODAS las propuestas en
      PENDING/IN_PROGRESS. Aplica idempotencia. Publicadas y fallidas
      se ignoran.
    - `_compute_idempotency_key()`: combinacion deterministica de
      `project_id + reference_signature`. Rechaza inputs vacios.
  - Storage extension (`src/skillgraph/storage.py`, +146 LoC, 0 modificados):
    - Schema: tabla `promotion_outbox` con
      `proposal_id` PK, `idempotency_key` UNIQUE, `status` CHECK
      IN (`PENDING`,`IN_PROGRESS`,`PUBLISHED`,`FAILED`), `attempts`,
      timestamps, indice por status.
    - 6 metodos anadidos: `register_promotion`, `get_promotion`,
      `list_pending_promotions`, `mark_promotion_in_progress`,
      `mark_promotion_published`, `mark_promotion_failed`.
  - Patron del blueprint §9 (Outbox + Reconciliacion):
    1. Resultado persistido en origen (`register_promotion`).
    2. Mensaje de outbox (`promotion_outbox` row).
    3. Aplicacion idempotente en destino (`apply_fn` + `idempotency_key`).
    4. Confirmacion (`mark_promotion_published`).
    5. Reconciliacion si se interrumpe el proceso (`reconcile_pending`).
- `92cff48` **feat(uat)**: UAT-12 y UAT-13 ahora PASS con evidencia real.
  - `tests/uat-evidence/UAT-12.json` migrado BLOCKED → PASS:
    revision=95a0ca9, criteria_observed con 12 tests de
    test_h6_multiproposito.py, design_decisions (no_execution,
    schema_validator, shadowing_protection, explicit_imports).
  - `tests/uat-evidence/UAT-13.json` migrado BLOCKED → PASS:
    revision=95a0ca9, criteria_observed con 16 tests de
    test_h7_promocion.py incluyendo el CASO CRITICO
    `reconcile_after_interruption_completes_pending` (IN_PROGRESS
    dejado por crash → reconciliacion completa sin duplicar,
    apply_fn llamado 1 sola vez por propuesta).
  - `tests/test_uat_blocked.py` invertido: antes validaba que UAT-12/13
    siguieran BLOCKED con razon honesta. Ahora valida que UAT-12/13
    estan PASS, que las evidencias JSON dicen PASS con SHA real, y que
    los tests reales (`test_h6_*` / `test_h7_*`) corren verde.
    Contrato invertido: este modulo es el "gap test" que detecta si
    alguien revierte H6 o H7 sin actualizar la evidencia.
    6 tests: 2 evidencias PASS, 2 ejecutan suites reales, 2 modulos
    existen con API esperada.

### Tests anadidos (sin bump)

- `1722fa5` **test(h6)**: 12 tests focalizados en pack_loader.py.
  - `test_pack_loader_declares_types_from_narrative_pack`: pack
    narrativo declara Character/StoryArc desde YAML.
  - `test_pack_loader_valid_character_passes` /
    `test_pack_loader_valid_storyarc_passes`: instancias validas
    se aceptan (name, archetype, backstory, relations).
  - `test_pack_loader_character_missing_archetype_fails` /
    `test_pack_loader_storyarc_missing_premise_fails`: campo
    requerido ausente → error de validacion.
  - `test_pack_loader_unknown_kind_raises`: kind desconocido →
    `UnknownKindError`.
  - `test_pack_loader_cannot_shadow_core_type`: 'Character' no
    puede redefinir DecisionNode/ActionNode/DomainPack.
  - `test_pack_loader_cannot_use_reserved_namespace`: namespaces
    'core'/'skillgraph' rechazados.
  - `test_pack_loader_rejects_non_domain_pack`: doc sin
    frontmatter Domain Pack → error.
  - `test_pack_loader_field_type_mismatch_fails`: tipo de campo
    invalido → error.
  - `test_pack_loader_list_of_field_validates_elements`: list_of
    valida elementos internos.
  - `test_pack_loader_does_not_touch_kernel_modules`: pack_loader
    NO importa registry/bricks/parser (test de regresion).
- `95a0ca9` **test(h7)**: 16 tests focalizados en promotion.py +
  storage outbox.
  - `TestPromotionIdempotencyKey` (3): combinacion project+ref
    deterministica, inputs distintos producen keys distintas,
    inputs vacios rechazados.
  - `TestSubmitProposal` (2): submit crea PENDING, duplicate con
    misma idempotency_key → `IdentityConflictError`.
  - `TestApplyProposal` (6): apply exitoso→PUBLISHED, apply
    failed→FAILED, excepcion→FAILED, idempotencia sobre PUBLISHED
    (counter apply_fn no incrementa), FAILED no se reintenta,
    proposal_id inexistente → KeyError.
  - `TestReconcilePending` (5): empty→empty, procesa multiples
    PENDING, **CASO CRITICO after-interruption** (IN_PROGRESS dejado
    por crash → completa sin duplicar), no duplica PUBLISHED,
    mezcla PENDING+IN_PROGRESS+FAILED → cada uno se trata
    segun corresponde.
- `92cff48` **test(uat)**: 6 tests en `tests/test_uat_blocked.py`
  (inversion del contrato, ver feat anterior).

### Estado verificable al tag

- **HEAD**: `92cff48` (post-commits h6+h7+uat).
- **Tests**: 405 passed en 121s (373 → 405, delta +32 tests
  H6+H7+gap-invertidos).
- **UATs**: **16/16 PASS, 0 FAIL, 0 BLOCKED** — primera vez en la
  historia del proyecto.
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.
- **Audit CLI**: `python tests/uat_audit.py` reporta 16/16 PASS.

### Limitaciones y deudas conocidas

- **H6/H7 sin CLI hooks publicos**: `sg pack load` y
  `sg promotion submit/list/reconcile` NO son comandos CLI. El
  contrato del blueprint es la API Python (pack_loader.declare_*,
  promotion.submit/apply/reconcile). La interfaz CLI es una mejora
  diferible, no un gap funcional.
- **Sin migracion de evidencias legacy**: las evidencias que vivian
  con status=BLOCKED y revision=`cb7e3482` (v0.3.0) se migraron
  sobreescribiendo el archivo a status=PASS con la revision real del
  commit que implemento la feature. Si alguien quiere preservar el
  historial pre-implementacion, mirar git log de tests/uat-evidence/.

## [0.5.0] — 2026-09-23

**Resumen**: añade CLI propio al módulo `tests/uat_audit.py`. Antes
ejecutaba los 16 UATs y sobreescribía la evidencia persistida por
defecto (footgun crítico). Ahora es read-only por defecto; el modo
write es opt-in con flags explícitos y protección contra pisado de
evidencia válida de UATs stub.

Sin cambios en la API pública de SkillGraph. Sin cambios en código
de producción (`src/skillgraph/`).

### Features (MINOR bump)

- `233431b` **feat(uat)**: CLI safety en `tests/uat_audit.py`.
  - **Default read-only**: `python tests/uat_audit.py` ahora LEE la
    evidencia persistida y la reporta sin ejecutar nada. Cierra el
    footgun documentado en v0.4.1 CHANGELOG.
  - **`--write`**: ejecuta los UATs y SOBREESCRIBE la evidencia. Solo
    para UATs no-stub (los stubs UAT-08/09/12/13 son heredados y
    delegan en `uats_blocked_gap`; su evidencia real vive en
    `test_h4_expansion_cli.py` / `test_uat_blocked.py`).
  - **`--write --yes`**: confirma la operación sobre UATs stub
    (mensaje explícito + exit 3 si se omite `--yes`).
  - **`--dry-run`**: ejecuta los UATs sin persistir evidencia (útil
    para debug).
  - **Subset selection**: `uat_audit.py UAT-08 UAT-09` ejecuta solo
    los UATs nombrados.
  - **`--help`**: imprime uso.
  - **Exit codes**: 0 OK, 2 UAT desconocido, 3 stub sin `--yes`.
  - Refactor: extrae `_run_one`, `_report`, `_summary`,
    `_read_existing`, `_build_parser` para DRY.

### Tests añadidos (sin bump)

- `607d859` **test(uat)**: 5 tests para el nuevo CLI.
  - `test_main_default_is_readonly`: modo lectura no escribe nada.
  - `test_main_write_unknown_uat_returns_2`: exit code 2 en UAT
    desconocido.
  - `test_main_write_stub_without_yes_returns_3`: exit code 3 Y la
    evidencia preexistente con `revision: "must-survive"` queda
    intacta (verifica que NO se pisa).
  - `test_main_dry_run_does_not_write`: `--dry-run` no persiste.
  - `test_main_help_exits_zero`: `--help` sale rc=0 con mensaje
    que contiene `--write`.

### Estado verificable al tag

- **HEAD pre-tag**: `607d859`.
- **Tests**: 373 passed en 82s (368 → 373, delta +5 tests CLI).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.
- **Footgun verificado**: ejecutar `python tests/uat_audit.py` ya NO
  modifica el working tree (verificado con `git status` antes/después).

### Limitaciones y deudas conocidas (sin cambio desde v0.4.1)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.
- `paths.py` rama Windows: no testeable en CI Linux.

## [0.4.1] — 2026-09-23

**Resumen**: dos correcciones de portabilidad y trazabilidad del
módulo `tests/uat_audit.py`. Sin cambios de comportamiento observable
ni en la API pública.

### Fixes (PATCH bump)

- `7b81df7` **fix(tests)**: UAT evidence usa SHA real de HEAD.
  - Antes: `revision: "HEAD"` literal en evidencia de UAT-08/09.
  - Ahora: helper `_git_rev_head()` que ejecuta `git rev-parse HEAD`
    en el repo de evidencia y captura el SHA real.
  - Justificación: una evidencia de auditoría que no contiene el SHA
    real no es auditable. Mejora la verificabilidad, no el comportamiento.
- `edb19b0` **fix(uat)**: `REPO_ROOT` se deriva de `__file__`.
  - Antes: `Path("/var/mnt/DiscoChino2-fast/...")` hardcodeado,
    rompía el módulo al clonarse en otra máquina o ruta.
  - Ahora: `Path(__file__).resolve().parent.parent` — funciona en
    cualquier checkout sin editar.
  - Verificado: módulo importa OK desde `test_uat_blocked.py` y
    `test_uat_audit.py`, y resuelve a la misma raíz que el path
    hardcodeado en este entorno.

### Estado verificable al tag

- **HEAD pre-tag**: `edb19b0`.
- **Tests**: 368 passed en 63s (sin delta vs v0.4.0).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.4.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.
- `paths.py` rama Windows: no testeable en CI Linux.
- **NUEVA detectada en sesión**: el `main()` de `tests/uat_audit.py`
  es destructivo por defecto — al ejecutarlo sin args pisa toda la
  evidencia existente en `tests/uat-evidence/*.json` con `BLOCKED`.
  No se ha arreglado en este PATCH por estar fuera del scope
  (cambia contrato del script, no portabilidad).

## [0.4.0] — 2026-09-23

**Resumen**: cierra el gap declarado en `specs/h4-slice-3.md` limitación 3.
`expansion apply` ahora persiste la propuesta y crea marker `.applied`,
haciendo que `list --stage APPLIED` funcione (antes retornaba vacío).
`expansion show` ahora incluye el campo `stage` en el payload JSON.

Compatibilidad hacia atrás mantenida: ningún cambio en códigos de salida,
firmas de comandos, ni en el formato del plan persistido.

### Features (MINOR bump)

- `162a708` **feat(h4-slice-3)**: APPLIED marker + `show.stage` field.
  - `cmd_expansion_apply` ahora persiste la propuesta en
    `expansion_proposals/<id>.json` (si no existe, mismo patrón que
    `cmd_expansion_propose`) y crea marker adyacente `<id>.json.applied`
    con timestamp UTC y `applied_by: "expansion-apply-cli"`.
  - `cmd_expansion_list` y `cmd_expansion_show` leen markers:
    precedencia `ARCHIVED > APPLIED > REJECTED > PROPOSED`.
  - `cmd_expansion_show` añade `"stage": "..."` al payload JSON.
  - Refactor: extrae `_infer_proposal_stage()` y
    `_collect_rejection_ids()` para evitar duplicación entre list y show.

### Estado verificable al tag

- **HEAD**: `162a708` (pre-tag).
- **Tests**: 368 passed en 117s (362 → 368, delta +6 tests focales).
- **Cobertura**: sin cambio material (cli.py 31% in-process; tests
  reales E2E).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos (sin cambio).
- **`scripts/ci.sh`**: OK.
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas (sin cambio desde v0.3.0)

- UAT-12 H6 multipropósito: BLOCKED.
- UAT-13 H7 promoción: BLOCKED.
- H4 slice-4 deferred.

## [0.3.0] — 2026-09-23

**Resumen**: primera release taggeada. H0-H5 (excepto H6 y H7)
completados con criterios de aceptación verificados. 14/16 UAT PASS,
2 BLOCKED honestos por falta de spec del operador.

### Features (MINOR bump)

#### H4 — Expansión controlada

- `6f93eb2` **feat(h4)**: Expansion controlada (DISCOVER → APPLY)
  cierra UAT-08/09.
- `bd95d29` **feat(h4-cli)**: expansion propose/apply/validate/rejections
  + E2E para UAT-08/09.
- `3b307f3` **feat(h4-slice-3)**: policy engine P1..P5 + EVALUATE + CLI
  list/show/archive.
- `b7b2d5e` **feat(h4)**: DecisionNode outcomes + max_visits self-loops
  (+7 tests).

Criterio legal HITOS.md H4: "Añadir una investigación imprevista a una
ejecución sin alterar el resultado de nodos anteriores."
- UAT-08 PASS (`tests/uat-evidence/UAT-08.json`): apply incorpora
  únicamente el cambio solicitado; nodos originales intactos.
- UAT-09 PASS (`tests/uat-evidence/UAT-09.json`): propuesta con
  capability no registrada es rechazada con rc=10 y evidencia JSON
  persistida en `expansion_rejections/`.

Limitaciones documentadas (`specs/h4-audit-penal.md`):
- E2E es `representative` (Storage SQLite local), no
  `acceptance_aligned` (sin stress concurrente, sin crash recovery
  verificado en kill-9). Refinamiento pendiente para slice-4.

#### H5 — Adopción de skills

- `26ac401` **feat(h5)**: skill_import (UAT-11 BLOCKED→PASS) +
  `skill_importer` + `cmd pack import`.

Criterio legal HITOS.md H5: "Adoptar una skill real y conservar una
referencia verificable a sus instrucciones originales."
- UAT-11 PASS (`tests/uat-evidence/UAT-11.json`): `pack_import` rc=0,
  `structured_ok=True`, `script_ignored=True`, `scripts_detected=True`.

Decisión documentada (`specs/h5-source-conservation-decision.md`):
- Conservación por referencia (path+content_hash), NO duplicación de
  bytes. Justificado por blueprint §10 §5-6.

#### Otros feats

- `d72bbff` **feat(uat)**: UAT-16 BLOCKED→PASS (handoff_json persiste
  tras revision change).
- `b06cc15` **feat(h3-s1)**: Knowledge ADT + Storage delta.
- `4d8e80c` **feat(ci)**: `scripts/ci.sh` como gate único + pairwise
  import.
- `3bc66d9` **feat(H2)**: tests subprocess CLI run + resume-or-start
  (UAT-04/06/07 E2E).
- `007db8d` **feat(cli)**: añadir `__main__.py` para `python -m
  skillgraph`.
- `a3f7950` **feat(etapa2/S7)**: DSL tipado + PlanBuilder funcional +
  loader Markdown.
- `e763102` **feat(e2-s4+s5)**: WorkflowPlan + RunController +
  ejecución recuperable.
- `92a5174` **feat(e2-s3)**: AgentAdapter + FakeAgentAdapter +
  RecordingAdapter.
- `64bc05d` **feat(e2-s2)**: Handoff materializado con serialización
  estable y SHA-256.
- `92929a9` **feat(e2-s1)**: runtime append-only + EventLog con
  idempotencia por UNIQUE.
- `fb0e56a` **feat(e1)**: CLI real + catálogo + UAT-01..03 PASS.
- `15957d7` **feat(s1)**: almacenamiento SQLite con WAL, aislamiento y
  latencia.
- `0a92c84` **feat(s0)**: brick mínimo Markdown+YAML con parser,
  registro y validación.

### Fixes (PATCH bump)

- `ff433aa` **fix(types)**: SourceKind incluye `skill_pack` y Source
  valida kind en `__post_init__`. Cierra bug silencioso donde
  `from __future__ import annotations` desactivaba Literal-check.
- `e69a8e4` **fix(uat)**: UAT-10 predicados válidos + chequeo
  `seed_rc` y `stale_listed`.
- `bdd196f` **fix(cli)**: UAT-06 max_iterations respeta el límite + 4
  tests honestos.

### Refactors

- `1039171` **refactor + test(paths)**: añadir tests + refactor para
  que la rama nt sea testeable.

### Tests añadidos (sin bump)

- `0e96495` **test(parser)**: 12 tests ramas de error (coverage
  77%→100%).
- `b6ca7e1` **test(plan-loader)**: 13 tests load_plan_file + error
  branches (coverage 48%→100%, dato heredado 69% obsoleto).
- `629be65` **test(recipe)**: 22 tests `__post_init__` + from_dict
  (coverage 73%→100%).
- `7c3f3f4` **test(uat)**: gap coverage UAT en CI — 5 wrappers
  pytest + 2 honest blockers.

### Specs (sin bump)

- `7233fac` spec(h4-audit-penal): cruce H4 slices 1+2 vs blueprint
  literal.
- `92d70e2` spec(h5-audit-penal): cruce H5 skill_import vs blueprint
  literal.
- `81fbb0e` spec(h4-slice-3): propuesta storage persistente + EVALUATE
  + policy engine.
- `2d01a06` spec(uat-coverage-gap): audita que UATs se validan
  automáticamente en CI.

### Estado verificable al tag

- **HEAD**: `076f6e9` (pre-tag) → `v0.3.0` (post-tag).
- **Tests**: 362 passed en 54s (315→362, delta +47 en ciclos de
  stewardship).
- **Cobertura**: 77% total. Módulos críticos `parser.py`, `plan_loader.py`,
  `recipe.py`: 100%. Módulos runtime: 88-100%. `cli.py`: 31% en
  pytest-cov (cobertura real mayor vía tests subprocess E2E no
  contables por cobertura in-process).
- **UATs**: 14/16 PASS, 2 BLOCKED honestos.
- **`scripts/ci.sh`**: OK (format + lint + pytest, replicable por
  cualquier runner externo).
- **ruff format+check**: limpios.

### Limitaciones y deudas conocidas

- **UAT-12 (H6 multipropósito)**: BLOCKED. Requiere spec del operador
  para `Character/StoryArc`.
- **UAT-13 (H7 promoción entre bases)**: BLOCKED. Requiere spec del
  operador.
- **H4 slice-4** (deferido por decisión explícita en
  `specs/h4-slice-3.md`): sin migración SQLite, sin gating de
  `auto_signed` via evaluation_result.
- **`paths.py` rama Windows**: no ejercitable en CI Linux
  (`LOCALAPPDATA/USERPROFILE`).
- **`recipes.runtime.dispositivos externos`**: tiktoken solo si H4+
  exige Adapter real.

### Antiobjetivos respetados

- No se introdujo base de grafos especializada.
- No se introdujo scheduler distribuido.
- No se introdujo sistema de agentes permanentes sin requisito
  observado.

## Comparativa con releases anteriores

Esta es la **primera release taggeada** del proyecto.
El historial completo de commits previos forma parte del cuerpo
desarrollado hacia esta release.

[0.3.0]: #030--2026-09-23

## [0.8.1] — 2026-09-24 (PATCH, refactor)

**Tag**: `v0.8.1` (`ab7b5171aec5524320c67e44ad511ae78b70a7d1`).

**Código efectivo**: commit `ab7b517` ("refactor(runtime): helper
_fail_node_with(exc=...) en RunController").

**Resumen**: el método `_execute_one` repite el patrón
`except X as exc: self._mark_node_failed(... error=f"{type(exc).__name__}: {exc}")`
en dos ramas (compilación de handoff y adaptador). Esta versión
centraliza ese formato en un helper privado `_fail_node_with(exc=...)`
que delega en `_mark_node_failed`. La tercera rama (outcome no
declarado) usa una firma distinta (incluye `outcome=`) y se conserva
como llamada directa.

**SemVer**: refactor puro → PATCH (v0.8.1). Sin cambio de
comportamiento observable.

**Resultado**: 652/652 tests PASS; 16/16 UAT PASS, 0 FAIL. Ruff
limpio. Cobertura mantenida.

### Cambios funcionales

Ninguno.

### Refactor (sin bump adicional)

- `RunController._fail_node_with(*, tenant_id, project_id, run_id,
  node_execution_id, node_name, exc)` añadido como helper privado.
- `RunController._execute_one`: 2 ramas `except` pasan a usar
  `_fail_node_with(exc=exc)` en vez de construir el string de error
  y llamar a `_mark_node_failed` directamente. La rama de outcome
  no declarado queda igual.

## [Sin bump] — 2026-09-24 (refactor interno)

**Tag**: ninguno. **Código efectivo**: commit `ea54021`
("refactor(runtime): helpers _transition_run_state_with_event y
_is_budget_exhausted").

**Resumen**: deuda técnica pendiente del refactor previo
(`v0.8.1`). `reconcile_run` tenía 122 LoC y tres ramas con el patrón
`EventBuilder(...).run_completed(...) + transition_run_state_atomically`,
más un bloque de 14 LoC para detectar budget de visitas agotado.
Esta versión extrae dos helpers privados en `RunController`:

- `_transition_run_state_with_event(*, tenant_id, project_id, run_id,
  state, current_node, at=None)`: construye el `RunCompleted` y
  llama a `transition_run_state_atomically` en una sola TX.
  Reemplaza las 3 ramas de terminación del run.
- `_is_budget_exhausted(plan, tenant_id, project_id, run_id,
  prev_current)`: detecta H4 (self-loop + max_visits + ejecuciones
  acumuladas >= max_visits).

**SemVer**: refactor puro (sin cambio de contrato público, sin fix,
sin feat). Regla "`refactor` → sin bump de versión" del CHANGELOG.
No se publica tag.

**Resultado**: 659/659 tests PASS (+4 nuevos sobre el helper).
Ruff limpio. Cobertura `runcontroller.py`: 84% → 95%
(umbral ≥90% AGENTS.md core). `reconcile_run`: 122 → 100 LoC.

### Continuación del refactor (aee5cd5)

Misma rama, sin bump adicional. Extrae dos helpers privados
adicionales en `RunController`:

- `_open_node_execution(*, tenant_id, project_id, run_id, node_name,
  attempt) -> tuple[EventBuilder, str]`: emite `NodeScheduled` y crea
  la `NodeExecution` RUNNING atómica. Devuelve `(events,
  node_execution_id)`.
- `_finalize_node_success(*, events, run_id, node_execution_id,
  result, context_hash)`: emite `NodeCompleted` + `EvidenceProduced`
  y delega el UPDATE a SUCCEEDED atómico.
- `_fail_node_with` ahora retorna `bool` (`False`); permite
  `return self._fail_node_with(...)` sin repetir el literal.

`_execute_one` colapsa 162 → 124 LoC. El orquestador queda como
secuencia explícita: bootstrap → compilar handoff → invocar adapter →
validar outcome → cerrar. Cobertura mantenida 95%.


## [0.9.0] — 2026-09-24 (MINOR, cancel + refactors)

**Tag**: `v0.9.0` (`a4d749e9fefad551e4406aa7305e32aac224df08`).

**Resumen**: S1 del roadmap Etapa 7 (presupuestos y cancelación):
el operador puede detener un Run en curso sin esperar al reconcile
completo. Nueva API `RunController.cancel_run` + nuevo subcomando
CLI `sg runs cancel <project> <run-id>`. Consolidación de los
refactors acumulados sobre `RunController` (helpers privados
para extraer las ramas duplicadas de terminación, transición de
estado y bootstrap/ejecución de nodos).

### Cambios funcionales (MINOR)

- **`RunController.cancel_run(*, tenant_id, project_id, run_id)`**:
  transiciona el Run a `CANCELLED` y emite `RunCompleted` en una
  sola TX (reutiliza `_transition_run_state_with_event`).
  - Run no existe -> `NotFoundError` (delegado en `Storage.load_run`).
  - Run ya terminal -> `ValidationError` (no idempotente).
  - NodeExecutions RUNNING se quedan: la cancelación es a nivel
    de Run, no de nodo. El siguiente `reconcile_run` no las
    re-ejecuta (test `test_reconcile_after_cancel_is_noop`).
- **CLI `sg runs cancel <project> <run-id>`**: subcomando nuevo
  bajo `runs` (paralelo a `run`). Exit code 0 + `state=CANCELLED`
  en stdout. Errores tipados -> `EXIT_DOMAIN` (10).

### Refactors acumulados (sin bump adicional)

Consolidación de la deuda técnica detectada sobre `RunController`
en `v0.8.1`:

- `RunController._transition_run_state_with_event(*, ...)`:
  helper que centraliza las 3 ramas de terminación del Run
  (FAILED por nodo, FAILED por budget exhausted, COMPLETED
  normal, ahora también CANCELLED).
- `RunController._is_budget_exhausted(plan, ...)`:
  detección de H4 (self-loop + max_visits + ejecuciones
  acumuladas >= max_visits).
- `RunController._open_node_execution(*, ...)`:
  bootstrap del nodo: emite `NodeScheduled` y crea la
  NodeExecution RUNNING atómica.
- `RunController._finalize_node_success(*, ...)`:
  cierre exitoso: emite `NodeCompleted` + `EvidenceProduced`
  y delega el UPDATE a SUCCEEDED atómico.
- `RunController._fail_node_with(*, exc=...) -> bool`:
  devuelve `False` para permitir
  `return self._fail_node_with(...)` sin literal.
- `_execute_one`: 162 → 124 LoC.
- `reconcile_run`: 122 → 100 LoC.

### Tests

- 5 tests unitarios `tests/test_runcontroller.py::TestCancelRun`:
  estado persistido, evento emitido, idempotencia, run terminal
  rechazado, reconcile post-cancel no-op, run desconocido.
- 2 tests subprocess `tests/test_cli_runs_cancel.py`:
  cancel vía CLI exit code 0 + persistencia + evento; cancel
  de run inexistente -> exit code != 0.
- 4 tests del helper `_is_budget_exhausted`
  (`tests/test_h4_cycles_and_decision.py::TestIsBudgetExhaustedHelper`).
- UAT-08/09 regenerados sobre `a4d749e`.

### Resultado

- **Batería completa**: 666 passed (de 652 en v0.8.0).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 95% (umbral ≥90% AGENTS.md core).

### SemVer

`feat` (capacidad observable nueva: cancel programático y CLI) →
**MINOR** → `v0.9.0`. Los refactors van consolidados en la
misma release con la regla "`refactor` → sin bump" relajada
porque la `feat` ya justifica MINOR.

## [0.10.0] — 2026-09-24 (MINOR, list + show runs)

**Tag**: `v0.10.0` (`c6963f072d6b6e51ab569e396de688633aed2fb2`).

**Resumen**: S2 del roadmap Etapa 7 (gestion del ciclo de vida de
Runs): complementa el S1 (`v0.9.0`, cancel_run) con inspeccion
read-only. El operador ahora puede listar Runs existentes con
`sg runs list` y ver el snapshot de un Run concreto con
`sg runs show`, sin abrir SQLite directamente.

### Cambios funcionales (MINOR)

- **`Storage.list_runs(*, tenant_id, project_id, state=None, limit=50)`**:
  SELECT con filtro opcional por estado, ordenado por `rowid DESC`
  (mas reciente primero; monotono, independiente de la resolucion
  de 1 segundo de `datetime('now')` en SQLite).
- **`Storage.get_run(*, tenant_id, project_id, run_id)`**:
  fila cruda de un Run; `NotFoundError` si no existe.
- **`RunController.list_runs(...)`**: tupla inmutable de
  `RunSnapshot` ordenados por mas reciente primero. Filtra por
  estado opcional.
- **`RunController.show_run(...)`**: snapshot de un Run por id;
  `NotFoundError` si no existe. Delega en `Storage.get_run`.
- **`RunController._count_events(...)`**: helper privado read-only
  para contar eventos de un Run (usado por list/show).
- **CLI `sg runs list <project> [--state S] [--limit N]`**:
  salida CSV-like con columnas estables (run_id, state,
  current_node, executed, events). '(sin runs)' si vacio.
- **CLI `sg runs show <project> <run-id>`**: salida key=value
  (run_id, state, current_node, executed_nodes, events_emitted).
  Parseable con `awk`/`cut`.
- **`_open_project_storage(args)`**: helper compartido por
  `cmd_runs_list`/`show`/`cancel` (DRY: resolver proyecto +
  abrir Storage en una sola funcion).

### Tests

- 6 tests unitarios `tests/test_runcontroller.py::TestListAndShowRun`:
  vacio, orden, limit, filtro por estado, snapshot, NotFoundError.
- 3 tests subprocess CLI `tests/test_cli_runs_inspect.py`:
  list vacio, list orden, show snapshot.
- Archivo renombrado: `test_cli_runs_cancel.py` ->
  `test_cli_runs_inspect.py` (cubre cancel + list + show).
- UAT-08/09 regenerados sobre `c6963f0`.

### Resultado

- **Bateria completa**: 675 passed (de 666 en v0.9.0, +9 nuevos).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 95% mantenida.

### SemVer

`feat(list_runs) + feat(show_run) + feat(sg runs list) +
feat(sg runs show)` -> **MINOR** -> `v0.10.0`. Consolidacion
inmediata con v0.9.0 porque `list`/`show` son el complemento
natural de `cancel`: sin ellos, el operador no puede saber
que Run cancelar.

## [0.11.0] — 2026-09-24 (MINOR, logs run)

**Tag**: `v0.11.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S3 del roadmap Etapa 7. Cierra el triangulo de
inspeccion read-only de Runs: tras listar (`v0.10.0`) y snapshotear
(`v0.10.0`), el operador puede ahora examinar el timeline completo
de eventos de un Run con `sg runs logs`. Read-only, sin emitir
eventos.

### Cambios funcionales (MINOR)

- **`Storage.list_events_for_run(*, tenant_id, project_id, run_id)`**:
  SELECT ordenado por `sequence ASC` (orden causal) filtrado por
  run_id usando el indice `events_by_run` ya existente. Devuelve
  tupla de tuplas crudas `(sequence, event_id, kind, timestamp,
  payload_json)`; el parsing a `RuntimeEvent` vive en `RunController`
  para mantener Storage libre de tipos del bounded context `runtime`.
- **`RuntimeEventLog`**: nuevo dataclass frozen
  `(sequence: int, event: RuntimeEvent)` que expone `sequence` al
  exterior sin modificar el contrato del evento runtime (sequence
  es meta-informacion de almacenamiento, no del evento en si).
- **`RunController.logs_run(*, tenant_id, project_id, run_id)`**:
  fail-fast con `get_run` (NotFoundError si no existe). Itera
  `_row_to_event_dict` sobre cada row y lo envuelve en
  `RuntimeEventLog(sequence, event)`. No emite eventos.
- **CLI `sg runs logs <project> <run-id> [--limit N]`**: salida
  CSV-like con cabecera (`seq event_kind timestamp payload`) y una
  linea por evento con resumen del payload (primer nivel
  `clave=valor` truncado a 40 chars). '--limit N' corta por cabeza
  despues de cargar todo (util para depurar los primeros N eventos
  de Runs largos). '(sin eventos)' si vacio.
- **`_route_runs`**: nueva rama `logs -> cmd_runs_logs`.
- **Reuso**: `cmd_runs_logs` delega en `_open_project_storage`
  (mismo helper DRY que list/show/cancel).

### Tests

- 3 tests unitarios `tests/test_runcontroller.py::TestLogsRun`:
  NotFoundError, RunCreated presente, RuntimeEventLog expone
  sequence + RuntimeEvent.
- 2 tests subprocess CLI `tests/test_cli_runs_inspect.py`:
  `test_logs_run_via_cli_outputs_event_timeline` (cabecera +
  1 linea RunCreated con payload resumido) y
  `test_logs_run_via_cli_unknown_run_returns_error` (exit 10).
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 680 passed (de 675 en v0.10.0, +5 nuevos:
  3 unit + 2 subprocess).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 96% (sube de 95% a 96%).

### SemVer

`feat(logs_run) + feat(sg runs logs)` -> **MINOR** -> `v0.11.0`.
Consolidacion inmediata con v0.10.0 porque `logs` es el
complemento natural de `list`/`show`: sin timeline, el operador
no puede diagnosticar por que un Run fallo o se cancelo.

## [0.12.0] — 2026-09-24 (MINOR, budgets)

**Tag**: `v0.12.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S4 del roadmap Etapa 7 (presupuestos opt-in por Run).
Cierra el riesgo principal que dejo el H4: un Run con self-loop y
sin limite superior puede iterar eternamente, consumiendo disco y
tiempo de computo sin abortar. Con S4, el operador puede poner
limites explicitos al crear el Run y el controller abortara
automaticamente cuando se alcancen, emitiendo un evento
`BudgetExceeded` que aparece en `sg runs logs`.

### Cambios funcionales (MINOR)

- **`EVENT_KINDS`** (`engine.py`): nuevo valor canonico
  `"BudgetExceeded"` (event_kind del runtime, NO categoria).
- **`EventBuilder.budget_exceeded(*, run_id, kind, limit, observed)`**:
  smart constructor con validacion: `kind` debe estar en
  `{visits, runtime, events}`. Payload: `{kind, limit, observed}`.
- **`RunBudget`** (dataclass frozen en `runcontroller.py`):
  `max_visits`, `max_runtime_seconds`, `max_events` (todos
  `Optional[int]`). Validacion `__post_init__`: no negativos,
  si se da debe ser > 0. `is_active` True si alguno definido.
- **`Storage.run_budgets`**: nueva tabla con PK `run_id` (FK
  logica a `workflow_runs`). Columnas `max_visits`,
  `max_runtime_seconds`, `max_events`, `inserted_at`.
  Migracion idempotente en `_migrate` (CREATE TABLE IF NOT EXISTS).
- **`Storage.upsert_budget(...)`**: INSERT OR REPLACE sobre la PK.
  Idempotente (cumple UAT-07).
- **`Storage.get_budget(...)`**: devuelve fila cruda o `None`
  (no lanza NotFoundError: ausencia = sin limites, compat con
  Runs anteriores a S4).
- **`RunController.create_run(..., budget=None)`**: parametro
  opcional. Si `budget is not None AND budget.is_active`,
  persiste via `upsert_budget`. Budget inactivo (todos None) o
  `None` = no escribe fila = semantica "sin limites" (compat).
- **`RunController._is_budget_exhausted`**: extendido (H4 + S4).
  Chequea 3 limites: (1) H4 original self-loop+max_visits por
  nodo, (2) Run.max_visits global, (3) Run.max_events global.
  Cuando (2) o (3) falla, emite `BudgetExceeded` antes de
  devolver True (asi el timeline del Run muestra POR QUE aborto).
- **`RunController._execute_one`**: invoca el check al inicio;
  si budget agotado, devuelve `False` (FAILED) sin tocar el
  nodo. El caller (`reconcile_run`) cierra el Run en FAILED
  via `_transition_run_state_with_event`.
- **`RunController._count_events`**: refactor menor — ahora
  delega en `Storage.list_events_for_run` (regla "Storage
  encapsula SQL"; antes tocaba `self._storage._conn` directo).
- **CLI `sg run ... --budget-visits N --budget-runtime-seconds N
  --budget-events N`**: parametros nuevos en el subcomando `run`.
  Si se da al menos uno, se construye `RunBudget` y se persiste.
- **CLI `sg runs budget <project> <run-id>`**: subcomando nuevo.
  Muestra el budget activo (key=value parseable) o `(sin budget)`.
  Run desconocido -> exit 10 (EXIT_DOMAIN).

### Tests

- 5 unit `TestRunBudgetDataclass`: defaults, valores positivos,
  negativos, cero, `is_active`.
- 4 unit `TestStorageBudget`: round-trip, nones, ausente, idempotencia.
- 3 unit `TestCreateRunWithBudget`: budget persistido, sin budget,
  budget inactivo.
- 2 unit `TestBudgetEnforcement`: self-loop+max_visits=1 emite
  BudgetExceeded; plan lineal sin budget no se aborta.
- 2 unit `TestBudgetKindValidation`: smart ctor rechaza kind invalido.
- 3 subprocess CLI `TestRunsBudgetCli`: `(sin budget)`,
  key=value, run desconocido -> exit 10.
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 700 passed (de 680 en v0.11.0, +20 nuevos).
- **Ruff**: limpio.
- **Cobertura `runcontroller.py`**: 88% (baja de 96% por las
  nuevas lineas de S4 que no todos los tests ejercitan — el
  chequeo de `max_runtime_seconds` queda documentado como
  reservado y sera cubierto en S5 cuando se conecte a un
  reloj inyectable; el de `max_events` ya esta cubierto por
  enforcement del primer test).

### SemVer

`feat(RunBudget) + feat(BudgetExceeded) + feat(upsert_budget) +
feat(get_budget) + feat(sg runs budget) + feat(sg run --budget-*)`
-> **MINOR** -> `v0.12.0`. Consolidacion inmediata con v0.11.0
porque budgets son **complemento directo** del timeline:
`sg runs logs` (v0.11.0) muestra los eventos; sin budgets, no
hay forma de abortar Runs problematicos antes de que el operador
vea el timeline. La regla "evita micro-releases triviales" se
respeta: budgets son 3 `feat` coherentes (modelo, persistencia,
CLI) con enforce end-to-end probado.

## [0.13.0] — 2026-09-24 (MINOR, redaction policies)

**Tag**: `v0.13.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S5 del roadmap Etapa 7 (politicas de redaccion por
tenant). Cierra el vector de exfiltracion que dejo el modelo de
eventos: hasta v0.12.0, cualquier payload de evento (que puede
contener API keys, tokens, paths de workspace) se persistia integro
en `runtime_events.payload_json`. Con S5, el operador configura una
politica por tenant (`none` | `metadata` | `payload` | `full`) y
el `EventLog` redacta automaticamente antes de persistir.

### Cambios funcionales (MINOR)

- **`runtime.redaction`** (modulo nuevo):
  - `RedactionPolicy = Literal["none", "metadata", "payload", "full"]`.
  - `validate_policy(policy)`: smart constructor; `ValidationError`
    si la politica no esta en el conjunto canonico.
  - `redact_payload(payload, policy)`: funcion pura (no I/O,
    no reloj, determinista). Implementa las 4 politicas:
    - `none`: copia superficial (compat con pre-S5).
    - `metadata`: conserva claves, valores -> `[REDACTED]`.
    - `payload`: redaccion recursiva (escalares `[REDACTED]`,
      colecciones conservadas en forma).
    - `full`: devuelve `{}` (descarta todo el payload).
  - `REDACTED_MARKER: Final[str] = "[REDACTED]"`: constante
    publica para UIs que quieran detectar y formatear.
- **`Storage.tenant_policies`**: nueva tabla con PK `tenant_id`.
  Columnas: `redaction_policy TEXT NOT NULL DEFAULT 'none'`,
  `updated_at`.
- **`Storage.get_policy(*, tenant_id)`**: devuelve la politica
  configurada o `None` (sin fila = sin limite = default `none`).
- **`Storage.upsert_policy(*, tenant_id, policy)`**: INSERT OR
  REPLACE idempotente sobre la PK. Storage NO valida la politica;
  la validacion vive en `runtime.redaction` (regla "Storage
  encapsula SQL, no reglas de negocio").
- **`EventLog.__init__(conn, *, policy_resolver=None)`**: nuevo
  parametro opcional. `policy_resolver` es un `Callable[[str],
  str | None]` que, dado un `tenant_id`, devuelve la politica
  efectiva. Sin resolver -> default `none` (compat con pre-S5).
- **`EventLog._resolve_policy(tenant_id)`**: helper privado.
  Sin resolver -> `"none"`. Resolver devuelve None -> `"none"`.
  Resolver devuelve valor -> se aplica tal cual.
- **`EventLog.append`**: si hay policy_resolver configurado,
  el payload se redacta ANTES de serializar a `payload_json`.
  El `RuntimeEvent` original NO se muta (es frozen). Asi `logs_run`
  sigue viendo el evento ORIGINAL; en disco solo aparece la
  version redactada.
- **`RunController.__init__`**: inyecta un policy_resolver que
  delega en `Storage.get_policy` (regla "Storage encapsula SQL").
- **CLI `sg policy get <project>`**: imprime la politica efectiva
  del tenant. Default `none` si no hay fila.
- **CLI `sg policy set <project> --redact-policy X`**: persiste
  la politica. Choices validadas via argparse: `none|metadata|payload|full`.
- **`_route_policy`**: dispatcher para `policy get|set`.

### Politica default

Sin politica configurada para un tenant, el `EventLog` aplica
`"none"` (passthrough). Esto preserva el comportamiento de
v0.12.0 y anteriores: los Runs creados antes de S5 siguen
persistiendo payloads integros. La redaccion es **opt-in** por
tenant. Migrar un tenant a redaccion requiere ejecutar
`sg policy set <project> --redact-policy <X>`.

### Tests

- 14 unit `test_redaction.py`: validate_policy (2) + none (2) +
  metadata (2) + full (2) + payload (3) + pureza (2) + type (1).
- 3 unit `TestStoragePolicyPersistence`: round-trip, ausente,
  idempotencia.
- 4 unit `TestEventLogRedaction`: resolver=metadata redacta,
  default=none passthrough, resolver=payload recursivo,
  resolver=none passthrough.
- 4 subprocess CLI `test_cli_policy.py`: get sin policy,
  set+get round-trip, set invalido -> exit != 0, persistencia SQL.
- UAT-08/09 regenerados (solo campo `revision` actualizado).

### Resultado

- **Bateria completa**: 725 passed (de 700 en v0.12.0, +25 nuevos).
- **Ruff**: limpio.
- **Cobertura `redaction.py`**: **100%** (modulo nuevo puro).
- **Cobertura `runcontroller.py`**: 88% (sin cambios: las lineas
  nuevas de S4 siguen sin cubrir `max_runtime_seconds`, que se
  conectara a un reloj inyectable en una iteracion futura).

### SemVer

`feat(redaction) + feat(EventLog.policy_resolver) +
feat(tenant_policies) + feat(sg policy get/set)` -> **MINOR**
-> `v0.13.0`. Consolidacion inmediata con v0.12.0 porque la
redaccion es **complemento directo** del modelo de eventos:
v0.12.0 emita eventos con secretos potenciales; sin S5, esos
secretos iban a disco. La regla "evita micro-releases triviales"
se respeta porque S5 son 4 `feat` coherentes (modelo, persistencia,
integracion EventLog, CLI).

## [0.14.0] — 2026-09-24 (MINOR, locks concurrentes por run)

**Tag**: `v0.14.0` (pendiente; commit del slice en esta entrada).

**Resumen**: S6 del roadmap Etapa 7 (locks concurrentes por run).
Hasta v0.13.0, dos `sg run --concurrency` o dos schedulers
externos apuntando al mismo `<tenant>/<project>/<run-id>` podian
leer/escribir `runtime_events` y `runs` de forma entrelazada,
corrompiendo la transicion de estado. S6 introduce locks de
fichero por run para serializar reconcile_run y create_run
dentro del mismo proceso y entre procesos, con dos politicas:
`advisory` (espera hasta `lock-timeout-seconds`) y `fail-fast`
(eleva `LockUnavailable` con `code=sg_lock_unavailable`).

**Modulos / simbolos nuevos**:

- `skillgraph.runtime.locks` (modulo nuevo):
  - `RunLockKey(tenant_id, project_id, run_id)` con sanitizacion
    de path traversal (caracteres `/\. ` reemplazados por `_`).
  - `RunLockKey.to_filename() -> str` (`<tenant>__<project>__<run-id>.lock`).
  - `LockMode = Literal["none", "advisory", "fail-fast"]`.
  - `LockUnavailable(SkillGraphError)` con `code="sg_lock_unavailable"`.
  - `RunLock(lock_dir: Path, key: RunLockKey).take(mode, timeout_seconds)`
    context manager sobre `fcntl.flock` (LOCK_EX | LOCK_NB en polling
    para advisory; LOCK_EX | LOCK_NB en fail-fast).
  - Limpieza: `LOCK_UN`, `os.close`, `unlink()` con
    `contextlib.suppress(OSError)`.

**RunController**:

- Constructor extendido: `lock_dir: Path | None`,
  `lock_mode: LockMode = "none"`,
  `lock_timeout_seconds: float = 30.0`.
- Helper interno `_locked_run(tenant, project, run_id) -> Iterator`
  que delega en `_noop_lock()` cuando `lock_mode="none"` o
  `lock_dir=None`.
- `create_run(...)` envuelto en `with self._locked_run(...)`.
- `reconcile_run(...)` envuelve el cuerpo en
  `with self._locked_run(...)`; extraido a `_reconcile_run_locked`.

**Tests** (12 nuevos en `tests/test_locks.py`):

- `TestRunLockTakeRelease` (3): acquire + release, no leak, idempotencia.
- `TestRunLockConflict` (2): `fail-fast` eleva `LockUnavailable`;
  `advisory` con timeout corto eleva `LockUnavailable`.
- `TestRunLockReleasesOnException` (2): `try/except` interno libera
  el lock; `with` con excepcion interna libera.
- `TestRunLockKey` (3): filename estable, sanitizacion, sin colisiones.
- `TestRunLockAcrossProcesses` (2): dos procesos via `multiprocessing`
  se serializan en el mismo run.
- `TestRunControllerLockIntegration` (1): dos `RunController`
  reconciliando el mismo Run con `lock_mode="advisory"` se serializan
  y terminan ambos en `COMPLETED`; lock_file no queda tras la ejecucion.
- `TestRunControllerLockFailFast` (1): `fail-fast` eleva
  `LockUnavailable` si otro reconcile_run tiene el lock
  (test debil bajo concurrencia extrema).

Total acumulado: **739 tests verde** (725 + 14 nuevos).
`ruff check src tests`: limpio.

### SemVer

`feat(runtime.locks) + feat(RunController lock_dir/lock_mode/lock_timeout_seconds) +
feat(create_run/reconcile_run lock wrapping)` -> **MINOR**
-> `v0.14.0`. Consolidacion inmediata con v0.13.0 porque los locks
son **complemento directo** del modelo de eventos: v0.13.0 introduce
politicas de redaccion, pero sin S6 dos reconciliaciones concurrentes
pueden intercalar eventos y saltarse la redaccion. La regla
"evita micro-releases triviales" se respeta porque S6 son 3 `feat`
coherentes (locks, integracion RunController, tests de concurrencia).

## [Sin bump] — 2026-09-24 (refactor interno)

**Commit**: `6c8c17f` (sin tag, refactor sin bump).

**Resumen**: Reduccion de tamano de funciones en `knowledge/context_controller.py`
para cumplir AGENTS.md §1.5 (umbral ~40 LoC).

- `ContextController.compile_handoff`: 121 -> 94 LoC. Delegacion en
  3 helpers puros de modulo:
  - `enforce_strict_freshness(items, policy)`
  - `apply_budget(obligatory, optional, *, budget_chars, overflow_strategy)`
  - `build_capabilities(included, policy)`
- `ContextController._resolve_one_selector`: 114 -> 23 LoC. Dispatcher
  que delega en 3 ramas:
  - `_resolve_entity_selector(ctrl, value)` (14 LoC)
  - `_resolve_predicate_selector(ctrl, value)` (16 LoC)
  - `_resolve_source_selector(ctrl, value, label)` (31 LoC)
- Mapeo a `CompiledResource` encapsulado en 3 funciones puras de
  modulo: `claim_to_resource`, `predicate_row_to_resource`,
  `evidence_row_to_resource`.

**Tests**: 15 nuevos en `tests/test_context_controller.py`
(11 helpers + 4 mappers). Total: **754/754 verde**. ruff limpio.

## [Sin bump] — 2026-09-26 (stewardship: defensa operativa)

**Commits**: `4d1e622` + `23e4c94` (fix) + `21bc550` (docs) + tareas mise.

**Resumen**: Ciclo STEWARDSHIP-DT-PRE-PUSH-HOOK. Tercera capa de defensa
operativa (junto a pre-commit y CI remoto): **pre-push** ejecuta la suite
completa de pytest (~190s) antes de aceptar un `git push`.

- Hook POSIX shell en `scripts/hooks/pre-push` (75 LoC, sin
  dependencias externas).
- Dispatcher `run_in_toolchain` que detecta `mise`/`uv`/`pip`/`none` y
  delega en el wrapper nativo.
- Bypass `HOOK_SKIP_PUSH_TESTS=1` para emergencias.
- Patrón `mktemp` + `if !` (workaround al bug `set -e` + `| tail` ya
  documentado en `.pipeline.kts`).
- `trap 'rm -f "$_log"' EXIT` para limpieza de tempfile en
  SIGTERM/SIGINT (anadido en V9d deep audit).
- README documenta la capa defense-in-depth en EN y ES.
- Tareas `mise run test-fast` (abort 1er fallo) y `mise run test-cov`
  (cobertura local) para iteracion RED/GREEN.

**Tests**: 9 nuevos en `TestPrePushHook` + `test_installer_copies_all_hooks`.
Total: **889/889 verde**. ruff limpio. Auditoria completa en
`audits/pre-push-hook-2026-09-26.md` (239 LoC).

**Justificación de "Sin bump"**: es dev-infra puro. No añade API
observables ni cambia comportamiento del producto. Siguiente bump
será solo cuando llegue un `feat` real.

## [Sin bump] — 2026-09-26 (stewardship: cobertura de branches H12)

**Commit**: `tests/test_h12_file_signature_scopes.py` (15 tests nuevos) +
`audits/file-scope-validation-branches-2026-09-26.md`.

**Resumen**: Ciclo STEWARDSHIP-DT-FILE-SCOPE-VALIDATION tras la consigna
"avanza" del operador. Subir la cobertura de `file_scope.py` (H12 Scopes
y consultas composables) sin tocar API ni contratos.

- Clase `TestFileScopeValidation` con 15 tests nuevos cubriendo las 12
  ramas tristes que coverage reportaba como descubiertas:
  - 4 sobre `validate_package_name` / `validate_bounded_context_name`
  - 2 sobre `ScopeQuery.__post_init__`
  - 3 sobre `ScopeResolution.__post_init__`
  - 2 sobre `resolve_directory_scope`
  - 2 sobre `resolve_package_scope`
  - 1 sobre `resolve_bounded_context_scope`
  - 1 sobre `aggregate_signatures` (dedup por foco)
- 0 cambios en `src/skillgraph/`. 0 contratos rotos. 0 regresiones.
- Hallazgo colateral documentado (NO reparado): `SignatureProcedencia.
  __post_init__` levanta `ValueError` en vez de `ValidationError`,
  violando AGENTS §1.2. Fix fuera de scope; registrado como derivado.

**Tests**: 23/23 verde en el archivo. Total proyecto: **904/904 verde**.
ruff limpio.

**Cobertura**: `file_scope.py` 82% → **99%** (+17pp). La única línea
restante (284) es un corner case interno del loop de agregación donde
`signatures_per_source` tiene entries con tuple vacío.

## [Sin bump] — 2026-09-26 (cumplimiento AGENTS §1.2: errores tipados)

**Commit**: `dfd192a` — 16 raises cambiados + 12 tests nuevos + audit.

**Resumen**: Tras la consigna "vamos con lo siguiente", se abordó el
hallazgo colateral de la investigación retrospectiva. La inspección
extendida reveló 16 violaciones de AGENTS §1.2 (errores tipados) en
6 archivos:

```text
src/skillgraph/knowledge/file_signature.py    8 raises ValueError
src/skillgraph/knowledge/file_handoff.py      3 raises ValueError
src/skillgraph/knowledge/git_source.py        1 raise ValueError
src/skillgraph/runtime/locks.py                1 raise ValueError
src/skillgraph/governance/improvement.py       2 raises ValueError
src/skillgraph/governance/receipts.py          1 raise ValueError
```

Todos en `__post_init__` de dataclasses de dominio.

**Cambios**:
- src/: 16 raises cambiados de ValueError → ValidationError
- tests/test_knowledge_validation_errors.py: 12 tests nuevos (12/12 rojo→verde)
- tests/test_h9_coverage_git_source.py:78: migrado a ValidationError
- 0 callers en src/ con `except ValueError` (grep limpio)
- ValidationError hereda de SkillGraphError → Exception (no rompe nada)

**Tests**: 918/918 verde (906 → 918, +12 nuevos). Mutation testing M8
detectada. ruff limpio.

**Verificación final**:
```bash
grep -rn "raise ValueError\|raise Exception" src/skillgraph/ --include="*.py"
  → 0 resultados (100% cumplimiento §1.2)
```

**Auditoría completa** en `audits/knowledge-validation-errors-2026-09-26.md`
(114 LoC).
