"""Backward-compatibility shim.

.. deprecated::
    Import from :mod:`skillgraph.domain.skill_importer` instead. This module
    will be removed in a future major release.
"""

from skillgraph.domain.skill_importer import *  # noqa: F403
from skillgraph.domain.skill_importer import __all__ as __all__
