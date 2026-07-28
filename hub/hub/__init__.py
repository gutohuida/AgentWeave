"""AgentWeave Hub — FastAPI server package."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # Authoritative source is hub/pyproject.toml; read it from installed
    # metadata so the number cannot drift from what was actually released.
    __version__ = _pkg_version("agentweave-hub")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+dev"
