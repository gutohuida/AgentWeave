"""Cross-platform PTY process spawn and output capture (Phase 3 task 3.4, prototype).

Decision 1 makes the Hub own agent execution directly. Spawning under a pseudo-terminal —
rather than a plain `subprocess.PIPE` — matches what T3 does (`proposal.md`: "its server
spawns the agent, owns the PTY") and preserves TTY-dependent CLI behaviour (colour,
progress indicators, prompts that check `isatty()`) that a plain pipe suppresses.

Windows has no stdlib PTY support, unlike POSIX's built-in `pty` module, so this wraps two
separate libraries behind one small interface: `pywinpty` (Windows, wraps ConPTY) and
`ptyprocess` (POSIX, wraps `pty.fork()`). Neither is importable on the other platform —
`ptyprocess` unconditionally imports `fcntl`, which does not exist on Windows — so the
platform-specific import happens only inside `PtySession.spawn()`, never at module level.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"

# Matches CSI sequences (ESC [ ... final-byte, e.g. cursor moves, mode toggles like the
# ConPTY handshake `\x1b[?9001h`) and OSC sequences (ESC ] ... BEL or ESC ] ... ST, e.g. the
# window-title-set `\x1b]0;claude\x1b\\` ConPTY emits before a child's first output). Live-
# verified against real ConPTY sessions: a spawned process's stdout is not plain text, it is
# terminal-control-sequence-laden text, and any consumer expecting to parse structured output
# (JSON lines, etc.) from it needs to strip these first, not just leading ones on the first
# chunk — control sequences can appear at any chunk boundary, e.g. a cursor-restore sequence
# ConPTY appends after a child process exits.
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-9;?]*[a-zA-Z]|\][^\x07\x1b]*(?:\x07|\x1b\\))")


def strip_ansi_escapes(text: str) -> str:
    """Remove terminal control sequences (CSI and OSC) from PTY output."""
    return _ANSI_ESCAPE_RE.sub("", text)


def resolve_executable(cmd: List[str]) -> List[str]:
    """Resolve ``cmd[0]`` to an absolute path via PATH/PATHEXT if it isn't one already.

    Mirrors the fix already applied in the watchdog's own spawn path
    (``src/agentweave/watchdog.py``, "Resolve the CLI binary to an absolute path"):
    handing a bare command name to a process launcher can fail to find `.cmd`/`.bat`
    shims on Windows (agent CLIs installed via npm, e.g. ``claude.cmd``), because shim
    resolution depends on PATHEXT, which the OS process launcher does not consult the way
    ``shutil.which`` (and ``cmd.exe``) do. Resolving first also avoids ever needing
    ``shell=True``, and the shell-injection surface that comes with it.

    Raises ``FileNotFoundError`` with a clear message if ``cmd[0]`` cannot be found.
    """
    if not cmd:
        raise ValueError("cmd must be a non-empty list")
    if Path(cmd[0]).is_absolute():
        return list(cmd)
    resolved = shutil.which(cmd[0])
    if not resolved:
        raise FileNotFoundError(f"{cmd[0]!r} was not found in PATH")
    return [resolved, *cmd[1:]]


def pid_alive(pid: int) -> bool:
    """Return whether *pid* still identifies a live process.

    Used for crash reconciliation (task 3.8): a Hub process restarted after a crash has no
    in-memory `PtySession` handle for a run that was mid-flight when it died — only the bare
    `pid` int persisted on the `Run` row — so liveness has to be checked against the OS
    directly rather than via `PtySession.isalive()`, which only works for a live handle.

    Known limitation, not solved here: this is a pid-existence check only, not a pid+identity
    check — if the Hub is down long enough for the OS to recycle *pid* onto an unrelated
    process before the Hub restarts, this returns a false "still alive." Narrow window in
    practice (pid reuse takes many process spawns), and closing it fully would need tracking
    process start time or command line, which the `Run` row doesn't carry.
    """
    if IS_WINDOWS:
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Alive but owned by another user — still alive, just not signalable by us.
            return True
        return True


def terminate_process_tree(pid: int, force: bool = True) -> None:
    """Terminate *pid* and its entire process tree so nothing is left orphaned.

    Used for task 3.9 (Hub shutdown): unlike `PtySession.terminate()`, which only signals
    the direct child pywinpty/ptyprocess wraps, this also reaches any grandchildren the
    agent CLI itself spawned (e.g. a Bash-tool subprocess) — exactly what a Hub shutting
    down cleanly must not leave running behind it.

    POSIX: a PTY child spawned via `ptyprocess.PtyProcessUnicode.spawn()` is a session
    leader (`pty.fork()` calls `setsid()`), so its process group ID equals its own pid —
    `os.killpg` reaches every process in that group. Windows has no equivalent process-group
    primitive here, so `taskkill /T` (walks the OS-recorded parent-child tree) is used
    instead — the standard idiom for this on Windows, not something pywinpty exposes itself.
    Silently no-ops if *pid* no longer exists (already dead) on either platform.
    """
    if IS_WINDOWS:
        import subprocess

        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
    else:
        import signal

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass


class PtySession:
    """A spawned process attached to a pseudo-terminal.

    Thin adapter over ``winpty.PtyProcess`` (Windows) / ``ptyprocess.PtyProcessUnicode``
    (POSIX). The two libraries expose a near-identical surface (``spawn``, ``read``,
    ``write``, ``isalive``, ``exitstatus``, ``terminate``) by the Windows library's own
    design, so one adapter covers both without reimplementing either.
    """

    def __init__(self, proc: Any) -> None:
        self._proc = proc

    @classmethod
    def spawn(
        cls,
        cmd: List[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        dimensions: Tuple[int, int] = (24, 80),
    ) -> "PtySession":
        """Resolve ``cmd`` and spawn it attached to a new pseudo-terminal.

        Raises ``FileNotFoundError`` if ``cmd[0]`` cannot be resolved to an executable.
        """
        resolved_cmd = resolve_executable(cmd)
        if IS_WINDOWS:
            import winpty

            proc = winpty.PtyProcess.spawn(resolved_cmd, cwd=cwd, env=env, dimensions=dimensions)
        else:
            import ptyprocess

            proc = ptyprocess.PtyProcessUnicode.spawn(
                resolved_cmd, cwd=cwd, env=env, dimensions=dimensions
            )
        return cls(proc)

    @property
    def pid(self) -> int:
        return self._proc.pid

    def read(self, size: int = 4096) -> str:
        """Read up to ``size`` characters of output.

        Returns ``""`` at end of stream. The two backends signal EOF differently
        (``winpty`` returns an empty read; ``ptyprocess`` raises ``EOFError``) — this
        normalizes both to an empty-string return so callers need one loop shape:
        ``while (chunk := session.read()): ...``.
        """
        try:
            chunk = self._proc.read(size)
        except EOFError:
            return ""
        return chunk or ""

    def write(self, data: str) -> None:
        self._proc.write(data)

    def isalive(self) -> bool:
        return bool(self._proc.isalive())

    @property
    def exitstatus(self) -> Optional[int]:
        return self._proc.exitstatus

    def wait(self) -> Optional[int]:
        """Block until the process exits and return its exit status."""
        self._proc.wait()
        return self._proc.exitstatus

    def terminate(self, force: bool = False) -> None:
        self._proc.terminate(force=force)
