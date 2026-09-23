"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.knowledge.git_source` instead. This module
    will be removed in a future major release.
"""

from skillgraph.knowledge.git_source import *  # noqa: F403
from skillgraph.knowledge.git_source import __all__ as __all__
