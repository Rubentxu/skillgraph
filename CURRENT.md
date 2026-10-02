# CURRENT — puntero operativo

> **Bloque 2026-10-02 (duodécima tanda) cerrado — WI-100, release `v0.20.1`.**
> Versión activa `0.20.1.dev0`; último tag `v0.20.1`. 2647 passed.
>
> **WI-100 — los hooks de git decían una cosa y hacían otra.**
> WI-99 dejó escrito, en dos sitios, que `scripts/hooks/pre-push` era deuda
> medida: mide con un instrumento distinto del canónico. Una deuda con
> dueño escrito es una promesa; este bloque la paga.
>
> **La medición, mismo commit y mismo `.coverage.rc`, única variable el hook
> `.pth`:**
>
> | módulo | hooks | `coverage.sh` | Δ |
> |---|---|---|---|
> | `cli/commands/runs.py` | **39 %** | **88 %** | **−49** |
> | `cli/runner.py` | 55 % | 79 % | −24 |
> | `cli/support.py` | **69 %** | 86 % | **−17** |
> | TOTAL | 90,79 % | 95,22 % | −4,4 |
>
> `cli/support.py` mide **69 %**, y el suelo que declara el propio
> `AGENTS.md §6.3` para la CLI es **70 %**. El gate más cercano al push
> podía dar **verde un paquete que no cumplía el suelo declarado**, y no
> ejecutaba ninguno de los cuatro contratos exigibles.
>
> **Lo que se decia y lo que se hacia.** El `pre-push` afirmaba que «el CI
> solo verifica que la ejecución es reproducible» — un mundo anterior a
> WI-98, donde el remoto era otro workflow. El `pre-commit` afirmaba ser un
> smoke de ~10 s: seleccionaba los `.py` staged y **no se los pasaba**.
> Medido: **2636 tests, 124,29 s**. El selector existía; la instrucción no.
> Ahora son **0,83 s**.
>
> **C4 se afina y la excepción desaparece.** La condición pasa a «pytest
> **sobre el repo entero**» (`evaluar_una_receta`,
> `check_ci_recipe_parity.py:452`): un hook que filtra por paths no emite un
> veredicto sobre el repo, y queda fuera sin una lista que lo diga
> (`filtra_por_ficheros`, `check_ci_recipe_parity.py:306`).
> `DIRECTORIOS_NO_RECETA` ya no existe. **Una propiedad que hay que
> mantener al día no es una propiedad, es una suscripción.**
>
> **Dos fallos del propio guard, y ninguno lo encontró un test:**
>
> - El guard **no veía los hooks**: `rglob("*.sh")` no los encuentra
>   porque no tienen extensión (`es_script_shell`,
>   `check_ci_recipe_parity.py:286`). Es la **segunda vez** en este bloque.
> - Un **`echo` de diagnóstico** con `pytest` y `$N_STAGED` hacía que
>   `filtra_por_ficheros` lo tomara por invocación, y C4 llevaba **dos
>   commits dando verde por el motivo equivocado** (`_VERBOS_DE_MENCION`,
>   `check_ci_recipe_parity.py:210`). Un guard que confunde un **mensaje**
>   con una **ejecución** no mide qué corre: mide qué se dice.
>   Lo encontró la mutación M7 (`test_un_mensaje_no_es_una_invocacion`,
>   `test_wi98_ci_recipe_parity.py:590`).
>
> **Mutaciones 10/10.** M4 es la más representativa: el hook **sigue
> diciendo** `HOOK_SKIP_PUSH_TESTS` en la cabecera, así que el guard de
> cadena de WI-99 la habría aprobado. Dos de los tests nuevos **ejecutan**
> el hook sobre un repo de prueba (`test_hooks_system.py:269`): es la
> primera vez que ese fichero comprueba comportamiento y no forma.
>
> Evidencia: `evidence/sddk-wi100-verify-2026-10-02.md`.

> **Bloque 2026-10-02 (undécima tanda) cerrado — WI-99, release `v0.20.0`.**
> Versión activa `0.20.0.dev0`; último tag `v0.20.0`. 2636 passed.
>
> **WI-99 — la evidencia de auditoría no era reproducible.**
> `scripts/audit_bundle.sh` existe para dar evidencia reproducible a una
> auditoría independiente. La medición dio que no lo era:
>
> | mismo commit `504b65d` | resultado |
> |---|---|
> | árbol de trabajo | `2625 passed` |
> | **clon limpio** | **`2 failed, 2623 passed`** |
>
> El mensaje literal del guard que fallaba era *«afirmación sin respaldo»*.
> **Un guard que dice la verdad y falla donde se audita no es un test rojo:
> es un entregable declarado cumplido cuya evidencia no viaja en el repo.**
>
> **Tres causas, las tres medidas antes de tocar nada:**
>
> 1. `.gitignore` tapaba la evidencia. `STATE.yaml` declaraba dos
>    entregables de H9 cumplidos con documentos que **no estaban
>    versionados**. De 150 referencias: 3 no versionadas, 1 inexistente
>    (anotada como irrecuperable — *no se inventó el testigo*), 3 bajo
>    `external/` y 1 plantilla.
> 2. `scripts/ci.sh` era una **cuarta receta**: 3 stages, 0 contratos
>    exigibles, `cli/commands/runs.py` al **39 %** frente al 87,96 % de la
>    instrumentada. Y `audit_bundle.sh` lo invocaba — el instrumento que
>    existe para medir medía con el que no ve. Ahora **delega**.
> 3. El **comando canónico no arrancaba en un clon nuevo**: `mise trust` y
>    que exista `.pipelinek/`. `pipelinek` abre el *fichero* SQLite, no el
>    directorio. Misma categoría que las diez rutas absolutas de WI-98: una
>    regla que no se puede cumplir fuera de esta máquina es una costumbre.
>
> **C4, el invariante que impide la recaída:** un script de `scripts/` que
> ejecuta `pytest` tiene que estar conectado a la receta canónica: o es un
> **fragmento** que ella invoca (`scripts_invocados_por`,
> `check_ci_recipe_parity.py:219` — se **leen** de `.pipeline.kts`, no de una
> lista aparte), o **delega** en ella (`evaluar_una_receta`,
> `check_ci_recipe_parity.py:329`). El veredicto se emite en
> `CODIGO_RECETA_SUYA`, `check_ci_recipe_parity.py:79`.
>
> Disyuntiva a propósito: la versión restrictiva hace del propio fichero de
> cobertura una infracción y sólo admite una lista de excepciones que el
> guard mantiene. `scripts/hooks/` queda excluido por
> `DIRECTORIOS_NO_RECETA`, `check_ci_recipe_parity.py:110`, y un test fija
> esa exclusión para que ampliarla no sea una puerta trasera.
>
> **Mutaciones 6/6**, y M1 restaura el `ci.sh` **real** de antes de WI-99,
> sacado de git: un contraejemplo inventado demuestra que el test está bien,
> no que el guard muerde. M6 —que amplía la exclusión hasta tapar
> `scripts/`— no pone rojo el checker sino **el test que fija la
> exclusión**: un guard que se puede silenciar a sí mismo no está verificado.
>
> **Cierre: divergencia 0 en el commit `984289d`.** Bundle sobre ese commit
> en clon limpio — `Pipeline finished with SUCCESS`, **8/8 stages**,
> **2636 passed**, cobertura 95,22 %, `PASS=16 FAIL=0`. El mismo commit da
> 2636 en el árbol y 2636 en el clon. Antes: 2625 y 2623+2 failed.
>
> **Y una corrección que esa medición no cubría.** Al escribir esta
> trazabilidad, la CI local dio `2 failed, 2634 passed`: el tag `v0.20.0` no
> estaba registrado en `STATE.yaml` y este bloque no citaba ninguna línea
> verificable. Dos guards existentes los atraparon. La divergencia 0 estaba
> medida **para `984289d`**, que es anterior a la trazabilidad; escribir
> «divergencia 0» como propiedad del estado final era una afirmación que
> nadie había medido. Corregido y re-medido.
>
> Evidencia: `evidence/sddk-wi99-verify-2026-10-02.md`.

> **Bloque 2026-10-02 (décima tanda) cerrado — WI-98, release `v0.19.0`.**
> Versión activa `0.19.0.dev0`; último tag `v0.19.0`. 2625 passed.
>
> **WI-98 — el remoto ejecutaba otra receta, y el guard buscaba cadenas.**
> `AGENTS.md` dice que todo runner remoto **debe** invocar el mismo
> `.pipeline.kts`. No lo hacía, y —esto es lo que el bloque midió— **no
> podía**: el script llevaba diez rutas absolutas a `/var/mnt/...`, así que
> la regla era una promesa inejecutable.
>
> **La divergencia, medida con el mismo instrumento:**
>
> | | receta local | `ci.yml` antes |
> |---|---|---|
> | stages ejecutados | **8** | **1** (`lint`) |
> | contratos exigibles | 4 | **0** |
> | `cli/commands/runs.py` | 87,96 % | **39 %** |
> | `cli/support.py` | 85,71 % | **69 %** ← suelo declarado: 70 % |
>
> El remoto podía dar **verde** un paquete que no cumplía el suelo que el
> propio `AGENTS.md §6.3` declara.
>
> **El guard cayó en la trampa que viene a cerrar.** Las cinco primeras
> mutaciones dieron `rc=0`: C1 buscaba `.pipeline.kts` en el contenido
> entero del workflow y lo encontraba en un comentario que explica que se
> usa; C2 buscaba rutas absolutas solo dentro de `sh(...)` y no las veía
> cuando estaban en una `val` de Kotlin, que es justo donde se mueven para
> arreglar el problema. **Un invariante que solo mira una sintaxis
> concreta se esquiva cambiando de sintaxis.**
>
> El script de mutaciones tampoco estaba mal, por dos motivos que quedan
> escritos: `mktemp` pasa por un wrapper que manda el fichero recién creado
> a la papelera, y las mutaciones sustituían una línea de un bloque
> `run: >` dejando las siguientes. **Un contraejemplo que no degrada nada
> no prueba que el guard funcione: prueba que el script de mutaciones
> está mal.**
>
> 20 tests, mutaciones **5/5**, stage nuevo `ci-parity` (**ocho stages**) —
> el cuarto contrato exigible y el primero que vigila a los otros tres.
>
> **Lectura estricta, escrita como decisión y no como cita**: `AGENTS.md §6.3`
> nombra `runtime` entre los módulos del core pero no enumera cada fichero. Se
> eligió que **todo módulo de `runtime/` con código herede el 90 %**, porque es
> la lectura que hace útil el contrato y la que encuentra el hueco. Consecuencia
> asumida: el checker **exige suelo declarado para todo módulo de `runtime/`
> con código** (`check_coverage_floors.py:55` mantiene el mapa; un módulo nuevo
> sin suelo pasa por él o aborta), para que añadir uno no pase inadvertido. Un
> guard que sólo vigila la lista que él mismo mantiene no vigila nada.
>
> **Dos decisiones de diseño del checker** (`scripts/check_coverage_floors.py`,
> suelos en `check_coverage_floors.py:55`, global en
> `check_coverage_floors.py:90`): agrega **recuentos, no porcentajes** (con
> `branch=true` una rama parcial cuenta como media, y promediar porcentajes da
> más de lo que hay: un paquete al 95 % de media puede esconder un módulo al
> 60 %); y un **suelo sobre un módulo fantasma es un fallo**, no un silencio. Los
> módulos vacíos (los `__init__.py` de reexport, 0 sentencias) quedan excluidos:
> exigirles suelo es medir un fichero vacío y revienta con división por cero.
>
> **CI**: `unit-tests` corre la **receta** en vez de pytest a pelo — **una sola
> pasada** para tests y cobertura, porque correr pytest dos veces costaría
> 110 + 203 s — y hay un stage nuevo `coverage-floors` que ejecuta el checker.
> Seis stages. Mutaciones del checker **3/3** con baseline y control final
> byte-idéntico.
>
> **Aprendizaje reutilizable, con su error medido**: durante el desarrollo leí
> `rc=0` de un `if pipeline | tail; then …` — el `rc` era el de `tail`, no el del
> pipeline, y el script estaba reportando cinco incumplimientos. Misma familia
> que medir `/usr/bin/sg` en vez de `skillgraph` (WI-88) o `wc -c` sobre una
> línea con `—` (WI-91): **medir la cosa equivocada produce un número que
> parece confirmar cualquier premisa.** Y una segunda medición dio 408 s de wall
> clock, pero ese comando incluía pasos extra y corría con carga concurrente;
> reportar 408 s como coste de la receta habría sido una medición equivocada con
> formato de dato.
>
> **CI certificada**: `Pipeline finished with SUCCESS`, **6/6 stages**
> (`discover-repo`, `sync-deps`, `unit-tests`, `coverage-floors`, `lint`,
> `evidence`), `run_id 3fdabce5-b4f1-47b5-ae0a-fddf38769662`, **2529 passed
> in 206.28s**, 0 `StepFailed`, `RunFinished/success`, SHA-256 de
> `.pipeline.kts` = `c05e97f5…` sin drift.
>
> **La CI salió roja dos veces antes, y las dos veces era verdad** — se dejan
> escritas porque un cierre que sólo cuenta la run verde falsea el mismo
> registro que este bloque corrige:
>
> 1. **FAILURE** por etiquetar `v0.16.18` sin registrarla en
>    `release.releases`. Lo cazaron los dos tests de `test_state_release_integrity`,
>    que existen justo para eso. Defecto de **secuencia** mío: cerré el commit de
>    trazabilidad antes de emitir el tag.
> 2. **SUCCESS que no valía**: 9 `StepStarted`, 0 `StepFailed`, 6 etapas — y sin
>    embargo **no cumplía el criterio 2** de AGENTS.md. Medido: `EchoOutputCaptured`
>    conserva sólo los últimos **~1,2 KB** de cada step, y con `pytest -q` la línea
>    `N passed in Xs` cae a media stream y se truncaba. La run era real y **su
>    prueba había quedado fuera del recorte**, que es peor que no tenerla: invita a
>    dar por verificado algo que nadie ha leído.
>
> **Bloque 2026-10-02 (séptima tanda) cerrado — WI-94, release `v0.16.19`.**
> Versión activa `0.16.19.dev0`; último tag `v0.16.19`. 2552 passed.
>
> **WI-94 — el contrato de cobertura que escribí en WI-93 sólo se cumplía donde
> yo miré** (`11294ec`, `569f318`). La pregunta que WI-93 no se hizo: *¿el
> contrato que escribí cubre lo que §6.3 declara?* Medido sobre el informe
> real, la respuesta era no, por dos vías:
>
> - **Siete de los ocho paquetes no tenían ninguna regla.** La regla de «todo
>   módulo de un paquete cubierto tiene suelo» —que WI-93 construyó
>   precisamente para que un módulo nuevo no pasara inadvertido— se aplicaba
>   **sólo a `runtime/`**. Un módulo nuevo al 40 % en `governance/` no lo
>   habría visto nadie. Es el mismo fallo que WI-93 cerraba, sin cerrar en el
>   resto.
> - **`cli/` se medía sólo en agregado**, con **16,91 puntos de holgura**
>   (86,91 % contra un suelo del 70 %). Un módulo de `cli/` podía caer al 0 %
>   y el contrato seguía verde. Y esto lo decía **la propia evidencia de
>   WI-93**: «la cobertura agregada puede tapar un módulo débil». Se aplicó a
>   `runtime/` y se pasó por alto en la otra mitad del contrato.
>
> **El defecto era del guard, no del código**: ninguno de los ocho paquetes
> tenía hoy un módulo por debajo de su suelo. Margen más estrecho,
> `runtime/locks.py` al 90,62 % sobre 90.
>
> **La decisión: heredar, no listar.** El contrato pasa de 21 entradas
> escritas a mano a 8 prefijos (`SUELOS_POR_PAQUETE`) más una excepción
> declarada (`EXCEPCIONES`: `paths.py` al 60 %, que es el suelo que §6.3 le da
> explícitamente; aplicarle el 90 % de `platform/` haría fallar al único módulo
> que el propio contrato exonera). Un módulo nuevo en cualquier paquete
> cubierto queda vigilado al aparecer, y eso ya no depende de que alguien
> recuerde añadirlo a una lista. `evaluar()` pasa a ser **pura**, lo que
> permite probar el contrato con informes sintéticos sin disco ni subprocess.
>
> **Mutaciones 4/4, y el reparto es el hallazgo**: M1 y M2 las caza el script,
> pero **M3 y M4 sólo el test**. M3 reintroduce la asimetría exacta de WI-93 y
> **no produce ningún fallo en el script**, porque el código cumple y luego
> todo verde: el defecto era invisible para el propio guard que lo dejaba
> pasar. *Un guard que vigila el árbol real sólo detecta lo que ya está roto;
> por property propia hay que construir el contraejemplo a mano.*
>
> **El SemVer no lo decide este bloque**: `git log v0.16.18..HEAD` = 0 feat,
> 0 breaking, **2 fix**, 1 refactor, 1 test, 1 chore, 1 docs → **PATCH**. Los
> dos `fix` son de la **cola de WI-93** (`81d07ed` y `430b2b8`), que se
> emitieron **después** del tag `v0.16.18` y quedaban en ninguna release. El
> SemVer hay que derivarlo siempre sobre el último **tag**, no sobre «lo que
> hizo este bloque».
>
> **Bloque 2026-10-02 (octava tanda) cerrado — WI-95, release `v0.16.20`.**
> Versión activa `0.16.20.dev0`; último tag `v0.16.20`. 2559 passed.
>
> **WI-95 — el CHANGELOG decía `[Unreleased]` para bloques ya publicados**
> (`9caeaa2`, `b06c258`). Misma pregunta que abrió WI-93 y WI-94: *¿qué
> contratos declara el repo que nada comprueba?* `STATE.yaml` tiene una red
> que lo ata a `git tag` desde WI-74. **El CHANGELOG no tenía ninguna**, y
> por eso llevaba **dos releases de desfase** sin que nada lo notara.
>
> | Medición | Valor |
> |---|---|
> | tags SemVer en git | 46 |
> | tags **sin sección** | **2** (`v0.16.14`, `v0.16.15`) |
> | cabeceras `[Unreleased]` falsas | **3** (WI-87, WI-88, WI-89) |
> | tests que parseen el CHANGELOG | **0** |
>
> **El fichero se contradecía a sí mismo.** La sección de WI-88 decía, en dos
> líneas consecutivas: «Sin bump todavía» y «la release que lo contiene es
> `v0.16.14`». Ambas eran ciertas al escribirlas —el tag aún no existía— y
> dejaron de serlo al etiquetar, sin que nadie volviera a leer la frase.
> *La contradicción interna es más fácil de detectar que la falsa afirmación
> aislada, y estaba debajo de la vista.*
>
> Corrección de las tres cabeceras a su versión real (`v0.16.15`, `v0.16.14`,
> `v0.16.14 (cont.)`), cada una con su nota `CORREGIDA`. Corregir una etiqueta
> de versión no es reescribir historia: el relato del cambio no se toca, y la
> afirmación corregida es sobre el **presente** (*¿esto salió o no?*).
>
> **El guard tenía un agujero y lo encontró la mutación M3 al primer intento.**
> La aserción sobre `(cont.)` contaba repeticiones, y dos secciones no son
> «más de dos», así que convertir un `(cont.)` en una versión más pasaba
> desapercibido. El invariante correcto no es contar: **sólo la primera
> aparición de una versión puede no ser continuación**. Sin eso la convención
> `(cont.)` es decorativa, porque nada obliga a marcarla. Mutaciones **3/3**,
> aplicadas al **artefacto**: lo que hay que demostrar es que el guard detecta
> cuando el documento vuelve a mentir.
>
> **El desorden antiguo se mide y NO se arregla**: `0.14.1 → 0.7.0 → … →
> 0.3.0 → 0.8.1 → … → 0.14.0`, diez pares fuera de orden. Es cosmético y
> preexistente, y mover 20 secciones de texto histórico es el riesgo que este
> proyecto lleva cuatro bloques evitando. Exigir orden global haría fallar el
> guard en el primer run por secciones de 2026-09, y **un guard que falla por
> ruido se aprende a ignorar**. Lo que sí se vigila es que la zona que se escribe
> hoy siga en orden descendente.
>
> **El SemVer agrupa un fix pendiente**: `git log v0.16.19..HEAD` = 0 feat,
> 0 breaking, **2 fix**, 1 test, 2 docs, 1 chore → PATCH. Los dos `fix` son el
> de este bloque y `cbc8c04`, que WI-94 dejó pendiente **a propósito** para no
> abrir una micro-release. Salieron juntos, y ninguno de los dos es trivial:
> es lo que hace útil la regla de cadencia.
>
> **Bloque 2026-10-02 (novena tanda) cerrado — WI-96, release `v0.17.0`.**
> Versión activa `0.17.0.dev0`; último tag `v0.17.0`. 2567 passed.
>
> **WI-96 — la regla de SemVer estaba en el fichero equivocado y no la
> comprobaba nadie** (`8e147e1`, `08d4a60`, `da86a66`). Tercera vez que se
> hace la pregunta que abre estos bloques: *¿qué declara el repo que nada
> comprueba?* Tras WI-93 (suelos de cobertura) y WI-95 (CHANGELOG contra
> git tag), esta vez el contrato es **la regla que decide el número de
> versión**.
>
> `AGENTS.md §12` se titula «Regla de release» y **no la contenía**. El único
> enunciado estaba en la cabecera del `CHANGELOG.md`, que no es el dueño de
> la gobernanza de releases. Medido sobre las **47 etiquetas** con la regla
> tal como estaba escrita: **9** cuyo SemVer no se deduce de ella, **9** que la
> regla dice que no deberían existir, y **3 con un cambio rompedor real que no
> llegaron a 1.0.0** (`v0.7.0`, que eliminó 20 shims de retro-compatibilidad;
> `v0.15.0`; `v0.16.2`). La exención 0.x que lo explica estaba escrita **en el
> mensaje de esos tres commits y en ningún otro sitio**.
>
> **El giro del bloque: los tres precedentes no llevan el marcador.** Ni `!`
> ni un footer `BREAKING CHANGE:` al principio de una línea — sino una **viñeta
> de prosa**. Con el marcador ninguna herramienta puede verlos; sin él, el
> bump se deduce mal y la exención queda sin justificación visible. El primer
> clasificador buscaba la cadena en el cuerpo y **contaba como breaking el
> propio commit que describía la cláusula**; al exigir la forma de footer, los
> tres desaparecieron del recuento. La conclusión correcta no es «no eran
> breaking», sino **«fueron breaking y no estaban marcados»**. Se reporta
> aparte y **no cuenta** para el bump: ensanchar la convención después de ver
> los datos sería rehacer la regla.
>
> **El número no lo decidió nadie**:
> ```
> == desde v0.16.20 hasta HEAD ==
>   b/f/x/n/d: 0/1/1/2/0
>   la regla pide MINOR -> v0.17.0
> ```
> `test_release_governance` ata la etiqueta a `__version__` —comprueba que el
> número sea coherente consigo mismo—; `derive_semver.py` lo ata **al
> historial**. Durante 47 releases ese cálculo se hizo a mano.
>
> Mutaciones **3/3**, y las dos primeras las encontró el propio guard: M1
> vaciaba la cláusula 0.x **conservando el texto `0.x`**, y el test solo
> buscaba esa cadena; M2 era el patrón que buscaba `->` en un fichero que usa
> `→` y pasaba en verde con la tabla presente. *Un guard que busca una cadena
> comprueba que la cadena exista, no la propiedad.*
>
> **Queda abierto**: las **credenciales de proveedor real** (Anthropic/OpenAI)
> no están en este entorno, así que el criterio de salida de **H9 sigue
> declarado incumplido** — con la mitad local del contrato probada (el
> adaptador *rechaza* bien lo que no debe aceptar) y la mitad remota sin
> probar. Declarar H9 cerrada sin ejecutarla sería el mismo defecto que este
> bloque corrige, en dirección contraria. También abiertos: `ADR-0015` designa
> dos documentos distintos (colisión medida, renombrar es decisión del
> mantenedor); 63 informes fechados en `audits/` (deuda de **datos**); y los
> commits siguen **sin push**, que no está autorizado.

