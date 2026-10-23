"""agentweave-opens-on-the-thread: the window opens first, on the splash, and the app follows.

pywebview's real window cannot be driven here (conftest makes `webview` unimportable), so a fake
module stands in. It behaves like pywebview 6 where the CLI depends on it: `create_window` returns
a window whose `events.loaded` fires once the page is up, and `start(func=...)` runs `func` on a
thread of its own while the UI loop holds the main thread.
"""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path

import pytest


class _Hook:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self) -> None:
        for handler in self.handlers:
            handler()


class _Window:
    def __init__(self, log, title, url=None, html=None, **kwargs):
        self.log, self.title, self.url, self.html, self.kwargs = log, title, url, html, kwargs
        self.events = types.SimpleNamespace(loaded=_Hook(), before_show=_Hook(), closed=_Hook())
        self.loaded_at: float | None = None

    def evaluate_js(self, script):
        self.log.append(("evaluate_js", script, time.monotonic()))
        return 300 if "awSplashLeave" in script else None

    def load_url(self, url):
        self.log.append(("load_url", url, time.monotonic()))

    def destroy(self):
        self.log.append(("destroy", None, time.monotonic()))


def _fake_webview(log):
    windows: list[_Window] = []

    def create_window(title, url=None, html=None, **kwargs):
        window = _Window(log, title, url, html, **kwargs)
        windows.append(window)
        log.append(("create_window", html is not None, time.monotonic()))
        return window

    def start(func=None, args=None, **kwargs):
        log.append(("start", kwargs.get("icon"), time.monotonic()))
        worker = threading.Thread(target=func, args=tuple(args or ())) if func else None
        if worker:
            worker.start()
        time.sleep(0.05)  # the page loads a moment after the UI loop starts
        for window in windows:
            window.loaded_at = time.monotonic()
            window.events.loaded.fire()
        if worker:
            worker.join(timeout=20)

    return types.SimpleNamespace(create_window=create_window, start=start, windows=windows)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    log: list = []
    module = _fake_webview(log)
    monkeypatch.setitem(sys.modules, "webview", module)
    monkeypatch.setattr("agentweave.cli.HUB_DIR", tmp_path)
    played: list = []
    monkeypatch.setattr("agentweave.cli._play_sound", lambda path: played.append(Path(path).name))
    monkeypatch.delenv("AGENTWEAVE_SOUND", raising=False)
    return types.SimpleNamespace(log=log, module=module, played=played)


def _first(log, name):
    return next(entry for entry in log if entry[0] == name)


def test_cold_open_shows_the_splash_first_and_the_app_after_the_minimum(fake):
    from agentweave import cli

    seen = {}

    def start_up():
        seen["thread"] = threading.current_thread() is threading.main_thread()
        seen["after_window"] = any(entry[0] == "create_window" for entry in fake.log)
        time.sleep(1.5)
        return "http://127.0.0.1:8161/?project=proj-1", None

    assert cli._open_app_with_splash(start_up, warm=False) == 0

    window = fake.module.windows[0]
    assert window.html and "awSplashLeave" in window.html, "the window opens on the splash page"
    assert window.kwargs.get("background_color", "").lower() in ("#0a0a0b", "#15171c")
    assert seen == {
        "thread": False,
        "after_window": True,
    }, "start-up runs after the window, off the main thread"
    loaded_url = _first(fake.log, "load_url")
    assert loaded_url[1] == "http://127.0.0.1:8161/?project=proj-1"
    assert loaded_url[2] - window.loaded_at >= cli._SPLASH_MIN_COLD == 2.0
    assert fake.played == ["opening.wav"]


def test_warm_open_is_short_and_plays_the_short_phrase(fake):
    from agentweave import cli

    assert cli._open_app_with_splash(lambda: ("http://127.0.0.1:8161/", None), warm=True) == 0
    window = fake.module.windows[0]
    loaded_url = _first(fake.log, "load_url")
    assert cli._SPLASH_MIN_WARM == 1.2
    assert loaded_url[2] - window.loaded_at >= 1.2
    assert loaded_url[2] - window.loaded_at < 2.0
    assert fake.played == ["opening-short.wav"]


def test_sound_can_be_turned_off(fake, monkeypatch):
    from agentweave import cli

    monkeypatch.setenv("AGENTWEAVE_SOUND", "0")
    assert cli._open_app_with_splash(lambda: ("http://127.0.0.1:8161/", None), warm=True) == 0
    assert fake.played == []


def test_a_failed_start_is_said_on_the_splash_then_the_window_closes(fake):
    from agentweave import cli

    assert (
        cli._open_app_with_splash(
            lambda: (None, "Hub failed to start within 60 seconds"), warm=False
        )
        == 1
    )
    said = [entry for entry in fake.log if entry[0] == "evaluate_js" and "awSplashFail" in entry[1]]
    assert said and "Hub failed to start within 60 seconds" in said[0][1]
    assert any(entry[0] == "destroy" for entry in fake.log)
    assert not any(entry[0] == "load_url" for entry in fake.log)


def test_without_pywebview_the_caller_falls_back(monkeypatch):
    from agentweave import cli

    monkeypatch.setitem(sys.modules, "webview", None)
    ran = []
    assert cli._open_app_with_splash(lambda: ran.append(1) or ("u", None), warm=False) is None
    assert (
        ran == []
    ), "nothing is started when the window cannot open; the caller keeps the old order"


def test_the_splash_and_sounds_are_packaged():
    assets = Path(__file__).resolve().parents[1] / "src" / "agentweave" / "assets"
    for name in ("splash.html", "opening.wav", "opening-short.wav"):
        assert (assets / name).is_file(), name
    html = (assets / "splash.html").read_text(encoding="utf-8")
    assert "Run your AI factory in the open." in html
    assert "http" not in html.replace("http://www.w3.org/2000/svg", ""), "the splash loads nothing"
