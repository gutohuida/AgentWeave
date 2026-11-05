"""Acceptance drive for "AgentWeave is its own app on Windows" (spec/changes/agentweave-is-its-own-app-on-windows).

Written failing first (task AWOAW-1). Every step runs this checkout's CLI and Hub (its src/ and
hub/ on PYTHONPATH) on scratch ports and scratch profiles -- never :8000 (the operator's) or :8010
(the trial Hub), and never their databases. Nothing here calls those two Hubs: the listener table is
read from `netstat`, not by connecting, and their processes are only listed.

The app is started the way the desktop shortcut starts it: `_resolve_shortcut_target()` from this
checkout (`pythonw.exe -m agentweave`), with `--profile` and `--port` appended so it lands on a
scratch Hub.

Steps, each named after the criterion it checks:

  identity  (FR-1 taskbar-button, FR-7 drive-own-app) -- the window's shell properties, read from
            this process with SHGetPropertyStoreForWindow: app identity, relaunch command, relaunch
            display name, relaunch icon.
  console   (FR-3 no-console) -- the window list is sampled every 100 ms from the first launch to
            the end of the own-hub step, so it covers a project being used (the busy Hub's agent
            turn spawns claude and powershell); a visible console or terminal window belonging to a
            process any of the three apps started (or a new terminal window titled after one) fails
            it.
  second    (FR-4 second-launch-focuses) -- the window is minimized and the app launched again:
            one window, one Hub process, the same window restored and in front, the launcher gone.
  close     (FR-7 close-idle) -- WM_CLOSE to the window with nothing running: no prompt, and within
            30 s no Hub process for the port and the port free.
  own-hub   (FR-10 other-hub-survives) -- two Hubs on two more scratch ports, each with a window,
            one running a real Haiku turn. The idle one's window is closed: the busy Hub's pid and
            its turn are unchanged. Then the busy one's is closed and 'Stop it all' is chosen through
            the page (UI Automation, by the button's name): only the busy Hub's processes are gone,
            and whatever serves :8000 and :8010 is the same process as before.

Before the change (today's master) the drive fails on: the relaunch command (and the window's own
app identity, name and icon) being absent, the second launch opening a second window and staying,
and the Hub surviving the close. Each run starts from fresh scratch profiles and project folders,
named for the run, so a second run sees nothing the first one left. It cleans up after itself either way (`agentweave stop` on each
scratch port, then killing what it started).

  py -3.11 scripts/drive/d1105_own_app.py                 # every step
  py -3.11 scripts/drive/d1105_own_app.py --skip-own-hub  # without the Haiku turn
  py -3.11 scripts/drive/d1105_own_app.py --port 8171     # first of three scratch ports
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[2]
HUB_HOME = pathlib.Path.home() / ".agentweave" / "hub"
FORBIDDEN_PORTS = {8000, 8010}
PROFILE_PREFIX = "d1105own"
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "agentweave-d1105-own-app"
RUN = time.strftime("%H%M%S")  # names this run's profiles and project folders
PROFILE = f"{PROFILE_PREFIX}{RUN}"
HAIKU = "claude-haiku-4-5-20251001"
CLOSE_LIMIT = 30.0
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)
    return ok


def note(text: str) -> None:
    print(f"       {text}", flush=True)


# --- Win32 -------------------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32")
ole32 = ctypes.WinDLL("ole32")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]

WM_CLOSE = 0x0010
SW_MINIMIZE = 6
ASFW_ANY = 0xFFFFFFFF
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}
# A new terminal window owned by Windows Terminal (not by our process tree, since Windows 11 hands a
# new console to the default terminal) is ours if its title names one of the app's own processes.
OURS_IN_TITLE = re.compile(r"python|uvicorn|agentweave|claude|conhost|openconsole", re.I)


def _text(fn, hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    fn(hwnd, buf, 512)
    return buf.value


def top_windows() -> list[dict]:
    """Every top-level window: handle, owning pid, class, title, visible."""
    found: list[dict] = []

    def each(hwnd, _param):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append(
            {
                "hwnd": int(hwnd),
                "pid": pid.value,
                "cls": _text(user32.GetClassNameW, hwnd),
                "title": _text(user32.GetWindowTextW, hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
            }
        )
        return True

    user32.EnumWindows(WNDENUMPROC(each), 0)
    return found


def app_windows(pids: set[int]) -> list[dict]:
    """The visible pywebview (WinForms) app windows owned by `pids` -- never matched by title,
    because the operator's own app window carries the same one."""
    return [
        w
        for w in top_windows()
        if w["pid"] in pids and w["visible"] and w["cls"].startswith("WindowsForms")
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        h = text.strip("{}").replace("-", "")
        tail = bytes.fromhex(h[16:])
        return cls(
            int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16), (ctypes.c_ubyte * 8)(*tail)
        )


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("r1", ctypes.c_ushort),
        ("r2", ctypes.c_ushort),
        ("r3", ctypes.c_ushort),
        ("data", ctypes.c_void_p),
        ("pad", ctypes.c_void_p),
    ]


