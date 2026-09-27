# Workflows dinámicos y ciclo de vida

## 1. Tres ciclos de vida

### Definición

DRAFT -> VALIDATED -> PUBLISHED -> DEPRECATED

### Ejecución

CREATED -> ACTIVE -> WAITING -> COMPLETED

También puede terminar en FAILED o CANCELLED.

### Conocimiento

UNKNOWN -> PROVISIONAL -> VERIFIED -> STALE

SUPERSEDED conserva la trazabilidad de versiones
que han sido reemplazadas.

## 2. Estados de una instancia de nodo

READY
RUNNING
WAITING
SUCCEEDED
FAILED
STOPPED
CANCELLED

Las transiciones deben estar declaradas y validadas.

Una instancia SUCCEEDED no vuelve automáticamente
a READY porque se reactive un controlador.

## 3. Algoritmo principal

```python
def reconcile_run(run_id):
    state = load_run(run_id)

    if state.is_terminal:
        return NOOP

    apply_pending_events(run_id)
    refresh_relevant_source_fingerprints(run_id)

    frontier = calculate_ready_frontier(run_id)

    if not frontier:
        if destination_verified(run_id):
            return finalize_run(run_id)

        return wait_or_stop(run_id)

    for node in select_within_budget(frontier):
        knowledge = resolve_required_knowledge(node)

        if knowledge.requires_refresh:
            schedule_refresh(node, knowledge)
            continue

        handoff = compile_handoff(node, knowledge)

        if not validate_handoff(handoff):
            stop_node(node)
            continue

        schedule_node_execution(node, handoff)

    return RUNNING
```

El código es pseudocódigo contractual, no una
implementación del runtime.

## 4. Eventos

RunCreated
NodeScheduled
HandoffCreated
NodeStarted
NodeCompleted
NodeFailed
EvidenceProduced
KnowledgeInvalidated
ProblemDiscovered
GraphExpansionProposed
GraphExpansionAccepted
GraphExpansionRejected
RunCompleted

Los eventos deben contener:

- eventId
- tenantId
- projectId
- runId, cuando proceda
- resourceRef
- causationId
- correlationId
- timestamp
- schemaVersion
- payload validado.

## 5. Expansión dinámica

DISCOVER
-> PROPOSE
-> VALIDATE
-> AUTHORIZE
-> APPLY
-> EXECUTE
-> EVALUATE

Una propuesta debe declarar:

- Problema observado.
- Evidencia.
- Revisión base.
- Operaciones mínimas.
- Nuevas dependencias.
- Capacidades necesarias.
- Alcance.
- Punto de incorporación.
- Condiciones de reversión.

## 6. Invariantes de expansión

- No reescribir resultados históricos.
- No alterar una instancia activa silenciosamente.
- No adquirir capacidades no autorizadas.
- No introducir referencias inexistentes.
- No crear dependencias circulares sin salida.
- No incorporar cambios sobre una revisión obsoleta.
- No promover automáticamente cambios locales
  a definiciones compartidas.

## 7. Presupuestos

Cada ejecución puede declarar límites de:

- Nodos activados.
- Profundidad de expansión.
- Reintentos.
- Concurrencia.
- Contexto.
- Coste del proveedor.
- Operaciones con efectos externos.

Superar un presupuesto produce WAITING o STOPPED,
no una ampliación automática del presupuesto.

## 8. Paralelismo

Solo ejecutar en paralelo trabajos cuyas dependencias
estén satisfechas y cuyos efectos sean compatibles.

Las escrituras sobre el mismo workspace necesitan
una estrategia explícita de coordinación.

## 9. Finalización

Una ejecución termina cuando:

- El destino está satisfecho.
- Los resultados obligatorios están verificados.
- No quedan trabajos imprescindibles pendientes.
- No quedan aprobaciones obligatorias abiertas.
- El estado terminal queda persistido.

No es necesario recorrer todos los nodos disponibles.
