"""The notices while no window is open: the window's listener, the watcher, and the hand-over.

Change `windows-notifications-for-what-calls-the-operator`, task background-watcher (FR-2, FR-3,
FR-10). A stub Hub serves the routes the listeners use (`/api/v1/setup/token`,
`/api/v1/events/ticket`, `/api/v1/events`, `/api/v1/notify-settings`) on 127.0.0.1, and the notifier
is driven through `AW_TOAST_COMMAND`, so nothing shows a real toast.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agentweave import cli, notifier

#: Taken before conftest's autouse fixtures replace them: the one test that starts a real watcher
#: needs the real start, and the watcher's lifecycle turns on whether a process is alive and whether
#: the Hub's port answers, which conftest answers "always" and "never" for the rest of the suite.
_REAL_START_NOTICE_WATCHER = cli._start_notice_watcher
_REAL_PID_ALIVE = cli.desktop_window.pid_alive
_REAL_PORT_ACCEPTS = cli._hub_port_accepts


@pytest.fixture(autouse=True)
def _real_processes_and_ports(monkeypatch):
    monkeypatch.setattr(cli.desktop_window, "pid_alive", _REAL_PID_ALIVE)
    monkeypatch.setattr(cli, "_hub_port_accepts", _REAL_PORT_ACCEPTS)


KEY = "aw_live_" + "k" * 32
TICKET = "aw_optick_t1"


def _notice(nid, kind="ask", **extra):
    return {
        "id": nid,
        "kind": kind,
        "project_id": "proj-abc123",
        "agent": "watchbot",
        "conversation_id": "conv-1",
        "title": "An agent needs you",
        "text": f"watchbot {kind} {nid}",
        "source_event": "question_asked",
        **extra,
    }


class StubHub:
    """The four routes the listeners read, with the operator stream fed from `push`."""

    def __init__(self):
        self.kinds = dict(notifier.DEFAULT_WINDOWS_KINDS)
        self.streams = []  # one queue per open stream
        self.connections = 0
        self.unauthorised = 0
        hub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _json(self, body, status=200):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                authorised = self.headers.get("Authorization") == f"Bearer {KEY}"
                if self.path == "/api/v1/setup/token":
                    return self._json({"api_key": KEY})
                if self.path == "/api/v1/events/ticket":
                    if not authorised:
                        hub.unauthorised += 1
                        return self._json({"detail": "no"}, 401)
                    return self._json({"token": TICKET})
                if self.path == "/api/v1/notify-settings":
                    if not authorised:
                        hub.unauthorised += 1
                        return self._json({"detail": "no"}, 401)
                    return self._json(hub.kinds)
                if self.path == f"/api/v1/events?token={TICKET}":
                    return self._stream()
                return self._json({"detail": "not found"}, 404)

            def _stream(self):
                q = queue.Queue()
                hub.streams.append(q)
                hub.connections += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    # The wire format `sse_starlette` writes: CRLF lines, a ping comment between.
                    self.wfile.write(b"event: connected\r\ndata: connected\r\n\r\n")
                    self.wfile.flush()
                    while not hub.closed:
                        try:
                            event, data = q.get(timeout=0.2)
                        except queue.Empty:
                            self.wfile.write(b": ping - 2026-11-08\r\n\r\n")
                            self.wfile.flush()
                            continue
                        frame = f"event: {event}\r\ndata: {json.dumps(data)}\r\n\r\n"
                        self.wfile.write(frame.encode())
                        self.wfile.flush()
                except OSError:
                    pass
                finally:
                    hub.streams.remove(q)
                    self.close_connection = True

        self.closed = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def push(self, event, data):
        for q in list(self.streams):
            q.put((event, data))

    def wait_for_streams(self, n, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.streams) >= n:
                return True
            time.sleep(0.05)
        return False

    def close(self):
        self.closed = True
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def hub():
    stub = StubHub()
    yield stub
    stub.close()


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(notifier, "supported", lambda: True)


@pytest.fixture
def hub_dir(tmp_path, monkeypatch):
    folder = tmp_path / ".agentweave" / "hub"
    folder.mkdir(parents=True)
    monkeypatch.setattr(cli, "HUB_DIR", folder)
    return folder


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    """An AW_TOAST_COMMAND that records each payload it is handed, one JSON file per call."""
    out = tmp_path / "shown"
    out.mkdir()
    script = tmp_path / "record.py"
    script.write_text(
        "import sys, pathlib, uuid\n"
        f"pathlib.Path({str(out)!r}, uuid.uuid4().hex).write_bytes(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(notifier.TOAST_COMMAND_ENV, f'"{sys.executable}" "{script}"')
    return lambda: [json.loads(p.read_text(encoding="utf-8"))["notice"] for p in out.iterdir()]


def _eventually(check, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return check()


def _ids(shown):
    return sorted(n["id"] for n in shown())


# --- reading the stream ------------------------------------------------------------------------


def test_the_hubs_wire_format_is_read_event_by_event():
    lines = [
        b"event: connected\r\n",
        b"data: connected\r\n",
        b"\r\n",
        b": ping - 2026-11-08 03:00:00\r\n",
        b"\r\n",
        b"event: operator_notice\r\n",
        b'data: {"id": "ntc-1", "kind": "ask"}\r\n',
        b"\r\n",
        b"event: question_asked\r\n",
        b'data: {"id": "q-1"}\r\n',
        b"\r\n",
    ]
    assert list(notifier.sse_events(lines)) == [
        ("connected", "connected"),
        ("operator_notice", {"id": "ntc-1", "kind": "ask"}),
        ("question_asked", {"id": "q-1"}),
    ]


def test_only_the_kinds_switched_on_are_wanted():
    kinds = {"ask": False, "fail": True, "done": False, "reply": True}
    assert notifier.wanted(_notice("a", "reply"), kinds)
    assert notifier.wanted(_notice("b", "fail"), kinds)
    assert not notifier.wanted(_notice("c", "ask"), kinds)
    assert not notifier.wanted(_notice("d", "mystery"), kinds)
    assert not notifier.wanted("not a notice", kinds)


# --- the hand-over rule (FR-3) -----------------------------------------------------------------


def test_a_window_in_front_for_the_whole_hold_shows_nothing(on_windows, hub_dir, recorder):
    shown = notifier.deliver(_notice("ntc-front"), 8181, hub_dir, lambda: True, hold=0.3, poll=0.05)
    assert shown is False
    assert recorder() == []


def test_a_window_leaving_the_front_within_the_hold_shows_it_at_once(on_windows, hub_dir, recorder):
    answers = iter([True, True, False])
    started = time.monotonic()
    shown = notifier.deliver(
        _notice("ntc-closing"), 8181, hub_dir, lambda: next(answers), hold=3.0, poll=0.05
    )
    assert shown is True
    assert time.monotonic() - started < 2.0
    assert _ids(recorder) == ["ntc-closing"]


def test_two_listeners_overlapping_at_a_hand_over_show_a_notice_once(on_windows, hub_dir, recorder):
    """c-in-front: the window's listener and the watcher both read the notice at a hand-over."""
    notice = _notice("ntc-overlap")
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                notifier.deliver(notice, 8181, hub_dir, lambda: False, hold=0.5)
            )
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, False, False, True]
    assert _ids(recorder) == ["ntc-overlap"]


