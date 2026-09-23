"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.domain.pack_loader` instead. This module
    will be removed in a future major release.
"""

from skillgraph.domain.pack_loader import *  # noqa: F403
from skillgraph.domain.pack_loader import __all__ as __all__
