"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.knowledge.knowledge_invalidator` instead. This module
    will be removed in a future major release.
"""

from skillgraph.knowledge.knowledge_invalidator import *  # noqa: F403
from skillgraph.knowledge.knowledge_invalidator import __all__ as __all__
