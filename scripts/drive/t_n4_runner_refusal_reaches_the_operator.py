"""Section 3 of `runner-model-is-chosen-from-the-catalog`, driven — F173's refusal on screen.

F173: the Hub refuses a runner and the operator is told nothing. `runnersUi.test.tsx` now asserts
the alert against a *mocked* mutation, which is a claim about a component. This is a claim about
the product: a live Hub on :8011, its real validators, real 4xx bodies, driven through a browser.

**It points at the Vite dev server, not at the Hub's own port**, because `hub/hub/static/ui` is a
committed build artefact and sections 2-3 are not in it yet (the change builds the bundle once, in
section 5, and re-drives this there). Start the server first:

    cd hub/ui && AW_DEV_HUB=http://127.0.0.1:8011 npx vite --port 5174 --strictPort

Run:  py -3.11 scripts/drive/t_n4_runner_refusal_reaches_the_operator.py

Creates its own fixture project and deletes it again, so it never reads AW_PROJECT and can never
touch a real one. Refuses :8000 outright.

Three refusals are driven, and they are deliberately different shapes:

* a **Pydantic 422** whose `detail` is a *list* of error objects — reachable by typing, and the
  exact body the deleted `extractErrorDetail` returned raw (an array of objects, which React
  cannot render at all). This is task 3.1's substance, not just its diff.
* the **model refusal itself**, `'opus' is not a model 'claude' declares`. Section 2 removed the
  free-text field, so an operator can no longer *produce* this from the screen — task 5.1 says so
  and calls the reproduction inverted. To read the sentence anyway the request body is rewritten
  on the wire before it leaves the browser; the 400 and its words are the Hub's own.
* a **409 with a string detail** from deleting a bound runner, which is task 3.5's existing alert
  still working after the helper swap.
"""

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
UI = os.environ.get("AW_UI", "http://127.0.0.1:5174")
KEY = os.environ.get("AW_KEY", "aw_live_n0901aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
if HUB.endswith(":8000") or UI.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

SHOTS = os.path.join(tempfile.gettempdir(), "n4-shots")
os.makedirs(SHOTS, exist_ok=True)

PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def call(method, path, body=None):
    req = urllib.request.Request(
        HUB + "/api/v1" + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def alert_text(page):
    """What the operator actually reads, or None. `.first` because the page-level delete alert
    and the dialog's own alert share the role — which one is on screen is the point of each
    check below, so the count is asserted separately where it matters."""
    box = page.get_by_role("alert")
    return box.first.inner_text().strip() if box.count() else None


wd = os.path.join(tempfile.gettempdir(), "n4-runner-refusal-fixture")
shutil.rmtree(wd, ignore_errors=True)
status, project = call("POST", "/projects/create", {"path": wd, "name": "n4-runner-refusal"})
if status != 201:
    print(f"could not create the fixture project: {status} {project}")
    sys.exit(1)
PID = project["id"]
print(f"fixture project {PID} at {wd}")

try:
    status, catalog = call("GET", "/model-catalog")
    declared = {
        p["provider"]: [(m["id"], m["label"]) for m in p["models"]] for p in catalog["providers"]
    }
    good_id, good_label = declared["claude"][0]

    # A runner nothing is bound to (deletable), and one an agent holds (a real 409 on delete).
    status, free = call(
        "POST", f"/projects/{PID}/runners", {"name": "N4 Free", "cli": "claude", "model": good_id}
    )
    assert status == 201, (status, free)
    status, held = call(
        "POST", f"/projects/{PID}/runners", {"name": "N4 Held", "cli": "claude", "model": good_id}
    )
    assert status == 201, (status, held)
    HELD_ID = held["id"]
    status, agent = call(
        "POST", f"/projects/{PID}/agents", {"name": "n4-holder", "runner_id": HELD_ID}
    )
    check(status == 201, f"an agent holds N4 Held, so deleting it is a real refusal ({status})")

    # The two refusals, confirmed at the API before any of them is looked for on screen — so a
    # green run cannot mean "the Hub stopped refusing".
    status, body = call("DELETE", f"/projects/{PID}/runners/{HELD_ID}")
    check(
        status == 409 and "n4-holder" in str(body.get("detail")),
        f"the Hub refuses to delete a bound runner: {status} {body}",
    )
    MODEL_REFUSAL = "'opus' is not a model 'claude' declares"
    status, body = call(
        "POST", f"/projects/{PID}/runners", {"name": "N4 Bad", "cli": "claude", "model": "opus"}
    )
    check(
        status == 400 and body.get("detail") == MODEL_REFUSAL,
        f"the Hub still refuses an undeclared model with F173's own sentence: {status} {body}",
    )

    seed = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PID)});
