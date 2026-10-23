"""Drive for two Tier 0 fixes (2026-10-23): the app opens dark by default, and the window remembers.

Launches the real CLI from this checkout (its src/ and hub/, so the Hub serves this checkout's UI
bundle) on a fresh scratch profile and port (never :8000), sound off. Captures the window once the
app is up, stops it, and checks the window's storage folder now holds the app's saved data for
that origin (private mode, the old default, writes nothing to disk). Then launches again and
captures again.

  py -3.11 scripts/drive/d1023_remembered.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from d1023_splash import capture_window, window_open  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "testbed" / "ui-judge" / "d1023-remembered"
STORAGE = pathlib.Path.home() / ".agentweave" / "hub" / "app-window"
PORT, PROFILE = "8162", "remember1"
failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def env():
    e = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "hub")]),
        "AGENTWEAVE_SOUND": "0",
    }
    e.pop("DATABASE_URL", None)
    return e


def origin_saved() -> bool:
    """Does the window's storage hold localStorage written by the app on our port?"""
    needles = (
        f"localhost:{PORT}".encode(),
        f"127.0.0.1:{PORT}".encode(),
    )  # the launch URL says localhost
    for path in STORAGE.rglob("*"):
        if path.is_file() and "Local Storage" in str(path):
            try:
                if any(n in path.read_bytes() for n in needles):
                    return True
            except OSError:
                pass
    return False


def launch(tag: str) -> None:
    cwd = ROOT / "testbed" / "remember-drive"
    cwd.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "agentweave", "--profile", PROFILE, "--port", PORT],
        cwd=cwd,
        env=env(),
    )
    started = time.monotonic()
    try:
        while time.monotonic() - started < 15 and not window_open(proc.pid):
            time.sleep(0.05)
        healthy = False
        while time.monotonic() - started < 90 and not healthy:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                    healthy = r.status == 200
            except Exception:
                time.sleep(0.3)
        check(f"{tag}: the Hub is up", healthy)
        time.sleep(8.0)
        shot = OUT / f"{tag}-app.png"
        check(
            f"{tag}: the window shows the app (captured)", capture_window(proc.pid, shot), str(shot)
        )
    finally:
        subprocess.run(
            [sys.executable, "-m", "agentweave", "stop", "--profile", PROFILE, "--port", PORT],
            cwd=cwd,
            env=env(),
            timeout=60,
        )
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    launch("first")
    time.sleep(1.5)
    check("the window's storage kept the app's saved data", origin_saved(), str(STORAGE))
    launch("second")
    print(f"\n{len(failures)} FAIL" if failures else "\nALL PASS")
    sys.exit(1 if failures else 0)
