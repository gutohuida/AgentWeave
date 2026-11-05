"""AgentWeave is its own app on Windows: taskbar identity, one window per Hub, remembered geometry.

Spec `agentweave-is-its-own-app-on-windows`, task AWOAW-2 (D1-D3). The launch decision is tested at
its real call site, `_hub_native_start`'s already-running branch, with the window markers it reads
on disk and only the Win32 window list faked. The shell properties and the placement round trip are
tested against a real window on Windows, since a ctypes call that silently does nothing is the
failure that matters there.
"""

from __future__ import annotations

import sys
import types
import urllib.request

import pytest

from agentweave import cli, desktop_window


class _Health:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def running_hub(tmp_path, monkeypatch):
    """A Hub that answers on its port, with HUB_DIR in tmp_path and the window openers recorded."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_hub_port_accepts", lambda port, timeout=0.3: True)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Health())
    monkeypatch.setattr(cli, "_hub_resolve_launch_url", lambda port, cwd: cli._hub_url(port))
    opened: list = []
    monkeypatch.setattr(
        cli, "_open_app_with_splash", lambda start, warm, port=8000: opened.append(port) or 0
    )
    started: list = []
    monkeypatch.setattr(cli, "_hub_pid_running", lambda **kw: started.append(kw))
    focused: list = []
    monkeypatch.setattr(
        desktop_window, "focus_window", lambda hwnd, owner_pid=None: focused.append(hwnd) or True
    )
    return types.SimpleNamespace(dir=tmp_path, opened=opened, focused=focused, started=started)


def _marker(folder, port, pid):
    path = folder / f"window-{port}-{pid}-1.open"
    path.write_text(f"http://localhost:{port}/", encoding="utf-8")
    return path


def _launch(port=8171):
    return cli._hub_native_start(port=port, detach=True, app=True, cwd=None, profile="default")


# --- D2: one window per Hub ---------------------------------------------------------------------


def test_a_launch_with_the_window_open_focuses_it_and_exits(running_hub, monkeypatch):
    _marker(running_hub.dir, 8171, 4242)
    monkeypatch.setattr(
        desktop_window, "find_app_window", lambda pid: 0xABC if pid == 4242 else None
    )

    assert _launch() == 0
    assert running_hub.focused == [0xABC]
    assert running_hub.opened == [], "no second window"
    assert running_hub.started == [], "no Hub start was attempted"


def test_a_launch_against_a_background_hub_opens_a_window_without_restarting_it(running_hub):
    """FR-5: no window open (no marker), the Hub up -- a window opens on that same Hub."""
    assert _launch() == 0
    assert running_hub.opened == [8171]
    assert running_hub.focused == []
    assert running_hub.started == [], "the running Hub is not restarted"


def test_a_window_on_another_port_is_not_this_hubs(running_hub, monkeypatch):
    _marker(running_hub.dir, 8172, 4242)
    monkeypatch.setattr(desktop_window, "find_app_window", lambda pid: 0xABC)

    assert _launch(8171) == 0
    assert running_hub.focused == []
    assert running_hub.opened == [8171]


def test_a_marker_left_by_a_dead_process_is_cleared_and_a_window_opens(running_hub, monkeypatch):
    stale = _marker(running_hub.dir, 8171, 4242)
    monkeypatch.setattr(desktop_window, "pid_alive", lambda pid: False)

    assert _launch() == 0
    assert not stale.exists()
    assert running_hub.opened == [8171]


def test_a_live_process_with_no_window_keeps_its_marker_and_a_window_opens(running_hub):
    """The marker's process lives but shows no app window (the default stub): passed over, kept."""
    live = _marker(running_hub.dir, 8171, 4242)

    assert _launch() == 0
    assert live.exists()
    assert running_hub.opened == [8171]


def test_marker_pid_reads_the_writers_process_from_the_name(tmp_path):
    assert cli._marker_pid(tmp_path / "window-8000-10312-38436.open") == 10312
    assert cli._marker_pid(tmp_path / "window-8000.open") is None


