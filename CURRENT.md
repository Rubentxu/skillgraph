# CURRENT — puntero operativo
> **Bloque 2026-10-03 (vigésima séptima tanda) en curso — WI-115, SIN RELEASE.**
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
