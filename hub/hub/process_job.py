"""Every process a child starts, reachable after its parents are gone (Windows; F1162).

`terminate_process_tree` walks the parent-child tree (`taskkill /T`), and that walk cannot find a
process whose parent has already exited. Stopping a Codex turn left exactly that: the app-server's
shell was gone and the command it had started was still running. A Windows job object holds every
process started inside it, whatever became of its parents, so terminating the job reaches them.

The job is created without `KILL_ON_JOB_CLOSE`: closing it ends nothing. Only `terminate()` does,
which is what a stop asks for; a turn that ends normally leaves what its agent started on purpose.

POSIX needs none of this: a child started in its own session keeps every descendant in its process
group, orphans included, and `terminate_process_tree` kills the group.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional

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
