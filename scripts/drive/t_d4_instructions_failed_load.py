"""D-4, 2026-09-02 (day window) — drive the `InstructionsPage:9` suspicion.

N-11 read this statically last night and *deliberately filed no finding number*, because a static
read cannot say what the page renders. The read was: `InstructionsPage.tsx:9` seeds its editor with

    useEffect(() => { if (data) setContent(data.content) }, [data])

so a **failed** load leaves `content` at its `useState('')` initial value while `isLoading` has
already gone false — an empty textarea, a Save button whose only `disabled` condition is
`saveMutation.isPending`, and a PUT body of `{"content": ""}` that the route accepts as a legitimate
value (`hub/hub/api/v1/instructions.py` documents the empty string as legitimate *on purpose*).

That is the claim. This drives it in a real browser against the served bundle.

Three questions:

  A. baseline — with the load succeeding, does the editor show what is stored, and is Save enabled?
  B. failed load — with only the GET failing (network abort, and separately a 500), what does the
     page actually render, is Save enabled, and is any failure visible to the operator at all?
     Then click Save with the Hub reachable again and read the row back from the API.
  C. cross-project — the sharper variant a static read does not reach: if the component stays
     mounted while the selected project changes and the *new* project's load fails, `content` still
     holds the **previous project's** text, so Save writes A's instructions into B.

Run:  py -3.11 scripts/drive/t_d4_instructions_failed_load.py

Creates two fixture projects and deletes them. Refuses :8000. No agent turn is triggered, so
nothing binds a model and nothing spends tokens.
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
KEY = os.environ.get("AW_KEY", "aw_live_n0901aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
if HUB.endswith(":8000") or UI.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

DIR_A = os.path.join(os.path.expanduser("~"), "Documents", "drive-0902-d4a")
DIR_B = os.path.join(os.path.expanduser("~"), "Documents", "drive-0902-d4b")
SHOTS = os.path.join(tempfile.gettempdir(), "d4-shots")
os.makedirs(SHOTS, exist_ok=True)

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
    """What an operator sees. Nothing here reads the component's source for its predicates."""
    ta = page.locator("textarea[aria-label='Project instructions']")
    skel = page.locator("[aria-label='Loading instructions']")
    save = page.get_by_role("button", name="Save", exact=True)
    alerts = page.locator("[role='alert']")
    state = {
        "skeleton": skel.count() > 0,
        "textarea": ta.count() > 0,
        "value": ta.first.input_value() if ta.count() else None,
        "save_visible": save.count() > 0,
        "save_disabled": save.first.is_disabled() if save.count() else None,
        "alerts": [alerts.nth(i).inner_text().strip() for i in range(alerts.count())],
    }
    page.screenshot(path=os.path.join(SHOTS, f"d4-{label}.png"))
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
    code, pa = call("POST", "/projects/open", {"path": DIR_A.replace("\\", "/"), "name": "d4-alpha"})
    if code != 200:
        print(f"could not open fixture A [{code}] {pa}")
        return 2
    pid_a = pa["id"]
    code, pb = call("POST", "/projects/open", {"path": DIR_B.replace("\\", "/"), "name": "d4-bravo"})
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
            print(f"cleanup: DELETE {pid} [{dcode}]")
            check(dcode in (200, 204), f"fixture {pid} is deleted")
        ccode, rest = call("GET", "/projects")
        check(
            ccode == 200 and not any(p["id"] in (pid_a, pid_b) for p in rest),
            "and neither is listed any more",
        )

    print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


