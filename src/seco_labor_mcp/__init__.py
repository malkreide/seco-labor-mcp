"""SECO Labor Market MCP Server – Swiss Public Data Portfolio."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    # Read the version from the installed distribution metadata, which is built
    # from pyproject.toml. Hand-maintaining the literal here let the numbers
    # drift apart: pyproject said 0.3.3, this said 0.3.0. A value nobody
    # has to remember to bump cannot go stale.
    __version__ = _distribution_version("seco-labor-mcp")
except PackageNotFoundError:
    # Running from the source tree without an install (e.g. a bare checkout).
    # Deliberately not a plausible-looking number: an obviously non-release
    # marker is better than a wrong version in the User-Agent.
    __version__ = "0.0.0+source"

from .server import mcp

__all__ = ["mcp"]
