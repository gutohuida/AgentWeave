"""D-1, 2026-09-10 (day window) — how long the page stays unclickable after a RowMenu selection.

The sibling probe of `t_d1_0910_escape_across_the_dialogs.py`, split out because it asks one
question that file was not built to ask: leg `C2d` there read
`getComputedStyle(document.body).pointerEvents === 'none'` **once**, at a fixed moment, and a single
sample cannot tell a leak from a transition. Radix's `DropdownMenu.Root` defaults to `modal: true`,
which makes the rest of the page inert while the menu is open and is supposed to restore it on
close. This samples on a clock instead, and on two different menu items, so the answer is a
duration and a scope rather than a snapshot.

Two paths through the same `RowMenu` (`hub/ui/src/components/layout/RowMenu.tsx`), from the same
menu on the same ticket:

  P1  "Move to assigned"  — an ordinary mutation. Nothing new is mounted.
  P2  "Move to blocked"   — mounts the blocking-reason input (`TaskDetailDrawer.tsx:400-460`).

If both leak, the defect is `RowMenu`'s and reaches every screen that uses it. If only P2 does, it
is the interaction between the closing menu and the control the selection mounts.

Run:  py -3.11 scripts/drive/t_d1_0910_rowmenu_leaves_the_page_inert.py
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
    print("set AW_KEY")
    sys.exit(2)

FIXTURE = os.path.join(tempfile.gettempdir(), "aw-d1-0910-inert", "fixture")
SHOTS = os.path.join(tempfile.gettempdir(), "d1-0910-shots")
os.makedirs(SHOTS, exist_ok=True)

PROBE = """() => ({
  body: getComputedStyle(document.body).pointerEvents,
  html: getComputedStyle(document.documentElement).pointerEvents,
  bodyInline: document.body.style.pointerEvents || '',
  poppers: document.querySelectorAll('[data-radix-popper-content-wrapper]').length,
  menuItems: document.querySelectorAll('[role="menuitem"]').length,
})"""

def focus_probe(tid):
    """Where the keyboard is, and whether that is inside the reason panel this ticket mounts."""
    return (
        "() => { const a = document.activeElement; const r = document.querySelector("
        + json.dumps(f"[data-testid='task-block-reason-{tid}']")
        + "); return {tag: a ? a.tagName : null,"
        " testid: a ? (a.getAttribute('data-testid') || '') : '',"
        " inReason: !!(r && a && r.contains(a))} }"
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


def seed_script(pid):
    return (
        "sessionStorage.setItem('agentweave-session', "
        + json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))
        + ");\nlocalStorage.setItem('agentweave-selected-project', "
        + json.dumps(pid)
        + ");\n"
    )


def watch(page, label, marks=(0, 500, 1000, 2000, 5000, 10000)):
    """Sample the inertness on a clock. A duration, not a snapshot."""
    seen = []
    waited = 0
    for m in marks:
        page.wait_for_timeout(m - waited)
        waited = m
        st = page.evaluate(PROBE)
        seen.append((m, st))
        print(f"    +{m:>5}ms  {json.dumps(st)}")
    recovered = [m for m, st in seen if st["body"] != "none"]
    print(
        "    [{}] body recovered at: {}".format(
            label, f"{recovered[0]}ms" if recovered else f"NEVER within {marks[-1]}ms"
        )
    )
    return seen


def open_ticket(page, tid):
    opener = page.locator(f"[data-testid='task-open-{tid}']")
    opener.first.click()
    page.wait_for_timeout(1200)
    return page.locator(f"[data-testid='task-drawer-{tid}']").count() == 1


def main():
    os.makedirs(FIXTURE, exist_ok=True)
    code, proj = call(
        "POST", "/projects/open", {"path": FIXTURE.replace("\\", "/"), "name": "d1-0910-inert"}
    )
    if code != 200:
        print(f"could not open the fixture project [{code}] {proj}")
        return 2
    pid = proj["id"]
    print("fixture project: " + pid)

    def new_task(title):
        c, t = call("POST", f"/projects/{pid}/tasks", {"title": title, "description": "x"})
        if c not in (200, 201):
            print(f"  task create failed [{c}] {t}")
            return None
        call("PATCH", "/projects/{}/tasks/{}".format(pid, t["id"]), {"status": "in_progress"})
        return t["id"]

    t1 = new_task("P1 - an ordinary move")
    t2 = new_task("P2 - the move that asks a question")
    if not t1 or not t2:
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for label, tid, item in (
            ("P1 'Move to assigned' — an ordinary mutation", t1, "assigned"),
            ("P2 'Move to blocked' — mounts the reason input", t2, "blocked"),
        ):
            print(f"\n=== {label} ===")
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.add_init_script(seed_script(pid))
            page.goto(f"{UI}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            if not open_ticket(page, tid):
                print("  could not open the ticket — skipped")
                page.close()
                continue

            FOCUS = focus_probe(tid)
            base = page.evaluate(PROBE)
            print(f"    baseline (menu never opened): {json.dumps(base)}")
            check(base["body"] != "none", "the page starts clickable")

            page.locator(f"[data-testid='task-status-menu-{tid}']").first.click()
            page.wait_for_timeout(800)
            opened = page.evaluate(PROBE)
            print(f"    menu open: {json.dumps(opened)}")
            check(
                opened["body"] == "none",
                "Radix makes the page inert while the menu is open, which is modal mode working",
            )

            page.locator(f"[data-testid='task-status-menu-{tid}-{item}']").first.click()
            print(f"    selected 'Move to {item}':")
            # §7.5 / §7.6's mouse half. Where the keyboard ends up is the whole subject of the
            # change these two paths bracket: an ordinary move leaves nothing on screen to hold
            # focus and must hand it back to the trigger, and the one move that opens a control
            # asking for an answer must leave it in that control. The same gesture, two answers,
            # and asserting only one of them is how a fix for the second breaks the first.
            page.wait_for_timeout(700)
            where = page.evaluate(FOCUS)
            print(f"    focus after the selection: {json.dumps(where)}")
            if item == "blocked":
                check(
                    where["tag"] == "INPUT" and where["inReason"],
                    "the reason input the selection opened HAS the keyboard ({}, inReason={})".format(
                        where["tag"], where["inReason"]
                    ),
                )
            else:
                check(
                    where["testid"] == f"task-status-menu-{tid}",
                    "an ordinary move hands the keyboard back to the trigger ({!r})".format(
                        where["testid"] or where["tag"]
                    ),
                )
            seen = watch(page, item)
            page.screenshot(path=os.path.join(SHOTS, f"inert-{item}.png"))
            last = seen[-1][1]
            check(
                last["body"] != "none",
                f"the page is clickable again 10s after the menu closed ({json.dumps(last)})",
            )
            check(
                last["menuItems"] == 0,
                "and the menu really is closed ({} items still in the DOM)".format(
                    last["menuItems"]
                ),
            )

            # The claim that matters is not a computed style, it is whether a click lands.
            probe_click = page.locator(f"[data-testid='task-drawer-close-{tid}']")
            landed = True
            if probe_click.count():
                try:
                    probe_click.first.click(timeout=3000)
                except Exception as exc:
                    landed = False
                    print(f"    a real click on Close: {str(exc).splitlines()[0][:90]}")
            check(landed, "a real click on the ticket's own Close button lands")
            page.close()

        # ------------------------------------------------------------------ P3
        # P1 and P2 both recover at +0ms, so selecting an item is not what leaks. The sibling
        # harness saw `body: none` persist, and the one gesture it made that these two did not is
        # **Escape while the menu is open** — which `useDialogFocus` turns into a drawer close, so
        # the menu's own Radix cleanup is running inside a subtree its parent is unmounting.
        print("\n=== P3 Escape while the menu is open — the sequence the sibling harness hit ===")
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed_script(pid))
        page.goto(f"{UI}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        if not open_ticket(page, t2):
            print("  could not open the ticket — skipped")
        else:
            page.locator(f"[data-testid='task-status-menu-{t2}']").first.click()
            page.wait_for_timeout(800)
            st = page.evaluate(PROBE)
            check(st["body"] == "none", "menu open, page inert as designed")
            print("    pressing Escape with the menu open:")
            page.keyboard.press("Escape")
            seen = watch(page, "escape-with-menu-open")
            page.screenshot(path=os.path.join(SHOTS, "inert-escape.png"))
            last = seen[-1][1]
            check(
                page.locator(f"[data-testid='task-drawer-{t2}']").count() == 1,
                "the ticket survived — one Escape should dismiss the menu, not the ticket too",
            )
            check(
                last["body"] != "none",
                f"and the page is clickable 10s later ({json.dumps(last)})",
            )
            check(
                last["poppers"] == 0,
                "with no orphaned menu wrapper left in the DOM ({})".format(last["poppers"]),
            )
            # The decisive one: not a style, a click. The board behind is the whole product.
            #
            # The ticket has to be dismissed first, and that is not a concession — it is the
            # consequence of the assertion two lines above. The drawer now correctly SURVIVES an
            # Escape aimed at the menu, and it renders over the board, so a click aimed at a card
            # underneath is intercepted by the ticket the operator still has open. Before this
            # change the drawer closed and the card was bare, which is the only reason this leg
            # ever reached the board. Relaxing the assertion instead would have been the wrong fix:
            # the probe above already reads `body` pointer-events as `auto`, so nothing is wedged
            # and there is nothing here to excuse.
            close = page.locator(f"[data-testid='task-drawer-close-{t2}']")
            if close.count():
                close.first.click()
                page.wait_for_timeout(700)
            check(
                page.locator(f"[data-testid='task-drawer-{t2}']").count() == 0,
                "the ticket closes when the operator actually asks it to",
            )
            board_click = page.locator("[data-testid^='task-open-']")
            landed = True
            if board_click.count():
                try:
                    board_click.first.click(timeout=3000)
                except Exception as exc:
                    landed = False
                    print(f"    a real click on the board: {str(exc).splitlines()[0][:90]}")
            check(landed, "and a real click anywhere on the board still lands")
            # Does a reload get the operator back? That is the difference between a wedge and a
            # nuisance, and it is one line to answer.
            if not landed:
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                after = page.evaluate(PROBE)
                print(f"    after a reload: {json.dumps(after)}")
                check(after["body"] != "none", "a reload is the only way out, and it does work")
            page.close()

        # ------------------------------------------------------------------ P4
        # P1, P2 and P3 all recover at +0ms, so none of them is what the sibling harness saw. This
        # replays that harness's sequence exactly, gesture for gesture, because the alternative to
        # reproducing it is filing a severity against an artefact of my own script.
        print("\n=== P4 the sibling harness's exact sequence, replayed ===")
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed_script(pid))
        page.goto(f"{UI}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        opener = page.locator(f"[data-testid='task-open-{t2}']")

        def reopen_if_closed():
            # Before this change, Escape-with-the-menu-open closed the ticket as well as the menu,
            # so the sibling harness's next gesture was to open it again. It no longer does, and
            # the ticket is already there — so this gesture is now conditional rather than removed.
            # Keeping it unconditional would click a card the open drawer covers, and the 30s
            # timeout that produced would `break` the loop below with no `check()` failing.
            if page.locator(f"[data-testid='task-drawer-{t2}']").count() == 0:
                opener.first.click()

        steps = [
            ("open the ticket", lambda: opener.first.click()),
            ("Escape on the drawer", lambda: page.keyboard.press("Escape")),
            ("open it again", lambda: opener.first.click()),
            (
                "open the status menu",
                lambda: page.locator(f"[data-testid='task-status-menu-{t2}']").first.click(),
            ),
            ("Escape with the menu open", lambda: page.keyboard.press("Escape")),
            ("open it a third time, if the Escape closed it", reopen_if_closed),
            (
                "open the status menu again",
                lambda: page.locator(f"[data-testid='task-status-menu-{t2}']").first.click(),
            ),
            (
                "select by visible text, as the sibling does",
                lambda: page.get_by_text("Move to blocked", exact=True).first.click(),
            ),
        ]
        for name, act in steps:
            # A refused gesture is a FAILED CHECK, not a `break`. The old form broke out of the
            # loop, so the last three gestures — including the selection this replay exists to
            # reach — never ran and nothing failed: the harness quietly shrank instead of going
            # red. Measured on 2026-09-10, when exactly that hid three gestures behind one 30s
            # click timeout.
            try:
                act()
            except Exception as exc:
                print(f"    [{name}] refused: {str(exc).splitlines()[0][:90]}")
                check(False, f"the replayed gesture '{name}' can be performed")
                continue
            page.wait_for_timeout(900)
            print("    after {:<44} {}".format(name + ":", json.dumps(page.evaluate(PROBE))))
        print("    then, on a clock:")
        seen = watch(page, "replay")
        page.screenshot(path=os.path.join(SHOTS, "inert-replay.png"))
        last = seen[-1][1]
        check(
            last["body"] != "none",
            f"the page is clickable 10s after the replayed sequence ({json.dumps(last)})",
        )
        reason = page.locator(f"[data-testid='task-block-reason-{t2}']")
        if reason.count():
            landed = True
            try:
                reason.locator("input").first.click(timeout=3000)
            except Exception as exc:
                landed = False
                print(f"    click on the reason input: {str(exc).splitlines()[0][:90]}")
            check(landed, "and the reason input the operator must fill in can be clicked")
        page.close()

        # ------------------------------------------------------------------ P5
        # P4 clears the harness: nothing about the sequence leaks. What the sibling harness actually
        # did that this did not is TYPE — and it typed at whatever had focus, which after selecting
        # "Move to blocked" is the menu trigger, not the reason input. A space on a focused button
        # is a click. This checks that, because it turns "the typed reason goes nowhere" into
        # "and every space in it re-opens the menu the operator just finished with".
        print("\n=== P5 what the operator's own sentence does when focus is on the trigger ===")
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed_script(pid))
        page.goto(f"{UI}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        if open_ticket(page, t1):
            trigger = page.locator(f"[data-testid='task-status-menu-{t1}']")
            trigger.first.focus()
            before = page.evaluate(PROBE)
            check(before["menuItems"] == 0, "the menu is closed and the trigger has focus")
            page.keyboard.press("Space")
            page.wait_for_timeout(700)
            after = page.evaluate(PROBE)
            print(f"    after one Space on the focused trigger: {json.dumps(after)}")
            check(
                after["menuItems"] > 0 and after["body"] == "none",
                "ONE SPACE re-opens the status menu and makes the page inert — and the reason an "
                "operator types contains spaces",
            )
        page.close()

        browser.close()

    print("\nshots: " + SHOTS)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED: " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
