

>

> **Bloque 2026-10-06 (B27) — Los conflictos avisan y son consultables.**
>
> Versión activa `0.36.0.dev0`; último tag `v0.36.0`; **3560 tests**.
>
> **LA FILA DE B27 DECIA UNA COSA QUE MEDIDA RESULTÓ SER FALSA**, y eso importa
> más que el resultado. Decía «dos claims incompatibles se pisan»; medido sobre
> una base real, eso solo pasa con la **misma** fuente y la **misma** revisión,
> porque el `UNIQUE` de `claims` lleva `source_id` dentro. Dos herramientas que
> discrepan ya coexistían de sobra.
>
> Lo que sí era cierto es la otra mitad —«y no hay forma de saberlo»—, y esa
> mitad es la que se arregla: `conflicts_for` por la fachada de `Storage`, y
> `record_claim` que devuelve si hubo conflicto y **qué se solapa** en lugar de
> devolver siempre el `claim_id` como si hubiera escrito. El aviso llega hasta
> la salida del reconcile, porque un aviso que se recoge y no se imprime es un
> aviso que no existió.
>
> **B27 avisa, no resuelve.** Decidir cuál de las dos afirmaciones vale es B28,
> y es por intención de consulta; borrar es B29. Contrasalto **5/5**.
>
> **B26 cerrado en `v0.36.0`**: `ObservationEnvelope` versionado, `normalizar`
> puro e `ingerir` idempotente. `observed_at` **entra** en el envelope, y eso es
> lo que hace posible la pureza. Arrancó por un bug: la promoción serializaba a
> mano y se quedó con la forma de anterior de `Claim`. Medido 5/5 → **0/5**.
>
> **B25 cerrado en `v0.35.0`** (SemVer derivado: `0 breaking, 1 feat, 1 fix, 3 otros`
> → MINOR, `scripts/derive_semver.py`). **B24 cerrado en `v0.34.1`**. La ruta de certificación se ejecuta
> entera sin credencial y sin dinero, y la etapa `evidence` ya no es un trinquete.
>
> **MEDIDO AL ABRIR: EL MÓDULO DECLARABA OCHO FRONTERAS Y SUS TRES TESTS
> TOCABAN TRES.** `tests/test_uat_real_provider.py` promete
> `workflow → ContextRecipe → handoff → adapter real → AgentResult → transicion
> → persistencia → recuperacion`, y ejecutaba `handoff`, `adapter` y
> `AgentResult`. Las otras cinco —`workflow`, `ContextRecipe`, `transicion`,
> `persistencia` y `recuperacion`— no se ejecutaban nunca.
>
> **Y SUS INSTRUCCIONES DE EJECUCIÓN APUNTABAN A UN FICHERO QUE NO EXISTE.**
> Decían `pytest tests/uat_real_provider.py`, sin el prefijo `test_`. Quien las
> siguiera ejecutaba nada y recibía `rc=4`: un error de uso de pytest, no un
> fallo de la UAT. Una instrucción que apunta a un path inexistente no es una
> instrucción, es una trampa con la forma de una instrucción.
>
> **LO QUE ENTRA: EL RECORRIDO, EJECUTABLE SIN DINERO Y SIN CREDENCIAL.**
> `tests/test_b24_recorrido_certificacion.py:94::TestElRecorridoCompletoSinDinero`
> cubre las ocho fronteras contra el `HttpAgentAdapter` **de verdad** —su
> `httpx.Client`, su retry y su parseo— contra el servidor local de
> `tests/_proveedor_local.py:87::proveedor_local`, que habla la FORMA de la
> respuesta del proveedor. Lo único que se sustituye es el otro extremo del
> cable: si el adapter fuera un doble, estaríamos certificando que el doble
> funciona, que es justo lo que B2 vino a cerrar.
>
> **UN SERVIDOR LOCAL NO ES UN PROVEEDOR.** Esto no certifica que Anthropic
> conteste: certifica que las ocho fronteras del camino funcionan. Lo único que
> queda fuera es «que el proveedor real conteste», y lo mide
> `tests/test_uat_real_provider.py` con `SG_UAT_REAL_PROVIDER=1` y credencial,
> camino que este bloque no toca. Un camino, dos endpoints: si el opt-in está
> puesto, el servidor local ni se levanta.
>
> **LA EVIDENCIA ES QUE HUBO UNA LLAMADA REAL, NO QUE ACABARA BIEN.** La
> propiedad no es «el nodo acabó SUCCEEDED» sino «el servidor RECIBIÓ una
> petición construida por el adapter». Eso lo mide
> `tests/_proveedor_local.py:107::peticiones`; sin ella, un adapter que no se
> invoca y otro que se invoca con la basura darían el mismo veredicto al resto
> del recorrido.
>
> **LO QUE EL HARNESS HIZO, Y FUE LO MÁS CARO DEL BLOQUE.**
> `scripts/mutate_b24_ruta_certificacion.py:123::SONDAS` declara cinco sondas, una
> propiedad por sonda. Dos de ellas, tal como estaban escritas, **no podían
> caer**: mutar `estado` es un no-op porque el setup de `proveedor_local()` lo
> repone, y `segunda = primera` deja el assert tautológico. Medidas, no supuestas:
> rehechas y **5/5 cazadas**.
>
> **Y DE AHÍ SALIÓ UN HALLAZGO DE PRODUCTO, NO DEL HARNESS: LA IDEMPOTENCIA DE
> RECONCILIAR UN RUN RESUELTO TIENE CINCO CAPAS.** Quitarle una —la guarda de
> `src/skillgraph/runtime/runcontroller.py:315::_reconcile_run_locked`, la de
> `src/skillgraph/runtime/run_observability_delegations.py:202::_calculate_frontier`,
> o que el run no se cierre— da `rc=0`. Ni dos juntas. La quinta no es una guarda
> de reconciliar: es el guard de nodo,
> `src/skillgraph/runtime/node_execution_delegations.py:182::_node_guard`, que
> devuelve veredicto si ya hay SUCCEEDED y el plan no declara self-loop. Las
> cuatro anteriores son cortocircuitos que evitan llegar hasta ahí. La propiedad
> que mide
> `tests/test_b24_recorrido_certificacion.py:212::test_6_reconciliar_de_nuevo_no_reejecuta_el_nodo`
> es el efecto conjunto de las cinco, y no nombra ninguna.
>
> **Y TRES DEFECTOS DE ESTADO DE B23 QUE ENCONTRÓ LA RED AL PUBLICAR.** El
> `pre-push` corre la verificación canónica, y con la suite en rojo no sube.
> `v0.34.0` estaba **duplicado** en `STATE.yaml release.releases`, la entrada de
> 0.34.0 **no estaba** en el CHANGELOG, y el total declarado se quedaba en 3465
> con 3475 en el árbol. Ninguno lo señalaba ningún test hasta que el push los
> pidió.


> **Bloque 2026-10-06 (B22) — La suite no puede cambiar el árbol por debajo de un instrumento.**
>
> Versión activa `0.33.0.dev0`; último tag `v0.33.0` (MINOR derivado: `b/f/x/n/d 0/1/0/4/0`).
>
> **NO ES UN OPEN. ES CERO INFORMACIÓN.** `measure_b9_gate_1_0.py` devolvió
> «Un predicado revanto y el informe NO esta completo» y con eso borró los
> veredictos de las otras diecinueve propiedades del gate de 1.0. Una sola
> excepción decidía sobre veinte preguntas.
>
> **LA CADENA, MEDIDA DE PUNTA A PUNTA.** `tests/test_b14_truth_single_reader.py`
> deforma `src/skillgraph/__init__.py` con `__version__ = "7.7.7"`. El
> predicado de reproducibilidad del gate lee ese fichero **real** como línea
> base, construye el paquete y exige que el contenido siga igual. Su premisa
> es que nadie lo toca: el aserto está en
> `scripts/measure_b9_gate_1_0.py:1595::_distribution_reproducible`, y el punto donde un predicado puede
> reventar sin que nadie lo contenga es `scripts/measure_b9_gate_1_0.py:1830::evaluar`
> —antes de este bloque esa línea era `predicado()` a pelo, y la excepción
> subía hasta `main()` y borraba el informe entero.
>
> **Y LA PRUEBA DE QUE EL CONTENIDO ERA ESE, NO UNA SOSPECHA.** El sha256 de
> `__version__ = "7.7.7"` es `7da24eaaf72e`. Durante la corrida completa ese
> fichero tuvo **dos** contenidos: el real, `cb720d34aeac`, en 195 649 lecturas
> y `7da24eaaf72e` en 1 214. Control: el gate en solitario da informe completo
> 2 de 2; con la suite en paralelo, lo pierde.
>
> **LO QUE ESTO SE LLEVA POR DELANTE: EL INVENTARIO, Y SALIÓ DE EJECUTAR.**
> 25 escrituras que cambian contenido de un versionado, en tres ficheros de
> test. El grep encuentra seis. El séptimo —`test_wi82`, que se llama «does not
> dirty tracked evidence» y por tanto declara lo contrario de lo que hace— solo
> apareció al instrumentar. Es la misma razón por la que el guard está en
> `tests/conftest.py` y no en un módulo: la propiedad es sobre **toda** la
> corrida, y un módulo de guard solo ve los tests que se le negocien al pedir.
>
> **ESCRIBIR NO ES CAMBIAR, Y LA DIFERENCIA SOSTIENE LA PROPIEDAD.** Cinco
> escrituras sobre ficheros versionados **no** cambian su contenido —los
> `finally` del gate y de B15— y son el mecanismo correcto del test que deforma
> y restaura. Contarlas como infracción obligaría a prohibir restaurar, que es
> lo único que permite medir.
>
> **R2.** Cada predicado se ejecuta aislado y su excepción se convierte en su
> veredicto: `NO_MEASURABLE` con la clase y el mensaje. El aislamiento está en
> `scripts/measure_b9_gate_1_0.py:1771::_aisla`. Y `NO_MEASURABLE` y no `OPEN`
> porque `OPEN` es una afirmación sobre el **proyecto**, y un predicado que
> revienta no ha medido nada. `listo_para_1_0` sigue exigiendo las veinte en
> `PASS`: el 1.0 no se puede declarar, y eso es lo correcto.
>
> **LO QUE NO SE CIERRA, Y POR QUÉ NO ERA UN ARREGLO DE TEST.** `test_b14`
> sigue deformando el árbol real, declarado como deuda con motivo medido.
> `project_truth.py` deriva su RAIZ de `__file__`, y medido que ningún sandbox
> da una respuesta de verdad: con los cuatro ficheros que el script lee la
> colecta sale **rc=5** y el verificador responde `ilegible` **por el motivo
> equivocado** —los tests que esperan `ilegible` por motivo pasarían de
> mentira—; copiando el árbol entero (722 ficheros) sale **rc=3** porque la
> copia no es un repositorio. Las dos salidas piden que el instrumento acepte
> su raíz por parámetro, que es la superficie de B0/B14.
>
> **CUATRO DEFECTOS PROPIOS, Y SON LO QUE MÁS CUESTÓ.** La constante que
> programa el guard al final llevaba escrito a mano un nombre de fichero que no
> era el suyo: no casaba, no movía nada, y el guard corría **en cabeza** dando
> verde con diecinueve infracciones ya registradas detrás. El contrasalto del
> caso base usó `test_b14` como ejemplo de escritor no declarado y se volvió
> no-op en cuanto ese fichero entró en el mapa de excepciones. El informe del
> instrumento imprimía con los nombres que deja un `for` normal —que ligan en el
> ámbito de la función— y por eso las dieciocho filas graves salían con el
> autor del último hallazgo. Y el harness dio un **4/4 falso**: las cuatro
> sondas «cayaban» por un `INTERNALERROR` del propio hook al colectar, no por su
> aserción, que es exactamente la forma que un guard no debe tener.
>
> **HARNESS 4/4**, cada una por su aserción, tras exigir que el test nombrado
> aparezca como `FAILED` y detectar anclas ambiguas —M2 deformaba la primera de
> dos apariciones y no miraba donde estaba el guard—.
>
> **CERTIFICADO** con los contratos de la receta, todos en verde: suite completa
> `3441 passed + 3 skipped` bajo `coverage.sh` —3444 declarados y colectados—,
> `check_public_surfaces.py`, `check_ci_recipe_parity.py`,
> `check_package_build.py`, `ruff`, y `check_coverage_floors.py` con
> `VEREDICTO: todo módulo gobernado por §6.3 cumple su suelo` al 95,87 % global.
>
> **LO QUE LA RECETA NO DIO, Y POR QUÉ NO ES DEFECTO DEL REPO.** `mise exec --
> pipelinek` sí resuelve la 0.39.0 que fija `mise.toml` —el shim suelto da
> 0.46.0—, pero el motor falla en la etapa 0 en 0,24 s con
> `failureKind: INFRASTRUCTURE` y «Cookie file not created; wrapper may have
> failed to start»: creó el directorio del run y `script.sh`, y nunca escribió
> `wrapper.sh`. Es el binario en este entorno, no el repo, y es el mismo
> veredicto no fiable en sesión agéntica que ya está registrado en
> `bl-bl-01M3WJ3KCP000387S47TMRXK40`.

---
> **Bloque 2026-10-05 (B21) — Una certificación en rojo no puede decir QUÉ falló.**
> (cerrado y publicado en `v0.32.7`)
> Versión activa `0.32.7.dev0`; último tag `v0.32.7`.
>
> **NO ES QUE LA CI NO MOSTRARA EL FALLO.** Es que el motor se queda con la
> **cola** de la salida de cada step y la recorta a media línea, y
> `coverage.sh` imprime ~100 líneas de tabla de cobertura **después** de
> pytest. Los `FAILED` existían en el log entero de esa misma corrida; lo que
> no existía era que nadie los dijera al final.
>
> **MEDIDO, sobre las consolas reales:** de 12 consolas de `unit-tests` en
> `.pipelinek/control/`, **las 12 terminan sin `FAILED`**, y la única que sí lo
> hace es `3bb3a3b8` — un run que de verdad falló.
>
> **LA PROPIEDAD Y NO OTRA.** «Lo que pytest dice de sus fallos tiene que
> aparecer **DESPUÉS** de la última tabla de cobertura», y no «que se impriman
> las FAILED»: la segunda ya se cumple sin el arreglo —el log tiene la lista
> entera— y por eso no distinguiría nada. La primera aguanta además que la
> tabla crezca.
>
> **SE CUMPLIÓ EN PRODUCCIÓN.** La primera certificación de B21 terminó en rojo
> y su journal **nombró** los cinco fallos. Era justo lo que se venía a
> arreglar, y lo demostró el propio run que lo sufre.
>
> **Y SIETE DEFECTOS AL CERTIFICAR, CINCO DE ELLOS REGRESIONES PROPIAS.** Y
> ninguno fallaba por mirar mal: **fallaban por no mirar**. El que mejor
> resume el patrón es el que llegó más tarde. El guard compara el estado del
> repo antes y después
> (`tests/test_b21_diagnostico.py:184::_estado_del_repo`), y ese estado lo
> mueve el proceso que lo contiene:
>
> ```
> guard de aislamiento: mide que la corrida aislada no toca el estado del repo
>   en LOCAL            -> 10 passed
>   en la SUITE COMPLETA -> 1 failed, con el aislamiento INTACTO
> ```
>
> La suite lanza cientos de subprocesos de la CLI y cada uno deja su
> `.coverage.parallel.<host>.<pid>.<rand>` en la raíz al terminar. La misma
> corrida lo dice — el estado «antes» ya traía `pid1223081` de otro proceso y
> el «después» traía `pid1286996` de otro. **Un reloj que se mueve solo no
> puede medir**, ni para pasar ni para fallar. La medición pasó al artefacto
> que la corrida escribe: si el `data_file` de la config aislada apunta a su
> sandbox, coverage no tiene a dónde ir en la raíz. Es un silogismo, y nadie
> de fuera lo puede contaminar. El recorte del diagnóstico, que es lo que
> este bloque arregla, se declara en
> `scripts/diagnose_pytest_run.sh:51::MAX_FALLIDOS` y se imprime al final
> desde ahí.
>
> **Y EL SEXTO LO ENCONTRÓ SU PROPIO CONTRASALTO**, que es para lo que existe:
> el reloj del log —el único utilizable, porque solo lo escribe `coverage.sh`—
> comparaba la clave `unit-tests.log` cuando el estado la declara como
> `.pipelinek/unit-tests.log`. Dos `.get()` a `None` y `None == None`: verde.
> El test que se suponía que vigilaba el log no miraba el log.
>
> **Certificado** con la receta canónica: 9/9 etapas, run
> `ba25dc8b-5d1d-4eb8-973d-1752aa3f5848` verificado por su receipt,
> **3428 passed + 3 skipped = 3431**.

---

