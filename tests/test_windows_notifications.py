"""Windows notifications for what calls the operator: the launcher's side.

Change `windows-notifications-for-what-calls-the-operator`, task launcher-notify (FR-1, FR-5, FR-6,
FR-8). The notifier is driven through `AW_TOAST_COMMAND`, the seam the CONTRACT names for drives and
for the quiet-failure check; nothing here shows a real toast or writes the operator's registry
(conftest's `_no_windows_notification_is_shown`).
"""

import json
import re
import sys
import threading
import types

import pytest

from agentweave import cli, desktop_window, notifier

NOTICE = {
    "id": "ntc-0123456789abcdef",
    "kind": "ask",
    "project_id": "proj-abc123",
    "agent": "behindbot",
    "conversation_id": "conv-def456",
    "title": "An agent needs you",
    "text": "behindbot asks: Proceed with <the> plan & ship?",
    "source_event": "question_asked",
}


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(notifier, "supported", lambda: True)


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
    return lambda: [json.loads(p.read_text(encoding="utf-8")) for p in out.iterdir()]


# --- the link a click opens (FR-6) -------------------------------------------------------------


def test_a_question_links_to_its_conversation_in_path_segments():
    link = notifier.link_for_notice(8180, NOTICE)
    # Path segments, never a query: explorer.exe drops an agentweave: link holding `?`.
    assert link == "agentweave:open/8180/proj-abc123/behindbot/conv-def456"
    assert "?" not in link and "&" not in link
    assert notifier.parse_open_link(link) == {
        "port": 8180,
        "project_id": "proj-abc123",
        "agent": "behindbot",
        "conversation_id": "conv-def456",
    }


def test_a_notice_without_a_conversation_links_to_the_project_overview():
    permission = {**NOTICE, "conversation_id": None, "source_event": "tool_permission_requested"}
    link = notifier.link_for_notice(8180, permission)
    assert link == "agentweave:open/8180/proj-abc123"
    target = notifier.parse_open_link(link)
    assert (
        notifier.app_url(8180, target) == "http://127.0.0.1:8180/?project=proj-abc123&tab=overview"
    )


def test_the_conversation_url_is_the_one_the_page_parses():
    target = notifier.parse_open_link("agentweave:open/8180/proj-abc123/behindbot/conv-def456/")
    assert (
        notifier.app_url(8180, target)
        == "http://127.0.0.1:8180/?project=proj-abc123&agent=behindbot&conversation=conv-def456"
    )


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/open/8180",
        "agentweave:open",
        "agentweave:open/notaport",
        "agentweave:open/8180/proj/agent",  # an agent with no conversation is not a link we write
        'agentweave:open/8180/proj"&calc',
        "agentweave:other/8180",
        None,
    ],
)
def test_a_link_this_module_would_not_write_is_refused(link):
    assert notifier.parse_open_link(link) is None


def test_a_segment_that_could_carry_structure_is_left_out_of_the_link():
    link = notifier.open_link(8180, "proj-1", "bad agent", "conv-1")
    assert link == "agentweave:open/8180/proj-1"


def test_the_registered_handler_runs_the_launcher_with_the_link():
    command = notifier.handler_command()
    assert command.endswith('--open "%1"')
    assert "from agentweave.cli import main" in command
    # Explorer starts it with its own environment: it carries where this process found its code.
    assert repr(str(__import__("pathlib").Path(notifier.__file__).resolve().parents[1])) in command


def test_registering_the_link_writes_hkcu_only(monkeypatch, on_windows):
    written = {}

    class _Key:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        REG_SZ=1,
        CreateKey=lambda root, path: (
            (_ for _ in ()).throw(AssertionError(root)) if root != "HKCU" else _Key(path)
        ),
        SetValueEx=lambda key, name, _r, _t, value: written.__setitem__((key.path, name), value),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert notifier.register_link() is True
    assert written[(r"Software\Classes\agentweave", "URL Protocol")] == ""
    assert written[(r"Software\Classes\agentweave\shell\open\command", "")].endswith('--open "%1"')


# --- showing one (FR-1, FR-5) ------------------------------------------------------------------


def test_the_toast_carries_the_in_app_words_and_its_link():
    xml = notifier.toast_xml({**NOTICE, "project_name": "Spike"}, "agentweave:open/8180/p/a/c")
    assert 'activationType="protocol"' in xml
    assert 'launch="agentweave:open/8180/p/a/c"' in xml
    # The in-app toast's title is the notice's text (it names the agent), its description the project.
    assert "<text>behindbot asks: Proceed with &lt;the&gt; plan &amp; ship?</text>" in xml
    assert "<text>Spike</text>" in xml


