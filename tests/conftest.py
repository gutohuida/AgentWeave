"""Shared fixtures for the CLI test suite.

The one fixture here exists to stop the suite opening a real desktop window.

`agentweave.cli._open_app_window_native` does `import webview` inside the function body (never at
module load, per CLAUDE.md's stdlib-only stance on the CLI's own code) and then calls
`webview.start()`, which blocks until a human closes the window. Two call sites reach it:
`cmd_hub_start`'s already-running branch and `_hub_native_start`.

That was harmless for as long as pywebview was not installed -- the ImportError guard returned
False and every caller fell through to `_open_app_window`. On 2026-08-17 `pip install pywebview`
was run so the desktop app could be driven, and the CLI suite stopped terminating: at least
`test_hub_start_docker_already_running_opens_app` (which patches only the `_open_app_window`
fallback) and `test_first_start_opens_the_invocation_directory` hung forever on a real window.

So the suite's behaviour depended on whether an optional package happened to be installed in the
developer's environment, which is exactly the kind of hidden dependency that makes a green run
meaningless. This fixture removes it: by default `webview` is unimportable for every test in this
directory, so the native path deterministically reports "I can't run" and callers take the
fallback -- the same state CI runs in today, and the state the tests were written against.

Tests that need the *installed* path still get it, by injecting their own fake over the top
(`TestAppModeNativeWindow` in test_cli.py does this). `monkeypatch.setitem` in a test body runs
after this fixture and undoes in reverse, so an explicit fake always wins.
"""

from __future__ import annotations

import os
import sys

import pytest

# An agent's run carries its bound credential and the Hub's address, and an agent may run this
# suite inside its run. Handed to every test, they sent `POST /session/sync` to the Hub that
# started the run and failed ten transport tests (F493, measured 2026-10-05). Removed before any
# test runs; `hub/tests/conftest.py` holds the same list, and its
# `test_suite_carries_no_run_credentials.py` keeps the two in step.
RUN_ENVIRONMENT_NAMES = (
    "AW_RUN_TOKEN",
    "AW_RUN_ID",
    "AW_AGENT_IDENTITY",
    "AW_WORKSPACE_DIR",
    "AW_PERMISSION_POSTURE",
    "AW_DECISION_TIMEOUT",
    "AW_QUESTION_TIMEOUT",
    "AW_TURN_DEPTH",
    "HUB_URL",
    "HUB_API_KEY",
    "HUB_PROJECT_ID",
)
for _name in RUN_ENVIRONMENT_NAMES:
    os.environ.pop(_name, None)


@pytest.fixture(autouse=True)
def _webview_unimportable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import webview` raise ImportError for every CLI test.

    `sys.modules[name] = None` is the documented way to force that, regardless of whether the real
    package is installed. Without this, a test that reaches `_open_app_window_native` without
    patching it opens a real OS window and the suite never finishes.
    """
    monkeypatch.setitem(sys.modules, "webview", None)


@pytest.fixture(autouse=True)
def _nothing_listens_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the CLI's "is a Hub already on this port?" probe answer no, as on CI's runners.

    `_hub_port_accepts` opens a real socket to 127.0.0.1. On a developer machine the operator's
    own Hub holds :8000, so tests that only faked `/health` passed locally and failed on every CI
    runner, where nothing listens (agentweave-opens-on-the-thread, 2026-10-23). A test that
    simulates a running Hub says so by patching the probe over this, as it fakes `/health`.
    """
    monkeypatch.setattr("agentweave.cli._hub_port_accepts", lambda port, timeout=0.3: False)


@pytest.fixture(autouse=True)
def _no_app_window_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make "is an app window open on this Hub?" answer no, as on CI's runners.

    A launch against a running Hub first looks for its open window (`_focus_open_app_window`) by
    reading the window markers and then the real window list. Most tests leave `HUB_DIR` at the
    real `~/.agentweave/hub`, where the operator's own :8000 window has a marker, so without this a
    test on port 8000 would bring the operator's window to the front and skip what it tests. A test
    of that decision patches the window list over this.
    """
    monkeypatch.setattr("agentweave.desktop_window.find_app_window", lambda pid: None)
    monkeypatch.setattr("agentweave.desktop_window.pid_alive", lambda pid: True)


@pytest.fixture(autouse=True)
def _no_windows_notification_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite out of the operator's Windows: no toast, no Start-menu shortcut, no link.

    Opening an app window registers the `agentweave:` link (HKCU) and the Start-menu shortcut
    notifications are shown under, and the notifier shows toasts through PowerShell. A test of
    either patches over this.
    """
    monkeypatch.setattr("agentweave.cli._register_windows_notifications", lambda: None)
    monkeypatch.setattr("agentweave.notifier._run_powershell", lambda script, timeout: False)
    # Nor a window's listener on the operator stream, nor the watcher a close starts.
    monkeypatch.setattr("agentweave.cli._listen_for_notices_in_window", lambda port, marker: None)
    monkeypatch.setattr("agentweave.cli._start_notice_watcher", lambda port: False)
