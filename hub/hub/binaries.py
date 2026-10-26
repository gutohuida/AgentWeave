"""Which executables are on PATH, remembered (D4 of
`turn-starts-approvals-and-evidence-never-freeze-the-hub`).

`shutil.which` walks every PATH directory and every PATHEXT suffix: 3-6 ms per name on the
operator's machine, paid by every launchability listing, queue-status read and turn start, on
the event loop. Whether `claude` is installed does not change between two requests, so the answer
is kept, keyed by the name and the PATH it was looked up on, for `TTL_SECONDS` -- and dropped at
once when a runner is created, changed or removed (`forget`), which is when an operator who just
installed or pinned a CLI looks again.

A replaced `shutil.which` (a test's patch) is always asked directly: its answer is not a fact
about this machine, and keeping it would outlive the patch.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from typing import Dict, Optional, Tuple

TTL_SECONDS = 60.0

_REAL_WHICH = shutil.which
_found: Dict[Tuple[str, str, str], Tuple[float, Optional[str]]] = {}
_lock = threading.Lock()


def which(name: str) -> Optional[str]:
    """`shutil.which(name)`, remembered as described above."""
    if shutil.which is not _REAL_WHICH:
        return shutil.which(name)
    key = (name, os.environ.get("PATH", ""), os.environ.get("PATHEXT", ""))
    now = time.monotonic()
    with _lock:
        hit = _found.get(key)
    if hit is not None and now - hit[0] < TTL_SECONDS:
        return hit[1]
    value = _REAL_WHICH(name)
    with _lock:
        if len(_found) > 512:
            _found.clear()
        _found[key] = (now, value)
    return value


def forget() -> None:
    """Look every name up again next time: a runner was created, changed or removed."""
    with _lock:
        _found.clear()
