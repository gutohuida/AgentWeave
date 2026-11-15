"""The operator's shells on the Hub (`a-terminal-in-the-side-panel`, TSP-2).

Every refusal is checked with its positive control beside it: the same request from loopback,
signed in, from the app's own page opens a shell, so a refusal is not a route that never worked.
"No process is started" is measured at the one place a shell process is spawned (`Shell.start`).

The real-process tests start the platform's own shell (Windows PowerShell on Windows, the first
detected shell elsewhere) and drive it through the attach WebSocket, called as ASGI in the test's
own loop (httpx's transport has no WebSocket).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time

import pytest
from httpx import ASGITransport, AsyncClient

from hub.terminal import access
from hub.terminal import shells as shell_detection
from hub.terminal.environment import clean_environment
from hub.terminal.sessions import LIMIT, OutputBuffer, Shell, registry
from hub.terminal.shells import ShellOption
from tests.test_changes_route import P, add_branch, seed  # noqa: F401
from tests.test_changes_route import repo as _repo

repo = _repo

HOST = "127.0.0.1:8000"
APP = f"http://{HOST}"
LOCAL = {"Host": HOST, "Origin": APP}
TERMINALS = f"/api/v1/projects/{P}/conversations/conv-ch/terminals"
SHELLS = f"/api/v1/projects/{P}/terminal/shells"
WT = ".agentweave/worktrees/worker"
IS_WINDOWS = sys.platform == "win32"

FAKE = [
    ShellOption(
        "powershell", "Windows PowerShell", "powershell.exe", ("powershell.exe",), "windows"
    ),
    ShellOption("git-bash", "Git Bash", r"C:\Git\bin\bash.exe", ("bash.exe",), "git-bash"),
    ShellOption("wsl:Ubuntu", "Ubuntu (WSL)", "wsl.exe -d Ubuntu", ("wsl.exe",), "wsl", "Ubuntu"),
]


@pytest.fixture(autouse=True)
async def _fresh_registry():
    registry.__init__()
    shell_detection._reset_detection_cache()
    yield
    await registry.end_all()
    registry.__init__()
    shell_detection._reset_detection_cache()


@pytest.fixture
def spawned(monkeypatch):
    """Fake shells: `Shell.start` records the call and starts nothing."""
    calls = []

    def _start(self, env):
        calls.append((self.option.id, str(self.path), env))

    monkeypatch.setattr(Shell, "start", _start)
    monkeypatch.setattr(Shell, "terminate_tree", lambda self: None)
    monkeypatch.setattr(shell_detection, "detect", lambda refresh=False: list(FAKE))
    monkeypatch.setattr(shell_detection, "wsl_directory", lambda d, p: shell_detection._mnt_path(p))
    return calls


def client_from(app, host):
    """A client on the same app whose requests arrive from *host*."""
    return AsyncClient(
        transport=ASGITransport(app=app._transport.app, client=(host, 50000)), base_url=APP
    )


async def open_shell(app, auth_headers, shell="powershell", location="root", headers=None, **kw):
    return await app.post(
        TERMINALS,
        json={"shell": shell, "location": location, **kw},
        headers={**auth_headers, **LOCAL, **(headers or {})},
    )


# --------------------------------------------------------------------------- FR-1, FR-2


@pytest.mark.asyncio
async def test_ac_remote_refused_each_source_and_no_process(app, auth_headers, repo, spawned):
    await seed()
    control = await open_shell(app, auth_headers)
    assert control.status_code == 201, control.text
    assert len(spawned) == 1

    async with client_from(app, "10.2.0.2") as lan:
        r = await lan.post(
            TERMINALS,
            json={"shell": "powershell"},
            headers={**auth_headers, "Host": "10.2.0.2:8000", "Origin": "http://10.2.0.2:8000"},
        )
        assert r.status_code == 403 and r.json()["detail"] == access.REMOTE_MESSAGE
        menu = await lan.get(
            SHELLS,
            params={"conversation_id": "conv-ch"},
            headers={**auth_headers, "Host": "10.2.0.2:8000"},
        )
        assert menu.status_code == 200
        assert menu.json()["unavailable"] == "remote" and menu.json()["shells"] == []
        assert "only on the computer AgentWeave runs on" in menu.json()["unavailable_reason"]
    async with client_from(app, "172.17.0.2") as bridge:
        r = await bridge.post(
            TERMINALS, json={"shell": "powershell"}, headers={**auth_headers, **LOCAL}
        )
        assert r.status_code == 403
    for forwarded in (
        {"X-Forwarded-For": "172.17.0.2"},
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Real-IP": "192.168.1.5"},
        {"Forwarded": "for=10.0.0.1"},
    ):
        r = await open_shell(app, auth_headers, headers=forwarded)
        assert r.status_code == 403, forwarded
    unsigned = await app.post(TERMINALS, json={"shell": "powershell"}, headers=LOCAL)
    assert unsigned.status_code == 401
    run_credential = await app.post(
        TERMINALS,
        json={"shell": "powershell"},
        headers={"Authorization": "Bearer aw_run_x", **LOCAL},
    )
    assert run_credential.status_code == 401
    rebound = await open_shell(
        app,
        auth_headers,
        headers={"Host": "evil.example:8000", "Origin": "http://evil.example:8000"},
    )
    assert rebound.status_code == 403
    assert len(spawned) == 1, "a refused request started a process"


@pytest.mark.asyncio
async def test_ac_other_site_refused_open_and_end(app, auth_headers, repo, spawned):
    await seed()
    for origin in ("http://evil.example", "null", "http://127.0.0.1:5999"):
        r = await open_shell(app, auth_headers, headers={"Origin": origin})
        assert r.status_code == 403, origin
        assert r.json()["detail"] == access.FOREIGN_MESSAGE
    no_origin = await app.post(
        TERMINALS, json={"shell": "powershell"}, headers={**auth_headers, "Host": HOST}
    )
    assert no_origin.status_code == 403
    assert spawned == []
    tid = (await open_shell(app, auth_headers)).json()["id"]
    for path, method in ((f"{TERMINALS}/{tid}", "DELETE"), (f"{TERMINALS}/{tid}/restart", "POST")):
        r = await app.request(
            method, path, headers={**auth_headers, "Host": HOST, "Origin": "http://evil.example"}
        )
        assert r.status_code == 403
    assert registry.get(tid) is not None and len(spawned) == 1


# --------------------------------------------------------------------------- WebSockets


class Socket:
    """An ASGI WebSocket session against the app, in this loop."""

    def __init__(self, app, path, headers, query="", client="127.0.0.1"):
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.outbox: asyncio.Queue = asyncio.Queue()
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (client, 50001),
            "server": ("127.0.0.1", 8000),
            "subprotocols": [],
        }
        self.inbox.put_nowait({"type": "websocket.connect"})
        self.task = asyncio.create_task(app._transport.app(scope, self.inbox.get, self.outbox.put))
        self.text = ""
        self.messages: list = []

    async def handshake(self) -> str:
        first = await asyncio.wait_for(self.outbox.get(), 30)
        return first["type"]

    async def send(self, payload):
        await self.inbox.put({"type": "websocket.receive", "text": json.dumps(payload)})

    async def read_until(self, predicate, timeout=30.0) -> bool:
        deadline = time.monotonic() + timeout
        while not predicate(self):
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            try:
                event = await asyncio.wait_for(self.outbox.get(), left)
            except asyncio.TimeoutError:
                return False
            if event["type"] == "websocket.send":
                msg = json.loads(event["text"])
                self.messages.append(msg)
                if msg.get("type") == "output":
                    self.text += msg["data"]
            elif event["type"] == "websocket.close":
                self.messages.append({"type": "socket-closed"})
        return True

    async def close(self):
        await self.inbox.put({"type": "websocket.disconnect", "code": 1000})
        try:
            await asyncio.wait_for(self.task, 10)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            self.task.cancel()


def attach_path(tid, conv="conv-ch"):
    return f"/api/v1/projects/{P}/conversations/{conv}/terminals/{tid}/attach"


@pytest.mark.asyncio
async def test_ac_attach_refused_from_elsewhere_and_other_sites(app, auth_headers, repo, spawned):
    from hub.auth import _make_ticket

    await seed()
    tid = (await open_shell(app, auth_headers)).json()["id"]
    ticket, _ = _make_ticket(P)
    good = {"Host": HOST, "Origin": APP}
    refused = [
        ({**good, "Origin": "http://evil.example"}, f"token={ticket}", "127.0.0.1"),
        ({"Host": HOST}, f"token={ticket}", "127.0.0.1"),  # no Origin
        (good, "", "127.0.0.1"),  # no sign-in
        (good, "token=aw_live_testkey_abcdefgh", "127.0.0.1"),  # a raw key in the URL
        (good, f"token={_make_ticket('proj-other')[0]}", "127.0.0.1"),
        ({**good, "Authorization": "Bearer aw_run_nope"}, "", "127.0.0.1"),
        (good, f"token={ticket}", "172.17.0.2"),
        ({**good, "X-Forwarded-For": "172.17.0.2"}, f"token={ticket}", "127.0.0.1"),
    ]
    for headers, query, peer in refused:
        sock = Socket(app, attach_path(tid), headers, query, client=peer)
        assert await sock.handshake() == "websocket.close", (headers, query, peer)
        await sock.close()
    for headers, query in ((good, f"token={ticket}"), ({**good, **auth_headers}, "")):
        sock = Socket(app, attach_path(tid), headers, query)
        assert await sock.handshake() == "websocket.accept"
        await sock.close()
    wrong_conversation = Socket(app, attach_path(tid, "conv-other"), good, f"token={ticket}")
    assert await wrong_conversation.handshake() == "websocket.close"
    await wrong_conversation.close()
    assert len(spawned) == 1


# --------------------------------------------------------------------------- FR-3


@pytest.mark.asyncio
async def test_ac_docker_menu_says_so_and_every_request_refused(
    app, auth_headers, repo, spawned, monkeypatch
):
    await seed()
    monkeypatch.setenv("AW_RUNTIME", "docker")
    menu = (
        await app.get(
            SHELLS, params={"conversation_id": "conv-ch"}, headers={**auth_headers, "Host": HOST}
        )
    ).json()
    assert menu["unavailable"] == "docker" and menu["shells"] == []
    assert menu["unavailable_reason"] == "The terminal is not available in Docker mode."
    r = await open_shell(app, auth_headers)
    assert r.status_code == 403 and "Docker mode" in r.json()["detail"]
    listing = await app.get(TERMINALS, headers={**auth_headers, "Host": HOST})
    assert listing.status_code == 403
    assert spawned == []


# --------------------------------------------------------------------------- FR-4


@pytest.mark.asyncio
async def test_ac_detected_menu_lists_installed_and_last_pick_first(
    app, auth_headers, repo, spawned
):
    await seed()
    menu = (
        await app.get(
            SHELLS, params={"conversation_id": "conv-ch"}, headers={**auth_headers, "Host": HOST}
        )
    ).json()
    assert [s["label"] for s in menu["shells"]] == [o.label for o in FAKE]
    assert menu["last_pick"] is None and not any(s["last_used"] for s in menu["shells"])
    assert menu["shells"][2]["wsl"] is True

    assert (await open_shell(app, auth_headers, shell="git-bash")).status_code == 201
    again = (
        await app.get(
            SHELLS, params={"conversation_id": "conv-ch"}, headers={**auth_headers, "Host": HOST}
        )
    ).json()
    assert again["shells"][0]["id"] == "git-bash" and again["shells"][0]["last_used"] is True
    assert [s["last_used"] for s in again["shells"]].count(True) == 1
    assert again["last_pick"] == {"option_id": "git-bash", "location": "root"}

    missing = await open_shell(app, auth_headers, shell="fish")
    assert missing.status_code == 422


def test_wsl_distributions_decoded_and_docker_desktop_left_out(monkeypatch):
    class Done:
        returncode = 0
        stdout = "Ubuntu-24.04\r\ndocker-desktop\r\nDebian\r\n".encode("utf-16-le")

    monkeypatch.setattr(shell_detection, "_first_file", lambda c: "wsl.exe")
    monkeypatch.setattr(shell_detection.subprocess, "run", lambda *a, **k: Done())
    assert shell_detection.wsl_distributions() == ["Ubuntu-24.04", "Debian"]


def test_git_bash_needs_git_bash_beside_bash(tmp_path, monkeypatch):
    git = tmp_path / "Git"
    (git / "cmd").mkdir(parents=True)
    (git / "bin").mkdir()
    (git / "cmd" / "git.exe").write_text("")
    (git / "bin" / "bash.exe").write_text("")
    monkeypatch.setattr(shell_detection.shutil, "which", lambda name: str(git / "cmd" / "git.exe"))
    monkeypatch.setattr(shell_detection, "_program_files", lambda: [])
    assert shell_detection._git_bash() is None
    (git / "git-bash.exe").write_text("")
    assert shell_detection._git_bash() == git / "bin" / "bash.exe"


# --------------------------------------------------------------------------- FR-5


@pytest.mark.asyncio
async def test_ac_where_worktree_root_and_wsl_path(app, auth_headers, repo, spawned):
    wt = add_branch(repo, "agentweave/worker", worktree=repo / WT)
    await seed()
    menu = (
        await app.get(
            SHELLS, params={"conversation_id": "conv-ch"}, headers={**auth_headers, "Host": HOST}
        )
    ).json()
    assert menu["worktree_unavailable"] is None
    in_wt = (await open_shell(app, auth_headers, location="worktree")).json()
    in_root = (await open_shell(app, auth_headers, location="root")).json()
    wsl = (await open_shell(app, auth_headers, shell="wsl:Ubuntu", location="worktree")).json()
    assert os.path.samefile(in_wt["directory"], wt)
    assert os.path.samefile(in_root["directory"], repo)
    assert [c[1] for c in spawned] == [in_wt["directory"], in_root["directory"], str(wt)]
    if IS_WINDOWS:
        assert wsl["directory"].startswith("/mnt/") and wsl["directory"].endswith(WT)
    assert wsl["label"] == "Ubuntu (WSL)" and wsl["wsl"] is True


@pytest.mark.asyncio
async def test_ac_where_no_worktree_choice_says_why(app, auth_headers, repo, spawned):
    await seed(agent="reader", conv="conv-ro", read_only=True)
    menu = (
        await app.get(
            SHELLS, params={"conversation_id": "conv-ro"}, headers={**auth_headers, "Host": HOST}
        )
    ).json()
    assert "read-only" in menu["worktree_unavailable"]
    r = await app.post(
        TERMINALS.replace("conv-ch", "conv-ro"),
        json={"shell": "powershell", "location": "worktree"},
        headers={**auth_headers, **LOCAL},
    )
    assert r.status_code == 409 and "read-only" in r.json()["detail"]
    assert spawned == []


def test_wsl_and_git_bash_name_the_directory_their_way():
    from pathlib import Path

    assert shell_detection._mnt_path(Path(r"C:\Users\me\proj")) == "/mnt/c/Users/me/proj"
    bash = FAKE[1]
    if IS_WINDOWS:
        assert shell_detection.shown_directory(bash, Path(r"D:\work\x")) == "/d/work/x"
    assert shell_detection.launch_argv(FAKE[2], Path("C:/p"))[-2:] == ["--cd", str(Path("C:/p"))]


# --------------------------------------------------------------------------- FR-7, FR-8


@pytest.mark.asyncio
async def test_ac_cap_fifth_refused_naming_four(app, auth_headers, repo, spawned):
    await seed()
    for _ in range(LIMIT):
        assert (await open_shell(app, auth_headers)).status_code == 201
    fifth = await open_shell(app, auth_headers)
    assert fifth.status_code == 409
    assert "Limit of 4 reached" in fifth.json()["detail"] and fifth.json()["limit"] == 4
    assert len(spawned) == LIMIT
    listed = (await app.get(TERMINALS, headers={**auth_headers, "Host": HOST})).json()["shells"]
    assert len(listed) == LIMIT
    # Another conversation has its own four.
    await seed(conv="conv-two")
    other = await app.post(
        TERMINALS.replace("conv-ch", "conv-two"),
        json={"shell": "powershell"},
        headers={**auth_headers, **LOCAL},
    )
    assert other.status_code == 201


def test_output_keeps_the_last_5000_lines():
    buffer = OutputBuffer()
    for i in range(1, 7001):
        buffer.append(f"\x1b[32mline {i}\x1b[0m\r\n")
    lines = buffer.lines()
    assert len(lines) == 5000 and lines[0] == "line 2001" and lines[-1] == "line 7000"
    assert buffer.lines(500)[0] == "line 6501"
    big = OutputBuffer(max_lines=10)
    big.append("".join(f"{i}\n" for i in range(100)))
    assert big.lines() == [str(i) for i in range(90, 100)]
    capped = OutputBuffer(max_characters=100)
    capped.append("x" * 250)
    assert len(capped.text()) == 100


# --------------------------------------------------------------------------- FR-10


def test_environment_drops_the_hubs_variables_and_keeps_path():
    env = clean_environment(
        {
            "PATH": "/usr/bin",
            "HOME": "/home/me",
            "DATABASE_URL": "sqlite+aiosqlite:///C:/hub/data.db",
            "AW_BOOTSTRAP_API_KEY": "aw_live_abc",
            "AW_RUN_TOKEN": "aw_run_tok",
            "AW_RUN_ID": "run-1",
            "HUB_URL": "http://127.0.0.1:8000",
            "MY_COPY": "Bearer aw_live_copied",
            "DB_AGAIN": "C:/hub/data.db",
            "WSLENV": "AW_RUN_TOKEN/u:USERPROFILE/p:MY_COPY:GOPATH/l",
        },
        extra_values=("C:/hub/data.db",),
    )
    assert env == {"PATH": "/usr/bin", "HOME": "/home/me", "WSLENV": "USERPROFILE/p:GOPATH/l"}


def _real_option() -> ShellOption:
    options = shell_detection.detect(refresh=True)
    wanted = "powershell" if IS_WINDOWS else None
    for option in options:
        if wanted is None or option.id == wanted:
            return option
    pytest.skip("no shell detected on this machine")


def _say(option: ShellOption, command: str) -> str:
    return command + ("\r" if IS_WINDOWS else "\n")


async def _real_shell(app, auth_headers, monkeypatch, **body):
    option = _real_option()
    monkeypatch.setattr(shell_detection, "detect", lambda refresh=False: [option])
    r = await open_shell(app, auth_headers, shell=option.id, **body)
    assert r.status_code == 201, r.text
    from hub.auth import _make_ticket

    sock = Socket(
        app,
        attach_path(r.json()["id"]),
        {"Host": HOST, "Origin": APP},
        f"token={_make_ticket(P)[0]}",
    )
    assert await sock.handshake() == "websocket.accept"
    return option, r.json(), sock


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_ac_env_a_real_shell_has_path_and_none_of_the_hubs(
    app, auth_headers, repo, monkeypatch
):
    await seed()
    monkeypatch.setenv("AW_BOOTSTRAP_API_KEY", "aw_live_planted_key_123")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_planted_token_123")
    monkeypatch.setenv("AW_RUN_ID", "run-planted-123")
    monkeypatch.setenv("AW_TERMINAL_PROBE", "present")
    option, shell, sock = await _real_shell(app, auth_headers, monkeypatch)
    if IS_WINDOWS:
        listing = "Get-ChildItem env: | % { 'ENV:' + $_.Name + '=' + $_.Value }; " "'ENV-' + 'DONE'"
    else:
        listing = "env | sed 's/^/ENV:/'; printf 'ENV-%s\\n' DONE"
    await asyncio.sleep(1.0)
    await sock.send({"type": "input", "data": _say(option, listing)})
    assert await sock.read_until(lambda s: "ENV-DONE" in s.text, 60), sock.text[-2000:]
    names = {line.split("=", 1)[0].upper() for line in sock.text.split("ENV:")[1:]}
    assert "PATH" in names
    for planted in (
        "DATABASE_URL",
        "AW_BOOTSTRAP_API_KEY",
        "AW_RUN_TOKEN",
        "AW_RUN_ID",
        "AW_TERMINAL_PROBE",
    ):
        assert planted not in names, planted
    for value in ("aw_live_planted_key_123", "aw_run_planted_token_123", "run-planted-123"):
        assert value not in sock.text
    await sock.close()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.skipif(not IS_WINDOWS, reason="priority classes and ConPTY are Windows")
async def test_a_shell_answers_at_normal_priority_under_a_hub_that_gives_way(
    app, auth_headers, repo, monkeypatch
):
    """A check runs the suite below normal (`project_checks.py`, give-way); ConPTY's console host
    and PowerShell inherited it and took ~28 s to answer a line, failing every real-shell test."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    normal, below = 0x20, 0x4000

    def priority(pid: int) -> int:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        try:
            return kernel32.GetPriorityClass(handle)
        finally:
            kernel32.CloseHandle(handle)

    me = kernel32.GetCurrentProcess()
    before = kernel32.GetPriorityClass(me)
    assert kernel32.SetPriorityClass(me, below)
    try:
        await seed()
        option, shell, sock = await _real_shell(app, auth_headers, monkeypatch)
        assert priority(registry.get(shell["id"])._pty.pid) == normal, "the shell gave way"
        hosts = [
            pid
            for pid, parent, name in _processes()
            if parent == os.getpid() and name.lower() in ("openconsole.exe", "conhost.exe")
        ]
        assert hosts and all(priority(pid) == normal for pid in hosts), "its console host gave way"
        started = time.monotonic()
        await sock.send({"type": "input", "data": _say(option, "'PRIORITY-' + 'OK'")})
        assert await sock.read_until(lambda s: "PRIORITY-OK" in s.text, 20), sock.text[-2000:]
        assert time.monotonic() - started < 20
        await sock.close()
    finally:
        kernel32.SetPriorityClass(me, before)


