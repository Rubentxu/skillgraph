"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.core.recipe` instead. This module
    will be removed in a future major release.
"""

from skillgraph.core.recipe import *  # noqa: F403
from skillgraph.core.recipe import __all__ as __all__
