# Contexto mínimo y handoff contractual

## 1. Principio

Cada agente recibe una vista suficiente y delimitada
para cumplir el contrato de su nodo.

El historial completo de conversaciones no es
el mecanismo principal de memoria.

## 2. Cuatro proyecciones

### Gestión

Objetivo, alcance, dependencias, autorizaciones
y trabajo asignado.

### Comportamiento

Directiva, pregunta, entradas, salidas, outcomes,
restricciones y criterios de éxito.

### Conocimiento

Afirmaciones, contratos, relaciones, fuentes
y evidencias necesarias para el trabajo.

### Ejecución

Identidad de run, workspace, revisión, resultados
previos aplicables y punto de continuación.

## 3. Cinco niveles de conocimiento

1. Fuentes originales.
2. Símbolos y componentes.
3. Relaciones y contratos.
4. Recorridos transversales.
5. Conocimiento y decisiones consolidadas.

No se incluyen automáticamente los cinco niveles.

La receta de contexto determina cuáles necesita
cada trabajo.

## 4. ContextRecipe

Debe especificar:

- Información obligatoria.
- Información opcional.
- Selectores de relaciones.
- Política de vigencia.
- Fuentes consultables bajo demanda.
- Presupuesto de contexto.
- Tratamiento de desbordamiento.
- Política de aislamiento.

## 5. Proceso de compilación

```text
NodeDefinition
  -> resolver contrato
  -> resolver ámbito y permisos
  -> identificar conocimiento obligatorio
  -> consultar relaciones
  -> comprobar vigencia
  -> seleccionar información
  -> materializar handoff
  -> validar presupuesto y contrato
  -> persistir handoff
  -> entregar al ejecutor
```

## 6. Contrato de handoff

```yaml
handoffVersion: 1

identity:
  tenantId: tenant-a
  projectId: project-001
  runId: run-001
  nodeExecutionId: node-exec-001

behavior:
  definitionRef: software.characterize
  definitionRevision: 3

management:
  goalRef: goal-001
  authorizedScope: research-only

knowledge:
  recipeRef: context.characterization
  included:
    - ref: slice.execution
      revision: 8
    - ref: contract.replay
      revision: 2

execution:
  workspaceRef: workspace-001
  sourceRevision: "<source-revision>"
  applicableDecisionRefs:
    - decision.preserve-contract

capabilities:
  - workspace.read
  - tests.run

expectedResult:
  schemaRef: result.characterization.v1

contextHash: "<sha256>"
```

## 7. Reglas

- El handoff materializado es inmutable.
- Su identidad y hash deben conservarse.
- Las referencias deben resolver al ámbito autorizado.
- Los contratos obligatorios no se eliminan
  para cumplir un presupuesto de tokens.
- Si falta conocimiento obligatorio, el nodo se bloquea.
- Si el conocimiento está obsoleto, se actualiza
  o se comunica explícitamente su limitación.
- Las solicitudes adicionales de contexto se registran.
- El agente no decide libremente su nodo de retorno.

## 8. Fuentes no confiables

Los archivos del proyecto, resultados de herramientas
y documentos externos se consideran datos.

Sus instrucciones no pueden modificar los permisos,
las políticas o la definición del workflow.

## 9. Evidencia de contexto

Cada resultado debe poder vincularse con:

- Handoff recibido.
- Revisión del comportamiento.
- Revisiones del conocimiento.
- Revisión del workspace.
- Identidad del agente ejecutor.
- Capacidades efectivamente autorizadas.

## 10. Hipótesis de mejora

Las consultas adicionales de los agentes pueden
originar propuestas de mejora de Context Recipes.

No se modifica una receta compartida automáticamente
por una única consulta contextual.
