"""Section 2 of `runner-model-is-chosen-from-the-catalog`, driven — the model picker on screen.

`runnersUi.test.tsx` asserts the select's options against a *mocked* catalog. That is a claim about
a component. This is a claim about the product: a live Hub on :8011, its real `GET /model-catalog`,
a real project, and a real legacy runner row — driven through a browser.

**It points at the Vite dev server, not at the Hub's own port**, because `hub/hub/static/ui` is a
committed build artefact and section 2's code is not in it yet (the change builds the bundle once,
in section 5). Start the server first:

    cd hub/ui && AW_DEV_HUB=http://127.0.0.1:8011 npx vite --port 5174 --strictPort

Run:  py -3.11 scripts/drive/t_n3_runner_model_picker_ui.py

Creates its own fixture project and deletes it again, so it never reads AW_PROJECT and can never
touch a real one. Refuses :8000 outright.

The legacy-runner row cannot be reached through the API — every write path is gated by
`_reject_undeclared_model` — so, exactly as `t_r2_runner_update_semantics.py` does, this writes one
unrecognised model directly into the fixture runner's row. Only that fixture row is touched.
"""

import json
import os
import shutil
import sqlite3
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

CANDIDATE_DBS = [p for p in [os.environ.get("AW_DB")] if p] + [
    os.path.join(tempfile.gettempdir(), "aw0901n", "aw0901n.db"),
    os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"),
]

LEGACY_MODEL = "claude-3-legacy-9"
SHOTS = os.path.join(tempfile.gettempdir(), "n3-shots")
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
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def options_of(page, label):
    """The visible option labels of a <select>, in DOM order — what the operator can pick."""
    return page.eval_on_selector_all(
        f"select#{label} option", "els => els.map(e => e.textContent.trim())"
    )


wd = os.path.join(tempfile.gettempdir(), "n3-runner-picker-fixture")
shutil.rmtree(wd, ignore_errors=True)
status, project = call("POST", "/projects/create", {"path": wd, "name": "n3-runner-picker"})
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
    print(f"catalog: claude={len(declared['claude'])} models, codex={len(declared['codex'])}\n")

    # A runner with a declared model, to prove clearing; and a runner the catalog cannot explain.
    good_id, good_label = declared["claude"][0]
    status, keep = call(
        "POST",
        f"/projects/{PID}/runners",
        {"name": "N3 Declared", "cli": "claude", "model": good_id},
    )
    assert status == 201, (status, keep)
    KEEP_ID = keep["id"]

    status, legacy = call(
        "POST", f"/projects/{PID}/runners", {"name": "N3 Legacy", "cli": "claude", "model": good_id}
    )
    assert status == 201, (status, legacy)
    LEGACY_ID = legacy["id"]

    db = next((p for p in CANDIDATE_DBS if os.path.exists(p)), None)
    if db is None:
        print("could not find the drive Hub's database — set AW_DB. Aborting.")
        sys.exit(1)
    con = sqlite3.connect(db)
    con.execute("UPDATE runners SET model = ? WHERE id = ?", (LEGACY_MODEL, LEGACY_ID))
    con.commit()
    con.close()
    status, legacy = call("GET", f"/projects/{PID}/runners/{LEGACY_ID}")
    check(
        legacy["model"] == LEGACY_MODEL and legacy["model_unrecognised"] is True,
        f"the API flags the legacy runner: model={legacy['model']!r} "
        f"model_unrecognised={legacy['model_unrecognised']}",
    )

    seed = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": ""}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PID)});
