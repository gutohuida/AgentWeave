"""F724: `agentweave stop` left the desktop window that start opened, alive on a dead Hub.

The window runs in the starting process (pywebview blocks in `webview.start`), not in the Hub, so
killing the Hub never touched it. Driven here through the real `_open_app_window_native` (with a
fake pywebview whose `start` blocks until the window is destroyed, as the real one does) and the
real `cmd_stop`.
"""

import argparse
import sys
import threading
import types

import pytest

from agentweave import cli


class _BlockingWebview:
    """pywebview's shape: `start` blocks until the window is destroyed."""

    def __init__(self):
        self.destroyed = threading.Event()
        self.started = threading.Event()

    def create_window(self, title, url, **kwargs):
        return types.SimpleNamespace(destroy=self.destroyed.set)

    def start(self, **kwargs):
        self.started.set()
        if not self.destroyed.wait(timeout=10):
            raise AssertionError("the window was never closed")


@pytest.fixture
def native_hub(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_APP_WINDOW_POLL_SECONDS", 0.02, raising=False)
    killed = []
    monkeypatch.setattr(cli, "_hub_pid_running", lambda **kw: 4242)
    monkeypatch.setattr(cli, "_hub_native_confirmed", lambda port: True)
    monkeypatch.setattr(cli, "_hub_kill_pid", killed.append)
    fake = _BlockingWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake, killed


def _open_window(url):
    result = {}
    thread = threading.Thread(
        target=lambda: result.setdefault("ok", cli._open_app_window_native(url)), daemon=True
    )
    thread.start()
    return thread, result


def test_stop_closes_the_window_start_opened(native_hub, capsys):
    fake, killed = native_hub
    thread, result = _open_window("http://localhost:8046/?project=proj-1&tab=overview")
    assert fake.started.wait(timeout=5)

    code = cli.cmd_stop(argparse.Namespace(port=8046, profile="sweep", local=False))

    thread.join(timeout=5)
    assert code == 0 and killed == [4242]
    assert fake.destroyed.is_set(), "the window outlived the Hub it shows"
    assert not thread.is_alive() and result["ok"] is True
    assert list(cli.HUB_DIR.glob("window-*.open")) == []


def test_stop_leaves_a_window_on_another_hub_alone(native_hub, capsys):
    fake, _ = native_hub
    thread, _ = _open_window("http://localhost:8047/")
    assert fake.started.wait(timeout=5)

    cli.cmd_stop(argparse.Namespace(port=8046, profile="sweep", local=False))

    assert not fake.destroyed.wait(timeout=0.3)
    assert len(list(cli.HUB_DIR.glob("window-8047-*.open"))) == 1
    fake.destroyed.set()
    thread.join(timeout=5)
    # The window's own exit removes its marker.
    assert list(cli.HUB_DIR.glob("window-*.open")) == []