IID_IPropertyStore = GUID.parse("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
_APPUSERMODEL = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"
SHELL_KEYS = {
    "app_id": 5,  # PKEY_AppUserModel_ID
    "relaunch_command": 2,  # PKEY_AppUserModel_RelaunchCommand
    "relaunch_icon": 3,  # PKEY_AppUserModel_RelaunchIconResource
    "relaunch_name": 4,  # PKEY_AppUserModel_RelaunchDisplayNameResource
}
VT_LPWSTR = 31

shell32.SHGetPropertyStoreForWindow.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
]
ole32.PropVariantClear.argtypes = [ctypes.POINTER(PROPVARIANT)]
_GetValue = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)
)
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def shell_properties(hwnd: int) -> dict:
    """The window's AppUserModel properties as the shell reads them for its taskbar button and a
    pin, read from this (another) process. A property never set reads None."""
    ole32.CoInitialize(None)
    store = ctypes.c_void_p()
    hr = shell32.SHGetPropertyStoreForWindow(
        hwnd, ctypes.byref(IID_IPropertyStore), ctypes.byref(store)
    )
    if hr != 0 or not store:
        return {"error": f"SHGetPropertyStoreForWindow HRESULT {hr & 0xFFFFFFFF:#010x}"}
    vtable = ctypes.cast(
        ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p)
    )
    get_value = _GetValue(vtable[5])
    release = _Release(vtable[2])
    out: dict = {}
    try:
        for name, pid in SHELL_KEYS.items():
            key = PROPERTYKEY(GUID.parse(_APPUSERMODEL), pid)
            value = PROPVARIANT()
            if get_value(store, ctypes.byref(key), ctypes.byref(value)) != 0:
                out[name] = None
                continue
            out[name] = (
                ctypes.wstring_at(value.data) if value.vt == VT_LPWSTR and value.data else None
            )
            ole32.PropVariantClear(ctypes.byref(value))
    finally:
        release(store)
    return out


# --- processes and ports -----------------------------------------------------------------------


def processes() -> list[dict]:
    """Every process: ProcessId, ParentProcessId, Name, CommandLine."""
    done = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine"
            " | ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=0x08000000,  # CREATE_NO_WINDOW: the drive itself must not flash a console
    )
    rows = json.loads(done.stdout or "[]")
    return rows if isinstance(rows, list) else [rows]


def descendants(rows: list[dict], roots: set[int]) -> set[int]:
    tree = set(roots)
    grew = True
    while grew:
        grew = False
        for row in rows:
            if row["ParentProcessId"] in tree and row["ProcessId"] not in tree:
                tree.add(row["ProcessId"])
                grew = True
    return tree


def hub_pids(port: int, rows: list[dict] | None = None) -> list[int]:
    """The uvicorn processes serving `port`, by command line."""
    pattern = re.compile(rf"uvicorn.*--port[ =\"']+{port}\b")
    return sorted(
        r["ProcessId"] for r in (rows or processes()) if pattern.search(r.get("CommandLine") or "")
    )


def listeners() -> dict[int, set[int]]:
    """port -> pids listening on it, from the TCP table (no connection is made)."""
    done = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=0x08000000,
    )
    table: dict[int, set[int]] = {}
    for line in done.stdout.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[3] == "LISTENING":
            try:
                port = int(parts[1].rsplit(":", 1)[1])
                table.setdefault(port, set()).add(int(parts[4]))
            except ValueError:
                pass
    return table


def port_free(port: int) -> bool:
    return port not in listeners()


def wait_for(predicate, timeout: float, step: float = 0.5):
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value or time.monotonic() >= deadline:
            return value
        time.sleep(step)


def healthy(port: int) -> bool:
    if port in FORBIDDEN_PORTS:
        raise SystemExit(f"refusing to touch :{port}")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# --- the app -----------------------------------------------------------------------------------


