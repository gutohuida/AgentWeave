"""D-4 task 4.4, 2026-09-06 (night, n6-retry) — the Retry control, driven with a real Hub.

The half no unit test reaches. `t_d4_instructions_failed_load.py` makes the read fail by
intercepting the route in the browser, which is enough to assert what the page renders but says
nothing about whether pressing **Retry** actually recovers against a Hub that really went away and
really came back. This drives that: one uvicorn started, stopped, and started again on the same
database, with a real browser sitting on the page across the whole thing.

The sequence, exactly as an operator would live it:

  1. The Hub is up. Open the app on the Environment tab's *Diagnostics* section, so the SPA is fully
     loaded but the instructions query has never run and nothing is cached for it.
  2. **Stop the Hub.** (The SPA is served *by* the Hub, so it must already be in the browser —
     an operator who reloads while it is down has no app at all, which is not this scenario.)
  3. Click **Instructions** in the sidebar. The GET fails against a socket that refuses.
     Assert: no editor, Save absent-or-inert, the failure stated, a Retry control present.
  4. **Start the Hub again** on the same database.
  5. Press **Retry**. Assert the textarea appears holding exactly what was stored.

Run:  py -3.11 scripts/drive/t_d4_retry_by_hand.py

Owns the Hub's whole lifecycle — do not have one already listening on the port. Creates one fixture
project and deletes it. Refuses :8000. No agent turn is triggered, so nothing binds a model.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

PORT = int(os.environ.get("AW_PORT", "8011"))
if PORT == 8000:
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)
HUB = f"http://127.0.0.1:{PORT}"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUB_DIR = os.path.join(REPO, "hub")
DB = os.environ.get(
    "AW_DB", os.path.join(tempfile.gettempdir(), "aw0906n5", "retry.db").replace("\\", "/")
)
FIXTURE = os.path.join(os.path.expanduser("~"), "Documents", "drive-0906-retry")
SHOTS = os.path.join(tempfile.gettempdir(), "d4-retry-shots")
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(os.path.dirname(DB), exist_ok=True)
os.makedirs(FIXTURE, exist_ok=True)

STORED = "RETRY FIXTURE RULES\n\n- The stored text must come back verbatim.\n"

PASS, FAIL = [], []
KEY = None


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def call(method, path, body=None):
    url = HUB + "/api/v1" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if KEY:
        req.add_header("Authorization", "Bearer " + KEY)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def port_open():
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start_hub():
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{DB}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=HUB_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(120):
        try:
            with urllib.request.urlopen(HUB + "/health", timeout=2) as r:
                if r.status == 200:
                    print(f"    hub up on {PORT} (pid {proc.pid})")
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit(f"hub never came up on {PORT}")


def stop_hub(proc):
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    for _ in range(40):
        if not port_open():
            print(f"    hub down, {PORT} refuses")
            return True
        time.sleep(0.5)
    return False


def observe(page, label):
    ta = page.locator("textarea[aria-label='Project instructions']")
    save = page.get_by_role("button", name="Save", exact=True)
    alerts = page.locator("[role='alert']")
    state = {
        "skeleton": page.locator("[aria-label='Loading instructions']").count() > 0,
        "textarea": ta.count() > 0,
        "value": ta.first.input_value() if ta.count() else None,
        "save_visible": save.count() > 0,
        "save_disabled": save.first.is_disabled() if save.count() else None,
        "retry": page.get_by_role("button", name="Retry", exact=True).count(),
        "alerts": [alerts.nth(i).inner_text().strip() for i in range(alerts.count())],
    }
    page.screenshot(path=os.path.join(SHOTS, f"retry-{label}.png"))
    print(f"    [{label}] {json.dumps(state, ensure_ascii=False)[:400]}")
    return state


def seed_script(pid):
    return (
        "sessionStorage.setItem('agentweave-session', "
        + json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))
        + ");\nlocalStorage.setItem('agentweave-selected-project', "
        + json.dumps(pid)
        + ");\n"
    )


def main():
    global KEY
    if port_open():
        print(f"REFUSING TO RUN: something is already listening on {PORT}. This drive owns the Hub.")
        return 2

    print(f"starting the Hub — db {DB}")
    proc = start_hub()
    with urllib.request.urlopen(HUB + "/api/v1/setup/token", timeout=10) as r:
        KEY = json.loads(r.read().decode())["api_key"]

    code, p = call("POST", "/projects/open", {"path": FIXTURE.replace("\\", "/"), "name": "d4-retry"})
    if code != 200:
        stop_hub(proc)
        print(f"could not open the fixture [{code}] {p}")
        return 2
    pid = p["id"]
    print(f"fixture: {pid}")

    code, _ = call("PUT", f"/projects/{pid}/project/instructions", {"content": STORED})
    check(code == 200, f"the fixture's instructions are stored [{code}]")

    try:
        proc = drive(proc, pid)
    finally:
        if not port_open():
            proc = start_hub()  # come back up so the fixture can be deleted through the API
        dcode, _ = call("DELETE", f"/projects/{pid}")
        check(dcode in (200, 204), f"fixture {pid} is deleted [{dcode}]")
        stop_hub(proc)

    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    print(f"screenshots: {SHOTS}")
    return 1 if FAIL else 0


def drive(proc, pid):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid))

        # 1 — the app is open, but never on the instructions section, so nothing is cached for it.
        print("\n1 — the app is loaded on another section while the Hub is up")
        page.goto(
            f"{HUB}/?project={pid}&tab=environment&section=diagnostics",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(5000)
        nav = page.get_by_role("button", name="Instructions", exact=True)
        check(nav.count() > 0, f"the Instructions destination is reachable ({nav.count()} control)")
        s = observe(page, "01-loaded-elsewhere")
        check(not s["textarea"], "and the instructions editor has not been visited yet")

        # 2 — the Hub really goes away. Not an intercepted route: the socket refuses.
        print("\n2 — the Hub is stopped")
        check(stop_hub(proc), f"the Hub is down and {PORT} refuses connections")

        # 3 — the operator navigates to Instructions with the Hub down.
        print("\n3 — the operator clicks Instructions with the Hub down")
        nav.first.click()
        page.wait_for_timeout(8000)
        s = observe(page, "02-hub-down")
        check(not s["textarea"], "no editor is offered over instructions that were never read")
        check(
            (not s["save_visible"]) or s["save_disabled"] is True,
            f"Save is absent-or-inert (visible={s['save_visible']}, disabled={s['save_disabled']})",
        )
        check(
            any("could not be loaded" in a.lower() for a in s["alerts"]),
            "the failure is stated to the operator in a role=alert",
        )
        check(s["retry"] > 0, f"and a Retry control is on screen ({s['retry']})")

        # 4 — the Hub comes back on the same database.
        print("\n4 — the Hub is started again on the same database")
        proc = start_hub()
        check(port_open(), "the Hub is listening again")
        # Nothing was clicked in between: the page is still showing the failure it showed above.
        s = observe(page, "03-hub-back-before-retry")
        check(
            not s["textarea"] and s["retry"] > 0,
            "the page has NOT healed on its own — it still shows the failure and its Retry",
        )

        # 5 — the operator presses Retry.
        print("\n5 — the operator presses Retry")
        page.get_by_role("button", name="Retry", exact=True).first.click()
        page.wait_for_timeout(6000)
        s = observe(page, "04-after-retry")
        check(s["textarea"], "the editor appears")
        check(s["value"] == STORED, f"holding exactly what was stored ({s['value']!r})")
        check(not s["alerts"], f"and the failure is gone ({s['alerts']!r:.120})")
        check(s["save_disabled"] is False, "with Save enabled again, because the read succeeded")

        page.close()
        browser.close()
    return proc


if __name__ == "__main__":
    sys.exit(main())
