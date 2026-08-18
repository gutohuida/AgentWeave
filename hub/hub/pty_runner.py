"""Cross-platform agent process spawning and output capture.

Decision 1 makes the Hub own agent execution directly. Spawning under a pseudo-terminal —
rather than a plain `subprocess.PIPE` — matches what T3 does (`proposal.md`: "its server
spawns the agent, owns the PTY") and preserves TTY-dependent CLI behaviour (colour,
progress indicators, prompts that check `isatty()`) that a plain pipe suppresses.

Windows has no stdlib PTY support, unlike POSIX's built-in `pty` module, so this wraps two
separate libraries behind one small interface: `pywinpty` (Windows, wraps ConPTY) and
`ptyprocess` (POSIX, wraps `pty.fork()`). Neither is importable on the other platform —
`ptyprocess` unconditionally imports `fcntl`, which does not exist on Windows — so the
platform-specific import happens only inside `PtySession.spawn()`, never at module level.

Codex is different: ``codex exec --json`` is an explicitly non-interactive JSONL interface.
`PipeSession` therefore runs it with redirected streams and no visible Windows console instead
of attaching a ConPTY. Both adapters expose the lifecycle surface used by the Hub run manager.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .subprocess_windows import no_console_kwargs

IS_WINDOWS = sys.platform == "win32"

# Agent CLIs emit newline-delimited JSON records that can be several kilobytes long. ConPTY
# materializes visual line wrapping in its output stream: an 80-column terminal therefore turns
# one JSON record into dozens of invalid fragments before the parser sees it. Use the largest
# signed-16-bit-safe width for structured-output sessions so only the CLI's real newline separates
# records. Kept as a named value because ordinary interactive PTYs may still want a normal width.
STRUCTURED_OUTPUT_DIMENSIONS: Tuple[int, int] = (24, 32_767)

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


# An npm `.cmd` shim's payload line: one quoted executable, then `%*` and nothing else, e.g.
#   "%dp0%\node_modules\@anthropic-ai\claude-code\bin\claude.exe"   %*
# The `%*`-and-nothing-else anchor is what makes the rewrite safe. A shim that bakes in its own
# arguments — `"%dp0%\node.exe" "%dp0%\..\cli.js" %*`, the usual JS-shim shape — must not match,
# because argv[0] substitution would silently drop those arguments and launch the wrong thing.
_CMD_SHIM_PAYLOAD_RE = re.compile(
    r'^\s*(?:@?call\s+)?"(%~?dp0%\\?)?([^"]+?\.exe)"\s*%\*\s*$',
    re.IGNORECASE | re.MULTILINE,
)


def _unwrap_cmd_shim(resolved: str) -> str:
    """Resolve a Windows `.cmd`/`.bat` shim to the real `.exe` it delegates to.

    This is a correctness fix, not an optimisation. A `.cmd` is executed *by cmd.exe*, and
    cmd.exe parses its command line before the target ever sees it — so a raw newline inside
    an argument terminates the command there and everything after it is silently discarded.

    That is catastrophic here: `claude` installs via npm as `claude.CMD`, and the Hub passes
    the whole turn prompt as one `-p` argument whose first line is the tool-access notice and
    whose remaining lines are the operator's actual message. Every Claude run on Windows
    therefore received only that first notice line, and agents answered clear instructions
    with "the user hasn't given me any task yet" — the message was delivered, queued, and
    marked delivered, but never reached the model
    (`2026-08-06-hub-collaboration-and-conversation-fixes`). Spawning the `.exe` directly
    bypasses cmd.exe entirely, and argv (newlines included) arrives intact.

    Conservative by design: only a shim that forwards *all* of its arguments to one executable
    and adds none of its own is rewritten — a JS shim running `node.exe some-script.js %*`
    would lose the script path, so it is left alone, as is a shim whose target does not exist
    or that names more than one payload. Worst case is today's behaviour, never a wrong command.
    """
    try:
        content = Path(resolved).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return resolved
    matches = {(m.group(1) or "", m.group(2)) for m in _CMD_SHIM_PAYLOAD_RE.finditer(content)}
    if len(matches) != 1:
        return resolved
    prefix, target = matches.pop()
    # `%dp0%` is the shim's own directory; without it the payload is already a full path.
    candidate = Path(resolved).parent / target if prefix else Path(target)
    try:
        if candidate.is_file():
            return str(candidate.resolve())
    except OSError:
        pass
    return resolved


def resolve_executable(cmd: List[str]) -> List[str]:
    """Resolve ``cmd[0]`` to an absolute path via PATH/PATHEXT if it isn't one already.

    Handing a bare command name to a process launcher can fail to find `.cmd`/`.bat`
    shims on Windows (agent CLIs installed via npm, e.g. ``claude.cmd``), because shim
    resolution depends on PATHEXT, which the OS process launcher does not consult the way
    ``shutil.which`` (and ``cmd.exe``) do. Resolving first also avoids ever needing
    ``shell=True``, and the shell-injection surface that comes with it.

    A resolved `.cmd`/`.bat` shim is then unwrapped to the executable it delegates to, so
    arguments containing newlines survive — see ``_unwrap_cmd_shim``.

    Raises ``FileNotFoundError`` with a clear message if ``cmd[0]`` cannot be found.
    """
    if not cmd:
        raise ValueError("cmd must be a non-empty list")
    if Path(cmd[0]).is_absolute():
        resolved: Optional[str] = cmd[0]
    else:
        resolved = shutil.which(cmd[0])
    if not resolved:
        raise FileNotFoundError(f"{cmd[0]!r} was not found in PATH")
    if IS_WINDOWS and Path(resolved).suffix.lower() in (".cmd", ".bat"):
        resolved = _unwrap_cmd_shim(resolved)
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

    Second limitation, and the reason it does not bite: on POSIX `os.kill(pid, 0)` succeeds for a
    **zombie**, so a child this process killed but has not reaped still reads as alive. The single
    caller cannot reach that state — `reconcile_interrupted_runs` runs once in `lifespan()` startup,
    against pids recorded by a *previous* Hub process, whose orphans were re-parented to init and
    reaped by it; a zombie only exists for its own parent. The shutdown path
    (`terminate_all_active_runs`) kills without ever asking this function. Only a test that both
    spawns and checks occupies that window, and those reap explicitly before asserting. If a future
    caller checks liveness of a process this same Hub killed, it needs `waitpid(WNOHANG)` or a
    `/proc/<pid>/stat` state check — do not assume this function alone is enough there.
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
            **no_console_kwargs(),
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
        if IS_WINDOWS:
            # pywinpty's native reader reliably captures fast-process output in blocking
            # mode, but can remain stuck after the child exits and never close this local
            # socket. A timeout lets read() poll liveness without discarding buffered data.
            self._proc.fileobj.settimeout(0.1)

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
        while True:
            try:
                chunk = self._proc.read(size)
            except EOFError:
                return ""
            except (socket.timeout, TimeoutError):
                if IS_WINDOWS and self._proc.isalive():
                    continue
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


class PipeSession:
    """A non-interactive child process with hidden, redirected standard streams.

    Codex's ``exec --json`` command is explicitly headless and emits JSONL without a
    terminal. Giving it a ConPTY is counterproductive on Windows: it can create visible
    console chrome and turns terminal-width wrapping/control sequences into protocol
    concerns. This adapter deliberately closes stdin, merges stderr into stdout, and uses
    ``CREATE_NO_WINDOW`` on Windows while retaining the lifecycle surface used by
    ``PtySession``.
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
    ) -> "PipeSession":
        resolved_cmd = resolve_executable(cmd)
        launch_cmd = resolved_cmd
        popen_options: Dict[str, Any] = {}

        if IS_WINDOWS:
            # Some Codex installations expose an npm .cmd/.bat shim. Invoke that shim
            # through the system command processor without shell=True and hide the
            # resulting console process. Native codex.exe installations take the direct
            # branch and avoid cmd.exe entirely.
            if Path(resolved_cmd[0]).suffix.lower() in (".cmd", ".bat"):
                command_processor = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
                if not command_processor:
                    raise FileNotFoundError("Windows command processor was not found")
                launch_cmd = [
                    command_processor,
                    "/d",
                    "/s",
                    "/c",
                    subprocess.list2cmdline(resolved_cmd),
                ]
            popen_options.update(no_console_kwargs())
        else:
            # Gives the child its own process group so terminate_process_tree can stop
            # commands Codex launched as well as the direct Codex process.
            popen_options["start_new_session"] = True

        proc = subprocess.Popen(
            launch_cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **popen_options,
        )
        return cls(proc)

    @property
    def pid(self) -> int:
        return int(self._proc.pid)

    def read(self, size: int = 4096) -> str:
        if self._proc.stdout is None:
            return ""
        # JSONL producers flush at record boundaries. readline() preserves live
        # streaming; TextIO.read(size) can wait for the whole buffer before returning.
        return self._proc.stdout.readline(size) or ""

    def write(self, data: str) -> None:
        raise RuntimeError("headless pipe sessions do not accept interactive input")

    def isalive(self) -> bool:
        return self._proc.poll() is None

    @property
    def exitstatus(self) -> Optional[int]:
        return self._proc.poll()

    def wait(self) -> int:
        return int(self._proc.wait())

    def terminate(self, force: bool = False) -> None:
        if force:
            terminate_process_tree(self.pid, force=True)
        else:
            self._proc.terminate()