> **Bloque 2026-10-02 (cuarta tanda) cerrado — WI-91, release `v0.16.17`.**
> Versión activa `0.16.17.dev0`; tag `v0.16.17` en `321fa10`. 2493 passed.
>
> **WI-91 — el registro de conformidad H9 afirmaba cuatro cosas falsas** (`04a0476`).
> `goal.h9_addendum_2026_09_25` es el artefacto que decide si el hito H9 del
> blueprint está cumplido, y su `conformance_score` es la cifra que se cita al
> decidir si la iniciativa se cierra. Se escribió el 2026-09-25; el 2026-09-26,
> `v0.14.7` entregó los cuatro entregables que daba por incompletos y el registro
> no se revalidó. **Nada lo comprobaba**.
>
> Medido: E1 «no hay adapter HTTP/LLM/anthropic/openai» → existe
> `HttpAgentAdapter` (`http_adapter.py:330`, Anthropic + OpenAI) y la CLI acepta
> `--adapter=http`. E2 «threat model NO ejecutado» → existe
> `ADR-0015-threat-model-stride.md` con su test. E3 «grieta de no-atomicidad
> abierta, 300-800 LoC» → `create_run_atomically` hace ambas escrituras en una
> sola transacción y está viva vía `RunController`. E4 «no hay runbook» → existe
> `docs/observability-runbook.md`. E5 16/16 UAT → **cierto**. Los 23 tests que
> respaldan E1/E2/E3 estaban verdes mientras el registro afirmaba lo contrario.
>
> **Cada entregable lleva ahora `evidencia_paths` y un guard exige que estado y
> evidencia sean verdad A LA VEZ, en las dos direcciones**: un guard de una sola
> vía deja pasar justo la mitad de los fallos, que es la mitad que se cuela en un
> documento.
>
> **H9 no se declara cerrada.** Los cinco entregables están entregados, pero el
> criterio de salida exige ejecutar contra un proveedor real y eso necesita
> credenciales. Declararla cerrada sería el mismo defecto en la dirección
> contraria: sustituir una afirmación falsa por otra que nadie ha medido.
>
> **Queda abierto**: `ADR-0015` designa dos documentos distintos (colisión medida,
> no ejecutada: renombrar es decisión del mantenedor); 63 informes fechados en
> `audits/` (deuda de **datos**); `governance/receipts.py:473-480` y
> `runtime/agent.py:57-64` replican el patrón de inverso manual (**hipótesis sin
> medir**); y los commits siguen **sin push**, que no está autorizado.

> **Bloque 2026-10-02 (tercera tanda) cerrado — WI-90, release `v0.16.16`.**
> Versión activa `0.16.16.dev0`; tag `v0.16.16` en `8a70667`. 2479 passed.
>
> **WI-90 — `FileSignature` tenía round-trip partido** (`e4fefb0`): sabía
> serializarse (`to_dict`) y **no** deserializarse. El inverso estaba escrito a
> mano dentro de `list_file_signatures_for_source`
> (`knowledge/knowledge_controller.py:329-336`) con subíndices crudos.
>
> Tres fallos medidos. El caro no era de los tres: un campo de más en el payload
> **se perdía en silencio** — sin `KeyError` ni `TypeError` que lo delatara. Los
> tres explotaban sin protección en `governance/improvement.py:208, 268, 324`, que
> es otra capa con otro vocabulario de errores: el fallo cruzaba la frontera de
> bounded context como excepción de Python, no como `SkillGraphError`.
>
> **Con esto queda cerrada la decisión (a) del roadmap**: no queda ningún item
> técnico abierto de (a)–(i). (d) → WI-87 / ADR-0015 · (f) → WI-88 / ADR-0016 ·
> auditoría en `audits/` → WI-89 · `list_file_signatures_for_source` → WI-90.
>
> **Decisión registrada**: `SignatureVigencia.from_dict` **no** comprueba `state`
> contra `EXTRACTION_STATES` porque esa validación ya vive en `__post_init__`.
> Duplicarla recrearía un segundo sitio desincronizable, que es exactamente el
> defecto que cerró WI-87 con ADR-0015.
>
> **Corrección de un incumplimiento propio en este bloque**: el subject del commit
> de código tenía 85 columnas contra las 72 de AGENTS §7. Se corrigió con `commit
> --amend` antes de publicar —el commit no estaba publicado y su árbol es
> byte-idéntico—, no se dejó anotado y sin corregir.
>
> **Queda abierto**: 63 informes fechados acumulados en `audits/` (deuda de
> **datos**, no de código: política de retención, no un defecto);
> `governance/receipts.py:473-480` y `runtime/agent.py:57-64` replican el patrón
> de inverso manual (**hipótesis registrada, no medida** — no se afirma que estén
> mal); y los commits siguen **sin push**, que no está autorizado.

> **Bloque 2026-10-02 (segunda tanda) cerrado — WI-89, release `v0.16.15`.**
> Versión activa `0.16.15.dev0`; tag `v0.16.15` en `6819f99`. 2463 passed.
>
> **WI-89 — la auditoría escribía dentro del repositorio que audita**
> (`64a28a8`): `audit_debt.py` tomaba su destino de `audits/`, relativo al
> cwd, y los tests lo lanzaban desde la raíz. Como `audits/` está
> **trackeado** y el nombre del informe lleva la fecha de ejecución, había
> dos modos de fallo: el informe de hoy cambia si el código se movió, y la
> **primera corrida de cada día crea un fichero nuevo sin trackear** sin
> que nada haya cambiado. Ahora `--src-root` y `--out-dir` parametrizan
> origen y destino. El síntoma era visible en cada commit: el hook dejaba
> `M audits/architecture-debt-<hoy>.md`.
>
> **Con esto queda cerrado el último seguimiento técnico de los items
> (a)–(i)**: (d) propiedad de dominio → WI-87 / ADR-0015; (f) exit code de
> argparse → WI-88 / ADR-0016; auditoría que escribía en `audits/` → WI-89.
>
> **Corrección de una medición propia, en el bloque que la cerró**: el
> seguimiento de WI-87 decía, con md5, que «9 tests verdes cambian el
> fichero». Re-medido en un árbol limpio **no se reproduce**: el informe
> commiteado estaba al día. La premisa era condicional y la redacción la
> presentó como incondicional.
>
> **Queda abierto**: 63 informes fechados acumulados en `audits/` (deuda de
> **datos**, no de código: es una política de retención, no un defecto);
> `list_file_signatures_for_source`, medido que no está muerto —4 consumidores
> reales— pero cuyo `cc 10` sigue sin medirse; y los commits siguen **sin
> push**, que no está autorizado.

> **Bloque 2026-10-02 cerrado — WI-87 y WI-88, release `v0.16.14`.**
> Versión activa `0.16.14.dev0`; tag `v0.16.14` en `3cfce09`. 2451 passed.
> Dos decisiones del operador cerradas, ambas con ADR y ambas medidas antes
> de tocar nada.
>
> **WI-88 — los errores de uso devuelven `EXIT_USAGE` y el 2 queda libre**
> (`1a0c38b`, ADR-0016): `argparse` abortaba con **2**, y 2 ya era
> `EXIT_BAD_NAME`, que `runner.py:131` devuelve vivo. Tres fallos sin
> relación —nombre de proyecto inválido, comando inexistente, subcomando
> sin argumentos— devolvían el mismo número, y `EXIT_USAGE` (1), que el
> propio contrato declaraba, **no se producía nunca**. La taxonomía de
> errores era inservible para scripting. `parser.py` usa ahora
> `_UsageParser`; la tabla de códigos se mueve a `cli/exit_codes.py`, un
> módulo hoja, porque `support.py` arrastra `Storage` y `pack_loader` y el
> parser es autocontenido por diseño. 8 tests cambian de 2 a 1 a propósito,
> 2 se quedan — uno de ellos pasa a ser el guardián del 2.
>
> **WI-87 — el vocabulario de estados se deriva de su ADT** (`d47b7af`,
> ADR-0015): `core/runtime_types.py` **ya tenía** `TERMINAL_RUN_STATES`, y
> `storage.py` reimplementaba su complemento a mano, sin relación
> verificada. Añadir un estado a `RunState` sin tocar el segundo fichero lo
> hacía terminal, y UAT-06 (reanudar tras crash) creaba un **segundo run**
> para el mismo trabajo, en silencio. El `CHECK` de SQLite se genera ahora
> desde `PROMOTION_STATUSES`, de modo que la base de datos y el validador no
> pueden divergir.
>
> **Dos formas de cerrar un defecto por error, ambas Cometidas en este
> bloque.** La primera medición de (f) dio exit 1 en los tres casos y
> habría permitido declarar la premisa caducada: se había medido
> `/usr/bin/sg` (la herramienta Unix de grupos) en vez del console script
> `skillgraph`. Y la primera lista de tests afectados decía «medidos uno a
> uno, no contados» y contaba 6 sobre un `grep | head -20` leído como
> lista completa: eran 10.
>
> **Sigue abierto**: `audits/architecture-debt-*.md` sigue ensuciando
> `git status` en cada corrida de la suite (medido con md5: 9 tests verdes
> cambian el fichero); `list_file_signatures_for_source` no está muerto —
> 4 consumidores reales — pero su `cc 10` sigue sin medirse; y los commits
> siguen **sin push**, que no está autorizado.

