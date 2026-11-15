"""Live shells, held in the Hub's memory only (FR-5, FR-7, FR-8, FR-9, FR-10).

A shell runs under a pseudo-terminal (`pty_runner.PtySession`: ConPTY on Windows, a pty on POSIX)
with a reader thread feeding its output to the event loop, where it is kept -- the last
`MAX_LINES` lines -- and sent to every attached page. Nothing is stored: a Hub restart ends every
shell, which is the decision (non-goal: a terminal that survives a reload or a restart).

**Ending a shell ends what it started.** On Windows a shell's children outlive it unless ended with
it, and an orphaned dev server holds its port. Each shell is put in a job object created with
`KILL_ON_JOB_CLOSE`, so the Hub's handle closing -- however the Hub stops, killed included -- ends
everything in it; closing a shell walks its tree while it is whole, then terminates the job, then
the tree again (`process_job`'s order, for the same reasons). A WSL shell's Linux processes are not
Windows processes: each carries `AGENTWEAVE_SHELL_ID` (passed across in `WSLENV`) and is ended
inside its distribution by that mark. On POSIX the pty child leads its own session, so killing its
process group reaches its children.

**A page owns the shells it opened.** The app holds one presence WebSocket per page load
(`/terminal/page?page=<id>`); when it goes away, the shells opened with that page id end after
`PAGE_GRACE_SECONDS`. That is what makes a reload end every shell while switching conversations --
the same page -- leaves them running. A shell opened with no page id (an API caller) is ended only
by close, Restart or Hub stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set

from ..pty_runner import PtySession, strip_ansi_escapes, terminate_process_tree
from ..subprocess_windows import no_console_kwargs
from . import shells as shell_detection
from .environment import clean_environment
from .shells import ShellOption

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
#: Open shells per conversation (FR-7).
LIMIT = 4
#: Output lines kept per shell (FR-8).
MAX_LINES = 5000
#: The most an agent reads of one shell's output (FR-12).
AGENT_READ_LINES = 500
#: A bound on what is kept when a program writes without newlines (a progress bar redrawn by `\r`).
MAX_CHARACTERS = 4 * 1024 * 1024
#: How long a page may be gone before its shells end: a reload is a new page, so this only rides
#: out a socket dropping and coming back for the same page.
PAGE_GRACE_SECONDS = 3.0
#: A shell opened for a page that never says it is there ends after this.
PAGE_ORPHAN_SECONDS = 30.0
SHELL_MARK = "AGENTWEAVE_SHELL_ID"
DEFAULT_SIZE = (24, 80)  # rows, cols

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x20
_NORMAL_PRIORITY_CLASS = 0x20
#: Priority classes below normal (`GetPriorityClass`): idle and below-normal.
_BELOW_NORMAL_CLASSES = (0x40, 0x4000)
#: The processes ConPTY starts to host a pseudo-console, as children of the Hub.
_CONSOLE_HOSTS = ("openconsole.exe", "conhost.exe")


class LimitReachedError(Exception):
    def __init__(self) -> None:
        super().__init__(
            f"Limit of {LIMIT} reached: a conversation can have at most {LIMIT} open shells. "
            "Close one to open another."
        )


class OutputBuffer:
    """The last `MAX_LINES` lines of a shell's output, as it was written (escape sequences kept, so
    a page attaching later redraws it)."""

    def __init__(self, max_lines: int = MAX_LINES, max_characters: int = MAX_CHARACTERS) -> None:
        self.max_lines = max_lines
        self.max_characters = max_characters
        self._chunks: Deque[str] = deque()
        self._newlines = 0
        self._characters = 0

    def append(self, text: str) -> None:
        if not text:
            return
        self._chunks.append(text)
        self._newlines += text.count("\n")
        self._characters += len(text)
        self._trim()

    def _trim(self) -> None:
        while self._chunks and (
            self._newlines > self.max_lines or self._characters > self.max_characters
        ):
            first = self._chunks[0]
            excess_lines = self._newlines - self.max_lines
            excess_chars = self._characters - self.max_characters
            cut = 0
            if excess_lines > 0:
                position = -1
                for _ in range(excess_lines):
                    position = first.find("\n", position + 1)
                    if position == -1:
                        break
                cut = len(first) if position == -1 else position + 1
            if excess_chars > 0:
                cut = max(cut, min(len(first), excess_chars))
            if cut >= len(first):
                self._chunks.popleft()
            else:
                self._chunks[0] = first[cut:]
            removed = first[:cut]
            self._newlines -= removed.count("\n")
            self._characters -= len(removed)

    def text(self) -> str:
        return "".join(self._chunks)

    def lines(self, limit: Optional[int] = None) -> List[str]:
        """The kept output as plain lines (escape sequences stripped), the last *limit* of them."""
        plain = strip_ansi_escapes(self.text()).replace("\r\n", "\n").replace("\r", "\n")
        rows = plain.split("\n")
        if rows and rows[-1] == "":
            rows.pop()
        return rows[-limit:] if limit else rows


def _kill_on_close_job(pid: int) -> Any:
    """A job holding *pid* that ends everything in it when its last handle closes: the Hub
    stopping, however it stops, ends the shell's tree. `None` where none can be had."""
    from ..process_job import ProcessJob

    job = ProcessJob.for_pid(pid)
    if job is None:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class _ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimits),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        info = _ExtendedLimits()
        # An operator's shell answers at interactive priority whatever the Hub runs at: a Hub
        # started below normal (a project check gives way, `project_checks.py`) would otherwise
        # hand it on, and PowerShell under ConPTY then takes tens of seconds to answer a line.
        info.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_PRIORITY_CLASS
        )
        info.BasicLimitInformation.PriorityClass = _NORMAL_PRIORITY_CLASS
        if not kernel32.SetInformationJobObject(
            job._handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            logger.debug("SetInformationJobObject failed: %s", ctypes.get_last_error())
    except Exception:  # noqa: BLE001 - the job still ends the tree on close; Hub stop ends it too
        logger.debug("could not mark the shell's job kill-on-close", exc_info=True)
    return job


def _raise_console_hosts() -> None:
    """Raise this process's below-normal console hosts to normal priority. Windows only.

    ConPTY starts the host drawing a shell's screen as a child of the Hub, not inside the shell's
    job, so the job's priority limit does not reach it; a host left below normal starves the shell
    it draws. Every host the Hub owns is an operator's shell's, so raising one is never wrong."""
    try:
        import ctypes
        import os
        from ctypes import wintypes

        class _Entry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == wintypes.HANDLE(-1).value:
            return
        hosts: List[int] = []
        try:
            entry = _Entry()
            entry.dwSize = ctypes.sizeof(_Entry)
            more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                if (
                    entry.th32ParentProcessID == os.getpid()
                    and entry.szExeFile.lower() in _CONSOLE_HOSTS
                ):
                    hosts.append(entry.th32ProcessID)
                more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        for pid in hosts:
            # PROCESS_SET_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION
            handle = kernel32.OpenProcess(0x0200 | 0x1000, False, pid)
            if not handle:
                continue
            try:
                if kernel32.GetPriorityClass(handle) in _BELOW_NORMAL_CLASSES:
                    kernel32.SetPriorityClass(handle, _NORMAL_PRIORITY_CLASS)
            finally:
                kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - the shell still works, only slower
        logger.debug("could not raise the shells' console hosts", exc_info=True)


def _end_wsl_processes(distribution: str, shell_id: str) -> None:
    """End every process in *distribution* carrying this shell's mark. Blocking."""
    script = (
        "for p in /proc/[0-9]*; do "
        f"if tr '\\000' '\\n' < \"$p/environ\" 2>/dev/null | grep -qx '{SHELL_MARK}={shell_id}'; "
        'then kill -9 "${p##*/}" 2>/dev/null; fi; done; exit 0'
    )
    try:
        subprocess.run(
            [shell_detection._wsl_exe(), "-d", distribution, "--", "sh", "-c", script],
            capture_output=True,
            timeout=20,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("could not end %s's processes in %s", shell_id, distribution, exc_info=True)


@dataclass
class Shell:
    id: str
    project_id: str
    conversation_id: str
    option: ShellOption
    location: str  # "worktree" | "root"
    path: Path
    directory: str  # as the shell prints it
    page: Optional[str]
    created_at: float = field(default_factory=time.time)
    buffer: OutputBuffer = field(default_factory=OutputBuffer)
    exit_code: Optional[int] = None
    running: bool = True
    closed: bool = False
    size: tuple = DEFAULT_SIZE
    _pty: Optional[PtySession] = None
    _job: Any = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _subscribers: Set[asyncio.Queue] = field(default_factory=set)

    @property
    def label(self) -> str:
        return self.option.label

    @property
    def pid(self) -> Optional[int]:
        return self._pty.pid if self._pty is not None else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "shell": self.option.id,
            "label": self.option.label,
            "wsl": self.option.wsl,
            "location": self.location,
            "directory": self.directory,
            "running": self.running,
            "exit_code": self.exit_code,
            "page": self.page,
            "created_at": self.created_at,
        }

    def agent_view(self) -> Dict[str, Any]:
        """What the conversation's agent reads of this shell (FR-12): plain text, nothing it could
        act on -- no id, since no agent route takes one."""
        return {
            "name": self.option.label,
            "wsl": self.option.wsl,
            "location": self.location,
            "directory": self.directory,
            "running": self.running,
            "exit_code": self.exit_code,
            "lines": self.buffer.lines(AGENT_READ_LINES),
        }

    # ------------------------------------------------------------------ the process

    def start(self, env: Dict[str, str]) -> None:
        """Spawn the shell and its reader. Blocking; call off the loop."""
        argv = shell_detection.launch_argv(self.option, self.path)
        self._pty = PtySession.spawn(argv, cwd=str(self.path), env=env, dimensions=self.size)
        if IS_WINDOWS:
            self._job = _kill_on_close_job(self._pty.pid)
            _raise_console_hosts()
        threading.Thread(target=self._read, name=f"terminal-{self.id}", daemon=True).start()

    def _read(self) -> None:
        pty = self._pty
        assert pty is not None
        while True:
            try:
                chunk = pty.read(8192)
            except Exception:  # noqa: BLE001 - the pty went away under the reader
                chunk = ""
            if not chunk:
                break
            self._deliver(self._on_output, chunk)
        code: Optional[int] = None
        for _ in range(50):
            try:
                if not pty.isalive():
                    code = pty.exitstatus
                    break
            except Exception:  # noqa: BLE001
                break
            time.sleep(0.1)
        self._deliver(self._on_exit, code)

    def _deliver(self, callback, value) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        # RuntimeError: the loop closed between the check and the call.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(callback, value)

    def _on_output(self, chunk: str) -> None:
        self.buffer.append(chunk)
        self._publish({"type": "output", "data": chunk})

    def _on_exit(self, code: Optional[int]) -> None:
        if not self.running:
            return
        self.running = False
        self.exit_code = code
        self._publish({"type": "exit", "code": code})

    # ------------------------------------------------------------------ attachments

    def subscribe(self) -> "asyncio.Queue[Optional[str]]":
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _publish(self, message: Optional[Dict[str, Any]]) -> None:
        frame = json.dumps(message) if message is not None else None
        for queue in list(self._subscribers):
            queue.put_nowait(frame)

    def write(self, data: str) -> None:
        # Known limitation (F1177): Git Bash under ConPTY intermittently drops the first key typed
        # after xterm's focus report (ESC [ I), e.g. after a resize. Dropping the report did not
        # stop it, so the bytes are passed through unchanged.
        if self.running and self._pty is not None and data:
            try:
                self._pty.write(data)
            except Exception:  # noqa: BLE001 - it ended between the check and the write
                logger.debug("write to shell %s failed", self.id, exc_info=True)

    def resize(self, rows: int, cols: int) -> None:
        rows, cols = max(2, min(int(rows), 500)), max(10, min(int(cols), 1000))
        self.size = (rows, cols)
        if self.running and self._pty is not None:
            try:
                self._pty.resize(rows, cols)
            except Exception:  # noqa: BLE001
                logger.debug("resize of shell %s failed", self.id, exc_info=True)

    # ------------------------------------------------------------------ ending

    def terminate_tree(self) -> None:
        """End the shell and every process it started. Blocking; idempotent; never raises."""
        pty, pid = self._pty, self.pid
        try:
            if self.option.kind == "wsl" and self.option.distribution:
                _end_wsl_processes(self.option.distribution, self.id)
            if IS_WINDOWS and pid:
                from ..process_job import terminate_descendants

                terminate_descendants(pid)
            if self._job is not None:
                self._job.terminate()
                self._job = None
            if pid:
                terminate_process_tree(pid, force=True)
            if pty is not None:
                with contextlib.suppress(Exception):  # already gone
                    pty.terminate(force=True)
        except Exception:  # noqa: BLE001
            logger.warning("ending shell %s's processes failed", self.id, exc_info=True)

    def mark_closed(self) -> None:
        self.closed = True
        if self.running:
            self.running = False
        self._publish({"type": "closed"})
        self._publish(None)


class Registry:
    """Every live shell of this Hub, and the pages that own them."""

    def __init__(self) -> None:
        self._shells: Dict[str, Shell] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._pages: Dict[str, int] = {}
        self._page_timers: Dict[str, asyncio.TimerHandle] = {}
        self._last_pick: Optional[Dict[str, str]] = None

    def _guard(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ------------------------------------------------------------------ reads

    def get(self, shell_id: str) -> Optional[Shell]:
        return self._shells.get(shell_id)

    def for_conversation(self, project_id: str, conversation_id: str) -> List[Shell]:
        return sorted(
            (
                s
                for s in self._shells.values()
                if s.project_id == project_id and s.conversation_id == conversation_id
            ),
            key=lambda s: s.created_at,
        )

    def all(self) -> List[Shell]:
        return list(self._shells.values())

    @property
    def last_pick(self) -> Optional[Dict[str, str]]:
        return dict(self._last_pick) if self._last_pick else None

    # ------------------------------------------------------------------ open, close, restart

    async def open(
        self,
        *,
        project_id: str,
        conversation_id: str,
        option: ShellOption,
        location: str,
        path: Path,
        page: Optional[str] = None,
        size: Optional[tuple] = None,
        replacing: Optional[Shell] = None,
    ) -> Shell:
        """Start a shell, or raise `LimitReachedError` -- before any process exists."""
        async with self._guard():
            # A page that has gone (its grace still running) has already lost its shells as far as
            # the operator can tell: end them now so they neither count toward the limit nor
            # outlive the reload that a fresh shell is opening after.
            for gone in [
                s
                for s in self.for_conversation(project_id, conversation_id)
                if s.page
                and s.page != page
                and s.page not in self._pages
                and s.page in self._page_timers
            ]:
                await self.close(gone)
            open_now = [
                s for s in self.for_conversation(project_id, conversation_id) if s is not replacing
            ]
            if len(open_now) >= LIMIT:
                raise LimitReachedError()
            shell_id = "term-" + secrets.token_hex(6)
            directory = await asyncio.to_thread(shell_detection.shown_directory, option, path)
            shell = Shell(
                id=shell_id,
                project_id=project_id,
                conversation_id=conversation_id,
                option=option,
                location=location,
                path=path,
                directory=directory,
                page=page,
                size=size or DEFAULT_SIZE,
            )
            if replacing is not None:
                shell.created_at = replacing.created_at
            shell._loop = asyncio.get_running_loop()
            await asyncio.to_thread(shell.start, self._environment(option, shell_id))
            self._shells[shell_id] = shell
            self._last_pick = {"option_id": option.id, "location": location}
        if page and page not in self._pages:
            self._schedule_page_end(page, PAGE_ORPHAN_SECONDS)
        return shell

    @staticmethod
    def _environment(option: ShellOption, shell_id: str) -> Dict[str, str]:
        env = clean_environment()
        env.update(dict(option.extra_env))
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env[SHELL_MARK] = shell_id
        if option.kind == "wsl":
            key = next((k for k in env if k.upper() == "WSLENV"), "WSLENV")
            entries = [e for e in env.get(key, "").split(":") if e]
            env[key] = ":".join([*entries, f"{SHELL_MARK}/u"])
        return env

    async def close(self, shell: Shell) -> None:
        self._shells.pop(shell.id, None)
        await asyncio.to_thread(shell.terminate_tree)
        shell.mark_closed()

    async def restart(self, shell: Shell) -> Shell:
        """The same shell in the same place, as a new process; the old one and its tree end."""
        self._shells.pop(shell.id, None)
        await asyncio.to_thread(shell.terminate_tree)
        try:
            fresh = await self.open(
                project_id=shell.project_id,
                conversation_id=shell.conversation_id,
                option=shell.option,
                location=shell.location,
                path=shell.path,
                page=shell.page,
                size=shell.size,
                replacing=shell,
            )
        finally:
            shell.mark_closed()
        return fresh

    async def end_all(self) -> None:
        """Hub stop: every shell and everything it started."""
        shells, self._shells = list(self._shells.values()), {}
        for handle in self._page_timers.values():
            handle.cancel()
        self._page_timers.clear()
        if shells:
            await asyncio.gather(
                *(asyncio.to_thread(s.terminate_tree) for s in shells), return_exceptions=True
            )
        for s in shells:
            s.mark_closed()

    # ------------------------------------------------------------------ pages

    def page_arrived(self, page: str) -> None:
        self._pages[page] = self._pages.get(page, 0) + 1
        handle = self._page_timers.pop(page, None)
        if handle is not None:
            handle.cancel()

    def page_left(self, page: str) -> None:
        count = self._pages.get(page, 0) - 1
        if count > 0:
            self._pages[page] = count
            return
        self._pages.pop(page, None)
        self._schedule_page_end(page, PAGE_GRACE_SECONDS)

    def _schedule_page_end(self, page: str, delay: float) -> None:
        loop = asyncio.get_running_loop()
        previous = self._page_timers.pop(page, None)
        if previous is not None:
            previous.cancel()
        self._page_timers[page] = loop.call_later(
            delay, lambda: asyncio.ensure_future(self._end_page(page))
        )

    async def _end_page(self, page: str) -> None:
        self._page_timers.pop(page, None)
        if page in self._pages:
            return
        owned = [s for s in self._shells.values() if s.page == page]
        for shell in owned:
            await self.close(shell)
        if owned:
            logger.info("The page %s went away; ended its %d shell(s)", page, len(owned))


registry = Registry()
