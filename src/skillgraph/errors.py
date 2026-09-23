"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.core.errors` instead. This module
    will be removed in a future major release.
"""

from skillgraph.core.errors import *  # noqa: F403
from skillgraph.core.errors import __all__ as __all__