> **WI-80 cerrado — un rechazo ilegible ya no se presenta como `PROPOSED`
> sin avisar** (2026-10-02, commit `eb19942`): cierra el punto (h) de
> `next_workitem`, que **dos bloques dieron por cerrado sin ejecutar**.
> `_collect_rejection_ids` se saltaba con `continue` un
> `expansion_rejections/*.json` ilegible; el `proposal_id` se perdía,
> `_infer_proposal_stage` caía a `PROPOSED`, y `expansion list` imprimía
> `stage=PROPOSED` con **exit 0 y sin aviso** para una propuesta que sí
> fue rechazada. Consecuencia medida: `--stage REJECTED` la hacía
> desaparecer. No era un falso éxito de escritura —`cmd_expansion_apply`
> no consulta el registro de rechazos, `apply` es idempotente por
> re-validación—; el alcance era de **visualización**. **El fix no
> adivina**: `record_rejection` escribe siempre `<proposal_id>.json`
> (`graph_expansion.py:618`), luego el stem **es** el `proposal_id` por
> construcción. Además se reporta en `RejectionScan.unreadable` y
> `list`/`show` avisan en stderr: sin el aviso, la corrección habría
> sustituido una mentira silenciosa por otra más pequeña. Listing sigue
> con exit 0 y el fichero roto **no se borra**. Red 6→8: los 4 tests que
> consignaban el defecto **se invierten, no se borran**, y se añaden 2
> que cierran el contrato por los dos lados —evidencia sana **no**
> avisa, porque el ruido es lo que hace que nadie lea los avisos—. 3/3
> mutaciones. 2416 passed. **Una lección**: «no tocar el contrato
> externo» es un criterio correcto en general y aquí estaba mal
> aplicado, porque confundía **cambiar un contrato** con **corregir una
> afirmación falsa**: el contrato de `--stage REJECTED` nunca fue «oculta
> las rechazadas cuyo fichero está roto». Evidencia:
> `evidence/sddk-wi80-verify-2026-10-02.md`.
> **WI-86 cerrado — los 5 consumidores de mappers dejan de pasar por el
> facade `Storage`** (2026-10-02, commit `cf6539b`): el punto (a) de
> `next_workitem`, abierto dos bloques con «requiere ADR NUEVO», resuelto
> por medición. Los 7 símbolos que `storage.py` importaba y reexportaba
> (`MAPPER_NAMES`, `_row_to_*` ×5, `_uid`) aparecían **exactamente dos
> veces** cada uno —el import y `__all__`— y **cero** en código dentro
> de `storage.py`: la capa entera existía para servir a hermanos. Y eran
> **cinco** hermanos, no los dos que nombraba el comentario del propio
> bloque. `row_mappers` es una **hoja** (importa `sqlite3`, `typing` y
> `ports`; no depende de nada que dependa de él), así que el rodeo no
> evitaba ningún ciclo — medido en runtime, `storage` no importa
> `run_repository` ni `promotion_repository` a nivel de módulo. Los 5
> importan ahora de la hoja y `storage` retira el bloque y las 7
> entradas de `__all__`. Cero cambios de comportamiento: la red lo
> comprueba por **identidad**, no por el nombre del símbolo. **No** se
> tocan `PROMOTION_STATUSES` ni `NON_TERMINAL_RUN_STATES`: están
> *definidos* en `storage.py`, no son re-exports, y que los consuman los
> componentes es una pregunta de propiedad de dominio que sí merece ADR.
> Es el mismo fallo que WI-81 una generación más abajo: anunciar en
> `__all__` una superficie que no se sostiene. 4/4 mutaciones cazadas;
> la cuarta (un consumidor enlaza el mapper equivocado) **no** la caza la
> red estructural y no debe: esa red fija la *forma*, no *qué* mapper
> corresponde a cada consumidor. Su oráculo son los tests
> comportamentales, y cazan 17. **Dos errores propios**, ambos antes de
> tocar `src/`: una aserción vacía que no podía fallar nunca (buscaba en
> `storage` un import de `storage`), y una comprobación del script de
> mutaciones que relajaba `is` a `==` esperando demostrar que el `is`
> protegía — **falla, porque para funciones `==` e `is` son la misma
> operación**; se retira en vez de dejar una que afirmara algo falso.
> 2414 passed.
> **Corrección de registro — «WI-65-fase-1» era falso** (2026-10-02):
> el bloque anterior anotó como siguiente trabajo la fase 1 de WI-65 sin
> verificar su premisa. Medido contra el árbol: `platform/storage.py`
> son **613 LoC con 15 métodos**, no 1807/80, y los 5 mixins existen y
> son live con 31/19/7/4/4 = 65 métodos. **WI-65 ya lo entregó ADR-0022**
> y WI-68 lo remató. El informe de exploración del ciclo se commiteó
> (`c471264`, 10:10) **81 minutos antes** de la release que lo implementó
> (`v0.16.10`, `2ee6d77`, 11:31): el informe *acertaba en todo lo que
> predecía*, estaba simplemente vencido. El ciclo
> `wi65-storage-facade-decomposition` se cerró con `goal-replaced`: su
> objetivo **fue entregado**, por otro bloque. El proyecto queda con
> **27 ciclos CLOSED y 0 abiertos**. *Lección*: un informe de
> exploración puede ser excelente y aun así estar vencido; la calidad del
> análisis no dice nada sobre si su premisa sigue en pie.
> Evidencia: `evidence/sddk-wi86-verify-2026-10-02.md`.
> **Estado post-release**: `__version__ = 0.16.13.dev0`, etiqueta `v0.16.13` en `6e97513`
> (bloque WI-86 + WI-80: la capa de re-export de `platform.storage` y el
> rechazo ilegible presentado como `PROPOSED`).
> El tag se crea sobre el commit que lleva el SemVer puro, que es lo que
> exige `tests/test_release_governance.py::test_version_matches_git_tag`:
> HEAD en etiqueta ⟺ `__version__` sin sufijo `.devN`; HEAD posterior a
> la etiqueta ⟺ `.devN`. El bloque esta publicado **en local y sin
> push**. La siguiente release se decide con el operador.
> **WI-84 cerrado — el estado SDDK decía una cosa y el ledger otra**
> (2026-10-02, ciclo transversal): `STATE.yaml.next_workitem` afirmaba
> «6 ciclos en `RELEASE_PENDING`». Medido contra
> `projects/p-b7740b96d79ec013/ledger.sqlite`, son **10** (`wi-72`..
> `wi-81`). El texto estaba caducado por dos razones a la vez: `wi-81`
> se creó después de escribirlo, y `wi-72/73/74` nunca se contaron.
> **Por qué no se podían cerrar: `release.complete` es
> estructuralmente inalcanzable aquí**, y no por un gate pendiente.
> Exige `release-receipt`, que solo emite `sddk release apply`, y ese
> comando falla con `VERSION LOCKSTEP ERROR: could not read
> …/Cargo.toml` — el plano de release de SDDK deriva la versión de un
> `Cargo.toml`. SkillGraph es un paquete Python. Los **gates** sí se
> pueden pasar, y se pasaron (`release-uat-approved` y
> `no-pending-effects` con evidencia real: exigen `argv`, `exit_code` y
> `output_digest`). Lo que falta no es un gate: es el paso de release.
> Los 10 cerrados por `cycle supersede`, con la evidencia como
> `--evidence-refs`. El enum ofrece tres razones y **ninguna describe el
> caso real**; se eligió la más cercana y la evidencia deja constancia
> de que la clasificación es aproximada — la razón es una etiqueta, el
> fichero es el registro.
> **Decisión asimétrica sobre los 2 ciclos `OPEN`**, que es el punto de
> este bloque: `wi-65-subprocess-coverage-file` se cerró
> (`goal-replaced`) porque es una cáscara de 1 evento y 0 artefactos, y
> WI-75 ya entregó su asunto (`scripts/coverage.sh`); **la premisa es
> una inferencia por nombre, y así queda anotada**.
> `wi65-storage-facade-decomposition` **no se cerró, a propósito**:
> contiene un informe de exploración real, medido y no ejecutado —759
> de 1807 LoC de `storage.py` son delegación pura, agrupable en 5 mixins
> disyuntos con cero ediciones en callers—. Cerrarlo sería tirar trabajo
> válido para dejar el tablero limpio. **Es el siguiente bloque.**
> Conocimiento negativo del plano de release: `sddk release apply
> --route local` **pushea** trunk y tag, fuera de lo pre-aprobado.
> Evidencia: `evidence/sddk-wi84-sddk-state-resolution-2026-10-02.md`.
> **WI-83 cerrado — `scripts/audit_bundle.sh` podía emitir un bundle no
> certificable pareciendo certificado** (2026-10-02, commit `2bd64da`):
> dos fallos encadenados. Ejecutaba el audit UAT como
> `uv run python tests/uat_audit.py`, forma en la que `sys.path[0]` es
> `tests/` y el `from tests._evidence_lock import` de nivel de módulo
> falla con `ModuleNotFoundError` (exit 1); la forma correcta es
> `python -m tests.uat_audit` (exit 0, `PASS=16 FAIL=0 BLOCKED=0`).
> Y el comando estaba en un pipe a `tee`, que se come el exit code: el
> script seguía, empaquetaba y salía con **0**, con un
> `uat-audit-cleanroom.txt` que contenía un traceback. La herramienta
> cuya razón de ser es producir evidencia reproducible para una
> auditoría externa podía producir un bundle sin certificar con
> apariencia de certificado. Se captura `PIPESTATUS[0]` y se aborta con
> el código real.
> **WI-82 cerrado — la suite ensuciaba `git status` en cada ejecución**
> (2026-10-02, ciclo SDDK `wi-82-evidence-write-idempotence`, commit
> `6db1000`): el diagnóstico registrado antes («evidencia UAT
> autorreferencial») era cierto y **no era el defecto** — es una
> propiedad del dato, no un bug. El defecto era otro:
> `save_with_lock` (`tests/_evidence_lock.py`) escribe
> incondicionalmente, así que la suite reescribía dos ficheros
> versionados aunque su contenido fuera semánticamente idéntico. El
> único campo que cambiaba era `revision` (`git rev-parse HEAD`), y
> **no puede converger por construcción**: un fichero versionado nunca
> puede contener el SHA del commit que lo versiona. `revision` resultó
> ser un sello informativo: **ningún test comprueba `revision == HEAD`**,
> y `tests/test_uat_audit.py:143` afirma lo contrario de lo que hacía el
> producto (`assert survived["revision"] == "must-survive"`). Fix:
> `save_with_lock` acepta `volatile_keys` y no reescribe si el fichero
> ya coincide en todas las demás claves; comparación sobre el JSON
> parseado (el orden de un dict no es información, el de una lista sí) y
> *fail-open* explícito si el fichero previo no se puede leer.
> `history_keep=True` intacto: ahí el registro de cada corrida **es** el
> propósito. **Verificado sobre la suite completa, no solo sobre el
> fichero afectado**: 2388 passed (2376 antes) y `git status --porcelain`
> **vacío**. 12 tests nuevos con las dos contrapartes (si el contenido
> cambia de verdad se escribe; si no cambia ni la mtime se toca) y 3/3
> mutaciones cazadas, incluida la de una guarda presente pero decorativa.
> Un error propio en el rojo, corregido antes de tocar `src/`: el test
> e2e con fixtures sintéticos pasaba **por el motivo equivocado**, y el
> caso «cambió de verdad» no comprobaba nada para UAT-08 (su payload usa
> `apply.stderr`, no `returncode`). Evidencia:
> `evidence/sddk-wi82-verify-2026-10-02.md`.
> **WI-81 cerrado — segunda tanda de ADR-0014: 7 alias de función sin
> callers** (2026-10-02, ciclo SDDK
> `wi-81-drop-dead-row-mapper-shims`): antes de aceptar deuda técnica
> como deuda, se verificó cada alerta, y **ninguna de las registradas lo
> era**. `sddk debt incs` devuelve 50 INCs que no son de este proyecto
> (el vault `p-b7740b96d79ec013` tiene **0 entradas**; están en
> `sddk-framework/` y en `p-733fb505b5a6bd2d`, y uno leído es
> `domain: kernel, status: closed`, sobre `Cargo.toml`). El backlog #1
> del shim de `pipelinek` tiene premisa caduca: dice 0.43.0, hoy es
> 0.46.0 y `mise.toml` **ya fija** 0.39.0 con bake-off documentado. Y
> `sddk lint` falla con 4 errores que son **opt-ins no adoptados**:
> `schemas/`, `docs/generated/` y `manifest.toml` nunca existieron en el
> historial de git. Lo único que sí era deuda real: los 7 alias de
> WI-56 (corte 3) en `platform/row_mappers.py`, cuyos docstrings decían
> «el corte 5 reubicará los callers» — el corte 5 ocurrió, los callers
> se fueron a `knowledge_mappers` y los alias se quedaron, dejando
> `MAPPER_NAMES` anunciando 12 mappers donde había 5. **Inercia medida
> en runtime, no por lectura**: `knowledge_repository._row_to_X is
> row_mappers._row_to_X` → `False` en los 7, porque ese símbolo es un
> alias *local* suyo (`knowledge_repository.py:696-702`). Un barrido
> textual habría dicho «los llama `knowledge_repository`» y es un falso
> positivo. Test rojo primero (23 tests, 13 failed / 10 passed de
> caracterización), fix mínimo, 2 mutaciones cazadas incluida la
> reintroducción de un caller real. `test_wi76_shim_execution.py`
> borrado: premisa resuelta, objeto desaparecido (AGENTS §6.2). Addendum
> en ADR-0014. **Una lección**: la primera versión del script de
> mutaciones revertía con `git checkout --`, que restaura HEAD y
> destruyó el fix sin commitear; el control del final lo detectó. Sin
> ese control se habría commiteado un árbol inconsistente. Evidencia:
> `evidence/sddk-wi81-verify-2026-10-02.md`.
> **WI-80 cerrado — un rechazo ilegible se presenta como `PROPOSED`,
> sin avisar** (2026-10-02, ciclo SDDK
> `wi-80-silent-handler-audit`): la señal que WI-76..WI-79 no habían
> barrido — *fallbacks silenciosos*. Barrido mecánico de los 66 handlers
> de excepción de `src/`: **59 con cuerpo efectivo, cero `pass`, cero
> handlers vacíos** (el antipatrón AGENTS §11.14.4 no está presente en
> esa forma) y 7 con cuerpo únicamente `continue`, todos de tolerancia a
> dato corrupto y documentados. Los 4 `except Exception` anchos están
> justificados en el código; los 3 `except BaseException` relanzan con
> `raise`, que es lo correcto (estrechar a `Exception` dejaría el
> `BEGIN` abierto ante un `ValidationError` o un `Ctrl-C`).
> **Hipótesis refutada sin tocar código**: `_load_registry` se salta un
> resource con `spec_json` ilegible, pero el registry es un *allowlist
> de existencia* (I3/I4 preguntan «la capability EXISTE»), no un detector
> de colisiones, así que un registro incompleto hace **fallar** la
> comprobación con I3 en vez de pasarla: *fail-closed* correcto.
> **Hallazgo real**: `_collect_rejection_ids` (`expansion.py:86`) se
> salta un `expansion_rejections/*.json` ilegible; el `proposal_id` no se
> registra y `_infer_proposal_stage` cae a `PROPOSED`, sin aviso. Es el
> patrón que `git_source.py:365` ya decidió corregir («un dato plausible
> y falso es peor que un error»). Consecuencia **medida**: `expansion
> list` imprime `stage=PROPOSED` con exit 0 para una propuesta
> rechazada, y `--stage REJECTED` la hace desaparecer. **No** es un
> falso éxito de escritura: `cmd_expansion_apply` no consulta el
> registro de rechazos — `apply` es idempotente por re-validación.
> Añadido `tests/test_wi80_expansion_rejection_visibility.py` (6 tests,
> **sin tocar `src/`**) con 2 mutaciones cazadas, incluida la
> *corrección candidata* (fallback por nombre de fichero), que pone la
> red en rojo: arreglarlo exige tocar el test a propósito. **No se
> corrige** — cambiar la salida de `expansion list` es contrato externo
> (AGENTS §6.4) con un consumidor (`--stage REJECTED`), y hay dos salidas
> no equivalentes. 2362 → **2368 passed**. Evidencia:
> `evidence/sddk-wi80-verify-2026-10-02.md`.
> **WI-79 cerrado — el contrato de exit code de la CLI no lo fijaba
> ningún test** (2026-10-02, ciclo SDDK `wi-79-cli-exit-contract`):
> `main()` termina en `sys.exit(main())`, así que un handler de
> `_DISPATCH` que devolviera `None` produciría **exit 0** sin traceback
> ni stderr — el falso éxito más silencioso posible, y sin un solo test
> que lo mirara. `test_wi57_dispatch_coverage.py` fija la *completitud*
> de la tabla, no la *forma* del retorno: son invariantes distintas.
> **Hipótesis REFUTADA con instrumento validado por mutación en ambas
> direcciones**: 31 handlers, 31 anotados `-> int`, **0** que devuelvan
> `None`, 0 con cuerpo que caiga por el final. La garantía se instala
> como guardarraíl, no como corrección. Añadido
> `tests/test_wi79_dispatch_exit_contract.py` (102 tests, **sin tocar
> `src/`**) con **6 mutaciones cazadas**, cada una por su test.
> **Hallazgo real dentro de esa refutación**: la rama
> `except FileNotFoundError` de `main` (`runner.py:250-254`) no la
> ejercitaba nadie — con su `return EXIT_PROJECT_NOT_FOUND` cambiado por
> `return EXIT_OK`, los **2260 tests de la suite completa se quedaban
> verdes** (medido, no supuesto). El oráculo conductual no la alcanzaba
> porque `runs budget` resuelve el proyecto antes y devuelve su código.
> Corregido con un test que sustituye `_resolve_handler` (la tabla es
> `MappingProxyType`, inmutable). 2260 → **2362 passed**.
> Nota de instrumento: el escáner AST falló **dos veces** antes de decir
> nada cierto — filtro por anotación dio 3 falsos positivos de stubs de
> `Protocol`; el extractor de `_DISPATCH` buscaba `Assign`/`Dict` cuando
> es `AnnAssign`/`MappingProxyType({...})` y devolvió 0 handlers, que
> parecía "nada sospechoso"; y era **ciego a `return None` explícito**,
> que en AST es `Return(value=Constant(None))`, un return *con*
> expresión. La v3 lleva guarda que aborta si la tabla no se extrae.
> Hallazgo lateral **sin corregir**: `argparse` sale con **2** mientras
> el `EXIT_USAGE` canónico es **1** (`support.py:47`); un operador que
> clasifique por `EXIT_USAGE` no ve los errores de invocación. Decisión
> de producto, fijada con un test que falla si `argparse` cambia.
> Evidencia: `evidence/sddk-wi79-verify-2026-10-02.md`.
> **WI-78 cerrado — serialización legacy de 4 DTO sin test** (2026-10-02,
> ciclo SDDK `wi-78-dto-serialization`): `platform/ports/dto.py` al 89 %;
> los misses reales eran `to_dict()` enteros en 4 de 9 DTO y las ramas
> `KeyError`/`get(key, default)`. Hay roundtrip para 5 DTO y ninguno para
> `StoredClaim`, `StoredEvidence`, `StoredPromotion`, `StoredBudget`.
> Ningún código de producción llama a esos `to_dict()`: es superficie de
> compatibilidad, no falso éxito. **Contradicción reportada, no
> corregida**: el docstring de `StoredBudget.to_dict` promete "preservando
> todas las columnas" y devuelve 3 de 6 (omite `tenant_id`, `project_id`,
> `run_id`); el test fija el comportamiento real. Añadido
> `tests/test_wi78_dto_serialization.py` (13 tests). 2247 → **2260 passed**.
> Evidencia: `evidence/sddk-wi78-verify-2026-10-02.md`.
> **WI-76 cerrado — falso éxito en los shims de compatibilidad**
> (2026-10-02, ciclo SDDK `wi-76-shim-false-success`): siete funciones de
> `platform/row_mappers.py` (`_row_to_source`, `_row_to_evidence`,
> `_row_to_stored_evidence`, `_row_to_claim`, `_row_to_stored_claim`,
> `_row_to_resource`, `_row_to_relation`) están en `storage.__all__` y en
> `MAPPER_NAMES`, y dos clases de test garantizaban que seguían vivas
> **sin ejecutarlas nunca**: `test_wi60` hace `inspect.getsource()` y
> comprueba el texto; `test_wi65` trabaja por AST sobre `ast.Call`.
> Probado invirtiendo los argumentos del `return` —que reventaría con
> `TypeError` si alguien los llamara—: **37 passed** en los tests que los
> preservan y **2225 passed** en la suite completa. Causa raíz: WI-56
> anunció que "el corte 5 reubicará los callers", ese corte sí ocurrió
> (los callers ya resuelven al mapper real), pero los alias no se
> borraron y `MAPPER_NAMES` siguió listándolos. Corregido con
> `tests/test_wi76_shim_execution.py` (14 tests, oráculo diferencial
> shim vs mapper real, **sin tocar `src/`**): la misma mutación da 10
> failed. 2225 → **2239 passed**. Borrar los shims queda como decisión del
> operador: es cambio de contrato (`storage.__all__`) y AGENTS §10 pide
> ADR. Evidencia: `evidence/sddk-wi76-verify-2026-10-02.md`.
> **Auditoría de extensión de WI-76: resultado NEGATIVO.** Se auditó si el
> patrón se repetía: 40 tests en 29 ficheros combinan `getsource`/AST con un
> `assert`. ~37 son contratos estructurales legítimos (sin SQL aquí, bajo 800
> LoC) que no se pueden verificar por comportamiento. Los 2 que afirmaban
> runtime (`_fail_node_with`, `_open_known_project`) son **falso positivo**:
> sus contratos sí están verificados conductualmente en otros tests. **El
> patrón no es sistémico y la hipótesis se retira.** Solo se corrigió el
> residuo: el guard de `_fail_node_with` ahora invoca la función (antes solo
> leía que la última línea fuese `return False`, con lo que un `return None`
> temprano pasaba) y su docstring deja de prometer que los callers usen el
> retorno — ninguno lo hace. Detalle en la evidencia §7.
> **WI-75 cerrado — la cobertura del CLI deja de estar ciega** (2026-10-02,
> ciclo SDDK `wi-75-subprocess-coverage-instrument`): `pytest --cov` mide solo
> el proceso principal, y la suite ejercita la frontera CLI por **subproceso**.
> El CLI marcaba **65,86 %** contra el contrato de AGENTS §6.3 (≥70 %) — un
> incumplimiento aparente que era **ceguera del instrumento, no deuda de
> tests**. Con `bash scripts/coverage.sh` el TOTAL sube a **94 %** y todos los
> módulos CLI superan el 70 % (parser 100, knowledge 95, run 96, runs 86,
> promotion 85, support 85, expansion 82, pack 78, runner 77). Efecto
> secundario: `cmd_expansion_apply`, la función que **WI-72 partió**, sale con
> cobertura real en vez de 0 %. Receta (4 ingredientes): hook `.pth` que llama
> a `coverage.process_startup()` **auto-instalado** (estaba colado a mano en
> el venv y sin declarar en `pyproject.toml`/`uv.lock`), `parallel = true`,
> `data_file` **absoluto** (los tests usan `cwd=tmp_path` y pytest borra su
> tmp), y pytest-cov para el principal + el hook para los subprocesos
> **compartiendo `data_file`**. `.pipeline.kts` **no** se toca: la
> instrumentación multiplica el tiempo de suite, y la CI canónica sigue
> corriendo pytest sin coverage. Evidencia:
> `evidence/sddk-wi75-verify-2026-10-02.md`.
> **WI-73 cerrado — P3 5 → 4** (2026-10-02, ciclo SDDK
> `wi-73-p3-aggregate-file-signatures`): `aggregate_file_signatures` 86 →
> **72 LoC** y cc 8 → **3**. El corte no fue "partir una función larga"
> sino **darle nombre a un invariante que no lo tenía**: el bucle de 18
> líneas mezclaba comprobar pertenencia al scope y clasificar el fallo,
> y UAT-EVO-08 ("un proyecto no ve las firmas de otro") solo existía en
> el docstring de la clase y en el nombre de un test. Ahora es
> `_sources_in_scope`, con sus tres casos documentados —incluido el
> tercero, el que no se ve: un source inexistente se **omite** en
> silencio, y esa distinción respecto al rechazo es deliberada—.
> De paso, el `for` que solo acumulaba en un dict pasa a comprehension
> (AGENTS §11.8).
> **Punto ciego del audit, medido y reportado sin actuar**: su vecino
> `list_file_signatures_for_source` tiene **cc 10**, la mayor del módulo,
> con 58 LoC. Cae entre los dos umbrales del audit (80 LoC y cc 20) y
> **ninguno lo captura**. No se corta aquí: abrir un frente nuevo a
> mitad de otro es inventar deuda. Queda con su medición para que la
> decisión sea del operador.
> **Un CRUDO contra AGENTS §1.2 que NO se toca**: el `raise TypeError`
> del guard de tipo parece una violación, pero `file_handoff.
> _validate_inputs` tiene **cuatro** iguales. La convención de la casa es
> `TypeError` para tipos y `ValidationError` para valores; cambiar una
> instancia dejando cuatro hermanas crearía inconsistencia, no la quitaría.
> Verificación: **2215 passed** (2197 + 18), ruff y format limpios, los
> tests de knowledge (H12/H13/H9) pasan sin modificarlos, y la red se
> verificó en ambos sentidos con tres mutaciones. La importante es la
> primera: **filtrar en silencio el cruce de proyecto** en vez de
> rechazarlo — que es la fuga que UAT-EVO-08 prohíbe. La cazan tres
> tests nuestros y también la red preexistente.
> **WI-72 cerrado — P3 6 → 5** (2026-10-02, ciclo SDDK
> `wi-72-p3-expansion-apply`, el primero con ciclo propio desde WI-65):
> `cmd_expansion_apply` 92 → **73 LoC**, cc 7 → 6, y por debajo del
> umbral P3. El hallazgo no era la complejidad sino una **duplicación**:
> el payload JSON de 9 claves de una propuesta se construía DOS veces, en
> `cmd_expansion_propose` y en `cmd_expansion_apply`, con tres
> divergencias. Es un contrato en disco con lectores externos (`list`,
> `show`, `_scan_proposals_dir`, `_infer_proposal_stage`) y con tests que
> construyen el fichero a mano, así que la duplicación era un riesgo
> silencioso. Ahora hay un constructor (`_proposal_payload`) y un escritor
> (`_write_json`) con el parámetro `overwrite` que hace explícita la única
> divergencia intencional: `apply` conserva el registro original,
> `propose` lo refresca. De paso desaparece el `plan` que se enlazaba dos
> veces con dos significados.
> Se eligió por medición AST: `aggregate_file_signatures` tiene cc 8 (una
> más) pero partiría 18 líneas y tocaría la invariante de aislamiento
> UAT-EVO-08; esta ofrecía eliminar una duplicación real con el mismo
> riesgo.
> **Me equivoqué en la exploración y lo corrijo**: di por hecho que la
> divergencia de `encoding` entre los dos escritores era un bug de locale
> en `propose`. Al implementarlo se ve que es **inerte**: `json.dumps` usa
> `ensure_ascii=True` por defecto, su salida es ASCII puro y el `encoding`
> de `write_text` no toca un solo byte. Unificarlo se mantiene por
> higiene del formato, no porque arregle nada. Los tres artefactos del
> ciclo quedaron corregidos, y el test que lo demuestra lleva el nombre
> del hallazgo.
> Verificación: **2197 passed** (2181 + 16), ruff y format limpios, los
> 50 tests de expansion existentes pasan sin tocarlos, y la red se
> verificó en ambos sentidos con cuatro mutaciones (quitar una clave,
> `overwrite=True` en apply, reintroducir el literal, y cambiar **solo un
> valor**) — las cuatro la cazan.
> **Estado post-release**: `__version__ = 0.16.10.dev0`, etiqueta
> `v0.16.10` en `2ee6d77`. El bloque WI-65..WI-71 mas el commit de
> release salen a `origin/main` en el push autorizado por el operador;
> la confirmacion se anota en `STATE.yaml` (`release.push`) y en
> `SESSION-JOURNAL.md` cuando el push termine. El numero `0.16.10` es
> PATCH, derivado de la regla del CHANGELOG aplicada al historial (0
> `feat`, 6 `fix`), no de un criterio propio.
> **RELEASE v0.16.10** (2026-10-02): publica el bloque **WI-65..WI-71**
> (57 commits) que estaba sin subir desde `e680b72`. Numero derivado del
> historial segun la regla del CHANGELOG, no por criterio propio: el
> bloque tiene **0 `feat` y 6 `fix`**, y la regla dice `fix` -> PATCH y
> `refactor`/`test`/`docs`/`chore` -> sin bump. Un MINOR se descarto
> pese a haberlo propuesto, porque el bloque no anade ninguna
> capacidad observable y la API publica se conserva identica
> (verificada por identidad de objeto, no por inspeccion). Contenido:
> cierre de H-01 (god modules 3 -> 0), siete redes de contrato nuevas
> (2154 -> 2181 tests) y seis correcciones reales, tres de ellas de
> gobernanza de CI (el SUCCESS cacheado que enmascaraba runs, la
> ambiguedad de PATH entre asdf y mise, y el hook pre-commit que se
> comia el exit de pytest). Nudo documentado: el admission gate exige
> que `__version__` puro coincida con una etiqueta en HEAD, asi que el
> commit de release no puede pasar el gate **antes** de que exista la
> etiqueta. Se commitea con `HOOK_SKIP_TESTS=1` (ruff sigue
> corriendo) y la suite completa se ejecuta despues de crear el tag,
> que es la condicion en la que el gate realmente debe pasar.
> **WI-71 cerrado — P3 7 → 6** (2026-10-02): `analyze_skill`
> (importacion de skills, UAT-11) 101 → **30 LoC** y cc 11 → **1**.
> Elegida por medicion, no por LoC: de las candidatas P3 era la de mayor
> cc real (11), con un bucle que llevaba dentro tres ramas `continue`
> (script / binario / desconocido) y sus motivos de ambiguedad. El
> corte mueve el detalle verbatim a `_classify_file` (51 LoC, cc 6) y
> la resolucion de la raiz a `_resolve_source` (25, cc 3); `analyze_skill`
> queda como un plegado `reduce` de una sola pasada sobre `_merge`, con
> tres records frozen con `slots` (`_ImportSource`, `_FileVerdict`,
> `_ScanResult`). God modules sigue en 0 y el cc maximo del repo en 10.
> La red (27 tests) incluye un **oraculo diferencial** que reimplementa
> en el test el algoritmo original de una sola pasada y compara el
> informe campo a campo: es lo que demuestra que el plegado no pierde
> ni reordena nada. Verificado en los dos sentidos con tres mutaciones
> (reintroducir el detalle, `_merge` que muta, perder la rama de
> markdown): las tres las caza la red. Dos rarezas preexistentes que
> ningun test cubria quedan fijadas, no corregidas: importar un fichero
> suelto lo nombra `"."` (porque `relative_to(f)` sobre si mismo es
> `"."`), y el mensaje de ruta inexistente usa la raiz ya resuelta.
> Cambiar la primera altera el payload que consumen UAT e informe: es
> decision de producto, no efecto del refactor. Verificacion: **2181
> passed** (2154 + 27), ruff y format limpios.
> Nota de metodo: la eleccion de candidata la hizo la medicion AST, no el
> tamano. `compile_handoff` (90, cc 3) y `compile_handoff_from_scopes`
> (85, cc 1) son mas largos pero son lineales: partirlas seria ceremonia,
> no legibilidad. Siguen fuera del frente.
> **GOD MODULES: 0** (2026-10-02, commits `405f49e` y `c29a848`):
> el audit de deuda arquitectonica ya no reporta ningun fichero >800
> LoC. El recorrido completo: `storage.py` 1807 → 623 (WI-65, H-01
> cerrado), `runcontroller.py` 1421 → 665 (WI-66/67),
> `storage_delegations.py` 915 → índice de 29 LoC con cinco módulos
> por componente (WI-68) y `ports/__init__.py` 927 → `dto.py` (448) +
> `repositories.py` (442) + índice de 55 (WI-69). Verificación:
> **2132 passed** (1880 originales + 252 nuevos), ruff y format
> limpios, CI canónica con 8 StepStarted/EchoOutputCaptured y 0
> StepFailed. Quedan 8 funciones >80 LoC (P3); el mayor es
> `build_parser` (409), un orquestador declarativo con cc baja.
> Nota de método: los dos últimos ficheros no tenían problema de
> concentración (la clase mayor de `ports` era 179 LoC, la de
> `storage_delegations` 366): estallaban por **anchura**, y el corte
> los resolvió separando familias, no partiendo clases.
> **WI-67 cerrado — god modules 3 → 2** (2026-10-02, commit `57121ed`,
> ADR-0024, completa ADR-0019 fase 2): `runcontroller.py` 1421 → **665
> LoC** con 14 métodos. La medición AST no dio un bloque sino seis
> clusters disjuntos; se movieron los tres más cohesivos a un mixin
> cada uno, en **módulos separados** (un único módulo habría salido en
> 845 LoC: reubicar el problema, no resolverlo) —
> `node_execution_delegations.py` (487), `run_observability_delegations.py`
> (255) y `run_budget_delegations.py` (138). Quedan dos god modules:
> `ports/__init__.py` (927) y `storage_delegations.py` (915, cinco
> clases cohesivas con métodos ≤27 LoC: estalla por tamaño de fichero,
> no por concentración de responsabilidad). **Tercera aparición del bug
> F401 de re-exports** (tras WI-65 con 61 tests y WI-66 con 133), esta
> vez detectada por la red dirigida. Dos aprendizajes escritos en la
> red: un grep de `from ... import` no ve los accesos por atributo
> (`runcontroller.BudgetViolationKind`), y `vars(cls)` no ve lo
> heredado, así que la superficie pública se afirma con
> `inspect.getmembers`. Verificación: **2019 passed** (1966 + 53),
> incluidos los 483 de runtime/H9/H10.
> **WI-66 cerrado** (2026-10-02, commit `e07413b`, ADR-0023):
> `RunController._execute_one` 143 → **74 LoC**, en cuatro fases
> nombradas cuyo nombre dice qué invariante protegen: `_node_guard`
> (budget e idempotencia antes de tocar el nodo), `_compile_node_handoff`
> (H9-context-in-run: FAILED sin invocar el adapter),
> `_invoke_node_adapter` (frontera con código externo que no tumba el
> run) y `_settle_node_outcome` (outcome declarado y cierre atómico).
> El hallazgo P3 del audit baja de **9 a 8** funciones >80 LoC.
> **Coste medido y consciente**: el fichero crece 1289 → 1421 LoC, así
> que se arregla P3 empeorando el número de god module (sigue en 3).
> Son métricas distintas y el módulo estaba y sigue sobre el umbral, así
> que el plan no cambia: fase 2 de ADR-0019. La red (16 tests) fija el
> **orden de los colaboradores de primer nivel** — que es lo que
> sostiene H9/H10 — por orden de primera aparición, porque el log plano
> mezcla las llamadas internas de `_is_budget_exhausted` y fijarlas
> produciría un contrato frágil que describe la implementación, no la
> invariante. Verificación: **1966 passed** (1950 + 16), incluidos los
> 433 de runtime/H9/H10.
> **H-01 CERRADO — WI-65 completo** (2026-10-02, commits `9c104ac` y
> `2f5f7e4`, ADR-0022): la god class `Storage` (1807 LoC, 80 métodos)
> deja de figurar como god module. `storage.py` queda en **623 LoC**
> tras dos fases: los 65 métodos de delegación pasan a cinco mixin por
> componente (`storage_delegations.py`, fase 1) y los 12 mappers
> fila→DTO + `_uid` y el DDL salen a `row_mappers.py` y `schema.py`
> (fase 2). **No se mueven** `_tx`/`_atomic`/`_migrate`/
> `_insert_event_in_tx`/`_atomic_state_and_event`: ADR-0016 exige que
> los atómicos H9/H10 compartan `self._conn` sin duplicarlo. Tres
> regresiones reales presas y corregidas por la red: (a) `ruff --fix`
> borró por F401 los DTO re-exportados que 7 módulos importan desde
> `storage` (61 tests caídos); (b) el helper `_public_methods` de
> `test_persistence_ports.py` quedó obsoleto con la herencia y daba
> por roto un `Storage` que sí cumple el Protocol; (c) los mappers
> **construyen** DTOs, así que bajo `if TYPE_CHECKING:` ruff pasa
> limpio y el `NameError` solo salta al ejecutar (133 tests caídos) —
> la red que lo fija se verificó que **falla** al reintroducir el bug.
> Verificación: **1950 passed** (1880 originales + 70 nuevos), ruff y
> format limpios. Quedan 3 god modules: `runcontroller.py` (1289),
> `ports/__init__.py` (927) y `storage_delegations.py` (915, cinco
> clases cohesivas en vez de una god class).
> Última verificación: 2026-10-02 (Europe/Madrid) — **CI local canónica
> REAL** con el binario pineado: `1880 passed in 85.34s`, `All checks
> passed!`, 8 StepStarted/StepFinished/EchoOutputCaptured, 5/5 stages,
> 0 StepFailed, `Pipeline finished with SUCCESS`. Dos defectos de
> gobernanza corregidos esta sesion (commits `1bb545d`, `3665262`):
> (a) `mise.toml` no fijaba `pipelinek`, asi que el comando canonico
> resolvia al shim homonimo de asdf con otra version; ahora fija
> `"github:Rubentxu/pipeline-kotlin" = "0.39.0"`. (b) El comando
> canonico **podia declarar verificado sin verificar nada**: sin
> `--rerun` el motor reutiliza el veredicto cacheado por `cacheKey` y
> devuelve SUCCESS en 72 ms con cero steps ejecutados (medido). Ver
> `evidence/pipelinek-bakeoff-2026-10-02.md`.
> Última verificación (release): 2026-10-02 00:55 (Europe/Madrid, **release v0.16.9 PUBLICADA y PUSHEADA** — tag anotado sobre `600279a`, `origin/main` = `cdbfbb2` con peel verificado; versión activa `0.16.9.dev0`, trabajo post-release por regla AGENTS §12).
> Iniciativa `g-skillgraph-bootstrap` **COMPLETED** en v0.6.0 (2026-09-23).
> Etapa 7 (runtime/reconciliación) **CERRADA** en v0.14.0 (2026-09-24).
> Versión activa: `0.16.8` — **RELEASE v0.16.8 PUBLICADA** (etiqueta anotada `v0.16.8` sobre el commit `8eda4ea`, peel verificado). SemVer derivado del historial verificado de `v0.16.7..8eda4ea`: 5 `refactor` + 2 `test` + 5 `chore` + 1 `docs`, 0 `feat`, 0 `fix`, 0 breaking => PATCH (solo forma). WI-56 descomposicion ADR-0016 completa: 5 cortes estranguladores (corte 1 runs `ce0f291`, corte 2 policy `7001479`, corte 3 knowledge `c125715`, corte 4 events `6895725`, corte 5 promotions `f439c74`), cada uno con red de contrato previa (RED honesto) y cero ediciones en callers (REQ-WI56-1/I1). Componentes reales: SqliteRunRepository, SqlitePolicyStore, SqliteKnowledgeRepository, SqliteEventStore, SqlitePromotionRepository; comparten conexion via Storage._conn, _tx/_atomic resueltas late (H9/H10 preservados: helpers atomicos permanecen en Storage). SQL vivo en storage.py restringido a DDL/_migrate/helpers atomicos; storage.py 2837 -> 1807 LoC. 1754/1754 tests no-UAT PASS, ruff limpio, release governance gate 2 passed. **Hallazgo operativo de esta sesion**: `.jcode-scratch/` no estaba ignorado, de modo que el propio acto de verificar dejaba `git status --porcelain` con entradas no versionadas y bloqueaba el paso 1 del checklist de release de SDDK; corregido en `8eda4ea` (verificado con `git check-ignore -v`). Segunda correccion: `STATE.yaml` declaraba 27 releases pero solo listaba hasta v0.16.0, es decir 7 releases publicadas (v0.16.1..v0.16.7) no estaban en el registro; rehechas con SHA y fecha reales verificados contra `git rev-list`. Gates del ciclo WI-56: implementation-complete, tests-pass, policy-compliant, debt-severity/priority-assigned; verification-report PASS con debt-report (1 finding low: flake preexistente de orden aleatorio en net knowledge, no regresion). Descubrimiento del ciclo: los def de Storage estan a nivel modulo (4sp) y el shim legacy posterior en el cuerpo de clase pisa el facade nuevo (la ULTIMA definicion gana); el Protocol EventStore exige 5 metodos (list_events_for_run vive en run_repository desde el corte 1: puente, no duplicar).
> Stewardship backlog P1 Opción A (H9 addendum honesto) **CERRADO** en `327a913` (2026-09-25).
> WI-01 (release & integration readiness) **RELEASE COMPLETA** — `v0.14.1`. WI-02a (refactor B+C puertos) **RELEASE COMPLETA** — `v0.14.2`. WI-02b (segundo refactor: EventLog/KC por Protocols + escape hatch removal) **RELEASE COMPLETA** — `v0.14.3`. WI-03 (governance/receipts migra a KnowledgeRepository, cierra ultimo escape hatch `_conn`) **RELEASE COMPLETA** — `v0.14.4`. WI-06 (coverage hardening `governance/receipts.py` 73%→99%) **HOUSEKEEPING COMPLETO** — `0.14.5.dev0`. WI-07 (coverage hardening `file_handoff.py` 85%→93%) **HOUSEKEEPING COMPLETO**. WI-08 (coverage hardening `governance/improvement.py` 84%→100%) **HOUSEKEEPING COMPLETO**. WI-11 (release `v0.14.6` housekeeping: WI-06..WI-10 agrupados) **RELEASE COMPLETA**. WI-12 (E1 Adapter real: `HttpAgentAdapter` Anthropic + OpenAI + retry + failpoints) **FEAT COMPLETA**. WI-13 (CLI wiring `sg run --adapter http (anthropic|openai)` con `--llm-provider/--llm-model/--llm-timeout-s`) **FEAT COMPLETA**. WI-14 (T3 Threat model S8: STRIDE sobre Adapter HTTP real; repr redact api_key tras RED test honesto; abuse-cases + 2 gaps P3) **DOC COMPLETA**. WI-15 (T5 Backups CLI: `sg backup create|list|restore` con ZIP + SHA-256 + Connection.backup() API atomica) **FEAT COMPLETA**. WI-16 (T6 Observabilidad runbook: 9 secciones, 3 niveles, schema/exit-codes/CLI verificados contra codigo real) **DOC COMPLETA**. WI-17 (H-06 deuda: `import json` redundante en `cmd_knowledge_compile` eliminado) **HOUSEKEEPING COMPLETO**. WI-18..WI-20 (H-10 locks.py drift Windows docstring honesto; H-03 pack_loader _validate cc 22→7; H-05 _DummyStorage anti-patron eliminado + raise FileNotFoundError legible) **HOUSEKEEPING COMPLETO**. WI-21..WI-30 (debt-reduction H-03) **RELEASE COMPLETA — `v0.14.8`**. WI-31 (cast Storage Protocol eliminado + factor `Storage.knowledge_repository()` + 7 tests) **REFEACTOR COMPLETO** (1 commit `e82c670`). WI-35 (documentar patron SDDK end-to-end) **DOC COMPLETA** (1 commit `2adeb52`).
> **RELEASE v0.15.0 COMPLETA** (QW-A..I R0 housekeeping + WI-31 + WI-35 sobre base post-v0.14.8): BREAKING QW-B + 3 feat + 1 fix → MINOR bump desde `0.14.8.dev0`. Tag anotado `v0.15.0` SHA `0d73f73` sobre commit `4d6d1b4` (release-receipt: `audits/release-v0.15.0-receipt.md`, archive: `audits/release-v0.15.0-archive.md`). 1078/1078 tests PASS, ruff limpio, cobertura 95.25%. Push al remote pendiente (regla 5: la operator decide el momento del push).
> Tag `v0.14.0` preservado como erratum histórico (package metadata decía `0.7.0.dev0`).

