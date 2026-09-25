# Auditoría S2/I — sitios `warnings.warn` en `src/skillgraph`

**Fecha**: 2026-09-26
**WorkItem**: STEWARDSHIP-T-WARNINGS-AUDIT
**Trigger**: El audit `T-SECURITY-AUDIT-FULL` (`21a096d`, 2026-09-25) cubrió
exhaustivamente los sitios `raise .*Error(f"...{...}...")`, pero enumeró como
follow-up explícito: "Auditar mensajes `WARNING` y `INFO` (este audit fue solo
sobre `raise .*Error`)". Esta auditoría cierra ese follow-up.

**Modelo de amenaza aplicado (ADR-0015)**: un sitio es gap S2/I si filtra
**un identificador cross-tenant** (`source_id`, `entity_id`, `claim_id`,
`event_id`, `run_id`, `uid`, `proposal_id`, etc.) **en un mensaje que llega a
un caller que NO aportó ese identificador**. Si el caller ya tenía ese valor
en su scope, no es leak.

## Inventario completo (3 sitios)

`rg -n "warnings\.warn\(" src/skillgraph/` arrojó exactamente **3 sitios** en
código de producto (más una mención en docstring de `errors.py:125` que NO es
sitio f-string y por tanto queda fuera del alcance).

| # | Sitio | Warning | Identificadores en mensaje | Veredicto |
|---|---|---|---|---|
| 1 | `knowledge/knowledge_invalidator.py:128-133` | `HopLimitExceededWarning` | `max_hops` (param caller) + `len(current_frontier)` (cardinalidad) | **NO gap** |
| 2 | `knowledge/knowledge_controller.py:115-119` | `StaleKnowledgeWarning` | `source.source_id` (caller lo acaba de pasar en `register_source`) | **NO gap** |
| 3 | `core/errors.py:125` | (docstring) | (N/A) | N/A (no es sitio f-string) |

**Verificación de exhaustividad**: `rg -n "import logging|from logging" src/skillgraph`
dio **0 matches**. El codebase SkillGraph **no usa `logging` estándar de Python
ni `structlog`**. La CLI escribe directamente a stdout/stderr con `print(...)` y
los warnings no fatales usan `warnings.warn(...)`. No hay, por tanto, un tercer
canal de output a auditar.

## Trazabilidad empírica uno-por-uno

### Sitio 1 — `HopLimitExceededWarning` (`knowledge_invalidator.py:128`)

```python
warnings.warn(
    f"max_hops={max_hops} alcanzado con frontier no vacia: "
    f"{len(current_frontier)} claims sin explorar",
    HopLimitExceededWarning,
    stacklevel=2,
)
```

**Callers**:
- `invalidate_from_source` (línea 95+ del mismo módulo), invocado por:
  - `KnowledgeController.invalidate_from_source` (mismo bounded context).
  - Tests programador (`tests/test_knowledge_invalidation.py:194, 285`).

**Análisis**:
- `max_hops` es un parámetro que el caller introdujo en su llamada a
  `invalidate_from_source(max_hops=N)`. El caller ya lo conoce.
- `len(current_frontier)` es **cardinalidad** (un entero, no un ID).
  ADR-0015 marca como gap "filtrar IDs cross-tenant" — un conteo no es
  un identificador (no se puede usar para enumerar recursos cross-tenant).
- El traversal BFS trabaja sobre claims del propio tenant por construcción
  (`KnowledgeController` filtra por `self.tenant_id` en cada `get_claim`).

**Veredicto**: **NO gap**. Cumple ADR-0015: filtra cardinalidad + parámetro
caller-provided, NO identificadores.

### Sitio 2 — `StaleKnowledgeWarning` (`knowledge_controller.py:115`)

```python
def register_source(self, *, source: Source) -> SourceID:
    existing = self.storage.get_source(
        tenant_id=self.tenant_id,
        project_id=self.project_id,
        source_id=source.source_id,
    )
    if existing is not None and existing.freshness != "fresh":
        warnings.warn(
            f"re-registrando source stale: {source.source_id!r}",
            StaleKnowledgeWarning,
            stacklevel=2,
        )
```

**Callers**:
- Programador que invoca `KnowledgeController.register_source(source=...)`.
- `register_source` recibe `source.source_id` como parte del argumento `Source`
  que el caller acaba de construir o pasar al controller.
