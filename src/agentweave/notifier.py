"""Windows notifications for what calls the operator.

Change `windows-notifications-for-what-calls-the-operator` (D3-D5). The Hub publishes one
`operator_notice` per event that calls the operator; this module shows one as a Windows
notification. The Hub never does: it stays platform-neutral. The app window's bridge calls `show`
when the window is not in front, and the launcher's watcher calls it while no window is open.

- D4: the notification is shown by Windows PowerShell 5.1 (named explicitly, started with
  CREATE_NO_WINDOW) through Windows' own toast interface, so the CLI stays stdlib-only. It is
  attributed to `desktop_window.APP_ID` by a Start-menu shortcut carrying that AppUserModelID and
  the packaged icon, which gives it AgentWeave's name and icon.
- D5: a click is protocol activation. An `agentweave:` link is registered per user under
  HKCU\\Software\\Classes; the toast launches `agentweave:open/<port>/<project>[/<agent>/<conversation>]`,
  which runs the launcher with `--open`. The link is path segments, never a query: `explorer.exe`
  drops a link holding `?` (tried on Windows 11, 2026-11-08).
- Every path de-duplicates by notice id through a per-port ledger (one file per notice, created
  exclusively), so the window and the watcher can overlap at a hand-over and still show one.
- Quiet failure (FR-8): nothing here raises. Off Windows, or when the shell call fails, `show`
  answers False and the app carries on. `AW_TOAST_COMMAND` replaces the PowerShell call: drives use
  it to record, and the quiet-failure check to fail. It receives a JSON payload on stdin.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from xml.sax.saxutils import escape, quoteattr

from . import desktop_window

PROTOCOL = "agentweave"
TOAST_COMMAND_ENV = "AW_TOAST_COMMAND"
SHORTCUT_NAME = f"{desktop_window.APP_NAME}.lnk"
TOAST_GROUP = "agentweave"

_CREATE_NO_WINDOW = 0x08000000
#: A toast that has not been handed to Windows by now is not coming.
_SHOW_TIMEOUT_SECONDS = 15
#: The shortcut is created once; compiling its helper takes PowerShell a few seconds.
_SHORTCUT_TIMEOUT_SECONDS = 60
#: Ledger entries older than this are forgotten; a notice is never re-sent that late.
_LEDGER_KEEP_SECONDS = 2 * 24 * 3600
#: Windows keeps a toast's tag to 64 characters.
_TAG_LIMIT = 64
#: What a link segment (port, project, agent, conversation id) may hold: nothing a URL or a command
#: line would read as structure.
_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def supported() -> bool:
    """Windows notifications exist only on Windows; everywhere else this module does nothing."""
    return sys.platform == "win32"


# --- the activation link (D5) ------------------------------------------------------------------


def _segment(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and _SEGMENT.match(value) else None


def open_link(
    port: int,
    project_id: Optional[str],
    agent: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> str:
    """The `agentweave:` link a notification's click opens.

    A conversation needs both its agent and its id; without either the link names the project only
    (its overview), and without a project, only the Hub.
    """
    parts = [f"{PROTOCOL}:open", str(int(port))]
    project = _segment(project_id)
    if project:
        parts.append(project)
        who, conversation = _segment(agent), _segment(conversation_id)
        if who and conversation:
            parts += [who, conversation]
    return "/".join(parts)


def parse_open_link(link: Any) -> Optional[Dict[str, Any]]:
    """`{port, project_id, agent, conversation_id}` from an `agentweave:` link, or None.

    Windows hands the handler the link as it was opened, sometimes with a trailing slash; a link
    with a segment this module would not have written is refused whole.
    """
    if not isinstance(link, str):
        return None
    prefix = f"{PROTOCOL}:"
    if not link.lower().startswith(prefix):
        return None
    rest = link[len(prefix) :].lstrip("/").rstrip("/")
    parts = rest.split("/")
    if not parts or parts[0] != "open" or len(parts) not in (2, 3, 5):
        return None
    if not parts[1].isdigit() or not 0 < int(parts[1]) < 65536:
        return None
    if any(_segment(p) is None for p in parts[2:]):
        return None
    return {
        "port": int(parts[1]),
        "project_id": parts[2] if len(parts) > 2 else None,
        "agent": parts[3] if len(parts) == 5 else None,
        "conversation_id": parts[4] if len(parts) == 5 else None,
    }


def app_url(port: int, target: Dict[str, Any]) -> str:
    """The page address an open target names: its conversation, else its project's overview."""
    base = f"http://127.0.0.1:{int(port)}/"
    project = target.get("project_id")
    if not project:
        return base
    if target.get("agent") and target.get("conversation_id"):
        query = {
            "project": project,
            "agent": target["agent"],
            "conversation": target["conversation_id"],
        }
    else:
        query = {"project": project, "tab": "overview"}
    return f"{base}?{urlencode(query)}"


