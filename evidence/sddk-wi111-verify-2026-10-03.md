# WI-111 — la inmutabilidad del handoff era de fachada

- **Fecha**: 2026-10-03
- **Ciclo SDDK**: `p-b7740b96d79ec013/wi111-handoff-frozen-window` (path `A-full`)
- **Release**: `v0.22.2` (PATCH)
- **Serie**: «¿qué declara el repo que nada comprueba?», decimotercera vía
- **Commits**: `168508e` (código), más el que fija la trazabilidad

---

## 1. La declaración

`AGENTS.md` §8, una viñeta, tres afirmaciones:

> **Handoff**: inmutable + SHA-256 sobre serialización estable
> (capacidades y budget ordenados). El Adapter recibe el hash
> firmado; nunca lo recalcula.

`handoff.py:9` lo repite: «Es INMUTABLE (dataclass frozen,
slots=True)».

El fallo es el mismo en las tres, y tiene una sola causa: **`frozen=True`
congela el *enlace* del atributo, no su *valor***. Con `budget: dict[str,
int]` dentro, la estructura era mutable por dentro y la firma seguía
diciendo «inmutable».

## 2. Por qué esto no es teórico

El budget está **dentro del hash**. Y el motor lo usa en dos
momentos distintos:

```
  node_execution_delegations.py:219   context_hash = handoff.context_hash   # PRE  -> persiste
  node_execution_delegations.py:241   update_node_execution_handoff(...)    #      fila + handoff_json
  node_execution_delegations.py:127   self._adapter.invoke(handoff)         # el Adapter recibe el VIVO
  node_execution_delegations.py:144   context_hash=handoff.context_hash     # POST -> RECALCULA
```

`AGENTS.md` dice que el hash «nunca se recalcula». La línea 144 hacía
exactamente lo que la viñeta prohíbe.

## 3. La medición

`.pipelinek/wi111_measure.py`, antes de tocar nada. No muta el árbol:
monta un `Storage` real en un directorio temporal y ejecuta **un nodo
de verdad** con un Adapter que cumple el `Protocol` y escribe en el
budget que recibe.

```
fila node_executions.context_hash : 0063e7dfd167afc6...
evento NodeCompleted               : 951a2d3a16cf7ea8...
evento EvidenceProduced            : 951a2d3a16cf7ea8...
hash que el Adapter vio AL ENTRAR  : 0063e7dfd167afc6...
budget en handoff_json persistido  : {'max_nodes': 1}
```

La fila describe el handoff de **antes**; los eventos, el de
**después**. Los dos son la misma `node_execution`.

**Sonda**: el `handoff_json` persistido contiene `{'max_nodes': 1}` y
**no** la clave que el Adapter inyecto. Sin eso, «los hashes difieren»
podría ser una lectura equivocada; con eso se ve que la fila precede
al Adapter — que es lo que la hace ser *la firma*.

## 4. El guard ejecuta; no lee

Un guard por AST habría comprobado que `budget` está anotado como
`Mapping` y habría dado verde. Habría medido **la regla**, no **el
defecto**: el defecto estaba en la distancia entre el instante en que
el Core firma y el instante en que el Adapter recibe el handoff, y esa
distancia no está en el texto de ningún fichero.

`TestElHashNoSeRecalculaDespuesDelInvoke` hace un `reconcile_run` y lee
`node_executions` y `runtime_events` **después**.

## 5. El arreglo

- `HandoffExecution.budget`: `dict[str, int]` → `Mapping[str, int]`,
  envuelto en `MappingProxyType` sobre una **copia defensiva**.
- `_compile_node_handoff` devuelve `(handoff, context_hash)`: el Core
  calcula el hash **una vez**, al firmarlo, y de ahí en adelante solo
  viaja.
- `_open_running_node` extraído de `_execute_one`, que había pasado de
  74 a 83 LoC y rompía el umbral de 80 del guard de WI-66.

## 6. Tres cosas que encontraron las propias pruebas

| lo que pasó | por qué importa |
|---|---|
| un test comparaba contra `_handoff()` —una llamada **nueva**— en vez de releer el handoff mutado | no podía fallar nunca; daba verde con el defecto puesto |
| `MappingProxyType == dict` es `True` | un test que exigía un dict plano y comparaba con `==` pasaba con el mapping vivo; discrimina el **tipo**, y que `json.dumps` lo acepte |
| contar llamadas a `context_hash` daba 2 y el motor calcula 1 | la segunda era la lectura del propio Adapter; hay que contar **por origen** |

## 7. M5 se reescribió dos veces