# --- D3: geometry -------------------------------------------------------------------------------

PRIMARY = {"x": 0, "y": 0, "width": 1920, "height": 1040}


def _kwargs(saved, on_screen=True):
    return desktop_window.window_kwargs(saved, lambda g: on_screen, lambda: PRIMARY)


def test_nothing_stored_keeps_pywebviews_defaults():
    assert _kwargs(None) == {}


def test_closed_maximized_reopens_maximized():
    saved = {"x": 100, "y": 50, "width": 1200, "height": 800, "maximized": True}
    assert _kwargs(saved) == {"x": 100, "y": 50, "width": 1200, "height": 800, "maximized": True}


def test_closed_at_a_size_and_position_reopens_there():
    saved = {"x": 130, "y": 70, "width": 1200, "height": 800, "maximized": False}
    assert _kwargs(saved) == {"x": 130, "y": 70, "width": 1200, "height": 800}


def test_off_every_screen_reopens_on_the_primary_screen_at_its_size():
    saved = {"x": 4000, "y": 70, "width": 1200, "height": 800, "maximized": False}
    assert _kwargs(saved, on_screen=False) == {"x": 360, "y": 120, "width": 1200, "height": 800}


def test_geometry_round_trips_and_rejects_what_it_did_not_write(tmp_path):
    path = tmp_path / "app-window" / "window-8171.json"
    saved = {"x": -8, "y": 0, "width": 1200, "height": 800, "maximized": True}
    assert desktop_window.write_geometry(path, saved)
    assert desktop_window.read_geometry(path) == saved

    path.write_text("not json", encoding="utf-8")
    assert desktop_window.read_geometry(path) is None
    path.write_text('{"x": 1, "y": 2, "width": 10, "height": 10}', encoding="utf-8")
    assert desktop_window.read_geometry(path) is None, "a window too small to use is not restored"
    assert desktop_window.read_geometry(tmp_path / "missing.json") is None