## Goal

**COMPLETED** (2026-09-23, tag v0.6.0).

`g-skillgraph-bootstrap`: "Arrancar SkillGraph siguiendo el blueprint:
Etapa 0 (S0 + S1) → Etapa 1 → Etapa 2".

Re-abierto en sesión 2026-09-23 → v0.6.0-CLOSED (H6 + H7 ejecutados).
Refactor arquitectónico follow-up cerrado en v0.7.0 (2026-09-24).
Etapa 7 cerrada en v0.14.0 (2026-09-24, 6 slices MINOR + 1 refactor sin bump).

Detalle completo de rationale y criterios en `.next-decision.md` y
`STATE.yaml` (`goal.*`, `etapa7_*`, `refactor_v070_*`).

## Hito y trabajo activo

**Sin trabajo activo material.** Iniciativa y Etapa 7 cerradas.

- H0..H7: **cerrados**.
- H8 (Integración pública CLI): **cerrado** en v0.6.0 (ADR-0013).
- Etapa 7 slices 1-6: **cerrados** (v0.8.0 → v0.14.0).
- Refactor context_controller (sin bump): **cerrado** en `6c8c17f`.

# INITIATIVE-CLOSED

**Initiative g-skillgraph-bootstrap cerrada formalmente** (segundo
acto, sesion 2026-09-25T15:37:08Z por consigna del operador "1").
HEAD terminal: `f1b92ff`. Certificado completo en
`INITIATIVE-CLOSED.md`.

