"""Sweep row 1's screen half — the project dialog, driven, not unit-tested.

`projectManagerIdentityConflict.test.tsx` asserts the remedy button exists. That is a claim about a
component; this is a claim about the product. It opens the real dashboard against the real Hub,
types the path of a directory carrying **another** project's marker, and looks for the sentence and
the button the operator would need to get past it.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=<any project> AW_CONFLICT_DIR=<dir> AW_SHOTS=<dir>
     py -3.11 scripts/drive/t_sweep_row1_ui.py
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
CONFLICT_DIR = os.environ["AW_CONFLICT_DIR"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""

results = []


def check(label, ok, detail=""):
    results.append((label, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(SEED)
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "row1-01-dashboard.png"), full_page=False)

    check(
        "the dashboard renders past the setup modal",
        "Add project" in page.content() or page.locator("text=Projects").count() > 0,
        page.title(),
    )

    # Reach the add-project dialog the way the rail offers it.
    opened = False
    for sel in [
        'button[aria-label="Add project"]',
        'button:has-text("Add project")',
        "text=Add project",
    ]:
        loc = page.locator(sel)
        if loc.count():
            loc.first.click()
            opened = True
            break
    if not opened:
        # The rail may hide it behind the project switcher.
        for sel in [
            'button[aria-label="Switch project"]',
            'button[aria-label="Projects"]',
            '[data-testid="project-switcher"]',
        ]:
            loc = page.locator(sel)
            if loc.count():
                loc.first.click()
                page.wait_for_timeout(400)
                if page.locator('button:has-text("Add project")').count():
                    page.locator('button:has-text("Add project")').first.click()
                    opened = True
                break
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / "row1-02-dialog.png"), full_page=False)
    check(
        "the add-project dialog is reachable from the dashboard chrome",
        opened and page.locator('[role="dialog"]').count() > 0,
    )

    if opened and page.locator('[role="dialog"]').count():
        dlg = page.locator('[role="dialog"]').first
        dlg.locator("input").first.fill(CONFLICT_DIR)
        page.wait_for_timeout(200)
        # Submit — the primary action in the dialog's footer.
        for sel in [
            'button:has-text("Add project")',
            'button:has-text("Open")',
            'button:has-text("Add")',
        ]:
            b = dlg.locator(sel)
            if b.count():
                b.last.click()
                break
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "row1-03-conflict.png"), full_page=False)
        body = dlg.inner_text()
        print("--- dialog text after the conflicting submit ---")
        print(body)
        check(
            "the identity-conflict refusal reaches the screen",
            "copied" in body.lower() or "conflict" in body.lower() or "already" in body.lower(),
            body[:200],
        )
        remedy = [
            t
            for t in (dlg.locator("button").all_inner_texts())
            if "new" in t.lower()
            and ("register" in t.lower() or "copy" in t.lower() or "separate" in t.lower())
        ]
        check(
            "the screen offers the remedy (register the copy as new), not just the sentence",
            bool(remedy),
            f"buttons: {dlg.locator('button').all_inner_texts()}",
        )

        # F171. The remedy is right and the explanation under it is not: this code is raised from
        # four distinct situations, and the copy-in-the-same-database one that this script drives
        # is not "another Hub instance on this machine" at all.
        check(
            "F171: the conflict explanation does not assert a cause it cannot know",
            "different agentweave database" not in body.lower(),
            "the fixed copy claims another database and another Hub instance; the server said "
            "'marker was copied while the registered directory is still available', which is the "
            "same database",
        )

    # The deliberate 409 is fetched by the app and logged by the browser; it is the refusal under
    # test, not a defect. Anything else is.
    real = [
        e
        for e in errors
        if "favicon" not in e.lower() and "409" not in e and "Failed to load resource" not in e
    ]
    check("no console errors while driving the dialog", not real, "; ".join(real[:3]))
    browser.close()

print()
bad = [r for r in results if not r[1]]
print(f"ROW 1 (screen): {len(results) - len(bad)}/{len(results)} passed")
for label, _, detail in bad:
    print("  FAIL:", label, "—", detail)
print("shots in", OUT)