def drive(pid_a, pid_b):
    # ------------------------------------------------------------------ store real instructions
    code, _ = call("PUT", f"/projects/{pid_a}/project/instructions", {"content": ALPHA})
    check(code == 200, f"A's instructions are stored [{code}]")
    code, _ = call("PUT", f"/projects/{pid_b}/project/instructions", {"content": BRAVO})
    check(code == 200, f"B's instructions are stored [{code}]")
    check(stored(pid_a) == ALPHA, "and A reads back exactly what was stored")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # -------------------------------------------------------------- A, baseline
        print("\nA — baseline: the load succeeds")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid_a))
        page.goto(instructions_url(pid_a), wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        s = observe(page, "01-baseline")
        check(s["textarea"] and s["value"] == ALPHA, "the editor shows exactly what is stored")
        check(s["save_disabled"] is False, "Save is enabled")
        page.close()

        # -------------------------------------------------------------- B1, network abort
        print("\nB1 — the GET fails as a dropped connection (Hub down / restarting)")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid_a))
        seen = {"get": 0, "put": 0}

        def handler(route, request):
            if "/project/instructions" in request.url and request.method == "GET":
                seen["get"] += 1
                route.abort("connectionrefused")
            else:
                if "/project/instructions" in request.url:
                    seen["put"] += 1
                route.continue_()

        page.route("**/project/instructions", handler)
        page.goto(instructions_url(pid_a), wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        s = observe(page, "02-abort")
        check(seen["get"] >= 1, f"the instructions GET was attempted and failed ({seen['get']}x)")
        check(not s["skeleton"], "the skeleton is gone — the page is no longer 'loading'")
        check(s["textarea"] and s["value"] == "", "and an EMPTY textarea is what the operator sees")
        check(s["save_disabled"] is False, "with Save ENABLED over a failed load")
        check(
            not s["alerts"],
            "and nothing on screen tells the operator the load failed "
            "(recorded: no role=alert)",
        )
        body_text = page.locator("body").inner_text().lower()
        says = [w for w in ("error", "failed", "could not", "unable", "retry") if w in body_text]
        print(f"    failure words anywhere in the page text: {says or 'none'}")

        # the operator now types nothing and clicks Save — the Hub is reachable again
        before = stored(pid_a)
        page.get_by_role("button", name="Save", exact=True).first.click()
        page.wait_for_timeout(3000)
        after = stored(pid_a)
        page.screenshot(path=os.path.join(SHOTS, "d4-03-after-save.png"))
        saved_badge = page.locator("[role='status']").count() > 0
        print(f"    PUT attempts seen: {seen['put']}; 'Saved' badge: {saved_badge}")
        print(f"    stored before Save: {before!r}\n    stored after  Save: {after!r}")
        check(before == ALPHA, "A's instructions were intact immediately before the click")
        check(
            after == "",
            "ONE CLICK ON SAVE BLANKED THEM — the failed load's empty editor was written through",
        )
        page.close()

        # restore for the 500 case
        call("PUT", f"/projects/{pid_a}/project/instructions", {"content": ALPHA})
        check(stored(pid_a) == ALPHA, "A's instructions are restored for the next case")

        # -------------------------------------------------------------- B2, a 500
        print("\nB2 — the GET fails as a server error rather than a dropped connection")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid_a))

        def handler500(route, request):
            if "/project/instructions" in request.url and request.method == "GET":
                route.fulfill(status=500, body='{"detail":"boom"}', content_type="application/json")
            else:
                route.continue_()

        page.route("**/project/instructions", handler500)
        page.goto(instructions_url(pid_a), wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        s = observe(page, "04-500")
        check(
            s["textarea"] and s["value"] == "" and s["save_disabled"] is False,
            "a 500 lands identically: empty editor, Save enabled",
        )
        page.close()

        # -------------------------------------------------------------- C, cross-project
        print("\nC — the component stays mounted while the selected project changes")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(seed_script(pid_a))
        page.goto(instructions_url(pid_a), wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        s = observe(page, "05-c-on-a")
        check(s["value"] == ALPHA, "A's editor holds A's text")

        switch = page.get_by_role("button", name="Switch project")
        print(f"    'Switch project' controls on screen: {switch.count()}")
        if switch.count() == 0:
            print("    NOT DRIVEN: no in-page project switch is reachable from this page.")
            check(True, "C not driven — recorded, not asserted")
        else:
            # B's load fails; A's already succeeded and is in component state
            def handler_b(route, request):
                if (
                    "/project/instructions" in request.url
                    and request.method == "GET"
                    and pid_b in request.url
                ):
                    route.abort("connectionrefused")
                else:
                    route.continue_()

            page.route("**/project/instructions", handler_b)
            switch.first.click()
            page.wait_for_timeout(800)
            page.screenshot(path=os.path.join(SHOTS, "d4-06-switcher.png"))
            target = page.get_by_text("d4-bravo", exact=False)
            if target.count() == 0:
                print("    NOT DRIVEN: the switcher does not list the other fixture.")
                check(True, "C not driven — recorded, not asserted")
            else:
                target.first.click()
                page.wait_for_timeout(5000)
                s = observe(page, "07-c-on-b")
                on_instructions = s["textarea"]
                print(f"    still on the instructions page after the switch: {on_instructions}")
                if not on_instructions:
                    print("    NOT DRIVEN: switching leaves the instructions page (state resets).")
                    check(True, "C not driven — the switch unmounts the editor")
                else:
                    leaked = s["value"] == ALPHA
                    check(
                        not leaked,
                        "B's failed load does NOT leave A's text in B's editor "
                        f"(value={s['value']!r})",
                    )
                    if leaked:
                        page.get_by_role("button", name="Save", exact=True).first.click()
                        page.wait_for_timeout(3000)
                        print(f"    B stored after Save: {stored(pid_b)!r}")
        page.close()
        browser.close()

    print(f"\nscreenshots: {SHOTS}")


if __name__ == "__main__":
    sys.exit(main())