def shortcut_command() -> tuple[str, list[str]]:
    """What the desktop shortcut runs, from this checkout's own code."""
    sys.path.insert(0, str(ROOT / "src"))
    from agentweave.cli import _resolve_shortcut_target

    target, arguments = _resolve_shortcut_target()
    return target, arguments.split()


def app_env() -> dict:
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "hub")]),
        "AGENTWEAVE_SOUND": "0",
    }
    env.pop("DATABASE_URL", None)  # the profile names the database, never an inherited one
    return env


def project_dir(name: str) -> pathlib.Path:
    """A scratch git repository the launch registers as its project (the shortcut's cwd)."""
    # Outside this checkout: a task worktree lives under a `.agentweave/` folder, and a launch from
    # inside one registered no project (2026-11-05, the first run of this drive).
    path = SCRATCH / RUN / name
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists():
        (path / "README.md").write_text("own-app drive\n", encoding="utf-8")
        for cmd in (
            ["git", "init", "-b", "main"],
            ["git", "config", "user.email", "d@example.invalid"],
            ["git", "config", "user.name", "d"],
            ["git", "add", "."],
            ["git", "commit", "-m", "x"],
        ):
            subprocess.run(cmd, cwd=path, check=True, capture_output=True)
    return path


class App:
    """One scratch Hub on one port, launched as the shortcut launches it."""

    def __init__(self, port: int, profile: str, cwd: pathlib.Path):
        if port in FORBIDDEN_PORTS:
            raise SystemExit(f"refusing port {port}: :8000 and :8010 are never driven")
        self.port, self.profile, self.cwd = port, profile, cwd
        self.launchers: list[subprocess.Popen] = []

    def launch(self) -> subprocess.Popen:
        target, args = shortcut_command()
        user32.AllowSetForegroundWindow(ASFW_ANY)  # as the shell grants the process a click starts
        proc = subprocess.Popen(
            [target, *args, "--profile", self.profile, "--port", str(self.port)],
            cwd=self.cwd,
            env=app_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.launchers.append(proc)
        return proc

    @property
    def pids(self) -> set[int]:
        return {p.pid for p in self.launchers}

    def windows(self) -> list[dict]:
        return app_windows(self.pids)

    def wait_window(self, proc: subprocess.Popen, timeout: float = 30) -> int | None:
        found = wait_for(lambda: app_windows({proc.pid}), timeout, 0.1)
        return found[0]["hwnd"] if found else None

    def wait_healthy(self, timeout: float = 120) -> bool:
        return bool(wait_for(lambda: healthy(self.port), timeout, 0.5))

    def key(self) -> str:
        for line in (HUB_HOME / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("AW_BOOTSTRAP_API_KEY="):
                return line.split("=", 1)[1].strip()
        raise SystemExit("no AW_BOOTSTRAP_API_KEY in the Hub folder's .env")

    def api(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/v1{path}",
            data,
            {"Authorization": "Bearer " + self.key(), "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")[:2000]

    def db(self, sql: str, args=()):
        path = HUB_HOME / "profiles" / self.profile / "agentweave.db"
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            return connection.execute(sql, args).fetchall()
        finally:
            connection.close()

    def cleanup(self) -> None:
        """Stop the scratch Hub and end every process this drive started for it."""
        target, args = shortcut_command()
        python = str(pathlib.Path(target).with_name("python.exe"))
        subprocess.run(
            [
                python,
                "-m",
                "agentweave",
                "stop",
                "--profile",
                self.profile,
                "--port",
                str(self.port),
            ],
            cwd=self.cwd,
            env=app_env(),
            capture_output=True,
            timeout=90,
            creationflags=0x08000000,
        )
        rows = processes()
        leftover = descendants(rows, set(hub_pids(self.port, rows)) | self.pids)
        for pid in leftover:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        for proc in self.launchers:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


class ConsoleWatch:
    """Samples the window list every 100 ms; collects console and terminal windows that appear."""

    def __init__(self, tree_roots):
        self.tree_roots = tree_roots  # callable -> set of pids the app started
        self.before = {w["hwnd"] for w in top_windows() if w["cls"] in CONSOLE_CLASSES}
        self.ours: dict[int, dict] = {}
        self.others: dict[int, dict] = {}
        self._stop = threading.Event()
        self._tree: set[int] = set()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "ConsoleWatch":
        self._thread.start()
        threading.Thread(target=self._refresh_tree, daemon=True).start()
        return self

    def _refresh_tree(self) -> None:
        while not self._stop.is_set():
            with contextlib.suppress(Exception):
                self._tree = descendants(processes(), self.tree_roots())
            self._stop.wait(1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            for w in top_windows():
                if w["cls"] not in CONSOLE_CLASSES or not w["visible"] or w["hwnd"] in self.before:
                    continue
                tree = self._tree | self.tree_roots()
                if w["pid"] in tree or OURS_IN_TITLE.search(w["title"]):
                    self.ours.setdefault(w["hwnd"], w)
                else:
                    self.others.setdefault(w["hwnd"], w)
            self._stop.wait(0.1)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


# --- steps -------------------------------------------------------------------------------------


def step_identity(app: App, hwnd: int) -> None:
    props = shell_properties(hwnd)
    note(f"window {hwnd:#x} shell properties: {props}")
    if "error" in props:
        check("identity: the window's shell properties can be read", False, props["error"])
        return
    app_id = props.get("app_id") or ""
    check(
        "identity: the window's app identity is AgentWeave's",
        "agentweave" in app_id.lower(),
        repr(app_id),
    )
    command = props.get("relaunch_command") or ""
    exe = re.match(r'\s*"([^"]+)"|\s*(\S+)', command)
    exe_path = pathlib.Path((exe.group(1) or exe.group(2)) if exe else "")
    check(
        "identity: the window carries a relaunch command that opens AgentWeave",
        bool(command) and "-m agentweave" in command and exe_path.is_file(),
        repr(command),
    )
    check(
        "identity: the relaunch command shows no console (pythonw, not python)",
        bool(command) and exe_path.name.lower() != "python.exe",
        exe_path.name or "no command",
    )
    check(
        "identity: the taskbar name is AgentWeave",
        (props.get("relaunch_name") or "") == "AgentWeave",
        repr(props.get("relaunch_name")),
    )
    icon = props.get("relaunch_icon") or ""
    icon_file = pathlib.Path(re.sub(r",-?\d+$", "", icon)) if icon else None
    check(
        "identity: the taskbar icon is AgentWeave's icon file",
        icon_file is not None
        and icon_file.is_file()
        and icon_file.name.lower() == "icon.ico"
        and icon_file.parent.name == "assets"
        and icon_file.parent.parent.name == "agentweave",
        repr(icon),
    )


def step_second_launch(app: App, hwnd: int) -> None:
    user32.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(1.0)
    check("second: the window was minimized before the launch", bool(user32.IsIconic(hwnd)))
    hubs_before = hub_pids(app.port)
    second = app.launch()
    exited = wait_for(lambda: second.poll() is not None, 30, 0.2)
    time.sleep(2.0)  # let a second window, if one is coming, show itself
    windows = app.windows()
    hubs = hub_pids(app.port)
    check("second: the launching process exits", bool(exited), f"exit code {second.poll()}")
    check(
        "second: one app window exists",
        len(windows) == 1,
        f"{len(windows)} window(s): {[hex(w['hwnd']) for w in windows]}",
    )
    check(
        "second: one Hub process exists, the same one",
        len(hubs) == 1 and hubs == hubs_before,
        f"before {hubs_before}, after {hubs}",
    )
    check(
        "second: the same window is restored",
        bool(user32.IsWindow(hwnd)) and not user32.IsIconic(hwnd),
    )
    front = user32.GetForegroundWindow()
    check(
        "second: the same window is in front",
        int(front or 0) == hwnd,
        f"foreground {int(front or 0):#x}",
    )
    # Today the second launch holds a window of its own: close it, so the next step closes one.
    for w in windows:
        if w["hwnd"] != hwnd:
            user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
    if second.poll() is None:
        try:
            second.wait(timeout=20)
        except subprocess.TimeoutExpired:
            second.kill()


def close_window(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def step_close_idle(app: App, hwnd: int) -> None:
    hubs = hub_pids(app.port)
    started = time.monotonic()
    close_window(hwnd)
    gone = wait_for(lambda: not user32.IsWindow(hwnd), 10, 0.1)
    check("close: the window closes without a prompt", bool(gone) and not app.windows())
    stopped = wait_for(lambda: not hub_pids(app.port) and port_free(app.port), CLOSE_LIMIT, 0.5)
    took = time.monotonic() - started
    check(
        f"close: within {CLOSE_LIMIT:.0f} s no Hub process for :{app.port} remains and the port is free",
        bool(stopped),
        f"Hub {hubs} -> {hub_pids(app.port)}, port free {port_free(app.port)}, {took:.1f} s",
    )


def bystanders() -> dict[int, set[int]]:
    """Who listens on :8000 and :8010 -- read, never called."""
    table = listeners()
    return {port: table.get(port, set()) for port in sorted(FORBIDDEN_PORTS)}


def start_turn(app: App) -> tuple[str | None, str]:
    """A real Haiku turn that stays in progress for a couple of minutes."""
    code, projects = app.api("GET", "/projects")
    rows = projects if isinstance(projects, list) else (projects or {}).get("projects", [])
    project = next(
        (
            p
            for p in rows
            if pathlib.Path(p.get("path") or p.get("working_directory") or "").resolve()
            == app.cwd.resolve()
        ),
        None,
    )
    if project is None:  # the launch did not register it; open it as the app's picker would
        code, project = app.api(
            "POST", "/projects/open", {"path": str(app.cwd), "name": app.cwd.name}
        )
        note(f"the launch registered no project for {app.cwd}; opened it: {code}")
    if not isinstance(project, dict) or "id" not in project:
        return None, f"no project for {app.cwd}: {code} {str(project)[:300]}"
    a = f"/projects/{project['id']}"
    app.api("PATCH", a, {"main_branch": "main"})
    _, runner = app.api("POST", f"{a}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    if not isinstance(runner, dict) or "id" not in runner:
        return None, f"runner: {runner}"
    app.api("POST", f"{a}/agents", {"name": "worker", "runner_id": runner["id"]})
    code, run = app.api(
        "POST",
        f"{a}/agent/trigger",
        {
            "agent": "worker",
            "session_mode": "new",
            "message": "Run this shell command and wait for it to finish: "
            "powershell -NoProfile -Command Start-Sleep -Seconds 150 . Then reply with the word done.",
        },
    )
    if not isinstance(run, dict):
        return None, f"trigger: {code} {run}"
    if run.get("run_id"):
        return run["run_id"], ""
    entry = run.get("queue_entry_id")
    if entry:  # queued rather than started: wait for the queue to deliver it to a run
        delivered = wait_for(
            lambda: (
                app.db("select delivered_in_run_id from inbound_queue_entries where id=?", (entry,))
                or [[None]]
            )[0][0],
            60,
            1.0,
        )
        if delivered:
            note(f"the trigger was queued ({entry}); it started as run {delivered}")
            return delivered, ""
    return None, f"trigger: {code} {json.dumps(run)[:600]}"


def run_status(app: App, run_id: str) -> str:
    rows = app.db("select status from runs where id=?", (run_id,))
    return rows[0][0] if rows else "missing"


def choose_in_page(hwnd: int, label: str) -> bool:
    """Invoke the page's button whose name starts with `label`, by UI Automation, as a click."""
    script = rf"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd})
$buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)))
foreach ($b in $buttons) {{
  if ($b.Current.Name -like '{label}*') {{
    $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); exit 0 }} }}
exit 3
"""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        timeout=60,
        creationflags=0x08000000,
    )
    return done.returncode == 0


def step_own_hub(idle: App, busy: App) -> None:
    others_before = bystanders()
    note(f":8000/:8010 listeners before: {others_before}")
    for app in (idle, busy):
        app.launch()
    idle_hwnd = idle.wait_window(idle.launchers[0])
    busy_hwnd = busy.wait_window(busy.launchers[0])
    if not (
        check(
            "own-hub: both Hubs are up with a window each",
            bool(idle_hwnd and busy_hwnd and idle.wait_healthy() and busy.wait_healthy()),
            f"idle {idle_hwnd}, busy {busy_hwnd}",
        )
    ):
        return
    time.sleep(4.0)  # the launch registers the project behind the splash
    run_id, why = start_turn(busy)
    if not check(
        "own-hub: the busy Hub has an agent turn in progress", run_id is not None, why or run_id
    ):
        return
    wait_for(lambda: run_status(busy, run_id) == "running", 60, 1.0)
    busy_hub = hub_pids(busy.port)
    rows = processes()
    busy_tree = descendants(rows, set(busy_hub)) - busy.pids
    note(
        f"busy Hub {busy_hub}, its processes {sorted(busy_tree)}, run {run_id} {run_status(busy, run_id)}"
    )

    close_window(idle_hwnd)
    wait_for(lambda: not idle_hub_running(idle), CLOSE_LIMIT, 0.5)
    time.sleep(2.0)
    check(
        "own-hub: after the idle window's close the busy Hub's process id is unchanged",
        hub_pids(busy.port) == busy_hub and bool(busy_hub),
        f"{busy_hub} -> {hub_pids(busy.port)}",
    )
    check(
        "own-hub: after the idle window's close the busy Hub's turn is unchanged",
        run_status(busy, run_id) == "running",
        run_status(busy, run_id),
    )
    check(
        "own-hub: after the idle window's close the idle Hub is gone",
        not idle_hub_running(idle),
        f"{hub_pids(idle.port)}, port free {port_free(idle.port)}",
    )

    close_window(busy_hwnd)
    time.sleep(3.0)
    prompted = bool(user32.IsWindow(busy_hwnd))
    check("own-hub: the busy window's close asks first (the window stays open)", prompted)
    if prompted:
        check(
            "own-hub: 'Stop it all' can be chosen in the page",
            choose_in_page(busy_hwnd, "Stop it all"),
        )

    def busy_gone() -> bool:
        alive = {r["ProcessId"] for r in processes()} & (busy_tree | set(busy_hub))
        return not alive and port_free(busy.port)

    gone = wait_for(busy_gone, CLOSE_LIMIT, 1.0)
    remaining = sorted({r["ProcessId"] for r in processes()} & (busy_tree | set(busy_hub)))
    check(
        "own-hub: after 'Stop it all' the busy Hub's processes are gone",
        bool(gone),
        f"remaining {remaining}, port free {port_free(busy.port)}",
    )
    others_after = bystanders()
    check(
        "own-hub: whatever serves :8000 and :8010 is the same process as before",
        others_after == others_before,
        f"{others_before} -> {others_after}",
    )


def idle_hub_running(app: App) -> bool:
    return bool(hub_pids(app.port)) or not port_free(app.port)


def clear_scratch() -> None:
    """Remove the scratch profiles and project folders of every run of this drive, this one's too.

    A second run must see nothing the first left: a reused profile kept the earlier run's agent,
    runner and an orphaned 'running' run, and its trigger was queued instead of started (QA,
    2026-11-05). Each run also names its own, so a folder Windows still holds open is never reused.
    """
    profiles = HUB_HOME / "profiles"
    for path in [*profiles.glob(PROFILE_PREFIX + "*"), SCRATCH]:
        shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8171, help="first of three scratch ports")
    parser.add_argument(
        "--skip-own-hub", action="store_true", help="skip the two-Hub step (Haiku turn)"
    )
    opts = parser.parse_args()
    ports = [opts.port, opts.port + 1, opts.port + 2]
    if FORBIDDEN_PORTS & set(ports):
        raise SystemExit(f"refusing ports {ports}: :8000 and :8010 are never driven")
    busy_ports = [p for p in ports if not port_free(p)]
    if busy_ports:
        raise SystemExit(f"scratch port(s) {busy_ports} already in use; pick another --port")
    target, args = shortcut_command()
    note(f"shortcut command: {target} {' '.join(args)} (+ --profile/--port)")

    clear_scratch()
    app = App(ports[0], PROFILE, project_dir("main"))
    idle = App(ports[1], PROFILE + "a", project_dir("idle"))
    busy = App(ports[2], PROFILE + "b", project_dir("busy"))
    # The Hubs and their runs descend from the launchers; the watch spans all three apps, through
    # the own-hub step's agent turn, so "a project is used" is inside it.
    watch = ConsoleWatch(lambda: app.pids | idle.pids | busy.pids).start()
    try:
        try:
            first = app.launch()
            hwnd = app.wait_window(first)
            if check("the app window opens", hwnd is not None, f"launcher pid {first.pid}"):
                check("the Hub answers", app.wait_healthy())
                time.sleep(6.0)  # past the splash, into the app, the project registered
                step_identity(app, hwnd)
                step_second_launch(app, hwnd)
                if user32.IsWindow(hwnd):
                    step_close_idle(app, hwnd)
        finally:
            app.cleanup()
        if not opts.skip_own_hub:
            try:
                step_own_hub(idle, busy)
            finally:
                idle.cleanup()
                busy.cleanup()
    finally:
        time.sleep(1.0)
        watch.stop()
        clear_scratch()
    check(
        "console: no console or terminal window of the apps' appeared during start, use and close",
        not watch.ours,
        f"{list(watch.ours.values())}" if watch.ours else "",
    )
    if watch.others:
        note(
            f"unattributed terminal windows that also appeared (not counted): {list(watch.others.values())}"
        )

    print(f"\n{len(failures)} FAIL" if failures else "\nALL PASS")
    for name in failures:
        print(f"  - {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
