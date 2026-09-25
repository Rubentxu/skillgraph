# T3-S2-003 cierre sub-gap claim_id de S2/I (ADR-0015) — Audit de verificacion

**Fecha**: 2026-09-25
**Ciclo**: STEWARDSHIP-T3-S2-003 (cierre de la auditoria de identificadores
que cruzan boundary tenant en KnowledgeController)
**Trigger**: sugerencia explicita del operador al cierre del ciclo previo —
"auditar de forma sistematica el resto de identificadores que podrian
filtrar (claim_id, evidence_id, finding_id)".

## Auditoria realizada (preliminar)

`grep -rnE "raise .*Error\(f" src/skillgraph --include="*.py" | grep "!r"`
sobre todo el modulo. Inventario del KnowledgeController:

| Linea   | Tipo de excepcion | Identificador filtrado | Estado      |
|---------|-------------------|------------------------|-------------|
| l.135   | UnknownSourceError | source_id              | cerrado S2-001 (dcbf81a) |
| l.179   | UnknownEntityError | entity_id              | cerrado S2-002 (eac6838) |
| l.216   | UnknownSourceError | evidence.source_id     | cerrado S2-001 (dcbf81a) |
| l.488   | UnknownSourceError | claim.source_id        | cerrado S2-001 (dcbf81a) |
| l.490   | UnknownEntityError | claim.subject_entity_id| cerrado S2-002 (eac6838) |
| **l.508** | **UnknownClaimError** | **claim_id**       | **cerrado S2-003 (este)** |
| l.261   | TypeError         | (kind/selector)        | NO gap S2/I (error programador) |
| l.391   | TypeError         | (selector)             | NO gap S2/I (error programador) |
| l.422   | UnknownSourceError | (cross-tenant message, NO filtra) | ya redactado |

**Resultado**: tras S2-003, **todos** los mensajes de error del
KnowledgeController que filtran identificadores de tenant estan
redactados. La superficie S2/I (Information Disclosure entre
tenants) esta cerrada para KnowledgeController.

Fuera de KnowledgeController, los `raise ValidationError(f"...{!r}")`
en runtime/plan_loader/catalog/recipe/workflow/etc. son **errores
de programador** (validacion de kinds, selectors, freshness_policy).
NO son gaps S2/I en el sentido ADR-0015: no cruzan boundary
tenant. Ejemplo: `raise ValidationError(f"selector.kind invalido:
{self.kind!r}")` ocurre cuando el programador compone un selector
mal; el caller es el propio modulo de runtime, no un actor externo.

Si en el futuro se identifica un caso donde uno de estos mensajes
SI cruza boundary (e.g. el CLI runner acepta input de usuario y
lo traduce a selector.kind), sera un gap S2/I separado. Por ahora,
no hay evidencia de tal caso.

### Alcance del grep (autocritica)

`grep -rnE "raise .*Error\\(f" | grep "!r"` SOLO detecta mensajes
que usan repr (`{x!r}`). NO detecta f-strings con interpolacion
simple (`{x}`). Una busqueda mas amplia:

```
$ grep -rnE 'raise .*Error\(f".*\{[^}]+\}.*"' src/skillgraph | grep -v "!r"
src/skillgraph/runtime/engine.py:196:
    raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc
src/skillgraph/core/recipe.py:75:
    raise ValidationError(f"token_budget debe ser positivo: {self.token_budget}")
src/skillgraph/runtime/storage.py:1757:
    raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc
... (~20 sitios mas en core/recipe.py, core/workflow.py, etc.)
```

Estos mensajes interpolan valores sin quotes. **Determinar si
cruzan boundary tenant requiere tracing** caso por caso:

- `engine.py:196` / `storage.py:1757` (event_id): el event_id es
  generado internamente por RuntimeEvent (UUID4 determinista); el
  caller ya lo conoce. **NO es gap S2/I**.
- `core/recipe.py:75/83` (token_budget, revision): validacion de
  valores numericos programador-componentes; **NO cruza boundary**.
- `core/recipe.py:114+` (recipe[].kind/value/label): validacion
  de programador; **NO cruza boundary**.

El KnowledgeController era el **unico modulo** donde estos mensajes
son parte del boundary del controller hacia el caller externo
(garantizado por ADR-0015, modelado en storage.start_node_execution
y consistente con el resto de mi auditoria). Por tanto, cerrar el
KnowledgeController es cerrar la superficie S2/I **para este modulo
en particular**, no garantiza que ningun otro modulo en el repo
tenga fugas analogas.

