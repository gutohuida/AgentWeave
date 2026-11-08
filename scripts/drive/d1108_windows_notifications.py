"""Acceptance drive for "Windows notifications for what calls the operator"
(spec/changes/windows-notifications-for-what-calls-the-operator). Written failing first (WNWCO-1).

Runs this checkout's CLI and Hub (src/ and hub/ on PYTHONPATH) on ONE scratch port (8180 by
default) with a scratch profile -- never :8000 (the operator's) or :8010 (the trial Hub). Reuses
d1105_own_app.py's launcher, window, process and Hub-API helpers.

What it reads, and how:
  * the shell's notification history: Windows' own store, %LOCALAPPDATA%\\Microsoft\\Windows\\
    Notifications\\wpndatabase.db (copied with its WAL, read read-only). Each row's handler is the
    AppUserModelID it was shown under; its payload is the toast XML (text, image, launch link).
    A "notification" in this drive is a new row under AgentWeave.Hub; nothing is read from the
    product's own bookkeeping.
  * the operator stream: GET /api/v1/events with the instance credential, kept by a reader thread.
  * the page: the window runs with WebView2's remote-debugging port (SCRATCH_CDP_PORT) and its own
    user-data folder (SCRATCH_UDF). Without the folder it joins the browser process of any app
    window already open on this machine -- the operator's -- which has no debugging port, and
    every page read came back empty (WNWCO-8). /json lists the page with its URL; the DevTools
    protocol (a stdlib WebSocket, `page_eval`) reads its text and title and clicks its controls.
    UI Automation is not used: it never found the in-app toast, and the Windows switches are
    role=switch, not buttons.
  * the activation link: taken from the toast XML's `launch` attribute and opened through the
    shell (`explorer.exe <link>`, as a click does) -- never by calling the launcher. Explorer starts
    the handler with the user's environment, so for that one step the two WebView2 variables are
    set in HKCU\\Environment (and announced with WM_SETTINGCHANGE), then put back.
  * app windows: by class and title across every process, less those open before the drive
    started (the operator's), since a window the link opens belongs to no process the drive began.
  * a step that cannot establish its precondition (the window in front, the switches changed, the
    failure close to the close) reports that as a failure and skips the checks that depend on it,
    rather than letting them pass for the wrong reason.

The drive rewrites nothing of the operator's for good: the `agentweave:` link registration (which
every scratch launch rewrites to point at this checkout) and HKCU\\Environment are restored on
exit.

Assumptions about the CONTRACT's open details (named once so the build can move them):
  NOTIFY_SETTINGS_PATH -- the Hub route for the Windows kinds, {ask, fail, done, reply} booleans.
  AW_TOAST_COMMAND     -- set to a command that exits non-zero for the c-quiet step.

Steps, each named after its criterion: c-event, c-notice, c-behind, c-identity, c-in-front,
c-closed, c-click, c-quiet, c-kinds. Real Haiku turns: the ask_user turn (c-behind, c-event) and
the run made to fail (its claude process is killed while it runs).

  py -3.11 scripts/drive/d1108_windows_notifications.py [--port 8180]
"""

import argparse
import base64
import ctypes
import json
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import winreg
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "drive"))
import d1105_own_app as d  # noqa: E402

user32 = d.user32
check, note, wait_for = d.check, d.note, d.wait_for

PROFILE_PREFIX = "d1108wn"
RUN = time.strftime("%H%M%S")
SCRATCH_CDP_PORT = 9338
SCRATCH_UDF = d.SCRATCH / f"webview-{RUN}"  # removed with d.SCRATCH at the end
WEBVIEW_ENV = {
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={SCRATCH_CDP_PORT}",
    "WEBVIEW2_USER_DATA_FOLDER": str(SCRATCH_UDF),
}
NO_WINDOW = 0x08000000
NOTIFY_SETTINGS_PATH = "/notify-settings"
WPN_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Notifications"
AUMID = "AgentWeave.Hub"
SW_RESTORE, SW_MINIMIZE = 9, 6
LIMIT = 5.0  # the spec's "within 5 seconds"
failures = d.failures


# --- the shell's notification history ----------------------------------------------------------


def history() -> list[dict]:
    """Every toast the shell holds: {id, aumid, xml}. Read from a copy so the store's lock is moot."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="d1108wpn"))
    try:
        for suffix in ("", "-wal", "-shm"):
            src = WPN_DIR / f"wpndatabase.db{suffix}"
            if src.exists():
                shutil.copy2(src, tmp / src.name)
        con = sqlite3.connect(f"file:{(tmp / 'wpndatabase.db').as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "select n.Id, h.PrimaryId, n.Payload from Notification n "
                "join NotificationHandler h on h.RecordId = n.HandlerId where n.Type = 'toast'"
            ).fetchall()
        finally:
            con.close()
        out = []
        for nid, aumid, payload in rows:
            xml = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(payload)
            out.append({"id": nid, "aumid": aumid or "", "xml": xml})
        return out
    except Exception as exc:  # a store that cannot be read is a failed step, said once
        note(f"history unreadable: {exc}")
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Shell:
    """Counts toasts that appear after a mark, by the text they carry."""

    def __init__(self):
        self.seen = {h["id"] for h in history()}

    def mark(self):
        self.seen = {h["id"] for h in history()}

    def new(self, needle: str = "", aumid: str | None = AUMID) -> list[dict]:
        return [
            h
            for h in history()
            if h["id"] not in self.seen
            and (aumid is None or h["aumid"] == aumid)
            and needle in h["xml"]
        ]

    def wait_new(self, needle: str, timeout: float) -> list[dict]:
        return wait_for(lambda: self.new(needle), timeout, 0.25) or []


# --- the operator stream -----------------------------------------------------------------------


class Stream:
    def __init__(self, app: d.App):
        self.app, self.events, self.log, self.stop = app, [], [], False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while not self.stop:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.app.port}/api/v1/events",
                    headers={"Authorization": "Bearer " + self.app.key()},
                )
                with urllib.request.urlopen(req, timeout=300) as r:
                    name = None
                    for raw in r:
                        if self.stop:
                            return
                        line = raw.decode("utf-8", "replace").rstrip("\r\n")
                        if line.startswith("event:"):
                            name = line[6:].strip()
                        elif line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                            except ValueError:
                                continue
                            if isinstance(data, dict):
                                data["_seen"] = time.monotonic()  # arrival time, for the 5 s limits
                            self.events.append((name, data))
                            self.log.append((name, data))  # never cleared: the final c-notice count
            except Exception:
                time.sleep(1.0)

    def of(self, name: str) -> list[dict]:
        return [dat for n, dat in list(self.events) if n == name]

    def logged(self, name: str) -> list[dict]:
        return [dat for n, dat in list(self.log) if n == name]


# --- the app, the page and the shell link ------------------------------------------------------


class WinApp(d.App):
    """d.App with the page readable (debugging port, own WebView2 folder), an optional
    AW_TOAST_COMMAND, and its windows found across every process."""

    toast_command: str | None = None
    baseline: set[int] = set()  # app windows open before the drive started: never ours

    def launch(self):
        saved = d.app_env

        def env():
            e = saved()
            # An explicit address for the agents' tool calls: a run's own HUB_URL otherwise comes from
            # the first connection the Hub sees (2026-11-08: a scratch Hub's run was refused 401).
            e["HUB_URL"] = f"http://127.0.0.1:{self.port}"
            e.update(WEBVIEW_ENV)
            if self.toast_command:
                e["AW_TOAST_COMMAND"] = self.toast_command
            return e

        d.app_env = env
        try:
            return super().launch()
        finally:
            d.app_env = saved

    def windows(self) -> list[dict]:
        """This Hub's app windows, whichever process opened them: one the activation link opens
        belongs to a process Explorer started, so d.App's own-pids filter never saw it."""
        return [
            w for w in all_app_windows() if w["pid"] in self.pids or w["hwnd"] not in self.baseline
        ]