## Reactivacion autonoma 2026-09-25T16:07:01Z

Operador reabre con modo AUTO: "avanza con criterio propio buscando
entrega de valor sin dejar la calidad". Workflow STEWARDSHIP-T3-001
aplicado: T3 Threat model (ADR-0015 + tests de attestation + audit).

**HEAD terminal T3**: pendiente commit. 14/14 tests PASS.

## Ultimo estado comprobado

- HEAD: `42a26cf` (WI-11 release v0.14.6 cerrado en tag anotado + bump `.dev0` post-tag; 23 commits ahead of `origin/main`, push pendiente de aprobacion operador; regla WI-01).
- Tests: **1009/1009 PASS** en 188s (`uv run pytest --no-header -q`; baseline post-WI-12). WI-12 anade +25 tests para `HttpAgentAdapter` (E1 Adapter real con strategies Anthropic + OpenAI, retry exponencial, failpoints).
- Package version: `0.14.6.dev0` (release `v0.14.6` cerrado en tag anotado; bump `.dev0` post-tag para cumplir release_governance). Tags previos: `v0.14.0` (erratum historico, d50f666), `v0.14.1` (WI-01 release, e2cdc53), `v0.14.2` (WI-02a release, da95923), `v0.14.3` (WI-02b release, 7dec857), `v0.14.4` (WI-03 release, dd7a3ef), `v0.14.5` (WI-04/05 housekeeping release, 6ac10ff), `v0.14.6` (WI-06..WI-10 housekeeping release, 42a26cf).
- CI dominante: local `pipelinek` (`.pipeline.kts`). GitHub Actions queda como notificacion informativa (ver AGENTS.md §CI Local Obligatorio).
- **20 releases** emitidas: v0.3.0 → v0.14.6 (incluye 4 PATCH/MINOR de refactor: v0.7.0/v0.7.1/v0.7.2/v0.7.3 + 1 refactor sin bump post-v0.14.0 + 1 v0.8.1 PATCH + 6 Etapa 7 S1..S6 + WI-02b v0.14.3 + WI-03 v0.14.4 + WI-04/05 v0.14.5 housekeeping + WI-06..WI-10 v0.14.6 housekeeping). Nota: H15 no requiere bump (no entrega capacidad nueva a nivel de release, añade superficie de governance).
- **UATs: 16/16 PASS** (uat_audit mantenible, invariante al avance).
- Cobertura nucleo re-medida post-WI-07+WI-08: governance/receipts.py 99% (WI-06), governance/improvement.py 100% (WI-08), file_handoff.py 93% (WI-07). Modulos H11/H12: file_signature.py 100%, file_scope.py 100%.
- Working tree: limpio (post-WI-07+WI-08 commit `951e9ef`).
- ruff format + ruff check: limpios.
- HEAD: 20 commits ahead of `origin/main` (push pendiente de aprobacion operador; regla WI-01).
- `STATE.yaml.release` sincronizado con realidad: tag=v0.14.0, 17 releases, 30 capacidades_entregadas, tag_sha=241ccc9f.
- **H9 addendum honesto**: 5/5 entregables cumplidos (WI-12 cierra E1 Adapter real con `HttpAgentAdapter` Anthropic + OpenAI). Ver `audits/h9-addendum-2026-09-25.md` y `specs/wi-12-http-adapter.md`.
- **H10 evolution-v2 COMPLETO**: mapa del recorrido real y baseline (audits/h10-recorrido-real-2026-09-25.md 325 LoC).
- **H11 evolution-v2 COMPLETO**: conocimiento tipado reutilizable (FileSignatures). Ver `src/skillgraph/knowledge/file_signature.py` (ADT cerrada, pure extractor) + `tests/test_h11_file_signature.py` (12 UAT-EVO-01..04 tests). Persistencia via Evidence(kind='file_signature') reusando tabla existente (regla AGENTS §1.5).
- **H12 evolution-v2 COMPLETO**: scopes y consultas composables (FileScope, ScopeQuery, ScopeResolution, aggregate_signatures). Ver `src/skillgraph/knowledge/file_scope.py` + `tests/test_h12_file_signature_scopes.py` (8 UAT-EVO-05..08 tests). Aislamiento E2E-08 estricto: source-en-otro-proyecto lanza `UnknownSourceError` SIN filtrar el source_id (mensaje generico).
- **H13 evolution-v2 COMPLETO**: handoff experto desde consultas (ScopeAwareRecipe, CoverageManifest, HandoffBlockedError, compile_handoff_from_scopes). Ver `src/skillgraph/knowledge/file_handoff.py` + `tests/test_h13_handoff_expert.py` (8 UAT-EVO-09..11 tests). Composicion pura sobre ContextRecipe (NO modifica Literal cerrada de ObligatorySelector). should_skip_adapter() decide skip LLM si manifest completo+fresco.
- **H14 evolution-v2 COMPLETO**: evidencia operativa temporal (ValidationReceipt, is_receipt_applicable, record_validation_receipt, list_applicable_receipts). Ver `src/skillgraph/governance/receipts.py` + `tests/test_h14_validation_receipts.py` (9 UAT-EVO-12..14 tests). Persistencia via Evidence(kind='validation_receipt') reusando tabla existente (regla AGENTS §1.5). is_receipt_applicable() pura: revision + dependency_revisions determinan aplicabilidad (UAT-EVO-14: recibo de A NO es validacion automatica de B).
- **H15 evolution-v2 COMPLETO**: evaluación y automejora acotada (ImprovementCandidate, detect_redundant_extraction, localize_omission, compare_recipes, promote_candidate, rollback_candidate). Ver `src/skillgraph/governance/improvement.py` + `tests/test_h15_improvement.py` (9 UAT-EVO-15..18 tests). Persistencia via Evidence(kind='promotion_decision'|'rollback') reusando tabla existente (regla AGENTS §1.5). UAT-EVO-18: promote_candidate() EXIGE human_approved=True, sin autocertificacion (SelfCertificationBlockedError tipado).
- **EVOLUTION-V2 COMPLETO** (H0..H15): roadmap evolution-v2 cerrado al 100%. 5 nuevos modulos (file_signature, file_scope, file_handoff, governance/receipts, governance/improvement), +58 tests nuevos UAT-EVO.

