# WI-77 — El tercer eje del presupuesto (`max_events`) estaba sin un solo test

- **Ciclo SDDK**: `p-b7740b96d79ec013/wi-77-budget-max-events`
- **Fecha**: 2026-10-02
- **Alcance**: sin cambios en `src/`. Solo red de tests. Sin ADR.

---

## 1. Qué se midió y por qué

Pendiente directo de la retrospectiva: cerrar el contrato de AGENTS §6.3
("módulos del core ≥ 90 %") para los que estaban por debajo. Con el
instrumento de cobertura fiable que landed WI-75 se puede medir por
primera vez:

| módulo | cobertura | líneas sin cubrir |
|---|---|---|
| `runtime/run_budget_delegations.py` | **83 %** | 91-105 |
| `runtime/http_adapter.py` | 88 % | (adaptador HTTP externo) |
| `platform/ports/dto.py` | 89 % | DTOs, mayormente `__getattr__` defensivo |

Las 15 líneas de `run_budget_delegations.py` son **el chequeo 2b: el
límite `max_events` del Run**.

## 2. Por qué no es "un detalle sin cubrir"

El docstring de `_is_budget_exhausted` describe tres ejes y promete:

> emite un evento `BudgetExceeded` con `kind=visits` o `kind=events`
> respectivamente antes de devolver True. Así el timeline del Run
> (v0.11.0) muestra al operador **POR QUÉ se abortó**.

Es un control de gobernanza, y su salida es exactamente la explicación
que el operador lee cuando un run se aborta. Sin un solo test: si el
límite estuviera invertido, ausente o escribiera `kind="visits"` por
error, nada lo detectaría. Los otros dos ejes (`max_visits` por nodo con
self-loop, y `max_visits` global del Run) sí están cubiertos.

## 3. Un casi-falso-exito que NO lo era

Al escribir el test, la aserción sobre el payload devolvía
`[REDACTED]` en las tres claves: `kind`, `limit` y `observed`. La lectura
apresurada era "el evento se emite y no dice nada: el operador nunca
sabrá por qué se abortó el run" — el falso éxito más grave que había
podido reportar en esta sesión.

**No es un defecto.** Antes de reportarlo se revisaron los tests
existentes:

- `tests/test_runcontroller.py:1053` afirma exactamente eso, bajo la
  etiqueta **QW-B**: *"default redaction 'metadata' -> valores
  [REDACTED], claves conservadas. El test verifica el shape y tipo, no
  contenido (que estaría filtrado bajo la política por defecto)"*.
- `src/skillgraph/runtime/engine.py:150-155` documenta que la redacción
  se aplica **antes de persistir** y que el `RuntimeEvent` original no se
  muta, así que los tests siguen viendo el evento sin redactar.
- `src/skillgraph/platform/schema.py:100` fija
  `redaction_policy TEXT NOT NULL DEFAULT 'metadata'`, y
  `redact_payload` con `metadata` conserva claves y sustituye valores.

Es una decisión deliberada, documentada y fijada por test. La lección
metodológica queda registrada: un valor `[REDACTED]` que aparece donde se
esperaba un entero **pide verificar si está fijado por contrato antes de
llamarlo defecto**.

## 4. Corrección aplicada

`tests/test_wi77_budget_max_events.py`, 8 tests, sin tocar `src/`:

| test | qué fija |
|---|---|
| `test_limit_reached_returns_true` | límite alcanzado → True |
| `test_limit_reached_emits_budget_exceeded_with_kind_events` | se emite `BudgetExceeded`; bajo política por defecto conserva claves y redacta valores (el contrato QW-B) |
| `test_policy_none_exposes_the_violated_axis` | con `policy=none`: `kind="events"`, `limit`, `observed` reales — **es el test que distingue `max_events` de `max_visits`** |
| `test_under_limit_returns_false_and_emits_nothing` | por debajo del límite → False y ningún evento |
| `test_no_max_events_means_no_limit` | sin `max_events` → nunca agota |
| `test_limit_is_inclusive` | el límite es `>=`, no `>` |
| `test_events_check_is_reached_after_visits_check` | con ambos límites puestos, decide el que se cumple primero |
| `test_absent_budget_means_no_exhaustion` | run sin fila de budget → False |

Solo se sustituye `_count_events` por un contador controlado: lo que se
prueba es la **decisión** del guard, no el conteo (que tiene su propio
contrato en `run_observability_delegations`). Storage, budget en disco y
el append del evento son reales, sin mocks.

## 5. Verificación en ambos sentidos

| mutación | resultado |
|---|---|
| eliminar el chequeo 2b (`if False`) | **5 failed** |
| `event_count > me` en vez de `>=` | **2 failed**, incluido `test_limit_is_inclusive` |
| `kind="visits"` en vez de `"events"` | **1 failed**, en `test_policy_none_exposes_the_violated_axis` |

Cada mutación la caza el test diseñado para ella, que es lo que distingue
una red útil de una que solo cuenta líneas.

## 6. Lo que queda abierto

- `runtime/http_adapter.py` (88 %) y `platform/ports/dto.py` (89 %) siguen
  bajo 90 %. El primero es un adaptador externo (contrato opaco, ramas de
  error de red); el segundo, DTOs con `__getattr__` defensivo. No se
  inventan tests para subir una cifra: quedan para decisión.
