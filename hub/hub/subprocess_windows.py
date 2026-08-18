"""Windows console-window suppression, shared by every subprocess spawn in this package.

The Hub is a windowed desktop app on Windows (see `native_dialog.py`, `cli.py`'s pywebview
window) — any child process spawned without `CREATE_NO_WINDOW` gets its own console, which
Windows briefly flashes on screen before the child exits. `pty_runner.py`'s ConPTY/pipe spawns
already handled this; every other spawn site in `hub/hub/` did not, so routine background work
(a git call, a conversation title, a launchability probe) visibly interrupted the operator.

Every `subprocess.run`/`Popen`/`asyncio.create_subprocess_exec`/`create_subprocess_shell` call in
`hub/hub/` must pass `**no_console_kwargs()`. `test_no_console_flash.py` statically enforces this
so a new bare spawn cannot creep back in unnoticed.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict

IS_WINDOWS = sys.platform == "win32"


def no_console_kwargs() -> Dict[str, Any]:
    """Extra kwargs that suppress a console window flash on Windows.

    `creationflags` is accepted identically by `subprocess.run`, `subprocess.Popen`,
    `asyncio.create_subprocess_exec`, and `asyncio.create_subprocess_shell` — one helper covers
    every spawn call in the package. Empty (a no-op) off Windows, where child processes never
    open a console of their own.
    """
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