> **Bloque 2026-10-04 (B20) — El gate se contradecía a sí mismo, y la razón era un sufijo.**
> (cerrado y publicado en `v0.32.5`, con B20-2 en `v0.32.6`)
>
> **ES EL HALLAZGO MÁS INCÓMODO DE LA SERIE, Y NO ES UN `PASS` FALSO NI UN
> `OPEN` FALSO.** B16 abrió propiedades que daban verde con el defecto
> presente. B18 endureció una que ya era cierta. B19 arregló un veredicto que
> afirmaba más de lo que podía sostener. B20 es otra cosa: **el gate se
> contradice a sí mismo.**
>
> `ontology extensible` y `core sin dependencias de impl. externa` son dos
> propiedades del mismo gate sobre la **misma frontera**. MEDIDO, con un solo
> import en `core/`:
>
> ```
> core/ importa skillgraph.packaging.manifest
>   ontology extensible    : PASS   «no nombra ningún tipo de recurso»
>   core sin dependencias  : OPEN   «depende de fuera de sí mismo»
> ```
>
> Dos veredictos sobre el mismo hecho, y no son el mismo. MEDIDO sobre la
> superficie **real** del proyecto, no sobre casos inventados: **7
> contradicciones de 9**.
>
> **LA RAZÓN, Y TIENE LAS DOS CARAS.** `_TIPO_DE_RECURSO` era
> `^[A-Z][A-Za-z]*Pack$` — un patrón por **forma**:
>
> - **No ve lo que importa.** De los ocho tipos de recurso que el proyecto
>   *declara de verdad* —`PackManifest`, `CompiledResource`, `CapabilitySpec`,
>   `BrickType`, `Catalog`, `Brick`— el patrón ve **cero**. `PackManifest` es el
>   manifiesto de un pack, el tipo central del proyecto, y no acaba en `Pack`.
> - **Ve lo que no importa.** El único nombre que contaba era `FilaDePack`, que
>   es una **fila** de la tabla de packs, no un tipo de recurso. Con su import
>   puesto salía `OPEN` acusando al núcleo de depender de los recursos.
>
> **Y EL COMENTARIO DEL CÓDIGO DE AL LADO RAZONABA CORRECTAMENTE.** Decía que no
> escribir una lista de tipos evita tener una segunda fuente de verdad. Lo que
> no ve es que **un patrón por forma *es* una lista**, más corta y peor, porque
> decide **cómo se escribe** un nombre en vez de **a qué conjunto pertenece**.
> El endurecimiento de B16 fue sobre el **formato** de la mirada —de cadenas a
> imports y atributos—: una vista más aguda de una cosa que no es la que hay.
>
> **QUÉ ENTREGA.** El conjunto se **deriva del árbol**, de los paquetes que el
> proyecto llama recursos por el nombre de su directorio; la evidencia dice
> cuántos son, de dónde salen y cuántos ficheros se recorrieron. Y los
> **docstrings** que nombran un recurso se **dicen** sin abrir el veredicto,
> porque documentar la frontera es lo contrario de depender de ella: medido,
> `core/` menciona `WorkflowPlan` en tres sitios y los tres son documentación
> de `NewType`.
>
> **EL TECHO, Y NO SE MAQUILLA.** Quedan **tres** contradicciones —
> `CompiledResource` en `knowledge/`, `CapabilitySpec` en `platform/ports/`,
> `SkillImportReport` en `domain/`— y el motivo es uno solo: el proyecto llama
> recurso a tres tipos cuyos **paquetes no lo dicen**. «Qué es un recurso» **no
> es un concepto que el código contenga**, y declararlo es una decisión de
> producto, no una tarea de guard. Por eso este bloque no la toma: **la mide y la
> deja escrita**, y el guard las **nombra** en vez de contarlas, porque un techo
> que no se nombra no se puede romper.
>
> **DOS DEFECTOS PROPIOS DEL MISMO CLASIFICADOR, que es una clase de error y no
> dos sucesos:**
>
> 1. `id(ast.get_docstring(nodo))` es el id de un **string**, no el del nodo
>    `Constant`; la comparación no coincidía nunca y el instrumento informó de
>    «0 docstrings» con `core/` llenándose de ellos.
> 2. Ya con los nodos, solo miraba `body[0]`, que **pierde la documentación de
>    los `NewType`** —la segunda sentencia del cuerpo del módulo—. Con esa
>    versión el veredicto daba `OPEN` sobre un árbol **sano**. Un `OPEN` falso
>    en estado sano es el fallo más caro que puede tener un guard, porque
>    entrena a su lector a no creerlo.
>
> **Y UN HALLAZGO SOBRE EL HARNESS:** la contrasalto de la contrasalto daba
> «NO CAYO» porque comprobaba `len(rotas) <= 3`, y con la implicación
> invertida la lista queda **vacía**: cero caben en tres. Un guard sin con qué
> enterarse no es un guard que no se entere.
>
> **Y, AL CERTIFICAR, EL GATE QUE CORRE NO ERA EL DECLARADO.** El hook instalado
> en `.git/hooks/pre-commit` **diverge** de `scripts/hooks/pre-commit`: el
> declarado corre pytest **solo sobre los `.py` staged** —el filtro de WI-100,
> un cambio de 12x— y el instalado corría la **suite entera**. MEDIDO, el hook que
> anunciaba «smoke, N files staged» estaba lanzando los 3321 tests.
>
> **LO NUEVO ES LA DIVERGENCIA, NO LA AUSENCIA.** `.git/hooks/pre-push` tampoco
> estaba instalado, y eso **ya lo tenía medido y escrito el propio hook** en su
> docstring: «en la máquina donde se operaba, este hook NO estaba instalado»,
> con la conclusión de que instalarlo es decisión del operador. No es un
> hallazgo de B20 y no se reclama como tal. Lo que sí es de B20 es la otra
> mitad: un hook **instalado y desfasado**, que es peor que uno ausente
> porque uno ausente no hace nada y del que corre se puede estar esperando
> que filtre.
>
> Eso no lo ve ningún guard porque `test_hooks_system.py` lee la copia
> **versionada** (`HOOK_PATH`): todas sus propiedades son ciertas del fichero
> que está en el repo y **silenciosas sobre el fichero que git ejecuta**. WI-100
> añadió el test de que «los ficheros staged llegan a pytest», y pasaba, con la
> puerta antigua corriendo. Es la forma de B19 un nivel más arriba: **la
> medición era correcta sobre el artefacto al que apuntaba, y el artefacto en
> uso era otro.**
>
> **POR QUÉ NO ES UN TEST, y es el mismo motivo por el que WI-97 se niega a
> comprobar `dist/`.** El hook instalado es estado **por clon** —no está en git,
> porque `.git/` no se versiona—, así que un test que lo comprobara estaría
> afirmando sobre el árbol de trabajo y no sobre el checker, y saldría rojo en
> cada clon recién hecho hasta que alguien corra el instalador. Paridad
> restaurada con `scripts/install-hooks.sh`: los dos hooks coinciden byte a byte.
> **Deuda que se registra y no se abre:** nada en el repo informa del desvío
> entre el hook declarado y el instalado.
>
> **UN FALLO PROPIO MÁS, Y UNO QUE NO ES MÍO.** Al certificar, un run dio «5
> failed» y a mí solo se me enseñaron **dos** líneas `FAILED`. Lo atribuí a que el
> hook imprime `tail -40` del log, y casi lo «arreglo». MEDIDO: `tail -40`
> enseña la lista **completa** incluso con 14 fallos, porque pytest las imprime
> justo antes de la línea de recuento; lo que me recortó a mí fue la captura de
> salida de mi propia herramienta. El cambio se revirtió: no iba a sostener una
> modificación con una medición que acababa de desmentir. Y los dos tests que
> azonearon en aquella corrida —`test_wi96…test_el_script_esta_versionado…` y
> `test_wi97…test_el_artefacto_cumple_el_contrato`— han pasado en **todas** las
> posteriores: dos sueltas y dos completas. **Causa no establecida, y no se
> afirma ninguna.**
>
> **Y LA CERTIFICACIÓN FALLÓ DESPUÉS DE QUE TODO PASARA, QUE ES LA FORMA
> PEOR.** La etapa `unit-tests` terminó con rc=1 cuando la suite entera llevaba
> un rato en verde: **3321 passed, cobertura 93,68 % sobre un suelo de 80**, y
> luego `No source for code: '/tmp/b17_16r3_ise/…'`.
>
> MEDIDO sobre el dato real, no sobre un caso inventado: de las **376** rutas
> del fichero de cobertura, **282 eran de `/tmp`**, y ninguna existía ya cuando
> llegaba el informe. El dato lo producía la clase `_ArbolCopiado` de
> `test_b17_pack_lifecycle_exec.py`, que abre un
> `TemporaryDirectory(prefix="b17_")`, copia `src/` dentro y levanta el paquete
> de ahí como subproceso —que el hook `.pth` mide igual que cualquier otro— y
> lo borra al terminar. Rompía **las dos** consumidoras: `coverage report` y
> `coverage json`, o sea la etapa siguiente de la receta.
>
> **LO QUE NO SE HIZO, Y ES LA DECISIÓN.** Los temporales no tienen un solo
> layout: conviven `/tmp/b17_*/src/` y `/tmp/b19_*/repo/src/`. Remapearlos con
> `[paths]` obligaba a enumerarlos, y **enumerar layouts es la misma lista
> encubierta por forma** que este bloque denuncia en el predicado: decide cómo
> se escribe la ruta en vez de a qué conjunto pertenece. La regla es una y no
> necesita lista: **lo que vive fuera del árbol del repo no es código de este
> repo, y no se mide.**
>
> **Y NO RELAJA EL SUELO.** MEDIDO: con el `omit` puesto, subir `fail_under` a
> 95 o a 99 sobre el 94 % real sigue dando **rc=2**. Lo que se deja de exigir es
> que coverage sepa abrir ficheros que ya no existen. El guard deriva la
> configuración del heredoc de `coverage.sh` en vez de copiarla —una copia en el
> propio guard sería el guard comparándose consigo mismo— y su contrasalto dio
> **rojo al escribirlo**: con un temporal que no se llamaba `skillgraph` la
> medición no registraba nada y el test principal pasaba por la razón
> equivocada. Dos mutaciones sobre producción, ambas cazadas.
>
> **Y UN SEGUNDO DEFECTO PROPIO, QUE INTRODUJE YO AL ESCRIBIR EL ARREGLO.** El
> comentario que explicaba el `omit` llevaba acentos graves, y el heredoc de
> `coverage.sh` va **sin comillas** porque tiene que expandir `$REPO_ROOT`.
> Bash los trató como **sustitución de comando**: la configuración salió
> ilegible y la etapa murió en el primer `coverage erase`, un segundo y medio
> después de empezar.
>
> Lo importante no es el error: es que **los tests del guard no lo cazaron.**
> Leían el **texto** del heredoc, que estaba perfecto — lo que estaba mal era
> lo que el shell **produce** de él. *Un guard que lee el fuente mide el
> fuente, y lo que se usa es lo que el shell escribe.* Por eso el guard ahora
> **genera** la configuración ejecutando el heredoc y exige que coverage la
> pueda leer. Tres mutaciones cazadas en total: quitar el `omit`, cambiarlo por
> uno que no cubre `/tmp`, y reponer un acento grave dentro del heredoc.
>
> **Y CUANDO POR FIN PUDO INFORMAR, DIJO QUE SEIS MÓDULOS NO CUMPLÍAN SU
> SUELO.** La etapa `coverage-floors` no es una lista de excepciones: el suelo
> se **deriva** de si el módulo cuelga de un paquete, y lo único declarado a
> mano es `platform/paths.py` al 60 % porque AGENTS §6.3 lo exonera.
>
> | módulo | antes | después | suelo |
> |---|---|---|---|
> | `cli/commands/pack.py` | 46,43 % | **91,07 %** | 70 % |
> | `platform/installed_packs_repository.py` | 78,57 % | **100,00 %** | 90 % |
> | `packaging/registry.py` | 77,86 % | **98,47 %** | 90 % |
> | `presentation/views.py` | 79,26 % | **98,52 %** | 90 % |
> | `governance/graph_diff.py` | 80,00 % | **99,13 %** | 90 % |
> | `resources/status.py` | 75,31 % | **92,59 %** | 90 % |
>
> **Y NO ES DEUDA QUE HAYAS CREADO EL ARREGLO ANTERIOR**, que es lo que había
> que descartar antes de mirar un solo test. MEDIDO: las 282 rutas de `/tmp`
> eran **copias** de estos mismos ficheros en otra ruta, y coverage cuenta los
> statements al fichero que se ejecuta — ejecutar `/tmp/.../pack.py` no puede
> sumar ni una línea a `src/.../pack.py`. Quitar esas rutas no bajó la
> cobertura de nadie: solo dejó de romper el informe. **Los seis
> incumplimientos ya estaban ahí y no los miraba nadie.**
>
> **LO QUE NO SE HACE ES BAJAR UN SUELO** para que la etapa pase. El suelo es
> el que AGENTS §6.3 declara; lo que se cubre es el código que lo incumplía.
> El más grande era `pack.py`, con `install`, `update`, `remove` y `list`
> **enteros sin ejecutar**: el ciclo ya se probaba de punta a punta por
> subproceso, y el cuerpo de los comandos no lo ejecutaba nadie.
>
> **DONDE SE MIRA, VERIFICADO POR AST:**
>
> | cita | que sostiene |
> |---|---|
> | `measure_b9_gate_1_0.py:622::_ontology_extensible` | los tres defectos, escritos en su docstring |
> | `measure_b9_gate_1_0.py:819::PAQUETES_DE_RECURSO` | el conjunto se declara por **paquete**, no por clase |
> | `measure_b9_gate_1_0.py:822::_tipos_de_recurso` | el conjunto se **deriva** del árbol, y la cifra se publica |
> | `measure_b9_gate_1_0.py:843::_docstrings_de` | documentación y código, separados —y sus dos defectos |
> | `test_b20_ontologia_contradictoria.py:95::PENDIENTES_POR_DECLARAR` | el techo **nombrado**, que es lo que lo hace rompible |
> | `test_b20_ontologia_contradictoria.py:216::TestElGateNoSeContradiceASiMismo` | el invariante que cierra la contradicción |
> | `mutate_b20_ontologia_contradictoria.py` | 3 sondas, 3/3, y **M1 y M2 declaran dos diagnósticos cada una** |
> | `test_b20_coverage_omit.py:85::_rc_generada` | la configuración se **genera ejecutando** el heredoc, no se lee |
> | `test_b20_coverage_omit.py:181::TestLaConfiguracionNoMideFueraDelRepo` | la propiedad **ejecutada**, con su contrasalto que dio rojo al escribirlo |
> | `test_b20_coverage_omit.py:230::TestElArregloNoRelajaElSuelo` | un arreglo que apaga el umbral no es un arreglo |
> | `test_b20_coverage_omit.py:250::TestLaConfiguracionEsLegible` | lo que el shell **produce** tiene que ser una configuración |
> | `check_coverage_floors.py:159::informe` | la **segunda** consumer, que también se rompía |
>
> ---
>
> **Y AL PUBLICAR, B20-2: LA MISMA FORMA DEL DEFECTO, OTRA VEZ Y MÁS ABAJO.**
> Publicar es certificar. El `pre-push` corre la receta, y su `unit-tests` dio
> `2 failed`. Uno era el par de versión de WI-109. El otro se atribuyó a un
> «fallo dependiente del orden» que **no se reproduce**: el par pasa, y
> tampoco pasa en la suite entera. Lo que sí es cierto, y medido, es esto:
>
> **`project_truth.py` tiene DOS salidas, y solo una se miraba.** `main()`
> responde `Estado` —las cinco verdades, `rc` 0/1— o `VerdadNoLegible` —
> `coherente: false` e `ilegible`, y **ninguna** de las cinco, `rc` 2—. Las
> dos son JSON válido, y por eso son dos contratos y no uno con un campo a
> veces ausente. De sus consumidores, **uno** conocía la segunda forma
> (`measure_b14_truth_single_reader.py`, que lee `ilegible`) y los otros dos
> no:
>
> | consumidor | qué salía | qué dice el guard sobre no mirar la causa |
> |---|---|---|
> | `test_b0_truth_convergence.py` | `KeyError: 'bloque'` | el guard que existe para explicar el problema era el que no lo explicaba |
> | `measure_b9_gate_1_0.py` | `OPEN` con la lista **vacía** | afirma que la propiedad no se cumple cuando lo que pasa es que no se pudo leer |
>
> Y el segundo no es que no diga nada: **orienta mal**. `OPEN` dice «arregla el
> proyecto»; aquí lo que hay que arreglar es una verdad rota. Es el error de
> B19 entrando por otra puerta, y por eso el veredicto nuevo es
> `NO_MEASURABLE`, que el vocabulario de la cabecera del gate ya definía para
> exactamente esto: «no hay forma de decidirla con este entorno, y se dice por
> qué». **Las dos dejan 1.0 lejos**, luego aquí no baja el veredicto: baja la
> **afirmación** de que el proyecto tiene un defecto que no se ha comprobado
> que tenga.
>
> **LA MEDICIÓN, con el script real sobre un árbol real:**
>
> ```
> respuesta sana      rc=0  bloque, coherente, contradicciones, objetivo, …
> respuesta ilegible  rc=2  coherente, ilegible      ← sin `bloque`, con la causa
> ```
>
> **Y, AL PUBLICAR, LA RELEASE QUE ESTE BLOQUE ACABABA DE HACER NO SE
> CONTABA A SÍ MISMA.** `v0.32.5` estaba en git y fuera de
> `release.releases`. No era un *forgot* en una tabla: el inventario es lo que
> decide qué releases se contrastan, y una que no está en la lista **se escapa
> de `test_every_listed_sha_matches_its_tag`**. Una release no listada es una
> release cuya provenance no mira nadie. MEDIDO, poniendo el sha que estaba
> escrito a mano en la prosa: `FAILED v0.32.5: dice a8c1ffaab559, git dice
> f3948feda480`. El guard estaba bien; lo que faltaba era la entrada. Y con
> ella caían tres afirmaciones caducadas en el mismo registro: la fila de
> SemVer de `v0.32.4` citada como si fuera la de `v0.32.5`, un `tests.total`
> que no cuadraba con el campo, y un comentario que afirmaba que «el guard que
> la lista no puede mirarlo» —falso, y una afirmación falsa en un comentario de
> provenance es justo lo que hace que nadie lo compruebe.
>
> **CERRADO CON HARNESS 4/4 CON 4 CAUSAS**, dos sondas sobre el guard de B0 y
> dos sobre el del gate. Y con un **fallo propio del arnés** que es el segundo
> en dos bloques: la primera versión contaba como CAZADA cualquier `rc != 0`, y
> los selectores de las dos sondas del gate estaban mal —les faltaba el
> `tests/`—, luego pytest salía con 4, que es **error de uso**, y el arnés lo
> leía como «la sonda cayó». Un arnés que cuenta su propio error como acierto es
> peor que no tener arnés: da el número que el bloque quiere mostrar y no midió
> nada. Ahora exige `rc == 1` **y** el nombre del test en la salida, y valida
> cada selector **antes** de deformar.
>
> ---
>
> **Bloque 2026-10-04 (B19) — «NO es reproducible» y «no he podido medirlo» son dos frases distintas.**
> (cerrado y publicado en `v0.32.4`)
> Versión activa `0.32.4.dev0`; último tag `v0.32.4`.
>
> **ESTE ES EL PRIMER BLOQUE DE LA SERIE QUE NO ES UNA PROPIEDAD FALSA.** B16 y
> B17 abrieron propiedades que daban verde con el defecto presente. B18 endureció
> una que ya era cierta. B19 es de otra clase: **la propiedad es cierta y el
> defecto está en el verbo del veredicto.**
>
> **NACE DE UN OPEN DE 1 DE 8 QUE SALIÓ AL CERTIFICAR B18**, y de un fallo mío
> que es parte del hallazgo. La primera vez que vi ese OPEN solo leí el nombre de
> la propiedad en un resumen y volví a ejecutar el gate. **No guardé la
> evidencia.** El primer instrumento dio 6 de 6 PASS — bien ejecutado, y midió la
> pregunta equivocada, porque sin el texto del fallo no se sabe qué pregunta
> hacer—. Guardar la evidencia del fallo es lo que convirtió un número raro en
> un diagnóstico, y es el mismo requisito que B18 le añadió a su arnés para las
> deformaciones: **no cuenta lo que no se ha visto caer.**
>
> **MEDIDO, Y LA PROPIEDAD ES CIERTA AL REVÉS:**
>
> ```
> 8 construcciones con la condición exacta del predicado → bytes IGUALES 8 de 8
>   cuatro sin tocar la fecha, cuatro tocándola con os.utime sobre __init__.py
> 2 sdists con la suite completa de pytest en paralelo → CONTENIDO idéntico
>   397 ficheros, 0 diferencias
> ```
>
> **EL DEFECTO, Y HAY DOS CAUSAS QUE PIDEN ACCIONES OPUESTAS:**
>
> | bytes distintos porque… | quién lo arregla |
> |---|---|
> | el build es irreproducible | el **build** |
> | la entrada cambió entre las dos mediciones | la **medición** |
>
> El predicado no las distinguía, y decia «la distribución **NO es
> reproducible**» en los dos casos. Eso es grave aquí de un modo que no lo era
> en B16: `distribution reproducible` es la clase de propiedad **más alta de la
> serie**, `ejecutada`, y es la única que alguien podría citar para decir «el
> build de este proyecto es irreproducible» sin comprobar nada más.
>
> **POR QUÉ NO SE RESUELVE DENTRO DEL ARTEFACTO, MEDIDO: no se puede.** Si un
> fichero ya versionado cambia entre las dos construcciones, los dos artefactos
> son coherentes consigo mismos y aun así se construyeron con **entradas
> distintas**. Hace falta el estado del árbol, y se toma con
> `_huella_de_entrada` justo antes de cada construcción: HEAD, el estado del
> árbol y el diff contra HEAD, con separador NUL. **El diff es lo que aporta el
> contenido de lo modificado**, y sin él la huella sería un `git status` que
> solo ve nombres.
>
> **LO QUE YA EXISTÍA Y CUBRE LA MITAD, Y NO SE TOCA.**
> `sg_build_sdist_no_versionado`, en `check_package_build.py`: medido, con un
> fichero sin versionar el veredicto es `OPEN` y la evidencia dice *«el artefacto
> depende de lo que haya en el árbol de trabajo, no del commit»*. Es un buen
> guard, y la hipótesis más obvia era la buena. Hay un test que lo comprueba,
> porque si el arreglo degrada en la frase acusadora un guard que ya era
> correcto, **se ha roto uno bueno mientras se arreglaba uno malo**.
>
> **LA DECISIÓN SE SACA DE LA MEDICIÓN Y POR ESO SE PRUEBA EN
> MILISEGUNDOS.** `_decide_por_bytes` es pura: dos dicts de hashes y dos
> huellas. Medido: dejarla dentro del predicado hacía que los tests tardaran
> **cero**, porque no se puede deformar la decisión sin deformar también la
> construcción. Un guard que no se puede deformar sin disparar el sistema
> entero no vigila la decisión: vigila que el sistema entero corra.
>
> **TRES FALLOS PROPIOS, Y LOS TRES IMPORTAN MÁS QUE EL ARREGLO:**
>
> 1. **El test midiò el repositorio equivocado.** La primera versión lanzaba el
>    gate del **árbol real** con `cwd` en el clon, y el gate calcula su `RAIZ`
>    desde `__file__`. El test **falló** —`PASS` en vez de `OPEN`— y por eso se
>    pudo ver. Un test que hubiera dado verde habría sido el peor de los tres.
> 2. **El contrasalto de M1 no mediò lo que decía.** Comparaba el árbol limpio
>    contra el árbol editado, y `git status` **ya cambia** entre esos dos casos.
>    No aislaba el contenido: mediaba que hay un cambio, que es justo lo que
>    `git status` ve sin el diff. Para que el diff sea necesario, los dos
>    árboles tienen que verse **iguales desde git** — que es el caso real de
>    B19: editar, construir, editar otra vez, construir.
> 3. **El harness no sabía leer su propia salida.** Daba `0 de 3` sobre tres
>    sondas que sí habían caído, porque hacía `split()[0]` sobre `FAILED
>    <fichero>::<clase>::<testo>` y se quedaba con `FAILED`. Un harness que no
>    sabe contar lo que ha medido da cero con la sensación de que el guard no
>    funciona.
>
> **DONDE SE MIRA, VERIFICADO POR AST:**
>
> | cita | que sostiene |
> |---|---|
> | `measure_b9_gate_1_0.py:1186::_huella_de_entrada` | la huella de la **entrada**, y por qué el diff es necesario |
> | `measure_b9_gate_1_0.py:1258::_decide_por_bytes` | la decisión, pura, deformable en milisegundos |
> | `test_b19_entrada_no_veredicto.py:187::TestLaHuellaMideLaEntradaYNoElCommit` | el contrasalto que exige que los dos árboles se vean **iguales** desde git |
> | `test_b19_entrada_no_veredicto.py:267::TestElVeredictoDistingueLasDosCausas` | el verbo, y el contrasalto de que siga pudiendo acusar |
> | `test_b19_entrada_no_veredicto.py:326::TestLoQueYaEstabaCubiertoNoSeRompio` | el guard que ya existía no se degrada |
> | `mutate_b19_entrada_no_veredicto.py` | 3 sondas, 3/3, y **M3 desincroniza el veredicto de su evidencia** |
>
> ---
>
> **Bloque 2026-10-04 (B18) — La frontera del núcleo no miraba la mitad de la superficie, y su verdad estaba escrita a mano.**
> (cerrado y publicado en `v0.32.3`)
> Versión activa `0.32.3.dev0`; último tag `v0.32.3`.
>
> **ES LA CUARTA DE LAS SIETE QUE B15 NOMBRÓ**, y la que B17 dejó escrita como
> «la primera que habría que mirar de las que quedan». Tres bloques seguidos
> encontraron sus propios instrumentos al escribirlos; este encontró algo peor:
> **un instrumento que miraba menos de lo que declaraba, y una lista de verdad
> escrita a dedo**.
>
> **MEDIDO ANTES DE ESCRIBIR UNA LÍNEA**, sobre copias del árbol con el repo real
> intacto. El predicado es `core sin dependencias de impl. externa`:
>
> ```
> MEDIDO A · se añade a core/ un `from ..platform.storage import Storage` (relativo, nivel 2)
>   veredicto : PASS
>   evidencia : core/ no depende de fuera de si mismo, MEDIDO sobre ... (5 modulos)
>   — byte a byte IDÉNTICA a la del caso limpio
>
> MEDIDO B · se añade a core/ un `import pathlib` (estándar, no estaba en la lista)
>   veredicto : OPEN
>   evidencia : core/ depende de fuera de si mismo: ['pathlib']
>   — un OPEN sobre una frontera que se estaba respetando
> ```
>
> **TRES DEFECTOS CON UNA RAÍZ, y la raíz es que el predicado no sabía qué
> superficie estaba mirando ni de dónde salía su propia verdad:**
>
> 1. **No miraba los imports RELATIVOS.** `_imports_de` exigía `nodo.level == 0`.
>    Y como `core/` está en `src/skillgraph/core/`, un `from ..platform.storage
>    import Storage` tiene `level == 2` y **sale de `core/` entero**. Con ese
>    import de verdad, la evidencia era **byte a byte idéntica** a la del caso
>    limpio: un veredicto que no puede distinguir «el núcleo está limpio» de
>    «no he mirado la mitad de la superficie». Y medido: `core/` **no usa hoy
>    ningún relativo**, luego la superficie estaba vacía y una superficie vacía
>    no se mira porque no hay nada que mirar.
>
> 2. **La estándar eran trece renglones a mano; el intérprete sabe de 290.**
>    Faltaban `pathlib`, `contextlib`, `abc`, `io`, `warnings` y `copy` — todos
>    de la estándar—, luego un import legítimo de cualquiera de ellos en `core/`
>    habría producido un `OPEN` **sobre una frontera que se estaba respetando**.
>    Una propiedad que se pone roja por lo contrario entrena a su lector a no
>    creerla, y eso es un fallo aunque salga del lado conservador. **La lista no
>    contenía ni un nombre falso: era correcta y estaba vieja.** Una lista de
>    trece que se queda vieja no avisa: simplemente empieza a dar veredictos que
>    nadie revisó.
>
> 3. **La evidencia decía «(5 modulos)» sobre un paquete de cuatro ficheros.**
>    Eran los nombres de import **distintos**, no módulos, y no decía cuántos
>    ficheros se habían recorrido. Una evidencia que no describe lo que recorrió
>    no permite saber si el recorrido estaba completo.
>
> **QUÉ ENTREGA.** `_paquete_de` + `_resuelve_import_relativo` resuelven los
> relativos a nombre absoluto, así que un relativo se mide como lo que es;
> `_MODULOS_ESTANDAR` se **deriva de `sys.stdlib_module_names`** (menos los
> privados de un solo guion bajo, que no son API); y `_ficheros_de` +
> `_MODULOS_ESTANDAR_ORIGEN` hacen que la evidencia **describa el recorrido** y
> diga de dónde sale la lista. Nada de esto se escribe a mano, porque escrito a
> mano se queda viejo en silencio.
>
> **LO QUE ESTE PREDICADO NO HACE, A PROPÓSITO.** No **prohíbe** los imports
> relativos. Que `core/` escriba `from .errors import ...` es correcto, y
> obligarle a escribir `from skillgraph.core.errors import ...` para que un
> predicado lo vea es **cambiar el código para que el guard quede bien**. Lo que
> faltaba era mirarlos, y ahora se miran.
>
> **DOS DEFECTOS PROPIOS QUE EL GUARD DE ESTE BLOQUE CAZÓ AL ESCRIBIRLO**, y que
> importan porque los dos habrían pasado un 6/6:
>
> - El filtro se llevaba `__future__` —falso `OPEN` visible **gracias a la
>   evidencia nueva**, que por una vez describía lo que había recorrido—. Sin esa
>   evidencia, un `OPEN` falso en `core/` habría sido indescifrable.
> - `_paquete_de` **devolvía el módulo en vez del paquete**: el recuento se movía
>   de 5 a 6 y el defecto quedaba entero, con un número que parecía correcto.
>
> **DONDE SE MIRA, VERIFICADO POR AST:**
>
> | cita | que sostiene |
> |---|---|
> | `measure_b9_gate_1_0.py:764::_core_sin_dependencias_de_impl_externa` | los tres defectos, escritos en su docstring |
> | `measure_b9_gate_1_0.py:412::_resuelve_import_relativo` | un relativo se resuelve a nombre absoluto, no a `None` |
> | `measure_b9_gate_1_0.py:480::_ficheros_de` | los ficheros del recorrido, contados del árbol |
> | `measure_b9_gate_1_0.py:1476::_MODULOS_ESTANDAR` | se deriva de `sys.stdlib_module_names`, no de trece renglones |
> | `test_b18_core_frontier.py:148::TestUnImportRelativoNoSeEscapa` | el relativo de nivel 2 es `OPEN`; **y un relativo que no sale no es `OPEN`** |
> | `test_b18_core_frontier.py:195::TestLaEstandarNoEsUnaListaEscritaAMano` | un módulo de la estándar ausente no da `OPEN`, y la evidencia dice de dónde sale |
> | `test_b18_core_frontier.py:244::TestLoQueNoSeMiraNoSeDeclaraMirado` | la cifra es la de los **ficheros**, y la evidencia no dice «modulos» cuando mide imports |
> | `mutate_b18_core_frontier.py` | 3 sondas, 3/3, cada una cayendo **solo su diagnóstico** |
>
> **Y UN REQUISITO NUEVO DEL HARNESS.** Una deformación que rompe la sintaxis hace
> caer la suite por **no importar**, no por detectar: parece la sonda más fuerte y
> no ha detectado nada. Por eso este harness **exige que la deformación parsee**
> (`ast.parse`) antes de contarla. Es la generalización de un error que ha salido
> en B16, B17 y B18 con tres síntomas distintos, y el más caro de B18 fue
> silencioso.
>
> ---
>
> **LO QUE LA MEDICIÓN DE CIERRE DE B18 ENCONTRÓ, y es el primer bloque nuevo de
> la serie que NO es una propiedad falsa.** Al correr el gate sobre el árbol de
> release, `distribution reproducible` dio **OPEN 1 vez de 8** ejecuciones. La
> evidencia, capturada: *«mismo contenido y distinta fecha dan bytes distintos
> en 2 artefacto(s) — wheel: 8612ab04ee18 vs dc5789082776; sdist:
> 673d9c2cc5f5 vs eb37bbcbabf2»*.
>
> **MEDIDO, y NO SUPUESTO, lo que se ha podido descartar:**
>
> - **La concurrencia como causa del contenido: REFUTADA.** Dos sdists
>   construidos con la suite completa de pytest corriendo en paralelo tienen
>   **exactamente el mismo contenido**: 397 ficheros, 0 solo en cada lado, 0
>   comunes con contenido distinto.
> - **La irreproducibilidad del build: REFUTADA.** Ocho construcciones con la
>   condición exacta del predicado dan **bytes iguales 8 de 8**: cuatro sin tocar
>   la fecha y cuatro tocándola con `os.utime` sobre `src/skillgraph/__init__.py`,
>   que es lo que hace el predicado para delatar un build que se embeba el
>   mtime. **La distribución ES reproducible.**
>
> **LO QUE NO SE HA ESTABLECIDO, y se dice así en vez de rellenarlo:** la causa
> de aquel OPEN. Y eso deja el defecto, que es real e independiente de la causa:
> **el OPEN de este predicado no distingue «la distribución no es reproducible»
> de «esta medición no ha podido hacerse».** Su evidencia afirma la primera con
> una seguridad que la medición no tiene. Es la lección de B17 —
> `NO_MEASURABLE` ≠ `OPEN` — aplicada a otra propiedad, y con un caso más difícil:
> aquí el instrumento **arranca y construye**, luego no hay forma de que el
> predicado sepa si construyó lo que cree.
>
> **Y UN FALLO PROPIO QUE ESTA MEDICIÓN EMPEZÓ TENIENDO, porque es la razón de
> que el bloque sea un hallazgo y no un recuerdo.** La primera vez que vi el OPEN
> solo leí el nombre de la propiedad en un resumen y volví a ejecutar el gate.
> **No guardé la evidencia.** Un veredicto del que no se conserva la frase no se
> puede diagnosticar, y por eso el primer instrumento de esto —6 de 6 PASS— no
> reproducía nada: estaba bien ejecutado y midió la pregunta equivocada. Guardar
> la evidencia del fallo es lo que convirtió un número raro en un diagnóstico.
>
> ---