def test_the_window_in_front_is_told_by_the_foreground_windows_owner(hub_dir, monkeypatch):
    (hub_dir / "window-8181-4242-1.open").write_text("u", encoding="utf-8")
    monkeypatch.setattr(cli, "_foreground_pid", lambda: 4242)
    assert cli._app_window_in_front(8181) is True
    assert cli._app_window_in_front(8182) is False  # another port's window is not this one's
    monkeypatch.setattr(cli, "_foreground_pid", lambda: 999)
    assert cli._app_window_in_front(8181) is False
    monkeypatch.setattr(cli, "_foreground_pid", lambda: None)
    assert cli._app_window_in_front(8181) is False


# --- a listener on the stub Hub (FR-2, FR-10) --------------------------------------------------


def _start_listener(port):
    ready = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(
        target=cli._listen_for_notices,
        args=(port, ready.set, lambda: not stop.is_set()),
        daemon=True,
    )
    thread.start()
    return ready, stop


def test_a_listener_reads_the_stream_with_the_launchers_credential_and_the_hubs_choices(
    on_windows, hub, hub_dir, recorder
):
    ready, stop = _start_listener(hub.port)
    try:
        assert ready.wait(10), "the listener never connected"
        assert hub.unauthorised == 0

        # The defaults: questions and failures reach Windows, done and replies do not.
        hub.push("operator_notice", _notice("ntc-ask-1", "ask"))
        hub.push("operator_notice", _notice("ntc-reply-1", "reply"))
        hub.push("operator_notice", _notice("ntc-fail-1", "fail"))
        hub.push("operator_notice", _notice("ntc-done-1", "done"))
        hub.push("question_asked", {"id": "q-1", "from_agent": "watchbot"})  # not a notice
        assert _eventually(lambda: _ids(recorder) == ["ntc-ask-1", "ntc-fail-1"])

        # c-kinds: the operator turns 'reply' on and 'question' off; the next notice obeys it.
        hub.kinds = {"ask": False, "fail": True, "done": False, "reply": True}
        hub.push("operator_notice", _notice("ntc-ask-2", "ask"))
        hub.push("operator_notice", _notice("ntc-reply-2", "reply"))
        assert _eventually(lambda: "ntc-reply-2" in _ids(recorder))
        time.sleep(0.5)
        assert _ids(recorder) == ["ntc-ask-1", "ntc-fail-1", "ntc-reply-2"]
    finally:
        stop.set()


