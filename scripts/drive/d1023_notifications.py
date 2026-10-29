"""Acceptance for agentweave-calls-you-with-its-own-sound (trial spdoc-3e64f37b5229).

Part 1 (default) opens the app through Vite on the trial Hub, on the AgentWeave project, and asks
real questions through the trial Hub's questions route in another project (aw-drive-f556), so the
event crosses projects exactly as the Hub broadcasts it. It checks:
  - in front: a toast naming the asking project appears, and the brand synth plays (oscillators
    counted by an init script);
  - behind (document.hasFocus() answering false): the title reads '(1) AgentWeave', and clears
    when the window is focused again;
  - after the sound switch in App settings (the rail's Settings control) is turned off: the toast still comes, no
    oscillator starts.
Each question is declined afterwards.

  AW_DEV_HUB=http://127.0.0.1:8010 npx vite --port 5193      (from hub/ui)
  py -3.11 scripts/drive/d1023_notifications.py [ui-url]

Part 2 (`--real`) launches the real CLI app on a scratch profile and port (never :8000), with
WebView2's remote debugging on, minimises the window without ever clicking it, asks a question in
that Hub, and checks the native window's title becomes '(1) AgentWeave' (EnumWindows by PID) and
that a page AudioContext made without a user gesture is running. It runs under its own home folder
(see part_two). It serves the committed bundle,
so it fails until the bundle is rebuilt. The notification sound plays aloud once.

  py -3.11 scripts/drive/d1023_notifications.py --real
"""