> **Bloque 2026-10-04 (B16) — Dos propiedades del gate daban PASS sin nada que comparar.**
> (cerrado y publicado en `v0.32.1`)
> Versión activa `0.32.1.dev0`; último tag `v0.32.1`.
>
> **ESTE ES UN BLOQUE HACÍA 1.0, Y ES LA PRIMERA DE LAS SIETE.** B15 dejó
> escrito que siete de las veinte propiedades del gate se deciden leyendo el
> árbol, y que sus PASS no se pueden retirar solos. Esa lista no era una cola de
> tareas: era **la medida de dónde el gate no sabe lo que dice saber**. Esta
> abre las dos primeras, y no eran débiles. **Eran falsas.**
>
> **MEDIDO ANTES DE ESCRIBIR UNA LÍNEA**, sobre copias del árbol con el repo
> real intacto:
>
> ```
> MEDIDO A · se renombra la constante a _CAPABILITY_VERSION en todo src/
>   veredicto : PASS
>   evidencia : CAPABILITY_VERSION se declara en un solo sitio: []
>
> MEDIDO B · core/ importa DomainPack de verdad
>   veredicto : PASS
>   evidencia : core/ no nombra ningun tipo de recurso: se anaden sin tocarlo
> ```
>
> La primera es **un PASS cuya evidencia dice una lista vacía**: un veredicto
> sobre la capacidad de contar del propio instrumento, no sobre el proyecto. La
> propiedad era cierta por suerte del caso —la constante existe en un sitio— y
> no por lo que el gate midió. Un repo donde nadie declarase la constante
> tendría el mismo veredicto.
>
> La segunda es **la fuga de B13 con el signo cambiado**. Allí el guard leía
> literales en vez de la consulta ensamblada y daba verde **con la fuga
> presente**; aquí leía cadenas en vez de los imports y daba verde **con la
> dependencia presente**. Y lo que se declara es una frontera arquitectónica
> —el núcleo no depende de los recursos, así que añadir un recurso no obliga a
> tocarlo— que **nada vigilaba**.
>
> **LO QUE EL BLOQUE ENCONTRÓ AL MEDIR, Y QUE NO ERA DE B16.**
> `concurrencia real certificada` pasó de PASS a OPEN y **no era ruido del
> medidor**: MEDIDO, 4 corridas rojas de 20 del `test_b2_real_concurrency`, y un
> hijo muerto de 30 con su stderr a la vista —
> `sqlite3.IntegrityError: UNIQUE constraint failed: schema_version.version`.
> Ocho procesos abren la misma base nueva, los ocho leen `MAX(version) == 0`, los
> ocho deciden subir, y el segundo `INSERT` se lleva un UNIQUE sobre la PRIMARY
> KEY y **muere antes de escribir un solo evento**. El `timeout` que arregló el
> `PRAGMA journal_mode` en B2 no lo puede arreglar: no es un candado esperando,
> es un `SELECT` seguido de un `INSERT`, y entre los dos cabe otro proceso. La
> respuesta es la que ya estaba quince líneas más arriba del mismo archivo, en
> las migraciones: **`INSERT OR IGNORE`**, una sola sentencia idempotente, y sin
> el `DELETE` que abría la ventana.
>
> **Y LO QUE NO SE PUDO HACER, MEDIDO Y ESCRITO.** La carrera **no es
> reproducible de forma determinista**: «el hermano sube y luego este sube»
> pasa con el defecto presente, y meter al hermano entre el `DELETE` y el
> `INSERT` con un `set_trace_callback` tampoco, porque SQLite serializa a los
> escritores y lo bloquea hasta agotar el `busy_timeout` —5,07 s frente a 0,15 s,
> y pasa igual con el defecto puesto—. El test que afirmaba reproducirlo sin
> reproducirlo **se ha retirado**: un guard que solo sabe dar verde fabrica
> confianza justo donde no la hay. Lo que queda es el guard de FORMA, que cae
> con el defecto puesto, y la tasa del test concurrente, de 4/20 a **0/25**.
>
> **DONDE SE MIRA, VERIFICADO POR AST:**
>
> | cita | que sostiene |
> |---|---|
> | `measure_b9_gate_1_0.py:635::_capabilities_deterministas` | el vacio no puede salir verde, y se exige EL PUERTO |
> | `measure_b9_gate_1_0.py:504::_ontology_extensible` | decide sobre imports y atributos, no sobre cadenas |
> | `migrations.py:211::_reescribe_version_si_cambia` | una sola sentencia idempotente, sin ventana |
> | `test_b16_vacuous_pass.py:122::TestUnPassSinNadaQueCompararNoEsUnPass` | el vacio, y el contrasalto de que no se rompa |
> | `test_b12_schema_upgrade.py:315::TestDosProcesosQueSubenLaMismaVersionNoSeMateN` | por que solo se mide la forma, y por que se puede |
> | `mutate_b16_vacuous_pass.py` | 6 sondas, 6/6, y dos de ellas no son de B16 |
>
> **RESULTADO:** las dos propiedades reales siguen en **PASS** y el gate no
> cambia de veredicto. Harness **6/6 con 6 causas**, y su propia autocomprobación
> cazó dos sondas que no median: una por leer `ERROR` como «no ha caído» y otra
> por agrupar las suites como cadenas. `tests.total` 3294 -> 3301.
>
> **LO QUE ESTE BLOQUE NO ABRE.** No sube las otras cinco `derivada`: cada una
> es un bloque, y nombrarlas es el orden.
>
> ---

> **Bloque 2026-10-04 (B15) — Un predicado que se declara leyendo código no sabe cuándo deja de medir.**
> (cerrado y publicado en `v0.32.0`)
> Versión activa `0.32.0.dev0`; último tag `v0.32.0`.
>
> **ESTE NO ES UN BLOQUE HACÍA 1.0 TODAVÍA. ES UN BLOQUE SOBRE CÓMO EL GATE
> SABE LO QUE SABE.**
>
> Las dos propiedades que quedan abiertas no se tocan: `runtime real
> certificado` necesita `SG_UAT_REAL_PROVIDER=1` y una credencial real, y
> `TUI operacional` necesita una persona usando un terminal.
>
> **EL HALLAZGO.** El gate de 1.0 declara veinte propiedades, y sus veinte PASS
> salían en la misma lista y con la misma tipografía. **No había manera de saber
> cuáles estaban respaldados por algo que se ejecuta y cuáles por una lectura
> del árbol.** La diferencia no es estética: es si el veredicto **puede volverse
> falso sin que nadie vuelva a mirarlo**. Medido, derivado del AST del propio
> gate: **13 `ejecutada`, 7 `derivada`**.
>
> **Y UNA PROPIEDAD QUE DECÍA PASS SIN COMPROBAR LO QUE DICE COMPROBAR.**
> `distribution reproducible` ejecutaba `check_package_build.py`, que construye
> el paquete, y devolvía PASS con la evidencia *«el wheel y el sdist se
> construyen y llevan lo que declaran»*. Eso prueba que SE CONSTRUYEN.
> Reproducible es que las mismas entradas den los mismos bytes, y un único build
> no puede distinguir «reproducible» de «esta vez salió bien».
>
> **MEDIDO ANTES DE ARREGLAR, con una prueba que tiene dientes:** se construye,
> se espera a que el reloj avance, se toca el mtime de un fuente con contenido
> IDÉNTICO, y se construye otra vez. Los sha256 coinciden —hatchling normaliza
> las fechas—. La propiedad **era cierta**; lo que no existía era nada que
> pudiera quitársela. Por eso el defecto no era de la distribución, era de la
> evidencia.
>
> **LO QUE EL BLOQUE ENCONTRÓ EN SU PROPIA CASA, Y QUE ES LO QUE LE DA
> SENTIDO.** La primera versión de la derivación devolvió **veinte de veinte
> `derivada`**, con la autoridad de un `print` y sin una sola advertencia: los
> predicados se registran en `PREDICADOS` como `_` + slug, la función buscaba el
> slug a secas, no lo encontraba, y **devolvía un valor por defecto** en vez de
> decir «no lo sé». Seis de esos predicados sí lanzan subproceso.
>
> > Un guard que se declara leyendo el código no sabe cuándo deja de medir. B13
> > lo cerró en el guard de SQL, que leía literales en vez de la consulta
> > ensamblada. B14 lo encontró en los guards atados a un valor vivo y en las
> > tres mutaciones no-op de su medidor. **Aquí apareció en el código del propio
> > bloque, y lo primero que produjo fue, en su casa, el falso que venía a
> > cerrar.**
>
> **Y UN DATO DE LA MISMA LÍNEA, MEDIDO.** Al buscar un PASS falso
> —`blueprint legacy completamente probado`, que cuenta cobertura de UAT con un
> `re.findall` sobre el texto de los tests— se construyeron cuatro sondeos para
> comprobarlo. **Las cuatro fallaron, cada una en una dirección distinta**, y
> dieron `0 de 12`, `9 de 12` y `3 de 12` en tres de ellas. El PASS que se
> buscaba era cierto: `tests/uat_audit.py` tiene una función completa por UAT con
> directorios temporales, la CLI de verdad y aserciones. **El predicado es débil;
> la propiedad es cierta**, y queda anotado con su debilidad, que es
> información y no deuda fingida.
>
> **LO QUE ENTREGA Y LO QUE NO.** Entrega: la clase de evidencia, derivada y
> vigilada en las dos direcciones; `distribution reproducible` ejecutada; y una
> lista **nombrada** de las siete propiedades que no se pueden retirar solas,
> que es lo que permite ordenar lo siguiente sin inventarlo. No sube las siete a
> `ejecutada`: cada una necesita un instrumento, y un instrumento es un bloque.
>
> **DONDE SE MIRA, VERIFICADO POR AST:**
>
> | cita | que sostiene |
> |---|---|
> | `measure_b9_gate_1_0.py:122::_grafo_del_modulo` | la clase sale de seguir el grafo, no de una lista |
> | `measure_b9_gate_1_0.py:189::_funcion_del_predicado` | una busqueda que no encuentra LEVANTA |
> | `measure_b9_gate_1_0.py:922::_construye_en` | construye para comparar, no para declarar |
> | `test_b15_evidence_kind.py:119::TestLaClaseSigueAlCodigo` | contrasalto en las dos direcciones |
> | `mutate_b15_evidence_kind.py` | 6 sondas, 6/6, que el harness se autocomprueba |
>
> **RESULTADO:** gate de 1.0 **sin cambios de veredicto**, 18 PASS / 1 OPEN / 1
> NO_MEASURABLE, ahora con la clase de cada una. Harness **6/6 con 6 causas**.
> Autocomprobación del medidor **13 de 20 clases giran**. `tests.total` 3285 ->
> 3294, +9, fichero nuevo entero, y lo fallo el propio guard de WI-115 con el
> texto `tests: STATE declara 3285, el arbol colecta 3294`.
>
> ---

