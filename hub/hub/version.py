"""The Hub's version, in a module of its own.

Kept out of the package's `__init__` so a module can import it without the package being
initialised: from the repository root a top-level `hub/` directory makes `hub` a namespace
package, and `from . import __version__` then fails (the CLI suite imports `hub.worktrees`,
which imports `traces`, from there).
"""

import subprocess
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Dict

try:
    # Authoritative source is hub/pyproject.toml; read it from installed
    # metadata so the number cannot drift from what was actually released.
    __version__ = _pkg_version("agentweave-hub")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+dev"


def _read_checkout(root: Path) -> Dict[str, str]:
    """The commit and branch of the git checkout at `root`; empty when it is not one.

    Every failure (no `.git`, no `git` on PATH, an unreadable repository) ends quietly with
    whatever was read, so a Hub outside a checkout simply omits the fields.
    """
    if not (root / ".git").exists():
        return {}

    def git(*args: str) -> str:
        from .subprocess_windows import no_console_kwargs

        try:
            out = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **no_console_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return out.stdout.strip() if out.returncode == 0 else ""

    state: Dict[str, str] = {}
    commit = git("rev-parse", "HEAD")
    if commit:
        state["commit"] = commit
        branch = git("symbolic-ref", "--short", "-q", "HEAD")  # empty on a detached HEAD
        if branch:
            state["branch"] = branch
    return state


# Recorded once, when the Hub starts: the working tree can move on under a running Hub, and
# "behind" (spec `a-development-checkout-updates-the-same-way`) needs the commit it started from.
CHECKOUT: Dict[str, str] = _read_checkout(Path(__file__).resolve().parents[2])


def checkout_state() -> Dict[str, str]:
    """`commit` and `branch` the Hub started from; absent keys when not run from a checkout."""
    return dict(CHECKOUT)


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
    # PEP 610: `archive_info` is a built archive (a release wheel or sdist); `dir_info` and
    # `vcs_info` are a local directory or a VCS checkout.
    if "archive_info" in info:
        return "pip"
    return "checkout" if "url" in info else "pip"
