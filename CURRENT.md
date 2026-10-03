> **Bloque 2026-10-03 (B5) — El diff del grafo deja de ser un parche sin comparar.**
> Versión activa `0.25.0`; último tag `v0.25.0`.
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
