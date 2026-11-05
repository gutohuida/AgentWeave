"""Closing the app window stops the Hub, asking first when work runs, unless the setting says not to.

Spec `agentweave-is-its-own-app-on-windows`, task AWOAW-3 (D4, D5; FR-7 to FR-11). The close is
driven through the real `_open_app_window_native` with a fake pywebview whose `start` closes the
window the way WinForms does (the `closing` handlers run, and a False cancels), against a real HTTP
server on a local port answering `/health`, `/api/v1/setup/token` and `/api/v1/work/running` in the
shape the Hub's route returns. The stop is `agentweave stop`'s real path, with only the process kill
recorded instead of done.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

import pytest

from agentweave import cli, desktop_window

_IDLE: Dict[str, Any] = {
    "running": False,
    "turns": 0,
    "check_runs": 0,
    "landings": 0,
    "builds": 0,
    "turn_agents": [],
    "build_list": [],
}
_ONE_TURN = dict(_IDLE, running=True, turns=1, turn_agents=[{"agent": "a", "project": "p"}])
_A_BUILD = dict(
    _IDLE,
    running=True,
    builds=1,
    build_list=[{"id": "build-1", "title": "Close means stop", "project": "p"}],
)


class _FakeHub:
    """A local HTTP server standing in for a Hub: what work it reports is `self.work`."""

    def __init__(self) -> None:
        self.work: Optional[Dict[str, Any]] = dict(_IDLE)
        self.work_status = 200
        self.asked: List[str] = []
        #: Seconds each `/health` answer is held back, in order; the rest answer at once.
        self.health_delays: List[float] = []
        hub = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                hub.asked.append(self.path)
                if self.path == "/health":
                    if hub.health_delays:
                        time.sleep(hub.health_delays.pop(0))
                    self._send(200, {"status": "ok", "runtime": "native"})
                elif self.path == "/api/v1/setup/token":
                    self._send(200, {"api_key": "aw_live_test"})
                elif self.path == "/api/v1/work/running":
                    if self.headers.get("Authorization") != "Bearer aw_live_test":
                        self._send(401, {"detail": "no"})
                    else:
                        self._send(hub.work_status, hub.work)
                else:
                    self._send(404, {})

            def _send(self, code: int, body: Any) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def hub(tmp_path, monkeypatch):
    """A fake Hub on a free local port, HUB_DIR in tmp_path, with a PID file for that port and the
    stop's process kill recorded rather than done."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_hub_url", lambda port=8000: f"http://127.0.0.1:{port}")
    fake = _FakeHub()
    # Something listens on the fake Hub's port, and on no other.
    monkeypatch.setattr(cli, "_hub_port_accepts", lambda port, timeout=0.3: port == fake.port)
    killed: List[int] = []
    monkeypatch.setattr(cli, "_hub_kill_pid", lambda pid: killed.append(pid))
    # The PID is this test process's own: alive, and never actually killed (recorded above).
    import os

    cli._hub_pid_file(fake.port).write_text(f"{os.getpid()}\n{fake.port}\n", encoding="utf-8")
    fake.killed = killed  # type: ignore[attr-defined]
    fake.pid = os.getpid()  # type: ignore[attr-defined]
    yield fake
    fake.close()


class _Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler: Any) -> "_Event":
        self.handlers.append(handler)
        return self


class _Window:
    """A pywebview window as the close sees it: `closing` handlers run on a close and any False
    cancels it, as WinForms' FormClosing does (webview/platforms/winforms.py `on_closing`)."""

    def __init__(self, page_has_prompt: bool = True) -> None:
        self.events = types.SimpleNamespace(before_show=_Event(), closing=_Event())
        self.native = types.SimpleNamespace(Handle=types.SimpleNamespace(ToInt64=lambda: 0))
        self.page_has_prompt = page_has_prompt
        self.prompts: List[Dict[str, Any]] = []
        self.prompted = threading.Event()
        self.closed = threading.Event()

    def close(self) -> bool:
        """The operator's click on the close button: whether the window went."""
        results = [handler(self) for handler in self.events.closing.handlers]
        if any(result is False for result in results):
            return False
        self.closed.set()
        return True

    def destroy(self) -> None:
        self.close()

    def evaluate_js(self, script: str) -> Any:
        if not self.page_has_prompt:
            return False
        payload = script[len("window.awClosePrompt ? (window.awClosePrompt(") :]
        payload = payload[: payload.rindex("), true) : false")]
        self.prompts.append(json.loads(payload))
        self.prompted.set()
        return True


