"""D-8, 2026-09-07 (day window, spec-loop round 3) — the clearing path AS IT EXISTS TODAY.

`2026-09-07-clearing-instructions-asks-first` proposes a confirmation before a save that would blank
a project's stored instructions. Rounds 1 and 2 both wrote that they drove nothing, and the whole
argument of the change is about what **one click** does — so this is round 3 paying that debt.

**This asserts the PRE-CHANGE behaviour, on purpose.** It is `tasks.md` 5.2, run before the fix
exists: *"the pre-change run must show one PUT and the row going to `''` on the first Save click. A
drive that has only ever seen the passing state has proved nothing."* Every check below passes
against today's bundle and is expected to **fail** once the change lands — that failure is the
instrument proving it can see the write whose absence the post-change harness will assert.

Six questions:

  A. baseline — does the editor show exactly what is stored, and is Save enabled?
  B. the destructive click — select all, delete, click Save. How many PUTs leave, is any confirmation
     shown, and what does the row hold afterwards? (One, none, `''` — today.)
  C. is the operator told anything that would let them undo it? Read the whole screen after the save.
  D. the near-miss `design.md` D1 exists for — a select-all-delete that leaves a single newline. Does
     it destroy the stored content exactly as an empty editor does? A predicate testing
     `content === ''` would not catch this one.
  E. the stored side of the same trim — content that is only whitespace, blanked. Nothing is lost
     here, so the confirmation must NOT fire post-change; today nothing fires either way.
  F. the ordinary save, which must stay uninterrupted before and after the change.

Run:  py -3.11 scripts/drive/t_d8_clearing_instructions_prechange.py

Creates one fixture project and deletes it. Refuses :8000. Never touches :8010. No agent turn is
triggered, so nothing binds a model and nothing spends tokens.
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
UI = os.environ.get("AW_UI", HUB)
KEY = os.environ.get("AW_KEY", "")
if HUB.endswith(":8000") or UI.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)
if HUB.endswith(":8010") or UI.endswith(":8010"):
    print("REFUSING TO RUN: 8010 is the trial Hub; this drive wants a throwaway.")
    sys.exit(1)
if not KEY:
    print("set AW_KEY (GET /api/v1/setup/token on the throwaway Hub)")
    sys.exit(2)

FIXTURE = os.path.join(os.path.expanduser("~"), "Documents", "drive-0907-d8")
SHOTS = os.path.join(tempfile.gettempdir(), "d8-shots")
os.makedirs(SHOTS, exist_ok=True)

# Deliberately long: the dialog the change proposes says "how much content would be discarded", and
# a baseline of four lines makes a bad line count invisible.
RULES = "PROJECT RULES\n\n" + "".join(f"- Rule number {i}: do the careful thing.\n" for i in range(1, 41))

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


def stored(pid):
    code, body = call("GET", f"/projects/{pid}/project/instructions")
    return body.get("content") if code == 200 and isinstance(body, dict) else f"<{code}>"


def seed_script(pid):
    return (
        "sessionStorage.setItem('agentweave-session', "
        + json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))
        + ");\nlocalStorage.setItem('agentweave-selected-project', "
        + json.dumps(pid)
        + ");\n"
    )


def instructions_url(pid):
    return f"{UI}/?project={pid}&tab=environment&section=instructions"


def observe(page, label):
    """What an operator sees. No predicate here reads the component's source."""
    ta = page.locator("textarea[aria-label='Project instructions']")
    save = page.get_by_role("button", name="Save", exact=True)
    dialogs = page.get_by_role("dialog")
    alerts = page.locator("[role='alert']")
    status = page.locator("[role='status']")
    state = {
        "textarea": ta.count() > 0,
        "value_len": len(ta.first.input_value()) if ta.count() else None,
        "value_repr": repr(ta.first.input_value()[:40]) if ta.count() else None,
        "save_visible": save.count() > 0,
        "save_disabled": save.first.is_disabled() if save.count() else None,
        "dialogs": dialogs.count(),
        "alerts": [alerts.nth(i).inner_text().strip()[:120] for i in range(alerts.count())],
        "status": [status.nth(i).inner_text().strip()[:60] for i in range(status.count())],
    }
    page.screenshot(path=os.path.join(SHOTS, f"d8-{label}.png"))
    print(f"    [{label}] {json.dumps(state, ensure_ascii=False)[:420]}")
    return state


