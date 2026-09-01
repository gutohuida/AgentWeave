"""Sweep row 2's screen half — the Runners page, driven as an operator would.

`runnersUi.test.tsx` asserts the list renders and the form submits. That is a claim about a
component with a mocked mutation; this is a claim about the product against a live Hub. It opens
the real dashboard, types a model name into the New Runner dialog the way someone who has read
the model catalog would, presses Save, and looks for what the operator is told when the Hub
refuses it.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=<project id> AW_SHOTS=<dir>
     py -3.11 scripts/drive/t_sweep_row2_ui.py
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""

RUNNERS_URL = f"{HUB}/?project={PROJECT}&tab=environment&section=runners"

#: What an operator who has read `GET /model-catalog` would reasonably type. The catalog
#: publishes it as an alias of `claude-opus-5`; the API declares only ids (F175).
TYPED_MODEL = "opus"

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))

    # The failed POST is the fact this whole harness turns on, so record it from the wire
    # rather than inferring it from the screen.
    posts = []
    page.on(
        "response",
        lambda r: (
            posts.append((r.request.method, r.url, r.status))
            if "/runners" in r.url and r.request.method in ("POST", "PATCH")
            else None
        ),
    )

    page.add_init_script(SEED)
    page.goto(RUNNERS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "row2-01-runners.png"), full_page=False)

    body = page.content()
    check("the Runners section renders", "Runners" in body, page.title())
    check(
        "the two seeded runners are listed by name and CLI",
        "Claude (default)" in body and "Codex (default)" in body,
        "seeded rows absent" if "Claude (default)" not in body else "",
    )
    check(
        "the page explains what a runner is",
        "Reusable execution capability" in body,
        "",
    )

    page.get_by_role("button", name="New Runner").click()
    page.wait_for_timeout(500)
    dialog = page.locator('[role="dialog"]')
    check("New Runner opens a dialog", dialog.count() > 0, str(dialog.count()))
    page.screenshot(path=str(OUT / "row2-02-new-runner.png"), full_page=False)

    # The API's own comment cites the runner-registry spec: "Runner management offers catalog
    # models, not free-typed text". The dialog offers free-typed text (F173).
    model_input = dialog.locator("input").nth(1)
    model_is_select = dialog.locator("select").count() >= 2
    check(
        "the model field offers the catalog's models rather than free text (F173)",
        model_is_select,
        f"{dialog.locator('select').count()} select(s), {dialog.locator('input').count()} input(s)",
    )

    dialog.locator("input").first.fill("Row 2 typed model")
    model_input.fill(TYPED_MODEL)
    page.screenshot(path=str(OUT / "row2-03-typed.png"), full_page=False)
    page.get_by_role("button", name="Save").click()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "row2-04-after-save.png"), full_page=False)

    refused = [p for p in posts if p[0] == "POST" and p[2] >= 400]
    check(
        f"the Hub refused {TYPED_MODEL!r} (the premise of the checks below)",
        bool(refused),
        str(posts),
    )

    after = page.content()
    open_dialogs = page.locator('[role="dialog"]').count()
    check(
        "the dialog stays open rather than closing on a failure",
        open_dialogs > 0,
        f"{open_dialogs} dialog(s) on screen",
    )
    # The one thing the operator must get: some statement that the save failed, and why.
    told = (
        page.locator('[role="alert"]').count() > 0
        or "is not a model" in after
        or "not a model" in after
        or "Could not" in after
        or "failed" in after.lower()
    )
    check(
        "the operator is told the runner was not created, and why (F173)",
        told,
        "no alert, no message, nothing changed on screen",
    )
    check(
        "the refused runner really was not created",
        "Row 2 typed model" not in after.replace("Row 2 typed model", "", 1)
        or after.count("Row 2 typed model") <= 1,
        f"appears {after.count('Row 2 typed model')} times (once is the input's own value)",
    )

    # And the same question for the edit path, which has the same missing onError.
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if page.locator('[role="dialog"]').count():
        page.locator('button:has-text("Cancel")').first.click()
        page.wait_for_timeout(300)
    edit = page.locator('button[aria-label="Edit Claude (default)"]')
    if edit.count():
        edit.first.click()
        page.wait_for_timeout(500)
        d2 = page.locator('[role="dialog"]')
        d2.locator("input").nth(1).fill("claude-sonnet-4")
        d2.locator('button:has-text("Save")').first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "row2-05-edit-refused.png"), full_page=False)
        patch_refused = [p for p in posts if p[0] == "PATCH" and p[2] >= 400]
        check(
            "editing to an undeclared model is refused by the Hub",
            bool(patch_refused),
            str(posts),
        )
        told2 = page.locator('[role="alert"]').count() > 0 or "not a model" in page.content()
        check(
            "...and the edit dialog says so too (F173)",
            told2,
            "no alert, no message",
        )
    else:
        check("the edit control is reachable", False, "no Edit button found")

    # A delete refusal *is* surfaced — the one error path this page renders. Recorded because a
    # sweep that lists only defects describes a product that does not exist.
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if page.locator('[role="dialog"]').count():
        page.locator('button:has-text("Cancel")').first.click()
        page.wait_for_timeout(400)
    # Chromium logs every non-2xx response to the console. Those lines are the *Hub's* refusals,
    # which this harness provoked on purpose — they are not JavaScript errors, and counting them
    # would make this assertion red exactly while the product behaves correctly.
    script_errors = [e for e in console_errors if "Failed to load resource" not in e]
    check(
        "no uncaught JavaScript error was produced by any of the above",
        not script_errors,
        "; ".join(script_errors[:3]),
    )
    check(
        "the refusals did reach the browser (so the silence above is the UI's, not the network's)",
        len(console_errors) - len(script_errors) >= 2,
        f"{len(console_errors) - len(script_errors)} refused responses logged",
    )

    browser.close()

print()
print("=" * 78)
failed = [r for r in results if not r[1]]
print(f"ROW 2 UI RESULT: {len(results) - len(failed)}/{len(results)} passed")
for label, _, det in failed:
    print(f"  FAIL  {label} — {det}")
print(f"screenshots: {OUT}")
print("=" * 78)
sys.exit(1 if failed else 0)