"""
    url = f"{UI}/?project={PID}&tab=environment&section=runners"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
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
        page.screenshot(path=os.path.join(SHOTS, "n3-01-list.png"))

        # ---------------------------------------------------------------- 2.6
        print("\n2.6 — the list marks a runner the catalog cannot explain")
        body = page.content()
        check(LEGACY_MODEL in body, "the legacy runner's model is rendered in the list")
        row = page.locator("div.row-group", has_text="N3 Legacy").first
        check(
            row.get_by_text("Unrecognised").count() == 1,
            "the legacy row carries an Unrecognised mark",
        )
        declared_row = page.locator("div.row-group", has_text="N3 Declared").first
        check(
            declared_row.get_by_text("Unrecognised").count() == 0,
            "the runner with a declared model carries no mark",
        )

        # ---------------------------------------------------------------- 2.2, create
        print("\n2.2 — creating a runner offers the catalog, and nothing to type into")
        page.get_by_role("button", name="New Runner").click()
        page.wait_for_selector("select#runner-model")
        page.screenshot(path=os.path.join(SHOTS, "n3-02-new.png"))
        opts = options_of(page, "runner-model")
        check(
            opts == ["Provider default"] + [label for _, label in declared["claude"]],
            f"the select offers Provider default plus claude's declared models: {opts}",
        )
        check(
            page.locator("input[placeholder='e.g. claude-sonnet-5']").count() == 0,
            "there is no free-typed model field on screen",
        )
        check(
            page.eval_on_selector("select#runner-model", "e => e.value") == "",
            "a new runner starts unset",
        )

        # ---------------------------------------------------------------- 2.4
        print("\n2.4 — changing the CLI resets to UNSET, not to the new provider's default")
        page.select_option("select#runner-model", declared["claude"][0][0])
        check(
            page.eval_on_selector("select#runner-model", "e => e.value")
            == declared["claude"][0][0],
            "a model can be selected",
        )
        page.select_option("select#runner-cli", "codex")
        page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(SHOTS, "n3-03-cli-changed.png"))
        after = page.eval_on_selector("select#runner-model", "e => e.value")
        codex_default = next((m for m, _ in declared["codex"] if m), None)
        check(after == "", f"the model reset to unset, not to a codex model (value={after!r})")
        check(
            after != codex_default,
            "specifically NOT codex's own default model — a runner must not have one chosen for it",
        )
        opts = options_of(page, "runner-model")
        check(
            opts == ["Provider default"] + [label for _, label in declared["codex"]],
            f"the option list followed the CLI: {opts}",
        )
        page.get_by_role("button", name="Cancel").click()

        # ---------------------------------------------------------------- 2.2, legacy edit
        print("\n2.2 — editing a legacy runner keeps its model offered, selected and marked")
        page.get_by_role("button", name="Edit N3 Legacy").click()
        page.wait_for_selector("select#runner-model")
        page.screenshot(path=os.path.join(SHOTS, "n3-04-legacy-edit.png"))
        check(
            page.eval_on_selector("select#runner-model", "e => e.value") == LEGACY_MODEL,
            "the stored unrecognised model is the selected option",
        )
        opts = options_of(page, "runner-model")
        check(
            opts
            == ["Provider default", f"{LEGACY_MODEL} — unrecognised"]
            + [label for _, label in declared["claude"]],
            f"it is offered and labelled unrecognised: {opts}",
        )

        writes.clear()
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(1500)
        sent = [w for w in writes if w[0] == "PATCH"]
        check(len(sent) == 1, f"Save sent exactly one PATCH ({len(sent)})")
        if sent:
            payload = json.loads(sent[0][2] or "{}")
            check(
                payload.get("model") == LEGACY_MODEL,
                f"the PATCH re-submits the stored model: {payload}",
            )
        status, after_save = call("GET", f"/projects/{PID}/runners/{LEGACY_ID}")
        check(
            status == 200 and after_save["model"] == LEGACY_MODEL,
            f"the Hub accepted it and the runner kept its model ({status}, "
            f"{after_save.get('model')!r}) — section 1's repair, reached from the screen",
        )

        # ---------------------------------------------------------------- 2.3
        print("\n2.3 — moving a runner back to Provider default clears it")
        page.get_by_role("button", name="Edit N3 Declared").click()
        page.wait_for_selector("select#runner-model")
        check(
            page.eval_on_selector("select#runner-model", "e => e.value") == good_id,
            f"the declared runner opens on its own model ({good_label})",
        )
        writes.clear()
        page.select_option("select#runner-model", "")
        page.get_by_role("button", name="Save").click()
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, "n3-05-cleared.png"))
        sent = [w for w in writes if w[0] == "PATCH"]
        payload = json.loads(sent[0][2] or "{}") if sent else {}
        check(
            "model" in payload and payload["model"] is None,
            f"the PATCH carries an explicit null, not an omitted field: {payload}",
        )
        status, cleared = call("GET", f"/projects/{PID}/runners/{KEEP_ID}")
        check(
            status == 200 and cleared["model"] is None,
            f"GET /runners/{{id}} now reports model=null ({cleared.get('model')!r})",
        )
        check(
            page.locator("div.row-group", has_text="N3 Declared").first.get_by_text(good_id).count()
            == 0,
            "the list row no longer shows a model for it",
        )

        check(not errors, f"no console errors ({errors[:3]})")

        # ---------------------------------------------------------------- 2.5
        # An empty select would read as "this provider declares no models" rather than "we do not
        # know yet". Induced rather than argued: the catalog request is failed at the wire.
        print("\n2.5 — while the catalog is unavailable the select says so, and Save still works")
        page.route("**/api/v1/model-catalog", lambda route: route.abort())
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        page.get_by_role("button", name="New Runner").click()
        page.wait_for_selector("select#runner-model")
        page.screenshot(path=os.path.join(SHOTS, "n3-06-no-catalog.png"))
        check(
            page.eval_on_selector("select#runner-model", "e => e.disabled") is True,
            "the model select is disabled",
        )
        check(
            options_of(page, "runner-model") == ["Provider default"],
            f"it offers only the unset choice: {options_of(page, 'runner-model')}",
        )
        check(
            page.get_by_text("The model catalog is unavailable").count() == 1,
            "the dialog says why, rather than presenting an empty list as fact",
        )
        page.fill("input#runner-name", "N3 No Catalog")
        check(
            page.get_by_role("button", name="Save").is_enabled(),
            "Save stays enabled — a runner with no model is a valid runner",
        )
        page.get_by_role("button", name="Cancel").click()

        browser.close()

finally:
    call("DELETE", f"/projects/{PID}")
    status, projects = call("GET", "/projects")
    print(
        f"\nfixture deleted; project count now {len(projects) if isinstance(projects, list) else projects}"
    )
    shutil.rmtree(wd, ignore_errors=True)

print(f"\nshots in {SHOTS}")
print(f"{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
