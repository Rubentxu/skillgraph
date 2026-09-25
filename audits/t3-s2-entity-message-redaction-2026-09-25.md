# T3-S2-002 cierre gap S2/I (entity_id, no source_id) — Audit de verificacion

**Fecha**: 2026-09-25
**Ciclo**: STEWARDSHIP-T3-S2-002 (continuacion directa de STEWARDSHIP-T3-S2-001)
**Trigger**: gap derivado detectado al cerrar el gap source_id en dcbf81a —
`KnowledgeController.get_entity` y la rama entity de `record_claim` (FK
violation) filtran `entity_id` del tenant atacado en el mensaje de error.

## Resumen

STEWARDSHIP-T3-S2-001 cerro el sub-gap source_id de la superficie S2/I
(ADR-0015). Durante ese ciclo se observo que **la misma clase de bug**
afectaba al path equivalente para `entity_id`. Este ciclo cierra ese
gap hermano con la misma estrategia:

- Tipo de excepcion invariante.
- Chain `__cause__` preservado en paths FK.
- `str(exc)` NO expone el `entity_id` pasado por el caller.

Regla del operador §3 (CIERRE REAL): "completado" requiere verificar
cada condicion original. Cuando T3-S2-001 se cerro, la condicion
pendiente "el controller NO debe filtrar identificadores que cruzan
boundary tenant" estaba **parcialmente verificada** (solo source_id).
Este ciclo la completa para entity_id.

Regla del operador §4 (CALIDAD): "evaluar duplicacion/responsabilidades
similares antes de plantear cambios". Este gap y el de source_id son
literalmente el mismo patron. Aplicar el mismo fix mantiene coherencia
y evita introducir un segundo mecanismo de redaction.

## Cambios

### `src/skillgraph/knowledge/knowledge_controller.py`

Dos lineas cambiadas (mensaje de error sin `entity_id`):

| Sitio              | Mensaje anterior                                       | Mensaje nuevo         |
|--------------------|--------------------------------------------------------|-----------------------|
| `get_entity`       | `"Entity no encontrada: {entity_id!r}"`                | `"Entity no encontrada"` |
| `record_claim` FK  | `"Entity no existe: {claim.subject_entity_id!r}"`      | `"Entity no existe"`  |

Notas:
- El tipo `UnknownEntityError` se mantiene (no cambia control flow).
- El `from exc` se mantiene en el path FK (el chain `__cause__` sigue
  apuntando a la `IntegrityError` de SQLite para diagnostico interno).
- **NO** se cambia la rama Source del mismo `record_claim` (esa ya
  fue arreglada en STEWARDSHIP-T3-S2-001, dcbf81a: "Source no existe").

### `tests/test_t3_s2_entity_message_no_entity_id.py` (nuevo, 154 LoC, 4 tests)

| Test                                                   | Cubre                                                                |
|--------------------------------------------------------|----------------------------------------------------------------------|
| `test_get_entity_message_does_not_leak_entity_id`       | knowledge_controller.py:179 (get_entity)                              |
| `test_record_claim_fk_entity_message_does_not_leak_entity_id` | knowledge_controller.py:490 (record_claim FK entity path)         |
| `test_record_claim_fk_entity_preserves_cause_chain`     | Garantiza `__cause__` no-regresion para path FK entity               |
| `test_get_entity_no_cause_chain`                        | Sanea: get_entity no es path FK, no debe preservar `__cause__`       |

Contrato verificado:
- `UnknownEntityError` se sigue lanzando.
- `str(exc) no contiene` el `entity_id` pasado por el caller.
- `__cause__` se preserva solo donde hay path FK (decisión de
  diagnóstico interno, no de redacción de mensajes).

## Verificacion

```
# T1: suite nueva
$ pytest tests/test_t3_s2_entity_message_no_entity_id.py -v
4 passed in 0.67s

# T4: suite completa
$ pytest tests/ -q
849 passed in 244s

# Lint
$ ruff check tests/test_t3_s2_entity_message_no_entity_id.py \
              src/skillgraph/knowledge/knowledge_controller.py
All checks passed!
```

## Compatibilidad con tests existentes

Los tests que validan el tipo de excepcion (`pytest.raises(UnknownEntityError)`)
siguen pasando porque el fix no cambia el tipo, solo el mensaje. Verificado
en `tests/test_knowledge_controller.py` con la suite completa 849/849 PASS.

## Bonus: endurecimiento del test S2-tenant-isolation E2E-08

En el mismo flujo se ha convertido el KNOWN GAP obsoleto en
`tests/test_t3_threat_model_attestation.py:301` en una verificacion
positiva: el test ya no acepta implicitamente la fuga de source_id,
sino que **exige** que ni source_id ni tenant_id crucen el boundary.
Esto blinda el codigo ante una futura regresion que intente reintroducir
mensajes con identificadores.

## Limitaciones connues (no se cierran en este ciclo)

- **Gap A (grieta workflow_runs <-> runtime_events)**: pendiente.
- **Gap C (stress concurrencia N=10)**: futura corrida.
- **Gap D (re-auditar tras cambio de schema Storage)**: disparador on-demand.
- **E1 Adapter real, T5 Backups, T6 Observabilidad**: requieren spec operador.
- **Claim ID preds / Evidence kind / Finding ID**: NO hemos auditado
  exhaustivamente si el controller filtra otros identificadores (claim_id,
  evidence_id, finding_id, etc.) en otros mensajes de error. Si existen
  fugas analogas, se abordaran en ciclos futuros con el mismo patron.

## Decision rationale

Por que minimo (2 lineas) y no un refactor sistematico:

1. El fix es aditivo. Los 3 fixes de source_id de T3-S2-001 ya
   validan el patron. Aplicarlo a entity_id es simetria esperada, no
   nuevo diseno.
2. Si en el futuro se descubre que TODOS los identificadores deben
   redactarse (claim_id, evidence_id, etc.), el patron es localizable
   y repetible. Un wrapper generico seria over-engineering en este
   momento: prefiero esperar evidencia antes de abstraer.
3. Regla del operador: "Sin bump ceremonial". Mantenemos release sin
   bump (acumulado a la siguiente release que decida el operador).

## Trazabilidad a entregas previas

- **STEWARDSHIP-T3-001** (a25e8f9): descubre los gaps S2/I y los
  registra en `audits/t3-threat-model-2026-09-25.md`.
- **STEWARDSHIP-T3-S2-001** (dcbf81a): cierra 3 sitios source_id.
- **STEWARDSHIP-T3-S2-002** (este ciclo): cierra 2 sitios entity_id
  analogos, manteniendo simetria.
- **Housekeeping UAT refresh** (176184c) + **endurecimiento E2E-08**
  (473a33f): llevados en el mismo turno porque derivan directamente
  de los commits previos.