La primera quitaba el `sorted()` de `dict(sorted(self.budget.items()))`.
Resultó **inocua** — quitar el orden no rompe la copia—, así que el
guard siguió verde. La mutación que discrimina es devolver el
**mapping vivo**, que deja de producir algo serializable. Con la sonda
reapuntada: **CAZADA**.

Es WI-110 con otro disfraz: una sonda mal apuntada que se cuenta como
victoria porque el guard no sabe que mira el sitio equivocado.

## 8. Resultados

| | |
|---|---|
| tests nuevos | 19 (`tests/test_wi111_handoff_frozen_window.py`) |
| mutaciones | **5/5 cazadas**, 0 no detectadas, 0 sin sonda, 0 inválidas |
| regresión runtime | 735 passed |
| mypy | 16 antes, 16 después (preexistentes del mixin) |
| ruff | limpio |
| CJK añadido | **0** |
| SemVer | PATCH → `v0.22.2` |

## 9. Dos guards que el cambio rompió y hubo que arreglar

No eran ruido: eran la red que este bloque dice que existe.

- **`test_execute_one_is_under_80_loc`** (WI-66): `_execute_one` pasó
  de 74 a 83 LoC con el desempaquetado. Arreglado **extrayendo**
  `_open_running_node`, no subiendo el umbral. 76 LoC.
- **`test_every_moved_method_is_reachable`** (WI-67): la lista de 22
  métodos movidos a mixins no incluía el nuevo. Añadido; el recuento
  pasa a 23.

Un umbral que se sube para que el código pase no comprueba nada. Los
dos se resolvieron cambiando el código, no la regla.

## 10. Certificación

**Run canónico**: `4a6a2ad2-282b-4ac3-be4d-cd50d9ce4a0c`. Leído del
journal **después** de terminar, por `run_id` **y** `occurred_at` —
nunca por la línea de salida. 9 pasos ejecutados.

| # | etapa | outcome |
|---|---|---|
| 0 | `discover-repo` | success |
| 1 | `sync-deps` | success |
| 2 | `unit-tests` | success |
| 3 | `coverage-floors` | success |
| 4 | `package-build` | success |
| 5 | `ci-parity` | success |
| 6 | `lint` | success |
| 7 | `evidence` | success |

`RunFinished` → `outcome: success`, `diagnostics: []`. **8/8 etapas en
`success`**.

**Suite dentro del run**: `pytest: 2795 passed in 250.96s`, **0
skipped**. Coincide con la ejecución local previa: 2776 + 19 = 2795.

**El arreglo en el estado final, verificado a mano.** Con un Adapter
que intenta escribir en el budget que recibe:

```
--- NodeFailed
    {"error": "TypeError: 'mappingproxy' object does not support item assignment"}
```

El nodo queda FAILED con el motivo persistido, en vez de continuar
como si nada. **Un intento de escritura ilegal no deja una segunda
descripción que contradiga a la firma.**

**Estado del repo al certificar:**

| | |
|---|---|
| HEAD | `76a0e17` post-release |
| versión activa | `0.22.2.dev0` |
| último tag | `v0.22.2` sobre `1c68a03` |
| SHA-256 `.pipeline.kts` | `7541ced5…2dd42`, **sin drift** |
| árbol | limpio |

**Criterios del PRE-FLIGHT:**

| criterio | verificado |
|---|---|
| C1 `budget` deja de ser dict mutable | `TypeError` al escribir; `MappingProxyType` sobre copia |
| C2 fila y eventos, mismo hash | `TestElHashNoSeRecalculaDespuesDelInvoke` |
| C3 el hash no se recalcula tras el invoke | contador de llamadas, por origen: **1** |
| C4 deduplicación intacta | dos handoffs iguales → mismo hash; el orden no cambia |
| C5 `to_dict()` sigue serializando | `isinstance(dict)` + `json.dumps` |
| C6 `.pipeline.kts` intacto | SHA sin drift |
| C7 el guard muerde si se revierte | **5/5 mutaciones cazadas** |

## 11. Lo que NO arregla

El barrido por AST encontró **12 campos** `list`/`dict`/`set` dentro de
dataclasses `frozen=True`+`slots=True`. Se arregló **uno**, el único
que participa en el hash firmado. Los otros once se registran en
`evidence/sddk-wi111-exploration-2026-10-03.md` §9.

El criterio de no abrir ese frente es la frontera misma: el hash
firmado es lo que separa lo publicado de lo que el agente ve, y lo
que está al otro lado no participa en él. Arreglar los doce sería
mezclar un defecto con una convención.

También: **6 dataclasses sin `frozen=True`**, todas en
`platform/uow.py`, capa adaptadora, que no mutan `self`.
