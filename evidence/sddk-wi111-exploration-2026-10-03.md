# WI-111 — la inmutabilidad del handoff era de fachada

- **Fecha**: 2026-10-03
- **Ciclo**: `p-b7740b96d79ec013/wi111-handoff-frozen-window` (path `A-full`)
- **Serie**: «¿qué declara el repo que nada comprueba?», decimotercera vía
- **Commit**: `168508e`

---

## 1. Lo que el repo declara

`AGENTS.md` §8, una sola viñeta, tres afirmaciones:

> **Handoff**: inmutable + SHA-256 sobre serialización estable
> (capacidades y budget ordenados). El Adapter recibe el hash
> firmado; nunca lo recalcula.

Y `handoff.py:9`, en el docstring del módulo:

> Es INMUTABLE (dataclass frozen, slots=True).

Ninguna de las tres se sostenía. Y la forma del fallo es la misma en
las tres: **`frozen=True` congela el enlace del atributo, no su
valor.** Con `budget: dict[str, int]` dentro, la estructura era
mutable por dentro, y `frozen=True` seguía diciendo "inmutable" en la
firma.

## 2. La segunda mitad es la grave

El bug de la mutabilidad, por sí solo, es theory. Lo que lo convierte
en un defecto es **dónde** se usa el budget: dentro del hash.

El motor, en `node_execution_delegations.py`:

```
  linea 219   context_hash = handoff.context_hash       # PRE  -> se persiste
  linea 241   update_node_execution_handoff(...)        #      fila + handoff_json
  linea 127   self._adapter.invoke(handoff)             # el Adapter recibe el
                                                        #      objeto VIVO
  linea 144   context_hash=handoff.context_hash         # POST -> se RECALCULA
```

El hash se persiste **antes** de que el Adapter toque el handoff, y se
recalcula **después**. `AGENTS.md` dice literalmente que el hash "nunca
se recalcula": la línea 144 hace exactamente lo que la regla prohíbe.

## 3. La medición, antes de tocar nada

`.pipelinek/wi111_measure.py`. No muta el árbol: monta un `Storage`
real en un directorio temporal y ejecuta **un nodo de verdad** con un
Adapter que cumple el `Protocol` y escribe en el budget que recibe.

```
fila node_executions.context_hash : 0063e7dfd167afc6...
evento NodeCompleted               : 951a2d3a16cf7ea8...
evento EvidenceProduced            : 951a2d3a16cf7ea8...
hash que el Adapter vio AL ENTRAR  : 0063e7dfd167afc6...
budget en handoff_json persistido  : {'max_nodes': 1}
```

La fila describe el handoff de **antes**; los eventos, el de
**después**. Los dos son la misma `node_execution`.

**La sonda**: el `handoff_json` persistido contiene `{'max_nodes': 1}`
y **no** la clave que el Adapter inyecto. Sin esa comprobación,
"los hashes difieren" podría ser una lectura equivocada. Con ella se
ve que la fila precede al Adapter — que es lo que la hace ser *la
firma* — y que la divergencia es real.

## 4. Por qué este guard ejecuta y no lee

Un guard por AST habría comprobado que `budget` está anotado como
`Mapping` y habría dado verde. Habría medido **la regla**, no **el
defecto**: el defecto estaba en la *distancia temporal* entre el
instante en que el Core firma el hash y el instante en que el Adapter
recibe el handoff. Esa distancia no aparece en el texto de ningún
fichero.

El guard hace un `reconcile_run` y lee `node_executions` y
`runtime_events` **después**. Es un guard que mide, no uno que lee un
snapshot.

## 5. El arreglo

- `HandoffExecution.budget`: `dict[str, int]` → `Mapping[str, int]`,
  envuelto en `MappingProxyType` sobre una **copia defensiva**.
  Escribir lanza `TypeError`. Mutar el dict que el llamante conserva
  no toca el handoff. El `isinstance(budget, Mapping)` se mantiene:
  sin él, un `str` pasaba como budget y el handoff quedaba corrupto
  con el fallo apareciendo lejos de su causa.
- `_compile_node_handoff` devuelve `(handoff, context_hash)`. El Core
  calcula el hash **una vez**, al firmarlo, y de ahí en adelante solo
  viaja.

## 6. Tres cosas que las propias pruebas encontraron

**Una que no podía fallar nunca.** El primer `test_el_budget_del_dict
_es_copia` mutaba el dict devuelto y luego comparaba contra
`_handoff()` — una **llamada nueva**. Dos objetos distintos, misma
forma: el assert no podía fallar. Ahora relee el **mismo** handoff.

**`MappingProxyType == dict` es `True`.** El test que exigía que
`to_dict` devolviera un dict plano comparaba con `==`, y un
mappingproxy **es igual** a un dict: pasaba con el mapping vivo
devuelto. Lo que discrimina es el **tipo**, y sobre todo que
`json.dumps` lo acepte.

**Contar llamadas sin distinguir el origen.** El primer contador de
llamadas a `context_hash` daba **2**, y el código del motor calcula **1**.
La segunda era la lectura que hace el propio Adapter. Un guard que
cuenta sin distinguir quién pregunta se quejaba de lo equivocado; se
cuenta por origen.

## 7. M5 se reescribió dos veces

La primera versión de M5 quitaba el `sorted()` de
`dict(sorted(self.budget.items()))`. Resultó **inocua**: quitar el
orden no rompe la copia, así que el guard siguió verde y la mutación
no se cazó. La sonda apuntaba además a un test comparativo que no
podía fallar.

La mutación que sí discrimina es devolver el **mapping vivo**
(`"budget": self.execution.budget`), porque `to_dict` deja de
producir algo serializable. Con la sonda reapuntada: **CAZADA**.

Es el mismo patrón de WI-110, con otro disfraz: una sonda mal
apuntada que se cuenta como victoria porque el guard no sabe que
está mirando el sitio equivocado.

## 8. Resultado

| | |
|---|---|
| tests nuevos | 19 (`tests/test_wi111_handoff_frozen_window.py`) |
| mutaciones | **5/5 cazadas**, 0 no detectadas, 0 sin sonda, 0 inválidas |
| regresión runtime | 735 passed |
| mypy | 16 antes, 16 después (preexistentes del mixin) |
| ruff | limpio |
| CJK añadido | **0** |

## 9. Lo que NO arregla

El barrido por AST de `src/skillgraph` encontró **12 campos**
`list`/`dict`/`set` dentro de dataclasses `frozen=True`+`slots=True`.
Se arregló **uno**, el que está en la ruta del hash firmado. Los otros
once:

```
governance/improvement.py:110       ImprovementCandidate.metrics
knowledge/context_controller.py:238 CompiledResource.body
knowledge/file_handoff.py:135-136   CoverageManifest.procedencia_por_firma,
                                   CoverageManifest.revisiones_por_fuente
knowledge/graph.py:118,121,168      Source.locator, Source.working_tree_status,
                                   Evidence.content
platform/ports/dto.py:46,382        StoredEvent.payload, StoredPromotion.payload
runtime/agent.py:44                 AgentResult.result
runtime/engine.py:51                RuntimeEvent.payload
```

Ninguno participa en el hash firmado. Se registran como deuda; abrir
otro frente sería salirse del alcance.

También: **6 dataclasses sin `frozen=True`**, todas en
`platform/uow.py`, capa adaptadora. No mutan `self`. Deuda menor.