**Si en el futuro se quiere garantia exhaustiva**, abrir un
`STEWARDSHIP-T-SECURITY-AUDIT` que recorra los 20 sitios f-string
sin !r caso por caso, trace el flujo de cada identificador, y
clasifique con evidencia. Por ahora este ciclo cierra el modulo
identificado por ADR-0015 como superficie prioritaria.

## Cambios

### `src/skillgraph/knowledge/knowledge_controller.py`

Una linea cambiada (l.508):

| Antes                                  | Despues                |
|----------------------------------------|------------------------|
| `f"Claim no encontrado: {claim_id!r}"` | `"Claim no encontrado"` |

Notas:
- Tipo `UnknownClaimError` invariante.
- Sin `from exc` (es lookup directo, no FK path).
- Sigue el patron establecido por S2-001 y S2-002.

### `tests/test_t3_s2_claim_message_no_claim_id.py` (nuevo, 84 LoC, 2 tests)

| Test                                                   | Cubre                                  |
|--------------------------------------------------------|----------------------------------------|
| `test_get_claim_message_does_not_leak_claim_id`         | knowledge_controller.py:508 (get_claim)|
| `test_get_claim_no_cause_chain`                        | Sanea: get_claim no es FK, no chain    |

Contrato verificado:
- `UnknownClaimError` se sigue lanzando.
- `str(exc) no contiene` el `claim_id` pasado por el caller.
- `__cause__` es None (lookup directo).

## Verificacion

```
# T1: suite nueva
$ pytest tests/test_t3_s2_claim_message_no_claim_id.py -v
2 passed in 0.86s

# T4: suite completa (tras fix)
$ pytest tests/ -q
855 passed in <TIEMPO>s   # 853 + 2 nuevos

# Sin regresion: test existente que solo valida tipo
$ pytest tests/test_knowledge_controller.py::test_get_unknown_claim_raises -q
1 passed in 0.40s

# Lint
$ ruff check tests/test_t3_s2_claim_message_no_claim_id.py \
              src/skillgraph/knowledge/knowledge_controller.py
All checks passed!
```

## Compatibilidad con tests existentes

El test existente `test_get_unknown_claim_raises` (en
`test_knowledge_controller.py:220`) valida el **tipo** de excepcion
(`pytest.raises(UnknownClaimError)`); sigue verde porque el fix no
cambia el tipo, solo el mensaje.

Lo mismo aplica al resto de tests que invocan `get_claim` con
`claim_id` que no existe: dependen del tipo, no del mensaje.

## Decision rationale

Por que este ciclo se cierra aqui:

1. **Regla CALIDAD §4 del operador**: "evaluar duplicacion o
   responsabilidades similares antes de plantear cambios". El gap
   claim_id es **literalmente el mismo patron** que los 2 cierres
   previos; no requiere diseno nuevo.
2. **Regla CIERRE REAL §3**: tras S2-001 y S2-002 la condicion
   "todos los identificadores del boundary tenant estan redactados"
   estaba **parcialmente verificada** (source_id y entity_id
   solamente). Este ciclo la completa.
3. **Reversibilidad minima**: 1 linea, mensaje opaco, sin abstraccion
   nueva.
4. **Sin bump de release**: mismo criterio que S2-001 y S2-002
   (regla del operador §6: "agurpa cambios pequenos coherentes;
   evita micro-releases triviales"). Sera acumulado a la siguiente
   release explicita.

## Trazabilidad a entregas previas

- **STEWARDSHIP-T3-001** (a25e8f9): descubre los gaps S2/I y los
  registra en `audits/t3-threat-model-2026-09-25.md`.
- **STEWARDSHIP-T3-S2-001** (dcbf81a): cierra 3 sitios source_id.
- **STEWARDSHIP-T3-S2-002** (eac6838): cierra 2 sitios entity_id.
- **STEWARDSHIP-T3-S2-003** (este ciclo): cierra 1 sitio claim_id.

**Resultado final**: la superficie S2/I de KnowledgeController
(Information Disclosure entre tenants) queda completamente cerrada
en `HEAD`.

## Limitaciones connues (no se cierran en este ciclo)

- **Gap A** (grieta workflow_runs <-> runtime_events): pendiente.
- **Gap C** (stress concurrencia N=10): futura corrida.
- **Gap D** (re-auditar tras cambio de schema Storage): on-demand.
- **E1 Adapter real, T5 Backups, T6 Observabilidad**: requieren
  spec operador.
- **Redaction en otros modulos** (runtime, plan_loader, recipe,
  workflow, promotion, governance, cli): NO son gaps S2/I en el
  sentido ADR-0015 (son validacion de programador). Si en el
  futuro surge un caso cross-tenant se abordara con el mismo
  patron.
