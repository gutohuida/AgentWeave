"""Windows console-window suppression, shared by every subprocess spawn in this package.

The Hub is a windowed desktop app on Windows (see `native_dialog.py`, `cli.py`'s pywebview
window) — any child process spawned without `CREATE_NO_WINDOW` gets its own console, which
Windows briefly flashes on screen before the child exits. `pty_runner.py`'s pipe spawns already
handled this; every other spawn site in `hub/hub/` did not, so routine background work (a git
call, a conversation title, a launchability probe) visibly interrupted the operator.

Every `subprocess.run`/`Popen`/`asyncio.create_subprocess_exec`/`create_subprocess_shell` call in
`hub/hub/` must pass `**no_console_kwargs()`. `test_no_console_flash.py` statically enforces this
so a new bare spawn cannot creep back in unnoticed.

The ConPTY spawn in `pty_runner.PtySession` cannot take a creation flag — pywinpty makes that
`CreateProcess` call itself — and needs `ensure_windowless_console()` instead. See there.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict

IS_WINDOWS = sys.platform == "win32"

logger = logging.getLogger(__name__)

_console_lock = threading.Lock()


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


def has_console() -> bool:
    """True when this process is attached to a console, windowed or not."""
    if not IS_WINDOWS:
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_ids = (ctypes.c_ulong * 1)()
    # Returns the number of processes attached to this process's console, and 0 — failure —
    # when there is no console at all. That failure is the answer being asked for.
    return bool(kernel32.GetConsoleProcessList(process_ids, 1))


def ensure_windowless_console() -> None:
    """Attach this process to a console that has no window, if it has no console at all.

    pywinpty's ConPTY backend begins every spawn with `AllocConsole()` followed by
    `ShowWindow(GetConsoleWindow(), SW_HIDE)` (winpty-rs `src/pty/conpty/pty_impl.rs`), for the
    case of a parent with no console. A natively started Hub is exactly that case, and on Windows
    11 the console `AllocConsole` creates is handed to the default terminal — Windows Terminal —
    whose window the `ShowWindow` call cannot reach. So every agent turn opened a terminal window
    that flashed up and stayed, and pywinpty's matching `FreeConsole` on teardown left the Hub
    without a console again for the next turn to repeat it: one window per message (F341).

    `AllocConsole` fails harmlessly when a console is already attached, and pywinpty then frees
    nothing, because it frees only a console it allocated. So the fix is to hold one: a console
    created with `CREATE_NO_WINDOW` never has a window and is never handed to a terminal. We
    borrow a helper's — started `CREATE_NO_WINDOW`, attached to with `AttachConsole`, and told to
    exit — and keep it, since a console lives as long as any process is attached to it.

    Idempotent and thread-safe, and a no-op off Windows or when a console is already attached
    (an interactive launch, or `agentweave` starting the Hub with `CREATE_NO_WINDOW`).

    Never raises. If no console can be borrowed the spawn still goes ahead — a window flashing is
    better than an agent turn that cannot start — but it says so in the log, because otherwise the
    only sign that F341 has come back is the window it opens.
    """
    if not IS_WINDOWS:
        return
    with _console_lock:
        if has_console():
            return
        import ctypes

        # `cmd.exe` because it is a console-subsystem program on every Windows install:
        # `sys.executable` may be `pythonw.exe`, a GUI program, for which `CREATE_NO_WINDOW` is
        # ignored and no console is created to borrow. `/k` with a piped stdin reads commands
        # until end of input, so closing the pipe is what lets it exit.
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        try:
            helper = subprocess.Popen(
                [comspec, "/d", "/q", "/k"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            logger.warning(
                "No windowless console for ConPTY spawns: could not start %s (%s). Each agent "
                "turn may open a terminal window (F341).",
                comspec,
                exc,
            )
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        last_error = 0
        try:
            # The helper's console exists once `CreateProcess` returns, so the first attempt
            # normally succeeds; the retries only absorb a scheduler hiccup.
            for _ in range(20):
                if kernel32.AttachConsole(helper.pid):
                    return
                last_error = ctypes.get_last_error()
                time.sleep(0.025)
            logger.warning(
                "No windowless console for ConPTY spawns: AttachConsole to helper %s failed "
                "(Windows error %s). Each agent turn may open a terminal window (F341).",
                helper.pid,
                last_error,
            )
        finally:
            if helper.stdin is not None:
                helper.stdin.close()
            try:
                helper.wait(timeout=5)
            except subprocess.TimeoutExpired:
                helper.kill()
