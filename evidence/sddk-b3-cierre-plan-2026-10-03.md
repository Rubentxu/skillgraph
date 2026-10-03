# Plan de implementación — B3-cierre

Ciclo `p-b7740b96d79ec013/b3` · fase `plan`. Encadena con la especificación
(`…-spec-…`) y el diseño (`…-design-…`).

Ocho pasos. Cada uno dice **el test que lo prueba** y **qué se hace si el
test no existe todavía**, porque un plan sin esa columna es una lista de
intenciones.

---

## T1 — Test rojo: el adapter de producción cumple el contrato

**Qué**: `tests/test_b3_production_adapter.py`, con un
`KnowledgeQueryCapability` construido sobre un `Storage` real en `tmp_path`.

**Por qué primero**: el requisito R1 dice «existe un adapter de producción».
El test debe referenciar algo que **todavía no existe**, para que la
ejecución sea roja de verdad y no «verde porque el test no encuentra nada y
salta».

**Rojo esperado**: `ImportError: cannot import name 'KnowledgeQueryCapability'`.

## T2 — Implementar `knowledge/knowledge_query.py`

**Qué**:

- `KNOWLEDGE_QUERY: Final[str] = "sg.knowledge.query"` — el tipo, en una
  constante, por `AGENTS.md 2.4`.
- `KnowledgeQueryCapability`, con `spec` e `invoke`.
- El `KnowledgeRepository` entra **por constructor**, como `Protocol`. Nunca
  `from skillgraph.platform.storage import Storage`.

**Invocación**: `subject` es el uid a mirar; `arguments` acepta `kind`
(`resource` | `claims`) y `limit`. Sin `kind`, no se adivina: se exige.

**Provenance**: cada elemento del `payload` lleva su `source_id` y su
`revision`. Es lo que distingue `observed` de lo que el agente afirmó, que es
la pregunta que B6 quiere poder hacer.

**Verde con**: T1.

## T3 — Test rojo: el kernel resuelve lo que el nodo pide

**Qué**: el recorrido entero —nodo declara `("sg.knowledge.query",)` →
registro con el adapter → kernel → resultado con procedencia— **con el
adapter de producción**, no con el del test de B3.

**Rojo esperado**: `ImportError: cannot import name 'CapabilityController'`.

## T4 — Implementar `runtime/capability_controller.py`

**Qué**:

- `CapabilityOutcome` (`frozen`, `slots`): une el `type_name` **pedido** con
  el `spec` **que respondió**. Son dos cosas distintas y el par es lo que
  permite auditar.
- `CapabilityController.execute(subject, required)` → tupla de outcomes.
- Falta de resolución → `CapabilityNotFound` con la lista de las que faltan
  y las que hay. Se usa `missing_from`, que **ya** existe en el contrato.

**Verde con**: T3.

## T5 — Guard del gate del roadmap, con su contrasalto

**Qué**: dos guards, y el segundo es la mitad importante:

1. `test_el_nucleo_no_nombra_ninguna_capability` — AST sobre `runtime/`,
   `core/`, `resources/`: el `type_name` del adapter **no** aparece.
2. `test_el_rastreo_encuentra_de_verdad_el_nucleo` — el contrasalto. Sin él,
   el primero pasa con una lista vacía, y una lista vacía hace que un guard
   que solo sabe pasar parezca uno que vigila.

**Por qué AST y no un test de comportamiento**: un test de comportamiento
pasa igual si el kernel tiene `if tipo == "sg.knowledge.query"` dentro,
porque el resultado es el mismo. La propiedad es *estructural*.

## T6 — Sonda de mutación, con restauración verificable

**Qué**: al menos cinco mutaciones que rompen propiedades reales, y **la
restauración comprobada por `git diff` de salida idéntico al de entrada**.

El aprendizaje de la sexta entrega, que ya se pagó una vez: invertir el
`replace` no es simétrico cuando el texto no es único, y tomar el sha de
referencia del árbol **antes** de mutar hace que un fallo de restauración se
vuelva invisible justo cuando más importa verlo. Por eso: copia del fichero
entero para restaurar, y `git diff` como única referencia, porque es la
única que el harness no controla.

`PYTHONHASHSEED=0`, por la mutación intermitente de la tercera entrega.

## T7 — Cifra de `STATE.yaml`, escrita DESPUÉS del run

**Qué**: `tests.total` se mide con `pytest --collect-only` y se escribe
después. La regla del propio campo lo dice y ya se incumplió una vez
(`2938` escrito antes del run, y además mal).

## T8 — Certificación y cierre

- `ruff check src tests` y `ruff format --check`.
- Suite completa.
- Guardas de gobernanza: `test_release_governance.py`,
  `test_b0_truth_convergence.py`, `test_wi115*`.
- Commits atómicos, uno por paso lógico.
- Cierre SDDK con evidencia y receipt de verify.

---

## Lo que este plan NO tiene

- **Un paso de «arreglar las 10 inversiones `platform → runtime`».** No son
  un defecto; son la razón por la que `Storage` puede hablar con el motor.
  Reescribirlas es un bloque entero y no compra nada del gate de B3.
- **Un paso de migrar `WorkflowNode.capabilities`.** Ruptura de datos, B8.
- **Un paso de tocar I4 o `'stale'`.** Cerrados y decididos.
- **Un paso de versionar `.pipelinek/`.** Es decisión de política del repo,
  medida y escrita en la evidencia de B3 §11. Se registra como ítem de
  backlog en SDDK, que es donde puede decidirse sin colarse aquí.