import ctypes
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def call(hub, key, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{hub}/api/v1{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def ask(hub, key, project, n):
    code, q = call(hub, key, "POST", f"/projects/{project}/questions", {
        "from_agent": "NotifyDrive",
        "question": f"Drive question {n}: does the call come through?",
        "header": "Drive",
        "options": [{"label": "Yes", "description": "It did"}, {"label": "No", "description": "It did not"}],
        "multi_select": False,
    })
    if code != 201:
        raise SystemExit(f"asking failed: {code} {q}")
    return q["id"]


def decline(hub, key, project, qid):
    call(hub, key, "POST", f"/projects/{project}/questions/{qid}/decline", {"reason": "drive cleanup"})


COUNT_SYNTH = """
  window.__awOsc = 0; window.__awFront = true;
  const make = AudioContext.prototype.createOscillator;
  AudioContext.prototype.createOscillator = function () { window.__awOsc += 1; return make.call(this); };
  Document.prototype.hasFocus = function () { return window.__awFront; };
"""


def part_one(ui):
    from uiharness import Judge

    trial = "http://127.0.0.1:8010"
    key = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
    viewing, asking, asking_name = "proj-d85a82bf4216", "proj-0223c963f214", "aw-drive-f556"
    asked = []
    with Judge("d1023-notifications", hub=ui, key=key) as j:
        page = j.page(viewing, mode="dark")
        page.context.add_init_script(COUNT_SYNTH)
        page.reload(wait_until="domcontentloaded")
        page.get_by_test_id("project-tab-overview").first.wait_for(timeout=30000)
        page.wait_for_timeout(2500)  # the stream connects

        asked.append(ask(trial, key, asking, 1))
        toast = page.locator(".aw-toast", has_text=asking_name)
        try:
            toast.first.wait_for(timeout=8000)
            shown = True
        except Exception:
            shown = False
        check("in front: a toast names the asking project", shown)
        page.wait_for_timeout(1800)
        osc = page.evaluate("window.__awOsc")
        check("in front: the brand synth plays", osc > 0, f"{osc} oscillators")
        if shown:
            j.shot(page, "front-toast")

        page.wait_for_timeout(4500)  # past the burst window
        page.evaluate("window.__awFront = false")
        before = page.evaluate("window.__awOsc")
        asked.append(ask(trial, key, asking, 2))
        page.wait_for_timeout(2500)
        title = page.title()
        check("behind: the title counts the call", title.startswith("(1) "), repr(title))
        check("behind: the sound plays", page.evaluate("window.__awOsc") > before)
        page.evaluate("window.__awFront = true; window.dispatchEvent(new Event('focus'))")
        page.wait_for_timeout(200)
        title = page.title()
        check("focus clears the count", not title.startswith("("), repr(title))

        page.goto(f"{ui}/?project={viewing}&appSettings=notifications", wait_until="domcontentloaded")
        switch = page.get_by_test_id("notify-sound")
        switch.wait_for(timeout=20000)
        j.shot(page, "settings", locator=page.locator("section[aria-label='Sound and notifications']"))
        if switch.get_attribute("aria-checked") == "true":
            switch.click()
        check("the sound switch turns off", switch.get_attribute("aria-checked") == "false")
        page.wait_for_timeout(2500)
        before = page.evaluate("window.__awOsc")
        asked.append(ask(trial, key, asking, 3))
        try:
            page.locator(".aw-toast", has_text=asking_name).first.wait_for(timeout=8000)
            muted_toast = True
        except Exception:
            muted_toast = False
        page.wait_for_timeout(1800)
        check("muted: the toast still comes", muted_toast)
        check("muted: no oscillator starts", page.evaluate("window.__awOsc") == before)
        stored = page.evaluate("localStorage.getItem('agentweave-notify')")
        check("muted: the choice is stored", stored is not None and '"sound":false' in stored, str(stored))
        page.context.close()
    for qid in asked:
        decline(trial, key, asking, qid)
    for e in j.errors:
        print("  " + e[:200])


def windows_of(pid):
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        rect = wintypes.RECT()
        if owner.value == pid and user32.IsWindowVisible(hwnd) and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            if rect.right - rect.left > 100 or user32.IsIconic(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(each, 0)
    return found


def part_two():
    from playwright.sync_api import sync_playwright

    port, profile, cdp = "8163", "notify1", "9343"
    cwd = ROOT / "testbed" / "notify-drive"
    cwd.mkdir(parents=True, exist_ok=True)
    # Its own home: app windows share one WebView2 browser per storage folder
    # (~/.agentweave/hub/app-window), so with the operator's app open a second window joins that
    # browser and its arguments (the autoplay flag, remote debugging) never apply.
    home = cwd / "home"
    home.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "USERPROFILE": str(home),
        "HOME": str(home),
        "PYTHONPATH": str(ROOT / "src"),
        "AGENTWEAVE_SOUND": "0",
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={cdp}",
    }
    env.pop("DATABASE_URL", None)
    hub = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "agentweave", "--profile", profile, "--port", port], cwd=cwd, env=env)
    try:
        started = time.monotonic()
        while time.monotonic() - started < 90:
            try:
                with urllib.request.urlopen(f"{hub}/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.3)
        time.sleep(9.0)  # the splash's minimum, its fade, the app's load and its stream
        wins = windows_of(proc.pid)
        check("the app window is up", bool(wins), str([t for _, t in wins]))
        if not wins:
            return
        ctypes.windll.user32.ShowWindow(wins[0][0], 6)  # SW_MINIMIZE: behind, never clicked
        time.sleep(1.0)
        _, token = call(hub, None, "GET", "/setup/token")
        key = token["api_key"]
        _, projects = call(hub, key, "GET", "/projects")
        project = next((p["id"] for p in projects if p.get("working_directory") and
                        pathlib.Path(p["working_directory"]).resolve() == cwd.resolve()), None)
        if project is None:
            code, made = call(hub, key, "POST", "/projects", {"path": str(cwd), "name": "notify-drive"})
            project = made["id"] if isinstance(made, dict) else None
        check("a project to ask in", project is not None, str(project))
        qid = ask(hub, key, project, 1)
        time.sleep(3.0)
        titles = [t for _, t in windows_of(proc.pid)]
        check("behind: the native title counts the call", any(t.startswith("(1) AgentWeave") for t in titles), str(titles))
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp}")
            pages = [p for c in browser.contexts for p in c.pages if f":{port}" in p.url]
            check("the app page is reachable over CDP", bool(pages), str([p.url for c in browser.contexts for p in c.pages]))
            if pages:
                session = pages[0].context.new_cdp_session(pages[0])
                res = session.send("Runtime.evaluate", {
                    "expression": "new AudioContext().state", "userGesture": False, "returnByValue": True})
                state = res.get("result", {}).get("value")
                check("a page AudioContext runs without a click", state == "running", str(state))
                focus = session.send("Runtime.evaluate", {"expression": "document.hasFocus()", "returnByValue": True})
                print("  document.hasFocus() =", focus.get("result", {}).get("value"))
            browser.close()
        # Back to the front. Windows' foreground lock may refuse a drive this, so it is reported,
        # not judged (DEAD-ENDS 2026-10-23).
        ctypes.windll.user32.ShowWindow(wins[0][0], 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(wins[0][0])
        time.sleep(1.5)
        print("  after restoring:", [t for _, t in windows_of(proc.pid)],
              "foreground ours:", ctypes.windll.user32.GetForegroundWindow() == wins[0][0])
        decline(hub, key, project, qid)
    finally:
        subprocess.run([sys.executable, "-m", "agentweave", "stop", "--profile", profile, "--port", port],
                       cwd=cwd, env=env, timeout=60)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    if "--real" in sys.argv:
        part_two()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        part_one(args[0] if args else "http://localhost:5193")
    print("ALL PASS" if not failures else f"{len(failures)} FAIL: {failures}")
    sys.exit(1 if failures else 0)