def link_for_notice(port: int, notice: Dict[str, Any]) -> str:
    """A question or reply opens its conversation; a permission request, a failure or anything
    without a conversation opens its project's overview (FR-6)."""
    return open_link(
        port, notice.get("project_id"), notice.get("agent"), notice.get("conversation_id")
    )


def _python_for_handler() -> str:
    """The windowless interpreter beside this one, so a click flashes no console."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return str(pythonw if pythonw.is_file() else Path(sys.executable))


def _import_roots() -> List[str]:
    """Where this process found `agentweave` and the Hub, for a handler started without our env.

    Explorer starts the handler with its own environment, so a launcher that found its packages
    through PYTHONPATH (a checkout) would otherwise register a link that cannot import them.
    """
    import importlib.util

    roots: List[str] = []
    for name in ("agentweave", "hub"):
        with contextlib.suppress(Exception):
            spec = importlib.util.find_spec(name)
            origin = spec.origin if spec is not None else None
            if origin:
                root = str(Path(origin).resolve().parents[1])
                if root not in roots:
                    roots.append(root)
    return roots


def handler_command() -> str:
    """The command Windows runs for an `agentweave:` link: the launcher with `--open "%1"`."""
    boot = (
        f"import sys;sys.path[:0]={_import_roots()!r};"
        "from agentweave.cli import main;sys.exit(main())"
    )
    return f'"{_python_for_handler()}" -c "{boot}" --open "%1"'


def register_link() -> bool:
    """Register the `agentweave:` link for this user (HKCU, so no elevation). Rewritten on every
    launch, so it follows the install the operator last opened. Never raises."""
    if not supported():
        return False
    try:
        import winreg

        base = rf"Software\Classes\{PROTOCOL}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{desktop_window.APP_NAME}")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        icon = _icon_path()
        if icon:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\DefaultIcon") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{icon}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, handler_command())
        return True
    except Exception:
        return False


def _icon_path() -> Optional[str]:
    with contextlib.suppress(Exception):
        from importlib import resources

        icon = resources.files("agentweave").joinpath("assets", "icon.ico")
        if icon.is_file():
            return str(icon)
    return None


# --- the Start-menu shortcut (D4) --------------------------------------------------------------

#: IShellLinkW + IPropertyStore, compiled by PowerShell's Add-Type: WScript.Shell cannot write a
#: shortcut's AppUserModelID, and the CLI takes no package to do it (operator, 2026-11-08).
_SHORTCUT_CSHARP = r"""
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
[ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAwShellLinkW {
  void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
  void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
  void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder n, int c);
  void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string n);
  void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder d, int c);
  void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string d);
  void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder a, int c);
  void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
  void GetHotkey(out short h); void SetHotkey(short h);
  void GetShowCmd(out int s); void SetShowCmd(int s);
  void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int c, out int i);
  void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string p, int i);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string p, uint r);
  void Resolve(IntPtr h, uint f);
  void SetPath([MarshalAs(UnmanagedType.LPWStr)] string f);
}
[StructLayout(LayoutKind.Sequential, Pack = 4)] struct AwPropertyKey { public Guid fmtid; public uint pid; }
[StructLayout(LayoutKind.Explicit, Size = 16)] struct AwPropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }
[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAwPropertyStore {
  void GetCount(out uint c); void GetAt(uint i, out AwPropertyKey k);
  void GetValue(ref AwPropertyKey k, out AwPropVariant v);
  void SetValue(ref AwPropertyKey k, ref AwPropVariant v); void Commit();
}
[ComImport, Guid("00021401-0000-0000-C000-000000000046")] class AwShellLink {}
public static class AwStartMenuLink {
  public static void Save(string lnk, string target, string args, string dir, string icon, string desc, string aumid) {
    var link = (IAwShellLinkW)new AwShellLink();
    link.SetPath(target); link.SetArguments(args); link.SetWorkingDirectory(dir); link.SetDescription(desc);
    if (icon.Length > 0) link.SetIconLocation(icon, 0);
    var store = (IAwPropertyStore)link;
    var key = new AwPropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    var pv = new AwPropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(aumid) };
    try { store.SetValue(ref key, ref pv); store.Commit(); ((IPersistFile)link).Save(lnk, true); }
    finally { Marshal.FreeCoTaskMem(pv.p); }
  }
}
"""


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _powershell() -> str:
    """Windows PowerShell 5.1 by its full path: `pwsh` cannot load the WinRT toast types."""
    root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
    exe = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(exe) if exe.is_file() else "powershell.exe"


def _run_powershell(script: str, timeout: float) -> bool:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def start_menu_shortcut() -> Optional[Path]:
    """Where the Start-menu shortcut lives: the user's own Programs folder."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / SHORTCUT_NAME