def _open(hub: _FakeHub, monkeypatch, script, page_has_prompt: bool = True) -> _Window:
    """Open the real native window on `hub`'s port and run `script(window, bridge)` as its life:
    `webview.start` returns when the script does, as it returns when the window has gone."""
    window = _Window(page_has_prompt)
    seen: Dict[str, Any] = {}

    def create_window(title, url, **kwargs):
        seen["bridge"] = kwargs["js_api"]
        return window

    def start(**_kw):
        script(window, seen["bridge"])

    monkeypatch.setitem(
        sys.modules, "webview", types.SimpleNamespace(create_window=create_window, start=start)
    )
    assert cli._open_app_window_native(f"http://127.0.0.1:{hub.port}/") is True
    return window


# --- the decision (D4, D5) ----------------------------------------------------------------------


def test_with_the_setting_on_the_hub_is_never_asked():
    """FR-11: the launcher reads the stored choice before it asks the Hub anything."""
    asked: list = []
    decision = desktop_window.close_decision(
        lambda: True, lambda: asked.append("work") or _ONE_TURN, lambda: asked.append("up") or True
    )
    assert decision == (desktop_window.CLOSE_WINDOW_ONLY, None)
    assert asked == []


def test_idle_stops_busy_asks():
    assert desktop_window.close_decision(lambda: False, lambda: _IDLE, lambda: True) == (
        desktop_window.CLOSE_AND_STOP,
        None,
    )
    assert desktop_window.close_decision(lambda: False, lambda: _ONE_TURN, lambda: True) == (
        desktop_window.CLOSE_ASKS,
        _ONE_TURN,
    )


def test_a_hub_that_is_up_but_cannot_answer_is_never_taken_as_idle():
    decision, work = desktop_window.close_decision(lambda: False, lambda: None, lambda: True)
    assert decision == desktop_window.CLOSE_ASKS and work == {"unknown": True}
    # Not up at all: nothing left to protect, so the close goes ahead as when idle.
    assert desktop_window.close_decision(lambda: False, lambda: None, lambda: False) == (
        desktop_window.CLOSE_AND_STOP,
        None,
    )


def test_the_prompt_names_what_is_running():
    assert desktop_window.describe_work(_ONE_TURN) == "1 agent turn is running"
    assert desktop_window.describe_work(_A_BUILD) == "The build Close means stop is running"
    assert (
        desktop_window.describe_work(dict(_A_BUILD, turns=2, check_runs=1))
        == "2 agent turns, 1 check run and the build Close means stop are running"
    )
    assert desktop_window.describe_work({"unknown": True}).startswith("AgentWeave could not say")


