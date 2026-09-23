---
apiVersion: skillgraph.dev/v1alpha1
kind: DecisionNode

metadata:
  name: orphan-outcomes
  namespace: software

spec:
  ctx_recipe_ref: software.implementation
---

# Falta la clave obligatoria `outcomes` en spec