def all_app_windows() -> list[dict]:
    """Every visible pywebview (WinForms) window titled AgentWeave, in any process."""
    return [
        w
        for w in d.top_windows()
        if w["visible"] and w["cls"].startswith("WindowsForms") and "AgentWeave" in w["title"]
    ]


# --- the page, through the DevTools protocol ---------------------------------------------------


def _pages() -> list[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{SCRATCH_CDP_PORT}/json", timeout=2) as r:
            return [p for p in json.loads(r.read()) if p.get("type") == "page"]
    except Exception:
        return []


def page_url() -> str:
    pages = _pages()
    return pages[0]["url"] if pages else ""


def app_page(port: int, timeout: float = 60) -> str:
    """The page's URL once it is the Hub's app, not the launcher's splash (a data: URL that the
    window leaves when the Hub answers: whatever was put into the splash is gone with it)."""
    return (
        wait_for(
            lambda: (
                page_url()
                if re.match(rf"https?://(127\.0\.0\.1|localhost):{port}/", page_url())
                and page_try("document.readyState") == "complete"
                else ""
            ),
            timeout,
            0.5,
        )
        or ""
    )


def _ws_recv_exact(sock: socket.socket, n: int, buf: bytearray) -> bytes:
    while len(buf) < n:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("DevTools socket closed")
        buf += chunk
    out = bytes(buf[:n])
    del buf[:n]
    return out


def page_eval(expression: str, timeout: float = 15):
    """Evaluate `expression` in the window's page and return its value (promises awaited).

    Raises when there is no page to reach: a caller that needs the page reports that, rather than
    reading an empty answer as "not there"."""
    pages = _pages()
    if not pages:
        raise RuntimeError(f"no page on the DevTools port {SCRATCH_CDP_PORT}")
    url = urllib.parse.urlparse(pages[0]["webSocketDebuggerUrl"])
    sock = socket.create_connection((url.hostname, url.port), timeout)
    try:
        sock.sendall(
            (
                f"GET {url.path} HTTP/1.1\r\nHost: {url.hostname}:{url.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("DevTools handshake closed")
            buf += chunk
        head, _, rest = bytes(buf).partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode("latin-1"))
        buf = bytearray(rest)
        payload = json.dumps(
            {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
            }
        ).encode()
        mask = os.urandom(4)
        n = len(payload)
        header = bytes([0x81]) + (
            bytes([0x80 | n])
            if n < 126
            else (
                bytes([0x80 | 126]) + struct.pack(">H", n)
                if n < 65536
                else bytes([0x80 | 127]) + struct.pack(">Q", n)
            )
        )
        sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        message = b""
        while True:
            b0, b1 = _ws_recv_exact(sock, 2, buf)
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", _ws_recv_exact(sock, 2, buf))[0]
            elif length == 127:
                length = struct.unpack(">Q", _ws_recv_exact(sock, 8, buf))[0]
            data = _ws_recv_exact(sock, length, buf)
            if b0 & 0x0F == 0x8:
                raise ConnectionError("DevTools closed the socket")
            message += data
            if not b0 & 0x80:
                continue  # a fragment: the rest follows
            reply, message = json.loads(message), b""
            if reply.get("id") != 1:
                continue
            result = reply.get("result", {})
            if "exceptionDetails" in result:
                raise RuntimeError(f"page threw: {result['exceptionDetails'].get('text')}")
            return result.get("result", {}).get("value")
    finally:
        sock.close()


def page_try(expression: str, default=None):
    try:
        return page_eval(expression)
    except Exception:
        return default


def click_testid(testid: str) -> bool:
    """Click the page's control with this data-testid, as the operator does; False when it is not
    there or is disabled."""
    return bool(
        page_try(
            f"(() => {{ const e = document.querySelector('[data-testid=\"{testid}\"]');"
            " if (!e || e.disabled) return false; e.click(); return true })()",
            False,
        )
    )


def switch_on(testid: str):
    """aria-checked of a switch, as True/False; None while it is absent or disabled (not loaded)."""
    value = page_try(
        f"(() => {{ const e = document.querySelector('[data-testid=\"{testid}\"]');"
        " return e && !e.disabled ? e.getAttribute('aria-checked') : null })()"
    )
    return None if value is None else value == "true"


# Every in-app toast the page draws, recorded as it appears and each time its text changes: a
# toast lasts 8 s, so a read made after it has gone would miss it, and a notice that arrives within
# 4 s of another is merged into the same toast in place (lib/notify/notifier.ts BURST_MS).
TOAST_RECORDER = """(() => {
  if (window.__awToasts) return true;
  window.__awToasts = [];
  const last = new WeakMap();
  const take = () => document.querySelectorAll('.aw-toast').forEach((t) => {
    const text = t.innerText;
    if (last.get(t) === text) return;
    last.set(t, text);
    window.__awToasts.push({ text, tone: t.getAttribute('data-tone'), at: Date.now() });
  });
  new MutationObserver(take).observe(document.body,
    { childList: true, subtree: true, characterData: true });
  take();
  return true;
})()"""
TOAST_QUIET_FOR = """(() => {
  const at = (window.__awToasts || []).reduce((m, t) => Math.max(m, t.at), 0);
  return at ? Date.now() - at : 1e9;
})()"""


def page_toasts() -> list[dict]:
    return page_try("window.__awToasts || []", []) or []


# --- the foreground ----------------------------------------------------------------------------

user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
kernel32 = ctypes.WinDLL("kernel32")


def foreground(hwnd: int) -> bool:
    return user32.GetForegroundWindow() == hwnd


def bring_front(hwnd: int) -> str:
    """Put the window in front; returns how ("" when nothing worked).

    Windows refuses SetForegroundWindow to a process that did not receive the last input, which
    is this drive whenever it runs unattended; so, in turn: the Alt tap, joining the foreground
    thread's input, and as a last resort a real click on the window's caption, as the operator's
    own click would do (the cursor is put back)."""
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.AllowSetForegroundWindow(d.ASFW_ANY)
    user32.keybd_event(0x12, 0, 0, 0)  # a tap of Alt lets this process take the foreground
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    if wait_for(lambda: foreground(hwnd), 2, 0.1):
        return "SetForegroundWindow"
    fg = user32.GetForegroundWindow()
    theirs = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    mine = kernel32.GetCurrentThreadId()
    if theirs and theirs != mine and user32.AttachThreadInput(mine, theirs, True):
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            user32.AttachThreadInput(mine, theirs, False)
        if wait_for(lambda: foreground(hwnd), 2, 0.1):
            return "AttachThreadInput"
    rect, cursor = wintypes.RECT(), wintypes.POINT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and user32.GetCursorPos(ctypes.byref(cursor)):
        user32.SetCursorPos(rect.left + min(200, (rect.right - rect.left) // 3), rect.top + 12)
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
        user32.SetCursorPos(cursor.x, cursor.y)
        if wait_for(lambda: foreground(hwnd), 2, 0.1):
            return "a click on its caption"
    return ""


def precondition(name: str, ok: bool, detail: str = "") -> bool:
    """A step's precondition: when it cannot be established that is a failure in its own right,
    and the checks that rest on it are skipped rather than counted."""
    return check(f"{name} (precondition established)", ok, detail)


# --- the shell link and the user's environment -------------------------------------------------

LINK_KEY = r"Software\Classes\agentweave"
ENV_KEY = "Environment"


def _read_values(path: str) -> dict[str, dict] | None:
    """Every value under HKCU\\path and its subkeys, {subkey: {name: (data, type)}}; None if absent."""
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        return None
    out: dict[str, dict] = {}

    def walk(key, sub: str):
        values, i = {}, 0
        while True:
            try:
                name, data, kind = winreg.EnumValue(key, i)
            except OSError:
                break
            values[name] = (data, kind)
            i += 1
        out[sub] = values
        j = 0
        while True:
            try:
                child = winreg.EnumKey(key, j)
            except OSError:
                break
            with winreg.OpenKey(key, child) as k:
                walk(k, f"{sub}\\{child}" if sub else child)
            j += 1

    with root:
        walk(root, "")
    return out


def _delete_tree(path: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            children = []
            while True:
                try:
                    children.append(winreg.EnumKey(key, len(children)))
                except OSError:
                    break
        for child in children:
            _delete_tree(f"{path}\\{child}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


class SavedLink:
    """The `agentweave:` registration as the drive found it; every scratch launch rewrites it to
    run this checkout, so it is put back on exit."""

    def __init__(self):
        self.values = _read_values(LINK_KEY)

    def restore(self) -> None:
        _delete_tree(LINK_KEY)
        if self.values is None:
            return
        for sub, values in self.values.items():
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, f"{LINK_KEY}\\{sub}" if sub else LINK_KEY
            ) as k:
                for name, (data, kind) in values.items():
                    winreg.SetValueEx(k, name, 0, kind, data)


def _announce_environment() -> None:
    """WM_SETTINGCHANGE "Environment": Explorer re-reads the user's variables for what it starts."""
    result = wintypes.DWORD()
    user32.SendMessageTimeoutW(
        wintypes.HWND(0xFFFF),
        0x001A,
        0,
        ctypes.c_wchar_p(ENV_KEY),
        0x0002,
        5000,
        ctypes.byref(result),
    )


class ShellWebviewEnv:
    """For the activation step only: the scratch WebView2 variables in HKCU\\Environment, so the
    window Explorer's handler opens has a page this drive can read. Restored on exit, and short-
    lived on purpose: while set, any WebView2 app the operator starts would share the scratch folder.
    """

    def __init__(self):
        self.saved: dict[str, tuple | None] = {}

    def __enter__(self):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENV_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
            for name, value in WEBVIEW_ENV.items():
                try:
                    self.saved[name] = winreg.QueryValueEx(k, name)
                except OSError:
                    self.saved[name] = None
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        _announce_environment()
        # Also this process's own, in case the explorer.exe it starts runs the handler itself
        # rather than passing the link to the running shell.
        self.process = {name: os.environ.get(name) for name in WEBVIEW_ENV}
        os.environ.update(WEBVIEW_ENV)
        return self

    def __exit__(self, *exc):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENV_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
            for name, old in self.saved.items():
                if old is None:
                    try:
                        winreg.DeleteValue(k, name)
                    except OSError:
                        pass
                else:
                    winreg.SetValueEx(k, name, 0, old[1], old[0])
        _announce_environment()
        for name, old in self.process.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        return False


def close_all(app: "WinApp") -> None:
    for w in app.windows():
        d.close_window(w["hwnd"])
    wait_for(lambda: not app.windows(), 15, 0.2)
    time.sleep(2.0)


def open_link(link: str) -> None:
    """As a click does: hand the registered agentweave: link to the shell."""
    subprocess.Popen(["explorer.exe", link], creationflags=NO_WINDOW)


def link_of(xml: str) -> str:
    m = re.search(r'launch="([^"]+)"', xml)
    return (m.group(1) if m else "").replace("&amp;", "&")


def text_of(xml: str) -> str:
    return " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", xml))


# --- scratch project ---------------------------------------------------------------------------


def project_of(app: WinApp) -> str:
    _, rows = app.api("GET", "/projects")
    rows = rows if isinstance(rows, list) else (rows or {}).get("projects", [])
    for p in rows:
        if (
            pathlib.Path(p.get("path") or p.get("working_directory") or "").resolve()
            == app.cwd.resolve()
        ):
            return p["id"]
    _, p = app.api("POST", "/projects/open", {"path": str(app.cwd), "name": app.cwd.name})
    return p["id"]


def make_agent(app: WinApp, project: str, name: str, model: str) -> None:
    a = f"/projects/{project}"
    app.api("PATCH", a, {"main_branch": "main"})
    _, runner = app.api(
        "POST", f"{a}/runners", {"name": f"r-{name}", "cli": "claude", "model": model}
    )
    if not isinstance(runner, dict) or "id" not in runner:
        raise SystemExit(f"runner for {name}: {runner}")
    app.api("POST", f"{a}/agents", {"name": name, "runner_id": runner["id"]})


def ask(app: WinApp, project: str, agent: str, blocking: bool = False) -> str | None:
    """A question as the operator's API takes it (non-blocking: no run to wait on)."""
    code, q = app.api(
        "POST",
        f"/projects/{project}/questions",
        {
            "from_agent": agent,
            "question": f"{agent}: does the call come through?",
            "header": "Drive",
            "options": [
                {"label": "Yes", "description": "ok"},
                {"label": "No", "description": "no"},
            ],
            "multi_select": False,
        },
    )
    return q.get("id") if isinstance(q, dict) else None


def trigger(app: WinApp, project: str, agent: str, message: str) -> str | None:
    code, run = app.api(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": agent, "session_mode": "new", "message": message},
    )
    return run.get("run_id") if isinstance(run, dict) else None


def settings_get(app: WinApp):
    return app.api("GET", NOTIFY_SETTINGS_PATH)


# --- the steps ---------------------------------------------------------------------------------


def step_event(app, stream, project):
    """c-event: a question asked from a conversation carries conversation_id."""
    run = trigger(
        app,
        project,
        "haikubot",
        "Call the ask_user tool once with the question 'Does the call come through?' and two "
        "options, Yes and No. Do nothing else until it is answered.",
    )
    check("c-event: a Haiku turn started", bool(run))
    got = wait_for(
        lambda: [e for e in stream.of("question_asked") if e.get("from_agent") == "haikubot"],
        90,
        1.0,
    )
    check("c-event: the Haiku agent's question reached the operator stream", bool(got))
    if got:
        ev = got[0]
        check("c-event: question_asked has conversation_id", "conversation_id" in ev, f"{ev}")
        rows = app.db("select conversation_id from questions where id=?", (ev.get("id"),))
        check(
            "c-event: it names the conversation the question belongs to",
            bool(rows) and rows[0][0] is not None and ev.get("conversation_id") == rows[0][0],
            f"{ev} vs {rows}",
        )
        check(
            "c-event: an old-style consumer still parses it (id, from_agent, blocking intact)",
            {"id", "from_agent", "blocking"} <= set(ev),
            f"{sorted(ev)}",
        )
    return run


# The recorded sequence of every kind of event (blocking and non-blocking question, permission
# request, failed run, finished loop, agent reply, and the silent ones) is replayed through the Hub
# by hub/tests/test_operator_notices.py -- that is where c-notice's exact-sequence check lives.
# This drive checks the same contract on what it can cause live.
NON_SILENT = {
    "question_asked",
    "permission_requested",
    "run_failed",
    "loop_stopped",
    "run_completed",
}
CONTRACT = {"id", "kind", "project_id", "agent", "conversation_id", "title", "text", "source_event"}


def step_notice(app, stream, project):
    """c-notice (early): the Haiku question made exactly one ask notice, with the whole contract."""
    notices = stream.of("operator_notice")
    check(
        "c-notice: the operator stream carries operator_notice events",
        bool(notices),
        f"{len(notices)} notices; events seen: {sorted({n for n, _ in stream.events})}",
    )
    asks = [n for n in notices if n.get("kind") == "ask" and n.get("agent") == "haikubot"]
    check(
        "c-notice: the Haiku question made exactly one ask notice with a stable id",
        len(asks) == 1 and bool(asks[0].get("id")),
        f"{asks}",
    )
    for n in notices:
        check(
            f"c-notice: notice {n.get('id')} has the whole contract",
            CONTRACT <= set(n),
            f"{sorted(n)}",
        )


def step_notice_final(stream):
    """c-notice (late): over every event the drive caused so far, one notice per non-silent one."""
    events = [(n, d_) for n, d_ in list(stream.log) if n != "operator_notice"]
    notices = stream.logged("operator_notice")
    silent = [n for n in notices if n.get("source_event") not in NON_SILENT]
    check("c-notice: no notice for run_started or any other silent event", not silent, f"{silent}")
    check(
        "c-notice: notice ids are unique (one notice per event)",
        bool(notices) and len({n.get("id") for n in notices}) == len(notices),
        f"{len(notices)} notices",
    )
    for source, want in (
        ("question_asked", [d_ for n, d_ in events if n == "question_asked"]),
        ("run_failed", [d_ for n, d_ in events if n == "run_failed"]),
        (
            "run_completed",
            [
                d_
                for n, d_ in events
                if n == "run_completed" and d_.get("initiator") != "autonomous"
            ],
        ),
    ):
        if not want:
            note(f"c-notice: no {source} event was caused by this drive; nothing to count")
            continue
        got = [n for n in notices if n.get("source_event") == source]
        check(
            f"c-notice: one notice per non-silent {source} event",
            len(got) == len(want),
            f"{len(got)} notices for {len(want)} events",
        )


def step_behind(app, stream, shell, hwnd, project):
    """c-behind: window open and minimized, Haiku calls ask_user -> one notification within 5 s."""
    user32.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(1.0)
    check("c-behind: the window is minimized", bool(user32.IsIconic(hwnd)))
    shell.mark()
    stream.events.clear()
    trigger(
        app,
        project,
        "behindbot",
        "Call the ask_user tool once with the question 'Behind: does it come through?' and two "
        "options, Yes and No. Do nothing else until it is answered.",
    )
    asked = wait_for(
        lambda: [e for e in stream.of("question_asked") if e.get("from_agent") == "behindbot"],
        90,
        1.0,
    )
    check("c-behind: the agent called ask_user", bool(asked))
    t0 = time.monotonic()
    got = shell.wait_new("behindbot", LIMIT)
    took = time.monotonic() - t0
    check(
        f"c-behind: one Windows notification within {LIMIT:.0f} s of the question",
        len(got) == 1,
        f"{len(got)} under {AUMID}, {took:.1f} s after the question",
    )
    return got[0] if got else None


def step_identity(toast, xml_extra=""):
    """c-identity: source AgentWeave, the packaged icon, text names the agent."""
    check("c-identity: a notification was shown to read", toast is not None)
    if toast is None:
        return
    check("c-identity: its source is AgentWeave.Hub", toast["aumid"] == AUMID, toast["aumid"])
    check(
        "c-identity: its text names the agent",
        "behindbot" in text_of(toast["xml"]),
        text_of(toast["xml"]),
    )
    ps = (
        "$lnk = Get-ChildItem -Recurse -Filter 'AgentWeave*.lnk' "
        "([Environment]::GetFolderPath('Programs')) | Select-Object -First 1; "
        "if ($lnk) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk.FullName); "
        "$lnk.BaseName; $s.IconLocation; "
        "(Get-StartApps | Where-Object { $_.Name -eq $lnk.BaseName } | "
        "ForEach-Object { $_.AppID }) -join ';' }"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=0x08000000,
    ).stdout.splitlines()  # by line: an icon path may hold spaces (Program Files)
    out = [line.strip() for line in out if line.strip()]
    icon = (out[1] if len(out) > 1 else "").rsplit(",", 1)[0]
    ids = (out[2] if len(out) > 2 else "").split(";")
    packaged = ROOT / "src" / "agentweave" / "assets" / "icon.ico"
    check(
        "c-identity: the Start-menu shortcut's AppUserModelID is AgentWeave.Hub",
        AUMID in ids,
        f"{out}",
    )
    check(
        "c-identity: that shortcut shows the packaged icon",
        bool(icon) and pathlib.Path(icon).name == packaged.name,
        f"{out}",
    )


def step_in_front(app, stream, shell, proc, hwnd, project):
    """c-in-front: in front -> none; closed while a second asked -> one; reopened while a third -> one."""
    how = bring_front(hwnd)
    if precondition(
        "c-in-front: the window is in front",
        bool(how),
        f"foreground {user32.GetForegroundWindow()}, the window {hwnd}",
    ):
        note(f"c-in-front: brought to the front by {how}")
        shell.mark()
        ask(app, project, "frontone")
        time.sleep(LIMIT + 1)
        first = shell.new("frontone")
        still = foreground(hwnd)
        if precondition(
            "c-in-front: it stayed in front while the first question was asked",
            still,
            f"foreground {user32.GetForegroundWindow()}, the window {hwnd}",
        ):
            check("c-in-front: no notification for the first question", not first, f"{len(first)}")
    else:
        note(
            "c-in-front: the first-question check is skipped: its precondition was not established"
        )

    d.close_window(hwnd)
    ask(app, project, "fronttwo")  # asked at the same moment the window closes
    wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.1)
    second = shell.wait_new("fronttwo", 10)
    time.sleep(LIMIT)
    second = shell.new("fronttwo")
    check("c-in-front: exactly one for the second question", len(second) == 1, f"{len(second)}")

    p2 = app.launch()
    ask(app, project, "frontthree")  # asked while the window comes back
    h2 = app.wait_window(p2, 60)
    check("c-in-front: the window reopened", h2 is not None)
    time.sleep(LIMIT + 3)
    third = shell.new("frontthree")
    check("c-in-front: exactly one for the third question", len(third) == 1, f"{len(third)}")
    return h2


def step_closed(app, stream, shell, hwnd, project, watch):
    """c-closed: window closed, 'closing leaves AgentWeave running' on, a failing run -> a notification.

    The failure and a question both land in the first seconds after the close (the moment the
    watcher takes over from the window, WNWCO-7), not only once the watcher is long up: the run is
    started with the window open and made to fail as it closes."""
    if not (hwnd and user32.IsWindow(hwnd)):
        p = app.launch()
        hwnd = app.wait_window(p, 90)
        time.sleep(4.0)
    if not precondition("c-closed: a window is open to close", bool(hwnd)):
        return
    before = set(watch.ours)

    def claude_children() -> set[int]:
        rows = d.processes()
        hub = set(d.hub_pids(app.port, rows))
        return {
            r["ProcessId"]
            for r in rows
            if r["ParentProcessId"] in hub and "claude" in (r.get("CommandLine") or "").lower()
        }

    existing = claude_children()  # haikubot's and behindbot's blocked turns: not to be touched
    run = trigger(
        app,
        project,
        "failbot",
        "Run this shell command and wait for it: powershell -NoProfile -Command Start-Sleep -Seconds 120",
    )
    check("c-closed: failbot's turn started", bool(run))
    mine: set[int] = set()
    if run and wait_for(lambda: d.run_status(app, run) == "running", 90, 1.0):
        mine = wait_for(lambda: claude_children() - existing, 60, 1.0) or set()
        time.sleep(8.0)  # let the turn get into its tool call
    if not precondition("c-closed: failbot's turn is running under the Hub", bool(mine)):
        return
    shell.mark()
    stream.events.clear()
    # Made to fail as the window closes: only this run's CLI process (the one that appeared after
    # the trigger) is killed under it, which the Hub records as run_failed.
    closed_at = time.monotonic()
    d.close_window(hwnd)
    for pid in mine | (claude_children() - existing):
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW
        )
    time.sleep(max(0.0, 1.0 - (time.monotonic() - closed_at)))
    asked_after = time.monotonic() - closed_at
    ask(app, project, "closedask")  # a question inside the first 2 s, too
    gone = wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.1)
    check("c-closed: the window closed", bool(gone))
    precondition(
        "c-closed: the question was asked within 2 s of the close",
        asked_after <= 2.0,
        f"{asked_after:.1f} s",
    )

    def failures_seen() -> list[dict]:
        return [
            e
            for e in stream.of("run_failed")
            if e.get("run_id") == run or e.get("agent") == "failbot"
        ]

    # One poll for everything, so each notification's time is when it appeared, not when a
    # later wait got round to looking.
    first_seen: dict[str, float] = {}
    deadline = closed_at + 120
    while time.monotonic() < deadline:
        now = time.monotonic()
        for needle in ("closedask", "failbot"):
            if needle not in first_seen and shell.new(needle):
                first_seen[needle] = now
        failed = failures_seen()
        q_done = "closedask" in first_seen or now - closed_at > asked_after + LIMIT + 1
        f_done = failed and ("failbot" in first_seen or now - failed[0]["_seen"] > LIMIT + 1)
        if q_done and f_done:
            break
        time.sleep(0.25)
    time.sleep(1.0)  # a duplicate would show by now
    got_q = shell.new("closedask")
    q_took = first_seen.get("closedask", float("inf")) - closed_at - asked_after
    check(
        f"c-closed: exactly one notification, within {LIMIT:.0f} s, for the question asked "
        f"{asked_after:.1f} s after the close",
        len(got_q) == 1 and q_took <= LIMIT,
        f"{len(got_q)} under {AUMID}, {q_took:.1f} s after the question",
    )
    check("c-closed: the Hub still runs with the window closed", d.healthy(app.port))
    failed = failures_seen()
    check("c-closed: the run made to fail failed", bool(failed))
    if failed:
        note(f"c-closed: run_failed arrived {failed[0]['_seen'] - closed_at:.1f} s after the close")
        got = shell.new("failbot")
        took = first_seen.get("failbot", float("inf")) - failed[0]["_seen"]
        check(
            f"c-closed: a notification within {LIMIT:.0f} s of the failure",
            len(got) >= 1 and took <= LIMIT,
            f"{len(got)} under {AUMID}, {took:.1f} s after run_failed",
        )
    check(
        "c-closed: no conhost or powershell window was shown",
        set(watch.ours) == before and not watch.others,
        f"{[v for k, v in watch.ours.items() if k not in before]} {watch.others}",
    )