def ensure_shortcut(target: str, arguments: str, icon: Optional[str]) -> bool:
    """Create the Start-menu shortcut that gives notifications AgentWeave's name and icon, once.

    Idempotent: a shortcut already there is left as it is, as the desktop one is. Never raises.
    """
    if not supported():
        return False
    lnk = start_menu_shortcut()
    if lnk is None:
        return False
    if lnk.exists():
        return True
    try:
        lnk.parent.mkdir(parents=True, exist_ok=True)
        script = "; ".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"Add-Type -TypeDefinition {_ps_quote(_SHORTCUT_CSHARP)}",
                "[AwStartMenuLink]::Save("
                + ", ".join(
                    _ps_quote(v)
                    for v in (
                        str(lnk),
                        target,
                        arguments,
                        str(Path.home()),
                        icon or "",
                        f"Launch {desktop_window.APP_NAME}",
                        desktop_window.APP_ID,
                    )
                )
                + ")",
            ]
        )
        return _run_powershell(script, _SHORTCUT_TIMEOUT_SECONDS) and lnk.exists()
    except Exception:
        return False


def register(target: str, arguments: str, icon: Optional[str]) -> bool:
    """Everything a notification needs from Windows: the link and the shortcut. Never raises."""
    linked = register_link()
    shortcut = ensure_shortcut(target, arguments, icon)
    return linked and shortcut


# --- the de-duplication ledger (D3) ------------------------------------------------------------


def _ledger_dir(hub_dir: Path, port: int) -> Path:
    return Path(hub_dir) / "notified" / str(int(port))


