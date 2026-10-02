# WI-65 — Exploration report: descomposicion del facade `Storage`

Ciclo: `p-b7740b96d79ec013/wi65-storage-facade-decomposition`
Fecha: 2026-10-02
Estado: Explore (preparado para `phase.explore.complete`)

## Pregunta

¿Puede reducirse `src/skillgraph/platform/storage.py` (1807 LoC, god
class H-01) sin romper la API publica ni editar un solo caller?

## Medicion (AST, reproducible)

`Storage` es una unica clase con **80 metodos**. Clasificados por
cuerpo real (no por comentario):

| Grupo | Metodos | LoC |
|---|---:|---:|
| Delegacion fina (sin SQL, delega a un componente) | **65** | **759** |
| Metodos con SQL vivo (`_conn` / `_tx` / `_atomic`) | 7 | 189 |
| Otros (propiedades, lifecycle, helpers atomicos) | 8 | 112 |
| Modulo (imports, DDL, dataclasses, helpers) | — | ~747 |

**El 42% del archivo (759 LoC) es delegacion pura.** No logica de
negocio: solo reenvio a los cinco componentes que WI-56 ya extrajo.

## Costuras: 5 mixins, una por componente

Las 65 delegaciones se agrupan de forma **perfectamente disyunta** por
el componente al que reenvian:

| Mixin propuesto | Componente | Metodos | LoC a mover |
|---|---|---:|---:|
| `KnowledgeDelegations` | `knowledge_repository()` | 31 | 329 |
| `RunDelegations` | `run_repository()` | 19 | 267 |
| `PromotionDelegations` | `promotion_repository()` | 7 | 66 |
| `EventStoreDelegations` | `event_store()` | 4 | 52 |
| `PolicyDelegations` | `policy_store()` | 4 | 45 |
| **Total** | | **65** | **759** |

Cada grupo llama a **un unico** metodo de accessor
(`self.knowledge_repository()` y solo ese). Esto hace la extraccion
mecanica: no hay grupo que mezcle componentes, asi que no hay
acoplamiento cruzado que resolver.

## Estrategia: mixin, no reenvio por `__getattr__`

Se propone herencia por mixin (`class Storage(RunDelegations, ...)`) en
vez de composicion con `__getattr__` dinamico.

Motivos:

1. `__getattr__` rompe el tipado estatico, que AGENTS.md §4.1 exige
   explicito. Un mixin conserva las anotaciones reales de cada metodo.
2. Cero ediciones en callers: `Storage` sigue siendo la misma clase
   con los mismos 80 metodos publicly disponibles.
3. Sin cambio de logica: el cuerpo de cada metodo se mueve verbatim.
   No hay rama nueva, ni ruta de error nueva, ni test que Adjustar.
4. Los mixins solo dependen de `self.<accessor>()`, que `Storage` ya
   provee. No hay imports circulares nuevos: los mixins no importan
   `Storage`.

## Riesgo y red de seguridad

| Riesgo | Mitigacion |
|---|---|
| Romper un caller que use uno de los 65 metodos | Tests existentes (1880) los cubren; se anade test de identidad de API publica |
| MRO / metodo Resolution Order inesperado | `Storage` conserva la definicion de los metodos con SQL; los mixins solo anaden nombres nuevos |
| Cambio de comportamiento | Movimiento verbatim + comparacion de bytecode antes/despues |
| Regresion de cobertura | Los 65 metodos ya estan cubiertos; no baja al moverlos |

**Red previa obligatoria (TDD, mismo patron que WI-56):** un test que
fije el conjunto de metodos publicos de `Storage` y otro que verifique
`Storage.<metodo>` es la MISMA funcion que la del mixin. Se escribe
rojo antes de mover.

## Resultado esperado

`storage.py`: 1807 -> ~1048 LoC tras el corte unico. Quedaria por
debajo de... **no**: 1048 sigue sobre el umbral de 800 del audit.
Hace falta una segunda fase (los ~747 LoC de modulo: DDL, dataclasses
y helpers) para cruzar el umbral. El informe de deuda de 2026-10-02
reporta 3 archivos >800 LoC:

| LoC | Path |
|---:|---|
| 1807 | `src/skillgraph/platform/storage.py` |
| 1289 | `src/skillgraph/runtime/runcontroller.py` |
| 927 | `src/skillgraph/platform/ports/__init__.py` |

Por tanto WI-65 se planifica en **dos fases**, y solo la fase 1 es
mecanica. La fase 2 (modulo) requiere decidir donde vive el DDL y los
helpers atomicos `_tx`/`_atomic`, que ADRs previas (H9/H10, ADR-0016)
dejan explicitamente en `Storage`.

## Conclusion de exploracion: SUFICIENTE

La exploracion es suficiente para Specify: la medicion es reproducible
(`python audits/audit_debt.py` + el clasificador AST de este informe),
las costuras son disyuntas y medibles, el riesgo es acotado por tests
existentes y la red nueva, y el patron es el ya validado en WI-56.

**No se ha modificado `storage.py`.** Este informe es solo exploracion.
