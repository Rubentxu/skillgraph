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

  transitions:
    SUCCEEDED: verify-evidence
    FAILED: recovery
    BLOCKED: propose-expansion
---

# Caracterizar comportamiento

Directiva semántica.