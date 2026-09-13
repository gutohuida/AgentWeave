"""F341: a console-less Hub must acquire a console with no window before any ConPTY spawn.

pywinpty's ConPTY backend begins every spawn with `AllocConsole()`, and on Windows 11 a console
allocated that way is handed to Windows Terminal — so a natively started Hub, which had no
console, opened a terminal window for every agent turn and left it open.

These tests run the real thing in a real console-less process (`DETACHED_PROCESS`, which is how
the Hub used to be started), so they are Windows-only. The call-order half — that `PtySession`
asks for the console before it spawns — is pinned on every platform in `test_pty_runner.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hub.subprocess_windows import IS_WINDOWS

pytestmark = pytest.mark.skipif(not IS_WINDOWS, reason="console allocation is Windows-only")

HUB_ROOT = Path(__file__).resolve().parent.parent

CHILD = r"""
import ctypes, json, sys
sys.path.insert(0, sys.argv[2])
from hub import subprocess_windows as sw
report = {"before": sw.has_console()}
sw.ensure_windowless_console()
report["after"] = sw.has_console()
hwnd = ctypes.WinDLL("kernel32").GetConsoleWindow()
report["window_visible"] = bool(hwnd) and bool(ctypes.WinDLL("user32").IsWindowVisible(hwnd))
sw.ensure_windowless_console()  # idempotent: must not replace or drop the console
report["after_second_call"] = sw.has_console()
try:
    import winpty
except ImportError:
    report["spawn_kept_console"] = None
else:
    proc = winpty.PtyProcess.spawn(["cmd.exe", "/c", "echo hi"])
    while proc.isalive():
        pass
    del proc
    # pywinpty frees a console on teardown only if it allocated one. Ours must survive.
    report["spawn_kept_console"] = sw.has_console()
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(report, fh)
"""


def _run_console_less(tmp_path: Path) -> dict:
    report = tmp_path / "report.json"
    # The base interpreter, not a venv's `python.exe`: a venv launcher re-execs the base one, and
    # a console-less launcher would give that child a fresh — visible — console of its own.
    python = getattr(sys, "_base_executable", None) or sys.executable
    proc = subprocess.run(
        [python, "-c", CHILD, str(report), str(HUB_ROOT)],
        creationflags=subprocess.DETACHED_PROCESS,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    )
    assert proc.returncode == 0 and report.exists(), "the console-less child did not report"
    return json.loads(report.read_text(encoding="utf-8"))


def test_a_console_less_process_gets_a_console_with_no_window(tmp_path):
    report = _run_console_less(tmp_path)
    # A guard on the guard: if the child already had a console, nothing below measures the fix.
    assert report["before"] is False
    assert report["after"] is True
    assert report["window_visible"] is False
    assert report["after_second_call"] is True


def test_a_conpty_spawn_does_not_take_the_console_away(tmp_path):
    report = _run_console_less(tmp_path)
    if report["spawn_kept_console"] is None:
        pytest.skip("pywinpty is not importable from the base interpreter")
    assert report["spawn_kept_console"] is True