> **Bloque 2026-10-04 (B14) — La autoridad de coherencia se puede engañar, y se engañó.**
> (cerrado y publicado en `v0.31.2`)
> Versión activa `0.31.2.dev0`; último tag `v0.31.2`.
>
> **MEDIDO ANTES DE ESCRIBIR NADA: 7 de 8. MEDIDO AL CERRAR: 8 de 8**, con la
> autocomprobación del instrumento en 3 de 3 y el harness en 6 de 6 con 6 causas
> distintas. La línea base era 7 de 8 y no 0, y esa diferencia es el bloque
> entero: aquí no se empezó porque el verificador mintiera, sino porque **no se
> podía saber si mentía**. Y la honestidad de un verificador al que solo se le
> pregunta «¿es coherente?» no se puede medir: hay que poder obligarlo a
> equivocarse y comprobar que se da cuenta.
>
> **ESTE NO ES UN BLOQUE HACÍA 1.0. ES EL BLOQUE QUE HACE QUE EL VERIFICADOR
> DEL QUE DEPENDEN TODOS LOS DEMÁS PUEDA SER CREÍDO.**
>
> `scripts/project_truth.py` es la respuesta a «¿dónde está el proyecto?». B0 la
> creó, y desde entonces B0..B13 se apoyan en su veredicto de `coherente`. Un
> verificador que dice «coherente» cuando no lo está es PEOR que no tener
> verificador, porque las dos mitades de la propiedad se apoyan en el.
>
> **NO ES HIPÓTESIS: ES UN CASO QUE YA PASÓ EN B13.** Al cerrar B13 se añadió una
> segunda clave `current_workitem` en `STATE.yaml`:
>
> ```
> yaml.safe_load          -> B13_cerrado   (última clave)
> regex de project_truth  -> B13           (primera coincidencia)
> project_truth           -> coherente: true, sin avisar
> ```
>
> Seis ficheros de test leen STATE con `yaml.safe_load`; `project_truth.py` **no
> importaba `yaml` en absoluto** y lo leía entero con regex. Dos lectores del
> mismo fichero discrepando en silencio.
>
> **MEDIDO ANTES DE ESCRIBIR NADA** (`scripts/measure_b14_truth_single_reader.py`,
> mutaciones EN SITIO con restauracion verificada por sha256): **7 de 8**.
> **MEDIDO AL CERRAR: 8 de 8**, y el instrumento tiene su propia
> contramutacion —`--autocomprobacion`, **3 de 3 sondas cazadas**— porque un
> 8/8 que no puede ponerse en rojo no es un 8/8. El harness de los tests es
> **6 de 6 sondas cazadas, 6 causas distintas**. La
> primera version del instrumento dio 7 de 8 en una COPIA temporal, y era
> mentira: la copia no colecta tests, `project_truth` no podía leer el recuento
> real, y todo daba rc=2 — incluidas las siete que contaba como buenas. Un
> instrumento que se pasa a sí mismo porque el entorno no puede correr es la
> forma exacta del falso verde que este repo lleva catorce bloques cazando.
>
> **LO QUE ENTRA.** STATE se lee **una vez** con `yaml.safe_load`, en vez de con
> tres regex que cada una puede encontrar otra cosa. Un loader que **rechaza
> claves duplicadas en el punto de lectura**, no despues con un guard: un guard
> que busca "¿hay dos claves iguales?" seria un segundo lector, que es el
> problema. Y comprobacion de **tipo** en los tres campos, porque con YAML un
> `total: 'muchos'` llegaba al verificador sin que nadie lo mirara.
>
> **TRES COSAS QUE EL BLOQUE ENCONTRO EN SI MISMO, Y QUE IMPORTAN MAS QUE EL
> ARREGLO:**
>
> - **El mecanismo central no lanzaba nunca.** `_construye` hacia
>   `construct_mapping(...)` y luego miraba `Mapping.items()`; y
>   `construct_mapping` ya devuelve un dict donde la clave repetida se colapso.
>   El bucle veia UNA clave, no dos. MEDIDO: con dos `current_workitem`,
>   `_estado()` leía `B99_inventado` sin protestar. Para cuando existe el dict,
>   la informacion de que había dos declaraciones ya no esta: hay que recorrer
>   `node.value`, que son los pares en crudo.
> - **El test de la clave duplicada daba verde aceptando el defecto.** Sin el
>   constructor, YAML toma la ultima y el verificador dice, textual, *«workitem:
>   STATE declara B99_inventado, CURRENT declara B13»*: **elige una de las dos y
>   la publica como la verdad**, atribuyendo la otra a otro fichero. El
>   veredicto SÍ cambia, luego un test de «cambia el veredicto» pasa. Ahora el
>   contrato es «el estado es ILEGIBLE», y hay un contrasalto que comprueba que
>   **no se publica ninguno de los dos valores**.
> - **La medicion usaba el mismo predicado debil**, y por eso daba 8/8 con el
>   mecanismo central roto. Endurecida a exigir `ilegible` nombrando la clave.
>
> > Los tres son de la misma clase que el falso verde que B13 cerro en el gate de
> > 1.0: **un guard que pasa por una causa ajena al objeto que vigila**. Y los
> > tres los manifesto el harness o la sonda manual, no una lectura del codigo.
>
> **LO QUE ESTE BLOQUE NO ABRE.** El PRE-FLIGHT anotó «los otros consumidores con
> regex que quedan en el repo». MEDIDO: **no quedan**. `project_truth.py` era el
> unico consumidor de produccion, y los seis de test ya usaban el parser. Era
> deuda sin verificar, y sin verificar no era deuda.
>
> **LO QUE EL BLOQUE ENCONTRO AL CERTIFICAR, Y QUE ES MÁS DE LO MISMO:**
>
> Instrumento es una palabra engañosa: un instrumento de medición que se pasa a
> sí mismo por un entorno que no puede correr no mide nada, y es la forma exacta
> del falso verde que este repo lleva catorce bloques cazando. Los cinco de
> abajo son el mismo defecto con distinto disfraz —**un predicado que se puede
> satisfacer por una causa que no es la que dice medir**— y los cinco los
> manifesto el harness o la sonda, ninguno una lectura del codigo.
>
> - **Dos guards de los tests estaban atados a `current_workitem: B13` escrito a
>   mano.** Al mover el bloque vivo a B14 los dos dejaron de mutar nada. Uno
>   hacia un `.replace()` que se volvio no-op —el estado se quedaba coherente y
>   el test caia sin que nadie hubiera tocado el verificador—; el otro prohibia
>   el conjunto `{"B13", "B99_inventado"}`, y con el bloque ya en B14 un
>   verificador roto publicaria `B14`: no prohibido, contrasalto verde midiendo
>   el defecto que describe. Los dos derivan ahora el valor del fichero real.
> - **La medicion tenia TRES mutaciones no-op, por el mismo motivo y en el mismo
>   fichero.** Las preguntas 2, 4 y 8 no tocaban el estado, el verificador
>   contestaba `coherente: true` con su respuesta NORMAL a un estado intacto, y
>   el instrumento imprimia **5 de 8 diciendo que el arreglo recién hecho no
>   funcionaba**. Lo que estaba roto era el instrumento. Ahora se derivan del
>   fichero y se ABORTA si la sustitución no aplicó.
> - **Tres de sus ocho preguntas pedían «no es coherente».** Eso lo cumple un
>   modulo roto con la misma facilidad que un modulo que dejó de mirar, y se
>   comprobó: con una sustitución mal escrita el estado era YAML inválido, el
>   verificador salía con rc=2, y la pregunta contaba eso como PASS.
> - **`RAIZ` era una ruta absoluta de esta máquina.** El instrumento mutaba
>   ficheros de un árbol que podía no ser el suyo.
> - **La sonda M1 del harness no media el guard que decía vigilar.** Mutaba una
>   función a una referencia a `_TAG_STATE`, que este mismo bloque borró: el
>   modulo reventaba con `NameError`, caían los DIEZ tests, ninguno el
>   diagnosticado. El harness la declaró INVALIDA, que es lo que distingue a una
>   sonda que mide de una que rompe. Ahora reinsta un reader FUNCIONAL.
>
> **Y UN DEFECTO DE VERDAD, NO DE INSTRUMENTO.** Al endurecer la pregunta que
> detecta una versión incoherente apareció esto: con `__init__.py` mutilado,
> pytest no termina la colecta, imprime «2867 tests collected, 27 errors» y sale
> con rc=2. Ese número es real —son los tests que llegó a ver— pero no es EL
> recuento, y `tests_colectados()` lo publicaba con su nombre:
>
> ```
> tests: STATE declara 3284, el arbol colecta 2867
> ```
>
> Sin 417 tests y sin decir por qué. Un número que no se pudo medir no es un
> número: es el de otra magnitud. Ahora se niega a leerlo. El fallo va en la
> dirección SEGURA —dice que no cuadra cuando sí cuadra—, así que no es el
> defecto que B14 persigue; se arregla porque la autoridad de coherencia
> hablando de un número que no contó es del mismo género que ella hablando de
> una coherencia que no midió. M6 del harness comprueba que sin esa negativa
> cae el test.
>
> **Y UNA LECCIÓN QUE CASO LA HIZO EL INSTRUMENTO CONTIGO A SÍ MISMO.** La
> primera ejecución de `--autocomprobacion` reventó a mitad —restauraba dos
> veces, y la segunda ya no encontraba la copia— y **dejó `project_truth.py` sin
> el constructor de claves duplicadas**, con el repo entero en `coherente: false`
> y sin que nadie lo dijera. La red que verifica por sha256 no cubría el
> fichero que el instrumento más deforma. `scripts/project_truth.py` entra ahora
> en `MUTABLES`: una red que no cubre lo que deforma no es una red.
>
> > **La sonda 3, con la deformación puesta, deja ver el defecto central de B14
> > a la vista:**
> >
> > ```
> > "coherente": true,  "contradicciones": [],
> > "workitem_current": "B14",  "workitem_state": "B99"
> > ```
> >
> > El verificador publicando como coherente un estado en el que STATE y CURRENT
> > dicen cosas distintas. Eso, y no el arreglo del loader, es lo que B14
> > existía para cerrar.
>
> **CITAS VERIFICADAS** (`fichero.py:LINEA::simbolo`, comprobadas por AST):
>
> | cita | que sostiene |
> |---|---|
> | `project_truth.py:120::_SinClavesDuplicadas` | el loader que no elige en silencio |
> | `project_truth.py:124::_construye` | recorre `node.value`, no el dict ya colapsado |
> | `project_truth.py:150::_estado` | la lectura UNICA por la que pasa todo |
> | `test_b14_truth_single_reader.py::TestUnaClaveDuplicadaNoPasaPorAlto` | el contrato: ilegible, no «elige una» |
> | `test_b14_truth_single_reader.py::TestElEstadoSeLeeDeUnaSolaManera` | no queda reader por regex ni segunda lectura |
> | `measure_b14_truth_single_reader.py::Arbol` | restaura y COMPRUEBA el sha256 |
> | `mutate_b14_truth_single_reader.py:77::_sin_trabajo_sin_commitar` | «restaurar» y «borrar» son lo mismo |
> | `test_b14_truth_single_reader.py::TestUnRecuentoQueNoSeTerminoNoSePublica` | un numero de una colecta a medias no se publica |
> | `measure_b14_truth_single_reader.py::Arbol` | restaura el VERIFICADOR tambien, y lo comprueba |
>
> **GATE DE 1.0: sin cambios, 18 PASS / 1 OPEN / 1 NO_MEASURABLE** (MEDIDO con
> `scripts/measure_b9_gate_1_0.py` al cerrar), que es lo correcto: B14 endurece
> la autoridad de coherencia de B0, no una propiedad de 1.0. `coherente: true`
> con `tests.total` cuadrando contra el árbol: 3285 declarados, 3285 colectados.
>
> ---
>
> **Bloque 2026-10-04 (B13) — El modelo de amenaza AFIRMABA que no habia fuga. Y habia una.**
> (cerrado y publicado en `v0.31.1`; evidencia en
> `evidence/sddk-b13-gate-report-2026-10-04.json`)
> Versión activa `0.31.1.dev0` (ya fuera del tag `v0.31.1`); último tag
> `v0.31.1`.
>
> **MEDIDO ANTES DE ESCRIBIR NADA** (`/tmp/b13_measure.py`): **0 de 5 preguntas
> en PASS**. Y la primera no es documental. Se inserta un `DomainPack` del
> tenant T1 en una base real, se pide desde T2, y **la fila de T1 vuelve**:
> *T2 recibio `['dp-de-t1']`*. No es un analisis del SQL: es una fila que cruzo.
>
> **LA CAUSA, Y POR QUE NADIE LA VIO.** `platform/knowledge_repository.py:196::list_resources`
> armaba el filtro sin parentesis. En SQL `AND` liga mas fuerte que `OR`, luego la
> segunda mitad del `OR` se come el `tenant_id` **y** el `project_id`, y devuelve
> cualquier fila de cualquier tenant con ese `kind`. Y **era alcanzable**:
> `cli/support.py:299::_build_registry_for_project` llama
> `list_resources(..., kind="DomainPack")`.
>
> **B11 ENCONTRO ESTE DEFECTO Y NO LO ARREGLO**, porque esquivarlo era la
> decision correcta para su bloque: necesitaba aislamiento fila a fila, y por
> eso lo comprobo asi. Lo que fallo es que la puerta se quedo abierta y el
> ADR-0015 —que en S1 decia, textual, *«las queries filtran por tenant_id,
> project_id en todos los paths verificados», estado OK* — la declaraba
> CERRADA.
>
> > Un modelo de amenaza que llama `OK` a una fuga que existe no es un modelo
> > caducado: es un modelo que dice lo contrario de la verdad.
>
> **LO QUE ENTRA.** (1) La fuga, **arreglada**: dos parentesis, con el porque
> escrito en el propio metodo y no en un comentario que alguien puede borrar.
> (2) Un guard **general** sobre el SQL que sale al motor, derivado por
> `set_trace_callback`: ninguna lectura con un `OR` sin agrupar, y toda lectura
> mencionando `tenant_id`. (3) Un contrasalto de **cobertura derivado del
> arbol**: solo 4 superficies combinan `tenant_id` con un filtro `kind` —la
> unica via por la que un `AND` se vuelve opcional— y una superficie nueva que
> admita esa combinacion tiene que entrar en la lista.
>
> **EL GUARD MIDE LA CONSULTA, NO EL TEXTO.** La primera version recorria
> literales y daba verde **con la fuga presente**, porque `WHERE` y `OR` estan
> en literales distintos y la frase solo existe ensamblada. Un guard que
> busca texto mide el texto.
>
> **EL ADR, ADEMAS, SE CONTRAIDIA A SI MISMO:** marcaba el adapter real
> HTTP/LLM como «E1, sin implementar, fuera de alcance» y a la vez le
> dedicaba una seccion S8 entera, marcandolo CERRADO. Y no nombraba tres
> superficies que el producto tiene desde B8: los packs instalables —que
> admiten contenido de fuera del proyecto, y es una frontera de confianza que
> el modelo no mencionaba—, la carga de planes y bricks, y el registro de
> instalaciones. Entran **S9 y S10**, con su amenaza y sus gaps, y una seccion
> `Superficies` con una fila por cada uno de los **10 paquetes del arbol**,
> cada una nombrando el fichero de test que la sostiene.
>
> **UN PREDICADO DEL GATE QUE MEDIA UNA FOTO.** La vigencia del modelo se
> comprobaba **comparando un numero de tests**. Un numero caduca con cada
> commit sin que nadie toque el analisis, y un gate que se pone rojo por
> causas ajenas al objeto que vigila ensena a ignorarlo. Ahora el predicado
> **EJECUTA** `tests/test_b13_threat_model.py` y decide por su resultado, y se
> verifico **en las dos direcciones con causas distintas**: quitar la fila de
> `packaging` de la tabla da `OPEN` con **1** fallo; reabrir la fuga da `OPEN`
> con **3** fallos.
>
> **CITAS VERIFICADAS** (`fichero.py:LINEA::simbolo`, comprobadas por AST):
>
> | cita | que sostiene |
> |---|---|
> | `knowledge_repository.py:196::list_resources` | la superficie con la fuga, ya agrupada |
> | `knowledge_repository.py:241::add_relation` | otra superficie que combina `kind` y `tenant_id` |
> | `knowledge_repository.py:450::find_entity` | tercera |
> | `knowledge_repository.py:640::list_resource_refs_for_run` | cuarta: son exactamente 4 |
> | `test_b13_threat_model.py:39::_or_de_nivel_superior` | el predicado, sobre la consulta ensamblada |
> | `test_b13_threat_model.py:92::TestLaFugaCrossTenant` | la fuga, **ejecutada**: T1 y T2 de verdad |
> | `test_b13_threat_model.py:198::test_toda_superficie_con_filtro_de_kind_esta_cubierta` | contrasalto de COBERTURA, derivado del arbol |
> | `test_b13_threat_model.py:214::test_ninguna_lectura_ejecuta_un_where_con_or_suelto` | el guard general sobre el SQL real |
> | `test_b13_threat_model.py:251::test_el_predicado_ve_un_or_suelto_y_respeta_un_agrupado` | el contrasalto del propio predicado |
> | `test_b13_threat_model.py:290::test_todo_paquete_del_arbol_tiene_fila_en_el_adr` | la tabla de superficies no se queda corta |
> | `test_b13_threat_model.py:301::test_el_adr_no_declara_un_numero_de_tests_como_su_vigencia` | el ADR no repite el error del gate |
> | `test_b13_threat_model.py:318::test_el_analisis_tiene_una_seccion_de_superficies` | la seccion se comprueba como ENCABEZADO, no como subcadena |
> | `test_b13_threat_model.py:386::test_cada_superficie_nombra_una_evidencia_que_existe` | cada «OK» nombra su prueba, y existe |
> | `test_b13_threat_model.py:421::test_el_adapter_no_puede_estar_fuera_de_alcance_y_cerrado` | la contradiccion, resuelta |
> | `test_b13_threat_model.py:452::test_el_adr_no_puede_decir_que_no_toca_codigo_mientras_lo_toca` | la TERCERA contradiccion, la mas discreta: decir que no se toca codigo |
> | `measure_b9_gate_1_0.py:614::_security_threat_model_actualizado` | el gate corre el guard y decide por su rc |
> | `mutate_b13_threat_model.py:165::_sucios` | la suite verde NO es el arbol restaurado |
> | `mutate_b13_threat_model.py:129::_colectados` | el harness rechaza arrancar si un diagnostico no existe |
>
> **CERRADO, CERTIFICADO Y PUBLICADO.** `v0.31.1` sale en `4d66e41`;
> `origin/main` en `a7eda50`, verificado con `git ls-remote`, con 0 commits sin
> publicar. Suite sobre el árbol ya commiteado: **3268 passed, 3 skipped, 0
> failed**. Evidencia: `evidence/sddk-b13-gate-report-2026-10-04.json`. Ciclo
> `p-b7740b96d79ec013/b13` en **PAUSED**, no CLOSED ni BLOCKED: los gates de
> deuda no son evaluables en esta build y no hay bloqueo externo.
>
> **GATE DE 1.0: 17 PASS / 2 OPEN / 1 NO_MEASURABLE -> 18 / 1 / 1.** Quedan
> `runtime real certificado` (credencial real) y `TUI operacional`
> (NO_MEASURABLE).
>
> **HARNESS: 6/6 sondas cazadas, 6 causas distintas.** Dos NACIERON ROTAS y
> las cazó el propio harness antes de contarlas, que es lo que un contador
> de sondas no hace:
>
> - **M5** declaraba sus dos diagnósticos con el nombre de la clase mal
>   escrito (`TestElModeloNoSecontradice` por `TestElModeloNoSeContradice`).
>   El harness lo|reportaba `[CAZADA]` igual: `caidos & esperados` no está
>   vacío mientras caiga **uno** de los dos, luego un nombre que no existe no
>   produce un fallo sino una causa más corta.
> - **M4** usaba `## Superficies` como ancla, y aparece **dos veces**: como
>   encabezado y dentro de una mención en prosa. `replace(..., 1)` se comía
>   la prosa, que no es lo que la sonda quiere deshacer.
>
> El harness ahora **rechaza arrancar** si un diagnóstico no existe o si un
> ancla no es única, y se comprueba a sí mismo antes de mutar nada. Es el
> mismo defecto que vigila, un nivel más abajo.
>
> **UNA CONTRADICCION MAS, ENCONTRADA AL REESCRIBIR EL ADR.** Sus
> consecuencias decían que el documento «no introduce cambios de código»,
> y el bloque que lo revisaba acababa de arreglar una fuga: la tercera
> versión de la misma mentira que S1, y la más discreta, porque no se
> contradice con otra frase suya — se contradice con lo que el repositorio
> hizo. El guard no busca la frase literal sino la **afirmación**, y cazar
> la redacción de su propia corrección (que citaba la frase falsa para
> explicarla) es la razón por la que está escrito así y no con un `in`.
>
> **LO QUE NO SE EXPLICÓ, DICHO COMO NO SE EXPLICÓ.** Una corrida del hook
> de pre-commit sobre este árbol dio `3 failed, 3264 passed`. Cinco corridas
> completas posteriores sobre el **mismo árbol** dieron `3267 passed, 0
> failed` cada una, y con el índice sucio (el estado en que estaba el hook)
> también. No se reproduce y **no se ha identificado la causa**. Se registra
> aquí sin maquillar: un verde posterior no borra un rojo anterior, y llamar
> «intermitente» a algo que no se ha dejado de ver sería sustituir una
> incógnita por una palabra.
>
> **LO QUE ESTE BLOQUE NO AFIRMA HABER MEDIDO.** Que la ausencia de un `OR`
> suelto cubra el aislamiento entre tenants. El guard es una heuristica sobre
> el texto de la consulta: no sabe de subtiles, ni de `LEFT JOIN` que
> reintrodUCE filas, ni de funciones que construyan el filtro dentro. Lo que
> si se sostiene es la fuga concreta, que se **ejecuta** contra dos tenants
> reales, y que ninguna superficie nueva pueda entrar sin que su `kind` la
> haga cubierta por el contrasalto de cobertura.
>
> ---
>
> **Bloque 2026-10-04 (B12) — La version del esquema era una constante, y por eso el upgrade era imposible.**
> Versión activa `0.31.0.dev0` (ya fuera del tag `v0.31.0`); último tag
> `v0.31.0`.
>
> **MEDIDO ANTES DE ESCRIBIR NADA** (`/tmp/b12_measure.py`, y despues
> `scripts/measure_b12_schema_upgrade.py`): **0 de 5 preguntas en PASS**, y
> **5 de 5** al final. Lo que encontro, textual:
>
> - `SCHEMA_VERSION = 1`, sin moverse en **73 releases**.
> - Se escribia con `INSERT OR IGNORE` y **no se leia en ningun sitio de
>   `platform/`**. El unico `SELECT version FROM schema_version` del repo
>   esta en `resources/catalog.py`, que es otro store.
> - **Borrar la tabla `schema_version` entera de una base y abrirla no daba
>   ningun error**: el codigo la recreaba en silencio. Una version que se
>   regenera cuando falta es un `DEFAULT`, no un hecho.
> - La unica migracion que existia era una funcion escrita a mano **para una
>   tabla**, porque SQLite no tiene `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
>
> **LO QUE ENTRA:** un libro de migraciones con identificadores estables; la
> version **derivada** de la lista, luego no se puede olvidar subirla; la
> migracion de `claims.assertion_origin` convertida de metodo privado del
> facade en la primera del libro —**el metodo se borra y hay un test que lo
> comprueba**—; `Storage.version_esquema()` y
> `Storage.migraciones_aplicadas()`, que responden «¿qué versión tiene este
> proyecto?» por el DATO de la base; y `SchemaTooNewError` para que una base
> mas nueva que el codigo **falle** en vez de abrirse en silencio.
>
> **LA DECISION DE DISENO, que es lo que mas se discutira: EL LIBRO
> REGISTRA, NO GOBIERNA.** `sincroniza` ejecuta *todas* las migraciones y
> anota las que faltaban. Podria haber guardado ejecutando solo las
> pendientes, y seria mas eficiente. Se eligio lo contrario por el caso que
> de verdad duele: una base restaurada de una copia parcial tiene el libro
> atrasado **y** el esquema con una columna que falta a la vez, y un libro que
> gobierna se creeria que esta bien y no repararia nada.
>
> **UNA REGRESION QUE EL BLOQUE INTRODUJO Y CORRIGIO, MEDIDA.** La primera
> version hacia `DELETE FROM schema_version` + `INSERT` SIEMPRE. Antes era
> `INSERT OR IGNORE`, que tras la primera apertura no escribe nada, luego
> abrir una base era una LECTURA. Con el `DELETE` incondicional, ocho procesos
> concurrentes se repartian mal el turno de escritura: *«se esperaban 8 autores
> distintos y hay 7»*. MEDIDO antes de arreglar: tres corridas dan verde,
> verde y ROJO. El contrasalto que lo vigila mide `total_changes`, que es
> determinista —abrir una base al dia da 0, subir una atrasada da 1— porque
> contar ejecuciones verdes de un test de concurrencia seria una tirada, no
> una prueba.
>
> **UN PREDICADO DEL GATE QUE MENTIA EN LA DIRECCION CONTRARIA.**
> «upgrade desde releases soportadas» buscaba `def upgrade` con un regex. La
> capacidad se llama `sincroniza`, luego B12 habria entregado la capacidad y
> el gate habria seguido diciendo `OPEN`: un falso **negativo**, la misma clase
> que el falso positivo de B9 con el signo cambiado. Ahora el predicado
> **ejecuta** el medidor y decide por su codigo de salida, y se verifico en las
> dos direcciones: capacidad entera da `PASS`, libro roto da `OPEN 3/5`.
>
> **CERRADO, CERTIFICADO Y PUBLICADO.** `v0.31.0` sale en `2567532`;
> `origin/main` en `afce3e8`, verificado con `git ls-remote`, con 0
> commits sin publicar. Suite sobre el árbol ya commiteado: **3251
> passed, 3 skipped, 0 failed**. Evidencia:
> `evidence/sddk-b12-gate-report-2026-10-04.json` (artefacto SDDK
> `art-ef6c915f8ba8-e9bc0dd0`). Ciclo `p-b7740b96d79ec013/b12` en
> **PAUSED**, no CLOSED ni BLOCKED: los gates de deuda no son evaluables
> en esta build y no hay bloqueo externo.
>
> **GATE DE 1.0: 16 PASS / 3 OPEN / 1 NO_MEASURABLE -> 17 / 2 / 1.** Quedan
> `runtime real certificado` (credencial), `security/threat model actualizado`
> (reescribir un ADR) y `TUI operacional` (NO_MEASURABLE).
>
> **CITAS VERIFICADAS** (`fichero.py:LINEA::simbolo`, comprobadas por AST):
>
> | cita | que sostiene |
> |---|---|
> | `migrations.py:111::MIGRACIONES` | la lista, en orden de aplicacion |
> | `migrations.py:117::version_declarada` | la version es `len(...)`, no un literal |
> | `migrations.py:147::comprueba_que_no_sea_mas_nueva` | una base mas nueva falla |
> | `migrations.py:164::sincroniza` | el libro REGISTRA, no gobierna |
> | `migrations.py:211::_reescribe_version_si_cambia` | abrir una base al dia no escribe |
> | `schema.py:44::SCHEMA_VERSION` | la version derivada |
> | `storage.py:470::_migrate` | DDL, comprobar, y luego el libro |
> | `storage.py:492::version_esquema` | la pregunta, respondida por el dato |
> | `storage.py:503::migraciones_aplicadas` | que migraciones tiene la base |
> | `errors.py:60::SchemaTooNewError` | el fallo es del dominio, no de sqlite3 |
> | `test_b12_schema_upgrade.py:250::test_abrir_una_base_al_dia_no_escribe_nada` | contrasalto de la regresion |
> | `test_b12_schema_upgrade.py:385::test_una_base_sin_esa_columna_la_recupera` | el libro REPARA, no solo anota |
> | `test_b12_schema_upgrade.py:397::test_storage_no_tiene_ya_el_metodo_ado_hoc` | el caso especial desaparece del facade |
> | `measure_b12_schema_upgrade.py:81::preguntar` | el medidor EJECUTA, no mira nombres |
> | `mutate_b12_schema_upgrade.py:114::_sucios` | la suite verde NO es el arbol restaurado |
> | `measure_b9_gate_1_0.py:571::_upgrade_desde_releases_soportadas` | el gate corre el medidor y decide por su rc |
>
> **HARNESS: 5/5 sondas cazadas, 5 causas distintas, y UNA NACIO ROTA.** M4
> apuntaba a una linea que `ruff format` habia movido al refactorizar, y el
> harness la reporto `[SIN SONDA]` en vez de contarla como verde. Es el error
> 32 de WI-113 repetido, detectado por el harness y no por una suposicion.
>
> **LO QUE ESTE BLOQUE NO AFIRMA HABER MEDIDO.** Que una base creada por una
> release de hace dos años conserve su contenido. La base «vieja» del medidor
> se RECONSTRUYE quitando lo que esa release no conocia; no es una base real
> de una release real. Lo que si se mide es que se abre, se sube, se
> versiona y no pierde filas.
>
> ---
>
> **Bloque 2026-10-04 (B11) — El ciclo de vida de los packs, que era un nombre en un gate.**
> (cerrado y publicado en `v0.30.0`; evidencia en
> `evidence/sddk-b11-gate-report-2026-10-04.json`)
> Versión activa `0.30.0.dev0` (ya fuera del tag `v0.30.0`); último tag
> `v0.30.0`.
>
> **CERRADO, CERTIFICADO Y PUBLICADO.** `v0.30.0` sale en `0fb0617`;
> `origin/main` en `29698cd`, verificado con `git ls-remote`, con 0
> commits sin publicar. Suite sobre el árbol ya commiteado: **3230
> passed, 3 skipped, 0 failed**. Gate de 1.0: 15 PASS / 4 OPEN / 1
> NO_MEASURABLE → **16 / 3 / 1**. Evidencia:
> `evidence/sddk-b11-gate-report-2026-10-04.json`. Ciclo SDDK
> `p-b7740b96d79ec013/b11` en **PAUSED** (no CLOSED ni BLOCKED: los gates
> de deuda no son evaluables en esta build, y no hay bloqueo externo).
>>
> **B11 cierra la primera de las cuatro `OPEN` que piden CODIGO, no
> certificacion.** El predicado del gate decia, textual: `sg pack` expone
> `['import', 'load']` y no `['install', 'update', 'remove']`. B8 entrego el
> CONTRATO —`PackManifest`, `Requires`, seis tipos, tres niveles de
> aislamiento, `es_compatible` con MOTIVOS—; faltaba la mitad: saber QUE hay
> instalado.
>
> **MEDIDO ANTES DE ESCRIBIR NADA** (`scripts/measure_b11_pack_lifecycle.py`):
> **5 de 5 preguntas ABIERTAS**, y 5 PASS al final. El instrumento EJECUTA la
> CLI en un proyecto de verdad en vez de mirar nombres, porque un predicado
> que comprueba tres nombres fijos dice «cumple» el dia que alguien escriba
> los tres en el parser sin que exista el ciclo entero.
>
> **UN DEFECTO DE PRODUCCION, Y ES EL QUE HACIA EL UPDATE IMPOSIBLE.**
> MEDIDO: `upsert_resource` RECHAZA cambiar el `spec` bajo la misma identidad
> con `IdentityConflictError` —deliberado, es lo que hace un recurso
> inmutable—, y un update de pack es por definicion un `spec` distinto bajo
> la misma identidad. No es un bug heredado: es que **UNA INSTALACION NO ES
> UN RECURSO**. El recurso es el CONTENIDO del pack; la instalacion es el
> HECHO de que ese pack este vivo en este proyecto, y ese hecho tiene su
> propio ciclo. De ahi la tabla `installed_packs` y su repositorio propio.
>
> **`retirar` NO borra: MARCA.** Un `DELETE` perderia la unica respuesta que
> existe a «¿este proyecto ha tenido alguna vez este pack?», porque el unico
> sitio donde vive la respuesta es la fila que se borra. Marcar es el
> `DELETE` mas su historia.
>
> **Y UN HALLAZGO SOBRE UN FILTRO QUE NO FILTRA.** `list_resources` construye
> su filtro de kind como `AND api_version || '/' || kind = ? OR kind = ?`,
> SIN parentesis: el `OR` se come el `AND` que lo precede. Delegar el
> aislamiento ahi habria costado una fuga entre tenants, asi que se comprueba
> fila a fila y hay dos guards que lo verifican en las dos direcciones.
>
> **EL HARNESS VOLVIO A DESTRUCTIRSE, Y POR ESO LLEVA UN GUARD NUEVO.**
> `MUTABLES` no incluia `installed_packs_repository.py`, luego esa sonda muto
> el fichero y no lo restauro — y el harness reporto «arbol restaurado y
> ejecutando como estaba» porque **LA SUITE SEGUIA VERDE**. Es el fallo de B9
> repetido con otro disfraz, y la leccion de ahi era que comprobar la suite no
> basta: el veredicto final mira ahora LAS DOS COSAS, que la suite pase y que
> `git status` de los mutables este limpio. Dos sondas mas salieron del
> harness y no del codigo: una apuntaba al filtro de ESTADO del SQL, que es
> REDUNDANTE porque `RegistroDePacks.instalados` vuelve a filtrar, luego no
> habia nada que un test pudiera ver; y dos expectativas estaban mal
> escritas, una nombrando la clase equivocada, que hace que una sonda salga
> PARCIAL aunque el fallo este detectado a la perfeccion.
>
> **UN HUECO DE COBERTURA REAL**, que la sonda de compatibilidad destapo: el
> recorrido de la CLI instalaba packs COMPATIBLES, luego el camino que ve el
> operador no estaba cubierto para el caso que duele. Dos tests lo cubren.
>
> **RESULTADO: 6/6 sondas con 6 causas distintas, 3233 tests, y el gate de
> 1.0 pasa de 15 PASS / 4 OPEN a 15 PASS / 3 OPEN** (`pack/controller
> lifecycle` sale de la lista; `roadmap/state/docs coherentes` entra y sale
> con el `tests.total` del final de bloque).
>
> Instrumento: `scripts/measure_b11_pack_lifecycle.py`. Harness:
> `scripts/mutate_b11_pack_lifecycle.py` (6/6, 6 causas distintas). Guards:
> `tests/test_b11_pack_lifecycle.py` (20 tests, cinco conjuntos disjuntos).
>
> installed_packs_repository.py:53::listar      el WHERE de verdad, con tenant y proyecto
> installed_packs_repository.py:81::guardar     la constraint decide, no el codigo
> installed_packs_repository.py:112::marcar_retirado  devuelve cuantas filas cambio
> pack.py:249::cmd_pack_install
> pack.py:265::cmd_pack_remove
> pack.py:290::cmd_pack_list
> test_b11_pack_lifecycle.py:285::test_update_compara_por_numero_y_no_por_texto
> test_b11_pack_lifecycle.py:340::test_la_fila_sigue_ahi_despues_de_retirar
> test_b11_pack_lifecycle.py:439::test_el_registro_no_muestra_packs_de_otro_tenant
> test_b11_pack_lifecycle.py:492::test_la_tabla_nace_en_una_base_creada_por_el_esquema_anterior
> measure_b11_pack_lifecycle.py:385::preguntar   ejecuta la CLI, no mira nombres
> mutate_b11_pack_lifecycle.py:111::_sucios     la suite verde NO es el arbol restaurado
>
> NOTA SOBRE LO QUE NO SE CITA: `packaging/registry.py` —donde viven
> `instalar`, `actualizar`, `retirar` y la comparacion de versiones— NO
> aparece en la tabla, y es a proposito: el guard de WI-92 resuelve por
> BASENAME y hay dos `registry.py` en el arbol (`resources/` y `packaging/`),
> luego la cita seria ambigua y el guard la rechaza. Es el mismo caso que
> `core/__init__.py` en B10, con catorce `__init__.py`. Las propiedades las
> comprueban los tests, que si tienen nombre unico.
>
> ---
>
> **Bloque 2026-10-04 (B10) — Las superficies públicas, declaradas y certificadas.**
> (cerrado; ver arriba el bloque vivo B11)
>
> **B10 cierra las dos `OPEN` que estaban abiertas SOLO por falta de
> certificacion.** B9 dejo el gate en 13 PASS / 6 OPEN / 1 NO_MEASURABLE.
> Dos de las seis OPEN —`resource/controller API estable` y `CLI estable`—
> no estaban abiertas por falta de codigo: `skillgraph.core` no declaraba
> `__all__` y no existia el snapshot de la CLI. Once comandos de primer
> nivel podian cambiar sin que nada lo notara.
>
> **LO IMPORTANTE NO ES LO QUE HACE, ES LO QUE SE LE OPUSO.** Las dos se
> cerraban en veinte segundos: se escribia un `__all__` y se hacia `touch`
> sobre el fichero de la declaracion. Los predicados de B9 comprobaban la
> EXISTENCIA del fichero, y un `is_file()` es lo mas facil de falsificar
> que hay. Un `touch` les daba PASS a los dos, con el gate de 1.0
> exactamente igual de lejos. Por eso el guard EJECUTA la comparacion en
> vez de mirar el fichero, y las dos superficies se GENERAN desde el arbol
> con `--actualizar`.
>
> Verificado en las cuatro direcciones que importan: snapshot vacio ->
> OPEN en las dos · comando quitado del snapshot -> OPEN · superficie real
> movida -> OPEN · estado de verdad -> PASS en las dos.
>
> **DEFECTO DEL PROPIO GUARD, MEDIDO AL ESCRIBIRLO.** La primera version
> comparaba los comandos de la CLI en UNA sola direccion
> (`reales - declarados`): anadir un comando INVENTADO al snapshot pasaba
> en verde. Un guard que solo sabe detectar que el arbol crecio no vigila la
> declaracion, y la declaracion es justamente lo que dice «esto es lo que
> hay». Ahora compara en las dos direcciones.
>
> **MEDIDO, 15 PASS / 4 OPEN / 1 NO_MEASURABLE.** Con el `tests.total`
> todavia sin actualizar la cuenta intermedia fue 14/5, y el `OPEN` que
> sobraba era `roadmap/state/docs coherentes`, que es precisamente el
> `tests.total` (estado 3176, arbol 3195). Puesta la cifra con el run ya
> ejecutado, esa propiedad vuelve a `PASS`. Las cuatro que quedan no
> dependen de certificacion: `pack/controller lifecycle` y `upgrade desde
> releases soportadas` piden codigo que no existe, `runtime real
> certificado` pide una credencial, y `security/threat model actualizado`
> pide reescribir un ADR caducado.
>
> Instrumento: `scripts/check_public_surfaces.py`. Harness:
> `scripts/mutate_b10_public_surfaces.py` (6/6, 6 causas distintas). Guards:
> `tests/test_b10_public_surface.py` (19 tests, cinco conjuntos disjuntos).
>
> check_public_surfaces.py:107::evaluar_core_declarado  la superficie es la UNION de los modulos
> check_public_surfaces.py:156::evaluar_core_snapshot   un `touch` no produce un snapshot valido
> check_public_surfaces.py:212::evaluar_cli_snapshot    compara en las DOS direcciones
> check_public_surfaces.py:303::evaluar_superficies_versionadas  por fichero, contra git ls-files
> mutate_b10_public_surfaces.py:84::_sin_trabajo_sin_commitar  «restaurar» y «borrar» son lo mismo
> test_b10_public_surface.py:301::test_un_comando_inventado_en_el_snapshot_no_pasa  la direccion que faltaba
> test_b10_public_surface.py:139::test_los_simbolos_reexportados_son_los_mismos_objetos  reexportar, NO copiar
>
> NOTA SOBRE LO QUE NO SE CITA: `core/__init__.py` —donde vive la superficie y
> la reexportacion por identidad— NO aparece en la tabla de citas, y es a
> proposito. El guard de WI-92 resuelve una cita por BASENAME, y hay
> CATORCE `__init__.py` en el arbol: la cita seria ambigua y el guard la
> rechaza. Citar el fichero por su ruta completa tampoco vale, porque la
> busqueda es por nombre de fichero. La propiedad —la superficie es la
> UNION de los tres `__all__` y los simbolos se reexportan por identidad— la
> comprueban `test_b10_public_surface.py::test_la_superficie_es_la_union_de_los_tres_modulos`
> y `::test_los_simbolos_reexportados_son_los_mismos_objetos`, que leen el
> modulo de verdad.
>
> ---
>
> **Bloque 2026-10-04 (B9) — El gate de 1.0 deja de ser una lista en prosa.**
> (cerrado; ver arriba el bloque vivo B10)
>
> **B9: `ROADMAP.md` dice, textual, que `v1.0.0` solo existe cuando se
> cumplan TODAS sus propiedades, y a continuacion lista veinte. Era la
> afirmacion mas fuerte del repositorio y la unica sin nada que la
> comprobara.** Veinte afirmaciones sin predicado no son veinte riesgos: son
> un documento. Es la misma forma que B0 senalo en un campo de estado, con
> veinte sujetos en vez de uno.
>
> **MEDIDO, no supuesto.** `scripts/measure_b9_gate_1_0.py` deriva las
> veinte del propio roadmap —la lista no esta escrita en el script, y una
> propiedad nueva que no sepa medir sale como `NO_MEDIBLE` en vez de pasar
> en verde— y ejecuta un predicado por cada una:
>
> ```
> 13 PASS · 6 OPEN · 1 NO_MEASURABLE · 0 NO_MEDIBLE
> listo_para_1_0: false
> ```
>
> **LO QUE DESTAPO, Y NO ERA UN NUMERO.** Al medir «concurrencia real
> certificada» salio `OPEN` con 1 de 5 corridas en rojo. MEDIDO en detalle:
> 1 ronda de 12, con **3 de 8 hijos muertos** y 50 de 80 filas escritas.
> El defecto de produccion era el mismo que B2 abrio y no termino de
> cerrar: `Storage.__init__` ejecutaba `PRAGMA journal_mode = WAL` en
> cada apertura, y el PRAGMA es idempotente pero **toma un lock de
> escritura para averiguar que no hace nada**. Con ocho procesos abriendo
> a la vez, uno moria con `database is locked` ANTES de escribir, y sus
> escrituras se perdian sin excepcion en el padre y sin log.
>
> B2 lo arreglo con un reintento, y el reintento no bastaba. Lo que
> faltaba era la otra mitad de lo que ya decia su propio comentario —«la
> solucion es no preguntar»—: **preguntar** el modo con
> `PRAGMA journal_mode` a secas, que es una LECTURA y no pide el lock
> exclusivo. Con eso, releer entre reintentos y dormir entre ellos (que
> `journal_mode` ignora el `busy_timeout`: devuelve `SQLITE_BUSY` de
> inmediato). Vive en `src/skillgraph/platform/journal.py`, no en
> `storage.py`, que esta bajo las 800 lineas por un guard de WI-65.
> MEDIDO con el mismo escenario que antes fallaba: **40 rondas de ocho
> procesos abriendo una base nueva a la vez, sin un solo fallo.**
>
> **LA SEGUNDA MITAD DEL HALLAZGO: LA PUERTA DE LOS HIJOS.** Lanzar ocho
> procesos en un bucle no los hace competir, solo los hace empezar, y cada
> uno tarda lo que tarde en arrancar. MEDIDO: 4 de 20 corridas del modulo
> de concurrencia fallaban, y el que caia no era el de solape sino el de
> autores, porque un hijo habia muerto sin que nadie se enterara —el test
> descarta el resultado de `_procesos`—. Los hijos ahora escriben su
> fichero de «listo» y esperan a que el padre abra la puerta, y el padre
> no abre hasta tenerlos a todos. 0 de 20 y 0 de 25 tras el cambio.
>
> **LAS SEIS OPEN, Y POR QUE CADA UNA PIDE COSAS DISTINTAS.**
> `resource/controller API estable` y `CLI estable`: no hay superficie
> declarada contra la que comparar, asi que estan OPEN por falta de
> certificacion, no por defecto. `runtime real certificado`: necesita
> `SG_UAT_REAL_PROVIDER=1` y una credencial, y se ve en el `skip` del
> propio UAT. `pack/controller lifecycle` y `upgrade desde releases
> soportadas`: son trabajo de B8 y de B9 respectivamente, no defects.
> `security/threat model actualizado`: el ADR-0015 se aprobo describiendo
> un proyecto de 830 tests y 17 releases, y el arbol de hoy colecta 3176.
> El modelo de amenaza esta bien escrito y caducado.
>
> **`TUI operacional` es NO_MEASURABLE, y no es un OPEN disfrazado.**
> «Operacional» es una propiedad de una persona usando un terminal. No hay
> forma de medirla ejecutando el repo, y declararla PASS seria la unica
> forma de mentir. No baja el veredicto igual que un OPEN: las dos dejan
> 1.0 lejos, y el roadmap dice TODAS.
>
> **EL HARNESS SE DESTRUYO A SI MISMO, Y POR QUE IMPORTA.** La primera
> version de `scripts/mutate_b9_gate_1_0.py` restauraba con
> `git checkout --`, que restaura **del indice**. Con el arreglo sin
> commitear —que es como esta mientras se escribe un bloque—, el primer
> `checkout` de la primera sonda se llevo el arreglo entero: tres ficheros
> volvieron al estado previo y las sondas M2 a M6 se encontraron sin texto
> que deformar. Lo malo no es que fallara: es que **parecia funcionar**,
> porque la base se verifico verde, la primera sonda cazo y el informe
> salio con un numero. «Restaurar» y «borrar» son la misma operacion si no
> hay commit debajo, y por eso el harness ahora **se niega a empezar** si
> encuentra cambios sin commitear en lo que va a restaurar.
>
> **CUATRO BUGS DEL PROPIO MEDIDOR, todos en la misma direccion.** (1) La
> hoja de B5 escribe `[CERRADO ]` con un espacio y la de B6 `[CERRADO]`
> sin el: buscando el texto exacto, el predicado de provenance leia cero
> preguntas y devolvia **PASS**. Un predicado que pasa porque no leyo nada.
> Ahora el marcador se reconoce por forma, y si no sale ninguna pregunta
> el veredicto es OPEN. (2) `_migrations_probadas` buscaba la palabra
> «deselected» para detectar que no se habia ejecutado nada, y da OPEN
> sobre un resumen que dice `3 passed, 20 deselected`: deselected aparece
> igual cuando los tests selectionados SI corrieron. Ahora se cuentan los
> `passed`. (3) Las dos consultas al parser llamaban a
> `construir_parser()`, que no existe —es `build_parser()`—, y el
> `ImportError` se comia en un `return ()`: dos veredictos falsos, ambos
> en la direccion de alarmar de mas. (4) B5 declara su P6 FUERA DE ALCANCE
> y por el principio de siempre —«fuera de alcance se registra y no baja el
> veredicto»— no cuenta como abierta; el primer medidor la contaba.
>
> **HARNESS: 6 de 6 sondas, 6 causas distintas.** Y tres de esas seis
> salidas fueron fallos de los guards, no de las sondas: uno miraba que
> el proceso siguiera vivo —un hijo sin puerta lo sigue estando 30 ms—,
> otro hacia `join()` del hilo ANTES de comprobar, y el tercero decia
> «ha salido un error» cuando queria decir «ha salido ESTE error»: con el
> error tragado, la excepcion igualmente salia de `_migrate()`. Los tres
> miden la mitad de lo que dicen medir. Un 3/6 es un numero honesto; un
> 6/6 sobre esos tests habria sido un numero falso.
>
> **LO QUE NO SE ABRE.** TUI usable (no medible aqui), proveedor real
> (credencial que este entorno no tiene), y el ciclo de vida de packs
> (trabajo de B8, no de B9). Se registran y no bajan el veredicto.
>
> Instrumento: `scripts/measure_b9_gate_1_0.py`. Harness:
> `scripts/mutate_b9_gate_1_0.py`. Guards: `tests/test_b9_wal_lock.py`.
>
> measure_b9_gate_1_0.py:123::propiedades_del_roadmap  las 20, DERIVADAS del roadmap
> measure_b9_gate_1_0.py:201::_preguntas          el marcador se reconoce por forma
> measure_b9_gate_1_0.py:319::_veredicto_de_hoja   cero preguntas leidas = OPEN
> measure_b9_gate_1_0.py:177::_pasaron             se cuentan los `passed`, no `deselected`
> measure_b9_gate_1_0.py:698::_comandos_de_la_cli  importa el parser, no lo adivina
> measure_b9_gate_1_0.py:758::evaluar             una sin predicado = NO_MEDIBLE
> measure_b9_gate_1_0.py:792::listo_para_1_0       NO_MEASURABLE tambien impide 1.0
> platform/journal.py:75::modo_de_journal          LECTURA, y por eso no pide lock
> platform/journal.py:85::asegura_wal             releer y dormir entre reintentos
> platform/journal.py:62::INTENTOS_WAL             tres, y el por que esta escrito
> test_b2_real_concurrency.py:156::_abre_la_puerta  no abre hasta tener a todos
> mutate_b9_gate_1_0.py:84::_sin_trabajo_sin_commitar  «restaurar» y «borrar» son lo mismo
> test_b9_wal_lock.py:113::TestLaBaseYaEstaEnWAL   una base en WAL no se repregunta
> test_b9_wal_lock.py:267::TestLaBarreraDeLosHijos  el solape es estructural, no una carrera

> **Bloque 2026-10-04 (B8) — El contrato de paquete, y lo que de él depende.**
> Versión activa `0.28.1.dev0`; último tag `v0.28.1`.
>
> **B8: el enunciado enumera siete frentes, y esa es la decisión del
> bloque.** `ROADMAP.md` §B8 lista seis tipos de paquete, aislamiento
> progresivo, `mise`/`asdf`/`uv tool`/PyPI, upgrade, install/update/remove,
> matriz de compatibilidad y un formato `requires`. Siete no es un bloque:
> son siete, y medirlos juntos daría un veredicto que no dice por dónde
> empezar. Este bloque mide y entrega **el manifiesto**, que es la pieza de
> la que los otros seis cuelgan.
>
> Medido antes de escribir nada (`scripts/measure_b8_package_contract.py`):
> **5 de 5 preguntas abiertas**. Y lo que encuentra es que no había
> manifiesto —solo un `Brick` con `kind="DomainPack"`, que es el contrato de
> *tipos*, no el de *paquete*.
>
> ```
> packaging/manifest.py:63::PACK_KINDS      los seis, DERIVADO por get_args
> packaging/manifest.py:69::ISOLATION_LEVELS  declarative -> subprocess -> sandbox
> packaging/manifest.py:105::IncompatiblePackError   code sg_incompatible_pack
> packaging/manifest.py:167::PackManifest    el manifiesto, frozen y comparable
> packaging/manifest.py:357::es_compatible   devuelve MOTIVOS, no un bool
> packaging/manifest.py:399::exigir_compatible  la version que lanza
> ```
>
> **La costura ya estaba puesta y es lo que hace el bloque posible.** B3
> dejó `CAPABILITY_VERSION: Final[str] = "v1"` en el puerto con un
> docstring que dice, literalmente, que está ahí «para que
> `requires.capabilities` de B8 tenga algo que versionar». Si la versión
> viviera en cada adaptador, cada uno inventaría la suya y no habría nada
> que comparar. Tres años de docstring y por fin se usó.
>
> **Tres decisiones, y las tres son correcciones de cosas que ya existían.**
>
> 1. **`PACK_KINDS` se deriva por `get_args`, nunca se escribe a mano.** Un
>    conjunto literal se queda corto en cuanto el `Literal` crece, y
>    entonces el validador rechaza el valor nuevo que el propio tipo
>    acepta. Es el error de QW-E, pagado una vez en B6.
> 2. **La versión de la capability la hereda del puerto.** Es la decisión
>    que B3 dejó anotada y B8 ejecutó.
> 3. **`ISOLATION_LEVELS` es una tupla ORDENADA, no un conjunto.** El orden
>    es el contenido: «cada nivel es al menos tan aislado como el anterior»
>    es lo que hace que «progresivo» sea una propiedad comprobable
>    (`es_al_menos`) y no un adjetivo.
>
> **Y `es_compatible` devuelve MOTIVOS, no un `bool`.** En un pack que se
> está instalando, el «por qué» es la mitad del trabajo: `no encaja` no le
> dice al operador si le falta una capability o si su SkillGraph es viejo.
> Los motivos van ordenados y deterministas, porque un mensaje de error
> que cambia de orden entre ejecuciones no se puede comparar ni copiar.
>
> **Dos defectos reales que los tests cazaron, y los dos son del código:**
>
> - **El parser rechazaba el formato del propio gate.** El enunciado
>   escribe `">=0.30,<1"`, que **mezcla** `>=0.30` —dos componentes— y `<1`
>   —uno solo—. Mi regex exigía `X.Y` o SemVer completo, así que ninguno
>   de los dos requisitos se aceptaba y **ningún pack encajaba contra el
>   formato que el gate define**. Lo cazaron seis tests a la vez.
> - **La capability larga se rompía en silencio.** `{type_name, version}`
>   devolvía `"a.b.v2@v2"` como `type_name` y se construía la requirement
>   con la versión pegada al nombre y la del puerto en el campo `version`.
>   Una requirement con la versión pegada no se puede comparar con un
>   `CapabilitySpec` instalado, que los tiene separados. Todo lo demás
>   parecía funcionar, que es lo que hace un fallo silencioso.
>
> **Y un defecto del harness, que es el más instructive.** «Árbol restaurado
> byte a byte» **no** es «el árbol está como estaba». Al restaurar, el
> `mtime` del `.py` puede no avanzar lo suficiente y Python sigue ejecutando
> el `.pyc` de la versión mutada: el árbol estaba restaurado y ejecutando
> la versión equivocada a la vez. Se vio porque M5 cazaba los tests de M4, no
> los suyos. El harness ahora borra `__pycache__` y **vuelve a pasar la
> suite al final**, que es la comprobación que faltaba.
>
> **Y un test mío que no podía fallar.** El test de alias mutaba
> `requires.skillgraph` en el dict de origen —los strings son inmutables en
> Python, así que eso no puede cambiar un `frozen` dataclass—. Era un test
> verde por construcción. Se quitó esa aserción y la sonda se movió a
> `metadatos`, donde el alias sí es posible. Un test que no puede fallar no
> mide nada: ocupa el sitio de una comprobación que sí podría.
>
> **Verificación:** 66 tests, cobertura del 100% del paquete nuevo (el suelo
> de §6.3 es 90%). Contra-saltos **5/5 con 5 conjuntos distintos de tests**,
> 0 sin sonda, árbol restaurado byte a byte **y ejecutando como estaba**.
> `tests.total` 3161, con el desglose medido pieza a pieza.
>
> **Fuera de alcance y registrado:** P6 —que un pack se instale de verdad en
> una instalación real—, porque depende de un registro remoto y de una
> política de fijación que el CI no tiene. Se mide el contrato, que es
> comprobable sin red. Evidencia: `scripts/measure_b8_package_contract.py` y
> `scripts/mutate_b8_package_contract.py`.
>
> ---
>
> **Bloque 2026-10-04 (B7) — Las vistas que CLI y TUI compartirian.**
> Versión activa `0.27.0.dev0`; último tag `v0.27.0`.
>
> **B7: el hueco no era que faltara una TUI, era que faltaba la pieza de la
> que la TUI depende.** El gate pide diez widgets vivos «sobre **las mismas**
> APIs y query models». Medido antes de escribir nada
> (`scripts/measure_b7_operational_ux.py`): **3 de 3 preguntas abiertas**, y
> lo que encuentra es lo de abajo — cero declaraciones de `--format` en siete
> módulos de comando, y ningún símbolo en `src/` que expusiera render. La
> palabra cargada del gate no tenía a qué referirse, y por eso el bloque se
> mide por la pieza de abajo, que el CI puede comprobar sin humano.
>
> ```
> presentation/views.py:89::TableView        una tabla, con texto y JSON
> presentation/views.py:175::DetailView      un panel, con texto y JSON
> presentation/views.py:206::to_key_value     el contrato antiguo de runs show
> presentation/widgets.py:49::run_view        de las diez proyecciones
> cli/commands/runs.py:43::_emit              la eleccion, en un solo sitio
> ```
> `--format` se declara con un helper `_add_format` en el parser de la CLI,
> y **no se cita aqui** por una razon que conviene saber: el guard de WI-92
> indexa los modulos por NOMBRE de fichero, no por ruta, y `parser.py` existe
> dos veces —en `cli/` y en `resources/`—, luego toda forma de esa cita cae
> en «ambiguo». No se forzo el guard para poder citar: declara la ambiguedad
> en vez de adivinarla, que es lo correcto. Queda como deuda, no como
> hueco de este bloque.
>
> **Tres decisiones, y las tres son el bloque.**
>
> 1. **Las vistas no leen disco.** Se construyen desde lo que el dominio ya
>    devolvió, porque una vista que consulta sería una segunda vía de
>    consulta — el duplicado que este bloque existe para impedir. Se comprueba
>    por AST: cero imports de `sqlite3` y de `Storage` en el paquete.
> 2. **Una sola vista, dos representaciones, leyendo los mismos campos**, para
>    que no puedan divergir. Y aquí se distinguirá algo que la primera versión
>    del test confundía: «mismos campos» **no** es «mismo renderizado». Un
>    vacío se imprime como `-` en texto — que es el contrato antiguo — y como
>    `[]` en JSON, que es lo que una máquina necesita para no tener que
>    adivinar si es vacío o la cadena `-`. Exigir que coincidieran habría
>    obligado a romper uno de los dos.
> 3. **B7 añade representaciones, no sustituye.** Sin `--format`, `runs show`
>    sigue siendo `clave=valor`, porque hay callers que lo leen con
>    `cut -d= -f2` y su docstring lo promete.
>
> **Y la tercera estaba rota, medido contra.** El guard que la vigila no es
> teórico: la primera versión de `_emit` pasaba `vacio=` a toda vista.
> `TableView` lo acepta, `DetailView` no — y `runs show`, que es el camino de
> **texto**, el de por defecto, el que se usa siempre que nadie pasa
> `--format`, salía con `TypeError`. Un test que mira la vista no lo ve: hay
> que **ejecutar el comando**. Por eso `TestB7NoRompeElContratoExterno` va por
> `subprocess` y no contra la vista.
>
> **Contra-saltos 3/3, cada uno con su propia causa** — y M3 la cazó un guard
> **nuevo** (`test_list_sigue_diciendo_sin_runs`), no uno preexistente: sin
> él, quitarle a `runs list` su `(sin runs)` propio no ponía nada en rojo.
> Un cuarto agujero, también del instrumento: el contra-salto del medidor
> copiaba el repo entero a `/tmp` y se puso rojo con `EDQUOT` al escribir
> cientos de MB. Un guard que se pone rojo porque se llenó el disco no mide
> la propiedad, mide el almacenamiento; ahora copia sólo `src/` y `scripts/`
> — 1,1 MB — y discrimina igual.
>
> **Verificación:** 23 tests. `tests.total` 3088, y el desglose está **medido**,
> no estimado: con `src/skillgraph/presentation/` apartado del árbol la suite
> colecta 3055, la cifra exacta que B6 declaró; al devolverlo, 3088. Los 10
> que no son de B7 los genera el guard de `wi47`, que pasó de 255 a 264 casos
> al aparecer los módulos nuevos. Es la predicción que B6 dejó escrita y que
> es fácil leer al revés.
>
> **Fuera de alcance y registrado:** P4 —que la TUI sea usable de verdad—,
> porque depende de un terminal y de una interacción humana que el CI no
> tiene. Se mide cuando haya alguien usándola. Al medidor la deja registrada
> y por eso **no** baja el veredicto. Evidencia:
> `scripts/measure_b7_operational_ux.py` y `scripts/mutate_b7_operational_ux.py`.
>
> **CERRADO Y PUBLICADO como `v0.27.0`** (MINOR por `0/1/1/2/0`, derivado con
> `scripts/derive_semver.py`; ninguno con marcador de ruptura). Entrega
> `0d9d423`, tag `v0.27.0` en `683dbfc`, cadena de release de cuatro commits
> con la suite completa en verde dentro de cada hook.
>
> El ciclo `p-b7740b96d79ec013/b7` queda **BLOCKED**, no `CLOSED`: los dos
> gates de deuda no son evaluables en esta build de SDDK y `verify` no puede
> pasar a `release`. El trabajo **está** entregado y verificado; lo que no se
> puede es cerrar el ciclo. Mismo bloqueo que `b4` y `b5`.
>
> **Y un hallazgo que vale más que el bloque.** El ciclo `b6` llevaba dos
> sesiones bloqueado en `explore` por un supuesto defecto del framework —
> «`sddk artifact store` no vincula el artefacto al ciclo»— y **no lo era**.
> `cycle transition` acepta `--artifact kind=path` **en la propia transición**,
> y con esa vía la transición se aplica: `b6` quedó desbloqueado y pasó a
> `specify`.
>
> Un `ENGINE_MISSING_ARTIFACT` que **nombra** el artefacto que falta es una
> instrucción, no un veredicto de avería. Se leyó como avería porque se
> escribió como avería, y una vez escrito el diagnóstico cada relectura lo
> confirmaba.
>
> ---
>
> **Bloque 2026-10-03 (B6) — Cada afirmacion dice QUIEN la afirma.**
> Versión activa `0.26.0.dev0`; último tag `v0.26.0`.
>
> **B6: el campo que parecia el sitio del origen no lo era.** El gate pide
> que cada afirmacion del Knowledge Graph distinga `observed` ·
> `derived-deterministically` · `agent-inferred` · `human-asserted`. Medido
> sobre el árbol real (`scripts/measure_b6_provenance.py`): **4 de 4
> preguntas abiertas**. Y lo que encuentra no es un campo que falte:
>
> ```
> knowledge/graph.py:177::Claim     la clase cuyo campo parecia el sitio
> ```
>
> Existe, y no dice lo que su nombre dice. Sus tres valores medidos —
> `static_analysis`, `regex_def`, `manual` — son **métodos de extracción**,
> no orígenes epistémicos. Son dos ejes ortogonales: con `regex_def` no se
> sabe si lo afirmó la máquina o una persona, y escribir `agent-inferred`
> ahí perdería el método. Un campo no puede decir las dos cosas.
>
> **Medido, y en contra de lo que parece:** nadie escribe
> `extraction_method` en `src/`. Las 10 de `"manual"` y las 4 de
> `"regex_def"` están todas en `tests/`; en producción sólo vive el default
> de la declaración. Un eje que nadie rellena no puede ser donde nazca el
> origen.
>
> ```
> core/runtime_types.py:96::AssertionOrigin      Literal cerrado (los cuatro)
> core/runtime_types.py:130::ASSERTION_ORIGINS    DERIVADO por get_args, nunca a mano
> knowledge/graph.py:177::Claim                   el campo y su validacion
> core/errors.py:135::InvalidAssertionOriginError   code sg_invalid_assertion_origin
> platform/storage.py:466::_anade_column_claims_assertion_origin  la migracion
> ```
>
> **El default es `observed` y es una decisión, no un descuido:** es el único
> de los cuatro que no promete autoridad, luego el único correcto para un
> valor que nadie ha declarado. Poner `agent-inferred` obligaría a corregir
> la afirmación más pequeña del sistema.
>
> **La migración es el hallazgo que la suite no ve.** `CREATE TABLE IF NOT
> EXISTS` **no** añade columnas a una tabla que ya existe: es un no-op
> silencioso. Medido: una base nueva funciona y una vieja no, y el fallo sale
> en producción y no en los tests, porque los tests construyen la base desde
> cero cada vez.
>
> **Tres bugs del propio instrumento antes de que sirviera**, los tres el
> error de siempre — un medidor que miente en verde. P3 buscaba `CHECK` en
> todo `schema.py` y daba CERRADO con el `CHECK` de *otra* tabla. P2
> escribía a mano «es str» en las dos ramas del detalle. Y `_campo_de_claim`
> derivaba el nombre del campo del nombre de la clase (`Claim` → `claim`),
> no encontraba `extraction_method`, devolvía `None` — y `None` se leía como
> «ya no es str». Un helper que devuelve `None` y un predicado que trata
> `None` como cerradura se combinan en una mentira con salida 0.
>
> **Cuatro agujeros reales encontró el harness, no sondas malas.** El
> primero es sobre el guard: el de P6 buscaba la *mención* de los dos
> nombres con `ast.dump` y pasaba en verde con la validación gutiada,
> porque el mensaje del `raise` sigue nombrando el conjunto. Se corrigió
> para exigir un `not in` real. El segundo es del harness: llevaba `-x`, y
> sin `-x`, **M3, M6, M7 y M8 no cazaban** — sus mutaciones dejaban la suite
> en verde. El 8/8 era un número que no se podía desarmar, con cuatro sondas
> heredando el fallo de la anterior. Añadidos los cuatro tests que faltaban;
> el recheck da **8 causas distintas de 8 sondas**: cada una rompe su propia
> propiedad.
>
> **Verificación:** 23 tests, mutaciones 8/8 con 8 causas distintas, árbol
> restaurado byte a byte. `tests.total` 3053 (+23, todos de
> `test_b6_provenance.py`: a diferencia de B4 y B5, este bloque no creó
> ningún módulo nuevo, así que el guard de `wi47` no generó casos).
>
> **Fuera de alcance y registrado:** P5 —si el proveedor real *puebla*
> conocimiento o lo *consume*—, que depende de una credencial que este
> entorno no tiene. El medidor la mantiene abierta y por eso no baja el
> veredicto: es deuda, no un olvido.
>
> ---
>

> **Bloque 2026-10-03 (B5) — El diff del grafo deja de ser un parche sin comparar.**
> Versión activa `0.25.0.dev0`; último tag `v0.25.0`.
>
> **B5: la secuencia del gate tenía un hueco con nombre.** El roadmap exige
> `Proposal → Diff → Policy → Decision → Evidence → Apply`, y medido sobre el
> árbol real (`scripts/measure_b5_graph_diff.py`, versionado en `scripts/`):
> **6 de 6 preguntas abiertas**. La que lo resumía era una línea —
>
> ```
> platform/…/graph_expansion.py::GraphExpansionProposal.operations   tuple[object, ...]
> ```
>
> Un saco de operaciones sin tipar. Las tres clases ya existían y el comentario
> del propio código decía *«PatchOp es ADT cerrado»* desde antes de que
> existiera un `PatchOp` que cerrara nada. Sin él, nada que quisiera preguntarle
> al parche qué invalida tenía por dónde mirar, y el `Diff` no podía ser una
> etapa porque no había nada que comparar.
>
> **Lo que sostiene el bloque, y es el hallazgo:** `required_capabilities` es lo
> que las operaciones **producen**; `declared_capabilities` es lo que la propuesta
> **dice**. Dos campos separados, y que discrepen no es un defecto del diff: es
> el resultado. Un diff que devolviera la declaración sería un eco con mejor
> tipografía, y un gate que comprueba ecos no mira nada.
>
> ```
> governance/graph_diff.py::GraphDiff          las 7 respuestas del roadmap
> governance/graph_diff.py::diff_graph         calcula comparando plan vs propuesta
> governance/graph_diff.py::base_fingerprint   SHA-256 del plan (R6 sin esto no se cumple)
> governance/graph_expansion.py::apply_expansion   rechaza el diff que no sea suyo
> governance/expansion_audit.py::record_rejection   mudado, reexportado
> ```
>
> **La huella no es adorno.** Sin ella, con el parche vacío el diff sale vacío
> sea cual sea el grafo, luego un diff de otro plan pasaba por suyo siempre que
> coincidiera la revisión — y dos estados pueden compartir revisión. Se midió
> al escribir el primer test de R6, que fallaba por eso.
>
> **La extracción se decidió con una medición, no con un gusto.** Al integrar el
> diff, `graph_expansion.py` pasó de 787 a **901** LoC y el guard de god file lo
> puso rojo. La salida no fue recortar prosa: `record_rejection` se mudó a
> `expansion_audit.py` —persistir un rechazo es escribir un registro de
> auditoría, no expandir un grafo— y se reexportó para que su ruta de importación
> no cambie. Queda en 785.
>
> **28 tests, mutaciones 8/8, 0 sondas inválidas.** Y tres sondas
> encontraron agujeros **reales** en la red, no sondas malas:
>
> - **M5 no fue cazada dos veces.** La primera quitaba el `sorted()` de
>   `to_dict` y no podía fallar: el constructor ya entregaba tuplas ordenadas,
>   luego la propiedad era **vacua**. La segunda lo quitaba del constructor y
>   tampoco — y ese es el hallazgo: la garantía está puesta **dos veces**, así
>   que no se rompe quitando una. Es la misma clase que la M6 de B4, segunda vez.
> - **M7** puso `reversible=True` fijo y nadie la cazó porque **ningún test**
>   afirmaba que la séptima pregunta dependiera del plan de rollback.
> - **M8** puso `esperado = diff`, con lo que la comparación se vuelve
>   `diff != diff`. No la cazó nadie porque la huella salta **antes** y los tests
>   de R6 usaban un diff bien calculado: la capa de recálculo no se ejecutaba
>   nunca. Un guard que solo se ejercita por el camino bueno no sabe si el malo
>   está cerrado.
>
> **Y un error propio del harness, de la misma clase que caza:** la sonda de dos
> sitios se aplicaba a medias porque el bucle usaba la primera sustitución y
> descartaba la segunda. Una sonda aplicada a medias se contaría como victoria.
>
> **Fuera de alcance y registrado:** las **cuatro vistas** del roadmap. El
> medidor las sigue dando por abiertas, y por eso **no bajan el veredicto**:
> son deuda, no un olvido. Construirlas sin el diff sería construirlas sin
> criterio.
>
> ---
>
> **B4 cerrado: lo declarado en el esquema ya se puede alcanzar.**
> Siete commits, un `feat` y seis sin bump. B3 dejó la mitad *declarada*
> de la separación CRD-like; B4 es la mitad *observada*, y estaba en el
> mismo estado: escrita en el esquema, inalcanzable en ejecución.
>
> **Lo que estaba medido al empezar** (`scripts/measure_b4_observed_state.py`,
> que sale 1 con el hueco abierto y 0 cuando ya no está):
>
> ```
> 1 INSERT y 0 UPDATE en `resources`    status_json = '{}' para siempre
> `conditions` en todo `src/`           cero
> `generation` escrita                  nunca
> ejecución real: status_json='{}' generation=1 resource_version=1
> ```
>
> `status_json` está declarada `NOT NULL DEFAULT '{}'` y nadie la
> actualizaba: cada recurso nacía sin observar y moría sin observar, y
> el `NOT NULL` lo hacía **parecer** un estado. Es el hueco con el que
> abrió B3, un nivel más abajo.
>
> **Lo que hay ahora:**
>
> ```
> platform/knowledge_repository.py:116::update_resource_status
> platform/knowledge_repository.py:170::get_resource_status
> resources/status.py:67::Condition
> resources/status.py:107::ResourceStatus
> resources/bricks.py:39::Brick            <- SIN status, y R5 lo fija por AST
> ```
>
> **La invariante, y por qué tiene guard propio:** `generation` es lo que
> el **spec** declara; `resource_version` es lo que el **almacenamiento**
> lleva. Escribir status sube `resource_version` y **no** `generation`.
> La sonda M3 quita el `generation` del `UPDATE` y lo que se midió al
> cazarla es lo importante: **el sistema sigue funcionando exactamente
> igual**. Nada falla y nada se rompe — la separación desired/observed se
> vuelve decorativa. Es el defecto que no se nota, y por eso necesita un
> guard que lo nombre en vez de confiar en que alguien lo note.
>
> `observed_generation` se **lee de la fila**, no se declara. Si lo
> declarara, mentiría en cuanto el spec cambiara por debajo, y sin ningún
> error: sería el status más fiable del mundo y el menos cierto.
>
> **Lo que NO se hizo, y por qué está en un guard:** `status` **no vive
> en `Brick`**. Si el tipo declarado llevara el status, un pack declararía
> el estado de su propio recurso y la mitad observada dejaría de estar
> observada: no habría forma de distinguir `observed` de
> `human-asserted`. La separación es de **tipo**, no de convención. R5 la
> fija por AST porque *«Brick no gana status»* no se deduce de un valor,
> se deduce de la forma.
>
> **19 tests** nuevos, uno de los cuales ejecuta el instrumento que abrió
> el bloque y exige que ya no reporte el hueco. **Mutaciones 8/8**, 0
> sondas inválidas, árbol restaurado byte a byte verificado por
> `git diff`.
>
> **Certificación**: 2991 passed, 3 skipped (los declarados) y **2
> failed** — y los 2 eran `tests.total` desactualizado y su gemelo de
> convergencia de B0, diciendo lo mismo. La cifra se escribió **después**
> del run, que es la regla, y el guard de WI-115 la cazó: es la primera
> vez que ese guard muerde en esta sesión, y lo hizo porque el recuento
> viene del árbol y no de una copia.
>
> **El `+22` no es todo mío, y está desglosado**: 19 de B4, 1 del
> renombrado de un test, y **3 de `test_wi47_broad_except_guard.py`**, que
> *parametriza sobre la lista de módulos* y por eso generó tres casos
> más al aparecer `resources/status.py`. Un guard que deriva sus casos del
> árbol se entera solo de que añadiste un módulo. Antes de atribuir la
> diferencia a B3 se comprobó en un worktree que el 2974 de B3 era
> **veraz**: 2974 colectados.
>
> ---
>
> <details>
> <summary>Bloque anterior (B3)</summary>
>
> **Bloque 2026-10-03 (B3) — Core extensible de verdad.**
> Versión activa `0.23.0.dev0`; último tag `v0.23.0`.
>
> **B3 cerrado: el puerto tiene consumidor y un adapter de producción.**
> Siete entregas. Las seis dejaron contrato, invariantes y procedencia; la
> séptima cierra los dos huecos que quedaban, y los dos eran el mismo hueco
> un nivel más arriba:
>
> ```
> sg.knowledge.query   knowledge/knowledge_query.py    adapter REAL, contra el Protocol
> CapabilityController runtime/capability_controller.py  el kernel: nombre -> ejecucion
> RunController(capabilities=…)                          la costura que lo hace alcanzable
> ```
>
> **Lo que estaba medido al empezar esta entrega:** dieciséis construcciones
> de `CapabilityRegistry` en el árbol, **las dieciséis en tests**, y cero
> módulos bajo `src/` que importaran el puerto. El gate del roadmap se
> cumplía **en vacío**: se podía añadir una capability sin tocar el core
> porque el core no la veía nunca.
>
> **La política de la costura, y por qué no rompe nada:** el registro se
> inyecta y su ausencia **es** la política. Sin registro —el default— un
> plan que declara `'stale'` sigue ejecutándose igual, porque `'stale'` es
> un `FreshnessState` y no una capability. Con registro, lo que el plan
> declara tiene que existir, o el nodo queda `FAILED` con
> `CapabilityNotFound` **sin gastar una llamada al adapter**: la
> verificación va dentro del `try` de `_compile_node_handoff`, que corre
> antes de `_invoke_node_adapter`. Esa propiedad no se ve en la fila del
> nodo, y un plan que paga una llamada de red y luego falla parece
> funcional.
>
> **Lo que NO se hace, por decisión:** las capabilities no se invocan
> durante la ejecución, solo se verifican. `Handoff.capabilities` sigue
> siendo `tuple[str, ...]` porque `runtime/handoff.py:195::Handoff.to_dict` lo mete en el
> hash firmado, y moverlo es ruptura de datos: **B8**.
>
> **Mutaciones 6/6**, 0 sondas inválidas, árbol restaurado y verificado por
> `git diff`. El harness está **versionado** en `scripts/`, no en
> `.pipelinek/`, y la razón está más abajo.
>
> **B3 — el hueco estaba medido antes de escribir una línea.** En el
> árbol real, las capabilities se declaraban, se transportaban, se
> serializaban, se imprimían y se validaban contra un registro de
> strings. Y nadie las resolvía a nada ejecutable:
>
> ```
> resources/workflow.py:71::WorkflowNode.capabilities        tuple[str, ...]
> governance/graph_expansion.py:449::_check_capabilities     dos preguntas al registro
> knowledge/context_controller.py:139::build_capabilities    produce ('stale',)
> runtime/http_adapter.py:167::_build_prompt                las imprime
> alguien que las RESUELVA                                 —— NINGUNO ——
> ```
>
> Eso es un hueco de **arquitectura**, no una función que falte. B1 ya
> lo había visto y lo dejó escrito como «la base de B3» en vez de
> deuda.
>
> **Lo que hay ahora**: `platform/ports/capabilities.py` — `CapabilitySpec`,
> `CapabilityRequest`, `CapabilityResult` (que **lleva `adapter`**: la
> procedencia que B6 necesitará para «¿quién afirmó esto?»), un
> `Protocol` **mínimo** (`spec` + `invoke`) y un `CapabilityRegistry`
> que es un **valor inyectado**, no un singleton. `resolve` lanza
> `CapabilityNotFound` tipado —cuelga de `SkillGraphError`, con `code`,
> traducible a exit code— en vez de devolver `None`.
>
> **El primer gate medía mal, y es el hallazgo del bloque.** Exigía
> `a == b` para dos registros, que es una propiedad que un **singleton
> cumple mejor que un valor**: un singleton siempre es igual a sí mismo.
> Medido sobre un registro convertido a singleton:
>
> ```
> hoy            : a == b  -> False   (el test lo exigía)
> singleton      : s1 == s2 -> True   <-- la aserción PASABA igual
> singleton      : s1.types  -> ('A',)  <-- la contaminación seguía ahí
> ```
>
> Exigía una propiedad cuyo único incumplimiento era el correcto, así
> que no distinguía un valor de un singleton. Reemplazada por
> **no-contaminación**, que sí discrimina. Es el error de WI-114 dado la
> vuelta: allí el instrumento medía la convención que el workitem
> eliminaba; aquí medía una que sí distingue, pero de una forma que un
> singleton también cumple.
>
> **Error propio, y el más importante: el harness de mutación se escribió
> al revés** —buscaba el texto *nuevo* para aplicar la mutación— y dio
> `0/12` con `SIN_SONDA` en las doce. La sonda hizo su trabajo y prefirió
> decir «no he medido nada» a contar doce victorias sobre un árbol que
> nunca cambió. **15/15 mutaciones cazadas**, 0 sondas inválidas, árbol
> restaurado byte a byte con sha256, repetido 3 veces seguidas.
>
> **Y una mutación era intermitente.** Quitar el `sorted` de `types`
> devuelve `tuple(set)`, y el orden de un set de cadenas depende del
> hash, que Python aleatoriza por proceso: **8 órdenes distintos en 8
> corridas**. Un defecto intermitente en un guard es peor que no tener
> guard, porque entrena a leer «a veces pasa» como ruido. Arreglado por
> dos vías: cinco capabilities en vez de dos en el test (con dos el set
> sale ordenado la mitad de las veces) y `PYTHONHASHSEED=0` en el
> harness, que hace el resultado atribuible al cambio y no al proceso.
>
> **Hallazgo de arquitectura, medido ejecutando un nodo de verdad.**
> `handoff.capabilities` tiene **dos productores con semánticas
> distintas**:
>
> ```
> runtime/runcontroller.py:580::RunController._build_handoff   -> node.capabilities
> knowledge/context_controller.py:341::ContextController.compile_handoff -> ('stale',) o ()
> ```
>
> Y `'stale'` es un valor de `FreshnessState`
> (`core/runtime_types.py:71::FreshnessState`): un **estado de frescura**,
> no una capability. Los dos caminos entregan lo mismo al Adapter — medido
> sobre disco, `.pipelinek/b3_measure.py`— pero **no porque el código lo
> decida**: porque
> `runtime/runcontroller.py:639::RunController._compile_knowledge`
> hace `return compiled.knowledge`, de modo que `compile_handoff` construye un
> `Handoff` **entero** —con identity, budget, capabilities y hash
> firmable— y lo destruye para usar una parte. Funciona por accidente.
>
> **CUARTA ENTREGA: `'stale'` se queda en `capabilities`, y la deuda se
> escribe donde se tropieza.** Medido con `Storage` real y una `Claim`
> real: `best_effort` produce `capabilities=('stale',)` con hash
> `e1f384db63feab26…`; `strict` lanza `StaleKnowledgeError` sin construir
> handoff. El coste de moverlo no es de estilo:
> `runtime/handoff.py:195::Handoff.to_dict` mete
> `sorted(self.capabilities)` en el **hash firmado**, luego cambiarlo
> rompe el replay de los runs ya persistidos. Y **no se pierde
> información**, porque el estado de frescura ya viaja por otra vía:
> `knowledge.included` lleva el recurso con su `stale`. La deuda queda
> escrita en el código —`runtime/http_adapter.py:167::_build_prompt`, justo encima del
> bucle que imprime un bloque titulado literalmente `## Capabilities` con
> una línea `- stale`, y en la docstring de
> `knowledge/context_controller.py:139::build_capabilities`— y fijada por
> test en las dos direcciones, con un mensaje que dice que moverla es un
> **cambio de contrato**, no un refactor.
>
> **Quinta entrega, y es de B3 aunque el arreglo parezca de B6: la
> procedencia se pierde ANTES de que nadie la pida.** `CapabilityResult`
> lleva `adapter` desde la primera entrega, y aun así **ningún artefacto
> persistido decía qué adapter produjo el resultado**. Ejecutando un nodo
> de verdad y leyendo de disco (`.pipelinek/b3_provenance_measure.py`):
>
> ```
> el AgentResult persistido : ['evidence_ref', 'outcome', 'result']
> hay campo 'adapter'       : False
> NodeCompleted       {node_execution_id, outcome, context_hash}
> EvidenceProduced    {node_execution_id, outcome, context_hash, evidence_ref}
> ```
>
> El motor sí lo sabía —es quien invocó al adapter—, y lo que falta no es
> un type al que añadirle un campo: es que **el type que el motor escribe
> lo lleve**. B6 no habría encontrado un type nuevo al que ponerle
> procedencia; habría encontrado que **no existe**, y la pérdida está en el
> runtime, luego es B3.
>
> El arreglo son `runtime/agent.py::adapter_name(adapter)` —lo declarado
> por `name`, o el nombre de la clase, **con default** porque los tres
> adapters del repo no declaran ninguno— y `adapter: str` **sin default**
> en las firmas de `node_completed` y `evidence_produced`, para que un
> call-site nuevo no pueda omitirlo sin que nada falle. Va en el **evento**
> y no en `AgentResult`, que es el payload que produjo el modelo: ahí el
> nombre del runtime se mezclaría con lo que el agente afirma. La columna
> en `node_executions` se deja para **B8**, porque añadir una columna es
> migración.
>
> **Un agujero en el guard, cazado por mutación (M30):** el test que
> fija que el nombre **no** se cuela en el resultado miraba solo *dentro*
> de `result`. Una mutación que lo ponía en la **raíz** de `result_json`
> pasaba sin ser vista. El guard afirmaba vigilar el lugar exacto donde
> la mezcla es perigosa, y la mezcla ocurría un nivel más arriba.
>
> **SEGUNDA ENTREGA: el invariante I4 no comprobaba lo que decía.**
> Buscando el segundo consumidor de `capabilities` apareció un
> invariante roto. Medido con el registro **real** que construye la CLI:
>
> ```
> dep que NO existe en ninguna parte        -> I4
> dep que SÍ existe (el pack del proyecto)  -> I4   <-- rechazaba lo que existe
> dep = 'code.analysis' (que además es cap) -> pasa <-- solo pasaba al confundirse
> ```
>
> **I4 rechazaba una referencia que existía** —el único pack del
> proyecto— y **solo pasaba cuando el autor escribía como «dependencia»
> el nombre de una capability**. Es decir, el invariante medía la
> confusión del autor, no la existencia de la referencia.
>
> La comprobación no era el problema: con la dependencia puesta a mano en
> el mapa, I4 dejaba de saltar. **El problema eran dos, y el segundo se
> ve menos:**
>
> 1. **La fuente.** `cli/commands/expansion.py:151::_load_registry`
>    construía el mapa recorriendo `spec_json.capabilities` y nunca
>    miraba `new_dependencies`.
> 2. **El tipo.** I3 y I4 eran dos preguntas —«¿esta capability está
>    autorizada?» y «¿esta referencia existe?»— sobre **un solo
>    `Mapping[str, str]`**. Un mapa no contesta dos preguntas distintas.
>
> **El arreglo, y la decisión que lo detrás.** `new_dependencies` pasa a
> tener formato declarado `ns:Kind/name` con un smart constructor
> (`governance/graph_expansion.py:79::resource_ref`), y el registro se
> parte en **dos vistas** —`ExpansionRegistry.capabilities` para I3 y
> `.references` para I4—. El formato no es inventado: es el que ya usan
> `ResourceIdentity` y el que `_load_registry` ya producía como valor.
>
> **Y no hay ruptura de datos, medido:** las propuestas **no se
> persisten** en la base. `record_rejection` escribe un JSON de auditoría
> en `expansion_rejections/`, y las aceptadas no se guardan. El campo
> solo existe en el JSON que el usuario aporta en cada invocación, así
> que darle formato cambia la validación de entrada, no la lectura de
> nada almacenado.
>
> **Un invariant se quedó sin su contrasalto al migrarlo:** el test de H4
> acababa con `assert "lint" in empty_registry`, que comprobaba que el
> *fixture* contenía lo que el *fixture* acababa de definir. No miraba
> producción, y con el tipo nuevo ni compilaba. Quitado: un contrasalto
> que no puede fallar es peor que no tener contrasalto.
>
> **Por qué B5 importa aquí.** El Graph Diff Gate se apoya en
> GraphExpansion. Con I4 rechazando toda propuesta con dependencia nueva,
> B5 nacía con el gate cerrado — no por decisión, sino porque el
> invariante no tenía fuente.
>
> **Y el hueco se repite un nivel más arriba, medido.** El gate demuestra
> que **el contrato se puede cumplir** —una capability inventada en un
> test se registra, se resuelve y se invoca—, pero no que **el runtime lo
> pueda alcanzar**. `.pipelinek/b3_wiring_measure.py`, con el criterio
> declarado antes de mirar:
>
> ```
> imports_produccion               : []
> construcciones de Registry en src : []
> ficheros que importan el puerto   : tests/test_b3_capability_kernel.py
> veredicto                         : INALCANZABLE_DESDE_PRODUCCION
> ```
>
> Dieciséis construcciones de `CapabilityRegistry` en el árbol. Las
> dieciséis están en el test. El criterio de B3 —«añadir una capability
> sin modificar `RunController`»— se cumple hoy de forma **vacua**: se
> puede añadir una sin tocar el core porque el core no la ve. El hueco
> original tenía esta forma exacta; solo se ha movido de sitio.
>
> La costura ya existe como precedente:
> `runtime/runcontroller.py:106::RunController.__init__` recibe
> `adapter: AgentAdapter` inyectado por palabra clave, y un
> `CapabilityRegistry` cabría en esa misma firma. **Si se abre, y con qué
> forma, está sin decidir** — es decisión de contrato, no un arreglo
> pendiente.
>
> **Dónde están las cosas**: el contrato, en
> `src/skillgraph/platform/ports/capabilities.py::CapabilityRegistry`;
> el gate, en `tests/test_b3_capability_kernel.py`; el invariante I4, en
> `src/skillgraph/governance/graph_expansion.py::ExpansionRegistry` con
> su test en `tests/test_b3_i4_reference_invariant.py`; la procedencia, en
> `src/skillgraph/runtime/agent.py::adapter_name` con su test en
> `tests/test_b3_provenance_persisted.py`; las mediciones, en
> `.pipelinek/b3_measure.py`, `.pipelinek/b3_i4_measure.py`,
> `.pipelinek/b3_stale_measure.py` y `.pipelinek/b3_provenance_measure.py`;
> y las 30 mutaciones, en `.pipelinek/b3_mutate.py`.
>
> **Con release `v0.23.0`**: `derive_semver.py` pidió MINOR (`0/5/2/20/0`)
> al cierre. La línea de abajo decía «Sin release» porque se escribió
> durante el bloque, antes de emitir la etiqueta; se corrige porque
> dejada así afirma algo falso de B3.
>
> ---
>
> </details>
>
> <details>
> <summary>Bloque anterior (B2)</summary>
>
> **Bloque 2026-10-03 (B2) — Runtime real, no representativo.**
> Versión activa `0.23.0.dev0`; último tag `v0.23.0`.
>
> **B2 — el repositorio admitía que ciertos escenarios eran
> *representativos*. Esto los atraviesa, y encontró tres defectos reales.**
>
> **Medido antes de escribir nada:** **cero `SIGKILL` en todo `tests/`**,
> y cero ficheros SQLite escritos por dos programas a la vez. Toda la
> superficie de crash eran **failpoints** y toda la de concurrencia,
> **threads**. Y no es lo que parece:
>
> - Un **failpoint** hace que el proceso lance. Al lanzar, Python
>   desenrolla la pila, ejecuta los `finally`, cierra la conexión y
>   SQLite consolida el journal por rollback. Es un cierre **ordenado**.
> - Un **thread** comparte el GIL: dos hilos no se ejecutan a la vez,
>   luego el test mide una interleaving que el sistema real no tiene.
>
> **Crash real, con `SIGKILL` desde dentro.** El hijo se mata a sí mismo
> justo después de la escritura que interesa —así el punto del corte es
> determinista— y el padre solo mira el disco:
>
> | escenario | corte | filas después |
> |---|---|---|
> | escribir sin commit | `INSERT` sin confirmar | **0** |
> | transacción abierta | `BEGIN` + 2 filas | **0** |
> | commit y muerte | `commit` hecho | **1** |
>
> La segunda fila es la que **ningún failpoint puede demostrar**: un
> rollback deja la base tan limpia como un commit. Solo apagando el
> proceso se ve que lo no confirmado desaparece entero. 10 tests,
> mutaciones 4/4.
>
> **Concurrencia real, y aquí estaba lo bueno.** Ocho procesos, diez
> escrituras cada uno, el `Storage` de verdad. **80 de 80, cero
> perdidas** — después de arreglar tres defectos que no estaban en el
> runtime sino **en la apertura de la base**:
>
> 1. `PRAGMA journal_mode = WAL` sin `busy_timeout` mataba procesos al
>    construirse: **70 de 80 eventos, diez escrituras perdidas sin dejar
>    rastro**. El PRAGMA es idempotente, pero toma un lock de escritura
>    para averiguarlo.
> 2. `_migrate` era un *check-then-act*: ocho procesos abriendo una base
>    nueva veían todos `schema_version` vacía y los ocho insertaban.
>    Ahora `INSERT OR IGNORE` y el `SELECT` desaparece — la constraint
>    resuelve la carrera, que es lo que manda `AGENTS.md §8`.
> 3. El `busy_timeout` no cubría el bloqueo **dentro** de la conversión
>    del journal. Reintento acotado, y si el segundo intento falla la
>    excepción sube: nunca `except: pass`, que dejaría la base en
>    `delete` sin que nadie lo supiera.
>
> **Un cuarto defecto, en el instrumento de B0.** La UAT real es opt-in
> por credencial, así que la suite la salta. El criterio de la receta
> contaba **todos** los skips, de modo que un skip correctamente
> **declarado** ponía rojo el run: la lista `SKIPS_PLATAFORMA` no
> servía para nada. La regla ahora tiene tres estados — 0 skips es
> limpio, los declarados se toleran, cualquier otro número incumple— y
> se cuenta por AST sobre la lista, con la misma convención que el guard
> de WI-108.
>
> **Proveedor real: NO CERTIFICADO.** La UAT existe y es opt-in
> (`tests/test_uat_real_provider.py`), pero **no se ejecutó**: necesita
> credenciales que este entorno no tiene. Declararlo es lo que WI-91
> hizo con el addendum de H9. Con eso, la frase del H7 —«escenario real
> completo»— **todavía no puede marcarse como probada literalmente**.
>
> **Dónde están los arreglos**, por si hay que volver a ellos: el
> `INSERT OR IGNORE` que cerró la carrera de la migración, en
> `src/skillgraph/platform/storage.py:465::_migrate`; y el
> `busy_timeout` que evita que el `PRAGMA journal_mode = WAL` mate un
> proceso al construirse, en la clase `Storage` de ese mismo fichero.
>
> **Sin release, y por regla**: `derive_semver.py` manda.
>
> </details>
>
> ---
>
> <details>
> <summary>Bloque anterior (B1)</summary>
>
> **Bloque 2026-10-03 (B1) — Cierre de stewardship.**
> Versión activa `0.23.0.dev0`; último tag `v0.23.0`.
>
> **B1 — la pregunta «¿qué declara el repo que nadie comprueba?» ya no
> admite un workitem por contrato, para siempre.** B0 cerró la serie
> WI-91..WI-115; B1 la convierte en un inventario **finito**, con
> criterio de terminación: cada contrato es `GUARDED`, `NO-GUARANTEED`, o
> `DEUDA` con el motivo por escrito. Cero deuda crítica.
>
> **Medido** (`.pipelinek/b1_inventory.py` + `b1_verdict.py`): 17
> contratos sobre 17 categorías, 1122 sitios, **14 GUARDED · 2 DEUDA ·
> 1 NO-APLICA · 0 deuda crítica**.
>
> **El problema que B1 nombraba ya estaba cerrado.** `promotion list`
> llama a `storage.list_promotions()`, la API pública; lo que quedaba era
> el README afirmándolo abierto, y el propio módulo lleva un comentario
> que dice lo contrario. Arreglarlo era corregir una afirmación vieja.
>
> **Lo que B1 encontró de verdad: cuatro medidores ROTOS.** El predicado
> de inmutabilidad miraba el primer argumento posicional de
> `@dataclass(...)`, y el repo usa `frozen=True` como palabra clave:
> daba **cero** dataclasses frozen donde hay 23. `capabilities` buscaba
> `port` y casaba dentro de «comportamiento»: **875** falsos positivos.
> Un predicado que devuelve la lista vacía no se ve raro — por eso el
> inventario imprime las categorías sin hallazgo en vez de contarlas
> como cumplidas.
>
> **El guard de B0 cazó esta misma transición.** Al mover el bloque a B1,
> `blocks.current` pasó a B1 y `roadmap.current_workitem` se quedó en B0:
> el guard lo puso rojo y lo dijo con las dos caras, en el commit que
> cambiaba de bloque. Es la primera vez que el guard que creó B0 caza un
> cambio hecho por el propio bloque, y ocurre porque la verdad se cruza
> **en un sitio y no en dos** — que es exactamente lo que B0 compró. El
> guard que lo hace es
> `tests/test_b0_truth_convergence.py:76::test_el_proyecto_no_se_contradice_a_si_mismo`.
>
> **Sin release, y por regla**: `derive_semver.py` manda.
>
> ---
>
> <details>
> <summary>Bloque anterior (B0)</summary>
>
> **Bloque 2026-10-03 (B0) cerrado — Convergencia de verdad, SIN RELEASE.**
> Versión activa `0.22.5.dev0`; último tag `v0.22.5`.
>
> **B0 — el proyecto tenía cinco verdades y se contradecían entre sí.**
> WI-115 fue el último workitem de la serie «qué declara el repo que nada
> comprueba», y el propio objetivo del bloque lo dice: **esa serie era
> abierta** y podía producir trabajo indefinidamente. B0 la cierra.
>
> **Medido antes de arreglar nada** (`.pipelinek/b0_measure.py`, lectura):
>
> ```
> version activa (__init__.py) : 0.22.5.dev0
> release declarada (STATE)    : 0.22.5
> tag real (git describe)      : 0.22.5
> workitem (STATE)             : WI-96     ← vive 19 workitems atrás
> workitem (CURRENT)           : WI-115
> tests declarados (STATE)     : 2838
> tests colectados (árbol)     : 2844      ← el guard de WI-115 EN ROJO
> ```
>
> Lo que la cifra de 2844 delata: había un `tests/test_wi116_doctest_examples.py`
> **sin trackear**, y el guard de WI-115 —que compara el estado contra el
> árbol— estaba en rojo desde antes de abrir este bloque. Un guard que
> funciona se ve feo; uno que no funciona no se ve.
>
> **Lo que hace este bloque:**
>
> 1. `ROADMAP.md` **en la raíz**, autoridad única del futuro (B0..B9).
>    `docs/blueprint/plan/ROADMAP.md` pasa a **histórico**: era el roadmap
>    del blueprint v1, no el del proyecto vivo. Se queda donde está y lo
>    dice en su primera línea, en vez de mudarse — mudarlo rompería las
>    citas de la evidencia vieja, y esa evidencia es *provenance*.
> 2. `scripts/project_truth.py`: **una** respuesta machine-readable a
>    *«¿dónde está el proyecto y qué toca después?»*. El cruce de las cinco
>    verdades vive en `scripts/project_truth.py:239::_contradicciones`, y
>    la respuesta completa en `scripts/project_truth.py:277::estado`.
>    Nadie la reconstruye.
> 3. `tests/test_b0_truth_convergence.py`: pone rojo el repo si las cinco
>    verdades se contradicen de nuevo, **con dos contrasaltos** —que el
>    cruce degradado se note, y que una verdad ilegible sea un fallo y no
>    un verde.
>
> **El guard usa el script, no reimplementa el cruce.** Un guard que
> calcula lo mismo por su cuenta tiene dos copias de la misma regla y se
> divergen el día que una se actualiza y la otra no: el guard acaba
> midiendo algo que el proyecto ya no responde. Es el error de WI-106
> aplicado a una comparación.
>
> **Un guard huérfano re-homeado.** El fichero de doctests que estaba sin
> trackear es `tests/test_doctest_examples_are_executable.py`: se llama
> por su propiedad y no por `WI-116`, porque un guard cuyo nombre es un
> número caduca con el contador. La propiedad que mide —el ejemplo del
> `PlanBuilder` es ejecutable, `AGENTS.md §3.2.7`— es permanente. Probado
> por mutación: Making el ejemplo mentir pone **dos** tests en rojo.
>
> **SIN RELEASE, Y POR REGLA.** `scripts/derive_semver.py` sigue mandando
> y decide por sí solo; B0 no obliga a ninguna versión.
>
> ---
>
> <details>
> <summary>Bloque anterior (WI-115)</summary>
>
> **Bloque 2026-10-03 (vigésima séptima tanda) cerrado — WI-115, SIN RELEASE.**
> Versión activa `0.22.5.dev0`; último tag `v0.22.5`.
>
> **WI-115 — el estado declara una cifra y nadie comprueba que sea cierta.**
> Decimoséptima vía de la serie «qué declara el repo que nada comprueba».
> Y es la más autoconsciente: el workitem salió de una **línea que yo
> mismo escribí** en WI-113, al registrar un descarte. Decía, textualmente,
> que no existía ningún guard que comparase `tests.total` con el recuento
> real, y lo dejé anotado como una precisión sobre por qué ese campo no
> había causado el fallo. Era cierto, y era exactamente el siguiente hueco.
>
> **Medido en las dos direcciones**, con `STATE.yaml` restaurado byte a
> byte y sha verificado:
>
> ```
> STATE.yaml tests.total : 2834
> tests colectados       : 2834
> hoy coinciden: True
>
> M1  tests.total = 2834 -> 2971:  governance rc=0  VERDE (NO LO VE)
> M2  añadido 1 test (2835 colectados, estado en 2834):  rc=0  VERDE
> ```
>
> Que hoy coincidan no es la propiedad. La propiedad es: **si dejaran de
> coincidir, ¿algo se pone rojo?** La respuesta era no, por exceso y por
> defecto.
>
> **Lo que le da gravedad está medido también.** En WI-109 la primera
> certificación dio `2753 passed + 1 failed`, y **el fallo era este
> campo**. Su hermano `package_version` quedó vigilado desde entonces;
> este grande seguía a oscuras.
>
> **El recuento viene del árbol**, con `pytest --collect-only` en un
> subproceso. Un guard que comparase contra una copia escrita en el
> propio test sería el de WI-106: hoy acierta y el día que la verdad se
> mueva dirá lo contrario con toda la autoridad de un test. La verdad
> está en
> `tests/test_wi115_state_total_truthfulness.py:113::test_el_total_declarado_es_el_total_colectado`.
>
> **Un test y no una etapa de la receta**, porque `.pipeline.kts` tiene un
> SHA-256 declarado invariante desde WI-110. Una etapa nueva es un
> contrato de CI; un test es un test.
>
> **4 tests, 3 de ellos contrasaltos**: que el campo exista y sea entero
> (si no, borrar el campo daría un `KeyError` que parece un bug del
> guard), que el YAML siga parseando, y que el recuento real se pueda
> leer —sin ese último, el guard compararía contra un **cero silencioso**
> el día que pytest cambie una cadena de su salida.
>
> **Mutaciones 3/3**, y la sonda M2 mide precisamente ese cero: rompe el
> patrón de la salida de pytest, y el guard tiene que **fallar por no
> poder medirse**, no pasar. Está cazada. M3 no apuntaba al principio
> —ocho espacios de indentación donde el texto real tiene cuatro— y eso
> se comprobó **antes** de mutar, que es lo único que hace falta.
>
> **SIN RELEASE, Y POR REGLA.** Desde `v0.22.5` hasta HEAD hay
> `b/f/x/n/d 0/0/0/4/4`: la herramienta dice *«la regla dice SIN BUMP: no
> hay release que emitir, se acumula»*. Segundo bloque de la serie que no
> libera, después de WI-106, y es la regla siguiendo. `release.tag` sigue
> en `v0.22.5` porque describe la última release real, no el workitem en
> curso. La primera versión de este bloque **sí** decía «PATCH →
> v0.22.6» y tenía su sección de changelog: se corrige al medir, que es
> exactamente para lo que está la herramienta.
>
> ---
>
> <details>
> <summary>Bloque anterior (WI-114)</summary>
>
> **Bloque 2026-10-03 (vigésima sexta tanda) cerrado — WI-114, release `v0.22.5`.**
> Versión activa `0.22.5.dev0`; último tag `v0.22.5`.
>
> **WI-114 — la frontera de idempotencia la sostenían cinco personas distintas.**
> Decimosexta vía de la serie «qué declara el repo que nada comprueba».
> Elegida por medición, no por suposición: antes de abrirla se rastrearon
> ocho viñetas declaradas y **cuatro dieron cero** —`lru_cache`,
> `time.time()`, `Optional[T]`, ORM—, que se sostienen hoy y que no se
> abren porque instrumentar una verdad que nadie puede romper es la peor
> versión de un guard. La quinta dio un cero **sospechoso**: cero
> `ON CONFLICT` en todo el repo, con un `UNIQUE(event_id)` que sí existe.
>
> **El defecto, medido por AST sobre el árbol real:**
> `storage.py:568::_atomic_state_and_event` tenía un docstring que decía «Re-raise como
> `IdempotencyError` cuando el UNIQUE sobre `runtime_events.event_id` se
> viola (UAT-07, replay-safe)», y su cuerpo hacía `except
> BaseException: raise`. La traducción no la hacía ese método: **la
> hacían los cinco llamadores, cada uno por su cuenta, sin ningún guard.**
>
> ```
> 6 sitios escriben eventos. 5 traducen, 1 no.
> ```
>
> **Lo grave no es que hoy falle.** Es que `sqlite3.IntegrityError` no
> es `SkillGraphError`, luego atraviesa el `except` que traduce a exit
> code —el de WI-109— y sale como **Traceback al usuario**. Bastaba un
> camino de escritura nuevo sin `try` para abrir la frontera, y ese
> camino no tendría ni a quién preguntarle.
>
> **La traducción baja al helper** `_insert_event_in_tx`, que es donde
> ocurre el INSERT y por donde pasan los seis caminos. Los cinco
> llamadores capturan ahora el error **del dominio** para enriquecer el
> mensaje; su `except sqlite3.IntegrityError` era código muerto que
> además parecía vivo, porque de ahí se deducía que la traducción
> dependía de él.
>
> **El conjunto se deriva del árbol.** Ni los seis caminos ni las cinco
> funciones están escritos en el test: salen de buscar las llamadas a
> los dos helpers. Una lista de «los sitios que traducen» es la misma
> trampa que `DIRECTORIAS_NO_RECETA` (WI-99) y que «conectar ≠
> contener» (WI-102). Dos contrasaltos vigilan que la derivación no
> devuelva siempre la lista vacía y que el helper no quede muerto.
>
> **El instrumento también tuvo que cambiar**, y eso es lo que más me
> gusta del bloque: el script que medía «quién traduce» tenía como
> predicado exactamente la convención que este trabajo elimina. Después
> del arreglo daba 0 de 6, que no era un resultado sino una mentira. Ahora
> mide **de dónde puede salir** un error del adapter. Un guard que mide
> la convención que acabas de tirar necesita tirarse también él.
>
> **7 tests, 4/4 mutaciones** con sonda verificada contra el texto real
> **después** de `ruff format` antes de contar. Tres de las cuatro
> apuntaban al texto anterior: es el error 32 de WI-113 repetido, y se
> detectó porque el harness distingue `SIN_SONDA` de `CAZADA`.
> **1214 tests afectados verdes.**
>
> ---
>
> <details>
> <summary>Bloque anterior (WI-113)</summary>
>
> **Bloque 2026-10-03 (vigésima quinta tanda) cerrado — WI-113, release `v0.22.4`.**
> Versión activa `0.22.4.dev0`; último tag `v0.22.4`.
>
> **WI-113 — el `AgentResult` del Adapter era un alias del dict externo.**
> Decimoquinta vía de la serie «qué declara el repo que nada comprueba».
>
> `AGENTS.md §1.1` decía que un dict externo se envuelve en
> `MappingProxyType`. **WI-111** lo aplicó al `budget` del Handoff y
> dejó once campos `dict`/`list`/`set` dentro de dataclasses `frozen`
> como deuda registrada, con el criterio de que no participaban en el
> hash firmado.
>
> Ese criterio era correcto para el hash y **equivocado para el resto**.
> Uno de los once no tenía un dict mutable: tenía un **alias**.
> `AgentResult.from_fixture` validaba que `result` fuera un dict y lo
> guardaba **tal cual**. El `AgentResult` que el Core creía inmutable
> **era** el dict de quien lo produjo — y quien lo produce es el
> Adapter, que es código externo al repo.
>
> Medido antes de arreglar nada:
>
> ```
> externo = {"outcome": "ok", "result": {"dato": 1}}
> r = AgentResult.from_fixture(externo)
> externo["result"]["dato"] = 999
> r.result  ->  {'dato': 999}
> ```
>
> **No era cosmético**: `node_execution_delegations.py:443::_finalize_node_success` serializa
> ese dict a disco, así que lo persistido era el del Adapter. El
> hash firmado del Handoff no se ve afectado — por eso el descarte de
> WI-111 era correcto *para el hash* y no para el resto.
>
> **El guard ejecuta, no lee.** Por AST se vería que el campo está
> anotado `dict[str, Any]`, que es exactamente lo que la regla
> permite. La propiedad —«el valor no se aliasa al llamante»— solo se
> mide construyendo el objeto y mutando el origen.
>
> **Por qué aquí NO hay `MappingProxyType`, y en WI-111 sí.** En
> `HandoffExecution.budget` el dict solo se leía. Aquí el motor
> **serializa** el resultado y `json.dumps` no acepta un
> `mappingproxy`: envolverlo rompería la frontera. Se aplica
> `deepcopy` y no `dict()` porque el payload tiene niveles anidados y
> una copia de primer nivel deja los hijos compartidos. La
> inmutabilidad de este campo no la aporta el tipo, la aporta que el
> Core ya no comparte memoria con el exterior.
>
> **Los otros diez dicts no se abren.** Se buscó mutación sobre
> `procedencia_por_firma`, `revisiones_por_fuente`, `limites` y
> `metadatos`, y hay **cero** sitios que los toquen. Son dicts mutables
> dentro de un frozen, pero nadie los cambia: es deuda de estilo, no
> un defecto de comportamiento, y arreglarlos sería tocar código
> correcto sin prueba de que está mal.
>
> **15 tests, 3/3 mutaciones**, cada sonda verificada con ejecución
> real antes de contar. Un criterio se reformuló sobre la marcha: el
> test que exigía `MappingProxyType` se sustituyó por
> `test_el_resultado_es_un_dict_plano_y_serializable`, porque exigir el
> tipo habría roto la frontera que el arreglo respeta.
>
> **Un error propio (32).** El primer harness daba 1/3 porque la
> sonda M3 apuntaba a un texto que `ruff format` había colapsado a
> una línea. Una mutación `INVALIDA` no es una mutación: es un
> artefacto del formateo, y contarla habría hecho creer que el guard
> cazaba menos de lo que caza.
>
> ---
>
> <details>
> <summary>Bloque anterior (WI-112)</summary>
>
> **Bloque 2026-10-03 (vigésima cuarta tanda) cerrado — WI-112, release `v0.22.3`.**
> Versión activa `0.22.3.dev0`; último tag `v0.22.3`.
>
> **WI-112 — el reloj tenía diez puntos de definición y declaraba uno.**
> Decimocuarta vía de la serie «qué declara el repo que nada comprueba».
>
> `AGENTS.md §1.3` decía que el reloj «se inyecta (default factory con
> `datetime.now(UTC)`) y se puede mockear», y `runtime/engine.py`
> declaraba que `now_iso()` era el **«único punto de definición»**
> (`src/skillgraph/runtime/engine.py:41::now_iso`). **Ninguna de las dos
> se sostenía.**
>
> **Medido por AST**, no por cadena: **10** llamadas a `datetime.now`
> en el núcleo, en **tres** formatos — `isoformat()` 5,
> `replace(microsecond=0)` 2, `strftime` 3. Dos instantes del mismo
> segundo podían serializarse a dos strings que no comparaban entre sí.
>
> Y `RuntimeEvent` traía su propia copia:
> `field(default_factory=lambda: datetime.now(UTC).isoformat())`. Una
> lambda que captura el reloj real **no tiene por dónde inyectarle
> otro**: «se puede mockear» era cierto solo con monkeypatch.
>
> **El guard mide la propiedad, no el nombre**: «no hay una segunda
> lectura del reloj», no «existe una función llamada `now_iso`». RASTREA
> POR AST porque el docstring del propio `now_iso` menciona
> `datetime.now`, y un rastreo por cadena contaría la prosa. Hay dos
> tests que rompen si el rastreo pasa a buscar texto: uno con un
> docstring inventado y otro con el caso real del repo.
>
> **`strftime` se queda** en `backups`, `improvement` y `receipts`:
> producen `2026-10-03T09:00:00Z`, que es un **nombre de fichero**, no
> un instante de evento. La lista está en el guard, no en producción,
> porque es una excepción y no una regla, y se vigila en las dos
> direcciones.
>
> **El default factory se queda.** `AGENTS.md §1.3` lo pide, así que
> hacerlo obligatorio iba contra la regla — y rompía **37 tests** sin
> añadir capacidad. La inyección real es `now_iso(clock=...)` y
> `EventBuilder._emit(timestamp=...)`.
>
> **17 tests, 5/5 mutaciones**, mypy 143 antes y 143 después.
>
> **Dos cosas que pasaron en este bloque y que no eran suyas.**
> Un `Disk quota exceeded` de `/tmp` (38 GB de un tmpfs con cuota de
> 38,5, ocupado en 26 GB por trabajo ajeno). Y, al esquivarlo poniendo
> el sandbox **dentro** del repo, WI-89 felló diciendo que el sandbox
> escribía dentro del repositorio: **tenía razón**. Movido fuera, sin
> tocar el guard.
>
> **Y una prueba intermitente destapada por el formato único.**
> `test_wi56` comparaba dos llamadas al reloj real: falló 2 de 22.
> Medido, **4 de cada 2000** pares de `now_iso` separados por 2 ms
> cruzan un segundo. Con microsegundos nunca habría pasado — la
> unificación cambió la **probabilidad**, no la extensión. Se normaliza
> el instante, con un contrasalto que exige que la normalización no se
> coma el resto del registro.

