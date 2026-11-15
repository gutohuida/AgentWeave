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


def install_kind() -> str:
    """How this Hub was installed: `pip` (a built release), `editable` or `checkout`.

    Only `pip` may be upgraded by the app (spec `agentweave-updates-itself`, FR-9). An install
    records where it came from in `direct_url.json`; a `dir_info.editable` entry is an editable
    install, and any other direct URL (a local path or VCS) is not a published release. No
    metadata at all means the code runs straight from a checkout.
    """
    import json

    try:
        from importlib.metadata import distribution

        dist = distribution("agentweave-hub")
    except PackageNotFoundError:
        return "checkout"
    raw = dist.read_text("direct_url.json")
    if not raw:
        return "pip"
    try:
        info = json.loads(raw)
    except ValueError:
        return "checkout"
    if (info.get("dir_info") or {}).get("editable"):
        return "editable"
    return "checkout" if "url" in info else "pip"
