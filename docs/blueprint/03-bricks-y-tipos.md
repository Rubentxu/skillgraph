# Modelo de bricks y tipos extensibles

## 1. Definición

Un brick es una unidad identificable, tipada, versionada
y relacionable que participa en conocimiento, gestión,
comportamiento, contexto o ejecución.

No todo brick contiene un prompt.

## 2. Distinción fundamental

BrickType: definición de un tipo de recurso.

Brick: instancia de un tipo registrado.

Controller: comportamiento que observa recursos y
propone operaciones para mantener su ciclo de vida.

NodeDefinition: comportamiento reutilizable.

NodeExecution: instancia concreta de una definición.

## 3. Campos estructurales comunes

Todo recurso declarativo debe tener:

- apiVersion
- kind
- metadata.name
- metadata.namespace
- spec

El núcleo genera y mantiene:

- uid
- resourceVersion
- generation
- creationTimestamp
- status, cuando sea aplicable.

Los usuarios no deben poder modificar directamente
los campos internos de estado.

La identidad de un recurso es:

tenant + scope + namespace + kind + name.

Las referencias persistentes utilizan UID y revisión
cuando se necesita una identidad histórica inmutable.

## 4. Familias

### Comportamiento

DecisionNode, ActionNode, ConditionNode,
GateNode y ControlNode.

### Composición

Subgraph, Sequence, Selector, Parallel y Join.

### Gestión

Goal, Task, Dependency, AgentProfile,
Policy y GraphExpansion.

### Conocimiento

Source, Entity, Relation, Claim, Evidence,
Contract, Rule, Finding y OutcomeTrace.

### Contexto y ejecución

ContextRecipe, Handoff, NodeExecution,
Run, Result y ExecutionReceipt.

## 5. Tipos de dominio

Un Domain Pack puede registrar tipos como:

- software.component
- software.architecture-rule
- software.quality-finding
- narrative.character
- narrative.story-arc
- learning.competency

Cada tipo debe declarar:

- Identidad y versión.
- Tipo base.
- Esquema de propiedades.
- Relaciones permitidas.
- Restricciones de validación.
- Políticas de migración, cuando sean necesarias.

No se admite que un paquete sobrescriba tipos
reservados del núcleo.

## 6. Relaciones

Cada relación define:

- Identificador.
- Tipo.
- Origen y destino.
- Ámbito.
- Propiedades.
- Revisión.
- Estado de validez, cuando aplique.

Ejemplos:

REQUIRES
DEPENDS_ON
CONSUMES
PRODUCES
SUPPORTED_BY
DERIVED_FROM
PARTICIPATES_IN
INVALIDATES
SUPERSEDES
PROPOSES
GOVERNS

No confundir relaciones descriptivas con relaciones
de control de flujo.

## 7. Subgrafos

Un subgrafo debe declarar:

- Puertos de entrada.
- Puertos de salida.
- Nodo de entrada.
- Resultados terminales.
- Dependencias.
- Límites de expansión.
- Reglas de aislamiento del estado.

Un subgrafo puede utilizarse como una unidad
dentro de otro workflow.

## 8. Principio de extensibilidad

La incorporación de tipos y relaciones nuevas
no debe requerir modificar el núcleo Python.

El comportamiento especializado puede utilizar
controladores existentes, reglas declarativas
o extensiones Python autorizadas.

## 9. Principio de compatibilidad

Una revisión nueva no modifica retroactivamente
la semántica de una ejecución anterior.

Los cambios incompatibles requieren una nueva
versión del contrato y una migración explícita.