</details>

---

<details>
<summary>Bloque anterior (WI-111)</summary>

> **Bloque 2026-10-03 (vigésima tercera tanda) en curso — WI-111, release `v0.22.2`.**
> Versión activa `0.22.2.dev0`; último tag `v0.22.2`.
>
> **WI-111 — la inmutabilidad del Handoff era de fachada.**
> Decimotercera vía de la serie «qué declara el repo que nada comprueba»,
> y la primera que encuentra el defecto en la estructura central: lo que
> el agente ve.
>
> `AGENTS.md §8` declaraba tres cosas del Handoff —inmutable, hash
> SHA-256 estable, y que el Adapter «recibe el hash firmado; nunca lo
> recalcula»— y **ninguna se sostenía**. Las tres tenían la misma causa:
> `frozen=True` congela el **enlace** del atributo, no su **valor**, y
> `HandoffExecution.budget` era `dict[str, int]`.
>
> **Medido, no teórico.** El budget está **dentro del hash**, y el motor
> lo persistía **antes** de invocar al Adapter
> (`src/skillgraph/runtime/node_execution_delegations.py:260::_compile_node_handoff`,
> dentro de `_compile_node_handoff`) y lo **recalculaba después**, en la
> línea 144 de la versión previa a WI-111. Ejecutando un nodo real y
> leyendo de disco:
>
> ```
> fila node_executions.context_hash : 0063e7dfd167afc6...
> evento NodeCompleted               : 951a2d3a16cf7ea8...
> evento EvidenceProduced            : 951a2d3a16cf7ea8...
> hash que el Adapter vio AL ENTRAR  : 0063e7dfd167afc6...
> budget en handoff_json persistido  : {'max_nodes': 1}
> ```
>
> La fila describe el handoff de **antes** y los eventos el de
> **después**, para la misma `node_execution`. La línea 144 hacía
> exactamente lo que la viñeta prohíbe.
>
> **El guard no lee el código: ejecuta un nodo.** Uno por AST habría
> medido la regla y no el defecto, que estaba en la distancia temporal
> entre firmar y entregar — y esa distancia no está en el texto de
> ningún fichero.
>
> **Tres defectos del propio guard**, que las mutaciones dejaron ver y
> que quedan escritos en `AGENTS.md §8`: un test comparaba contra una
> llamada **nueva** de `_handoff()` y no podía fallar nunca;
> `MappingProxyType == dict` es `True`, así que comparar con `==` pasaba
> con el mapping vivo; y contar llamadas a `context_hash` sin distinguir
> el origen contaba la lectura del Adapter como una recalculación del
> motor.
>
> **M5 se reescribió dos veces**: la primera quitaba el `sorted()`, que
> resultó **inocua** — quitar el orden no rompe la copia— y su sonda
> apuntaba al test tautológico.
>
> **5/5 mutaciones**, 19 tests, 2795 passed, 0 skipped.
>
> **Dos guards rotos por el propio cambio**, resueltos cambiando el
> código y no la regla: el de 80 LoC (WI-66) se cumplió extrayendo
> `_open_running_node` — 74 → 83 → 76 — y el de WI-67, la lista de
> métodos movidos, pasó de 22 a 23. **Un umbral que se sube para que el
> código pase no comprueba nada.**

