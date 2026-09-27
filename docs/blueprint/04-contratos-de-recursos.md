# Contratos declarativos Markdown/YAML

## 1. Regla general

El YAML define la estructura interpretable por el núcleo.

El Markdown define instrucciones, preguntas o contenido
semántico asociado al recurso.

El cuerpo Markdown no puede aumentar permisos,
modificar rutas ni alterar contratos estructurales.

## 2. DecisionNode

```markdown
---
apiVersion: skillgraph.dev/v1alpha1
kind: DecisionNode

metadata:
  name: select-implementation
  namespace: software

spec:
  inputs:
    - name: goal
      type: core.GoalRef
      required: true

    - name: evidence
      type: core.EvidenceBundleRef
      required: true

  contextRecipeRef: software.implementation

  outcomes:
    - name: EXISTING_SOLUTION
      next: implement-minimal-change

    - name: MISSING_EVIDENCE
      next: investigate-behavior

    - name: UNCOVERED_PROBLEM
      next: propose-expansion

  controllerRef: core.decision
---

# Seleccionar implementación

## Pregunta

¿Qué alternativa satisface el objetivo
y conserva las restricciones aplicables?

## Directiva

Evalúa las alternativas con la evidencia recibida.

Devuelve uno de los outcomes declarados,
sus motivos y las referencias a la evidencia.

No ejecutes cambios de producción.
```

## 3. ActionNode

```markdown
---
apiVersion: skillgraph.dev/v1alpha1
kind: ActionNode

metadata:
  name: characterize-behavior
  namespace: software

spec:
  inputs:
    - name: target
      type: core.EntityRef
      required: true

  outputs:
    - name: characterization
      type: core.EvidenceBundleRef

  capabilities:
    - workspace.read
    - tests.run

  transitions:
    SUCCEEDED: verify-evidence
    FAILED: recovery
    BLOCKED: propose-expansion
---

# Caracterizar comportamiento

## Directiva

Inspecciona el recorrido observable y ejecuta
las pruebas de caracterización autorizadas.

Registra entradas, salidas, efectos, errores
y comportamientos desconocidos.

No modifiques código de producción.
```

La hoja expresa una directiva firme.

Una precondición ausente se devuelve como resultado
tipado; no se transforma dentro de la hoja en una
nueva decisión arquitectónica.

## 4. DomainPack mínimo

```markdown
---
apiVersion: skillgraph.dev/v1alpha1
kind: DomainPack

metadata:
  name: narrative-basic
  namespace: shared

spec:
  version: 1.0.0

  capabilities:
    - name: review-story
      entrypoint: narrative.review-root

  requiredTypes: []

  extensions: []
---

# Narrative Basic

Revisa la coherencia narrativa de un manuscrito
a partir de los personajes, acontecimientos
y decisiones editoriales aplicables.
```

Un Domain Pack mínimo puede funcionar como
comportamiento encapsulado.

La asimilación posterior puede descomponerlo
en bricks especializados.

## 5. ContextRecipe

```yaml
apiVersion: skillgraph.dev/v1alpha1
kind: ContextRecipe

metadata:
  name: implementation-context
  namespace: software

spec:
  required:
    - task.goal
    - behavior.contract
    - applicable_decisions
    - target_slice
    - target_slice.contracts

  optional:
    - related_component_summaries

  onStaleRequiredKnowledge: REFRESH_OR_BLOCK
  onBudgetOverflow: SPLIT_OR_BLOCK

  includeConversationHistory: false
```

## 6. Result

```yaml
resultVersion: 1

identity:
  runId: run-001
  nodeExecutionId: node-exec-001
  attempt: 1

outcome:
  type: SUCCEEDED

outputs:
  characterization: evidence-bundle-001

evidenceRefs:
  - evidence-001

discoveries:
  knowledgeProposals: []
  graphExpansionProposals: []
  unresolvedQuestions: []
```

## 7. Validaciones obligatorias

- apiVersion reconocida.
- kind registrado.
- Identidad única en el ámbito.
- Campos obligatorios presentes.
- Tipos de entrada y salida válidos.
- Referencias existentes y autorizadas.
- Outcomes y transiciones definidos.
- Ausencia de destinos implícitos.
- Ausencia de ciclos no acotados.
- Compatibilidad de versiones.
- Capacidades permitidas.
- Extensiones ejecutables expresamente autorizadas.

Un recurso inválido no puede activarse.

## 8. Semántica de versiones

resourceVersion identifica revisiones operativas.

generation cambia cuando cambia la especificación.

Las definiciones reutilizables publicadas poseen
una revisión inmutable.

observedGeneration registra la generación que
ha procesado el controlador.

No asumir que una revisión del documento
equivale a una revisión del código fuente
que el agente está analizando.
