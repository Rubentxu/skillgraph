---
apiVersion: skillgraph.dev/v1alpha1
kind: DecisionNode

metadata:
  namespace: software

spec:
  ctx_recipe_ref: software.implementation
  outcomes:
    - name: ONLY
      next: somewhere
---

# Falta metadata.name