</details>

---

<details>
<summary>Bloque anterior (WI-110)</summary>

> **Bloque 2026-10-03 (vigésima segunda tanda) cerrado — WI-110, release `v0.22.1`.**
> Versión activa `0.22.1.dev0`; último tag `v0.22.1`.
>
> **WI-110 — la etapa `evidence` se verificaba a sí misma y la cadena no volvía.**
> Duodécima vía de la serie «qué declara el repo que nada comprueba», y la
> primera que no cierra un hueco del **código** sino del **instrumento**.
> Las once anteriores cerraban una propiedad sin comprobar; esta hace que
> el aparato que comprueba pueda volver a comprobar.
>
> **Medido, no teórico** — `8d6a9594` (03:48:17) fue el último run con las
> 8 etapas en `success`. Los **cinco siguientes** tuvieron las **siete
> etapas de código** en `success`, `2754 passed`, y **todos** terminaron en
> `failure`.
>
> **La causa**: `evidence` mide el run **anterior** (cuando corre, el run
> en curso aún no tiene `RunFinished`), así que su propio paso aparece
> como `StepFailed` dentro del run que falló por ella, y
> `check_pipeline_receipt.py:314::evaluar` lo rechazaba por el **mismo**
> criterio con el que rechaza un fallo de código. **Un fallo ya
> corregido no devolvía la cadena a verde**: dejaba de estar en el código
> pero seguía en el veredicto.
>
> **Y la medición desmintió el diagnóstico del bloque anterior.** WI-109
> escribió que arreglarlo exigía tocar `.pipeline.kts`, y lo descartó por
> eso. Era **medio verdad**: el criterio no vive en la receta, vive en
> `evaluar()`. Por eso el SHA-256 de `.pipeline.kts` **no cambia**,
> sigue `7541ced5…`, y las once certificaciones anteriores siguen
> valiendo. Un test lo fija.
>
> **El cambio de fondo es el nombre.** `step_failed` era un **contador**,
> y un contador no sabe quién falló: por eso no había base para exculpar.
> `InformeRun.paso_fallido` lo lleva desde el journal.
>
> **La exculpación es mínima**, por eso son **tres** condiciones: un solo
> `StepFailed`, con el nombre conocido, y que el nombre sea `evidence/`.
> Y el **veredicto del run nunca** se exculpa.
>
> **Medido**: `startswith(ETAPA_AUTOEVALUADA)` sin la barra dejaba pasar
> `evidence-hack/sh-0`. Lo cazaron las ocho etapas del parametrize, y mi
> propio comentario lo daba por bueno: un comentario que describe un
> hueco sin cerrarlo es una promesa que el código no cumple.
>
> **11/11 mutaciones** con sonda por mutación, y el harness distingue
> **cuatro** salidas porque cuatro sondas apuntaban mal y las contaba
> como victorias sin que el guard hubiera opinado.
>
> **Certificado** — run `be32259e-f012-47f7-b146-1490343ada10`, terminado
> a las `06:10:30.751893188Z`, `exit=0`, `RunFinished outcome=success`,
> **8/8 etapas en `success`**, `2776 passed in 277.98s`. Leído del
> journal **después** de terminar, por `run_id` **y** `occurred_at`.
>
> **La línea que prueba el arreglo** la escribió la propia etapa
> `evidence` al evaluarse a sí misma:
>
> ```
> run bf2a8e23-c07d-46f9-89f2-9ac939be3ea5: 7/7 etapas, 9 pasos,
> veredicto 'failure'
> ```
>
> **`evidence` pasó evaluando un run en `failure`.** Esa combinación era
> imposible antes: el run en `failure` es el inmediatamente anterior, y
> su único `StepFailed` era el propio fallo de `evidence`. El deadlock se
> había exculpado a sí mismo. Lo que se midió es que la cadena **deja de
> envenenarse**; un run con `evidence` en rojo y las otras siete verdes
> sigue terminando en `FAILURE` por construcción, y llega verde **uno
> después**.

