"""D-1, 2026-09-07 (day window) — drive F271's column C for real.

The 2026-09-06 night window closed column C **by construction**, and FINDINGS.md records the
ground it used verbatim:

    "this page offers no in-page project switcher (`'Switch project' controls on screen: 0`,
     unchanged since 2026-09-02), so no browser has been made to perform the switch"

That number comes from `t_d4_instructions_failed_load.py:316`:

    switch = page.get_by_role("button", name="Switch project")

`ProjectHeader.tsx:48` renders the switcher as a **`<select aria-label="Switch project">`**, whose
implicit ARIA role is `combobox`, not `button`. The harness's own repo already knows this —
`App-mount.test.tsx:214` reaches it with `getByRole('combobox', { name: 'Switch project' })`. So the
locator can never return anything but 0 whatever the page renders, and "0 controls on screen" is a
statement about the instrument, not about the product. F190's lesson, in a drive harness rather than
a unit test.

This asks the three questions that separate instrument from product:

  C0. With the correct role, is a project switcher on screen on the Instructions page?
  C1. When it is used, does the Instructions page stay mounted? `App.tsx:602` wires
      `onSelectProject` to `navigateTo(projectDestination(id))`, and `projectDestination`'s
      default tab is `'overview'` (`lib/navigation.ts:55`) — so the prediction is that the switch
      navigates AWAY and the component unmounts. That is a *different* reason for column C being
      unreachable than the one FINDINGS.md records, and it is the one that has to be measured.
  C2. The hazard itself, driven rather than argued: switch from A (loaded, editor holding A's
      text) to B whose GET fails. Is an editor holding A's text EVER offered while B is selected,
      and is any PUT issued? Measured on the wire and read back from the API for both projects.

Run:  AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/t_d1_0907_cross_project_switch.py

Creates two fixture projects and deletes them. Refuses :8000. No agent turn, no model bound.
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
KEY = os.environ.get("AW_KEY", "aw_live_d0907aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
if HUB.endswith(":8000") or UI.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

DIR_A = os.path.join(os.path.expanduser("~"), "Documents", "drive-0907-d1a")
DIR_B = os.path.join(os.path.expanduser("~"), "Documents", "drive-0907-d1b")
SHOTS = os.path.join(tempfile.gettempdir(), "d1-0907-shots")
os.makedirs(SHOTS, exist_ok=True)
# `POST /projects/open` refuses a path that does not exist with a 409
# `project_workspace_missing`, so the fixtures are made here rather than assumed.
os.makedirs(DIR_A, exist_ok=True)
os.makedirs(DIR_B, exist_ok=True)

ALPHA = "ALPHA PROJECT RULES\n\n- Never force-push.\n- Every PR needs a test.\n"
BRAVO = "BRAVO PROJECT RULES\n\n- Ship behind a flag.\n"

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


def observe(page, label):
    ta = page.locator("textarea[aria-label='Project instructions']")
    skel = page.locator("[aria-label='Loading instructions']")
    save = page.get_by_role("button", name="Save", exact=True)
    alerts = page.locator("[role='alert']")
    state = {
        "loc": page.evaluate("location.search + location.hash"),
        "skeleton": skel.count() > 0,
        "textarea": ta.count() > 0,
        "value": ta.first.input_value() if ta.count() else None,
        "save_visible": save.count() > 0,
        "alerts_n": alerts.count(),
    }
    page.screenshot(path=os.path.join(SHOTS, f"d1-{label}.png"))
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


def instructions_url(pid):
    return f"{UI}/?project={pid}&tab=environment&section=instructions"


def main():
    code, pa = call("POST", "/projects/open", {"path": DIR_A.replace("\\", "/"), "name": "d1-0907-alpha"})
    if code != 200:
        print(f"could not open fixture A [{code}] {pa}")
        return 2
    pid_a = pa["id"]
    code, pb = call("POST", "/projects/open", {"path": DIR_B.replace("\\", "/"), "name": "d1-0907-bravo"})
    if code != 200:
        call("DELETE", f"/projects/{pid_a}")
        print(f"could not open fixture B [{code}] {pb}")
        return 2
    pid_b = pb["id"]
    print(f"fixtures: A={pid_a}  B={pid_b}")
    try:
        drive(pid_a, pid_b)
    finally:
        for pid in (pid_a, pid_b):
            dcode, _ = call("DELETE", f"/projects/{pid}")
            check(dcode in (200, 204), f"fixture {pid} is deleted [{dcode}]")
    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


def drive(pid_a, pid_b):
    check(call("PUT", f"/projects/{pid_a}/project/instructions", {"content": ALPHA})[0] == 200,
          "A's instructions are stored")
    check(call("PUT", f"/projects/{pid_b}/project/instructions", {"content": BRAVO})[0] == 200,
          "B's instructions are stored")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # ------------------------------------------------------ C0: is the switcher on screen?
        print("\nC0 - the instrument: which role does the switcher actually have?")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid_a))
        page.goto(instructions_url(pid_a), wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        observe(page, "01-on-a")
        as_button = page.get_by_role("button", name="Switch project").count()
        as_combobox = page.get_by_role("combobox", name="Switch project").count()
        by_testid = page.locator("[data-testid='project-switcher-select']").count()
        print(f"    role=button:'Switch project' -> {as_button}"
              f"   role=combobox:'Switch project' -> {as_combobox}"
              f"   [data-testid=project-switcher-select] -> {by_testid}")
        check(as_button == 0,
              f"the night's locator (role=button) still returns 0 - reproduced ({as_button})")
        check(as_combobox >= 1,
              f"but a switcher IS on screen under its real role, combobox ({as_combobox}) - "
              "so '0 controls on screen' measured the instrument, not the page")
        check(by_testid == as_combobox,
              f"and the testid agrees with the role query ({by_testid} vs {as_combobox})")
        opts = page.locator("[data-testid='project-switcher-select'] option").all_text_contents()
        print(f"    options: {opts}")
        check(len(opts) >= 2, f"the switcher offers both fixtures ({len(opts)} options)")

        # ------------------------------------------------------ C1: does the page stay mounted?
        print("\nC1 - use the switcher for real. Does InstructionsPage survive the switch?")
        before = observe(page, "02-before-switch")
        check(before["textarea"] and before["value"] == ALPHA,
              "A's editor holds A's text before the switch")
        page.select_option("[data-testid='project-switcher-select']", pid_b)
        page.wait_for_timeout(5000)
        after = observe(page, "03-after-switch")
        selected = page.evaluate("localStorage.getItem('agentweave-selected-project')")
        print(f"    selected project in localStorage after switch: {selected}")
        check(selected == pid_b, f"the switch did select B ({selected})")
        check("tab=environment" not in after["loc"],
              f"the switch navigated AWAY from the environment tab ({after['loc']}) - "
              "this, not a missing control, is why column C is unreachable")
        check(not after["textarea"],
              "and no instructions editor is on screen at all after the switch - the page unmounted")

        # -------------------------------------- C2: the hazard, with B's read made to fail
        print("\nC2 - the hazard itself: A loaded, then switch to B whose GET fails")
        page.close()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid_a))
        seen = {"get_a": 0, "get_b": 0, "puts": []}

        def handler(route, request):
            u = request.url
            if "/project/instructions" in u:
                if request.method == "PUT":
                    seen["puts"].append((u, request.post_data))
                    route.abort("failed")
                    return
                if pid_b in u:
                    seen["get_b"] += 1
                    route.abort("connectionrefused")
                    return
                if pid_a in u:
                    seen["get_a"] += 1
            route.continue_()

        page.route("**/*", handler)
        page.goto(instructions_url(pid_a), wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        s = observe(page, "04-c2-on-a")
        check(s["value"] == ALPHA, "A's editor holds A's text, load succeeded")

        page.select_option("[data-testid='project-switcher-select']", pid_b)
        page.wait_for_timeout(4000)
        observe(page, "05-c2-mid")
        # Navigate deliberately back to the instructions section under B - the sharpest reachable
        # approximation of "the component is showing B while content still holds A".
        page.goto(instructions_url(pid_b), wait_until="domcontentloaded")
        page.wait_for_timeout(10000)
        s = observe(page, "06-c2-on-b-failed")
        print(f"    GET A: {seen['get_a']}   GET B (aborted): {seen['get_b']}   PUTs: {len(seen['puts'])}")
        check(seen["get_b"] >= 1, f"B's instructions GET was attempted and failed ({seen['get_b']}x)")
        check(s["value"] != ALPHA,
              f"no editor holding A's text is offered while B is selected (value={s['value']!r})")
        check(not s["textarea"], "in fact no editor is offered at all under B's failed load")
        check(s["alerts_n"] >= 1, f"the failure is stated instead ({s['alerts_n']} alert(s))")

        boxes = page.locator("textarea")
        typed = 0
        for i in range(boxes.count()):
            try:
                boxes.nth(i).fill("TYPED BY THE 0907 DRIVE")
                typed += 1
            except Exception as exc:
                print(f"    (textarea {i} refused input: {type(exc).__name__})")
        saves = page.get_by_role("button", name="Save", exact=True)
        clicked = 0
        for i in range(saves.count()):
            try:
                saves.nth(i).click(timeout=2000)
                clicked += 1
            except Exception as exc:
                print(f"    (Save {i} refused the click: {type(exc).__name__})")
        page.wait_for_timeout(3000)
        print(f"    interacted: typed into {typed}, clicked {clicked} Save")
        check(len(seen["puts"]) == 0, f"no PUT was issued by any interaction ({len(seen['puts'])})")
        page.unroute("**/*")
        a_after, b_after = stored(pid_a), stored(pid_b)
        print(f"    stored A after: {a_after!r}")
        print(f"    stored B after: {b_after!r}")
        check(a_after == ALPHA, "A's stored instructions are byte-identical")
        check(b_after == BRAVO,
              "B's stored instructions are byte-identical - A's text never landed in B")
        page.close()
        browser.close()
    print(f"\nscreenshots: {SHOTS}")


if __name__ == "__main__":
    sys.exit(main())
