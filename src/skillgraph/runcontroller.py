"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.runtime.runcontroller` instead. This module
    will be removed in a future major release.
"""

from skillgraph.runtime.runcontroller import *  # noqa: F403
from skillgraph.runtime.runcontroller import __all__ as __all__
