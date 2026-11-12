"""Every process a child starts, reachable after its parents are gone (Windows; F1162).

`terminate_process_tree` walks the parent-child tree (`taskkill /T`), and that walk cannot find a
process whose parent has already exited. Stopping a Codex turn left exactly that: the app-server's
shell was gone and the command it had started was still running. A Windows job object holds every
process started inside it, whatever became of its parents, so terminating the job reaches them.

The job is created without `KILL_ON_JOB_CLOSE`: closing it ends nothing. Only `terminate()` does,
which is what a stop asks for; a turn that ends normally leaves what its agent started on purpose.

The job is not enough on its own, measured live on 2026-11-11 (Codex 0.167.1, a stop during
`py -3.11 -c ...`): the app-server's PowerShell was in the job and the `py.exe` it started was not
(it left at creation, into the job above ours), and `turn/interrupt` then ended PowerShell and
orphaned it. So a stop first ends the app-server's descendants while the tree is still whole
(`terminate_descendants`), and only then interrupts; the job and the tree walk at close catch
what started after.

POSIX needs none of this: a child started in its own session keeps every descendant in its process
group, orphans included, and `terminate_process_tree` kills the group.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


class ProcessJob:
    """A job object holding one process and everything it starts. Windows only."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    @classmethod
    def for_pid(cls, pid: Optional[int]) -> Optional["ProcessJob"]:
        """A job holding *pid*, or `None` where there is none to be had (not Windows, the process
        is gone, or the Hub's own job forbids nesting). `None` leaves the tree walk to do what it
        can; it never fails the spawn."""
        if sys.platform != "win32" or not pid:
            return None
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            logger.debug("CreateJobObjectW failed: %s", ctypes.get_last_error())
            return None
        process = kernel32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid)
        if not process:
            kernel32.CloseHandle(job)
            return None
        try:
            if not kernel32.AssignProcessToJobObject(job, process):
                logger.debug("AssignProcessToJobObject failed: %s", ctypes.get_last_error())
                kernel32.CloseHandle(job)
                return None
        finally:
            kernel32.CloseHandle(process)
        return cls(job)

    def terminate(self, exit_code: int = 1) -> None:
        """End every process in the job, then release it. Idempotent; never raises."""
        if self._handle is None:
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.TerminateJobObject(self._handle, exit_code)
        except Exception:  # noqa: BLE001 - the tree walk beside it still runs
            logger.debug("TerminateJobObject failed", exc_info=True)
        self.close()

    def close(self) -> None:
        """Release the job without ending anything in it. Idempotent; never raises."""
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            logger.debug("closing a job handle failed", exc_info=True)


def _process_table() -> Dict[int, Tuple[int, int]]:
    """`{pid: (parent pid, creation time)}` for every process this one may query. Windows only."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    parents: Dict[int, int] = {}
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    table: Dict[int, Tuple[int, int]] = {}
    for pid, parent in parents.items():
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                table[pid] = (parent, (created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            kernel32.CloseHandle(handle)
    return table


def descendants(root: int, table: Optional[Dict[int, Tuple[int, int]]] = None) -> List[int]:
    """Every live process descended from *root*, by recorded parent pid. A pid counts as a child
    only when it was created after its recorded parent, so a reused pid is never mistaken for one.
    Windows only; elsewhere, and on any failure, empty."""
    if sys.platform != "win32":
        return []
    try:
        table = _process_table() if table is None else table
        if root not in table:
            return []
        found: List[int] = []
        frontier = [root]
        while frontier:
            parent = frontier.pop()
            born = table[parent][1]
            for pid, (ppid, created) in table.items():
                if ppid == parent and pid != parent and created >= born and pid not in found:
                    found.append(pid)
                    frontier.append(pid)
        return found
    except Exception:  # noqa: BLE001 -- a failed walk ends nothing; the job still runs
        logger.debug("walking the process tree failed", exc_info=True)
        return []


def terminate_descendants(root: Optional[int]) -> List[int]:
    """End every process descended from *root*, leaving *root* itself running, and return their
    pids. What a stop does before it interrupts, while the tree is still whole. Never raises."""
    if not root:
        return []
    pids = descendants(root)
    if not pids:
        return []
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        # Deepest first, so no parent outlives the moment to notice its child die and start more.
        for pid in reversed(pids):
            handle = kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid)
            if handle:
                try:
                    kernel32.TerminateProcess(handle, 1)
                finally:
                    kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        logger.debug("ending a stopped turn's commands failed", exc_info=True)
    return pids