def test_the_geometry_file_is_per_port(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    assert cli._app_window_geometry_file(8000) != cli._app_window_geometry_file(8171)


class _Event:
    def __init__(self):
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def _fake_window():
    return types.SimpleNamespace(
        events=types.SimpleNamespace(before_show=_Event(), closing=_Event()),
        native=types.SimpleNamespace(Handle=types.SimpleNamespace(ToInt64=lambda: 0x123)),
    )


def test_the_window_opens_with_its_remembered_geometry_and_saves_it_on_close(tmp_path, monkeypatch):
    """The real `_open_app_window_native`: create_window gets the stored geometry; the closing hook
    writes the window's placement back, and before_show writes its shell properties."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    stored = {"x": 130, "y": 70, "width": 1200, "height": 800, "maximized": True}
    desktop_window.write_geometry(cli._app_window_geometry_file(8171), stored)
    monkeypatch.setattr(desktop_window, "on_a_screen", lambda g: True)
    identity: list = []
    monkeypatch.setattr(
        desktop_window,
        "set_window_identity",
        lambda hwnd, command, icon: identity.append((hwnd, command, icon)) or True,
    )
    closed_at = {"x": 10, "y": 20, "width": 1000, "height": 700, "maximized": False}
    monkeypatch.setattr(desktop_window, "placement", lambda hwnd: dict(closed_at, hwnd=hwnd))

    window = _fake_window()
    created: dict = {}

    def create_window(title, url, **kwargs):
        created.update(kwargs)
        return window

    monkeypatch.setitem(
        sys.modules,
        "webview",
        types.SimpleNamespace(create_window=create_window, start=lambda **kw: None),
    )
    assert cli._open_app_window_native("http://127.0.0.1:8171/") is True
    assert {k: created[k] for k in ("x", "y", "width", "height", "maximized")} == stored

    _context_menus, before_show = window.events.before_show.handlers
    before_show(window)
    ((hwnd, command, icon),) = identity
    target, arguments = cli._resolve_shortcut_target()
    assert hwnd == 0x123
    assert command == f'"{target}" {arguments}'.strip()
    assert icon is not None and icon.endswith("icon.ico")

    (closing,) = window.events.closing.handlers
    closing(window)
    assert desktop_window.read_geometry(cli._app_window_geometry_file(8171)) == closed_at


def test_the_splash_window_carries_the_same_hooks(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    window = _fake_window()
    window.events.loaded = _Event()
    seen: dict = {}

    def create_window(title, url=None, html=None, **kwargs):
        seen.update(kwargs)
        return window

    desktop_window.write_geometry(
        cli._app_window_geometry_file(8172),
        {"x": 5, "y": 6, "width": 1200, "height": 800, "maximized": False},
    )
    monkeypatch.setattr(desktop_window, "on_a_screen", lambda g: True)
    monkeypatch.setitem(
        sys.modules,
        "webview",
        types.SimpleNamespace(create_window=create_window, start=lambda **kw: None),
    )
    assert cli._open_app_with_splash(lambda: (None, "x"), warm=True, port=8172) == 0
    assert (seen["width"], seen["height"], seen["x"], seen["y"]) == (1200, 800, 5, 6)
    assert len(window.events.before_show.handlers) == 2  # context menus, then identity
    assert len(window.events.closing.handlers) == 1


def test_relaunch_command_quotes_the_target():
    assert (
        desktop_window.relaunch_command(r"C:\Py 3\pythonw.exe", "-m agentweave")
        == '"C:\\Py 3\\pythonw.exe" -m agentweave'
    )


# --- Win32, against a real window --------------------------------------------------------------

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Win32 shell properties")


@pytest.fixture
def real_window():
    """A plain hidden top-level window of this process (a STATIC control), destroyed after."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.CreateWindowExW.argtypes = (
        [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p]
        + [ctypes.c_int] * 5
        + [ctypes.c_void_p] * 4
    )
    user32.CreateWindowExW.argtypes[3] = ctypes.c_uint
    hwnd = user32.CreateWindowExW(
        0, "STATIC", "aw-test", 0x00CF0000, 140, 90, 1200, 800, None, None, None, None
    )
    assert hwnd, "a test window could be created"
    yield int(hwnd)
    user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    user32.DestroyWindow(hwnd)


def _read_shell_properties(hwnd):
    """Read back with the drive's own reader (scripts/drive/d1105_own_app.py), not this module's."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "drive" / "d1105_own_app.py"
    spec = importlib.util.spec_from_file_location("d1105_own_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.shell_properties(hwnd)


@windows_only
def test_the_shell_properties_are_written_and_read_back(real_window):
    icon = cli._app_icon_path()
    command = desktop_window.relaunch_command(*cli._resolve_shortcut_target())
    assert desktop_window.set_window_identity(real_window, command, icon) is True

    props = _read_shell_properties(real_window)
    assert props == {
        "app_id": "AgentWeave.Hub",
        "relaunch_command": command,
        "relaunch_icon": f"{icon},0",
        "relaunch_name": "AgentWeave",
    }


@windows_only
def test_the_placement_reads_the_windows_restored_rectangle(real_window):
    """Hidden throughout, so nothing appears on the operator's screen; the maximized case runs in
    the drive, on a real app window."""
    geometry = desktop_window.placement(real_window)
    scale = desktop_window._scale_for(real_window)
    assert geometry is not None
    assert geometry["maximized"] is False
    assert (geometry["width"], geometry["height"]) == (round(1200 / scale), round(800 / scale))


@windows_only
def test_a_position_far_off_every_screen_is_not_on_a_screen():
    assert desktop_window.on_a_screen({"x": 100, "y": 100, "width": 800, "height": 600})
    assert not desktop_window.on_a_screen({"x": 60000, "y": 60000, "width": 800, "height": 600})