## Releases post-refactor v0.7.0

| Tag | Commit | Capacidad |
|---|---|---|
| v0.8.0 | `a4d749e` | `cancel_run` + `sg runs cancel` |
| v0.8.1 | `08caacd` | PATCH refactor `_fail_node_with` |
| v0.9.0 | `b4ff317` | `cancel_run` + refactors (`_transition_run_state_with_event`, `_is_budget_exhausted`) |
| v0.10.0 | `72152fe` | `list_runs` + `show_run` + `sg runs list/show` |
| v0.11.0 | `6ad5789` | `logs_run` + `sg runs logs` |
| v0.12.0 | `9d9ae09` | `RunBudget` + `sg runs budget` |
| v0.13.0 | `72651ee` | `RedactionPolicy` + `sg policy get/set` |
| v0.14.0 | `241ccc9` | `RunLock` + `sg run --lock-mode` (locks concurrentes por run) |

Refactor sin bump: `6c8c17f` (extract pure helpers from ContextController).

## Pendientes (sin spec operador explícita)

1. **S7+ del blueprint v1**: no definido en `external/blueprint-v1/`.
   Etapa 7 cierra con "futuros horizontes abiertos".
2. **Grieta de no-atomicidad workflow_runs ↔ runtime_events**: **CERRADA**
   por ADR-0017 (2026-10-01, ciclo wi-50): todo par estado+evento
   semántico se escribe en TX única vía las variantes `*_atomically`
   (H9/H10, sobre la conexión compartida de ADR-0016), con inyección
   de fallos verificada en tests; las escrituras de estado sin evento
   (activación, avance de puntero) son intencionales, y los eventos
   advisory (BudgetExceeded/HandoffCreated/NodeScheduled) convergen
   por `_recover_interrupted` + reconcile determinista. La premisa
   original ("requeriría SQLite WAL transactions coordinando") quedó
   superada por las variantes H9/H10.
3. **Concurrencia real entre procesos**: probada con `multiprocessing`
   en `test_locks.py` (2 procesos se serializan en el mismo run),
   pero no certificada con proveedores reales ni bajo carga.

## Próxima acción concreta

**Initiative cerrada formalmente** (2026-09-25T15:37:08Z, segundo
acto por consigna del operador "1"). Sin próxima acción autonoma.

Para reactivar la iniciativa o abrir una nueva:
- Operador aporta spec para uno de los 4 Trabajos pendientes de
  Etapa 7 (E1 Adapter real, T3 Threat model, T5 Backups CLI,
  T6 Observabilidad), formato libre ~1 parrafo.
- Operador reabre con consigna explicita; el protocolo de
  reapertura esta en `INITIATIVE-CLOSED.md` seccion 8.

**Estado al 2026-09-26 ~11:35 (post-3 consignas 'continua')**:

El operador ha enviado la consigna "continua con el roadmap y sddk"
3 veces en 2 horas sin spec adicional. Búsqueda exhaustiva en 10+
categorías confirma: 0 trabajo substantivo pendiente.

**Estado al 2026-09-26 ~18:18 (post-WI-06/07/08)**:

El operador renueva la consigna "continuamos completando, deuda
tecnica primero y luego roadmap" (autorización explicita para
stewardship créatif). WI-06/07/08 cierran los 3 gaps materiales
reconocidos en cobertura (H-14): `governance/receipts.py` 73%→99%,
`file_handoff.py` 85%→93%, `governance/improvement.py` 84%→100%.
Núcleo evolution-v2 (H11..H15) queda al ≥93% en todos los modulos.

Próximo bloque substantivo (WI-09/10): sincronizar la prosa del
propio CURRENT.md con la realidad post-stewardship + README badges
+ texto evolution-v2. Tras WI-09/10, si no hay spec nueva del
operador, **el agente entra en modo de espera** honesto y NO
fabrica roadmap.

**Modo de espera documentado**: el proyecto está en estado
"esperando spec del operador". Cualquier ciclo de stewardship
transversal posterior requiere:

1. Spec del operador (~1 parrafo) para uno de:
   - E1 Adapter real (proveedor + formato prompts + timeouts + credenciales)
   - T3 Threat model formal (STRIDE/abuse-cases)
   - T5 Backups CLI (formato + retención)
   - T6 Observabilidad (sinks + retención)

2. O desbloquear opcionales con medios:
   - Codecov badge: secret `CODECOV_TOKEN` en GitHub repo settings
   - Audit advisories upstream: acceso a red para `pip-audit` o similar

3. O reabrir iniciativa con nuevo roadmap (ver protocolo seccion 8).

**El agente NO debe fabricar trabajo**. Si la consigna "continua"
se repite sin spec, responder con honest assessment + búsqueda
exhaustiva documentada (como se hizo en este turno).

## Reactivacion 2026-09-26 — WI-06/07/08 (Coverage hardening H-14) cerrado

Cierra el derivado #17 del audit técnico senior (`audits/h14-coverage-gaps-2026-09-26.md`):
los 3 unicos gaps materiales de cobertura reconocidos en `CURRENT.md`
(modulos evolution-v2 H11..H15). Stewardship créatif ejecutado bajo
autorización operador ("continuamos completando, deuda tecnica primero").

### WI-06 (governance/receipts.py 73%→99%)

- Spec: `specs/wi-06-receipts-coverage.md`.
- +28 tests nuevos en `tests/test_h14_validation_receipts.py`.
- 5 clases nuevas: `TestReceiptDataclassValidation`,
  `TestIsReceiptApplicableDeps`, `TestRecordEarlyValidation`,
  `TestListApplicableDefensive`, `TestReceiptVerdictsConstant`.
- Suite: 929→957 PASS en 156.55s.
- Bump `__version__ = "0.14.5.dev0"` post-v0.14.5.
- Commit: `e6ea5c5`.

### WI-07 (file_handoff.py 85%→93%)

- Spec: `specs/wi-07-coverage-file-handoff.md` (retro).
- +17 tests nuevos en `tests/test_h13_handoff_expert.py`.
- 5 clases nuevas: `TestHandoffBlockedErrorMessages`,
  `TestBuildCoverageManifestFoco`, `TestShouldSkipAdapterEmpty`,
  `TestScopeAwareRecipeValidation`, `TestCompileHandoffFromScopesTypeErrors`.
- 5 ramas uncovered restantes (L106, L281, L296, L322, L327):
  type-checks sobre frozen dataclass + isinstance encadenado,
  documentadas en `test_scope_query_invalido_doc` como defensive code.

### WI-08 (governance/improvement.py 84%→100%)

- Spec: `specs/wi-08-coverage-improvement.md`.
- +14 tests nuevos en `tests/test_h15_improvement.py`.
- 7 clases nuevas: `TestImprovementCandidateValidation` (4),
  `TestPromotionDecisionValidation` (4),
  `TestPromoteCandidateApproverRequired` (1),
  `TestRollbackBlockedPolicy` (1),
  `TestDetectRedundantExtractionEmptySigs` (1),
  `TestLocalizeOmissionDefensiveBranches` (2),
  `TestCompareRecipesCorrectionFalse` (1).
- 140 stmts / 0 uncovered / 38 branches / 0 partial → 100%.

### Veredicto

- **Núcleo evolution-v2 (H11..H15) ≥93% cobertura** en todos los modulos.
- Suite consolidada: **984/984 PASS** en 174.26s (+27 tests vs baseline 957).
- Working tree limpio (commit `951e9ef`).
- 0 cambios en codigo de produccion (WI-06/07/08 son solo tests).
- 0 release/tag nuevo. `__version__` sigue en `0.14.5.dev0`.
- Próximos: WI-09 (sincronizar prosa de este mismo `CURRENT.md`,
  cleaning stale markers), WI-10 (README badges + texto evolution-v2),
  después release v0.14.6 si operador aprueba.

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-PRE-PUSH-HOOK cerrado

Cierra el derivado #4 del audit `hooks-ci-2026-09-26.md`: **3ª capa
de defensa operativa** — pre-push hook que ejecuta la suite completa
de pytest antes del push, evitando push que rompan CI.

**Hook** (`scripts/hooks/pre-push`, 62 LoC):
- POSIX shell (mismo patron que pre-commit)
- Toolchain-aware: `mise exec -- uv` con fallback a `uv`
- Suite completa de pytest (~190s) via `run_in_toolchain`
- Bypass via `HOOK_SKIP_PUSH_TESTS=1` (ramas experimentales)
- Bug detectado y corregido: `pipe | tail -N` rompe exit code con
  `set -e`; fix con `mktemp` + `if !` (mismo workaround que `.pipeline.kts`)
- Prefijo `[pre-push]` en logs para identificarse

**Tests** (`tests/test_hooks_system.py`):
- `TestPrePushHook` (8 tests): existe/ejecutable/shebang/pytest/toolchain
  dispatcher/HOOK_SKIP_PUSH_TESTS/prefijo [pre-push]/documenta proposito
- `test_installer_copies_all_hooks` (1 test): e2e en tmpdir con git
  init + installer real; verifica que pre-push NO queda excluido
- Total: 9 tests nuevos

**Verificacion e2e**:
- Caso bypass OK: `HOOK_SKIP_PUSH_TESTS=1 bash scripts/hooks/pre-push`
  -> `[pre-push] HOOK_SKIP_PUSH_TESTS=1 -> saltando suite completa`
- Caso fallo (simulado): patch del hook para usar fake pytest exit 1
  -> `[pre-push] OK` **NO** aparece, aborta con exit 1 + tail del log
- Installer: copia pre-push ejecutable a `.git/hooks/pre-push` con chmod +x

**Suite final**: **888/888 PASS** en 253s (879 baseline + 9 nuevos),
0 regresiones.

**Audit doc**: `audits/pre-push-hook-2026-09-26.md` (239 LoC):
problema + 3 capas defensa + bug doc + 5 limitaciones + 4 derivados.

Sin bump de release (dev-infra).

**Defensa en profundidad completa**:
```text
Local:  pre-commit (lint+format+smoke) → pre-push (full) → push
Remoto: CI (lint+format+full+coverage+cache uv)
```

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-CI-CACHE-COVERAGE cerrado

Implementa derivados #2 (cache uv) y #3 (cobertura) del audit
`hooks-ci-2026-09-26.md` en un solo commit.

**Cache uv en CI**:
- `env.UV_CACHE_DIR = ${{ github.workspace }}/.cache/uv`
- `actions/cache@v4` keyed por `uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}`
- restore-keys fallback (cambios que no afectan deps)
- `uv cache prune --ci` al final (optimiza tamano)

**Cobertura en CI**:
- pytest ahora corre con `--cov=skillgraph --cov-report=xml
  --cov-report=term-missing`
- `upload-artifact@v4` sube coverage.xml (retention 30d, if: always())
- Step summary incluye outcome del nuevo step

**Tests**: 2 nuevos en `TestCIWorkflow` con 6 invariantes totales.
22 → 24 tests en `test_hooks_system.py`. 24/24 PASS.

**Verificacion local**: `pytest --cov` corre 877/877 PASS en 263s.
**Cobertura total medida: 83%** (10 modulos 100%, 4 <80% documentados).

**Limitaciones** (autocritica en audit):
- Sin Codecov badge (decidido NO aplicar).
- Sin enforcement de umbral (fail_under=0, no fuerzo techo).
- Cache miss en primer run (cold start).
- Cache uv funciona porque `mise run sync` internamente usa
  uv sync, que respeta UV_CACHE_DIR.

**Commits**: `8430232 ci: cache uv + coverage artifact`
(4 files, +57/-5 LoC).

**Audit doc**: `audits/ci-cache-coverage-2026-09-26.md` (185 LoC).

Sin bump de release (CI infra).

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-HOOKS-CI cerrado

Implementa el derivado #1 del audit `format-drift-2026-09-26.md`:
pre-commit hook + CI workflow para evitar regresion del drift de
ruff format. **Defensa en profundidad en 3 capas**:

1. **Pre-commit hook local** (`scripts/hooks/pre-commit`, 69 LoC):
   ejecuta `ruff check` + `ruff format --check` + `pytest -q` (cuando
   hay `.py` staged). Toolchain-aware (mise si disponible, fallback
   uv). Bypass via `HOOK_SKIP_TESTS=1` o `--no-verify`.

2. **Installer** (`scripts/install-hooks.sh`, 26 LoC): copia hooks a
   `.git/hooks/`, idempotente, chmod +x automatico.

3. **CI workflow** (`.github/workflows/ci.yml`, 43 LoC): corre en
   push y pull_request a main con `actions/checkout@v4` +
   `jdx/mise-action@v2` + `mise run sync/lint/format/test`. Protege
   incluso si el dev local no instala los hooks.

**Tests** (`tests/test_hooks_system.py`, 165 LoC): 22 tests en 4
clases que verifican presencia + ejecutabilidad + contenido +
contrato del sistema. 22/22 PASS en 0.07s.

**Verificacion e2e del hook**:
- Caso exito: ruff check OK, format OK, pytest 855/855 PASS,
  commit procede.
- Caso negativo: format roto -> error claro con diff sugerido +
  commit abortado.

**Suite completa post-cambios**: **877/877 PASS** en 186s (855
baseline + 22 nuevos), 0 regresiones.

**Limitaciones** (autocritica en audit):
- El agente usa `core.hooksPath=/home/rubentxu/.git-hooks/`
  globalmente, asi que en mi entorno instale un wrapper NO
  commiteable que delega al hook local.
- CI sin cache de uv (~1-2 min extra) y sin cobertura.
- Sin pre-push hook completo (suite lenta vs smoke).

**Commits**: `c7118ef feat(hooks)` (scripts + tests, +246 LoC) +
`d949e33 ci:` (workflow, +45 LoC).

**Audit doc**: `audits/hooks-ci-2026-09-26.md` (172 LoC) con 3
capas + 4 limitaciones + 3 derivados opcionales.

