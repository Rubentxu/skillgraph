"""CLI bounded context.

Entry point y comandos del CLI. La función :func:`main` y todos los
helpers se reexportan desde :mod:`skillgraph.cli.runner` para que
``from skillgraph.cli import open_catalog`` y similares sigan
funcionando como antes.
"""

from skillgraph.cli.runner import *  # noqa: F403
from skillgraph.cli.runner import __all__ as __all__