def step_click(app, stream, shell, project):
    """c-click: the activation link, opened through the shell, opens the conversation."""
    shell.mark()
    stream.events.clear()
    run = trigger(
        app,
        project,
        "clickbot",
        "Call the ask_user tool once with the question 'Click: does it come through?' and two "
        "options, Yes and No. Do nothing else until it is answered.",
    )
    wait_for(
        lambda: [e for e in stream.of("question_asked") if e.get("from_agent") == "clickbot"],
        90,
        1.0,
    )
    got = shell.wait_new("clickbot", 10)
    check("c-click: the question's notification was shown", bool(got))
    link = link_of(got[0]["xml"]) if got else ""
    check("c-click: it carries an agentweave: link", link.startswith("agentweave:"), link)
    hub = d.hub_pids(app.port)
    conv = None
    ev = [e for e in stream.of("question_asked") if e.get("from_agent") == "clickbot"]
    if ev:
        conv = ev[0].get("conversation_id")
    if not (
        precondition("c-click: a link to open", link.startswith("agentweave:"), link)
        & precondition("c-click: no window is open", not app.windows(), f"{app.windows()}")
        & precondition(
            "c-click: the Hub is running clickbot's turn",
            bool(run) and d.run_status(app, run) == "running" and bool(hub),
            f"run {run} {d.run_status(app, run) if run else ''}, Hub {hub}",
        )
    ):
        return None
    # The handler Explorer starts gets the user's environment, not this drive's: for this one
    # launch the page's debugging variables are the user's too, then put back.
    with ShellWebviewEnv():
        open_link(link)
        found = wait_for(app.windows, 60, 0.2)
        h = found[0]["hwnd"] if found else None
        check("c-click: a window opens", bool(h), f"{all_app_windows()}")
        url = app_page(app.port, 30)
    precondition("c-click: the opened window's page is readable", bool(url))
    if url:
        wait_for(lambda: conv and conv in page_url(), 10, 0.5)
        url = page_url()
        check(
            "c-click: it opens on that agent's conversation",
            bool(conv) and conv in url and "agent=clickbot" in url,
            f"{url} vs {conv}",
        )
    check(
        "c-click: the Hub's process id is unchanged",
        d.hub_pids(app.port) == hub,
        f"{hub} -> {d.hub_pids(app.port)}",
    )
    check(
        "c-click: the running turn is unchanged (same run, still running)",
        bool(run) and d.run_status(app, run) == "running",
        d.run_status(app, run) if run else "no run",
    )
    if not h:
        return None
    user32.ShowWindow(h, SW_MINIMIZE)
    time.sleep(1.0)
    if not precondition("c-click: the window is minimized", bool(user32.IsIconic(h))):
        return h
    shell.mark()
    ask(app, project, "clicktwo")  # no conversation: its link names the project's overview
    got2 = shell.wait_new("clicktwo", 10)
    link2 = link_of(got2[0]["xml"]) if got2 else ""
    if not precondition("c-click: a second notification with a link", bool(link2), link2):
        return h
    before = page_url()
    open_link(link2)
    wait_for(lambda: not user32.IsIconic(h), 15, 0.2)
    time.sleep(2.0)
    check("c-click: with a window open and minimized, it is restored", not user32.IsIconic(h))
    check(
        "c-click: and it navigates there (the project's overview, no second window)",
        len(app.windows()) == 1 and "tab=overview" in page_url() and page_url() != before,
        f"{len(app.windows())} windows; {before} -> {page_url()}",
    )
    check(
        "c-click: and the running turn is still the same one",
        d.run_status(app, run) == "running",
        d.run_status(app, run),
    )
    return h