"""
    url = f"{UI}/?project={PID}&tab=environment&section=runners"
    long_name = "N" * 300

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []

        def note_console(m):
            # Chromium logs "Failed to load resource ..." for every 4xx, and this drive provokes
            # four on purpose. Those are the subject, not a symptom; anything else is real.
            if m.type == "error" and "Failed to load resource" not in m.text:
                errors.append(m.text)

        page.on("console", note_console)
        page.on("pageerror", lambda e: errors.append(str(e)))
        writes = []
        page.on(
            "request",
            lambda r: (
                writes.append((r.method, r.url, r.post_data))
                if "/runners" in r.url and r.method in ("POST", "PATCH")
                else None
            ),
        )
        page.add_init_script(seed)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.screenshot(path=os.path.join(SHOTS, "n4-01-list.png"))
        check(alert_text(page) is None, "the page opens with no alert on it")

        # ------------------------------------------------- 3.1, 3.2, 3.3 — the Pydantic body
        print("\n3.1/3.2/3.3 — a refused create is read inside the dialog, which keeps its values")
        page.get_by_role("button", name="New Runner").click()
        page.wait_for_selector("select#runner-model")
        page.fill("input#runner-name", long_name)
        page.select_option("select#runner-model", good_id)
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, "n4-02-refused.png"))

        said = alert_text(page)
        check(said is not None, f"the operator is told something at all (F173 proper): {said!r}")
        check(
            said is not None and "256" in said and "[" not in said,
            f"and it is the refusal's sentence, not the raw array the old helper returned: {said!r}",
        )
        check(
            page.locator("div[role='dialog']").count() == 1,
            "the dialog is still open",
        )
        check(
            page.eval_on_selector("input#runner-name", "e => e.value") == long_name,
            "the entered name survived the refusal",
        )
        check(
            page.eval_on_selector("select#runner-model", "e => e.value") == good_id,
            f"so did the chosen model ({good_label})",
        )
        check(
            page.locator("div[role='dialog'] div[role='alert']").count() == 1,
            "the alert is inside the dialog, beside the values it refused",
        )

        # ------------------------------------------------- 3.4 — the reset
        print("\n3.4 — Cancel, then reopen: no stale refusal")
        page.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(300)
        check(alert_text(page) is None, "cancelling takes the refusal away with the dialog")
        page.get_by_role("button", name="New Runner").click()
        page.wait_for_selector("select#runner-model")
        page.screenshot(path=os.path.join(SHOTS, "n4-03-reopened.png"))
        check(
            alert_text(page) is None,
            "a reopened New Runner shows no refusal before anything is submitted",
        )
        check(
            page.eval_on_selector("input#runner-name", "e => e.value") == "",
            "and it opens empty",
        )
        page.get_by_role("button", name="Cancel").click()

        # ------------------------------------------------- 5.1 inverted — the model refusal
        print("\n5.1 (inverted) — the model refusal cannot be produced from the screen any more")
        page.get_by_role("button", name="New Runner").click()
        page.wait_for_selector("select#runner-model")
        check(
            page.locator("input[placeholder='e.g. claude-sonnet-5']").count() == 0,
            "there is no field to type 'opus' into",
        )
        offered = page.eval_on_selector_all(
            "select#runner-model option", "els => els.map(e => e.value)"
        )
        check(
            "opus" not in offered and set(offered) <= {""} | {m for m, _ in declared["claude"]},
            f"and every offered value is a declared model or the unset one: {offered}",
        )

        # The Hub's own 400, reached by rewriting the body on the wire — the request is tampered
        # with, the refusal and its words are not.
        print("      so the sentence is reached by rewriting the request, not by typing it")

        def inject_bad_model(route):
            body = json.loads(route.request.post_data or "{}")
            body["model"] = "opus"
            route.continue_(post_data=json.dumps(body))

        page.route("**/api/v1/projects/*/runners", inject_bad_model)
        page.fill("input#runner-name", "N4 Opus")
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, "n4-04-model-refusal.png"))
        said = alert_text(page)
        check(
            said == MODEL_REFUSAL,
            f"the operator reads F173's exact sentence: {said!r}",
        )
        page.unroute("**/api/v1/projects/*/runners")
        page.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(300)

        # ------------------------------------------------- 3.4 on the edit path too
        print("\n3.4 — the edit dialog resets the same way")
        page.get_by_role("button", name="Edit N4 Free").click()
        page.wait_for_selector("select#runner-model")
        check(alert_text(page) is None, "Edit opens clean after a refused create")
        page.fill("input#runner-name", long_name)
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(1500)
        said = alert_text(page)
        check(
            said is not None and "256" in said,
            f"a refused *edit* is read too, not only a refused create: {said!r}",
        )
        page.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="Edit N4 Free").click()
        page.wait_for_selector("select#runner-model")
        check(alert_text(page) is None, "and reopening Edit shows no stale refusal")
        page.get_by_role("button", name="Cancel").click()
        page.wait_for_timeout(300)

        # ------------------------------------------------- 3.5 — the delete alert still reads
        print("\n3.5 — the delete refusal still names the agents holding the runner")
        page.get_by_role("button", name="Delete N4 Held").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, "n4-05-delete-refused.png"))
        said = alert_text(page)
        check(
            said is not None and "n4-holder" in said,
            f"the 409's sentence survived the swap to readableApiError: {said!r}",
        )
        check(
            said != "Could not delete runner",
            "it is the Hub's words, not the fallback",
        )
        status, still_there = call("GET", f"/projects/{PID}/runners/{HELD_ID}")
        check(status == 200, f"and the runner is still there ({status})")

        check(not errors, f"no console errors beyond the refusals themselves ({errors[:3]})")

        # Nothing this drive did should have created a runner.
        status, runners = call("GET", f"/projects/{PID}/runners")
        names = sorted(r["name"] for r in runners)
        check(
            all(not n.startswith("NNN") and n != "N4 Opus" for n in names),
            f"no refused runner was created behind the alert: {names}",
        )

        browser.close()

finally:
    status, body = call("DELETE", f"/projects/{PID}")
    print(f"\nfixture project deleted: {status}")
    status, projects = call("GET", "/projects")
    print(f"projects now: {len(projects) if isinstance(projects, list) else projects}")
    shutil.rmtree(wd, ignore_errors=True)

print(f"\n{len(PASS)} passed / {len(FAIL)} failed   (screenshots in {SHOTS})")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
