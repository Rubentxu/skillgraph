"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.domain.dsl` instead. This module
    will be removed in a future major release.
"""

from skillgraph.domain.dsl import *  # noqa: F403
from skillgraph.domain.dsl import __all__ as __all__
