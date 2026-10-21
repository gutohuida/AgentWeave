"""Projects x Runners & models sweep 2026-10-21, API phases (scratch Hub :8158, profile p1021).
Reuses the 2026-10-20 drive (`s1020_p_api.py`) with this drive's state file and project.

    block <n>  -- F806 re-drive: list/open/create/relocate a UNC path on a fresh blackholed host
                  (10.255.255.<n>..<n+3>; Windows caches a failed host, so each needs its own)
                  while timing GET /health
    listing    -- GET /projects while a registered project's folder is a UNC path on a dead host

    AW_P=<project> py -3.11 scripts/drive/s1021_p_api.py block 31
"""

import os
import sys
import threading
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-p1021.json")
sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import s1020_p_api as base  # noqa: E402
from s1020_p_lib import P, req  # noqa: E402


def block(n):
    n = int(n)
    base.fs_block("\\\\10.255.255.%d\\share" % n)
    base.blocking(
        "POST /projects/open",
        lambda: req("POST", "/projects/open", {"path": "\\\\10.255.255.%d\\share\\proj" % (n + 1)}),
    )
    base.blocking(
        "POST /projects/create",
        lambda: req("POST", "/projects/create", {"path": "\\\\10.255.255.%d\\share\\new" % (n + 2)}),
    )
    base.blocking(
        f"POST /projects/{P}/relocate",
        lambda: req("POST", f"/projects/{P}/relocate", {"path": "\\\\10.255.255.%d\\share\\p" % (n + 3)}),
    )


def listing():
    """Time GET /projects (every project's directory refreshed) against /health."""
    for _ in range(3):
        started = time.time()
        status, res = req("GET", "/projects")
        print(f"GET /projects -> {status} in {time.time() - started:.2f}s, {len(res) if isinstance(res, list) else res}")
    base.blocking("GET /projects", lambda: req("GET", "/projects")[0])


if __name__ == "__main__":
    phase = sys.argv[1]
    if phase == "block":
        block(*sys.argv[2:])
    elif phase == "listing":
        listing()
    else:
        raise SystemExit(f"unknown phase {phase}")
    threading.Event().wait(0)
