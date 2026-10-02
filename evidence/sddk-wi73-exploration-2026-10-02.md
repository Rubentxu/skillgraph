# WI-73 — Exploración: `aggregate_file_signatures` y un punto ciego del audit

> Ciclo `p-b7740b96d79ec013/wi-73-p3-aggregate-file-signatures`. Base:
> `e477241` (post-release v0.16.10, ya con WI-72 publicado).

## 1. Medición

| Función | LoC | cc | decisiones | bucles |
|---|---:|---:|---:|---:|
| `list_file_signatures_for_source` | 58 | **10** | 6 | 1 |
| `aggregate_file_signatures` | 86 | **8** | 6 | 2 |

Ambas en `src/skillgraph/knowledge/knowledge_controller.py` (627 líneas).

## 2. Hallazgo: el audit tiene un punto ciego

`list_file_signatures_for_source` es **la función de mayor cc de este
módulo**, y **ningún umbral del audit la captura**:

- P3 (funciones >80 LoC) no la ve: está en 58 LoC.
- P1/P2 (hotspots cc>=20) no la ven: está en cc 10.

El audit mide dos cosas — longitud y cc �� con umbrales 80 y 20. Una
función de 58 LoC y cc 10 cae en el hueco entre ambos. No es una
deuda inventada: está medida, y es la más compleja del fichero. Pero
**no se corta en este workitem**, porque el frente está definido por el
audit y abrir un frente nuevo a mitad de otro es precisamente lo que
las reglas prohíben ("no inventar deuda: medir antes de actuar"). Se
registra aquí con su medición para que la decisión sea del operador.

## 3. Por qué `aggregate_file_signatures` sí está en el frente

86 LoC, cc 8, 6 construcciones de decisión y 2 bucles. Cumple el
umbral P3 con holgura y es, de las cinco funciones que quedan en P3, la
de mayor cc:

| LoC | cc | Función | cc alto? |
|----:|---:|---------|----------|
| 409 | 1 | `build_parser` | no (declarativo) |
| 90 | 2 | `compile_handoff` | no (lineal) |
| 86 | **8** | `aggregate_file_signatures` | **sí** |
| 85 | 1 | `compile_handoff_from_scopes` | no (lineal) |
| 84 | 4 | `promote_candidate` | marginal |

Las otras tres con cc >=4 son o declarativas o lineales:
`build_parser` tiene cc 1 y cero decisiones (tabla de `add_argument`);
`compile_handoff` cc 2 y una decisión; `compile_handoff_from_scopes`
cc 1 y cero.

## 4. Qué hay dentro, medido

El cuerpo tiene cuatro bloques:

1. **Lazy import** de `AggregatedSignatures`, `ScopeQuery` y
   `aggregate_signatures` (regla AGENTS §11.7: evita el ciclo
   runtime↔knowledge).
2. **Guard de tipo**: `isinstance(scope_query, ScopeQuery)` → `TypeError`.
3. **Camino de miembros vacíos**: agregación vacía, 7 líneas.
4. **El bucle de aislamiento** (UAT-EVO-08): por cada `source_id`,
   `get_source`; si lanza `UnknownSourceError`, distinguir
   *existe en otro proyecto* (→ rechazo explícito, sin revelar el
   `source_id`) de *no existe en ninguno* (→ omitir en silencio).
5. **El bucle de recolección**: `signatures_per_source[source_id] = ...`.

El bucle 4 es el núcleo: son 18 líneas que mezclan **dos
responsabilidades** (comprobar pertenencia y clasificar el fallo), con
un `try/except` y un `raise ... from None` dentro. Su nombre en el
código es hoy una variable local (`sources_in_scope`); el nombre del
invariante no existe en ninguna parte.

El bucle 5 es un `for` que **solo acumula** en un dict, exactamente el
patrón que AGENTS §11.8 prohíbe cuando una comprehension dice lo mismo.

## 5. Lo que NO se va a tocar, y por qué

- **El `raise TypeError` del guard de tipo.** Es un CRUDO real contra
  AGENTS §1.2 ("errores tipados, no strings"), pero **no es una
  anomalía**: `file_handoff._validate_inputs` tiene **cuatro** `raise
  TypeError(...)` idénticos para la misma clase de validacion. La
  convención de la casa es `TypeError` para validar **tipos** y
  `ValidationError` para validar **valores**. Cambiar una instancia
  dejando cuatro hermanas igual no quita la inconsistencia: la crea.
  Se reporta como convención no escrita, no se toca.
- **La invariante de aislamiento UAT-EVO-08.** Se mueve *verbatim*. Su
  red actual (`tests/test_h12_file_signature_scopes.py::
  TestUatEvo08ProjectIsolation`) ya fija los dos lados: el rechazo
  explícito sin filtrar el `source_id`, y la omisión silenciosa del
  source inexistente.
- **`list_file_signatures_for_source`.** Medida y reportada (§2), fuera
  de alcance.

## 6. Veredicto

Exploración suficiente. Un workitem, un método, una extracción con
nombre para el invariante, y un `for`-solo-acumula convertido en
comprehension. Sin cambio de contrato observable, sin ADR (mismo
criterio que WI-70/71/72: helpers privados en un fichero que ya es
pequeño, sin frontera de dominio ni superficie publica).