def _ledger_name(notice_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", notice_id)[:100]
    return safe or "_"


def claim(hub_dir: Path, port: int, notice_id: str) -> bool:
    """Claim the right to show `notice_id` on this port; False if anyone already has.

    One file per notice, created exclusively: the operating system decides between two processes
    claiming at the same moment, so the window and the watcher never both show one notice.
    """
    folder = _ledger_dir(hub_dir, port)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _forget_old(folder)
        fd = os.open(str(folder / _ledger_name(notice_id)), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError:
        return False
    with contextlib.suppress(OSError):
        os.write(fd, f"{time.time():.0f}\n".encode("ascii"))
    with contextlib.suppress(OSError):
        os.close(fd)
    return True


def release(hub_dir: Path, port: int, notice_id: str) -> None:
    """Give back a claim whose notification was never shown, so another path may try."""
    with contextlib.suppress(OSError):
        (_ledger_dir(hub_dir, port) / _ledger_name(notice_id)).unlink()


def _forget_old(folder: Path) -> None:
    cutoff = time.time() - _LEDGER_KEEP_SECONDS
    with contextlib.suppress(OSError):
        for entry in os.scandir(folder):
            with contextlib.suppress(OSError):
                if entry.stat().st_mtime < cutoff:
                    os.unlink(entry.path)


# --- showing one (D4) --------------------------------------------------------------------------


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def toast_xml(notice: Dict[str, Any], link: str) -> str:
    """The toast: the in-app toast's words, its first line the notice's text (which names the agent
    or project and why), its second the project's name, or the notice's headline without one."""
    first = _text(notice.get("text")) or _text(notice.get("title")) or desktop_window.APP_NAME
    second = _text(notice.get("project_name")) or _text(notice.get("title"))
    lines = f"<text>{escape(first)}</text>"
    if second and second != first:
        lines += f"<text>{escape(second)}</text>"
    return (
        f'<toast activationType="protocol" launch={quoteattr(link)}>'
        f'<visual><binding template="ToastGeneric">{lines}</binding></visual>'
        "</toast>"
    )


def _tag(notice_id: str) -> str:
    return _ledger_name(notice_id)[:_TAG_LIMIT]


def _show_script(xml: str, tag: str) -> str:
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] > $null",
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
            "ContentType = WindowsRuntime] > $null",
            "$x = New-Object Windows.Data.Xml.Dom.XmlDocument",
            f"$x.LoadXml({_ps_quote(xml)})",
            "$t = New-Object Windows.UI.Notifications.ToastNotification $x",
            f"$t.Tag = {_ps_quote(tag)}",
            f"$t.Group = {_ps_quote(TOAST_GROUP)}",
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
            f"{_ps_quote(desktop_window.APP_ID)}).Show($t)",
        ]
    )


