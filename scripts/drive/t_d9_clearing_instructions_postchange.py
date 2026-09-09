"""D-9, 2026-09-10 (night window) — the clearing path AFTER the fix. This closes
`2026-09-07-clearing-instructions-asks-first`.

`tasks.md` 5.1: *"A drive harness under `scripts/drive/`, against a real browser and a real Hub.
The decisive measurements, in this order: (a) with real stored text on screen, select all, delete,
click Save — assert zero PUTs on the wire while the dialog is open, then read the row back over the
API and assert it is byte-identical; (b) Cancel, read back again, still byte-identical; (c) Confirm,
and only now does the row become `''`. Read the wire, not the DOM's `disabled` attributes."*

**The sibling of `t_d8_clearing_instructions_prechange.py`, and deliberately its mirror.** That file
is task 5.2 — the same gestures against bundle `eb1d1d7`, where they showed one PUT, no dialog and
an emptied row. It is the instrument proof: this harness's shape is already known to be able to
*see* the write whose absence the legs below assert. Legs G1-G4 are D-8's legs D, E and F re-run
post-change, because the three cases the change must **not** interrupt are worth as much as the one
it must.

**Why a browser and not a transcription.** A UI change is driven against the served bundle or it is
not driven. `F274` survived 29/29 checks in two phases because those checks re-implemented the
component in another language instead of loading it; every predicate here reads the page an operator
would see, and leg 0 refuses to trust the run unless the asset the Hub is actually serving contains
the dialog's own words.

Eight legs:

  0. instrument — is the bundle on the wire the post-change one at all?
  A. baseline — the stored instructions are on screen and Save is live.
  B. 5.1(a) — select all, delete, Save. A dialog, ZERO PUTs while it is open, row untouched.
  C. 5.1(b) — Cancel. Still zero PUTs, still byte-identical, and the editor keeps what was typed.
  D. 5.1(c) — Confirm. Now, and only now, one PUT and an empty row.
  E. 5.4 — the keyboard: Tab inside the panel, Escape cancels, focus returns to Save. That is
     `useDialogFocus`'s contract, it is unprovable in jsdom, and section 4 leaves it owed here.
  F. the singular branch — one stored line reads "1 line", not "1 lines".
  G. the three saves that must NOT be interrupted, plus the near-miss that must be.

Run:  py -3.11 scripts/drive/t_d9_clearing_instructions_postchange.py

Creates one fixture project and deletes it. Refuses :8000 (the operator's real usage) and :8010 (the
trial Hub). No agent turn is triggered, so nothing binds a model and nothing spends tokens.
"""

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8012")
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

# This repo's own registered project. Named as the class it belongs to and not only as a literal:
# the 2026-09-07 clean slate invalidated the two ids task 5.3 originally forbade.
PROTECTED = {"proj-d85a82bf4216"}

FIXTURE = os.path.join(tempfile.gettempdir(), "aw-d9-drive", "fixture")
SHOTS = os.path.join(tempfile.gettempdir(), "d9-shots")
os.makedirs(SHOTS, exist_ok=True)

# Long on purpose, exactly as D-8's baseline is: the dialog states how much would be discarded, and
# a four-line baseline would make a wrong line count invisible.
RULES = "PROJECT RULES\n\n" + "".join(
    f"- Rule number {i}: do the careful thing.\n" for i in range(1, 41)
)
# Hardcoded rather than computed, so this is not a transcription of the component's own expression:
# one title line, one blank line, forty rules — and the trailing newline is not a forty-third line.
EXPECTED_LINES = 42

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


def put_stored(pid, text):
    code, _ = call("PUT", f"/projects/{pid}/project/instructions", {"content": text})
    return code


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


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


def observe(page, label):
    """What an operator sees. No predicate here reads the component's source."""
    ta = page.locator("textarea[aria-label='Project instructions']")
    save = page.get_by_role("button", name="Save", exact=True)
    dialogs = page.get_by_role("dialog")
    state = {
        "textarea": ta.count() > 0,
        "value_len": len(ta.first.input_value()) if ta.count() else None,
        "save_visible": save.count() > 0,
        "save_disabled": save.first.is_disabled() if save.count() else None,
        "dialogs": dialogs.count(),
        "dialog_text": dialogs.first.inner_text().strip()[:300] if dialogs.count() else None,
        "status": [
            page.locator("[role='status']").nth(i).inner_text().strip()[:60]
            for i in range(page.locator("[role='status']").count())
        ],
    }
    page.screenshot(path=os.path.join(SHOTS, f"d9-{label}.png"))
    print(f"    [{label}] {json.dumps(state, ensure_ascii=False)[:460]}")
    return state


