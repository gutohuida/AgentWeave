"""Task 3.2 of `a-dialog-takes-the-keyboard-when-it-opens`: drive the four D5-shape dialogs
(`CharterForm`, `RunnerForm`, `JobForm`, `SetupModal`) with the keyboard alone, from each one's own
trigger, and record `document.activeElement` on open and after Escape closes it.

Not committed as a durable regression harness like `t_d9_...`: this is the one-off evidence task
3.2 asks for, over a throwaway Hub. Refuses :8000 and :8010 the same way its sibling does.

Run:  AW_HUB=... AW_KEY=... py -3.11 scripts/drive/t_d10_dialog_focus_sweep.py
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8012")
KEY = os.environ.get("AW_KEY", "")
if HUB.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)
if HUB.endswith(":8010"):
    print("REFUSING TO RUN: 8010 is the trial Hub; this drive wants a throwaway.")
    sys.exit(1)
if not KEY:
    print("set AW_KEY (GET /api/v1/setup/token on the throwaway Hub)")
    sys.exit(2)

PROTECTED = {"proj-d85a82bf4216"}

FIXTURE = os.path.join(tempfile.gettempdir(), "aw-d10-drive", "fixture")

PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def call(method, path, body=None):
    url = HUB + "/api/v1" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
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


def seed_script(pid):
    return (
        "sessionStorage.setItem('agentweave-session', "
        + json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))
        + ");\nlocalStorage.setItem('agentweave-selected-project', "
        + json.dumps(pid)
        + ");\n"
    )


FOCUS_PROBE = """() => {
  const a = document.activeElement
  // The D5-shape dialogs (CharterForm, RunnerForm, JobForm, SetupModal) put role="dialog"
  // directly on panelRef itself -- unlike ClearInstructionsDialog, which wraps panelRef in a
  // separate, unmarked scrim div. So the element role='dialog' resolves to IS the panel here;
  // there is no extra firstElementChild indirection to apply.
  const panel = document.querySelector("[role='dialog'], [role='alertdialog']")
  return {
    tag: a ? a.tagName : null,
    text: a ? (a.textContent || '').trim().slice(0, 32) : null,
    aria: a ? (a.getAttribute('aria-label') || '') : '',
    inPanel: panel && a ? panel.contains(a) : false,
    dialogOpen: !!panel,
  }
}"""


def focus_now(page):
    return page.evaluate(FOCUS_PROBE)


def goto(page, pid, tab, section=None):
    url = f"{HUB}/?project={pid}&tab={tab}"
    if section:
        url += f"&section={section}"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)


def drive_dialog(page, label, open_trigger_text, after_open_check=None):
    """Tab to the named trigger button, activate it with the keyboard, record focus on open,
    then Escape and record focus after close."""
    print(f"\n{label} — keyboard open from its own trigger, then Escape")

    def is_trigger(state):
        # An icon-only button (SetupModal's "Hub setup") carries the name in aria-label, not
        # textContent -- check whichever one actually holds the trigger's accessible name.
        return state["text"] == open_trigger_text or state["aria"] == open_trigger_text

    trigger = page.get_by_role("button", name=open_trigger_text, exact=True).first
    trigger.focus()
    before = focus_now(page)
    check(
        is_trigger(before) and not before["dialogOpen"],
        f"keyboard focus is on the trigger before anything opens {before}",
    )
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    opened = focus_now(page)
    print(f"    on open: {opened}")
    check(opened["dialogOpen"], f"the dialog is open ({label})")
    check(
        opened["inPanel"] is True,
        f"focus moved straight into the panel on open ({label}) {opened}",
    )
    if after_open_check:
        after_open_check(opened)
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    closed = focus_now(page)
    print(f"    after Escape: {closed}")
    check(not closed["dialogOpen"], f"Escape closed the dialog ({label})")
    check(
        is_trigger(closed),
        f"focus returned to the trigger that opened it ({label}) {closed}",
    )


def main():
    os.makedirs(FIXTURE, exist_ok=True)
    code, proj = call(
        "POST", "/projects/open", {"path": FIXTURE.replace("\\", "/"), "name": "d10-dialogs"}
    )
    if code != 200:
        print(f"could not open the fixture project [{code}] {proj}")
        return 2
    pid = proj["id"]
    print(f"fixture project: {pid}")
    if pid in PROTECTED:
        print("REFUSING: that is a protected project id.")
        return 2

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.add_init_script(seed_script(pid))

            goto(page, pid, "environment", "charters")
            drive_dialog(page, "CharterForm (New Charter)", "New Charter")

            goto(page, pid, "environment", "runners")
            drive_dialog(page, "RunnerForm (New Runner)", "New Runner")

            goto(page, pid, "jobs")
            drive_dialog(page, "JobForm (New Job)", "New Job")

            goto(page, pid, "overview") if False else goto(page, pid, "jobs")
            # SetupModal's trigger is the "Hub setup" button in the project header, not page-local.
            drive_dialog(page, "SetupModal (Hub setup)", "Hub setup")

            browser.close()
    finally:
        dcode, _ = call("DELETE", f"/projects/{pid}")
        print(f"\ncleanup: DELETE {pid} [{dcode}]")
        check(dcode in (200, 204), f"fixture {pid} is deleted")

    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