def _run_toast_command(command: str, payload: Dict[str, Any]) -> bool:
    """`AW_TOAST_COMMAND` in place of PowerShell, with the payload as JSON on stdin."""
    args: Any = command if sys.platform == "win32" else shlex.split(command)
    result = subprocess.run(
        args,
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=_SHOW_TIMEOUT_SECONDS,
        creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return result.returncode == 0


def show(notice: Any, port: int, hub_dir: Path) -> bool:
    """Show `notice` as a Windows notification, at most once per notice per port.

    Answers whether it was handed to Windows. False, and nothing shown, off Windows, for a notice
    without an id or words, for one already shown, and when the shell call fails or times out.
    Never raises: a notification is a convenience, never a dependency for work (FR-8).
    """
    try:
        if not supported() or not isinstance(notice, dict):
            return False
        notice_id = _text(notice.get("id"))
        if not notice_id or not (_text(notice.get("text")) or _text(notice.get("title"))):
            return False
        if not claim(hub_dir, port, notice_id):
            return False
        shown = False
        try:
            link = link_for_notice(port, notice)
            xml = toast_xml(notice, link)
            command = os.environ.get(TOAST_COMMAND_ENV, "").strip()
            if command:
                payload = {
                    "notice": notice,
                    "xml": xml,
                    "link": link,
                    "app_id": desktop_window.APP_ID,
                }
                shown = _run_toast_command(command, payload)
            else:
                shown = _run_powershell(_show_script(xml, _tag(notice_id)), _SHOW_TIMEOUT_SECONDS)
        except Exception:
            shown = False
        if not shown:
            release(hub_dir, port, notice_id)
        return shown
    except Exception:
        return False


# --- listening for notices (task background-watcher: FR-2, FR-3, FR-10) ------------------------
#
# Two listeners read the operator stream and show what calls the operator: one in every app window's
# process, from the moment the window shows the app, and the launcher's watcher (`pythonw`, one per
# port) while no window is open. The window's own listener keeps reading after its window has gone,
# until the watcher it starts says it is listening, and until every notice it has claimed is shown;
# the watcher ends once a live window's listener says the same, giving up its word that it listens
# before it finishes what it is showing. So some listener is always reading across a close or a
# reopen, and the ledger in `show` makes an overlap show each notice once.

NOTICE_EVENT = "operator_notice"
#: The Hub's defaults (FR-10), for when its choices cannot be read.
DEFAULT_WINDOWS_KINDS: Dict[str, bool] = {"ask": True, "fail": True, "done": False, "reply": False}
#: How long a notice waits for the app window to leave the front before it is let go. A window in
#: front shows its own in-app toast (FR-3); one closing as the notice arrives does not, so the notice
#: is shown as soon as no window of the port is in front, within this time (FR-3, and FR-2's 5 s).
HAND_OVER_SECONDS = 3.0
_HAND_OVER_POLL_SECONDS = 0.25


def sse_events(lines: Any) -> Any:
    """`(event, data)` for each event in a Server-Sent Events byte stream, `data` parsed as JSON
    where it is JSON. Comments (the Hub's pings) are skipped; a frame without data is skipped."""
    event = "message"
    data: List[str] = []
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        line = line.rstrip("\r\n")
        if not line:
            if data:
                text = "\n".join(data)
                try:
                    value: Any = json.loads(text)
                except ValueError:
                    value = text
                yield event, value
            event, data = "message", []
            continue
        if line.startswith(":"):
            continue
        name, _, value_text = line.partition(":")
        value_text = value_text[1:] if value_text.startswith(" ") else value_text
        if name == "event":
            event = value_text
        elif name == "data":
            data.append(value_text)


def wanted(notice: Any, kinds: Dict[str, bool]) -> bool:
    """Is `notice` of a kind the operator switched on for Windows?"""
    return isinstance(notice, dict) and kinds.get(str(notice.get("kind"))) is True


def deliver(
    notice: Dict[str, Any],
    port: int,
    hub_dir: Path,
    in_front: Any,
    hold: float = HAND_OVER_SECONDS,
    poll: float = _HAND_OVER_POLL_SECONDS,
) -> bool:
    """Show `notice` once no app window of the port is in front, waiting at most `hold` seconds.

    A notice that arrives with no window in front is shown at once; one that arrives while a window
    stays in front for all of `hold` is the window's own in-app toast, and nothing is shown. Never
    raises.
    """
    try:
        deadline = time.monotonic() + hold
        while True:
            if not in_front():
                return show(notice, port, hub_dir)
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll)
    except Exception:
        return False


def listen(
    lines: Any,
    port: int,
    hub_dir: Path,
    kinds: Any,
    in_front: Any,
    on_ready: Any = None,
) -> None:
    """Read one connection of the operator stream and show each wanted notice (FR-2, FR-10).

    `kinds()` answers the Hub's current choices and is asked for each notice, so a change applies
    without a restart. Each notice is delivered on its own thread, so one waiting on the window
    never holds up the next. `on_ready()` runs once the Hub has said the stream is connected.
    Returns when the connection ends; raises what reading it raises.
    """
    import threading

    for event, data in sse_events(lines):
        if event == "connected":
            if on_ready is not None:
                with contextlib.suppress(Exception):
                    on_ready()
            continue
        if event != NOTICE_EVENT:
            continue
        try:
            choices = kinds()
        except Exception:
            choices = dict(DEFAULT_WINDOWS_KINDS)
        if not wanted(data, choices):
            continue
        threading.Thread(
            target=deliver,
            args=(data, port, hub_dir, in_front),
            name="aw-notice",
            daemon=True,
        ).start()


def launcher_argv(*arguments: str) -> List[str]:
    """The launcher with `arguments`, under the windowless interpreter, importable from wherever
    this process found it (as the link's handler is)."""
    boot = (
        f"import sys;sys.path[:0]={_import_roots()!r};"
        "from agentweave.cli import main;sys.exit(main())"
    )
    return [_python_for_handler(), "-c", boot, *arguments]