def clear_editor(page, replacement=None):
    """The operator's actual gesture: click into the editor, select all, delete."""
    ta = page.locator("textarea[aria-label='Project instructions']").first
    ta.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    if replacement == "\n":
        page.keyboard.press("Enter")
    elif replacement:
        page.keyboard.type(replacement)
    page.wait_for_timeout(300)


def click_save(page, settle=1500):
    page.get_by_role("button", name="Save", exact=True).first.click()
    # A PUT that has not been given time to leave is not a PUT that did not leave. Every
    # "zero PUTs" assertion in this file is made after this wait, never straight after the click.
    page.wait_for_timeout(settle)


def ack(page, budget=1800):
    """The success acknowledgement is a 2000 ms flash (`InstructionsPage.tsx`), so it is POLLED.

    D-8's docstring warns that a late observer reports a correct page as broken, and this file's
    first run walked into it anyway: leg G4 read the status after `click_save`'s 1500 ms settle plus
    a fixed 600 ms wait — ~2100 ms, past the expiry — and reported a page that had acknowledged the
    save perfectly well as silent. The other legs passed only because they happened to look sooner.

    A fixed delay is the wrong instrument for a flash. This returns as soon as a status appears,
    so no leg depends on a constant sitting inside the window.
    """
    waited = 0
    while waited <= budget:
        seen = [
            page.locator("[role='status']").nth(i).inner_text().strip()
            for i in range(page.locator("[role='status']").count())
        ]
        if any(t for t in seen):
            print(f"    ack seen ~{waited}ms after the write: {seen}")
            return seen
        page.wait_for_timeout(200)
        waited += 200
    print(f"    no ack within {budget}ms of the write")
    return []


FOCUS_PROBE = """() => {
  const a = document.activeElement
  const scrim = document.querySelector("[role='dialog']")
  const panel = scrim ? scrim.firstElementChild : null
  return {
    tag: a ? a.tagName : null,
    text: a ? (a.textContent || '').trim().slice(0, 24) : null,
    aria: a ? (a.getAttribute('aria-label') || '') : '',
    inPanel: panel && a ? panel.contains(a) : false,
    dialogOpen: !!scrim,
  }
}"""


def focus_now(page):
    return page.evaluate(FOCUS_PROBE)