---

<details>
<summary>Bloques anteriores (WI-109 y anteriores)</summary>

> **Bloque 2026-10-03 (vigésima primera tanda) cerrado — WI-109, release `v0.22.0`.**
> Versión activa `0.22.0.dev0`; último tag `v0.22.0`. 2754 passed, **0 skipped**.
>
> **WI-109 — la tercera viñeta de §1.2 que nadie ejecutaba, y una entrada
> de usuario que salía como traceback.**
> Undécima vía de la serie «qué declara el repo que nada comprueba», y la
> primera cuya regla resultó **menos** violada de lo que la alerta suponía.
>
> La consigna era `AGENTS.md §1.2`: *prohibido `raise ValueError` /
> `raise Exception` en código de dominio*. **Medida antes de tocar nada**:
> `grep -rn 'raise ValueError|raise Exception' src/` → **0**. La
> prohibición literal **se cumple**. Instrumentarla habría sido vigilar una
> verdad que nadie puede romper: la peor versión de un guard.
>
> Lo que el dominio lanza de verdad son **otros** builtins —`TypeError` ×6,
> `KeyError` ×5, `RuntimeError` ×2, `NotImplementedError` ×1, medido por
> AST— y todos en invariantes internas de adaptadores (`unwrap()`,
> `dto.py`), ninguno en el camino de error que ve el usuario.
>
> **El defecto real estaba en la tercera viñeta**, que sí era cierta y no
> estaba instrumentada: *«cada excepción lleva un `code` estable (`sg_*`)
> usado por la CLI para traducir a exit codes»*. Medido en tres partes:
>
> 1. **La traducción no existía.** `runner.main` hacía
>    `except SkillGraphError -> return EXIT_DOMAIN` (10) para todo. Los
>    códigos 11 y 12 solo se alcanzaban porque **cada comando repetía su
>    propio `except ParseError`**: la decisión la tomaba el *tipo* en el
>    sitio de la llamada, y el `code` se imprimía sin decidir nada.
> 2. **Entrada de usuario malformada salía como traceback.**
>    `knowledge compile <p> '{"obligatory": ['` devolvía **rc=1** con el
>    `Traceback` entero de `json.JSONDecodeError`: el `json.loads` estaba
>    **fuera** del `try` y `JSONDecodeError` no es `SkillGraphError`.
> 3. **Tres clases compartían `sg_error`** (`SkillGraphError`,
>    `SelfCertificationBlockedError`, `HandoffBlockedError`) y **dos
>    `sg_invalid_expansion`**. Un `code` compartido no puede mapear a dos
>    exit codes distintos, y entonces el `code` deja de ser la clave: la
>    traducción prometida **no se podía construir encima de él**.
>
> **Ahora** `src/skillgraph/cli/exit_codes.py:77::exit_para` es la
> traducción: pura sobre `exc.code`, en el módulo hoja que **sigue sin
> importar nada** porque ADR-0016 lo movió allí para que `parser.py`
> consuma el contrato sin arrastrar `Storage`. Y
> `src/skillgraph/cli/runner.py:256::main` la cablea, con un `code`
> desconocido cayendo en `EXIT_DOMAIN` y **nunca** en `EXIT_OK`: 0
> significa éxito, y un error de dominio que sale con 0 es peor que uno
> que sale con 10.
>
> **Medido con el binario**: `rc=1 + Traceback` → `rc=11 + ERROR (sg_parse)`.
> Los errores de dominio no distinguibles **siguen en 10**, que es lo que
> afirman 16 tests que ya existían: cambiarlo habría roto un contrato
> as-built bien observado, y aquí no se cambia comportamiento observable
> que no sea el defecto.
>
> **El guard que mira el cableado mira el AST, no el texto.** La primera
> versión buscaba la cadena `return EXIT_DOMAIN` y se puso roja **por su
> propio comentario**, que explica por qué se sustituyó. Tercera vez en
> tres semanas por el mismo motivo (WI-98 con rutas absolutas, WI-108 con
> el patrón de `pytest.skip`): un guard que busca una cadena busca la
> cadena.
>
> `tests/test_wi109_code_to_exit.py` (19 tests): la traducción por
> `code`, que `main()` la cablea, que ningún `json.loads` de la CLI queda
> sin `try` (`:325`), que ningún `code` comparte clase (`:449`), y que la
> receta malformada no escapa (`:241`).
>
> **Mutaciones 11/11 con sonda.** Una no la cazó la sonda, y la señal fue
> que **M6 no la cazó**, no que el guard estuviera roto: `code = "sg_error"`
> es una *colisión* (la clase declara code, el mismo que otra), no una
> *herencia* (no tenerlo en `__dict__`). Son dos propiedades con dos
> tests. Se corrigió la sonda y se añadió M6b para la herencia.
>
> **Release `v0.22.0`**: MINOR derivado con `scripts/derive_semver.py`
> (`b/f/x/n/d 0/1/0/3/0`). Etiqueta anotada, post-release con el `sha`
> real.
>
> **Sin push**: 158 commits sin publicar, `origin/main` en `0ebbd58`.