Sin bump de release (dev-infra).

## Reactivacion 2026-09-26 — STEWARDSHIP-DT-FORMAT-DRIFT cerrado

Inspeccion de salud del repo al iniciar sesion detecta **drift de
ruff format en 15 archivos** introducido por los commits H11-H15
evolution-v2 (5c52750 + dc1ef18 + c5f8a94 + 116a2b5) + t3/t3-s2.
El CI gate `format/format --check` estaba **roto**.

Drift puramente cosmetico: collapse de f-strings multilinea,
reorganizacion de kwargs, reordenamiento de tuplas en fixtures.
0 cambios semanticos. Aplicar `ruff format` cierra el gap sin
regresiones.

Verificacion:
- `ruff format src tests` -> 15 files reformatted, 122 unchanged.
- `ruff check src tests` -> All checks passed.
- `ruff format --check src tests` -> 137 files already formatted.
- `pytest -q` -> 855/855 PASS en 251s.

Resultado: **-91 LoC netos** (97 insertions, 188 deletions). CI
gate `format/format --check` desbloqueado.

Commit `3031795 style(format)`. Audit doc en
`audits/format-drift-2026-09-26.md` (117 LoC, tabla 15 archivos
+ trazabilidad origen + derivado pre-commit hook).

Sin bump de release (style/format). HEAD `3031795`.

Recomendacion derivada (futuro ciclo, sin accion ahora): pre-commit
hook + CI workflow para evitar regresion. Coste ~30 min.

## Reactivacion 2026-09-26 — STEWARDSHIP-T-WARNINGS-AUDIT cerrado

Operador reabre con modo AUTO: "continua con tareas roadmap y deuda
tecnica a tu criterio". Sigo el follow-up explicito de
`T-SECURITY-AUDIT-FULL`: "Auditar mensajes `WARNING` y `INFO`".

Inventario: 3 sitios `warnings.warn(...)` en `src/skillgraph`:
- `knowledge/knowledge_invalidator.py:128` (HopLimitExceededWarning):
  expone `max_hops` (param caller) + `len(frontier)` (cardinalidad).
  NO gap.
- `knowledge/knowledge_controller.py:115` (StaleKnowledgeWarning):
  expone `source.source_id` (caller-provided, mismo tenant, mismo
  caller que acaba de pasar el `source`). NO gap, mismo principio
  que `storage.py:446` (uid caller-provided).
- `core/errors.py:125` docstring (N/A).

Verificacion transversal: **0 imports de logging/structlog** en
`src/skillgraph`. El codebase no usa logging estandar, solo CLI
prints (caller-provided) + warnings.warn (cubierto aqui).

Endurecimiento de tests: 3 tests existentes que solo verificaban
TIPO de warning ahora verifican CONTENIDO con `pytest.warns(match=...)`.
Esto convierte la cobertura "verifica tipo" en "verifica tipo +
contenido" y protege contra regresiones futuras.

Commit `5cda0c0 test(security): harden warning content matchers per
ADR-0015`. Audit doc en `audits/warnings-audit-2026-09-26.md`
(234 LoC, tabla 3 sitios + tracing + limitacion autocritica).

HEAD `5cda0c0`, 855/855 tests PASS, 0 regresiones vs baseline.
Sin bump de release (tests-only + docs).

## Reactivacion 2026-09-25T22:20Z — STEWARDSHIP-T-SECURITY-AUDIT-FULL cerrado

Operador reabre con modo AUTO. Auditoria exhaustiva S2/I (ADR-0015)
de los 38 sitios f-string sin `!r` restantes tras mini-audit
previo (244ddf3, 5 sitios). Inventario total: 43 sitios.

Resultado: **0 gaps S2/I** en los 38 sitios restantes.

Trazabilidad uno-por-uno:
- `platform/storage.py:446` (IdentityConflictError uid): caller-provided
- `platform/storage.py:1265/1405` (NotFoundError run_id): caller-provided
- `governance/graph_expansion.py:103` (RuntimeError reason): API misuse
- `knowledge/context_controller.py:92` (StaleKnowledgeError count): cuenta, no ID

+ 26 sitios triviales (path filesystem, source nombre, field validation
  programador): grep transversal confirma callers CLI local o programador.

HEAD `21a096d` == origin/main, working dir limpio. ADR-0015
implementado al 100% para f-strings con identificadores.

Mientras tanto, el repo esta en estado estable con checkpoint
sincronizado en `f1b92ff` (HEAD terminal) y certificado de cierre
en `INITIATIVE-CLOSED.md`.

## Auditoría 2026-09-25

Producido `audits/runtime-2026-09-25.md` (367 LoC, 0 modificado en
producción). Resultado: RunController post-Etapa 7 está en buen
estado. 0 hallazgos materiales, 5 menores (opcionales), 1 deuda
defendible (transaccional cross-proceso). Sin bump recomendado.
163 tests PASS verificados en este turno (23s).

## Stewardship backlog P2 (DT-2 lock) — cerrado 2026-09-25 08:44

3 commits (9889ee8, 8bebaf3, 984d739 + docs en f31fa53) cierran
DT-2 (lock preventivo `tests/uat-evidence/`):

- **9889ee8** `style(format)`: cerrar drift de ruff format (CI gate
  desbloqueado) + SIM117 nested-with en `test_locks.py`. 10 archivos,
  100% cosmetico, 765/765 PASS post-fix.
- **8bebaf3** `feat(tests)`: helper `tests/_evidence_lock.py` (162 LoC)
  + 11 tests en `tests/test_evidence_lock.py` que cubren escritura
  simple, dir auto-creacion, 8 escritores concurrentes al mismo
  uat_id (exactamente 1 payload), 6 a uat_ids distintos (locking
  granular), `history_keep` True/False, fallback Windows, payload
  no serializable, 4-thread barrier sync.
- **984d739** `refactor(tests)`: callers (`_save_evidence` en
  `uat_audit.py`, `_emit_uat_08/09_evidence` en
  `test_h4_expansion_cli.py`) usan el helper. DRY: -18 LoC. Fixtures
  UAT-08/09.json reescritas con HEAD `b53de0d3`.

Suite final: **765/765 PASS** en 166s, ruff limpio, 3 commits
pushados FF a origin/main.

Pendientes stewardship backlog:
- P1: spec S7+ del operador (4 opciones: A Adapter real, B grieta
  transaccional, C cert. concurrencia, D multi-tenancy).
- P3: auditoria `src/skillgraph/runtime/redaction.py` (cifra heredada
  39% vs gaps reales).
- P4: cobertura `cli/runner.py` 55% → 70%+.
- P5: ejecucion S7+ (depende P1).

## Stewardship backlog P3 + P4 (audit redaction + runner) — cerrado 2026-09-25 09:04

3 commits cierran P3 y P4 del stewardship backlog:

- **32197db** `feat(tests)`: 4 tests argparse errors InProcess en
  `tests/test_cli_branches.py` (TestCliArgparseErrors). Cierran el
  contrato observable del parser ante invocaciones inválidas:
  `--bogus-flag`, subcommand inválido, positional extra, `--help`.
- **5de1717** `docs(audit)`: 2 auditorías nuevas
  (`audits/redaction-2026-09-25.md` 170 LoC +
  `audits/runner-coverage-2026-09-25.md` 270 LoC).
- **cda56fa** `docs(state)`: P3 y P4 marcados completed.

### P3 verdict (redaction.py)

- Cifra 39% en STATE.yaml era **heredada** del snapshot T1
  (subset focal de 4 ficheros).
- Re-medido con suite completa: **100% real** (27/27 stmts, 14/14
  branches, 0 miss).
- Módulo puro (sin I/O, sin globales, sin reloj).
- 21 tests en 8 clases cubren cada contrato observable.
- 0 LoC producción modificados, 0 tests nuevos, **sin gaps**.

### P4 verdict (cli/runner.py)

- Cifra 55% en STATE.yaml era **heredada** del subset T1.
- Re-medido con suite completa: **49% real** (1077 stmts, 501 miss).
- Gap **estructural**, no de tests: pytest-cov NO rastrea código
  ejecutado en proceso hijo. 24 comandos cubiertos por subprocess
  (acceptance real) + 6 InProcess.
- Subir cifra sin duplicar subprocess tests violaría CALIDAD §4
  (no duplicar acceptance).
- 4 tests argparse errors aplicados cierran **contrato** de argparse
  (NO suben cifra: argparse eleva SystemExit antes del main()).
- Sin acción adicional posible sin refactor mayor (subprocess-coverage
  plugin, 2-3h, frágil).

## Stewardship backlog P1 Opción D (T8 benchmark) — cerrado 2026-09-25 09:37

3 commits cierran la Opción D de P1 (suite mínima de benchmarks,
ejecutable sin spec del operador):

- **3b4dc7d** `feat(bench)`: `bench/__init__.py` (16 LoC) +
  `bench/bench_context.py` (322 LoC) + `bench/README.md` (104 LoC).
  Mide `compile_handoff` y `refresh_handoff` sobre corpus sintetico
  (Storage SQLite en tempdir). 3 fases por tamaño: `compile_cold`,
  `compile_warm` (mediana de 3), `refresh_warm` (mediana de 3).
  Salida humana (tabla Markdown) o JSON con schema
  `skillgraph.bench.v1`.
- **ee00a9f** `test(bench)`: 3 smoke tests subprocess en
  `tests/test_bench_smoke.py` (78 LoC). Subprocess (NO pytest-cov
  in-process) por el gap estructural documentado en
  `audits/runner-coverage-2026-09-25.md`.
- **cd51732** `docs(bench)`: `audits/t8-benchmark-2026-09-25.md`
  (132 LoC, auditoría de entrega) + `audits/bench/baseline-2026-09-25.json`
  (snapshot primera corrida) + refresh UAT-08/09 con HEAD actual.

### Baseline 2026-09-25

| claims | src | compile_cold(ms) | compile_warm(ms) | refresh_warm(ms) |
| ---    | --- | ---              | ---              | ---              |
| 10     | 2   | 0.526            | 0.310            | 0.318            |
| 100    | 15  | 2.667            | 2.368            | 2.489            |
| 1000   | 143 | 34.245           | 31.985           | 33.323           |

Conclusiones:

- **Linealidad**: ~30 µs/claim en `compile_warm`.
- **Sin cache en refresh**: `refresh_warm ≈ compile_warm`. Hoy
  `refresh_handoff` SIEMPRE recompila aunque no haya cambios
  (oportunidad de optimización documentada).
- **Cold ≈ warm**: gap < 2x en todos los tamaños (sin warm-up patológico).

### Verificación final

- `mise exec -- uv run pytest` — **772/772 PASS** (769 → 772; +3 nuevos).
- `mise exec -- uv run ruff check .` — All checks passed.
- HEAD: `cd51732` (3b4dc7d + ee00a9f + cd51732 pendientes de push).

### Verificación T3 Threat model (2026-09-25 ~16:25)

- HEAD post-ciclo: `fdb2398` (`a25e8f9` + state sync), push OK.
- 14/14 tests PASS en `tests/test_t3_threat_model_attestation.py` (0.97s).
- 167/167 tests PASS en T2 (t3 + redaction + locks + storage + runcontroller + graph_expansion).
- ADR-0015 vive en filesystem local (`external/` gitignored por diseno).
- Audit dedicado: `audits/t3-threat-model-2026-09-25.md`.

### Verificación T3-S2 gap cierre (2026-09-25 ~17:00)

- HEAD post-ciclo: pendiente (commit en este mismo turno).
- 5/5 tests nuevos PASS en `tests/test_t3_s2_message_no_source_id.py` (0.83s).
- 789/789 tests PASS en suite completa (T2; 195s) — 0 regresiones.
- ruff check limpio.
- Audit dedicado: `audits/t3-s2-message-redaction-2026-09-25.md`.
- 3 sitios en `knowledge_controller.py` corregidos (l.135, l.216, l.488).
- Sin bump de release (regla SEMVER: fix sin breaking en contrato observable, acumulado a proxima release).

### Verificación T3-S2-002 entity_id (2026-09-25 ~17:20)

- HEAD post-ciclo: `026747e` == origin/main.
- 4/4 tests nuevos PASS en `tests/test_t3_s2_entity_message_no_entity_id.py` (0.67s).
- T4 completa: **853/853 PASS en 478s, exit 0**, 0 regresiones.
- Audit dedicado: `audits/t3-s2-entity-message-redaction-2026-09-25.md`.
- 2 sitios en `knowledge_controller.py` corregidos (l.179, l.490).
- Housekeeping adicional: T3 test E2E-08 endurecido (ya exige no source_id ni tenant_id), UAT-08/09 refresh pointers.
- Sin bump de release (4 commits coherentes acumulados a proxima release).

## Pendientes (sin cambio)

- **P1 opciones A/B/C** (Adapter real / grieta transaccional /
  certificación de concurrencia) — siguen requiriendo spec operador
  explícito. D (T8) ya cerrada.
- **Gap S2/I** (mensaje filtra source_id): **CERRADO** en `STEWARDSHIP-T3-S2-001` (mensaje opaco al client, chain preservado).
- Quedan: E1 Adapter real (spec: proveedor, prompts, timeouts, credenciales),
  T5 Backups CLI (spec: formato + retención), T6 Observabilidad (spec: sinks + retención),
  Gap A (grieta workflow_runs↔runtime_events, bloqueado por H9-Plan-B).
- **No bump**: T8 no introduce breaking change ni capacidad nueva
  observable para el usuario. Es observabilidad interna. No genera
  release.

## Reactivacion 2026-09-26 — WI-13 CLI HTTP wiring cerrado

WI-13 cierra el bucle del Adapter real (WI-12). El usuario ya puede
ejecutar `sg run` con `--adapter http` para invocar Anthropic u OpenAI
sin tocar codigo, manteniendo `--adapter fake` como default determinista.

### Cambios

- `src/skillgraph/cli/runner.py`: 4 nuevos flags (`--adapter`, `--llm-provider`,
  `--llm-model`, `--llm-timeout-s`) + helper `_build_adapter(args, fixtures_root)`
  que retorna `FakeAgentAdapter` o `HttpAgentAdapter` segun el caso, con
  `ValidationError` tipado para valores invalidos.
- `tests/test_cli_adapter_wiring.py` (nuevo, 219 LoC, 11 tests, 4 clases):
  fake/http/missing-key/rejects-invalid.
- `specs/wi-13-cli-http-wiring.md` (spec + evidencia).

### Evidencia

- HEAD pre-commit: `31562a8` (WI-12 baseline).
- Tests: **1020/1020 PASS** en 238.73s (era 1009, +11 tests nuevos).
- ruff: `check` All checks passed; `format --check` 146 files already formatted.
- CLI `sg run --help` muestra los 4 nuevos flags correctamente.
- D-46: Adapter como drop-in replacement via Protocol `AgentAdapter`
  (D-41). Default `fake` preserva backward-compat 100%.

### Pendiente

- **WI-14 (T3 Threat model)**: STRIDE/abuse-cases documentados sobre
  superficie HTTP nueva (credenciales en env, retry storms, secretos
  en logs).
- **WI-15 (T5 Backups CLI)**: `sg backup create|restore|list`.
- **WI-16 (T6 Observabilidad)**: runbook sinks + retención.
- **WI-17+ (deuda arquitectónica)**: H-01 Storage god-class (2407 LoC),
  H-02 CLI god-module (2332 LoC), H-03 funciones cc>10, H-05 `_DummyStorage`,
  H-06 `import json` inline, H-10 `locks.py` drift Windows.
- Bump `0.14.6.dev0 → 0.14.7` cuando haya suficientes feats acumulados
  (siguiente release candidato).
- Push a origin (regla WI-01, ahora 26 commits ahead of origin/main).

## Reactivacion 2026-09-26 — WI-14 T3 Threat model S8 cerrado

WI-14 cierra el ciclo T3 (Threat model) extendiendo el modelo STRIDE
a la superficie HTTP nueva introducida por WI-12/13. Tambien descubre
y corrige un gap real: el repr/str del adapter filtraba la api_key.

### Cambios

- `docs/architecture/ADR-0015-threat-model-stride.md`: nueva seccion
  S8 (Adapter HTTP real Anthropic + OpenAI) con 6 filas STRIDE
  (4 OK, 2 mitigados con gaps menores P3 deferred). E1 Adapter real
  pasa de gap abierto a CERRADO.
- `src/skillgraph/runtime/http_adapter.py`: `api_key: str = field(repr=False)`
  + `__repr__` explicito que solo muestra provider/model/timeouts.
  Antes, el dataclass auto-generado exponia `api_key='sk-ant-...'`
  en cualquier `repr(adapter)` o `print(adapter)`.
