"""The Hub's version, in a module of its own.

Kept out of the package's `__init__` so a module can import it without the package being
initialised: from the repository root a top-level `hub/` directory makes `hub` a namespace
package, and `from . import __version__` then fails (the CLI suite imports `hub.worktrees`,
which imports `traces`, from there).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # Authoritative source is hub/pyproject.toml; read it from installed
    # metadata so the number cannot drift from what was actually released.
    __version__ = _pkg_version("agentweave-hub")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+dev"
