# WI-78 — Asimetría en la serialización legacy de los DTO de `ports`

- **Ciclo SDDK**: `p-b7740b96d79ec013/wi-78-dto-serialization`
- **Fecha**: 2026-10-02
- **Alcance**: sin cambios en `src/`. Solo red de tests. Sin ADR.

---

## 1. Qué se midió

Cierre del contrato de AGENTS §6.3 (core ≥ 90 %). Quedaban dos módulos
bajo el umbral después de WI-77:

| módulo | antes | líneas sin cubrir |
|---|---|---|
| `platform/ports/dto.py` | 89 % | 65, 289, 294-297, 301, 338, 345-346, 350, 397, 402, 439, 444 |
| `runtime/http_adapter.py` | 88 % | (adaptador HTTP externo) |

La primera suposición era que las líneas sin cubrir eran las **claves
legacy** de `__getitem__` (`payload_json`, `object_literal_json`,
`stale`). **Es falsa**: mirando los números de línea exactos, son

- `raise KeyError(key)` en el `__getitem__` de 5 DTO,
- el método `get(key, default)` de StoredClaim y StoredEvidence,
- **`to_dict()` entero en 4 de los 9 DTO**.

## 2. Por qué importa

`to_dict()` es la API dict-legacy que los consumers antiguos usan
("serializa preservando los nombres históricos de columnas"). La
cobertura es **asimétrica**:

| DTO | test roundtrip de `to_dict()` |
|---|---|
| StoredEvent, StoredRun, StoredNodeExecution, StoredResource, StoredRelation | sí (`test_stored_event_dto.py`, `test_run_dto.py`, `test_resource_dto.py`) |
| **StoredClaim, StoredEvidence, StoredPromotion, StoredBudget** | **no** |

Ningún código de producción llama a estos `to_dict()` (es superficie de
compatibilidad, igual que los shims de WI-76). La diferencia con WI-76 es
que aquí la mitad **sí** está verificada: no es un falso éxito, es una red
a medio coser. Un nombre de columna mal puesto en uno de los cuatro
pasaría hoy inadvertido.

## 3. Hallazgo lateral: el docstring de `StoredBudget.to_dict` miente

El docstring dice:

> "Serializa a dict preservando **todas** las columnas"

El método devuelve **3 de las 6**:

```python
return {
    "max_visits": self.max_visits,
    "max_runtime_seconds": self.max_runtime_seconds,
    "max_events": self.max_events,
}
```

Omite `tenant_id`, `project_id` y `run_id`.

**No se corrige aquí.** No hay consumidor que diga cuál de las dos cosas
es la correcta: un UPDATE puede acotarse con la identidad y no
necesitarla en el payload, y eso sería legítimo. Cambiar el código
cambia el contrato; cambiar el docstring borra la contradicción sin
resolverla. Conforme al criterio ya usado en este repo (un hallazgo
semántico se fija con test y se reporta como decisión de producto), el
test fija **el comportamiento real** y la contradicción se reporta.

## 4. Corrección aplicada

`tests/test_wi78_dto_serialization.py`, 13 tests, sin tocar `src/`:

- **4 roundtrip** para los DTO que faltaban, con la misma forma que los
  existentes: se fija el nombre histórico de columna
  (`object_literal_json`, `content_json`, `payload_json`), el tipo de
  `stale` (`int`, no `bool`) y el round-trip por `json.loads`.
- **1 test explícito del caso raro**:
  `test_budget_to_dict_returns_only_the_three_limits` afirma el
  comportamiento real y además que `run_id` / `tenant_id` /
  `project_id` **no** están. Si alguien "arregla" el método añadiendo las
  seis claves, el test lo delata en vez de dejar que el docstring gane en
  silencio.
- **4 tests de compat dict**: `get(key, default)` devuelve el default y
  el valor real, y `__getitem__` lanza `KeyError` con clave desconocida.
- **4 tests de serializabilidad**: la salida de `to_dict()` tiene que
  sobrevivir a `json.dumps`, que es como se emite.

## 5. Verificación en ambos sentidos

| mutación | resultado |
|---|---|
| `object_literal_json` → `object_literal` (nombre legacy equivocado) | **1 failed** en el roundtrip del claim |
| `StoredBudget.to_dict` añade las 3 claves de identidad que hoy omite | **1 failed** en el test del caso raro |
| `get()` devuelve `None` en vez del default | **2 failed** en los tests de compat |

Cada mutación la caza el test escrito para ella.

## 6. Lo que queda abierto

- `StoredBudget.to_dict`: decidir si el docstring o el código llevan la
  razón. No es cosmético: cambia lo que un consumer dict-legacy recibe.
- `runtime/http_adapter.py` (88 %): adaptador HTTP externo, ramas de
  error de red y reintentos. No se inventan tests para subir una cifra;
  queda para decisión si se asume o se baja el umbral.
