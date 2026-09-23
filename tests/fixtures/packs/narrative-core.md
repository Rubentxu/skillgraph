---
apiVersion: skillgraph.dev/v1alpha1
kind: DomainPack

metadata:
  name: narrative-core
  namespace: shared

spec:
  version: 1.0.0
  capabilities:
    - name: create-character
      entrypoint: narrative.create-character
    - name: relate-character-to-arc
      entrypoint: narrative.relate-character-to-arc
  types:
    - kind: Character
      schema:
        required: [name, archetype]
        fields:
          name: string
          archetype: string
          backstory: string
          relations:
            refs:
              - StoryArc
    - kind: StoryArc
      schema:
        required: [title, premise]
        fields:
          title: string
          premise: string
          acts:
            list_of: string
          characters:
            refs:
              - Character
---

# Narrative Core Domain Pack

Tipados extensibles para UAT-12 (H6 multiprosito):

- Character: nombre + arquetipo + backstory opcional.
- StoryArc: titulo + premisa + lista de actos + refs a Character.

Las refs son estructurales: NO se valida FK aqui (responsabilidad
del motor). El pack solo declara el esquema.