def main():
    os.makedirs(FIXTURE, exist_ok=True)
    code, proj = call(
        "POST", "/projects/open", {"path": FIXTURE.replace("\\", "/"), "name": "d9-clearing"}
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
        drive(pid)
    finally:
        dcode, _ = call("DELETE", f"/projects/{pid}")
        print(f"\ncleanup: DELETE {pid} [{dcode}]")
        check(dcode in (200, 204), f"fixture {pid} is deleted")
        ccode, rest = call("GET", "/projects")
        listed = (
            rest
            if isinstance(rest, list)
            else rest.get("projects", [])
            if isinstance(rest, dict)
            else []
        )
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
    # -------------------------------------------------------------- 0, the instrument
    print("\n0 — is the bundle on the wire the post-change one?")
    index = fetch(UI + "/")
    asset = re.search(r"/assets/(index-[A-Za-z0-9_-]+\.js)", index)
    check(
        asset is not None,
        f"the served page names a JS asset ({asset.group(1) if asset else None})",
    )
    js = fetch(UI + "/assets/" + asset.group(1)) if asset else ""
    check(
        "AgentWeave keeps no copy" in js,
        "and that asset carries the dialog's own words — this IS the post-change bundle",
    )
    check(
        "Clear the instructions for" in js,
        "including its heading, so the legs below are not driving a stale page",
    )

    check(put_stored(pid, RULES) == 200, "the fixture's instructions are stored")
    check(stored(pid) == RULES, f"and read back byte-identical ({len(RULES)} chars)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # ---------------------------------------------------------- A, baseline
        print("\nA — baseline: the stored instructions are on screen")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        s = observe(page, "01-baseline")
        check(
            s["textarea"] and s["value_len"] == len(RULES),
            "the editor holds exactly what is stored",
        )
        check(s["save_disabled"] is False, "Save is enabled")
        check(s["dialogs"] == 0, "no dialog is on screen before anything is done")

        # ---------------------------------------------------------- B, 5.1(a)
        print("\nB — 5.1(a): select all, delete, Save. The ask, and nothing on the wire.")
        clear_editor(page)
        click_save(page)
        s = observe(page, "02-dialog-open")
        check(s["dialogs"] == 1, f"a confirmation is on screen ({s['dialogs']} dialog(s))")
        check(
            wire["put"] == 0,
            f"ZERO PUTs left the page while the dialog is open ({wire['put']}) — the wire, not `disabled`",
        )
        after = stored(pid)
        check(after == RULES, "and the stored row read back over the API is BYTE-IDENTICAL")
        text = (s["dialog_text"] or "").replace("\n", " ")
        check("d9-clearing" in text, f"the dialog names the project it would clear ({text[:70]!r})")
        check(
            f"{EXPECTED_LINES} lines" in text,
            f"and how much would be lost — {EXPECTED_LINES} lines",
        )
        check(
            "keeps no copy" in text and "no undo" in text,
            "and the thing the operator cannot discover anywhere else: no copy is kept",
        )
        check(
            s["value_len"] == 0,
            "the editor still holds the emptiness that was typed, unedited by the question",
        )

        # ---------------------------------------------------------- C, 5.1(b)
        print("\nC — 5.1(b): Cancel. Still nothing written.")
        page.get_by_role("button", name="Cancel", exact=True).first.click()
        page.wait_for_timeout(1200)
        s = observe(page, "03-cancelled")
        check(s["dialogs"] == 0, "the dialog is gone")
        check(wire["put"] == 0, f"still ZERO PUTs after Cancel ({wire['put']})")
        check(stored(pid) == RULES, "and the row is STILL byte-identical to what was stored")
        check(
            s["value_len"] == 0,
            "Cancel leaves the empty editor as typed — it does not restore the old text underneath",
        )

        # ---------------------------------------------------------- D, 5.1(c)
        print("\nD — 5.1(c): Save again, Confirm. Now it goes.")
        click_save(page)
        s = observe(page, "04-dialog-again")
        check(s["dialogs"] == 1, "the same question is asked again")
        check(wire["put"] == 0, f"and still nothing on the wire ({wire['put']})")
        page.get_by_role("button", name="Clear instructions", exact=True).first.click()
        early = ack(page)
        s = observe(page, "05-confirmed")
        check(s["dialogs"] == 0, "Confirm closes the dialog")
        check(wire["put"] == 1, f"EXACTLY ONE PUT left the page, and only now ({wire['put']})")
        body = json.loads(wire["bodies"][0]) if wire["bodies"] and wire["bodies"][0] else {}
        check(body.get("content") == "", f"carrying the empty string ({body!r:.60})")
        after = stored(pid)
        check(after == "", f"and the row is finally empty ({after!r:.40})")
        check(
            any("saved" in t.lower() for t in early),
            f"reported as an ordinary success, in the same place as any save {early}",
        )
        page.close()

        # ---------------------------------------------------------- E, 5.4
        print("\nE — 5.4: the keyboard. Tab, Escape, and where focus lands afterwards.")
        check(put_stored(pid, RULES) == 200, "the fixture's instructions are restored")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_editor(page)
        page.get_by_role("button", name="Save", exact=True).first.focus()
        before = focus_now(page)
        check(
            before["tag"] == "BUTTON" and before["text"] == "Save",
            f"Save has keyboard focus before the dialog opens {before}",
        )
        # Activated by the keyboard, not the mouse: this is the leg that owes a keyboard operator.
        page.keyboard.press("Enter")
        page.wait_for_timeout(1200)
        s = observe(page, "06-keyboard-dialog")
        check(s["dialogs"] == 1, "Enter on Save asks the same question a click does")
        check(wire["put"] == 0, f"and writes nothing ({wire['put']})")

        walk = []
        for _ in range(5):
            page.keyboard.press("Tab")
            page.wait_for_timeout(150)
            walk.append(focus_now(page))
        print("    Tab walk from Save, five presses:")
        for i, w in enumerate(walk, 1):
            print(f"      {i}. {w['tag']}/{w['text']!r} aria={w['aria']!r} inPanel={w['inPanel']}")

        # 5.4 says "Tab cycles within the panel". The measured answer is: it does, once focus is
        # inside — and the FIRST press escapes, because `useDialogFocus` never moves focus into the
        # panel on open and its trap only fires when `document.activeElement` is the panel's first
        # or last focusable. Focus is still on Save, outside, so press 1 follows native DOM order
        # into the textarea behind the scrim. Filed as F307 and NOT fixed here: the hook is shared
        # by six dialogs, so which control takes focus on open is a design decision this window
        # does not get to make.
        #
        # Both halves are asserted, the escape as a KEPT REPRODUCTION rather than as a red check —
        # so this drive's exit code means "the change's own contract holds and F307 is unchanged",
        # and fixing F307 will fail this file loudly, which is the correct time to revisit it.
        cycle = walk[1:]
        check(
            all(w["inPanel"] for w in cycle),
            f"once focus is inside the panel, Tab stays there — presses 2-5 {[w['inPanel'] for w in cycle]}",
        )
        check(
            [w["text"] for w in cycle] == ["Cancel", "Clear instructions"] * 2,
            f"cycling the dialog's own two controls and nothing else {[w['text'] for w in cycle]}",
        )
        check(
            walk[0]["inPanel"] is False and walk[0]["aria"] == "Project instructions",
            f"F307 REPRODUCED (filed, pre-existing, shared with ArchiveConfirmDialog): the first Tab "
            f"escapes to the editor behind the scrim — {walk[0]['tag']}/{walk[0]['aria']!r}",
        )

        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        s = observe(page, "07-escaped")
        check(s["dialogs"] == 0, "Escape cancels the dialog")
        check(wire["put"] == 0, f"having written nothing ({wire['put']})")
        check(stored(pid) == RULES, "and the row is byte-identical")
        restored = focus_now(page)
        check(
            restored["tag"] == "BUTTON" and restored["text"] == "Save",
            f"FOCUS RETURNED TO SAVE — useDialogFocus's contract, unprovable in jsdom {restored}",
        )
        page.close()

        # ---------------------------------------------------------- F, the singular branch
        print("\nF — one stored line reads '1 line', not '1 lines'")
        check(put_stored(pid, "keep it short.") == 200, "one line is stored")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_editor(page)
        click_save(page)
        s = observe(page, "08-singular")
        text = (s["dialog_text"] or "").replace("\n", " ")
        check(s["dialogs"] == 1, "the question is asked for one line as well")
        check("1 line of stored" in text, f"and says '1 line' {text[:100]!r}")
        check("1 lines" not in text, "not '1 lines'")
        check(wire["put"] == 0, f"nothing written ({wire['put']})")
        page.close()

        # ---------------------------------------------------------- G, what must not be interrupted
        print("\nG1 — the near-miss: a select-all-delete that leaves one newline (design.md D1)")
        check(put_stored(pid, RULES) == 200, "the rules are restored")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_editor(page, replacement="\n")
        click_save(page)
        s = observe(page, "09-newline-asks")
        check(
            s["dialogs"] == 1,
            "THIS is the case D-8 measured going straight through pre-change — it now asks",
        )
        check(wire["put"] == 0, f"and nothing has left the page ({wire['put']})")
        page.get_by_role("button", name="Clear instructions", exact=True).first.click()
        page.wait_for_timeout(1500)
        check(wire["put"] == 1, f"one PUT after Confirm ({wire['put']})")
        body = json.loads(wire["bodies"][0]) if wire["bodies"] and wire["bodies"][0] else {}
        wrote = body.get("content")
        check(
            wrote == "\n",
            f"carrying the newline EXACTLY as typed — the confirmed save trims nothing ({wrote!r})",
        )
        page.close()

        print("\nG2 — stored content that is only whitespace: nothing is lost, so nothing is asked")
        check(put_stored(pid, "   \n\n  ") == 200, "whitespace is stored")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_editor(page)
        click_save(page)
        s = observe(page, "10-whitespace-stored")
        check(s["dialogs"] == 0, "no dialog — this save is NOT interrupted")
        check(wire["put"] == 1, f"it went straight out ({wire['put']})")
        check(stored(pid) == "", "and the row is empty")
        page.close()

        print("\nG3 — an already-empty row, cleared again: nothing to lose")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        clear_editor(page)
        click_save(page)
        s = observe(page, "11-empty-stored")
        check(s["dialogs"] == 0, "no dialog")
        check(wire["put"] == 1, f"one PUT, uninterrupted ({wire['put']})")
        page.close()

        print("\nG4 — the ordinary save, which the change must leave completely alone")
        wire = {"put": 0, "bodies": []}
        page = open_page(browser, pid, wire)
        ta = page.locator("textarea[aria-label='Project instructions']").first
        ta.click()
        page.keyboard.press("Control+A")
        page.keyboard.type("ONE REAL RULE\n")
        # Short settle, then poll: the ack is a 2000 ms flash and the default 1500 ms settle plus a
        # look leaves almost nothing of the window. This is the leg that first exposed the trap.
        click_save(page, settle=200)
        early = ack(page)
        s = observe(page, "12-ordinary")
        check(s["dialogs"] == 0, "no confirmation, before or after the change")
        check(wire["put"] == 1, f"one PUT ({wire['put']})")
        check(stored(pid).startswith("ONE REAL RULE"), f"and it landed ({stored(pid)!r:.40})")
        check(any("saved" in t.lower() for t in early), f"acknowledged the same way {early}")
        page.close()
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
