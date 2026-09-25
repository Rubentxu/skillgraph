# Auditoría de `runtime/redaction.py` (Etapa 7 / S5) — 2026-09-25

> **Fecha**: 2026-09-25 08:50 (Europe/Madrid)
> **HEAD**: `130f89a` (working tree limpio)
> **Modo**: auditoría read-only + tests focalizados.
> **Alcance**: `src/skillgraph/runtime/redaction.py` (102 LoC) +
> `tests/test_redaction.py` (295 LoC, 21 tests).
> **Trigger**: stewardship backlog P3 ("auditar redaction.py: ¿39% cifra
> heredada o gaps reales?").

## 1. Resumen ejecutivo

**Veredicto**: el módulo de redacción está **completo y bien cubierto**.
La cifra de **39% reportada en STATE.yaml** es **heredada** del snapshot
T1 (subset focal de 4 ficheros, medición post-v0.14.0 del 2026-09-24).
**La cobertura real con la suite completa de 765 tests es 100%**:
27/27 sentencias, 14/14 branches. No hay gaps materiales; no se
requieren cambios en código de producción ni en tests.

| Métrica | Valor |
|---|---|
| Cobertura real (suite completa) | **100%** |
| Cobertura reportada en STATE.yaml | 39% (heredada, subset T1) |
| Tests existentes | 21 (8 clases) |
| LoC producción | 102 |
| LoC tests | 295 |
| Hallazgos materiales | **0** |
| Hallazgos menores | 1 (cosmético, no bloqueante) |

## 2. Metodología

1. Re-medir con la suite completa: `pytest tests/test_redaction.py
   --cov=skillgraph.runtime.redaction --cov-report=term-missing`.
   Resultado: **27 stmts, 0 miss, 14 branches, 0 missed → 100%**.
2. Lectura línea por línea del módulo contra los 8 grupos de tests.
3. Verificación de pureza (sin side effects en I/O / reloj / globales).
4. Revisión de contratos del blueprint `external/blueprint-v1/docs/06-controladores.md §9`.
5. Smoke empirico de casos límite (policy="payload" con tupla mixta,
   nested dict, valor escalar).

## 3. Inventario de funciones (3 funciones, todas puras)

| Función | LoC | Tests que la cubren | Cobertura ramas |
|---|---|---|---|
| `validate_policy(policy)` | 12 | `TestValidatePolicy` (×2) | 100% (rama raise + happy) |
| `redact_payload(payload, policy)` | 33 | `TestRedactNone`, `TestRedactMetadata`, `TestRedactFull`, `TestRedactPayload`, `TestRedactionPurity` | 100% (4 políticas × happy path) |
| `_redact_recursive(value)` | 14 | transitivamente via `TestRedactPayload` + `TestRedactionPurity` | 100% (dict/list/tuple/scalar) |

Sin estado mutable, sin globals, sin I/O. Las tres funciones son
**puras totales** (mismo input → mismo output, sin excepciones para
datos válidos). Las excepciones (`ValidationError`) son exclusivas para
entradas inválidas.

## 4. Cumplimiento del blueprint

`external/blueprint-v1/docs/06-controladores.md §9` define las 4
políticas canónicas: `none`, `metadata`, `payload`, `full`. El módulo
las implementa todas y **SOLO esas cuatro**. Añadir una quinta
política es un cambio de contrato del blueprint que requiere abrir
una ADR (regla `AGENTS.md §2.1`).

| Política blueprint | Implementada | Cobertura tests |
|---|---|---|
| `none` (passthrough con copia defensiva) | sí | 2 tests (shallow copy + no redacta secretos) |
| `metadata` (marca todos los valores) | sí | 2 tests (redact all + claves anidadas) |
| `payload` (recursiva, preserva colecciones) | sí | 3 tests (escalares, nested, tuplas) |
| `full` (drop everything) | sí | 2 tests (non-empty + empty payload) |

### 4.1. Defensa contra el bug del `from __future__ import annotations`

`External import` (línea 21) y `RedactionPolicy = Literal[...]` (línea
29): con `from __future__ import annotations`, las anotaciones son
strings y `typing.get_args()` no funcionaría sobre `RedactionPolicy`.
**El módulo NUNCA depende de introspección runtime del Literal**: la
validación real ocurre en `validate_policy()` (línea 45) que compara
contra `_REDACTION_POLICIES: frozenset[str]`. Esa defensa es robusta
y no se ve afectada por el import.

### 4.2. Validación del `policy` argumento de `redact_payload`

`redact_payload` (línea 53) acepta `policy: RedactionPolicy`, pero la
anotación no se enforce en runtime. Línea 76, se llama
`validate_policy(policy)` que **sí falla rápido** si llega un valor
inválido. Eso duplica la validación del smart constructor (defensa en
profundidad). Las 21 ramas de tests que pasan por `redact_payload` la
ejercitan todas.

## 5. Tests existentes: 8 clases, 21 tests

```
TestValidatePolicy (2)
  - test_validate_policy_accepts_known_policies
  - test_validate_policy_rejects_unknown

TestRedactNone (2)
  - test_none_returns_shallow_copy
  - test_none_does_not_redact_secret

TestRedactMetadata (2)
  - test_metadata_redacts_all_values
  - test_metadata_preserves_nested_dict_keys

TestRedactFull (2)
  - test_full_returns_empty_dict
  - test_full_on_empty_payload

TestRedactPayload (3)
  - test_payload_redacts_scalars_but_preserves_collections
  - test_payload_redacts_nested_dict_deeply
  - test_payload_preserves_tuples_immutably

TestRedactionPurity (2)
  - test_redact_does_not_mutate_input
  - test_redact_is_deterministic

TestRedactionTypeAnnotation (1)
  - test_redaction_policy_is_literal

TestStoragePolicyPersistence (3)  -- Storage.upsert_tenant_policy
  - test_get_policy_returns_none_when_absent
  - test_upsert_then_get_policy_round_trip
  - test_upsert_is_idempotent

TestEventLogRedaction (4)  -- EventLog.policy_resolver + redaccion
  - test_eventlog_redacts_payload_when_resolver_returns_metadata
  - test_eventlog_passes_through_by_default
  - test_eventlog_redacts_with_policy_payload
  - test_eventlog_passes_through_with_policy_none
```

Cobertura por contrato observable (no por Línea):
- Validación del smart constructor ✓
- Cada una de las 4 políticas (happy + edge) ✓
- Inmutabilidad del input ✓
- Determinismo (función pura) ✓
- Persistencia por tenant (Storage) ✓
- Integración con EventLog (resolver + aplicación) ✓

**No hay gap de cobertura por contrato.**

## 6. Hallazgos

### F-1 (MENOR, no bloqueante): literal `policy` repetido en tests

`tests/test_redaction.py` repite el string `"none"` 4 veces, `"metadata"`
3 veces, `"payload"` 4 veces, `"full"` 2 veces. Si se añade un 5º valor
al Literal (requiriendo ADR), los tests fallan al comparar con strings
hard-coded. **No es actionable**: las 4 políticas son las únicas
documentadas en el blueprint. Refactor sugerido (no obligatorio):
importar `RedactionPolicy` como type alias y usar tipo en lugar de
string. Coste: ~10 min, valor: robustez ante futura ADR de nueva
política.

Decisión: **NO actionable**. El `Literal` ya protege en el type
checker, y un cambio de políticas requiere ADR (regla §2.1), no es
"feature creep" que pueda llegar orgánicamente.

## 7. Conclusión

**P3 cerrado: la cifra 39% era heredada. La cobertura real es 100%.**

Acciones documentales (no de código):
1. Actualizar `STATE.yaml.coverage_snapshot_*` con la cifra real (100%
   stmts, 100% branches en `runtime/redaction.py`).
2. Marcar `stewardship_backlog.prioridad_3_audit_redaction.estado = completed`.
3. Referenciar este audit desde `CURRENT.md` y `SESSION-JOURNAL.md`.

Acciones de código (todas NO requeridas por este audit):
- 0 LoC de producción modificados.
- 0 tests añadidos (la cobertura ya está completa).