---

> **Bloque 2026-10-03 (vigésima tanda) cerrado — WI-108, release `v0.21.2`.**
> Versión activa `0.21.2.dev0`; último tag `v0.21.2`. 2735 passed, **0 skipped**.
>
> **WI-108 — la regla que se escribe con tu letra y no se comprueba con ninguna.**
> Décima vía de la serie «qué declara el repo que nada comprueba», y la más
> pequeña en código: una prohibición de siete palabras con su «por qué»
> escrito al lado.
>
> `AGENTS.md §6.2` dice: **NO usar `pytest.skip` para esconder fallos**,
> y que *un skip por falta de artefacto es el mismo defecto, con otra
> forma*. La segunda línea la escribió WI-103 midiendo un gate que se
> saltaba por falta de informe. De todo el repo, los instrumentos que
> miran skips: **0**. Las etapas de la receta que los miran: **0**.
>
> **Medido antes de tocar nada**, con un run sintético cuyo único cambio es
> la línea de resumen del journal:
>
> ```
> run sin skips:   0 problemas []
> run con 3 skips: 0 problemas []
> veredicto: «OK: el run cumple los criterios que declara AGENTS.md»
> ```
>
> **El detalle grave no es el regex.** Es que el **criterio 2** —el que
> existe para separar un run real de un veredicto cacheado— acepta un
> resumen con skips: `2715 passed, 3 skipped` casa con su regex igual que
> `2718 passed`. No es un bug del regex: es que **la pregunta no se había
> hecho**. Una regla y el criterio que la vigila no se contradicen cuando
> nunca se cruzan.
>
> **Y la regla la incumplía el autor de la regla.** De los cinco skips,
> dos son de plataforma (`fcntl` no existe en Windows: no esconden un
> fallo) y **tres de artefacto** —«sin journal: clon nuevo»—, que es
> literalmente lo que la segunda línea prohíbe. Los escribí yo en WI-105,
> en el guard que construí para no esconder nada.
>
> **Ahora**, `tests/test_wi108_zero_skips.py:301::TestTodoSkipEstaDeclarado`
> exige que no haya skip de ejecución y que los legítimos estén
> declarados, y `scripts/check_pipeline_receipt.py:240::resumen_sin_skips`
> es el predicado puro que la etapa `evidence` mide vía
> `sg_pipeline_tests_skipped`. Pregunta por el **valor**, no por la
> presencia: `0 skipped` es un run limpio.
>
> **Los 3 skips se fueron y no se sustituyeron por nada**, que es la
> decisión que hay que defender: medían el **entorno** —qué pasó en esta
> máquina— y no el **entregable**. El journal no está versionado, así que
> en un clon nuevo se saltaban en silencio y la suite pasaba en verde con
> skips. La tabla de dónde vive ahora cada propiedad está en el fichero
> donde estaban, en `TestLaClaseDeTestQueVivioAQui`.
>
> **El guard que mira el código mira el AST, no el texto.** La primera
> versión buscaba `pytest.skip(` con regex y se puso roja **por su propia
> documentación**: un docstring que cita el patrón es indistinguible de una
> llamada. Segunda vez en dos semanas, mismo repositorio, mismo motivo.
>
> **Mutaciones 9/9 en tres pasadas.** Una de las nueve no la cazó la
> primera sonda porque medía la forma de retorno de un árbol sin llamadas,
> donde esa forma nunca se ejerce: la mutación era inválida, y el harness
> lo dijo en vez de acusar al guard.
>
> **2735 passed y 0 SKIPPED** (+17: 20 tests nuevos de WI-108 menos los 3
> de WI-105 que se fueron). La aritmética y el run coinciden:
> `2718 + 20 − 3 = 2735`. Run canónico `2387c4cc`, verificado por `run_id`.
>
> **Release `v0.21.2`**: PATCH derivado con `scripts/derive_semver.py`
> (`b/f/x/n/d 0/0/1/4/0`). Commit `841a075`, etiqueta anotada sobre él,
> post-release `4eb56af`.
>
> **Sin push**: 156 commits sin publicar, `origin/main` en `0ebbd58`.


>
> **WI-108 — la regla que se escribe con tu letra y no se comprueba con ninguna.**
> Décima vía de la serie «qué declara el repo que nada comprueba», y la más
> pequeña en código: una prohibición de siete palabras con su «por qué»
> escrito al lado.
>
> `AGENTS.md §6.2` dice: **NO usar `pytest.skip` para esconder fallos**,
> y que *un skip por falta de artefacto es el mismo defecto, con otra
> forma*. La segunda línea la escribió WI-103 midiendo un gate que se
> saltaba por falta de informe. De todo el repo, los instrumentos que
> miran skips: **0**. Las etapas de la receta que los miran: **0**.
>
> **Medido antes de tocar nada**, con un run sintético cuyo único cambio es
> la línea de resumen del journal:
>
> ```
> run sin skips:   0 problemas []
> run con 3 skips: 0 problemas []
> veredicto: «OK: el run cumple los criterios que declara AGENTS.md»
> ```
>
> **El detalle grave no es el regex.** Es que el **criterio 2** —el que
> existe para separar un run real de un veredicto cacheado— acepta un
> resumen con skips: `2715 passed, 3 skipped` casa con su regex igual que
> `2718 passed`. No es un bug del regex: es que **la pregunta no se había
> hecho**. Una regla y el criterio que la vigila no se contradicen cuando
> nunca se cruzan.
>
> **Y la regla la incumplía el autor de la regla.** De los cinco skips,
> dos son de plataforma (`fcntl` no existe en Windows: no esconden un
> fallo) y **tres de artefacto** —«sin journal: clon nuevo»—, que es
> literalmente lo que la segunda línea prohíbe. Los escribí yo en WI-105,
> en el guard que construí para no esconder nada.
>
> **Ahora**, `tests/test_wi108_zero_skips.py:301::TestTodoSkipEstaDeclarado`
> exige que no haya skip de ejecución y que los legítimos estén
> declarados, y `scripts/check_pipeline_receipt.py:240::resumen_sin_skips`
> es el predicado puro que la etapa `evidence` mide vía
> `sg_pipeline_tests_skipped`. Pregunta por el **valor**, no por la
> presencia: `0 skipped` es un run limpio.
>
> **Los 3 skips se fueron y no se sustituyeron por nada**, que es la
> decisión que hay que defender: medían el **entorno** —qué pasó en esta
> máquina— y no el **entregable**. El journal no está versionado, así que
> en un clon nuevo se saltaban en silencio y la suite pasaba en verde con
> skips. La tabla de dónde vive ahora cada propiedad está en el fichero
> donde estaban, en `TestLaClaseDeTestQueVivioAQui`.
>
> **El guard que mira el código mira el AST, no el texto.** La primera
> versión buscaba `pytest.skip(` con regex y se puso roja **por su propia
> documentación**: un docstring que cita el patrón es indistinguible de una
> llamada. Segunda vez en dos semanas, mismo repositorio, mismo motivo.
>
> **Mutaciones 9/9 en tres pasadas.** Una de las nueve no la cazó la
> primera sonda porque medía la forma de retorno de un árbol sin llamadas,
> donde esa forma nunca se ejerce: la mutación era inválida, y el harness
> lo dijo en vez de acusar al guard.
>
> **2735 passed y 0 SKIPPED** (+17: 20 tests nuevos de WI-108 menos los 3
> de WI-105 que se fueron). La aritmética y el run coinciden:
> `2718 + 20 − 3 = 2735`. Run canónico `2387c4cc`, verificado por `run_id`.
>
> **Release `v0.21.2`**: PATCH derivado con `scripts/derive_semver.py`
> (`b/f/x/n/d 0/0/1/4/0`). Commit `841a075`, etiqueta anotada sobre él,
> post-release `4eb56af`.
>
> **Sin push**: 156 commits sin publicar, `origin/main` en `0ebbd58`.

---
---

<details>
<summary>Bloques anteriores (WI-106 y anteriores)</summary>

> **Bloque 2026-10-03 (decimoctava tanda) cerrado — WI-106, SIN RELEASE.**
> Versión activa `0.21.0.dev0`; último tag `v0.21.0`. 2703 passed, **0 skipped**.
>
> **WI-106 — la causa de un bump era una afirmación sin verificar.**
> Octava vía de la serie «qué declara el repo que nada comprueba», y la
> más pequeña: un solo campo.
>
> `STATE.yaml` declara **por qué** se movió la versión
> (`release.semver_bump`). `scripts/derive_semver.py` la **calcula**.
> Nadie los comparaba: el campo aparecía en un sitio y en dos informes de
> `audits/`, y ningún test lo leía.
>
> **Medido**, con `STATE.yaml` restaurado byte a byte y sha verificado:
> puesto el campo a `MAJOR` cuando el release fue `MINOR`, la suite de
> gobernanza de release daba **18 passed, exit 0**, y los tres checkers
> de la receta y el bundle de auditoría, también `exit 0`. Con el guard
> puesto, la misma mentira da **2 failed, exit 1**.
>
> **Ahora se contrasta:**
> `tests/test_wi96_semver_rule.py:380::TestLaDeclaracionDelBumpCoincideConLaHerramienta`
> exige que el campo sea lo que la regla dice para `release.tag`. El
> **nivel** de la versión ya estaba verificado —la lista de divergencias
> históricas no puede crecer—; lo que no exigía nadie es que el campo
> dijera la verdad.
>
> **Dos trampas, y las dos las encontré porque las mutaciones
> sobrevivieron.** La primera versión daba 4/6. (1) Comparar contra una
> **constante escrita a mano**: hoy la copia dice lo mismo que la verdad,
> y el día que la regla cambie dirá lo contrario — se exige que el cálculo
> acierte en **dos bumps distintos**, cosa que un literal no puede. (2)
> Comprobar el dominio sobre el valor de hoy: que `MINOR` sea válido no
> es que el dominio exista, así que `RELLENO` y `v9.9.9` tienen que ser
> rechazados por entrada, no por el valor real.
>
> **M1 —borrar la aserción que manda— NO se cuenta como fallo.** Es
> indetectable por construcción: un test que comprueba que el estado
> coincide con la herramienta no puede comprobar que sigue ahí. Lo que
> se mide es su interacción con M6, y con M1 puesta el estado puede
> mentir y nadie lo ve: la demostración de que era el **único** punto de
> aplicación. Mutaciones 6/6.
>
> **SIN RELEASE, y por regla.** Los cinco commits desde `v0.21.0`
> clasifican como `neutro` —ni `feat` ni `fix`— así que
> `derive_semver.py` dice **SIN RELEASE**, y `AGENTS.md §12` es
> explícito: *«Si la regla dice “sin bump”, no se emite etiqueta: el
> trabajo se acumula»*. Es el primer bloque de la serie que no libera, y
> es la regla siguiendo en vez de la regla saltándose.
>
> **Dos hipótesis que medí y resultaron falsas**, antes de llegar a esta:
> que el `pre-push` comprobara el CI con un `grep` sobre el stdout —falso:
> usa el exit code, y `ci.sh` pasa `--rerun`— y que los cuatro UAT stub
> pudieran desaparecer en verde —falso: WI-101 lo cerró, `--verify` da
> exit 1 con `persistido=MISSING`.
>
> **Sin push**: 143 commits sin publicar, `origin/main` en `0ebbd58`.

</details>
</details>
