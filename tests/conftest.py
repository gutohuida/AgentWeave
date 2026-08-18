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

import sys

import pytest


@pytest.fixture(autouse=True)
def _webview_unimportable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import webview` raise ImportError for every CLI test.

    `sys.modules[name] = None` is the documented way to force that, regardless of whether the real
    package is installed. Without this, a test that reaches `_open_app_window_native` without
    patching it opens a real OS window and the suite never finishes.
    """
    monkeypatch.setitem(sys.modules, "webview", None)
