# WI-81 — segunda tanda de ADR-0014: 7 alias de función sin callers

**Fecha**: 2026-10-02
**Ciclo SDDK**: `p-b7740b96d79ec013/wi-81-drop-dead-row-mapper-shims`
**Estado**: verificado
**Suite**: 2368 → **2376 passed** (2368 + 23 nuevos de WI-81 − 14 de `test_wi76_shim_execution.py` − 1 de `test_wi60`, ambos borrados con su objeto)

---

## 1. Origen: "alerta de deuda" sin verificar no es deuda

El encargo pedía priorizar deuda técnica reciente. Antes de aceptarla
como deuda, se verificó cada alerta. **Ninguna de las registradas era
deuda real de SkillGraph:**

| Alerta | Verificación | Veredicto |
|---|---|---|
| `sddk debt incs` → 50 INCs | El vault del proyecto `p-b7740b96d79ec013` tiene **0 entradas**. Los 50 están en `sddk-framework/incs` y en `p-733fb505b5a6bd2d`. Leído uno: `domain: kernel`, `status: closed`, habla de `Cargo.toml`. | **Deuda de otro proyecto.** El comando no filtra por proyecto. |
| backlog #1 — shim de `pipelinek` | El item dice 0.43.0; hoy el shim del PATH es **0.46.0** y `mise.toml` **ya fija** 0.39.0 con bake-off documentado. | **Premisa caduca**, acción ya hecha. |
| backlog #2 — `cycle supersede` | Bug del framework (event ID sin `cycle_id`). | **No accionable desde aquí.** |
| `sddk lint` → 4 errores | `schemas/`, `docs/generated/` y `manifest.toml` **nunca existieron** en el historial de git. | **Opt-ins no adoptados**, no drift ni contratos violados. |
| `audits/architecture-debt` | Autogenerado hoy: 0 god modules, 0 hotspots cc≥20, 0 anidamiento ≥5. | **Limpio.** |
| `next_workitem` (c) — 7 shims | ADR-0014 (aceptada) establece el criterio de eliminar shims de retro-compatibilidad, y su paso 8 ya está aplicado a los de módulo. Los 7 de WI-76 son la **misma deuda, segunda forma**. | **Deuda real con decisión normativa previa.** ← este workitem |

## 2. Qué eran

WI-56 (corte 3) dejó 7 alias de función en `platform/row_mappers.py`
que reenvían a `knowledge_mappers.row_to_*`. Sus docstrings decían:

> "Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
> `SqliteKnowledgeRepository.row_to_X`. **El corte 5 reubicará los
> callers.**"

El corte 5 ocurrió (ADR-0020, WI-60). Los callers se fueron al mapper
real. Los alias se quedaron, y `MAPPER_NAMES` los seguía contando: el
módulo anunciaba **12 mappers donde había 5**.

## 3. Verificación de ineria: en runtime, no por lectura

Un barrido textual habría dicho "los llama `knowledge_repository`", y
eso es un **falso positivo**: ese símbolo es un alias *local* suyo.

La pregunta correcta es si el símbolo que se resuelve **es** el alias.
Eso solo se responde con identidad de objetos:

```
knowledge_repository._row_to_source is row_mappers._row_to_source -> False
knowledge_repository._row_to_evidence ...                            -> False
knowledge_repository._row_to_stored_evidence ...                     -> False
knowledge_repository._row_to_claim ...                               -> False
knowledge_repository._row_to_stored_claim ...                        -> False
knowledge_repository._row_to_resource ...                            -> False
knowledge_repository._row_to_relation ...                            -> False
```

Los alias de `knowledge_repository.py:696-702` apuntan a
`knowledge_mappers.row_to_X`, no a estos. Y **ningún módulo de `src/`
los importaba**: `event_store.py:24` importa `_SCHEMA_SQL, Storage,
_row_to_stored_event`, y ese último es uno de los **cinco reales**.

El docstring del módulo decía "NO renombrar ni mover sin migrar
`event_store`, `policy_store` y `knowledge_repository`". Esa premisa
sigue vigente para los 5 que quedan y era **obsoleta** para estos 7.

## 4. Test rojo → fix → verde

`tests/test_wi81_dead_aliases.py`, 23 tests, escrito antes del fix.

**Rojo: 13 failed, 10 passed.** Los 10 verdes son caracterización
—muestran por qué el borrado es seguro— y deben seguir verdes después.

Un error propio durante el rojo, corregido antes de tocar `src/`: la
primera versión de `test_no_production_module_calls_it` buscaba
"quién llama a `_row_to_source`" por AST y daba 7 falsos positivos, porque
en `knowledge_repository` ese nombre resuelve al alias local. La
caracterización correcta es por identidad en runtime
(`test_callers_resolve_to_real_mapper`).

**Fix mínimo**:

- `row_mappers.py`: borradas las 7 funciones, `MAPPER_NAMES` 12 → 5,
  `__all__` actualizado, docstring del módulo con la premisa
  obsoleta sustituida por la vigente.
- `storage.py`: 7 nombres fuera del import y de `__all__`, con nota de
  por qué.
- `test_wi65`: recuento 12 → 5, import y mapper representativo
  actualizados.
- `test_wi60`: retirado `test_storage_shim_import_keeps_working`; su
  objeto era el shim.
- `test_wi76_shim_execution.py`: **borrado** (14 tests). Su premisa —
"los shims se ejecutan, no solo se inspeccionan"— quedó resuelta, y su
  objeto ya no existe. AGENTS §6.2: "o arreglas el test o lo borras".

**Verde: 23 passed.** Quirúrgico sobre consumidores: **1034 passed**
(81 ficheros que importan `platform.storage`, `event_store`,
`policy_store`, `knowledge_repository` o `knowledge_mappers`).

## 5. Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | Reintroducir un alias muerto + su entrada en `MAPPER_NAMES` | **CAZADA**, 3 failed |
| M2 | `knowledge_repository` pasa a resolver al alias (caller real) | **CAZADA**, 3 failed |

M2 es la importante: es el escenario que habríajustificado **no**
borrarlos. La red lo detecta.

### Una lección del propio script

La primera ejecución de `.pipelinek/wi81_mutate.sh` revertía cada
mutación con `git checkout -- <file>`, que restaura la versión de
**HEAD** y por tanto destruye el fix sin commitear. El control del
final del script (que exige verde con el árbol de trabajo) lo detectó:
tras las dos mutaciones el control falló con 4 failed y
`row_mappers.py` volvió a tener 12 funciones.

Restaurado desde el backup y el script corregido: revertir con `cp`
del backup, y comprobar que la mutación aplicó con `diff -q` contra el
backup en lugar de `git diff --quiet` contra HEAD. Sin el control, se
habría commitado un árbol inconsistente creyendo que las mutaciones
estaban validadas.

## 6. Lo que este workitem no hace

- **No toca el comportamiento observable.** Los 5 mappers que quedan
  siguen reexportados; `event_store` y `policy_store` no se ven
  afectados.
- **No reabre ADR-0014**: lo completa con un addendum.
- **No fuerza ningún ciclo a `CLOSED`.**

## 7. Verificación

```
CI canónica  : Pipeline finished with SUCCESS
               run 6d5e68a5-4c80-4f03-b026-3ed1317d5405
               8 StepStarted | 8 EchoOutputCaptured | 5/5 stages | 0 StepFailed
               2376 passed in 104.41s | All checks passed!
ruff check   : All checks passed!
ruff format  : 241 files already formatted
Mutaciones   : 2/2 cazadas
Quirúrgico   : 1034 passed (81 ficheros consumidores)
```