def open_page(browser, pid, wire):
    """A page whose every instructions PUT is counted on the wire, body and all."""
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.add_init_script(seed_script(pid))

    def handler(route, request):
        if "/project/instructions" in request.url and request.method == "PUT":
            wire["put"] += 1
            try:
                wire["bodies"].append(request.post_data)
            except Exception:
                wire["bodies"].append("<unreadable>")
        route.continue_()

    page.route("**/project/instructions", handler)
    page.goto(instructions_url(pid), wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    return page


def clear_and_save(page, replacement=None):
    """The operator's actual gesture: click into the editor, select all, delete, Save.

    `replacement` types something after the delete — a single newline is the near-miss D1 exists for.
    """
    ta = page.locator("textarea[aria-label='Project instructions']").first
    ta.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    if replacement:
        page.keyboard.type(replacement) if replacement != "\n" else page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    page.get_by_role("button", name="Save", exact=True).first.click()
    return ack_window(page)


def ack_window(page):
    """Watch the success acknowledgement appear and expire.

    Measured by this drive, and it is an instrument fact the post-change harness needs: the "Saved"
    badge is cleared by a 2000 ms `setTimeout`, so a harness that observes three seconds after the
    click sees an empty screen and reports the acknowledgement missing. Two checks in the first run
    of this file failed exactly that way, against a page that was behaving correctly.
    """
    page.wait_for_timeout(700)
    early = [
        page.locator("[role='status']").nth(i).inner_text().strip()
        for i in range(page.locator("[role='status']").count())
    ]
    page.wait_for_timeout(2600)
    late = [
        page.locator("[role='status']").nth(i).inner_text().strip()
        for i in range(page.locator("[role='status']").count())
    ]
    print(f"    ack at 0.7s {early} / at 3.3s {late}")
    return early, late


def main():
    code, proj = call(
        "POST", "/projects/open", {"path": FIXTURE.replace("\\", "/"), "name": "d8-clearing"}
    )
    if code != 200:
        print(f"could not open the fixture project [{code}] {proj}")
        return 2
    pid = proj["id"]
    print(f"fixture project: {pid}")
    if pid in ("proj-5e960453", "proj-18e5d4e0"):
        print("REFUSING: that is a protected project id.")
        return 2

    try:
        drive(pid)
    finally:
        dcode, _ = call("DELETE", f"/projects/{pid}")
        print(f"\ncleanup: DELETE {pid} [{dcode}]")
        check(dcode in (200, 204), f"fixture {pid} is deleted")
        ccode, rest = call("GET", "/projects")
        listed = rest if isinstance(rest, list) else rest.get("projects", []) if isinstance(rest, dict) else []
        check(
            ccode == 200 and not any(p.get("id") == pid for p in listed),
            "and it is not listed any more",
        )

    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    print(f"\nscreenshots: {SHOTS}")
    return 1 if FAIL else 0


def drive(pid):
    code, _ = call("PUT", f"/projects/{pid}/project/instructions", {"content": RULES})
    check(code == 200, f"the fixture's instructions are stored [{code}]")
    check(stored(pid) == RULES, f"and read back byte-identical ({len(RULES)} chars)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # ------------------------------------------------------------------ A, baseline
        print("\nA — baseline: the stored instructions are on screen")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        s = observe(page, "01-baseline")
        check(s["textarea"] and s["value_len"] == len(RULES), "the editor holds exactly what is stored")
        check(s["save_disabled"] is False, "Save is enabled")
        check(s["dialogs"] == 0, "no dialog is on screen before anything is done")

        # ------------------------------------------------------------------ B, the destructive click
        print("\nB — select all, delete, Save. One click, and what does it cost?")
        early, late = clear_and_save(page)
        s = observe(page, "02-after-clear-save")
        check(wire["put"] == 1, f"exactly one PUT left the page ({wire['put']})")
        body = json.loads(wire["bodies"][0]) if wire["bodies"] and wire["bodies"][0] else {}
        check(body.get("content") == "", f"and it carried the empty string ({body!r:.80})")
        check(
            s["dialogs"] == 0,
            f"NOTHING asked the operator to confirm — {s['dialogs']} dialog(s) on screen",
        )
        after = stored(pid)
        check(after == "", f"the stored row is now empty ({after!r:.40})")
        check(
            any("saved" in t.lower() for t in early),
            f"and the screen reports it as an ordinary success {early}",
        )
        check(
            not any("saved" in t.lower() for t in late),
            f"an acknowledgement that expires after ~2s, so a slow observer misses it {late}",
        )

        # ------------------------------------------------------------------ C, is it recoverable?
        print("\nC — is the operator offered any way back?")
        text = page.locator("body").inner_text().lower()
        undo_words = [w for w in ("undo", "restore", "revert", "recover", "previous version", "history") if w in text]
        check(
            not undo_words,
            f"nothing on the screen offers undo, restore or history {undo_words}",
        )
        code2, hist = call("GET", f"/projects/{pid}/project/instructions/history")
        check(
            code2 == 404,
            f"and the Hub serves no instructions history at all [{code2}]",
        )
        page.close()

        # ------------------------------------------------------------------ D, the newline near-miss
        print("\nD — the same gesture leaving one newline behind (design.md D1's near-miss)")
        call("PUT", f"/projects/{pid}/project/instructions", {"content": RULES})
        check(stored(pid) == RULES, "the fixture's instructions are restored")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_and_save(page, replacement="\n")
        s = observe(page, "03-newline")
        check(wire["put"] == 1, f"one PUT ({wire['put']})")
        body = json.loads(wire["bodies"][0]) if wire["bodies"] and wire["bodies"][0] else {}
        wrote = body.get("content")
        check(
            wrote is not None and wrote.strip() == "" and wrote != "",
            f"carrying whitespace that is not the empty string ({wrote!r})",
        )
        after = stored(pid)
        check(
            after.strip() == "" and after != RULES,
            f"and forty lines of rules are gone exactly as before ({after!r:.30})",
        )
        check(s["dialogs"] == 0, "no confirmation here either — the case `content === ''` would miss")
        page.close()

        # ------------------------------------------------------------------ E, the stored side
        print("\nE — blanking stored content that is itself only whitespace (nothing is lost)")
        call("PUT", f"/projects/{pid}/project/instructions", {"content": "   \n\n  "})
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_and_save(page)
        s = observe(page, "04-whitespace-stored")
        check(wire["put"] == 1, f"one PUT ({wire['put']})")
        check(stored(pid) == "", "the row is empty")
        check(
            s["dialogs"] == 0,
            "and no confirmation — which is what must STILL be true after the change",
        )
        page.close()

        # ------------------------------------------------------------------ F, the ordinary save
        print("\nF — an ordinary save, which the change must leave alone")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        ta = page.locator("textarea[aria-label='Project instructions']").first
        ta.click()
        page.keyboard.press("Control+A")
        page.keyboard.type("ONE REAL RULE\n")
        page.get_by_role("button", name="Save", exact=True).first.click()
        page.wait_for_timeout(2500)
        s = observe(page, "05-ordinary")
        check(wire["put"] == 1, f"one PUT ({wire['put']})")
        check(s["dialogs"] == 0, "no confirmation, before or after the change")
        check(stored(pid).startswith("ONE REAL RULE"), f"and it landed ({stored(pid)!r:.40})")
        check(
            any("saved" in t.lower() for t in early),
            f"the success acknowledgement is the same one B showed {early}",
        )
        page.close()
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
