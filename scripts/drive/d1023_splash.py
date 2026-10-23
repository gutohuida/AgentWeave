"""Acceptance for agentweave-opens-on-the-thread: the splash really plays, and the app follows it.

Part 1 (default) loads the packaged splash page in Chromium and checks its motion and its two
hooks: the shuttle pass draws (the thread's dash moves, the glint shows at 0.6 s), the name is up
by 2 s, `awSplashLeave()` during the wait answers a delay under one cycle plus the fade after which
the thread is fully drawn and the page fading, `awSplashFail()` says the failure, and under reduced
motion the thread is fully drawn at once.

Part 2 (`--real`) launches the real CLI on a scratch profile and port (never :8000), sound off,
captures the AgentWeave window it opened at ~0.9 s and again once the Hub answered, and stops it.

  py -3.11 scripts/drive/d1023_splash.py [--real]
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPLASH = ROOT / "src" / "agentweave" / "assets" / "splash.html"
OUT = ROOT / "testbed" / "ui-judge" / "d1023-splash"
failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


STATE = """() => { const cs = (id) => getComputedStyle(document.getElementById(id));
  const a = document.getElementById('a');
  return { a: cs('a').strokeDasharray + '|' + cs('a').strokeDashoffset, aOpacity: +cs('a').opacity,
    b: cs('b').strokeDasharray, glint: +cs('ga').opacity + +cs('gb').opacity,
    name: +cs('name').opacity, lenA: a.getTotalLength(), leaving: document.getElementById('main').classList.contains('leaving'),
    tag: document.getElementById('tag').textContent }; }"""


def fully_drawn(state) -> bool:
    shown = state["a"].split("|")[0].split(",")[0].replace("px", "").strip()
    return state["aOpacity"] == 1 and (shown == "none" or float(shown) >= state["lenA"] - 0.5)


def part_one():
    from playwright.sync_api import sync_playwright

    check("the splash page is packaged", SPLASH.is_file(), str(SPLASH))
    if not SPLASH.is_file():
        return
    OUT.mkdir(parents=True, exist_ok=True)
    page_file = pathlib.Path(tempfile.gettempdir()) / "aw-splash-drive.html"
    page_file.write_text(
        SPLASH.read_text(encoding="utf-8").replace("__AW_WARM__", "false"), encoding="utf-8"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(250)
        early = page.evaluate(STATE)
        page.wait_for_timeout(350)
        mid = page.evaluate(STATE)
        page.screenshot(path=str(OUT / "intro-0.6s.png"))
        check(
            "the thread draws during the intro",
            early["a"] != mid["a"],
            f"{early['a']} -> {mid['a']}",
        )
        check(
            "the glint runs at the thread's head at 0.6 s",
            mid["glint"] > 0.5,
            f"glint opacity {mid['glint']}",
        )
        page.wait_for_timeout(1500)
        named = page.evaluate(STATE)
        page.screenshot(path=str(OUT / "named-2.1s.png"))
        check("the name is up by 2 s", named["name"] > 0.95, f"name opacity {named['name']}")
        page.wait_for_timeout(1400)
        waiting = page.evaluate(STATE)
        page.wait_for_timeout(200)
        waiting2 = page.evaluate(STATE)
        check(
            "while the Hub starts, the thread keeps weaving",
            waiting["a"] + waiting["b"] != waiting2["a"] + waiting2["b"],
        )
        delay = page.evaluate("awSplashLeave()")
        check(
            "awSplashLeave answers less than a cycle plus the fade",
            250 <= delay <= 1600 + 250,
            f"{delay} ms",
        )
        page.wait_for_timeout(delay - 200)
        left = page.evaluate(STATE)
        check(
            "at the moment it leaves, the thread is fully drawn and the page fades",
            fully_drawn(left) and left["leaving"],
            str(left),
        )

        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        page.evaluate("awSplashFail('Hub failed to start within 60 seconds.')")
        failed = page.evaluate(STATE)
        page.screenshot(path=str(OUT / "failed.png"))
        check(
            "a failed start is said in words",
            "Hub failed to start" in failed["tag"] and "terminal" in failed["tag"],
            failed["tag"],
        )

        reduced = browser.new_page(viewport={"width": 800, "height": 600}, reduced_motion="reduce")
        reduced.goto(page_file.as_uri())
        reduced.wait_for_timeout(150)
        still = reduced.evaluate(STATE)
        check(
            "under reduced motion the thread is fully drawn at once",
            fully_drawn(still) and still["name"] == 1,
            str(still),
        )
        browser.close()


def window_open(pid: int) -> bool:
    """Is a visible top-level window of `pid` up? ctypes, so polling costs nothing (Windows only)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        rect = wintypes.RECT()
        if (
            owner.value == pid
            and user32.IsWindowVisible(hwnd)
            and user32.GetWindowRect(hwnd, ctypes.byref(rect))
        ):
            if rect.right - rect.left > 300:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(each, 0)
    return bool(found)


