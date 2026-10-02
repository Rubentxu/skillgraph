# WI-76 — Falso éxito: siete shims públicos "preservados" por tests que nunca los ejecutan

- **Ciclo SDDK**: `p-b7740b96d79ec013/wi-76-shim-false-success`
- **Fecha**: 2026-10-02
- **Tipo**: investigación retrospectiva del ciclo WI-72..WI-75 (y del estado heredado que ese ciclo no tocó)
- **Alcance**: sin cambios en `src/`. Solo red de tests. Sin ADR (no cambia contrato).

---

## 1. El hallazgo

Siete funciones de `src/skillgraph/platform/row_mappers.py` están declaradas
como compatibilidad en `storage.__all__` y listadas en `MAPPER_NAMES`
("los 12 mappers extraídos de `storage.py`"), y **dos clases de test
garantizan que siguen vivas**. Ninguna de las dos las ejecuta.

| shim | líneas | qué promete su docstring |
|---|---|---|
| `_row_to_source` | 148-154 | "Alias de compatibilidad (WI-56 corte 3) … El corte 5 reubicara los callers." |
| `_row_to_evidence` | 157-163 | ídem |
| `_row_to_stored_evidence` | 166-172 | ídem |
| `_row_to_claim` | 175-181 | ídem |
| `_row_to_stored_claim` | 184-190 | ídem |
| `_row_to_resource` | 237-243 | ídem |
| `_row_to_relation` | 246-252 | ídem |

Las dos "guardas" existentes:

1. `test_wi60_knowledge_mappers_extraction.py::test_storage_shim_import_keeps_working`
   hace `inspect.getsource(storage._row_to_source)` y comprueba que la línea
   `from skillgraph.platform.knowledge_repository import row_to_source` aparece
   en el **texto**. Su docstring dice literalmente: *"el shim es un wrapper, no
   el mapper mismo"*. Lee la prueba; no la ejecuta.
2. `test_wi65_storage_schema_mappers.py::TestShimPreserved::test_runtime_constructed_dtos_are_importable`
   trabaja **por AST**: recoge los nombres que el módulo construye en runtime
   (`ast.Call`) y exige que estén importados. Tampoco ejecuta.

## 2. Prueba de que es un falso éxito

**Mutación**: se invierten los argumentos del `return` de los 7 shims
(`row_to_source(json, row)` en lugar de `row_to_source(row, json)`). Si alguien
invocara cualquiera de ellos, reventaría con `TypeError`.

| suite | resultado con la mutación |
|---|---|
| `test_wi60` + `test_wi65` (los que "preservan" los shims) | **37 passed** |
| **suite completa** | **2225 passed** |

Siete funciones públicas pueden estar rotas y nada se entera. Eso no es una
cobertura débil: es una garantía que **no existe**, Sostenida por dos clases
de test que dan la impresión de existir.

Mutaciones descartadas por el camino, para no presentar un artefacto como
prueba:

- **Sustituir el `return` por `return None`**: la caza `test_wi60`, pero porque
  el regex que usé borró la línea del import — es una aserción de texto, no de
  comportamiento.
- **Añadir `raise RuntimeError(...)` en el cuerpo**: la caza
  `test_wi65`, pero introduce un nodo `ast.Call` (`RuntimeError`) que su chequeo
  estático no resuelve. Falso positivo de la propia aserción.
- **Invertir argumentos**: no introduce llamadas nuevas ni altera el texto del
  import. Es la mutación honesta, y es la que la suite no ve.

## 3. Por qué nadie los llama (y por qué el shim está muerto)

Resolviendo cada nombre con AST hasta su origen real:

| shim | origen real del nombre en cada uso |
|---|---|
| `_row_to_source` | `knowledge_repository.py:696` → `_row_to_source = row_to_source` |
| `_row_to_evidence` | `knowledge_repository.py:697` → alias local |
| `_row_to_stored_evidence` | `knowledge_repository.py:698` → alias local |
| `_row_to_claim` | `knowledge_repository.py:699`; y `knowledge_claims.py:16` importa `row_to_claim` directamente |
| `_row_to_stored_claim` | `knowledge_repository.py:700`; y `knowledge_claims.py:19` |
| `_row_to_resource` | `knowledge_repository.py:701` → alias local |
| `_row_to_relation` | `knowledge_repository.py:702` → alias local |

Es decir: los callers ya resuelven al **mapper de verdad** (2-3 argumentos), y
el shim de `row_mappers` toma **1**. No hay ni un call-site que lo alcance. Lo
único que los toca es el `import` de re-export de `storage.py:56`.

**Causa raíz**: WI-56 corte 3 dejó los alias en `row_mappers.py` y anunció
que el "corte 5 reubicará los callers". Ese corte 5 sí ocurrió — fue el que
movió los mappers a `knowledge_mappers.py` (ADR-0020) y creó los aliases
`_row_to_X = row_to_X` en `knowledge_repository.py`. Pero los alias de
compatibilidad no se borraron, `MAPPER_NAMES` siguió listándolos, y el
re-export de `storage` se mantuvo. El corte se completó a medias.

