"""Which executables are on PATH, remembered (D4 of
`turn-starts-approvals-and-evidence-never-freeze-the-hub`).

`shutil.which` walks every PATH directory and every PATHEXT suffix: 3-6 ms per name on the
operator's machine, paid by every launchability listing, queue-status read and turn start, on
the event loop. Whether `claude` is installed does not change between two requests, so the answer
is kept, keyed by the name and the PATH it was looked up on, for `TTL_SECONDS` -- and dropped at
once when a runner is created, changed or removed (`forget`), which is when an operator who just
installed or pinned a CLI looks again.

**Under WSL a Windows copy is not the runner** (F1195). WSL appends the Windows PATH, so an
npm-installed `codex` shim under `/mnt/c/...` can come before the Linux binary, and launching it
fails every turn at once (`node: not found`, exit 127). On Linux, candidates under `/mnt/<drive>/`
are skipped and the search goes on (`native_which`); `windows_copy` names one when it is all there
is, so launchability can say why. Windows and macOS are untouched.

A replaced `shutil.which` (a test's patch) is always asked directly: its answer is not a fact
about this machine, and keeping it would outlive the patch.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from typing import Dict, Optional, Tuple

TTL_SECONDS = 60.0

_REAL_WHICH = shutil.which
_found: Dict[Tuple[str, str, str], Tuple[float, Optional[str]]] = {}
_lock = threading.Lock()


_WINDOWS_DRIVE = re.compile(r"^/mnt/[A-Za-z](/|$)")


def _linux() -> bool:
    return sys.platform.startswith("linux")


def _on_a_windows_drive(path: Optional[str]) -> bool:
    return bool(path) and _linux() and _WINDOWS_DRIVE.match(path) is not None


def native_which(name: str) -> Optional[str]:
    """`shutil.which(name)`, except that on Linux a copy under `/mnt/<drive>/` is passed over for
    the next one on PATH. Not remembered: the spawn path asks it too."""
    found = shutil.which(name)
    if not _on_a_windows_drive(found):
        return found
    kept = [
        d for d in os.environ.get("PATH", "").split(os.pathsep) if not _on_a_windows_drive(d + "/")
    ]
    return shutil.which(name, path=os.pathsep.join(kept))


def windows_copy(name: str) -> Optional[str]:
    """The Windows copy of *name* PATH finds, where that is the only one (Linux only)."""
    found = shutil.which(name)
    if _on_a_windows_drive(found) and native_which(name) is None:
        return found
    return None


def which(name: str) -> Optional[str]:
    """`native_which(name)`, remembered as described above."""
    if shutil.which is not _REAL_WHICH:
        return native_which(name)
    key = (name, os.environ.get("PATH", ""), os.environ.get("PATHEXT", ""))
    now = time.monotonic()
    with _lock:
        hit = _found.get(key)
    if hit is not None and now - hit[0] < TTL_SECONDS:
        return hit[1]
    value = native_which(name)
    with _lock:
        if len(_found) > 512:
            _found.clear()
        _found[key] = (now, value)
    return value


def forget() -> None:
    """Look every name up again next time: a runner was created, changed or removed."""
    with _lock:
        _found.clear()