- `tests/test_http_adapter_repr_no_disclosure.py` (nuevo, 2 tests):
  RED -> GREEN tras la mitigacion. Verifica repr y str.
- `specs/wi-14-t3-threat-model-http.md`: spec + 8 abuse-cases.

### Hallazgo honesto (D-47)

El ADR-0015 afirmaba que "el repr NO expone api_key" sin haberlo
verificado. RED test revelo que el dataclass default SI lo exponia.
Mitigacion aplicada: field(repr=False) + __repr__ explicito. Leccion:
los claims de seguridad deben tener tests que los verifiquen.

### Evidencia

- HEAD pre-commit: `8213ea4` (WI-13 baseline).
- Tests: 1022/1022 PASS proyectados (+2 vs WI-13).
- ADR-0015 con 8 superficies (S1..S8), 5 gaps abiertos documentados.
- ruff: All checks passed.

### Pendiente

- WI-15 (T5 Backups CLI) + WI-16 (T6 Observabilidad).
- WI-17+ (deuda H-01..H-10).
- Bump `0.14.6.dev0 → 0.14.7` cuando WI-12/13/14/+15/+16 acumulados.
- Push a origin (regla WI-01, ahora 27 commits ahead).

## Reactivacion 2026-09-26 — WI-15 T5 Backups CLI cerrado

WI-15 cierra el feature T5 del roadmap (`Backups y migraciones`).
El operador ahora puede hacer backup/restore del data-root completo
con verificacion criptografica, sin dependencias externas.

### Cambios

- `src/skillgraph/governance/backups.py` (nuevo, ~395 LoC): API publica
  (create/list/verify/restore) + tipos BackupEntry/BackupManifest/BackupInfo
  frozen+slots; formato ZIP con manifest.json y SHA-256 por archivo.
- `src/skillgraph/cli/runner.py`: sub-comandos `sg backup create|list|restore`
  + dispatcher `cmd_backup` con output legible para humanos.
- `tests/test_backups.py` (nuevo, 22 tests, 6 clases): cubre manifest
  round-trip, errores (data_root/catalog ausentes), SHA-256 mismatch,
  overwrite policy, filtrado de corruptos en `list`.
- `specs/wi-15-t5-backups-cli.md`: spec + decisiones (D-48).

### Evidencia

- HEAD pre-commit: `fc4601c` (WI-14 baseline).
- Tests: **1044/1044 PASS** en 180.48s (+22 vs WI-14).
- ruff: All checks passed.
- CLI: `sg backup --help` muestra los 3 sub-comandos.

### Pendiente

- **WI-16 (T6 Observabilidad runbook)**: docs + sinks.
- **WI-17+ (deuda arquitectónica)**: H-01..H-10.
- Bump `0.14.6.dev0 → 0.14.7` con WI-12/13/14/15/16 acumulados.
- Push a origin (regla WI-01).

## Reactivacion 2026-09-26 — WI-16 T6 Observabilidad runbook cerrado

WI-16 cierra el item `Observabilidad` del ROADMAP. Runbook completo
con 3 niveles (eventos / logs / metricas), validado contra el codigo
real (schema, exit codes, comandos CLI).

### Cambios

- `docs/observability-runbook.md` (nuevo, 300 LoC, 9 secciones).
- `specs/wi-16-t6-observability-runbook.md`: spec + decisiones (D-49).

### Hallazgos durante la escritura (claims verificados honestamente)

- Schema `runtime_events` corregido para coincidir con el real
  (`event_kind`/`payload_json`/`timestamp`, no `event_type`/`payload`/`occurred_at`).
- Exit codes corregidos: `EXIT_VALIDATION=12`, `EXIT_DB_MISSING=5`
  (definidos en `runner.py`, no en `exit_codes.py`).
- `sg runs logs` no soporta `--type`/`--json` (es CSV-like); queries
  avanzadas via `sqlite3` directo.
- Referencia `audits/locks-*.md` no existe; apuntamos a `tests/test_locks.py`.

### Evidencia

- HEAD pre-commit: `c53f0a7` (WI-15 baseline).
- Tests: **1044/1044 PASS** sin cambios (docs-only).
- ruff: N/A (markdown).

### Pendiente

- WI-17+ (deuda arquitectónica H-01..H-10).
- Bump `0.14.6.dev0 → 0.14.7` con WI-12..WI-16 acumulados.
- Push a origin (regla WI-01, ahora 30 commits ahead).

## Reactivacion 2026-09-26 — WI-18..WI-20 deuda cerrada (H-10, H-03, H-05)

Continuacion del cierre de la deuda arquitectonica tras v0.14.7.
Tres fixes quirurgicos:

### Cambios

- `src/skillgraph/runtime/locks.py`: docstring honesto sobre Windows
  (NO soportado, `import fcntl` top-level rompe).
- `src/skillgraph/domain/pack_loader.py`: refactor `_validate`
  (cc 22→7) extrayendo `_check_required/_check_primitive/_check_list`.
- `src/skillgraph/cli/runner.py`: `_open_known_project` ahora RAISE
  FileNotFoundError con mensaje legible cuando el proyecto no existe;
  `main()` tiene handler global que devuelve EXIT_PROJECT_NOT_FOUND=4.
  Clase `_DummyStorage` eliminada (anti-patron).
- `tests/test_h9_cli_inproc_knowledge_refresh_compile_trace.py`: 2 tests
  actualizados al nuevo comportamiento (mensaje legible en lugar de generico).
- `specs/wi-18-20-deuda-arquitectonica.md`: spec + D-51.

### Evidencia

- HEAD pre-commit: `12f389f` (v0.14.7 archive baseline).
- Tests: **1044/1044 PASS** en 188.77s.
- ruff: All checks passed.
- cc `_validate` en pack_loader: 22 -> 7 (~68% reduccion).
- 0 `_DummyStorage` en codigo de produccion.

### Pendiente

- WI-21+ (deuda restante): H-01 Storage god-class (2407 LoC),
  H-02 CLI god-module (2332 LoC), H-03 funciones con cc 11..15.
- Bump `0.14.7.dev0 -> 0.14.8` cuando haya suficientes feats.
- Push a origin (regla WI-01, ~37 commits ahead).

## Reactivacion 2026-09-26 21:36 — WI-21..WI-22 (H-03 continuation)

Continuacion de la deuda H-03 (cc>10) tras WI-19. Tres funciones
mas quedan reducidas con el patron helper extraction:

### Cambios

- `src/skillgraph/governance/graph_expansion.py` WI-21:
  - `validate` cc 24 -> 4 (3 helpers puros: `_check_capabilities`
    cc=3, `_active_remove_warnings` cc<=3, `_check_cycle_bound` cc=10).
- `src/skillgraph/resources/parser.py` WI-22:
  - `parse_markdown` cc 17 -> 2 (4 helpers: `_require_str`,
    `_require_dict`, `_metadata_name`, `_metadata_namespace`).
  - Mensajes de ParseError preservados verbatim.
- `specs/wi-21-h03-graph-expansion-validate.md`,
  `specs/wi-22-h03-parser.md`.

### Decisiones registradas

- D-52: validate-like -> 1 helper por invariante, retorno tuple, <30 LoC.
- D-53: parse_X con 4+ isinstance -> extraer _require_* helpers.
- D-54: _require_* siempre lanza ParseError tipado con source kwarg.

### Evidencia

- Suite completa **1044/1044 PASS** (178-199s).
- ruff: All checks passed.
- commit `9e914ad` (WI-22) sobre `74fe0b8` (WI-21) sobre `1cc52a1`
  (WI-18..WI-20).
- 37 commits ahead of origin/main.

### Pendiente

- WI-23+ H-03 restantes: `take` (runtime/locks.py, cc=16),
  `record_validation_receipt` (governance/receipts.py, cc=14),
  `cmd_promotion_reconcile` (cli/runner.py, cc=14),
  `traverse_invalidations` (cc=13), `invoke` (http_adapter.py, cc=12),
  `compile_handoff_from_scopes` (cc=12).
- H-01 Storage god-class (2407 LoC) y H-02 CLI god-module (2332 LoC)
  son scoped WIs propios, no hacer en este ciclo.
- Considerar bump `0.14.7.dev0 -> 0.14.8` con WI-21+WI-22 (refactor).

## Reactivacion 2026-09-26 22:59 — WI-23..WI-27 (H-03 cleanup masivo)

Continuacion agresiva del refactor H-03. 5 WIs cerrados, cc total
reducido en multiples funciones de la capa core:

### Cambios

- `src/skillgraph/runtime/locks.py` WI-23:
  - `take` cc 16 -> 5 (4 helpers: `_acquire_with_timeout`,
    `_acquire_fail_fast`, `_open_lock`, `_release`).
- `src/skillgraph/governance/receipts.py` WI-24:
  - `record_validation_receipt` cc 14 -> 5 (4 helpers:
    `_require_non_empty` con `empty_msg` kwarg para preservar
    genero, `_require_known_verdict`, `_require_artifact_exists`,
    `_persist_validation_evidence`).
- `src/skillgraph/knowledge/knowledge_invalidator.py` WI-25:
  - `traverse_invalidations` cc 13 -> 5 (3 helpers: `_seed_hop_zero`,
    `_expand_one_hop`, `_warn_if_truncated`).
- `src/skillgraph/runtime/http_adapter.py` WI-26:
  - `invoke` cc 12 -> 7 (sentinel `RetryableHttpStatus` + helper
    `_dispatch_response`).
- `src/skillgraph/knowledge/file_handoff.py` WI-27:
  - `compile_handoff_from_scopes` cc 12 -> 1 (triada clasica
    `_validate_inputs` + `_enforce_coverage_or_raise` +
    `_build_synth_recipe`).
- Specs: `specs/wi-23..wi-27-*.md` y D-55..D-60.

### Decisiones registradas

- D-55: context manager "tomar lock" -> 4 fases, cada fase en helper.
- D-56: `_require_*` con `empty_msg` kwarg para preservar genero.
- D-57: persistencia acoplada (Source+Evidence misma entidad) -> helper.
- D-58: traversal BFS hops -> seed + expand + warn.
- D-59: dispatch por valor con raise tipado por tipo de respuesta.
- D-60: triada clasica de pipeline (validate/enforce/build_synth).

### Estado funciones publicas cc>10

- Antes (WI-22 baseline): 15 funciones.
- Despues (WI-27): 8 funciones. Reduccion 47%.
- Las 8 restantes son mayormente CLI entry points (main, cmd_run,
  cmd_promotion_reconcile) y detect_changes (cc=18).

### Evidencia

- Suite completa **1044/1044 PASS** en cada cierre.
- ruff: All checks passed.
- 5 commits atomicos: `e4e5927`, `3cd8633`, `ab9970f`, `fe67b79`,
  + WI-27 pendiente.
- 41+ commits ahead of origin/main.


## Reactivacion 2026-09-26 23:17 — WI-28 (caracterizacion de deuda)

Hito ceremonial: el auditor `audits/audit_debt.py` (215 LoC) se
ejecuta de forma reproducible y emite `audits/architecture-debt-YYYY-MM-DD.md`
con metricas homologas (cc, loc, nesting) al algoritmo usado en
WI-21..WI-27. Ver D-61..D-66.

### Cambios WI-29 / WI-30 (post-auditor, 2026-09-26 23:25..23:29)

WI-29: cmd_run cc 22 -> 5 (D-67: patron _resolve_X_inputs +
_reconcile_until_terminal + _resolve_X_summary). Tras WI-29 los
hotspots publicos cc>=20 en src/ se reducen a 1: main() cc=43
(excluido por D-64).

WI-30: detect_changes cc 18 -> 8 (D-68: helpers puros
tree-walking a module-level). Tras WI-30 los hotspots publicos
cc>=15 en src/ quedan en 1: main() cc=50 (excluido por D-64).

Politica D-66 satisfecha: cero hotspots publicos cc>=20.

### Cambios

- `audits/audit_debt.py`: CLI `python audits/audit_debt.py`.
  Reporta: 46 modulos, 15985 LoC, 555 funciones, 4 god files,
  hotspots publicos, hotspots privados, funciones largas,
  anidamiento profundo, recomendaciones P0..P3.
- `audits/architecture-debt-2026-09-26.md`: reporte generado.
- `tests/test_audit_debt_smoke.py`: 4 tests via subprocess.
- `specs/wi-28-audit-deuda-arquitectonica.md`.

### Estado de la deuda al cierre WI-28

**P0 (refactor obligatorio)**:
- `cmd_run` (runner.py) cc=22, 122 LoC.
- `_make_schema_validator` (pack_loader.py) cc=22, 77 LoC (privada).
  El main() cc=43 NO se refactoriza surgicalmente (D-64: CLI entry
  point, forma parte del H-02 god module).

**P1 (god modules, requiere ADR)**:
- H-01 storage.py (2407 LoC).
- H-02 cli/runner.py (2477 LoC, incluye `main` cc=43).
- runcontroller.py (1357 LoC).

**P2 (privados cc>=20, opcional)**: caso por caso.

**P3 (funciones >80 LoC)**: ver tabla en reporte.

### Politica D-66

Cero hotspots publicos cc>=20 en cada release, o documentar la
excepcion en CURRENT/CHANGELOG.

### Evidencia

- 4/4 smoke tests audit PASS.
- 1048/1048 suite completa PASS (1044 + 4 nuevos).
- ruff: All checks passed.
- commit `8006c58`, 45 ahead of origin/main.


## Recuperación de contexto SDDK — 2026-10-01

Tras corte de sesión, el contexto se reconstruyó desde autoridad (CLI
SDDK + ledger previo + git), no desde memoria. Detalle completo:
`evidence/sddk-context-recovery-2026-10-01.md`.

- **Drift de gobernanza corregido**: `7e6df87` quedó post-tag
  `v0.16.8` con `__version__` puro (gate en rojo). Corregido en
  `2a3732b`: bump a `0.16.8.dev0` (regla AGENTS §12), STATE.yaml y
  cabecera actualizados; gate 2/2 PASS. Suelto del 29-sep commiteado
  en `18e77d3` (recibos absorbed-cycles, bloqueador B4, capacidad
  `cycle_supersede`, evidencia UAT-08/09). Suite completa 1754/1754
  (hook pre-commit).
- **Migración de identidad SDDK**: el remote normalizó su casing
  (`Rubentxu` → `rubentxu`) y el CLI 2.5.3 deriva otra identidad.
  Decisión del operador: re-adoptar limpio → `sddk adopt apply`
  complete en `p-b7740b96d79ec013`; vault y perfil creados y
  validados; 0 ciclos activos. El historial de `p-74299cf88f51dab9`
  (12 ciclos, 84 eventos) queda archivado, sin migrar.
- **Cierre documental de los 6 ciclos OPEN de la identidad anterior**:
  wi-31/wi-41/wi-42/wi-43/wi-44 CLOSED (trabajo verificado dentro de
  v0.16.8 vía `merge-base --is-ancestor`); wi-46 CLOSED
  (superseded-by-release: su sustancia salió en `dbe7f81`/`21087d1` y
  las etiquetas WI-46 de pack_loader — veredicto inicial DEFERRED
  corregido con constancia en la nota de evidence, §2).
- **B4 mitigado en build actual**: `sddk debt report` ya no fabrica el
  reporte ajeno; falla honesta (fail-closed, "debt detection is not
  implemented"). Los debt gates siguen sin ser evidencia válida;
  alternativa: `audits/audit_debt.py`.
- **pipelinek NO concluyente en sesión agéntica** (addendum en
  `evidence/sddk-context-recovery-2026-10-01.md` §6): run 1 = FAILURE
  falso (motor da por muerto el paso a los ~10s; el pytest real siguió
  y terminó en exit 0), run 2 = SUCCESS sospechoso (unit-tests "pass"
  en 10,2s sin `EchoOutputCaptured`; imposible para 1754 tests).
  Causas documentadas: binario sin gobernar (shim activo 0.43.0; el
  canon AGENTS.md v0.39.0 no está instalado) + interferencia de la
  capa de ficheros del entorno agéntico con la supervisión por cookie
  del engine. Verificación de la sesión: ejecución directa
  (1754/1754, ruff, gate 2/2). Decisión pendiente del operador: fijar
  versión canónica y run de control fuera del entorno agéntico.
- **Próximos pasos legales**: PUSH EJECUTADO (2026-10-02, aprobación
  del operador: `df72bcc..cdbfbb2` + tag `v0.16.9`, peel verificado);
  siguiente trabajo = `sddk cycle start` (candidatos: wi-46, deuda P2
  `cmd_promotion_reconcile` cc=14 / `_make_schema_validator` cc=13).
