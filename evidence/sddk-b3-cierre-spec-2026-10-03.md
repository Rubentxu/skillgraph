# Especificación — B3-cierre: el adapter real y el controller kernel

Ciclo: `p-b7740b96d79ec013/b3` · fase `specify` · HEAD de partida
`01d5864f9720e03154ee30277054b2ee304d8a25`.

Esta es la especificación que exige la transición `phase.specify.complete` del
ciclo `b3`. Es `requirements-testable`: cada requisito de aquí abajo tiene un
test que lo mide, y el test falla si el requisito no se cumple.

---

## 1. El hueco, medido sobre el árbol real

Las seis entregas anteriores de B3 dejaron el contrato
(`platform/ports/capabilities.py`) y su resolución
(`CapabilityRegistry`). Lo que **no** existe es lo que el roadmap pide y el
propio bloque admite en su §11:

```
$ git grep -l CapabilityRegistry -- src tests
src/skillgraph/platform/ports/capabilities.py     <- el contrato
tests/test_b3_capability_kernel.py                <- un adapter DENTRO de un test
```

**El único `Capability` que existe está en un fichero de test.** Eso deja el
gate del roadmap sin nada que demostrar fuera del testsuite:

> `ROADMAP.md` §B3 — *«Se puede añadir una capability (tipo, contrato,
> adapter, controller opcional, policy, tests) **sin modificar**
> `RunController`, el storage base ni el motor del workflow.»*

El guard que existe (`TestUnaCapabilitySeAnadeSinTocarElCore`) recorre el
camino entero **con un adapter que nace en el propio fichero de test**. Eso
demuestra que el *núcleo* no está cableado, que es distinto de demostrar que
el *contrato* es cumplible. Un contrato que solo cumple un doble de test es
una forma de contrato, no un contrato.

## 2. Dos requisitos, y por qué son dos

### R1 — Un adapter de producción que satisfaga el contrato

**Debe**: existir una clase, en `src/skillgraph/`, que implemente el
`Protocol` `Capability` y resuelva trabajo real contra machinery que ya
existe en el repo.

**Por qué `sg.knowledge.query`.** El roadmap lista siete capabilities
candidatas. Seis son de productos externos (`CodeAnalysis`, `TelemetryQuery`,
`SecretAccess`…) ySkillGraph no debe reconstruirlos: eso lo dicen tanto el
roadmap como el docstring de `TestElNucleoNoImportaAdapters`. La séptima,
`KnowledgeQuery`, es **dominio propio**: el repo ya tiene la capa de
conocimiento con `KnowledgeRepository` declarado como `Protocol` en
`platform/ports/repositories.py`. Servirla con el primer adapter real:

- no reconstruye el producto de nadie;
- no necesita credenciales ni red, luego es determinista y testeable;
- invierte la dependencia por el puerto, no por la implementación, que es
  lo que §4.3 exige.

**Criterio**: invocar el adapter devuelve un `CapabilityResult` cuyo
`payload` describe lo que el grafo realmente tiene, con la procedencia de
cada elemento, y el `adapter` de la clase.

### R2 — El controller kernel

**Debe**: existir el punto donde un **nombre de capability escrito en un plan**
se convierte en una ejecución, sin que ningún módulo del núcleo nombre una
capability concreta.

**Medida, no plantilla**: el guard tiene que seguir la llamada y comprobar
que ningún fichero bajo `runtime/`, `core/` o `resources/` menciona el
nombre de ningún adapter. Se deriva del árbol, no de una lista escrita.

**Por qué no `core/`.** El docstring de `core/__init__.py` dice: *«Pure types
and errors that have no dependency on infrastructure, storage, runtime, or any
other bounded context»*. Un kernel que consume `platform.ports` depende de
otro contexto acotado, luego **no** va en `core/`. Va en `runtime/`, que ya
importa `platform.ports` en `engine.py` y `runcontroller.py`, y donde vive
el resto de la orquestación.

**Criterio**: dado un registro y un conjunto de capabilities declaradas por
un nodo, el kernel produce un resultado por capability pedida, con su
procedencia, y falla con error tipado si alguna falta.

## 3. Lo que este trabajo NO hace

Declarado, porque el repo mide mucho mejor un límite escrito que un límite
implícito:

- **No** migra `WorkflowNode.capabilities` a specs. §9 de la evidencia: 9
  sitios construyen el campo, 30 lo leen, y `runtime/handoff.py:195` lo mete
  en el hash firmado. Es ruptura de datos, materia de B8.
- **No** mueve `'stale'` fuera de `capabilities`. Decidido y escrito en §8.
- **No** toca el invariante I4. Cerrado en la cuarta entrega.
- **No** emite eventos. La procedencia ya se persiste en el runtime desde la
  sexta entrega (`699e67d`); el kernel devuelve la procedencia, y quien la
  persiste es el motor, que es el que ya sabe el nombre del adapter que
  invocó.

## 4. Cómo se mide cada requisito

| Requisito | Quién lo mide | Cómo |
|---|---|---|
| R1 cumple el contrato | `test_el_adapter_de_produccion_cumple_el_contrato` | `isinstance` sobre el `Protocol` **e** invocación real con `KnowledgeRepository` real |
| R1 no es un doble | `test_el_adapter_de_produccion_esta_en_src_y_no_en_tests` | ruta del fichero, y el nombre no aparece en `tests/` como definición |
| R1 devuelve procedencia | `test_el_resultado_real_dice_quien_y_de_donde` | el `payload` trae `adapter` y la fuente de cada elemento |
| R2 no nombra capabilities | `test_el_kernel_no_nombra_ninguna_capability` | AST sobre el árbol real: ningún fichero del núcleo menciona el tipo del adapter |
| R2 resuelve lo pedido | `test_el_kernel_resuelve_lo_que_el_nodo_pide` | recorrido completo con `CapabilityRegistry` inyectado |
| R2 falla tipado si falta | `test_el_kernel_avisa_de_todas_las_que_faltan` | `CapabilityNotFound` y el mensaje lista las que sí hay |
| El rastreo no mide sobre vacío | `test_el_rastreo_encuentra_de_verdad_el_nucleo` | contrasalto: la derivación tiene que devolver ficheros, y los paquetes vigilados tienen que existir |

## 5. El contrasalto que este bloque ya sabe que necesita

B3 ya cometió dos veces el mismo error de instrumento, y están escritos:

1. El primer gate medía `a == b` entre registros — propiedad que un
   **singleton** cumple mejor que un valor. No distinguía.
2. El harness de mutación se escribió al revés y dio `0/12` con
   `SIN_SONDA` en las doce: prefirió decir «no he medido nada» antes que
   contar doce victorias sobre un árbol que nunca cambió.

La lección que se aplica aquí, y que no es opcional: **todo guard nuevo
necesita su contrasalto en el mismo fichero que el guard**. Un guard que no
puede fallar no es un guard, es decoración con nombre de test.