def test_the_hubs_choices_unreadable_keep_the_last_answer_else_the_defaults(monkeypatch):
    kinds = cli._WindowsKinds(1)  # nothing listens on port 1
    assert kinds() == notifier.DEFAULT_WINDOWS_KINDS
    kinds._last = {"ask": False, "fail": False, "done": True, "reply": True}
    assert kinds() == {"ask": False, "fail": False, "done": True, "reply": True}


# --- the watcher's lifecycle (FR-2) ------------------------------------------------------------


def _run_watcher_in_thread(port):
    result = {}
    thread = threading.Thread(
        target=lambda: result.setdefault("code", cli._run_notice_watcher(port)), daemon=True
    )
    thread.start()
    return thread, result


def test_the_watcher_shows_notices_and_ends_when_a_window_listens(
    on_windows, hub, hub_dir, recorder
):
    claim, ready = cli._notice_watcher_files(hub.port)
    thread, result = _run_watcher_in_thread(hub.port)
    assert _eventually(ready.exists), "the watcher never said it was listening"
    assert cli._notice_watcher_ready(hub.port)
    assert claim.read_text(encoding="utf-8") == str(os.getpid())

    hub.push("operator_notice", _notice("ntc-closed-1", "fail"))
    assert _eventually(lambda: _ids(recorder) == ["ntc-closed-1"])

    # A window opens; until its listener says it is listening, the watcher stays.
    marker = hub_dir / f"window-{hub.port}-{os.getpid()}-1.open"
    marker.write_text("u", encoding="utf-8")
    time.sleep(1.0)
    assert thread.is_alive()
    cli._app_window_listening(marker).write_text("1", encoding="utf-8")
    thread.join(timeout=10)
    assert not thread.is_alive() and result["code"] == 0
    assert not claim.exists() and not ready.exists()


def test_the_watcher_ends_when_the_hub_ends(on_windows, hub, hub_dir, monkeypatch):
    monkeypatch.setattr(cli, "_NOTICE_WATCHER_HUB_GRACE_SECONDS", 0.5)
    _, ready = cli._notice_watcher_files(hub.port)
    thread, result = _run_watcher_in_thread(hub.port)
    assert _eventually(ready.exists)
    hub.close()
    thread.join(timeout=10)
    assert not thread.is_alive() and result["code"] == 0
    assert not ready.exists()


def test_one_watcher_per_port(on_windows, hub_dir):
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        claim, _ = cli._notice_watcher_files(8183)
        claim.write_text(str(holder.pid), encoding="utf-8")
        assert cli._run_notice_watcher(8183) == 0  # at once: the port is held
        assert claim.read_text(encoding="utf-8") == str(holder.pid)
    finally:
        holder.kill()
        holder.wait()
    # A claim whose watcher has gone is stale, and taken over.
    assert cli._claim_notice_watcher(8183) is True
    assert claim.read_text(encoding="utf-8") == str(os.getpid())


def test_off_windows_no_watcher_runs(hub_dir, monkeypatch):
    monkeypatch.setattr(notifier, "supported", lambda: False)
    assert cli._run_notice_watcher(8184) == 0
    assert not cli._notice_watcher_files(8184)[0].exists()


# --- when a close starts the watcher -----------------------------------------------------------


@pytest.fixture
def hand_over(on_windows, hub_dir, monkeypatch):
    started = []
    monkeypatch.setattr(cli, "_start_notice_watcher", lambda port: started.append(port) or True)
    monkeypatch.setattr(cli, "_hub_pid_running", lambda port, profile: 777)
    return started


def test_a_close_that_keeps_the_hub_running_starts_the_watcher(hand_over):
    closer = cli._AppWindowCloser(8185, "scratch")
    assert cli._hand_over_to_watcher(closer, stopped=False) is True
    assert hand_over == [8185]


def test_a_close_that_stops_the_hub_starts_no_watcher(hand_over):
    closer = cli._AppWindowCloser(8185)
    closer.stop_after = True
    assert cli._hand_over_to_watcher(closer, stopped=False) is False
    assert cli._hand_over_to_watcher(cli._AppWindowCloser(8185), stopped=True) is False
    assert hand_over == []