def step_quiet(app, stream, shell, project):
    """c-quiet: AW_TOAST_COMMAND failing -> in-app toast/sound/flash still happen, no error, run goes on."""
    close_all(app)
    app.cleanup()
    app.toast_command = f'"{sys.executable}" -c "import sys; sys.exit(7)"'
    p = app.launch()
    h = app.wait_window(p, 90)
    app.wait_healthy()
    time.sleep(6.0)
    check("c-quiet: the window opens with a failing toast command", h is not None)
    if not h:
        return
    readable = bool(app_page(app.port)) and bool(
        wait_for(lambda: page_try(TOAST_RECORDER), 30, 1.0)
    )
    if not precondition("c-quiet: the app's page is readable (DevTools)", readable, page_url()):
        return
    project = project_of(app)
    run = trigger(
        app,
        project,
        "quietbot",
        "Run: powershell -NoProfile -Command Start-Sleep -Seconds 60 . Then say done.",
    )
    user32.ShowWindow(h, SW_MINIMIZE)
    time.sleep(1.0)
    if not precondition("c-quiet: the window is minimized", bool(user32.IsIconic(h))):
        return
    shell.mark()
    stream.events.clear()
    page_try(TOAST_RECORDER)  # again, in case the page reloaded since: a no-op otherwise
    # Whatever the page was already toasting (a restarted Hub asks its open questions again) must
    # be over first, or the question below is merged into it and never named on its own.
    settled = wait_for(lambda: (page_try(TOAST_QUIET_FOR, 0) or 0) > 5000, 60, 0.5)
    if not precondition(
        "c-quiet: the page's earlier toasts are over", bool(settled), f"{page_toasts()}"
    ):
        return
    ask(app, project, "quietone")
    toast = wait_for(
        lambda: [t for t in page_toasts() if "quietone" in (t.get("text") or "")], LIMIT + 3, 0.5
    )
    notices = [n for n in stream.of("operator_notice") if n.get("agent") == "quietone"]
    check(
        "c-quiet: the notice was published (the in-app toast is drawn from it)",
        len(notices) == 1,
        f"{len(notices)}",
    )
    check(
        "c-quiet: the in-app toast still shows in the page",
        bool(toast),
        f"toasts seen: {page_toasts()}",
    )
    # The page's attention call is what flashes the taskbar button and counts in the title; the
    # flash itself and the sound have no read Windows exposes, so the count is the observable.
    title = page_try("document.title", "") or ""
    check(
        "c-quiet: the page still called attention (a count in the title, the taskbar flash's call)",
        title.startswith("("),
        title,
    )
    note(
        "c-quiet: the sound and the flash themselves are NOT observed -- Windows exposes no read "
        "of either; the toast and the title count above show the page's notifier still ran"
    )
    errors = [t for t in page_toasts() if t.get("tone") == "error"]
    check("c-quiet: no error toast in the page", not errors, f"{errors}")
    shown = shell.new("quietone")
    check(
        "c-quiet: no Windows notification, no error window",
        not shown and len(app.windows()) == 1,
        f"{len(shown)} notifications, {len(app.windows())} windows",
    )
    check(
        "c-quiet: the run continues",
        d.run_status(app, run) in ("running", "queued", "starting", "completed"),
        d.run_status(app, run) if run else "no run",
    )
    d.close_window(h)
    wait_for(lambda: not user32.IsWindow(h), 15, 0.1)
    time.sleep(3.0)
    ask(app, project, "quiettwo")
    published = wait_for(
        lambda: [n for n in stream.of("operator_notice") if n.get("agent") == "quiettwo"],
        LIMIT,
        0.25,
    )
    time.sleep(1.0)
    check("c-quiet: with the window closed, the notice is still published", bool(published))
    check("c-quiet: with the window closed, the Hub carries on", d.healthy(app.port))
    check("c-quiet: and still no error window", not app.windows(), f"{app.windows()}")
    check(
        "c-quiet: and the run continues",
        d.run_status(app, run) in ("running", "queued", "starting", "completed"),
        d.run_status(app, run) if run else "no run",
    )


