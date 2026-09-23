"""Core bounded context of SkillGraph.

Pure types and errors that have no dependency on infrastructure,
storage, runtime, or any other bounded context. This is the rock
on which the rest of the codebase is built.

Modules in this subpackage:

- :mod:`skillgraph.core.errors` — Domain exception hierarchy.
- :mod:`skillgraph.core.runtime_types` — Closed ADTs (node kinds,
  run states, claim predicates, source kinds, finding results).
- :mod:`skillgraph.core.recipe` — ContextRecipe declaration and
  validation.

Backward compatibility: every module here is also re-exported from
its legacy top-level location (``skillgraph.errors``, etc.) so
existing imports keep working unchanged.

New code SHOULD import from :mod:`skillgraph.core` to make the
bounded context explicit. Legacy imports will be removed in a
future major version.
"""
