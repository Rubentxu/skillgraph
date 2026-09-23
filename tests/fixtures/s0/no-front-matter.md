apiVersion: skillgraph.dev/v1alpha1
kind: DecisionNode

metadata:
  name: no-front-matter
  namespace: software

spec:
  ctx_recipe_ref: software.implementation
  outcomes:
    - name: ONLY
      next: somewhere

# Sin delimitadores `---` al principio