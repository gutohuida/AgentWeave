"""The app window as Windows sees it: its taskbar identity, finding and focusing it, and its geometry.

Change `agentweave-is-its-own-app-on-windows`. Everything here goes through ctypes, because the CLI's
own code imports only the standard library (CLAUDE.md); off Windows every function is a no-op that
answers "nothing" rather than raising, and a Win32 call that fails leaves today's window.

- D1: the window carries its own app identity, relaunch command, display name and icon, written
  on its handle before it is shown, so its taskbar button and a pin of it are AgentWeave's and a
  pin relaunches what the desktop shortcut runs instead of `pythonw.exe`.
- D2: a launch that finds the window already open restores it and brings it to the front itself.
- D3: the window's restored size, position and maximized state, read with GetWindowPlacement when
  it closes and passed to `webview.create_window` when it next opens.
- D4/D5: what a close does: close the window only (the rollback setting on), stop the Hub (nothing
  running), or ask (work running, or a Hub that is up and would not say), and the words for it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

#: The shell's name for the app: the process claims it, and so does each window (D1).
APP_ID = "AgentWeave.Hub"
APP_NAME = "AgentWeave"

#: The window's remembered size when nothing is stored, pywebview's own default.
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
#: Smaller than this is not a size the operator left the window at; it is not restored.
_MIN_WIDTH = 200
_MIN_HEIGHT = 100

# PKEY_AppUserModel_* (propkey.h): fmtid {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}.
_PKEY_RELAUNCH_COMMAND = 2
_PKEY_RELAUNCH_ICON = 3
_PKEY_RELAUNCH_NAME = 4
_PKEY_ID = 5
_VT_LPWSTR = 31
_IID_IPROPERTYSTORE = "886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"
_FMTID_APPUSERMODEL = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"

_SW_RESTORE = 9
_SW_SHOWMAXIMIZED = 3
_MONITOR_DEFAULTTONULL = 0
_SPI_GETWORKAREA = 0x0030


def _windows() -> bool:
    return sys.platform == "win32"


# --- D1: the taskbar identity -------------------------------------------------------------------


def relaunch_command(target: str, arguments: str) -> str:
    """The command line a pin runs: the desktop shortcut's target, quoted, then its arguments."""
    return f'"{target}" {arguments}'.strip()


def window_handle(window: Any) -> Optional[int]:
    """The HWND of a pywebview window's WinForms form, or None on another backend."""
    with contextlib.suppress(Exception):
        return int(window.native.Handle.ToInt64())
    return None


def set_window_identity(hwnd: int, command: str, icon: Optional[str]) -> bool:
    """Write the window's app identity, relaunch command, display name and icon (D1).

    These are the window's own shell properties (SHGetPropertyStoreForWindow), which is what the
    taskbar reads for the button and copies into a pin; the process-wide AppUserModelID alone
    names the group but gives a pin nothing to relaunch, so it fell back to `pythonw.exe`. The
    relaunch properties are written before the identity, which the shell reads them under.
    Returns whether every property was written and committed.
    """
    if not _windows() or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class _Guid(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def _guid(text: str) -> _Guid:
            h = text.replace("-", "")
            tail = bytes.fromhex(h[16:])
            return _Guid(
                int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16), (ctypes.c_ubyte * 8)(*tail)
            )

        class _PropertyKey(ctypes.Structure):
            _fields_ = [("fmtid", _Guid), ("pid", wintypes.DWORD)]

        class _PropVariant(ctypes.Structure):
            _fields_ = [
                ("vt", ctypes.c_ushort),
                ("r1", ctypes.c_ushort),
                ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort),
                ("data", ctypes.c_void_p),
                ("pad", ctypes.c_void_p),
            ]

        shell32 = ctypes.WinDLL("shell32")  # type: ignore[attr-defined]
        ole32 = ctypes.WinDLL("ole32")  # type: ignore[attr-defined]
        shell32.SHGetPropertyStoreForWindow.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        ole32.CoInitialize.restype = ctypes.c_long

        initialized = ole32.CoInitialize(None) in (0, 1)  # S_OK, S_FALSE: ours to balance
        try:
            store = ctypes.c_void_p()
            iid = _guid(_IID_IPROPERTYSTORE)
            if shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store)):
                return False
            if not store:
                return False
            vtable = ctypes.cast(
                ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0],
                ctypes.POINTER(ctypes.c_void_p),
            )
            hresult = ctypes.c_long
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(  # type: ignore[attr-defined]
                vtable[2]
            )
            set_value = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
                hresult,
                ctypes.c_void_p,
                ctypes.POINTER(_PropertyKey),
                ctypes.POINTER(_PropVariant),
            )(vtable[6])
            commit = ctypes.WINFUNCTYPE(hresult, ctypes.c_void_p)(  # type: ignore[attr-defined]
                vtable[7]
            )
            values = [
                (_PKEY_RELAUNCH_COMMAND, command),
                (_PKEY_RELAUNCH_NAME, APP_NAME),
            ]
            if icon:
                values.append((_PKEY_RELAUNCH_ICON, f"{icon},0"))
            values.append((_PKEY_ID, APP_ID))
            ok = True
            try:
                for pid, text in values:
                    buffer = ctypes.create_unicode_buffer(text)  # SetValue copies it
                    value = _PropVariant(_VT_LPWSTR, 0, 0, 0, ctypes.addressof(buffer), None)
                    key = _PropertyKey(_guid(_FMTID_APPUSERMODEL), pid)
                    if set_value(store, ctypes.byref(key), ctypes.byref(value)) != 0:
                        ok = False
                if commit(store) != 0:
                    ok = False
            finally:
                release(store)
            return ok
        finally:
            if initialized:
                ole32.CoUninitialize()
    except Exception:
        logger.debug("setting the window's shell properties failed", exc_info=True)
        return False


