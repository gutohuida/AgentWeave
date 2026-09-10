"""D-1, 2026-09-10 (day window) — the confirm dialog driven as an operator, and the Escape
key across every dialog `useDialogFocus` serves.

Two subjects, one Hub, one browser.

**Subject 1 — last night's `ClearInstructionsDialog`, driven rather than scripted.** The night
window drove it 59/59 legs and every one of those legs opened the dialog and then finished with it.
An operator does not. They dismiss it, they open it again, they click the destructive button twice
because the first click did not visibly do anything. Legs A1-A4 are exactly those gestures, and each
counts writes on the wire rather than reading the DOM.

**Subject 2 — `useDialogFocus`'s Escape branch across all six call sites.** `F307` measured the Tab
branch on one dialog and tabulated *five*. `grep -rn useDialogFocus hub/ui/src` returns **six**, and
the missing one — `TaskDetailDrawer` — is the only call site that is not a confirm-shaped panel and
the only one that mounts a control with an Escape handler of its own
(`TaskDetailDrawer.tsx:409-415`, the blocking-reason input). The hook's Escape branch is bound on
`document`; React 18 delegates `onKeyDown` at the root container, which is a *descendant* of
`document`. Both therefore fire on one keystroke unless someone stops propagation, and nobody does.
Leg C drives that. Legs D1-D2 are the same key on other call sites, so a defect found in C is
reported as specific rather than as "the hook is broken".

Run:  py -3.11 scripts/drive/t_d1_0910_escape_across_the_dialogs.py
      (AW_HUB / AW_UI / AW_KEY; defaults to :8013)

Creates one fixture project and one fixture task. Refuses :8000 (the operator's real usage) and
:8010 (the trial Hub). No agent turn is triggered, so nothing binds a model and nothing spends
tokens.
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8013")
UI = os.environ.get("AW_UI", HUB)
KEY = os.environ.get("AW_KEY", "")
for _port in (":8000", ":8010"):
    if HUB.endswith(_port) or UI.endswith(_port):
        print("REFUSING TO RUN: " + _port + " is not a throwaway.")
        sys.exit(1)
if not KEY:
    print("set AW_KEY (GET /api/v1/setup/token on the throwaway Hub)")
    sys.exit(2)

PROTECTED = {"proj-d85a82bf4216", "proj-5e960453", "proj-18e5d4e0"}
FIXTURE = os.path.join(tempfile.gettempdir(), "aw-d1-0910-drive", "fixture")
SHOTS = os.path.join(tempfile.gettempdir(), "d1-0910-shots")
os.makedirs(SHOTS, exist_ok=True)

RULES = "PROJECT RULES\n\n" + "".join(
    f"- Rule number {i}: do the careful thing.\n" for i in range(1, 41)
)

PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print("  [{}] {}".format("PASS" if ok else "FAIL", label))


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


def seed_script(pid):
    return (
        "sessionStorage.setItem('agentweave-session', "
        + json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))
        + ");\nlocalStorage.setItem('agentweave-selected-project', "
        + json.dumps(pid)
        + ");\n"
    )


def open_page(browser, pid, tab, wire=None, section=None):
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    page.add_init_script(seed_script(pid))
    if wire is not None:

        def handler(route, request):
            if request.method in ("PUT", "POST", "PATCH", "DELETE"):
                wire.append((request.method, request.url.split("/api/v1")[-1]))
            route.continue_()

        page.route("**/api/v1/**", handler)
    url = f"{UI}/?project={pid}&tab={tab}"
    if section:
        url += "&section=" + section
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    return page


FOCUS_PROBE = """() => {
  const a = document.activeElement
  const scrim = document.querySelector("[role='dialog']")
  const panel = scrim ? scrim.firstElementChild : null
  return {
    tag: a ? a.tagName : null,
    text: a ? (a.textContent || '').trim().slice(0, 30) : null,
    aria: a ? (a.getAttribute('aria-label') || '') : '',
    testid: a ? (a.getAttribute('data-testid') || '') : '',
    inPanel: panel && a ? panel.contains(a) : false,
    dialogs: document.querySelectorAll("[role='dialog']").length,
  }
}"""


def focus_now(page, label=""):
    st = page.evaluate(FOCUS_PROBE)
    if label:
        print(f"    [{label}] focus={json.dumps(st, ensure_ascii=False)}")
    return st


def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, name + ".png"))


def instr_puts(wire):
    return [w for w in wire if w[0] == "PUT" and "instructions" in w[1]]


# ----------------------------------------------------------------------------- subject 1


def subject_one(browser, pid):
    print("\n=== SUBJECT 1 — the clear-instructions dialog, as an operator uses it ===")

    print("\nA1 — Escape dismisses: nothing on the wire, the editor keeps the gesture, focus back")
    check(put_stored(pid, RULES) == 200, "the 42-line baseline is stored")
    wire = []
    page = open_page(browser, pid, "environment", wire, section="instructions")
    ta = page.locator("textarea[aria-label='Project instructions']").first
    ta.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    save = page.get_by_role("button", name="Save", exact=True).first
    save.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    check(page.get_by_role("dialog").count() == 1, "the dialog opened on the keyboard alone")
    opened_text = (
        page.get_by_role("dialog").first.inner_text().strip()
        if page.get_by_role("dialog").count()
        else ""
    )
    print(f"    dialog says: {opened_text[:160]!r}")
    shot(page, "a1-open")
    page.keyboard.press("Escape")
    page.wait_for_timeout(900)
    check(page.get_by_role("dialog").count() == 0, "Escape closed it")
    check(len(instr_puts(wire)) == 0, f"and nothing left the page ({len(instr_puts(wire))} PUTs)")
    check(stored(pid) == RULES, "the stored row is byte-identical")
    check(ta.input_value() == "", "the editor still holds the operator's deletion")
    st = focus_now(page, "after Escape")
    check(
        st["text"] == "Save",
        "focus is back on Save, not lost to the body ({!r})".format(st["text"]),
    )

    print("\nA2 — re-opened from that restored focus, without touching the mouse")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    reopened = page.get_by_role("dialog")
    check(reopened.count() == 1, "it opens again")
    if reopened.count():
        again = reopened.first.inner_text().strip()
        check(
            again == opened_text,
            "and says exactly what it said before — the dismissal left no residue",
        )
        if again != opened_text:
            print(f"      first : {opened_text[:200]!r}")
            print(f"      second: {again[:200]!r}")
    shot(page, "a2-reopen")

    print("\nA3 — the race: the destructive button clicked twice, the way an operator does")
    before = len(instr_puts(wire))
    btn = page.get_by_role("button", name="Clear instructions", exact=True).first
    btn.click(click_count=2, delay=40)
    page.wait_for_timeout(2200)
    after = len(instr_puts(wire))
    shot(page, "a3-double")
    check(after - before == 1, f"a double click is one write, not two ({after - before} PUTs)")
    check(stored(pid) == "", "the row is cleared")
    check(page.get_by_role("dialog").count() == 0, "and the dialog is gone")
    page.close()

    print("\nA4 — F307's wrong-write path, driven end to end rather than described")
    check(put_stored(pid, RULES) == 200, "baseline restored")
    wire2 = []
    page = open_page(browser, pid, "environment", wire2, section="instructions")
    ta = page.locator("textarea[aria-label='Project instructions']").first
    ta.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    page.get_by_role("button", name="Save", exact=True).first.click()
    page.wait_for_timeout(1200)
    check(page.get_by_role("dialog").count() == 1, "the dialog is up")
    page.keyboard.press("Tab")
    st = focus_now(page, "after one Tab")
    check(
        st["aria"] == "Project instructions", "F307 unchanged: the first Tab lands behind the scrim"
    )
    page.keyboard.type("TYPED BEHIND THE SCRIM")
    page.wait_for_timeout(300)
    shot(page, "a4-typed-behind")
    page.keyboard.press("Escape")
    page.wait_for_timeout(900)
    check(
        page.get_by_role("dialog").count() == 0, "Escape closed the dialog from inside the editor"
    )
    hidden = ta.input_value()
    print(f"    the editor now holds: {hidden!r}")
    check(
        hidden == "TYPED BEHIND THE SCRIM",
        "the text typed at a control the operator could not see is in the editor",
    )
    focus_now(page, "after Escape from the editor")
    page.get_by_role("button", name="Save", exact=True).first.click()
    page.wait_for_timeout(2000)
    landed = stored(pid)
    shot(page, "a4-saved")
    check(
        landed == "TYPED BEHIND THE SCRIM",
        f"F307's wrong write REACHES THE DATABASE, unasked ({landed[:60]!r})",
    )
    page.close()


# ----------------------------------------------------------------------------- subject 2


def subject_two(browser, pid):
    print("\n=== SUBJECT 2 — Escape across the call sites of useDialogFocus ===")

    code, task = call(
        "POST",
        f"/projects/{pid}/tasks",
        {"title": "A ticket to press Escape inside", "description": "fixture"},
    )
    if code not in (200, 201):
        print(f"  could not create the fixture task [{code}] {task}")
        return
    tid = task["id"]
    # `blocked` is reachable only from `in_progress` (GET /tasks/transitions/allowed), and the
    # reason input is the only control on this screen that owns the Escape key itself. Put the
    # fixture where that control is offered, over the API, so no leg below depends on the UI to
    # arrange its own precondition.
    code, moved = call("PATCH", f"/projects/{pid}/tasks/{tid}", {"status": "in_progress"})
    print("  fixture task: {} status={} (moved: {})".format(tid, task.get("status"), code))
    if code != 200:
        print(f"  could not move it to in_progress [{code}] {moved}")

    print("\nC — TaskDetailDrawer: the sixth call site F307 never tabulated")
    wire = []
    page = open_page(browser, pid, "tasks", wire)
    opener = page.locator(f"[data-testid='task-open-{tid}']")
    if opener.count() == 0:
        opener = page.get_by_text("A ticket to press Escape inside").first
    opener.first.click()
    page.wait_for_timeout(1200)
    check(page.locator(f"[data-testid='task-drawer-{tid}']").count() == 1, "the ticket is open")
    shot(page, "c1-drawer")

    print("  C1 — the plain contract first: Escape on the drawer itself closes it")
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    check(
        page.locator(f"[data-testid='task-drawer-{tid}']").count() == 0,
        "Escape closes the drawer",
    )

    print("  C2 — the status menu is itself a nested control that owns Escape (Radix)")
    opener.first.click()
    page.wait_for_timeout(1200)
    menu = page.locator(f"[data-testid='task-status-menu-{tid}']")
    check(menu.count() == 1, "the status menu is there")
    if menu.count():
        menu.first.click()
        page.wait_for_timeout(800)
    check(
        page.get_by_text("Move to blocked", exact=True).count() >= 1,
        "the menu is open and offers the moves legal from in_progress",
    )
    shot(page, "c2-menu-open")
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    menu_closed = page.get_by_text("Move to blocked", exact=True).count() == 0
    drawer_survived = page.locator(f"[data-testid='task-drawer-{tid}']").count() == 1
    print(f"    menu closed: {menu_closed}   ticket survived: {drawer_survived}")
    check(menu_closed, "Escape closes the menu, which is Radix doing its job")
    check(
        drawer_survived,
        "and the ticket behind it is STILL OPEN — dismissing a menu is not dismissing the ticket",
    )
    shot(page, "c2b-after-menu-escape")

    print("  C2c — now the reason input: Move to blocked, type, then Escape")
    if not drawer_survived:
        opener.first.click()
        page.wait_for_timeout(1200)
    menu = page.locator(f"[data-testid='task-status-menu-{tid}']")
    if menu.count():
        menu.first.click()
        page.wait_for_timeout(800)
    blocked_item = page.get_by_text("Move to blocked", exact=True)
    check(blocked_item.count() >= 1, "'Move to blocked' is offered")
    if blocked_item.count():
        blocked_item.first.click()
    page.wait_for_timeout(900)
    reason = page.locator(f"[data-testid='task-block-reason-{tid}']")
    check(reason.count() == 1, "the reason input opened instead of sending the status")
    shot(page, "c2-reason-open")
    st = focus_now(page, "reason input")
    check(
        st["tag"] == "INPUT",
        "the input the control mounts with autoFocus actually HAS focus ({}, testid={!r})".format(
            st["tag"], st["testid"]
        ),
    )
    # Not a second reading of the same fact. `document.activeElement` says where the browser thinks
    # focus is; this says where the operator's keystrokes went, which is the thing that matters and
    # the thing they can see.
    page.keyboard.type("the staging API key")
    page.wait_for_timeout(300)
    typed_into = reason.locator("input").first.input_value() if reason.count() else "<no input>"
    print(f"    the reason field now holds: {typed_into!r}")
    check(
        typed_into == "the staging API key",
        f"and the operator's typed reason is IN it ({typed_into!r})",
    )

    print("  C2d — so the operator reaches for the mouse instead, and cannot use that either")
    # THE CAUSE HERE IS C2c, NOT A RADIX LEAK. `pointer-events: none` on `document.body` is how a
    # modal `DropdownMenu` makes the page inert while it is open — and the sentence typed in C2c
    # went to the focused menu *trigger*, where a space is a click, so its last space re-opened the
    # menu. The sibling probe `t_d1_0910_rowmenu_leaves_the_page_inert.py` sampled this on a clock
    # after an ordinary selection, after the blocked selection, after Escape-with-the-menu-open and
    # after this whole sequence replayed without typing: `body` recovers at +0 ms in all four.
    # Radix cleans up correctly. Read these two lines as the SECOND-ORDER cost of F309, not as a
    # finding of their own — that distinction cost an hour and is why it is written here.
    inert = page.evaluate(
        "() => ({html: getComputedStyle(document.documentElement).pointerEvents,"
        " body: getComputedStyle(document.body).pointerEvents,"
        " menus: document.querySelectorAll('[data-radix-popper-content-wrapper]').length})"
    )
    print(f"    pointer-events after typing a reason with spaces in it: {json.dumps(inert)}")
    check(
        inert["body"] != "none" and inert["html"] != "none",
        f"the page is still clickable after typing a reason ({json.dumps(inert)})",
    )
    clickable = True
    if reason.count():
        try:
            reason.locator("input").first.click(timeout=4000)
        except Exception as exc:
            clickable = False
            print(f"    the click never landed: {str(exc).splitlines()[0][:120]}")
    check(clickable, "the reason input can then be reached with the mouse")
    if clickable and reason.count():
        page.keyboard.type("the staging API key")
        page.wait_for_timeout(300)
        clicked_in = reason.locator("input").first.input_value()
        print(f"    after clicking into it first: {clicked_in!r}")
        check(
            clicked_in == "the staging API key",
            "the control itself works once focus is put in it by hand",
        )
        st = focus_now(page, "after clicking in")
        check(st["tag"] == "INPUT", "and focus is now genuinely in the input")
    else:
        # Focus it programmatically, so C3 still measures the Escape branch it exists to measure.
        page.evaluate(
            "(sel) => document.querySelector(sel + ' input').focus()",
            f"[data-testid='task-block-reason-{tid}']",
        )
        page.keyboard.type("the staging API key")
        page.wait_for_timeout(300)
        print(
            "    forced focus in; field now: {!r}".format(
                reason.locator("input").first.input_value()
            )
        )

    print("  C3 — Escape from INSIDE the input, where its own handler is bound (line 413-414)")
    page.keyboard.press("Escape")
    page.wait_for_timeout(900)
    shot(page, "c3-after-escape")
    reason_gone = page.locator(f"[data-testid='task-block-reason-{tid}']").count() == 0
    drawer_gone = page.locator(f"[data-testid='task-drawer-{tid}']").count() == 0
    print(f"    reason cancelled: {reason_gone}   drawer closed too: {drawer_gone}")
    check(reason_gone, "the reason input is cancelled, which is what its own handler asks for")
    check(
        not drawer_gone,
        "AND THE TICKET IS STILL OPEN — one Escape should undo one thing, not two",
    )
    writes = [w for w in wire if w[0] in ("PATCH", "PUT") and "/tasks/" in w[1]]
    check(len(writes) == 0, f"nothing was written by any of it ({writes})")

    print("\n  C4 — and what the operator has to do to get back to where they were")
    still = page.locator(f"[data-testid='task-drawer-{tid}']").count()
    print(f"    drawers on screen after one Escape: {still}")
    if still:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    page.close()

    print("\nD — the same key on other call sites, so C is reported as specific")

    print("  D1 — AgentCreateDialog")
    page = open_page(browser, pid, "agents")
    trigger = page.locator(f"[data-testid='rail-add-agent-{pid}']")
    if trigger.count() == 0:
        print("    no 'Add agent' rail trigger found — skipped")
    else:
        trigger.first.click()
        page.wait_for_timeout(1200)
        check(page.get_by_role("dialog").count() >= 1, "the create dialog opened")
        st = focus_now(page, "on open")
        check(st["inPanel"], "it autofocuses inside the panel ({})".format(st["tag"]))
        page.keyboard.type("escape-probe")
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)
        check(page.get_by_role("dialog").count() == 0, "Escape closes it")
        shot(page, "d1-agent-dialog")
    page.close()

    print("  D2 — ProjectManagerModal")
    # The old form of this leg looked for `add-project` on the environment tab and, not finding
    # it, printed "skipped" and called no `check()` — so a leg that never ran lowered the passed
    # count without raising the failed one, and the run still read as clean. It was not the
    # product: `tab=environment` puts the rail into SECTION mode (`rail-section-back` is present,
    # the project list is not), and the single "Add project" action only renders in the list view.
    # One click on the rail's back control restores it. The skip is now a `check()` too, so a
    # trigger that genuinely disappears fails this harness instead of quietly shrinking it.
    page = open_page(browser, pid, "environment")
    back = page.locator("[data-testid='rail-section-back']")
    if back.count():
        back.first.click()
        page.wait_for_timeout(1000)
    trigger = page.locator("[data-testid='add-project']")
    check(trigger.count() >= 1, f"the rail's 'Add project' action is reachable ({trigger.count()})")
    opened = False
    if trigger.count():
        trigger.first.click()
        page.wait_for_timeout(1400)
        opened = page.locator("[aria-labelledby='project-manager-title']").count() > 0
    check(opened, "the project manager opened")
    if opened:
        focus_now(page, "on open")
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)
        check(
            page.locator("[aria-labelledby='project-manager-title']").count() == 0,
            "Escape closes the project manager",
        )
        shot(page, "d2-project-manager")
    page.close()

    print(
        "  D3 — the directory browser, with Escape pressed where the operator's focus ACTUALLY is"
    )
    # §7.4. The point of this leg is the gesture it does NOT make: it never clicks inside the
    # browser first. `DirectoryPicker` binds its Escape handler with React's `onKeyDown` on its own
    # root div, so that handler runs only when focus is inside the browser. Opening the browser
    # leaves focus on the control that opened it, which is OUTSIDE that root — so nothing calls
    # `preventDefault()`, the modal's `useDialogFocus` sees an unclaimed Escape on `document`, and
    # the operator loses the whole modal and their typed path when they meant to dismiss a
    # dropdown. Two review rounds recorded that this component needed no edit; R3 measured that it
    # does, and this leg is that measurement.
    #
    # Asserted in the direction of the CORRECT behaviour, so it is red until §2.2 lands and green
    # after. Against a bundle carrying §1.1 and not §2.2 it MUST fail — that red run is the only
    # mutation-check §2.2 gets, because the fix and its evidence cannot both be present at once.
    page = open_page(browser, pid, "environment")
    back = page.locator("[data-testid='rail-section-back']")
    if back.count():
        back.first.click()
        page.wait_for_timeout(1000)
    trigger = page.locator("[data-testid='add-project']")
    check(trigger.count() >= 1, "the rail's 'Add project' action is reachable for the browser leg")
    if trigger.count():
        trigger.first.click()
        page.wait_for_timeout(1400)
    modal = "[aria-labelledby='project-manager-title']"
    picker = "[aria-label='Browse for a directory']"
    check(page.locator(modal).count() == 1, "the project manager is up")
    # A path is typed first so the leg can say what an Escape costs, not merely what it closes.
    typed_path = "C:/some/deliberate/path"
    path_input = page.locator(modal).locator("input").first
    path_input.click()
    page.keyboard.press("Control+A")
    page.keyboard.type(typed_path)
    page.wait_for_timeout(300)
    # The native folder dialog is offered on this host, so the in-Hub browser lives behind the
    # link beside it. Never click "Browse…" here: that spawns an OS dialog this process cannot
    # dismiss and the run would hang rather than fail.
    in_hub = page.get_by_text("Browse within the Hub instead", exact=True)
    if in_hub.count():
        in_hub.first.click()
    else:
        page.get_by_role("button", name="Open directory browser").first.click()
    page.wait_for_timeout(1200)
    check(page.locator(picker).count() == 1, "the in-Hub directory browser opened")
    shot(page, "d3-picker-open")
    st = focus_now(page, "browser just opened — nothing clicked inside it")
    # Not decoration: this records WHY the leg below fails, so a future reader does not have to
    # re-derive it. Focus is on the opener, which is outside the browser's own root.
    inside = page.evaluate(
        "(sel) => { const r = document.querySelector(sel); const a = document.activeElement;"
        " return !!(r && a && r.contains(a)) }",
        picker,
    )
    print(f"    focus is inside the browser: {inside}   ({st['tag']}, text={st['text']!r})")

    page.keyboard.press("Escape")
    page.wait_for_timeout(900)
    shot(page, "d3-after-escape")
    picker_gone = page.locator(picker).count() == 0
    modal_alive = page.locator(modal).count() == 1
    survived_path = path_input.input_value() if modal_alive else "<the modal is gone>"
    print(
        f"    browser closed: {picker_gone}   modal survived: {modal_alive}   path: {survived_path!r}"
    )
    check(picker_gone, "Escape closes the directory browser")
    check(
        modal_alive,
        "AND THE PROJECT MODAL IS STILL OPEN — one Escape dismisses the dropdown, not the dialog "
        "behind it",
    )
    check(
        survived_path == typed_path,
        f"and the path the operator typed is still there ({survived_path!r})",
    )
    page.close()


def drive(pid):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        subject_one(browser, pid)
        subject_two(browser, pid)
        browser.close()


def main():
    os.makedirs(FIXTURE, exist_ok=True)
    code, proj = call(
        "POST", "/projects/open", {"path": FIXTURE.replace("\\", "/"), "name": "d1-0910-escape"}
    )
    if code != 200:
        print(f"could not open the fixture project [{code}] {proj}")
        return 2
    pid = proj["id"]
    print("fixture project: " + pid)
    if pid in PROTECTED:
        print("REFUSING: that is a protected project id.")
        return 2
    try:
        drive(pid)
    finally:
        print("\nshots: " + SHOTS)
        print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
        for f in FAIL:
            print("  FAILED: " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