def capture_window(pid: int, path: pathlib.Path) -> bool:
    """Capture the top-level window owned by `pid` (never by title: the operator's app shares it)."""
    script = rf"""
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Text;
public class W {{
  public delegate bool P(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(P p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public struct R {{ public int L, T, Ri, B; }}
}}
'@
$found = [IntPtr]::Zero
[W]::EnumWindows({{ param($h, $l) $p = 0; [void][W]::GetWindowThreadProcessId($h, [ref]$p)
  if ($p -eq {pid} -and [W]::IsWindowVisible($h)) {{ $r = New-Object W+R; [void][W]::GetWindowRect($h, [ref]$r)
    if (($r.Ri - $r.L) -gt 300) {{ $script:found = $h; return $false }} }}; return $true }}, [IntPtr]::Zero) | Out-Null
if ($found -eq [IntPtr]::Zero) {{ exit 3 }}
[void][W]::SetForegroundWindow($found); Start-Sleep -Milliseconds 120
$r = New-Object W+R; [void][W]::GetWindowRect($found, [ref]$r)
$bmp = New-Object System.Drawing.Bitmap ($r.Ri - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
$bmp.Save('{path}'); exit 0
"""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30
    )
    return done.returncode == 0 and path.is_file()


def part_two():
    port, profile = "8161", "splash1"
    cwd = ROOT / "testbed" / "splash-drive"
    cwd.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTWEAVE_SOUND": "0"}
    env.pop("DATABASE_URL", None)
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "agentweave", "--profile", profile, "--port", port], cwd=cwd, env=env
    )
    try:
        shot, window_at = OUT / "real-splash.png", None
        while time.monotonic() - started < 15 and window_at is None:
            if window_open(proc.pid):
                window_at = time.monotonic() - started
            else:
                time.sleep(0.05)
        time.sleep(0.8)  # into the intro: the thread is drawing
        check(
            "the open window shows the splash (captured)", capture_window(proc.pid, shot), str(shot)
        )
        healthy_at = None
        while time.monotonic() - started < 90:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                    if r.status == 200:
                        healthy_at = time.monotonic() - started
                        break
            except Exception:
                time.sleep(0.3)
        check(
            "the Hub came up behind the splash",
            healthy_at is not None,
            f"healthy after {healthy_at and round(healthy_at, 1)} s",
        )
        check(
            "the window opened before the Hub answered, within 3 s of the command",
            window_at is not None
            and window_at < 3.0
            and (healthy_at is None or window_at < healthy_at),
            f"window at {window_at and round(window_at, 1)} s",
        )
        time.sleep(7.0)  # the minimum, the wait for a fully drawn thread, the fade, the app's load
        shot2 = OUT / "real-app.png"
        check("the window then shows the app", capture_window(proc.pid, shot2), str(shot2))
    finally:
        subprocess.run(
            [sys.executable, "-m", "agentweave", "stop", "--profile", profile, "--port", port],
            cwd=cwd,
            env=env,
            timeout=60,
        )
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    part_two() if "--real" in sys.argv else part_one()
    print(f"\n{len(failures)} FAIL" if failures else "\nALL PASS")
    sys.exit(1 if failures else 0)
