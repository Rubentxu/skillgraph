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
---

# Narrative Basic

Texto libre.