def test_the_toast_is_shown_under_agentweaves_own_app_id():
    script = notifier._show_script("<toast/>", "ntc-1")
    assert f"CreateToastNotifier('{desktop_window.APP_ID}')" in script
    assert desktop_window.APP_ID == "AgentWeave.Hub"


def test_a_notice_is_shown_once_with_its_link(tmp_path, on_windows, recorder):
    assert notifier.show(NOTICE, 8180, tmp_path) is True
    shown = recorder()
    assert len(shown) == 1
    assert shown[0]["app_id"] == "AgentWeave.Hub"
    assert shown[0]["link"] == "agentweave:open/8180/proj-abc123/behindbot/conv-def456"
    assert "behindbot" in shown[0]["xml"]
    # The same notice again, from the window or the watcher: nothing more (D3's ledger).
    assert notifier.show(NOTICE, 8180, tmp_path) is False
    assert len(recorder()) == 1


def test_two_paths_racing_on_one_notice_show_it_once(tmp_path, on_windows, recorder):
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(notifier.show(NOTICE, 8180, tmp_path)))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results) == [False, False, False, True]
    assert len(recorder()) == 1


def test_the_ledger_is_per_port(tmp_path):
    assert notifier.claim(tmp_path, 8180, "ntc-1") is True
    assert notifier.claim(tmp_path, 8180, "ntc-1") is False
    assert notifier.claim(tmp_path, 8000, "ntc-1") is True


@pytest.mark.parametrize("bad", [None, "text", {}, {**NOTICE, "id": ""}, {**NOTICE, "text": ""}])
def test_a_notice_without_an_id_or_words_is_not_shown(tmp_path, on_windows, recorder, bad):
    if isinstance(bad, dict) and bad.get("text") == "":
        bad = {**bad, "title": ""}
    assert notifier.show(bad, 8180, tmp_path) is False
    assert recorder() == []


# --- quiet failure (FR-8) ----------------------------------------------------------------------


def test_off_windows_the_notifier_does_nothing(tmp_path, monkeypatch, recorder):
    monkeypatch.setattr(notifier.sys, "platform", "linux")
    assert notifier.supported() is False
    assert notifier.show(NOTICE, 8180, tmp_path) is False
    assert notifier.register_link() is False
    assert notifier.ensure_shortcut("t", "", None) is False
    assert recorder() == []
    assert not (tmp_path / "notified").exists()


def test_a_failing_shell_call_answers_false_and_frees_the_notice(tmp_path, monkeypatch, on_windows):
    monkeypatch.setenv(
        notifier.TOAST_COMMAND_ENV, f'"{sys.executable}" -c "import sys; sys.exit(7)"'
    )
    assert notifier.show(NOTICE, 8180, tmp_path) is False
    # Nothing was shown, so the other path (window or watcher) may still try.
    assert notifier.claim(tmp_path, 8180, NOTICE["id"]) is True


def test_a_shell_call_that_cannot_start_never_raises(tmp_path, monkeypatch, on_windows):
    monkeypatch.setenv(notifier.TOAST_COMMAND_ENV, str(tmp_path / "no-such-program.exe"))
    assert notifier.show(NOTICE, 8180, tmp_path) is False


def test_a_shell_call_that_hangs_times_out_quietly(tmp_path, monkeypatch, on_windows):
    monkeypatch.setattr(notifier, "_SHOW_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setenv(
        notifier.TOAST_COMMAND_ENV, f'"{sys.executable}" -c "import time; time.sleep(30)"'
    )
    assert notifier.show(NOTICE, 8180, tmp_path) is False


# --- the bridge (FR-1, FR-3, FR-8) -------------------------------------------------------------


def _bridge(port=8180):
    return cli._AppWindowApi(cli._AppWindowCloser(port))


def test_the_bridge_shows_a_notice_while_the_window_is_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_foreground_is_ours", lambda: False)
    calls = []
    monkeypatch.setattr(
        cli.notifier,
        "show",
        lambda notice, port, hub_dir: calls.append((notice, port, hub_dir)) or True,
    )
    assert _bridge().notify(NOTICE) is True
    assert calls == [(NOTICE, 8180, tmp_path)]


def test_the_bridge_refuses_while_the_window_is_in_front(monkeypatch):
    monkeypatch.setattr(cli, "_foreground_is_ours", lambda: True)
    monkeypatch.setattr(
        cli.notifier, "show", lambda *a: (_ for _ in ()).throw(AssertionError("shown in front"))
    )
    assert _bridge().notify(NOTICE) is False


def test_the_bridge_never_raises(monkeypatch):
    monkeypatch.setattr(cli, "_foreground_is_ours", lambda: False)
    monkeypatch.setattr(
        cli.notifier, "show", lambda *a: (_ for _ in ()).throw(RuntimeError("shell gone"))
    )
    assert _bridge().notify(NOTICE) is False
    assert cli._AppWindowApi(None).notify(NOTICE) is False