def test_no_watcher_while_another_window_listens(hand_over, hub_dir):
    marker = hub_dir / "window-8185-55-1.open"
    marker.write_text("u", encoding="utf-8")
    cli._app_window_listening(marker).write_text("55", encoding="utf-8")
    assert cli._hand_over_to_watcher(cli._AppWindowCloser(8185), stopped=False) is False
    assert hand_over == []


def test_no_watcher_for_a_hub_this_launcher_did_not_start(hand_over, monkeypatch):
    monkeypatch.setattr(cli, "_hub_pid_running", lambda port, profile: None)
    assert cli._hand_over_to_watcher(cli._AppWindowCloser(8185), stopped=False) is False
    assert hand_over == []


def test_a_closing_window_says_whether_stop_closed_it(hub_dir):
    marker = hub_dir / "window-8186-1-1.open"
    marker.write_text("u", encoding="utf-8")
    cli._app_window_listening(marker).write_text("1", encoding="utf-8")
    assert cli._app_window_unregister(marker) is False
    assert not marker.exists() and not cli._app_window_listening(marker).exists()
    assert cli._app_window_unregister(marker) is True  # gone already: `agentweave stop` took it
    assert cli._app_window_unregister(None) is False


class _FakeWebview:
    """`webview` for the native window path: `start` returns as a closed window does."""

    def __init__(self):
        self.window = _FakeWindow()

    def create_window(self, *args, **kwargs):
        return self.window

    def start(self, *args, **kwargs):
        return None


class _FakeEvents:
    def __getattr__(self, name):
        return self

    def __iadd__(self, other):
        return self


class _FakeWindow:
    events = _FakeEvents()

    def evaluate_js(self, script):
        return None

    def destroy(self):
        pass


def test_the_native_window_hands_over_once_it_has_closed(hub_dir, monkeypatch):
    seen = []
    monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
    monkeypatch.setattr(cli, "_set_windows_app_user_model_id", lambda: None)
    monkeypatch.setattr(cli, "_app_window_storage", lambda: {})
    monkeypatch.setattr(cli, "_allow_sound_before_a_click", lambda: None)
    monkeypatch.setattr(cli, "_enable_default_context_menus", lambda window: None)
    monkeypatch.setattr(cli, "_make_window_ours", lambda window, port, closer: None)
    monkeypatch.setattr(
        cli, "_hand_over_to_watcher", lambda closer, stopped: seen.append((closer.port, stopped))
    )
    assert cli._open_app_window_native("http://127.0.0.1:8187/") is True
    assert seen == [(8187, False)]
    assert list(hub_dir.glob("window-8187-*")) == []


# --- the real watcher process (FR-2: pythonw, no console) --------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="the watcher runs only on Windows")
def test_a_started_watcher_is_its_own_windowless_process(hub, tmp_path, recorder, monkeypatch):
    home = tmp_path / "home"
    folder = home / ".agentweave" / "hub"
    folder.mkdir(parents=True)
    # The watcher finds its folder from the home directory it inherits: the test's, not ours.
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli, "HUB_DIR", folder)

    argv = notifier.launcher_argv("--watch-notices", str(hub.port))
    if Path(sys.executable).with_name("pythonw.exe").is_file():
        assert argv[0].lower().endswith("pythonw.exe")

    assert _REAL_START_NOTICE_WATCHER(hub.port) is True
    claim, ready = cli._notice_watcher_files(hub.port)
    pid = int(ready.read_text(encoding="utf-8"))
    assert pid != os.getpid()
    try:
        # Started again while it listens: the same watcher, no second one.
        assert _REAL_START_NOTICE_WATCHER(hub.port) is True
        assert int(ready.read_text(encoding="utf-8")) == pid
        assert hub.wait_for_streams(1)

        started = time.monotonic()
        hub.push("operator_notice", _notice("ntc-real-1", "fail"))
        assert _eventually(lambda: _ids(recorder) == ["ntc-real-1"], timeout=10)
        assert time.monotonic() - started < 5.0  # FR-2: within 5 seconds

        marker = folder / f"window-{hub.port}-{os.getpid()}-1.open"
        marker.write_text("u", encoding="utf-8")
        cli._app_window_listening(marker).write_text("1", encoding="utf-8")
        assert _eventually(lambda: not cli.desktop_window.pid_alive(pid), timeout=15)
        assert not claim.exists() and not ready.exists()
    finally:
        if cli.desktop_window.pid_alive(pid):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