def test_the_setting_is_off_by_default_survives_and_is_per_port(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    first = cli._AppWindowCloser(8171)
    assert first.keeps_running() is False
    assert first.set_keeps_running(True) is True
    # A new closer is a restarted app: it reads the stored choice.
    assert cli._AppWindowCloser(8171).keeps_running() is True
    assert cli._AppWindowCloser(8172).keeps_running() is False
    assert cli._app_close_setting_file(8171).parent == cli._app_window_geometry_file(8171).parent


def test_app_settings_reads_and_writes_the_setting_through_the_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    bridge = cli._AppWindowApi(cli._AppWindowCloser(8171))
    assert bridge.close_keeps_running() is False
    assert bridge.set_close_keeps_running(True) is True
    assert bridge.close_keeps_running() is True
    assert desktop_window.read_keeps_running(cli._app_close_setting_file(8171)) is True
    # A bridge with no closer (a page outside the app window) answers no and changes nothing.
    assert cli._AppWindowApi().set_close_keeps_running(True) is False


# --- the close, end to end through the real window opener ----------------------------------------


def test_closing_while_idle_stops_the_hub_without_asking(hub, monkeypatch):
    """FR-7: no prompt; the Hub is stopped by `agentweave stop`'s path once the window has gone.

    The close is held while the Hub is asked, off the window's thread, then the window is closed."""

    def life(window, bridge):
        assert window.close() is False
        assert window.closed.wait(5)
        assert hub.killed == []  # not while the window is still going

    window = _open(hub, monkeypatch, life)
    assert window.prompts == []
    assert hub.killed == [hub.pid]
    assert not cli._hub_pid_file(hub.port).exists()
    assert "/api/v1/work/running" in hub.asked


def test_closing_while_busy_asks_and_cancel_leaves_everything(hub, monkeypatch):
    """FR-8: the close is cancelled and the prompt names one agent turn; Cancel changes nothing,
    and the next close asks again."""
    hub.work = _ONE_TURN

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        assert window.prompts[-1]["turns"] == 1
        assert bridge.close_choice("cancel") is True
        assert not window.closed.is_set()
        window.prompted.clear()
        assert window.close() is False
        assert window.prompted.wait(5)
        bridge.close_choice("keep")  # let the test end

    window = _open(hub, monkeypatch, life)
    assert len(window.prompts) == 2
    assert hub.killed == []


def test_keep_running_closes_the_window_only(hub, monkeypatch):
    hub.work = _ONE_TURN

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        assert bridge.close_choice("keep") is True
        assert window.closed.is_set()

    _open(hub, monkeypatch, life)
    assert hub.killed == []
    assert cli._hub_pid_file(hub.port).exists()


def test_stop_it_all_closes_and_stops_the_hub(hub, monkeypatch):
    hub.work = _ONE_TURN

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        assert bridge.close_choice("stop") is True
        assert window.closed.is_set()

    _open(hub, monkeypatch, life)
    assert hub.killed == [hub.pid]


def test_a_build_between_its_firings_makes_the_close_ask(hub, monkeypatch):
    """FR-9: the Hub's answer counts a running build with no turn; the window asks, naming it."""
    hub.work = _A_BUILD

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        bridge.close_choice("keep")

    window = _open(hub, monkeypatch, life)
    assert window.prompts[0]["build_list"][0]["title"] == "Close means stop"
    assert hub.killed == []


def test_without_the_page_prompt_the_native_box_asks(hub, monkeypatch):
    """On a page that cannot show the prompt, the operator is still asked, never guessed for."""
    hub.work = _ONE_TURN
    asked: list = []
    monkeypatch.setattr(
        desktop_window,
        "ask_natively",
        lambda hwnd, work: asked.append(work) or desktop_window.CHOICE_STOP,
    )

    def life(window, bridge):
        assert window.close() is False
        assert window.closed.wait(5)

    _open(hub, monkeypatch, life, page_has_prompt=False)
    assert asked == [_ONE_TURN]
    assert hub.killed == [hub.pid]


def test_a_hub_that_answers_an_error_is_asked_about(hub, monkeypatch):
    hub.work_status = 500

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        assert window.prompts[0] == {"unknown": True}
        bridge.close_choice("keep")

    _open(hub, monkeypatch, life)
    assert hub.killed == []


def test_with_the_setting_on_the_window_closes_and_the_hub_is_left(hub, monkeypatch):
    """FR-11: no question to the Hub, no prompt, no stop."""
    desktop_window.write_keeps_running(cli._app_close_setting_file(hub.port), True)

    def life(window, bridge):
        assert window.close() is True

    window = _open(hub, monkeypatch, life)
    assert window.prompts == []
    assert hub.killed == []
    assert "/api/v1/work/running" not in hub.asked


def test_a_close_agentweave_stop_asked_for_is_not_second_guessed(hub, monkeypatch):
    """`agentweave stop` deletes the window's marker and the watcher destroys it: no question, and
    no second stop."""

    def life(window, bridge):
        cli._app_windows_close(hub.port)
        assert window.close() is True

    _open(hub, monkeypatch, life)
    assert hub.killed == []
    assert "/api/v1/work/running" not in hub.asked


def test_a_close_on_the_splash_stops_the_hub_once_the_start_up_is_done(hub, monkeypatch):
    """A slow start (the drive's two Hubs at once) left the window on the splash long enough to be
    closed there; the close then left the Hub running. It is decided like any other close, and the
    stop waits for the start-up, so it finds the Hub that start-up spawned; no app is then shown."""
    window = _Window(page_has_prompt=False)
    window.events.loaded = _Event()
    loaded_urls: list = []
    window.load_url = loaded_urls.append  # type: ignore[attr-defined]
    started_up = threading.Event()
    order: list = []

    def start():
        # Still starting when the operator closes the window.
        assert window.closed.wait(5)
        order.append("start-up done")
        started_up.set()
        return f"http://127.0.0.1:{hub.port}/", None

    def run(func, **_kw):
        for handler in window.events.loaded.handlers:
            handler()
        threading.Thread(target=func, daemon=True).start()
        window.close()
        assert window.closed.wait(5)

    monkeypatch.setattr(cli, "_splash_html", lambda warm: "<html></html>")
    monkeypatch.setattr(cli, "_SPLASH_MIN_WARM", 0)
    monkeypatch.setattr(cli, "_play_opening_sound", lambda short: None)
    monkeypatch.setattr(
        cli, "_hub_kill_pid", lambda pid: order.append("stopped") or hub.killed.append(pid)
    )
    monkeypatch.setitem(
        sys.modules,
        "webview",
        types.SimpleNamespace(create_window=lambda *a, **k: window, start=run),
    )
    assert cli._open_app_with_splash(start, warm=True, port=hub.port) == 0
    assert started_up.is_set()
    assert order == ["start-up done", "stopped"]
    assert hub.killed == [hub.pid]
    assert loaded_urls == []
    assert not list(cli.HUB_DIR.glob(f"window-{hub.port}-*.open"))


def test_a_close_stops_only_its_own_ports_hub(hub, tmp_path, monkeypatch):
    """FR-10: the stop runs for the window's port alone; another port's Hub and its PID file are
    left as they were."""
    other_port = hub.port + 1 if hub.port < 65535 else hub.port - 1
    other = cli._hub_pid_file(other_port)
    other.write_text(f"999999\n{other_port}\n", encoding="utf-8")

    def life(window, bridge):
        window.close()
        assert window.closed.wait(5)

    _open(hub, monkeypatch, life)
    assert hub.killed == [hub.pid]
    assert other.exists()


def test_a_close_while_the_question_is_unanswered_shows_it_again(hub, monkeypatch):
    """A page answer that never arrived (a reload, a lost bridge call) must not leave every later
    close refused in silence: the next close shows the prompt again, without asking the Hub again.
    """
    hub.work = _ONE_TURN

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        window.prompted.clear()
        asked = hub.asked.count("/api/v1/work/running")
        assert window.close() is False  # no answer was given to the first prompt
        assert window.prompted.wait(5)
        assert hub.asked.count("/api/v1/work/running") == asked
        bridge.close_choice("keep")

    window = _open(hub, monkeypatch, life)
    assert len(window.prompts) == 2
    assert hub.killed == []


# --- a busy Hub slow to answer its health check (QA's send-back of AWOAW-3) ---------------------


def test_stop_it_all_waits_for_a_busy_hub_slow_to_answer_its_health_check(hub, monkeypatch):
    """The first `/health` outlasts an attempt; the stop asks again rather than taking the Hub for
    a recycled PID, deleting its PID file and leaving it serving."""
    monkeypatch.setattr(cli, "_HUB_HEALTH_ATTEMPT_SECONDS", 2.0)
    hub.work = _ONE_TURN

    def life(window, bridge):
        assert window.close() is False
        assert window.prompted.wait(5)
        hub.health_delays = [3.0]
        assert bridge.close_choice("stop") is True

    _open(hub, monkeypatch, life)
    assert hub.killed == [hub.pid]
    assert hub.asked.count("/health") >= 2
    assert not cli._hub_pid_file(hub.port).exists()


def test_a_hub_that_never_answers_is_neither_killed_nor_forgotten(hub, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_HUB_HEALTH_ATTEMPT_SECONDS", 2.0)
    monkeypatch.setattr(cli, "_HUB_STOP_PATIENCE_SECONDS", 3)
    hub.health_delays = [5.0, 5.0, 5.0]
    import argparse

    code = cli.cmd_stop(argparse.Namespace(port=hub.port, profile="default", local=False))
    assert code == 1
    assert hub.killed == []
    assert cli._hub_pid_file(hub.port).exists()
    assert "did not answer" in capsys.readouterr().out


def test_health_answers_tell_silence_from_absence(hub):
    assert cli._hub_native_answer(hub.port) == cli._HUB_ANSWERED
    hub.health_delays = [3.0]
    assert cli._hub_native_answer(hub.port) == cli._HUB_SILENT
    import socket

    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    assert cli._hub_native_answer(port) == cli._HUB_ABSENT
