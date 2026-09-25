# T3-S2 cierre gap S2/I (message redacting) — Audit de verificacion

**Fecha**: 2026-09-25
**Ciclo**: STEWARDSHIP-T3-S2-001 (continuacion directa de STEWARDSHIP-T3-001)
**Trigger**: gap abierto en ADR-0015 §S2 / Information Disclosure ("KnowledgeController
filtra source_id en mensaje de error")

## Resumen

T3 (audits/t3-threat-model-2026-09-25.md) descubrio que `KnowledgeController.get_source`
filtraba `source_id` en su mensaje de error al cruzar el boundary tenant. El ciclo T3
lo documento como **gap abierto** (responsable: engineering / cuando llegue el fix).

Este ciclo cierra ese gap con 3 cambios minimos y 5 nuevos tests de attestation. El
criterio es estrictamente aditivo: el comportamiento de control flow (se sigue
lanzando `UnknownSourceError`) y el chain (`from exc`) no cambian; solo el mensaje
expuesto al caller deja de filtrar el `source_id`.

## Cambios

### `src/skillgraph/knowledge/knowledge_controller.py`

Tres lineas cambiadas (mensaje de error sin `source_id`):

| Sitio              | Mensaje anterior                              | Mensaje nuevo        |
|--------------------|-----------------------------------------------|----------------------|
| `get_source`       | `"Source no encontrada: {source_id!r}"`       | `"Source no encontrada"` |
| `record_evidence`  | `"Source no existe: {evidence.source_id!r}"`  | `"Source no existe"` |
| `record_claim`     | `"Source no existe: {claim.source_id!r}"`     | `"Source no existe"` |

Notas:
- El tipo `UnknownSourceError` se mantiene (no cambia control flow).
- El `from exc` se mantiene en los paths FK (el chain `__cause__` sigue
  apuntando a la `IntegrityError` de SQLite para diagnostico interno en
  logs/log handlers).
- **NO** se toco la linea 116 (`f"re-registrando source stale: ..."`).
  Esa es una `warnings.warn(StaleKnowledgeWarning)` **interna al
  controller**, no cruza el boundary tenant. El controller opera
  sobre su propio tenant y emite el warning al operator local que ya
  tiene visibilidad sobre ese tenant. La policy es: el controller
  filtra cuando un input **del cliente externo** cruza el boundary y
  podria exponer info de otro tenant.

### `tests/test_t3_s2_message_no_source_id.py` (nuevo, 197 LoC, 5 tests)

| Test                                                   | Cubre                                                                |
|--------------------------------------------------------|----------------------------------------------------------------------|
| `test_get_source_message_does_not_leak_source_id`       | knowledge_controller.py:135 (get_source)                             |
| `test_record_evidence_fk_message_does_not_leak_source_id` | knowledge_controller.py:216 (record_evidence FK path)              |
| `test_record_claim_fk_message_does_not_leak_source_id`  | knowledge_controller.py:488 (record_claim FK source path)            |
| `test_record_evidence_fk_preserves_cause_chain`         | Garantiza `__cause__` no-regresion para record_evidence             |
| `test_record_claim_fk_preserves_cause_chain`            | Garantiza `__cause__` no-regresion para record_claim (path source)   |

Contrato verificado:
- `UnknownSourceError` se sigue lanzando (control flow invariante).
- `str(exc) no contiene` el `source_id` pasado por el caller.
- `__cause__ is not None` para los paths FK (chain preservado).

## Verificacion

```
# Suite nueva (T1)
$ pytest tests/test_t3_s2_message_no_source_id.py -v
5 passed in 0.83s

# Suite completa (T2; sin h9_* characterization)
$ pytest tests/ -q
789 passed in 195.09s

# Lint
$ ruff check tests/test_t3_s2_message_no_source_id.py \
              src/skillgraph/knowledge/knowledge_controller.py
All checks passed!
```

## Compatibilidad con tests existentes

Los tests que validan el tipo de excepcion (`pytest.raises(UnknownSourceError)`)
siguen pasando porque el fix no cambia el tipo, solo el mensaje. Verificado
en `tests/test_knowledge_controller.py` (suite completa, 789/789 PASS).

El test `tests/test_t3_threat_model_attestation.py::test_e2e08_*` que marcaba
el gap como "KNOWN GAP (ADR-0015 S2 / pending)" sigue pasando: su asercion es
que `tenant_id` no aparece, lo cual sigue siendo cierto.

## Limitaciones connues (no se cierran en este ciclo)

- **Gap A (grieta workflow_runs <-> runtime_events)**: pendiente; ver ADR-0015.
- **Gap C (stress concurrencia N=10)**: futura corrida de stress; ver H9-Plan-B.
- **Gap D (re-auditar tras cambio de schema Storage)**: disparador on-demand.
- **Entity no encontrada filtra entity_id** (knowledge_controller.py:490): mismo
  patron pero NO estaba en el gap documentado (el gap fue S2/I sobre
  `source_id`; `entity_id` es otra fuga que requeriria decision del operador
  sobre el modelo de mensajes opacos). No se modifica.
- **Tests que siguen marcando KNOWN GAP**: el comentario en
  `tests/test_t3_threat_model_attestation.py:301` ("KNOWN GAP (ADR-0015 S2 /
  pending): ...NO cumple strict E2E-08") ya es parcialmente obsoleto: el test
  actual acepta la fuga de source_id (no lo verifica). Decidi NO actualizarlo
  aqui para minimizar el delta de este commit; el comentario se podra limpiar
  en un follow-up de mantencion si el operador lo autoriza.

## Decision rationale

Por que un fix minimo (3 lineas, 0 cambios estructurales) y no un refactor:

1. **Calidad (regla operador)**: el controller no tenia un solo "uncaught
   Exception" handler que pudiera reworkear; los tres sitios eran explicitos
   y modificables sin efectos colaterales.
2. **Cobertura del gap**: el contrato del fix esta 100% cubierto por 5 tests
   nuevos (no se relajan contratos existentes).
3. **Reversibilidad**: si el operador decide otro formato de mensaje (e.g.
   incluir `tenant_id` corto, codigos de error), el revert es trivial.
4. **Sin bump de release**: regla SEMVER derivada del historial — el fix es
   `fix(security)` (cierre de fuga). Segun CONVENTIONAL_COMMITS, `fix:`
   sin breaking implica PATCH bump. Sin embargo, dado que el contrato externo
   observable (tipo de excepcion, signatures) no cambia, lo mas seguro es
   **dejar el bump para una release acumulada** (siguiente ciclo o
   trabajo que decida el operador). No se hace bump ceremonial aqui.
