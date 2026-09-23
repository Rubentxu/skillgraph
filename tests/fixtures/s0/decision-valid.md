---
apiVersion: skillgraph.dev/v1alpha1
kind: DecisionNode

metadata:
  name: select-implementation
  namespace: software

spec:
  ctx_recipe_ref: software.implementation
  outcomes:
    - name: EXISTING_SOLUTION
      next: implement-minimal-change
    - name: MISSING_EVIDENCE
      next: investigate-behavior
    - name: UNCOVERED_PROBLEM
      next: propose-expansion
---

# Seleccionar implementación

Texto Markdown de directiva semántica. No debe afectar la identidad
estructural del brick.