def test_the_bridge_with_a_failing_toast_command_carries_on(tmp_path, monkeypatch, on_windows):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_foreground_is_ours", lambda: False)
    monkeypatch.setenv(
        notifier.TOAST_COMMAND_ENV, f'"{sys.executable}" -c "import sys; sys.exit(7)"'
    )
    assert _bridge().notify(NOTICE) is False


# --- a click: the open target (FR-6) -----------------------------------------------------------

LINK = "agentweave:open/8180/proj-abc123/behindbot/conv-def456"


@pytest.fixture
def running_hub(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_hub_native_answer_healthy", lambda port: True)
    monkeypatch.setattr(cli, "_hub_profile_serving_port", lambda port: None)
    started = []
    monkeypatch.setattr(cli, "_hub_native_start", lambda **kw: started.append(kw) or 0)
    return started


def test_a_click_with_no_window_opens_one_on_the_conversation_without_restarting(
    running_hub, monkeypatch
):
    opened = []
    monkeypatch.setattr(
        cli,
        "_open_app_with_splash",
        lambda start, warm, port, profile: opened.append((start(), warm, port, profile)) or 0,
    )
    assert cli.main(["--open", LINK]) == 0
    assert opened == [
        (
            (
                "http://127.0.0.1:8180/?project=proj-abc123&agent=behindbot&conversation=conv-def456",
                None,
            ),
            True,
            8180,
            "default",
        )
    ]
    assert running_hub == []  # the running Hub is not started again


def test_a_click_with_a_window_open_restores_it_and_sends_it_there(
    running_hub, monkeypatch, tmp_path
):
    marker = tmp_path / "window-8180-4242-1.open"
    marker.write_text("http://127.0.0.1:8180/", encoding="utf-8")
    monkeypatch.setattr(desktop_window, "find_app_window", lambda pid: 777)
    focused = []
    monkeypatch.setattr(
        desktop_window,
        "focus_window",
        lambda hwnd, owner_pid=None: focused.append((hwnd, owner_pid)),
    )
    monkeypatch.setattr(
        cli, "_open_app_with_splash", lambda *a, **k: (_ for _ in ()).throw(AssertionError("2nd"))
    )
    assert cli.main(["--open", LINK]) == 0
    assert focused == [(777, 4242)]
    assert cli._app_window_take_open(marker) == {
        "port": 8180,
        "project_id": "proj-abc123",
        "agent": "behindbot",
        "conversation_id": "conv-def456",
    }
    assert running_hub == []


def test_a_click_names_the_profile_serving_the_port(running_hub, monkeypatch):
    monkeypatch.setattr(cli, "_hub_profile_serving_port", lambda port: "d1108wn")
    seen = []
    monkeypatch.setattr(
        cli, "_open_app_with_splash", lambda start, warm, port, profile: seen.append(profile) or 0
    )
    assert cli.main(["--open", LINK]) == 0
    assert seen == ["d1108wn"]


def test_a_click_with_no_hub_running_starts_agentweave(running_hub, monkeypatch):
    monkeypatch.setattr(cli, "_hub_native_answer_healthy", lambda port: False)
    assert cli.main(["--open", LINK]) == 0
    assert running_hub == [
        {"port": 8180, "detach": True, "app": True, "cwd": None, "profile": "default"}
    ]


def test_a_link_that_is_not_ours_opens_nothing(running_hub, monkeypatch):
    monkeypatch.setattr(
        cli, "_open_app_with_splash", lambda *a, **k: (_ for _ in ()).throw(AssertionError("open"))
    )
    assert cli.main(["--open", "agentweave:open/notaport"]) == 1
    assert running_hub == []


def test_the_open_window_passes_a_click_to_its_page(tmp_path, monkeypatch):
    """The window's own watcher reads the request another process left and tells the page."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(cli, "_APP_WINDOW_POLL_SECONDS", 0.02)
    ran = []
    seen = threading.Event()

    def _evaluate(js):
        ran.append(js)
        seen.set()

    window = types.SimpleNamespace(evaluate_js=_evaluate, destroy=lambda: None)
    marker = cli._app_window_register("http://127.0.0.1:8180/", window)
    try:
        target = notifier.parse_open_link(LINK)
        assert cli._app_window_send_open(marker, target) is True
        assert seen.wait(timeout=5)
    finally:
        marker.unlink()
    assert "aw-app-open" in ran[0]
    detail = json.loads(re.search(r"detail: (\{.*?\}) \}", ran[0]).group(1))
    assert detail == {
        "project_id": "proj-abc123",
        "agent": "behindbot",
        "conversation_id": "conv-def456",
    }
    assert not cli._app_window_open_request(marker).exists()