# --- D2: finding and focusing the open window --------------------------------------------------


def pid_alive(pid: int) -> bool:
    """Is a process with this id running? (A recycled id answers yes; `find_app_window` then also
    requires that process to own an app window.)"""
    if not _windows():
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return bool(code.value == 259)  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def find_app_window(pid: int) -> Optional[int]:
    """The visible top-level pywebview (WinForms) window `pid` owns, or None.

    Found by owning process and window class, never by title: every AgentWeave window is titled
    AgentWeave, the operator's own included.
    """
    if not _windows() or not pid:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        found: list = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]
        def _each(hwnd: Any, _param: Any) -> bool:
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, name, 256)
                if name.value.startswith("WindowsForms"):
                    found.append(int(hwnd))
            return True

        user32.EnumWindows(_each, 0)
        return found[0] if found else None
    except Exception:
        return None


def focus_window(hwnd: int, owner_pid: Optional[int] = None) -> bool:
    """Restore `hwnd` if it is minimized and bring it to the front; return whether it is in front.

    The launching process does this itself (D2): a process the operator's click just started may
    take the foreground, so it hands the foreground to the window rather than asking the window's
    own process, which may not.
    """
    if not _windows() or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        if owner_pid:
            user32.AllowSetForegroundWindow(owner_pid)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, _SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        if int(user32.GetForegroundWindow() or 0) == hwnd:
            return True
        # Refused: this launch was not started by the foreground process (a pin clicked after
        # focus moved on, a launch from a background script). Sharing the foreground thread's
        # input for the call is the documented way its owner's rights extend to us.
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        front = user32.GetForegroundWindow()
        theirs = user32.GetWindowThreadProcessId(front, None) if front else 0
        ours = kernel32.GetCurrentThreadId()
        attached = bool(theirs and theirs != ours and user32.AttachThreadInput(ours, theirs, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(ours, theirs, False)
        return bool(int(user32.GetForegroundWindow() or 0) == hwnd)
    except Exception:
        return False


# --- D3: the window's geometry -----------------------------------------------------------------


def read_geometry(path: Path) -> Optional[Dict[str, Any]]:
    """The stored geometry, or None when there is none or it is not one this module wrote."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        geometry = {
            "x": int(data["x"]),
            "y": int(data["y"]),
            "width": int(data["width"]),
            "height": int(data["height"]),
            "maximized": bool(data.get("maximized", False)),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if geometry["width"] < _MIN_WIDTH or geometry["height"] < _MIN_HEIGHT:
        return None
    return geometry


def write_geometry(path: Path, geometry: Dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(geometry), encoding="utf-8")
    except OSError:
        return False
    return True


def window_kwargs(
    saved: Optional[Dict[str, Any]],
    on_screen: Callable[[Dict[str, Any]], bool],
    primary: Callable[[], Optional[Dict[str, int]]],
) -> Dict[str, Any]:
    """`webview.create_window` keyword arguments for the remembered geometry (D3).

    Nothing stored: pywebview's defaults. Stored on a connected screen: its size and position, and
    maximized if it closed maximized. Stored off every connected screen: its size, centred on the
    primary screen's work area (`primary`, logical pixels), still maximized if it was.
    """
    if saved is None:
        return {}
    kwargs: Dict[str, Any] = {"width": saved["width"], "height": saved["height"]}
    if on_screen(saved):
        kwargs["x"], kwargs["y"] = saved["x"], saved["y"]
    else:
        area = primary()
        if area is not None:
            kwargs["x"] = area["x"] + max(0, (area["width"] - saved["width"]) // 2)
            kwargs["y"] = area["y"] + max(0, (area["height"] - saved["height"]) // 2)
    if saved.get("maximized"):
        kwargs["maximized"] = True
    return kwargs


def _scale_for(hwnd: Optional[int]) -> float:
    """Physical pixels per logical pixel: the window's DPI, else the system's, over 96."""
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        dpi = user32.GetDpiForWindow(hwnd) if hwnd else 0
        if not dpi:
            dpi = user32.GetDpiForSystem()
        return float(dpi) / 96.0 if dpi else 1.0
    except Exception:
        return 1.0


def _rect(left: int, top: int, right: int, bottom: int) -> Any:
    from ctypes import wintypes

    return wintypes.RECT(left, top, right, bottom)


def _primary_work_origin() -> tuple:
    """The primary work area's top-left (physical): GetWindowPlacement answers in workspace
    coordinates, which are offset from screen coordinates by it."""
    import ctypes

    area = _rect(0, 0, 0, 0)
    ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
        _SPI_GETWORKAREA, 0, ctypes.byref(area), 0
    )
    return area.left, area.top


def placement(hwnd: int) -> Optional[Dict[str, Any]]:
    """The window's restored rectangle (logical pixels, screen coordinates) and whether it is
    maximized, as GetWindowPlacement reports it: the size it would return to, not the maximized
    one."""
    if not _windows() or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _Placement(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.UINT),
                ("flags", wintypes.UINT),
                ("showCmd", wintypes.UINT),
                ("ptMinPosition", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT),
                ("rcNormalPosition", wintypes.RECT),
            ]

        info = _Placement()
        info.length = ctypes.sizeof(_Placement)
        if not ctypes.windll.user32.GetWindowPlacement(  # type: ignore[attr-defined]
            hwnd, ctypes.byref(info)
        ):
            return None
        rect = info.rcNormalPosition
        dx, dy = _primary_work_origin()
        scale = _scale_for(hwnd)
        return {
            "x": int(round((rect.left + dx) / scale)),
            "y": int(round((rect.top + dy) / scale)),
            "width": int(round((rect.right - rect.left) / scale)),
            "height": int(round((rect.bottom - rect.top) / scale)),
            "maximized": info.showCmd == _SW_SHOWMAXIMIZED,
        }
    except Exception:
        logger.debug("reading the window's placement failed", exc_info=True)
        return None


def on_a_screen(geometry: Dict[str, Any]) -> bool:
    """Is the window's title bar region on a connected monitor? Off Windows, assume so."""
    if not _windows():
        return True
    try:
        import ctypes

        scale = _scale_for(None)
        left = int(geometry["x"] * scale)
        top = int(geometry["y"] * scale)
        # The top strip of the window: where it is grabbed to move it, so it must be reachable.
        rect = _rect(left, top, left + int(geometry["width"] * scale), top + int(32 * scale))
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.MonitorFromRect.restype = ctypes.c_void_p
        return bool(user32.MonitorFromRect(ctypes.byref(rect), _MONITOR_DEFAULTTONULL))
    except Exception:
        return True


def primary_work_area() -> Optional[Dict[str, int]]:
    """The primary screen's work area in logical pixels, or None off Windows."""
    if not _windows():
        return None
    try:
        import ctypes

        area = _rect(0, 0, 0, 0)
        if not ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            _SPI_GETWORKAREA, 0, ctypes.byref(area), 0
        ):
            return None
        scale = _scale_for(None)
        return {
            "x": int(area.left / scale),
            "y": int(area.top / scale),
            "width": int((area.right - area.left) / scale),
            "height": int((area.bottom - area.top) / scale),
        }
    except Exception:
        return None


# --- D4/D5: what closing the window does --------------------------------------------------------

#: The three ways a close can go (D4): close the window and leave the Hub running, close it and
#: stop the Hub, or keep it open and ask the operator.
CLOSE_WINDOW_ONLY = "close"
CLOSE_AND_STOP = "stop"
CLOSE_ASKS = "ask"

#: The operator's answers to the prompt, as the page sends them through the window's bridge.
CHOICE_STOP = "stop"
CHOICE_KEEP = "keep"
CHOICE_CANCEL = "cancel"
CHOICES = (CHOICE_STOP, CHOICE_KEEP, CHOICE_CANCEL)


def read_keeps_running(path: Path) -> bool:
    """The rollback setting (D5): does closing the window leave AgentWeave running? Off unless
    stored on."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(isinstance(data, dict) and data.get("keep_running") is True)


def write_keeps_running(path: Path, on: bool) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"keep_running": bool(on)}), encoding="utf-8")
    except OSError:
        return False
    return True


def close_decision(
    keeps_running: Callable[[], bool],
    work_running: Callable[[], Optional[Dict[str, Any]]],
    hub_up: Callable[[], bool],
) -> tuple:
    """What a close does, as `(CLOSE_*, work)` (D4, D5).

    The setting is read first, and when it is on the Hub is never asked. Otherwise the Hub's
    answer decides: nothing running stops it, anything running asks. A Hub that does not answer
    is only taken as having nothing to protect when it is not up at all; one still up but not
    answering is asked about, never guessed idle (the hazard's mitigation), with `unknown` set.
    """
    if keeps_running():
        return CLOSE_WINDOW_ONLY, None
    work = work_running()
    if work is None:
        if hub_up():
            return CLOSE_ASKS, {"unknown": True}
        return CLOSE_AND_STOP, None
    if work.get("running"):
        return CLOSE_ASKS, work
    return CLOSE_AND_STOP, None


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def describe_work(work: Dict[str, Any]) -> str:
    """What is running, in words: "1 agent turn, 2 check runs and the build Close means stop"."""
    if work.get("unknown"):
        return "AgentWeave could not say what is running"
    parts = []
    if work.get("turns"):
        parts.append(_plural(int(work["turns"]), "agent turn", "agent turns"))
    if work.get("check_runs"):
        parts.append(_plural(int(work["check_runs"]), "check run", "check runs"))
    if work.get("landings"):
        parts.append(_plural(int(work["landings"]), "landing", "landings"))
    builds = [b.get("title") for b in work.get("build_list") or [] if b.get("title")]
    if builds:
        names = ", ".join(builds)
        parts.append(f"the build {names}" if len(builds) == 1 else f"the builds {names}")
    elif work.get("builds"):
        parts.append(_plural(int(work["builds"]), "build", "builds"))
    if not parts:
        return "Work is running"
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return text[0].upper() + text[1:] + (" is running" if len(parts) == 1 else " are running")


_MB_YESNOCANCEL = 0x3
_MB_ICONWARNING = 0x30
_MB_DEFBUTTON3 = 0x200
_IDYES = 6
_IDNO = 7


def ask_natively(hwnd: Optional[int], work: Dict[str, Any]) -> str:
    """The three-way prompt as a native message box, when the page cannot show it (the splash,
    or a page that has not loaded): Yes stops it all, No keeps it running, Cancel cancels."""
    if not _windows():
        return CHOICE_CANCEL
    try:
        import ctypes

        text = (
            f"{describe_work(work)}.\n\n"
            "Yes: stop it all and close.\n"
            "No: keep it running in the background and close the window.\n"
            "Cancel: leave everything as it is."
        )
        answer = ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            hwnd or 0, text, APP_NAME, _MB_YESNOCANCEL | _MB_ICONWARNING | _MB_DEFBUTTON3
        )
    except Exception:
        return CHOICE_CANCEL
    if answer == _IDYES:
        return CHOICE_STOP
    if answer == _IDNO:
        return CHOICE_KEEP
    return CHOICE_CANCEL