- Test: `tests/test_knowledge_controller.py:307` (`test_register_stale_source_emits_warning`).

**Análisis**:
- El `source.source_id` filtrado en el mensaje es **idéntico** al que el caller
  pasó en `source.source_id` un milisegundo antes. El caller ya lo tiene en su
  scope.
- El warning se emite **dentro** de `KnowledgeController` cuyo `self.tenant_id`
  está fijado en `__init__`. No hay boundary que cruzar.
- **Asimetría con `get_source`** (línea 134-137): cuando un lookup de source
  arbitrario falla, el código **deliberadamente omite** el `source_id` del
  mensaje (`UnknownSourceError("Source no encontrada")` con comentario `# NO
  expone source_id (S2/I)`). Esto es correcto porque en `get_source` el caller
  introduce un `source_id` que NO tiene por qué existir (lookup arbitrario),
  y filtrar el id que buscó filtra información cross-tenant. En `register_source`
  la situación es distinta: el caller YA pasó ese id exitosamente al storage
  (la línea 120 ejecuta `self.storage.register_source(...)` justo después del
  warning, lo que demuestra que el id es válido y pertenece al propio tenant
  del caller).

**Veredicto**: **NO gap**. Mismo principio que `storage.py:446` (uid en
`IdentityConflictError`) y `storage.py:1265/1405` (run_id en `NotFoundError`):
el caller ya tenía el identificador en su scope.

### Sitio 3 — `errors.py:125` (docstring)

```python
class SkillGraphWarning(UserWarning):
    """Raiz de los warnings no fatales de SkillGraph.
    ...
    Vive como `UserWarning` para que `warnings.warn()` la trate como warning
    estandar de Python (visible con `-W error::UserWarning` si se quiere
    estricto).
    """
```

**Análisis**: NO es un sitio f-string (es texto de docstring). Fuera del
alcance del modelo ADR-0015.

**Veredicto**: **N/A**.

## Verificación adicional: CLI prints

Para eliminar complacencia, se ejecutó un grep transversal sobre todos los
`print(f"...")` en `cli/runner.py` que mencionan identificadores:

- `runner.py:165` — `print(f"Proyecto {args.name!r} creado en: {db}")`: `args.name`
  lo pasó el operador en la CLI. Caller-provided.
- `runner.py:180` — `print(f"{p['name']}\t{p['db_path']}\t{p['created_at']}")`:
  datos del proyecto del propio operador (CLI local).
- `runner.py:209` — `print(f"Tenant:   {project['tenant_id']}")`: tenant del
  propio proyecto del operador.
- `runner.py:310` — `print(f"stale claims ({len(stale)}):")`: cardinalidad.
- `runner.py:312` — `print(f"  - {c.claim_id} ...")` : claim_id del propio
  tenant del operador (CLI local, list-stale).
- `runner.py:328` — `print(f"  - {cid}")` (knowledge invalidate): claim_id
  devuelto por la operación que el operador acaba de invocar.
- `runner.py:385` — `print(f"--- context_hash: {handoff.context_hash}")`:
  hash generado para el handoff del propio run del operador.
- `runner.py:906-908, 939-943, 975-979` — `sg runs list/show/logs`: IDs de
  runs del propio operador (CLI local).
- `runner.py:1241-1243, 1280-1281, 1478-1479` — `sg domain-pack` /
  `sg brick` / `sg expansion submit`: UIDs y proposal_ids del propio
  operador.

**Análisis**: todos estos prints son **CLI local** (el operador introduce
su propio tenant/project/run_id/source_id en su sesión interactiva). Igual
que en `T-SECURITY-AUDIT-FULL` §"Sitios secundarios — verificación
transversal", se considera caller-provided y por tanto NO gap.

## Endurecimiento de tests (parte del ciclo)

Los 3 tests que ya verificaban los warnings (solo el TIPO, no el contenido)
se han endurecido con `pytest.warns(match=...)` para que cualquier regresión
futura que filtrara un identificador no caller-provided sea cazada:

```python
# tests/test_knowledge_invalidation.py:194 (endurecido)
with pytest.warns(HopLimitExceededWarning, match=r"max_hops=1.*frontier"):
    invalidated = ctl.invalidate_from_source(source_id="local:a", max_hops=1)

# tests/test_knowledge_invalidation.py:285 (endurecido)
with pytest.warns(HopLimitExceededWarning, match=r"max_hops=1.*frontier"):
    ctl.invalidate_from_source(source_id="local:a", max_hops=1)

# tests/test_knowledge_controller.py:307 (endurecido)
with pytest.warns(StaleKnowledgeWarning, match=r"re-registrando source stale:"):
    ctl.register_source(source=_src(freshness="stale"))
```

Esto convierte los 3 tests de "verifica tipo" a "verifica tipo + contenido".
Si en el futuro alguien cambia el formato del mensaje (e.g. para añadir un
identificador cross-tenant real), el test fallará y exigirá justificación
explícita.

**Commit**: `5cda0c0 test(security): harden warning content matchers per ADR-0015`
(2 archivos, +15/-4 LoC, 27/27 PASS en módulos afectados, ruff limpio en
archivos modificados).

## Resultado

**0 gaps S2/I en los 3 sitios `warnings.warn`** (los 2 reales + el docstring
fuera de alcance).

Combinado con el audit previo `T-SECURITY-AUDIT-FULL` (43 sitios en
`raise .*Error`), el repositorio SkillGraph está **100% conforme con
ADR-0015** para f-strings y warnings en código de producto.

| Round | Sitios tratados | Gaps reales | Estado |
|---|---|---|---|
| STEWARDSHIP-T3-S2-001 | 3 (`source_id` en `raise`) | 3 | cerrado `dcbf81a` |
| STEWARDSHIP-T3-S2-002 | 2 (`entity_id` en `raise`) | 2 | cerrado `eac6838` |
| STEWARDSHIP-T3-S2-003 | 1 (`claim_id` en `raise`) | 1 | cerrado `a84b44c` |
| T-SECURITY-AUDIT (mini) | 5 (`raise` misc.) | 0 | cerrado `244ddf3` |
| T-SECURITY-AUDIT-FULL | 38 restantes (`raise`) | 0 | cerrado `21a096d` |
| **T-WARNINGS-AUDIT (este)** | **3 (`warnings.warn`)** | **0** | **cerrado `5cda0c0`** |

## Limitaciones reconocidas (autocrítica)

1. **No audito los prints de CLI uno-por-uno**. El grep transversal
   identificó 14+ sitios con `print(f"...{identificador}...")` pero todos
   son caller-provided por construcción (el operador introduce su propio
   tenant/project/ids en la sesión CLI). El audit `T-SECURITY-AUDIT-FULL`
   ya documentó el mismo principio ("Sitios secundarios — verificación
   transversal"). Si en el futuro se introduce un caller automático que
   invoca la CLI con datos cross-tenant, este audit queda invalidado y
   requiere re-evaluación (Gap E trigger).

2. **No audito `print` desde `__str__`/`__repr__` de dataclasses**. Las
   dataclasses frozen pueden filtrar IDs al imprimirse. Sin embargo, las
   13 ADT cerradas del proyecto (`Source`, `Entity`, `Claim`, `Evidence`,
   `Finding`, `OutcomeTrace`, etc.) tienen `__repr__` trivial (delegado a
   `dataclasses`) que filtra TODOS los campos. Esto es un trade-off
   deliberado del proyecto: el operador local NECESITA ver los IDs para
   poder operar (`sg knowledge list-stale` lista claim_ids). El modelo
   ADR-0015 no se aplica a `__repr__` de ADT propias del tenant del
   operador. Si en el futuro se serializan ADT cross-tenant (e.g. para
   un endpoint HTTP multi-tenant), reconsiderar.

3. **No audito mensajes `__cause__` chain en excepciones**. Esto sí lo cubrió
   el ciclo `STEWARDSHIP-T3-S2-002` (`eac6838`, gaps entity_id chain).
   Los 2 sitios chain de `get_entity` se cerraron con tests específicos.

## Próximos pasos derivados (opcionales, sin gap actual)

1. Si se introduce `structlog` o `logging` en el futuro (e.g. para T6
   Observabilidad del ROADMAP), re-auditar aplicando este mismo inventario.
2. Si se introduce un caller HTTP/API multi-tenant, re-evaluar los 14+
   prints de CLI y los 3 warnings.warn de este audit.
3. Si se cambia `register_source` para aceptar `source_id` derivados
   (no caller-provided), re-auditar el sitio 2.