def step_kinds(app, stream, shell):
    """c-kinds: defaults, a changed choice through the page, a restart, and the choice applied with
    the window closed. Without the change made, the closed-window checks are skipped: under the
    defaults they would pass for the wrong reason."""
    want_default = {"ask": True, "fail": True, "done": False, "reply": False}
    want_changed = {"ask": False, "fail": True, "done": False, "reply": True}
    code, body = settings_get(app)
    check(
        "c-kinds: defaults read question and failure on, done and reply off",
        code == 200 and body == want_default,
        f"{code} {body}",
    )
    # c-quiet left a failing shell command in place; c-kinds must see real toasts.
    app.cleanup()
    app.toast_command = None
    p0 = app.launch()
    h0 = app.wait_window(p0, 90)
    app.wait_healthy()
    if not precondition(
        "c-kinds: a window with a readable page",
        h0 is not None and bool(app_page(app.port)),
        page_url(),
    ):
        return
    # Through the page, as the operator does: App settings from the rail, then the Windows switches.
    opened = wait_for(lambda: click_testid("rail-app-settings"), 30, 1.0) and wait_for(
        lambda: "appSettings=" in page_url(), 10, 0.5
    )
    check("c-kinds: App settings opens in the page", bool(opened), page_url())
    loaded = wait_for(
        lambda: switch_on("windows-notify-reply") is not None
        and switch_on("windows-notify-ask") is not None,
        30,
        0.5,
    )
    if not precondition("c-kinds: the page shows the Windows switches", bool(loaded), page_url()):
        return
    check(
        "c-kinds: the page's switches show the defaults (question on, reply off)",
        switch_on("windows-notify-ask") is True and switch_on("windows-notify-reply") is False,
    )
    click_testid("windows-notify-reply")
    wait_for(lambda: switch_on("windows-notify-reply") is True, 10, 0.25)
    wait_for(lambda: switch_on("windows-notify-ask") is not None, 10, 0.25)  # the save settles
    click_testid("windows-notify-ask")
    wait_for(lambda: switch_on("windows-notify-ask") is False, 10, 0.25)
    wait_for(lambda: settings_get(app)[1] == want_changed, 10, 0.5)
    code, body = settings_get(app)
    if not precondition(
        "c-kinds: the page's switches reached the Hub ('reply' on, 'question' off)",
        code == 200 and body == want_changed,
        f"{code} {body}",
    ):
        note("c-kinds: the restart and closed-window checks are skipped: nothing was changed")
        return
    app.cleanup()
    p = app.launch()
    app.wait_window(p, 90)
    app.wait_healthy()
    code, body = settings_get(app)
    check(
        "c-kinds: after a restart the changed choices are still in force",
        code == 200 and body == want_changed,
        f"{code} {body}",
    )
    app_page(app.port)
    check(
        "c-kinds: and the page shows them after the restart",
        bool(
            wait_for(
                lambda: click_testid("rail-app-settings")
                and switch_on("windows-notify-reply") is True
                and switch_on("windows-notify-ask") is False,
                30,
                1.0,
            )
        ),
    )
    close_all(app)
    if not precondition("c-kinds: the window is closed", not app.windows()):
        return
    time.sleep(1.0)
    project = project_of(app)
    shell.mark()
    ask(app, project, "kindquestion")
    published = wait_for(
        lambda: [n for n in stream.of("operator_notice") if n.get("agent") == "kindquestion"],
        LIMIT,
        0.25,
    )
    precondition("c-kinds: the question's notice was published", bool(published))
    time.sleep(LIMIT + 1)
    shown = shell.new("kindquestion")
    check(
        "c-kinds: with the window closed a question gives no Windows notification",
        not shown,
        f"{len(shown)}",
    )
    # A reply: a run the operator started in a conversation, finished while the window is closed.
    stream.events.clear()
    trigger(app, project, "replybot", "Say hello in one word.")
    replied = wait_for(
        lambda: [
            n
            for n in stream.of("operator_notice")
            if n.get("agent") == "replybot" and n.get("kind") == "reply"
        ],
        120,
        1.0,
    )
    if precondition("c-kinds: replybot's turn made a reply notice", bool(replied)):
        shell.wait_new("replybot", LIMIT)
        time.sleep(1.0)
        got = shell.new("replybot")
        check("c-kinds: and a reply gives one", len(got) == 1, f"{len(got)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8180)
    opts = parser.parse_args()
    if opts.port in d.FORBIDDEN_PORTS:
        raise SystemExit(f"refusing port {opts.port}: :8000 and :8010 are never driven")
    if not d.port_free(opts.port):
        raise SystemExit(f"scratch port {opts.port} already in use; pick another --port")
    if os.name != "nt" or not WPN_DIR.exists():
        raise SystemExit("this drive reads Windows' notification store; run it on Windows")

    profile = PROFILE_PREFIX + RUN
    app = WinApp(opts.port, profile, d.project_dir("wn"))
    close_file = d.HUB_HOME / "app-window" / f"close-{opts.port}.json"
    close_file.parent.mkdir(parents=True, exist_ok=True)
    close_file.write_text(json.dumps({"keep_running": True}), encoding="utf-8")
    app.baseline = {w["hwnd"] for w in all_app_windows()}  # the operator's: never ours
    link = SavedLink()
    shell = Shell()
    watch = d.ConsoleWatch(lambda: app.pids).start()
    stream = None
    try:
        p = app.launch()
        hwnd = app.wait_window(p, 90)
        if not check("the app window opens", hwnd is not None):
            return 1
        check("the Hub answers", app.wait_healthy())
        time.sleep(6.0)
        stream = Stream(app)
        project = project_of(app)
        for name, model in (
            ("haikubot", d.HAIKU),
            ("behindbot", d.HAIKU),
            ("clickbot", d.HAIKU),
            ("failbot", d.HAIKU),
            ("quietbot", d.HAIKU),
            ("replybot", d.HAIKU),
        ):
            make_agent(app, project, name, model)
        steps = [
            ("c-event", lambda: step_event(app, stream, project)),
            ("c-notice", lambda: step_notice(app, stream, project)),
            (
                "c-behind+c-identity",
                lambda: step_identity(step_behind(app, stream, shell, hwnd, project)),
            ),
            ("c-in-front", lambda: step_in_front(app, stream, shell, p, hwnd, project)),
        ]
        state = {"hwnd": hwnd}
        for label, fn in steps:
            try:
                r = fn()
                if label == "c-in-front":
                    state["hwnd"] = r or state["hwnd"]
            except Exception as exc:
                check(f"{label}: ran to the end", False, f"{type(exc).__name__}: {exc}")
        for label, fn in (
            ("c-closed", lambda: step_closed(app, stream, shell, state["hwnd"], project, watch)),
            ("c-click", lambda: step_click(app, stream, shell, project)),
            ("c-notice (all events)", lambda: step_notice_final(stream)),
            (
                "c-quiet",
                lambda: step_quiet(app, stream, shell, project),
            ),
            ("c-kinds", lambda: step_kinds(app, stream, shell)),
        ):
            try:
                fn()
            except Exception as exc:
                check(f"{label}: ran to the end", False, f"{type(exc).__name__}: {exc}")
    finally:
        if stream:
            stream.stop = True
        watch.stop()
        close_all(app)  # a window the link opened is no child of anything cleanup ends
        app.cleanup()
        close_file.unlink(missing_ok=True)
        link.restore()
        for path in [*(d.HUB_HOME / "profiles").glob(PROFILE_PREFIX + "*"), d.SCRATCH]:
            shutil.rmtree(path, ignore_errors=True)
    print("\n%d FAIL" % len(failures) if failures else "\nALL PASS", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