Y hay una pista de que nunca hizo falta: el propio docstring de
`test_wi65_storage_schema_mappers.py` justifica el re-export de `storage`
**solo para tres símbolos** — `_SCHEMA_SQL`, `_row_to_stored_event`,
`_row_to_stored_budget`, `_uid` — "porque tres módulos los importan desde ahí
(ADR-0016 corte 5)". Los otros siete no tienen justificación documentada y no
los importa nadie del repo.

## 4. Corrección aplicada

`tests/test_wi76_shim_execution.py`, 14 tests, sin tocar `src/`:

- Oráculo **diferencial**: `shim(fila) == mapper_real(fila)`, y el tipo
  devuelto debe coincidir. Si el shim devuelve otra cosa, revienta, o
  devuelve `None`, el test falla.
- Anti-test-degenerado: se exige que el DTO transporte valor real, para que la
  igualdad no se cumpla comparando dos cosas vacías.

Verificación en ambos sentidos, con la misma mutación de la sección 2:

| suite | antes del arreglo | con el test nuevo |
|---|---|---|
| `test_wi60` + `test_wi65` | 37 passed | 37 passed (siguen ciegos) |
| `test_wi76` | — | **10 failed** |
| suite completa | 2225 passed | 2239 passed |

Los 4 que pasan son los 2 shims de un solo argumento (`_row_to_resource`,
`_row_to_relation`), donde invertir la lista de argumentos no cambia nada: la
mutación es inocua para ellos, no un fallo no detectado.

## 5. Lo que NO se corrige aquí, y por qué

**Borrar los siete shims** los dejaría en un sitio mejor, pero es un cambio de
contrato: están en `storage.__all__` y en `MAPPER_NAMES`. AGENTS.md §10 exige
ADR para desviaciones materiales. Es decisión del operador, no un cleanup.

Lo que sí era defecto —y no opinión— es que nadie los ejecutaba. Eso queda
arreglado y verificado.

## 6. Salvedad

La cobertura de `platform/row_mappers.py` estaba en **68 %**, y los 14
statements sin cubrir eran exactamente los 7 shims × 2 sentencias. Con el test
nuevo esos cuerpos se ejecutan, así que el deficit desaparece. Esto **no**
significa que el código nuevo esté mejor: significa que la cifra por fin
mide lo que dice medir. El instrumento de cobertura fiable es el que landed
WI-75; antes de este trabajo esa cifra era ciega al CLI entero.

---

## 7. Auditoría de extensión: ¿el patrón se repite?

La hipótesis que dejó este trabajo era que un guard sostenido por
`getsource` o por AST podría aparecer en más sitios. Se auditó en vez de
suponerla.

**Inventario**: 40 tests en 29 ficheros combinan `inspect.getsource` con un
`assert`. Triaje:

| categoría | nº | veredicto |
|---|---|---|
| Contratos estructurales ("X no debe contener SQL", "bajo 800 LoC", "Y ya no redefine el tipo que movimos") | ~37 | **legítimos**: no se pueden verificar por comportamiento; comprueban que una refactor movió el código |
| Afirman comportamiento en runtime y solo leen texto | 2 | **falso positivo**: el contrato sí está verificado en otro sitio |
| Falso éxito confirmado | 1 | corregido en §4 |

Los dos candidatos que afirmaban comportamiento en runtime:

**A. `test_wi66::test_fail_node_with_always_returns_false`** — decía
"`_fail_node_with` debe seguir **devolviendo** False" y solo comprobaba que
la última línea del fuente fuese `return False`.

Descartado como falso éxito: insertando un `return None` temprano (dejando
intacta la última línea, que es el punto ciego del guard de texto), lo
cazan 2 tests de `test_runcontroller.py` — porque el efecto secundario de
marcar el nodo FAILED sí está verificado conductualmente. El valor de
retorno no lo consume ningún caller, así que su valor es irrelevante.

Sí quedaba un residuo real: el docstring de `_fail_node_with` afirma
"Devuelve siempre `False` para que el caller haga `return
self._fail_node_with(...)`", y **ninguno de los dos call-sites lo hace**
(`node_execution_delegations.py:210` y `:268` la invocan como sentencia).
Corregido: el guard pasa a invocar la función y comprobar el retorno de
verdad, y el docstring deja de prometer un uso que no existe.

**B. `test_wi44::test_open_known_project_sigue_lanzando`** — decía "debe
seguir **levantando** FileNotFoundError" y comprobaba que la cadena
`"FileNotFoundError"` estuviera en el fuente.

Descartado: `test_h9_cli_inproc_knowledge_refresh_compile_trace.py:198`
verifica el contrato entero y en proceso con
`pytest.raises(FileNotFoundError, match="proyecto 'missing' no encontrado")`.
El guard de texto es redundante, no peligroso.

**Conclusión honesta**: el patrón **no es sistémico**. De los dos candidatos,
ninguno era un falso éxito. La hipótesis del `siguiente` #3 no se sostiene y
se retira. Queda una corrección menor ya aplicada, que es la de WI-76
aplicada por prophylaxis a un guard que era redundante pero nominal.

Esto no vuelve verde el hallazgo de §2: aquel sí era real, y lo era porque
**nada** ejecutaba el shim — ni test conductual, ni el propio contrato. La
diferencia entre A/B y §2 es exactamente esa.
