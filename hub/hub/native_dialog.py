"""Native OS folder-choice dialog (composer/chrome refinement §7, design.md Decision 4).

Windows only, for now — "Windows first, since that is the operator's platform. ...
Platform support is a capability the Hub reports, not a promise it makes."

The dialog runs as a short-lived Python subprocess, not a thread hosting a blocking Tk
mainloop: a subprocess can be terminated cleanly on timeout; a thread cannot be killed
from the outside without corrupting process state. `tkinter` is the standard library
(ships with the official Windows Python installer) — no new dependency, matching every
other choice in this codebase.
"""

from __future__ import annotations

import asyncio
import ctypes
import sys
from dataclasses import dataclass
from typing import Literal, Optional

DEFAULT_TIMEOUT_SECONDS = 120.0

_CHOSEN_PREFIX = "CHOSEN:"
_CANCELLED_MARKER = "CANCELLED"
_UNAVAILABLE_PREFIX = "UNAVAILABLE:"

# Runs in a fresh interpreter, isolated from the Hub's own event loop and any Tk state
# a prior call left behind. Printed markers, not exit codes, distinguish outcomes — Tk
# itself can exit 0 whether the operator chose a path or cancelled.
_DIALOG_SCRIPT = f"""
import sys
try:
    import tkinter
    from tkinter import filedialog
except Exception as exc:
    print("{_UNAVAILABLE_PREFIX}" + str(exc))
    sys.exit(0)
try:
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title="Choose a project folder", mustexist=True)
    root.destroy()
except Exception as exc:
    print("{_UNAVAILABLE_PREFIX}" + str(exc))
    sys.exit(0)
if path:
    print("{_CHOSEN_PREFIX}" + path)
else:
    print("{_CANCELLED_MARKER}")
"""

Outcome = Literal["chosen", "cancelled", "timeout", "unavailable", "failed"]


@dataclass
class DialogResult:
    outcome: Outcome
    path: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class AvailabilityResult:
    available: bool
    reason: Optional[str] = None


class DialogBusyError(RuntimeError):
    """Raised when a dialog is already open — the caller must not open a second one."""


def is_supported_platform() -> bool:
    return sys.platform == "win32"


def _has_interactive_desktop() -> bool:
    """False in a non-interactive window station (a Windows service in Session 0, most
    container configurations) — the same technique .NET's own `Environment.UserInteractive`
    uses, via ctypes (stdlib), not a new dependency."""
    if not is_supported_platform():
        return False
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwinsta = user32.GetProcessWindowStation()
        if not hwinsta:
            return False
        uoi_flags = 1
        wsf_visible = 0x0001

        class _UserObjectFlags(ctypes.Structure):
            _fields_ = [("fInherit", ctypes.c_int), ("fReserved", ctypes.c_int), ("dwFlags", ctypes.c_ulong)]

        info = _UserObjectFlags()
        needed = ctypes.c_ulong(0)
        ok = user32.GetUserObjectInformationW(
            hwinsta, uoi_flags, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(needed)
        )
        if not ok:
            return False
        return bool(info.dwFlags & wsf_visible)
    except Exception:
        return False


def check_availability() -> AvailabilityResult:
    if not is_supported_platform():
        return AvailabilityResult(
            available=False,
            reason=f"The native folder dialog is only supported on Windows (this Hub is running on {sys.platform!r}).",
        )
    if not _has_interactive_desktop():
        return AvailabilityResult(
            available=False,
            reason="No interactive desktop session is available to this Hub process "
            "(for example, running as a background service or in a container).",
        )
    return AvailabilityResult(available=True)


_lock = asyncio.Lock()


async def open_folder_dialog(*, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> DialogResult:
    """Open the host's native folder dialog and await its result.

    Raises `DialogBusyError` immediately (no subprocess spawned) if a dialog is already
    open — the caller decides how to report that (§8: the second request's own terms, not
    silently queued behind the first).
    """
    availability = check_availability()
    if not availability.available:
        return DialogResult(outcome="unavailable", detail=availability.reason)

    if _lock.locked():
        raise DialogBusyError("A folder dialog is already open")

    async with _lock:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            _DIALOG_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return DialogResult(outcome="timeout", detail=f"No response within {timeout_seconds}s")

        if proc.returncode != 0:
            detail = stderr.decode("utf-8", "replace").strip() or f"exit code {proc.returncode}"
            return DialogResult(outcome="failed", detail=detail)

        output = stdout.decode("utf-8", "replace").strip()
        if output.startswith(_CHOSEN_PREFIX):
            return DialogResult(outcome="chosen", path=output[len(_CHOSEN_PREFIX) :])
        if output == _CANCELLED_MARKER:
            return DialogResult(outcome="cancelled")
        if output.startswith(_UNAVAILABLE_PREFIX):
            return DialogResult(outcome="unavailable", detail=output[len(_UNAVAILABLE_PREFIX) :])
        return DialogResult(outcome="failed", detail=f"Unexpected dialog output: {output!r}")
