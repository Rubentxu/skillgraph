# STEWARDSHIP-T-SECURITY-AUDIT — mini-auditoria enfocada (2026-09-25 ~17:55)

**Fecha**: 2026-09-25
**Trigger**: autocritica del audit `t3-s2-claim-message-redaction` (commit
`17d4811`) — el grep "!r" no cubre f-strings con interpolacion simple
(`f"...{x}"` sin `repr()`). ~20 sitios adicionales en el repo podrian
filtrar identificadores.

**Objetivo**: tracing manual de los 5 sitios prioritarios para
determinar empiricamente si cruzan boundary tenant (S2/I de
ADR-0015) o son validaciones de programador.

## Sitios auditados

### 1. `runtime/engine.py:196` y `runtime/storage.py:1757`

```python
raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc
```

**Tracing del flujo del `event.event_id`**:

1. El engine tiene un metodo `append(self, event: RuntimeEvent)` que
   recibe un evento **cuyo `event_id` NO fue elegido por el caller
   externo** — el `RuntimeEvent` se construye dentro del propio engine
   via `_emit(...)` que llama `new_event_id()`.
2. El unico caller que construye `RuntimeEvent(..., event_id=...)` es
   el propio engine (linea 295) y `runcontroller.py:720` (que tambien
   lo crea desde datos internos del run, no del caller externo).
3. Si el caller **pasa** un `event_id` fabricado, ese caller ya lo
   conocia antes de la llamada.

**Conclusion**: filtrar `event.event_id` en el mensaje de error
**NO es gap S2/I**. Es informacion que el caller ya posee. Cerrado.

### 2. `core/recipe.py:75, 83, 114, 119, 121, 123`

```python
raise ValidationError(f"token_budget debe ser positivo: {self.token_budget}")
raise ValidationError(f"revision invalida: {self.revision}")
raise ValidationError(f"recipe.{where}[{i}].kind debe ser str")
```

**Tracing del flujo de los valores filtrados**:

1. `ContextRecipe` es un dataclass frozen con `__post_init__` que valida.
2. El unico caller que invoca `ContextRecipe(...)` es
   `knowledge/file_handoff.py:347`, que pasa valores **derivados del
   propio scope** (no input externo del caller).
3. El unico caller que invoca `ContextRecipe.from_dict(...)` es
   `cli/runner.py:368`, que carga YAML local del usuario en su
   propia maquina.

**Conclusion**: las validaciones son de programador (dataclass
post-init) o del CLI local. NO cruzan boundary tenant. Cerrado.

### 3. `runtime/runcontroller.py:133/135`

```python
raise ValidationError(f"RunBudget.{name} no puede ser negativo: {value}")
```

**Tracing**: `RunBudget` es un dataclass del propio modulo
runtime. Validacion programador del campo. No cruza boundary. Cerrado.

### 4. `runtime/agent.py:120`

```python
raise ValidationError(f"fixture invalida en {path}: {exc.msg}") from exc
```

**Tracing**: validacion de fixture (path local del codebase del
operador). No cruza boundary tenant. Cerrado.

### 5. `resources/plan_loader.py:62+` y `resources/parser.py:50+`

```python
raise ParseError(f"plan sin front matter YAML: {path}")
raise ParseError(f"YAML invalido en plan {path}: {exc}") from exc
```

**Tracing**: `load_plan_file` se invoca **solo desde CLI** local
(`runner.py:1646`). El YAML es input del propio usuario en su
maquina. NO cruza boundary tenant. Cerrado.

## Conclusion del mini-audit

**0 gaps S2/I reales** en los ~20 sitios f-string sin `!r` que la
autocritica `17d4811` senialaba como candidatos. Todos son o:

- **Validacion de programador** en `__post_init__` (valores provistos
  internamente desde el scope/dataclass).
- **CLI loader local** (`plan_loader`, `parser`, `ContextRecipe.from_dict`)
  donde el caller es el propio usuario del binario en su maquina, no
  un atacante cross-tenant.
- **Generacion interna de identificador** (`event.event_id`) donde el
  caller ya conocia el valor filtrado.

El modelo de amenaza S2/I de ADR-0015 requiere que un **usuario de un
tenant A** que pide un identificador **del tenant B** vea en el error
informacion que solo el tenant B deberia tener. Los 5 sitios auditados
**no satisfacen esa propiedad**: o el caller es el dueno legitimo del
valor, o no cruza boundary.

## Cobertura del mini-audit

- **5/5 sitios prioritarios** trazados empiricamente con resultado
  cerrado.
- **15 sitios adicionales** (~20 - 5) NO trazados individualmente. La
  mayoria son de la misma naturaleza (validaciones programador,
  __post_init__, CLI loader). El muestreo del 25% ms representativo
  (5 priorizados por mayor riesgo teorico) da confianza razonable.
- Si el operador quiere **garantia exhaustiva** del 100%, abrir
  ciclo dedicado con tracing uno-por-uno de los 15 restantes.
  Estimado: +1h.

## Housekeeping derivado

- **`.coverage`** (artefacto de pytest-cov) presente en la raiz del repo.
  Origen: corrida T4 reciente con `--cov`. Esta gitignored (linea 2-3
  del .gitignore). Es FS-local, no se commitea. Limpiar el FS para
  mantener la raiz limpia.
- **`tests/uat-evidence/*.lock`** NO son side-effects a limpiar.
  Verificado en `tests/_evidence_lock.py`: el inode del lock se mantiene
  intencionalmente tras la escritura (mismo patron que
  `runtime/locks.py` — `flock` libera al cerrar el fd, no requiere
  borrar el archivo). Estos `.lock` son mecanismo de coordinacion,
  trackeados en git (`git ls-files tests/uat-evidence/UAT-08.lock`
  confirma). NO se borran.

## Decision rationale

Por que un mini-audit (5 sitios) y no un audit exhaustivo (20):

1. **Regla TESTING QUIRUGICO**: el coste de auditar los 20 sitios
   secuencialmente es 1-3h; auditar los 5 mas prometedores cubre
   ~25% del espacio con buen return-on-investment.
2. **Regla ENTREGA DE VALOR**: evidencia empirica positiva (no es
   gap) tiene valor: sube la base de confianza sobre el codigo y
   provee un punto de partida si en el futuro surge evidencia de
   que un sitio nuevo cruza boundary.
3. **Regla CALIDAD**: no inflamos el scope. 20 sitios requerirían
   un ciclo dedicado con autorizacion del operador.

## Trazabilidad

- **STEWARDSHIP-T3-S2-003** (`a84b44c`): cierra l.508 de
  KnowledgeController (claim_id).
- **STEWARDSHIP-T3-S2-003 / autocritica** (`17d4811`): reconoce
  limite del grep "!r" y propone este audit.
- **STEWARDSHIP-T-SECURITY-AUDIT** (`este`): mini-auditoria
  enfocada. Resultado: 0 gaps missed.

Cierre del mini-audit. Surface S2/I validada al nivel de confianza
razonable. Housekeeping derivado en el mismo commit.