def _processes() -> list:
    """(pid, parent pid, executable) for every process. Windows only."""
    import ctypes
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
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    rows = []
    try:
        entry = _Entry()
        entry.dwSize = ctypes.sizeof(_Entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            rows.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return rows


# --------------------------------------------------------------------------- FR-9


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait(predicate, timeout=30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await asyncio.to_thread(predicate):
            return True
        await asyncio.sleep(0.3)
    return False


async def _shell_serving_a_port(app, auth_headers, monkeypatch, **body):
    option, shell, sock = await _real_shell(app, auth_headers, monkeypatch, **body)
    port = _free_port()
    server = f"-m http.server {port} --bind 127.0.0.1"
    command = f"& '{sys.executable}' {server}" if IS_WINDOWS else f"'{sys.executable}' {server}"
    await asyncio.sleep(1.0)
    await sock.send({"type": "input", "data": _say(option, command)})
    assert await _wait(lambda: _port_open(port)), sock.text[-2000:]
    return shell, sock, port


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_ac_ends_close_and_restart_end_the_child_and_free_the_port(
    app, auth_headers, repo, monkeypatch
):
    await seed()
    shell, sock, port = await _shell_serving_a_port(app, auth_headers, monkeypatch)
    closed = await app.delete(f"{TERMINALS}/{shell['id']}", headers={**auth_headers, **LOCAL})
    assert closed.status_code == 200
    assert await _wait(lambda: not _port_open(port), 20), "the child outlived its closed shell"
    assert await sock.read_until(lambda s: {"type": "closed"} in s.messages, 10)
    await sock.close()
    assert (await app.get(TERMINALS, headers={**auth_headers, "Host": HOST})).json()["shells"] == []

    shell, sock, port = await _shell_serving_a_port(app, auth_headers, monkeypatch)
    restarted = await app.post(
        f"{TERMINALS}/{shell['id']}/restart", headers={**auth_headers, **LOCAL}
    )
    assert restarted.status_code == 200 and restarted.json()["replaces"] == shell["id"]
    assert await _wait(lambda: not _port_open(port), 20), "the child outlived a Restart"
    listed = (await app.get(TERMINALS, headers={**auth_headers, "Host": HOST})).json()["shells"]
    assert [s["id"] for s in listed] == [restarted.json()["id"]] and listed[0]["running"]
    await sock.close()


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_ac_ends_the_page_going_away_and_hub_stop(app, auth_headers, repo, monkeypatch):
    from hub.auth import _make_ticket
    from hub.terminal import sessions

    monkeypatch.setattr(sessions, "PAGE_GRACE_SECONDS", 0.2)
    await seed()
    page_path = f"/api/v1/projects/{P}/terminal/page"
    presence = Socket(
        app, page_path, {"Host": HOST, "Origin": APP}, f"page=page-1&token={_make_ticket(P)[0]}"
    )
    assert await presence.handshake() == "websocket.accept"
    owned, sock, port = await _shell_serving_a_port(app, auth_headers, monkeypatch, page="page-1")
    unowned, sock2, port2 = await _shell_serving_a_port(app, auth_headers, monkeypatch)
    await asyncio.sleep(0.5)
    assert registry.get(owned["id"]) is not None, "a page still there lost its shell"
    await presence.close()  # the page reloads
    assert await _wait(lambda: registry.get(owned["id"]) is None, 10)
    assert await _wait(lambda: not _port_open(port), 20), "the child outlived its page"
    assert registry.get(unowned["id"]) is not None and _port_open(port2)

    await registry.end_all()  # what lifespan's shutdown runs
    assert await _wait(lambda: not _port_open(port2), 20), "the child outlived the Hub's stop"
    assert registry.all() == []
    await sock.close()
    await sock2.close()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_a_gone_pages_shells_do_not_count_toward_the_limit(
    app, auth_headers, repo, monkeypatch
):
    """FR-9 at the cap: after a reload the fresh page's one shell opens even with 4 left behind."""
    from hub.auth import _make_ticket
    from hub.terminal import sessions

    monkeypatch.setattr(sessions, "PAGE_GRACE_SECONDS", 30.0)
    await seed()
    presence = Socket(
        app,
        f"/api/v1/projects/{P}/terminal/page",
        {"Host": HOST, "Origin": APP},
        f"page=page-old&token={_make_ticket(P)[0]}",
    )
    assert await presence.handshake() == "websocket.accept"
    old = []
    for _ in range(sessions.LIMIT):
        shell, sock, _port = await _shell_serving_a_port(
            app, auth_headers, monkeypatch, page="page-old"
        )
        old.append((shell, sock))
    await presence.close()  # the reload; the old page is in its grace
    assert await _wait(lambda: "page-old" in registry._page_timers, 5)
    fresh, fresh_sock, _ = await _shell_serving_a_port(
        app, auth_headers, monkeypatch, page="page-new"
    )
    assert registry.get(fresh["id"]) is not None
    assert all(registry.get(s["id"]) is None for s, _ in old), "the gone page's shells lingered"
    await fresh_sock.close()
    for _, sock in old:
        await sock.close()
    await registry.end_all()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_ac_ends_exit_shows_its_code_and_stays_listed(app, auth_headers, repo, monkeypatch):
    await seed()
    option, shell, sock = await _real_shell(app, auth_headers, monkeypatch)
    await asyncio.sleep(1.0)
    await sock.send({"type": "input", "data": _say(option, "exit 3")})
    assert await sock.read_until(
        lambda s: any(m.get("type") == "exit" for m in s.messages), 30
    ), sock.text[-1000:]
    assert [m for m in sock.messages if m.get("type") == "exit"][0]["code"] == 3
    listed = (await app.get(TERMINALS, headers={**auth_headers, "Host": HOST})).json()["shells"]
    assert listed[0]["running"] is False and listed[0]["exit_code"] == 3
    await sock.close()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_ac_keeps_running_detached_and_replays_meanwhile(
    app, auth_headers, repo, monkeypatch
):
    await seed()
    option, shell, sock = await _real_shell(app, auth_headers, monkeypatch)
    if IS_WINDOWS:
        ticker = "1..6 | % { 'tick-' + $_; Start-Sleep -Milliseconds 400 }"
    else:
        ticker = "for i in 1 2 3 4 5 6; do echo tick-$i; sleep 0.4; done"
    await asyncio.sleep(1.0)
    await sock.send({"type": "input", "data": _say(option, ticker)})
    await sock.read_until(lambda s: "tick-1" in s.text.replace("tick-' + $_", ""), 30)
    await sock.close()  # the operator goes to another conversation
    await asyncio.sleep(4.0)
    again = Socket(app, attach_path(shell["id"]), {"Host": HOST, "Origin": APP, **auth_headers})
    assert await again.handshake() == "websocket.accept"
    assert await again.read_until(lambda s: "tick-6" in s.text, 10), again.text[-1000:]
    assert registry.get(shell["id"]).running
    await again.close()


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.skipif(not IS_WINDOWS, reason="ConPTY and MSYS readline are Windows")
@pytest.mark.skipif(
    not os.environ.get("AW_LIVE_SHELL_TESTS"),
    reason="Git Bash under ConPTY intermittently drops the first key after an xterm focus report "
    "(ESC [ I), about 1 run in 4 (F1177): a shell limitation, not the Hub's, so this live check "
    "runs on request (AW_LIVE_SHELL_TESTS=1) rather than gating every landing",
)
async def test_a_keystroke_typed_just_after_a_resize_reaches_the_shell(
    app, auth_headers, repo, monkeypatch
):
    """Drive run 231921 lost the leading `e` of a command typed right after the panel was widened
    (`cho ...: command not found`). Resize, then type at once, one input frame per character as
    xterm's onData sends them: every character must arrive."""
    option = next((o for o in shell_detection.detect(refresh=True) if o.id == "git-bash"), None)
    if option is None:
        pytest.skip("Git Bash is not installed")
    await seed()
    monkeypatch.setattr(shell_detection, "detect", lambda refresh=False: [option])
    r = await open_shell(app, auth_headers, shell=option.id)
    assert r.status_code == 201, r.text
    from hub.auth import _make_ticket

    sock = Socket(
        app,
        attach_path(r.json()["id"]),
        {"Host": HOST, "Origin": APP},
        f"token={_make_ticket(P)[0]}",
    )
    assert await sock.handshake() == "websocket.accept"
    await asyncio.sleep(3.0)
    lost = []
    for round_no, (cols, delay) in enumerate(
        [(100, 0), (140, 0.01), (90, 0.05), (160, 0), (120, 0.2)]
    ):
        await sock.send({"type": "resize", "cols": cols, "rows": 30})
        if delay:
            await asyncio.sleep(delay)
        mark = f"AWR{round_no}"
        # Clicking xterm focuses it, and it reports that to the shell (ESC [ I) before the first
        # key; then one input frame per key, as xterm's onData sends them.
        for ch in ["\x1b[I", *f"echo {mark}$((40+2))W\r"]:
            await sock.send({"type": "input", "data": ch})
        arrived = await sock.read_until(lambda s, m=mark: f"{m}42W" in s.text, 20)
        if not arrived:
            lost.append((cols, delay, sock.text[-300:]))
    await sock.close()
    assert not lost, lost
