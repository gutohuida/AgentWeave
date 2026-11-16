"""Kill a process tree from a drive without ever ending a process that is not ours (F1197 suspect).

The old drive cleanup read the process table with `Get-CimInstance` (seconds), walked
`ParentProcessId` from remembered pids, and ran `taskkill /PID <pid> /T /F` on each result. On
Windows an exited pid is reused, and an orphan's ParentProcessId can name a reused pid, so that
cleanup could end an unrelated process -- the real Hub's `git checkout` among them.

This module reuses `hub/hub/process_job.py` (its table carries (parent pid, creation time), and a
child counts only when it was created no earlier than its recorded parent), and ends a process
only through a handle opened *after* checking that its creation time is the one the snapshot saw.
Loaded by file path: a drive must not depend on how `hub` resolves on sys.path.
"""

from __future__ import annotations

import ctypes
import importlib.util
import pathlib
import sys
from ctypes import wintypes

_SPEC = importlib.util.spec_from_file_location(
    "_aw_process_job",
    pathlib.Path(__file__).resolve().parents[2] / "hub" / "hub" / "process_job.py",
)
assert _SPEC is not None and _SPEC.loader is not None
process_job = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = process_job  # `from __future__ import annotations` needs it registered
_SPEC.loader.exec_module(process_job)

Table = dict[int, tuple[int, int]]

_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _filetime_now() -> int:
    ft = wintypes.FILETIME()
    ctypes.WinDLL("kernel32").GetSystemTimeAsFileTime(ctypes.byref(ft))
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


# Anything a drive started has a creation time at or after this; a remembered pid older than it is
# somebody else's, whatever number it carries.
DRIVE_START = _filetime_now() if sys.platform == "win32" else 0


def snapshot() -> Table:
    """{pid: (parent pid, creation time)} -- a Toolhelp snapshot, milliseconds rather than seconds."""
    return process_job._process_table() if sys.platform == "win32" else {}


def tree(roots, table: Table | None = None, since: int | None = None) -> list[int]:
    """*roots* still present in *table* and everything under them, children before parents.

    A root created before *since* is not ours (its pid was reused) and is left out with its
    subtree. Descendants come from `process_job.descendants`, which refuses a child created
    before its parent."""
    table = snapshot() if table is None else table
    found: list[int] = []
    for root in roots:
        if root not in table or (since is not None and table[root][1] < since):
            continue
        for pid in [root, *process_job.descendants(root, table)]:
            if pid not in found:
                found.append(pid)
    return list(reversed(found))


def _created(kernel32, handle) -> int | None:
    created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not kernel32.GetProcessTimes(
        handle,
        ctypes.byref(created),
        ctypes.byref(exited),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        return None
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def kill_pids(pids, table: Table) -> list[int]:
    """End each pid through a handle, only if that process was created when *table* says it was.
    Returns the pids ended. A pid that is gone, or has become a different process, is skipped."""
    pids = [pid for pid in pids if pid in table]
    if not pids or sys.platform != "win32":
        return []
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    ended: list[int] = []
    for pid in pids:
        handle = kernel32.OpenProcess(
            _PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            continue
        try:
            if _created(kernel32, handle) == table[pid][1] and kernel32.TerminateProcess(handle, 1):
                ended.append(pid)
        finally:
            kernel32.CloseHandle(handle)
    return ended


def genuine(pids, table: Table, before: Table | None = None) -> list[int]:
    """Of *pids*, those that are the processes they appear to be in *table*.

    A pid whose creation time differs from *before*'s (when given) was reused since. A pid created
    before its recorded parent is an orphan of a dead process whose pid something else now holds,
    so the parent it names is not its parent. A parent that is gone altogether is a real orphan and
    stays: that is what a tree-walk from the parent could never reach."""
    keep = []
    for pid in pids:
        if pid not in table:
            continue
        if before is not None and (pid not in before or before[pid][1] != table[pid][1]):
            continue
        parent, created = table[pid]
        if parent in table and table[parent][1] > created:
            continue
        keep.append(pid)
    return keep


def kill_candidates(pids, before: Table | None = None) -> list[int]:
    """End each of *pids* (named by a slow CIM read or an old walk) only if `genuine`, and only it:
    no tree. *before* is a `snapshot()` taken before that read."""
    table = snapshot()
    return kill_pids(genuine(pids, table, before), table)


def kill_tree(roots, since: int | None = None, before: Table | None = None) -> list[int]:
    """End *roots* and everything under them, deepest first, touching only our own processes.

    `since` (e.g. `DRIVE_START`) drops remembered roots older than it. `before` is an earlier
    `snapshot()`, taken before the roots were read: a root counts only if it still has the creation
    time that snapshot saw. Either way a root created before its recorded parent is dropped."""
    table = snapshot()
    roots = genuine(roots, table, before)
    return kill_pids(tree(roots, table, since), table)
