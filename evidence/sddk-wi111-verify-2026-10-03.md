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

## 10. Lo que NO arregla

El barrido por AST encontró **12 campos** `list`/`dict`/`set` dentro de
dataclasses `frozen=True`+`slots=True`. Se arregló **uno**, el único
que participa en el hash firmado. Los otros once se registran en
`evidence/sddk-wi111-exploration-2026-10-03.md` §9.

También: **6 dataclasses sin `frozen=True`**, todas en
`platform/uow.py`, capa adaptadora, que no mutan `self`.
