"""Sweep row 4's screen half — the charter surfaces, driven as an operator would.

The API half of row 4 measures what the Hub answers. This asks the two questions it cannot:
whether the refusals the charter routes produce reach the operator at all, and whether the
`agent-charter` spec's own UI requirements (`openspec/specs/agent-charter/spec.md:75-95`) are
actually satisfied by the shipped screen — read without an editor, two open at once, collapsed by
default.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=<project id> AW_AGENT=<an agent with a charter bound>
     AW_SHOTS=<dir> py -3.11 scripts/drive/t_sweep_row4_ui.py

Every assertion about text an operator must READ goes through `page.inner_text("body")`, never
`page.content()`. Row 3 lost a real defect to a green row because `"bind"` matched `tabindex` in
the markup.

The Hub on :8011 serves `hub/hub/static/ui`, a committed build artefact — a UI source change does
not appear here until it is rebuilt. Nothing in this iteration changed UI source, so what this
captures is the shipped bundle.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
PROJECT = os.environ["AW_PROJECT"]
AGENT = os.environ["AW_AGENT"]
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""

CHARTERS_URL = f"{HUB}/?project={PROJECT}&tab=environment&section=charters"
A = f"/projects/{PROJECT}"

results = []


def check(label, ok, detail=""):
    """`detail` is the evidence, printed either way — a passing row's evidence is what a later
    reader needs to know the assertion was about something real."""
    results.append((label, bool(ok), detail))
    shown = detail if len(detail) <= 300 else detail[:300] + f"... ({len(detail)} chars)"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {shown}" if shown else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    urls = []
    page.on("request", lambda r: urls.append(r.url))
    page.add_init_script(SEED)

    # ------------------------------------------------------------ 1. the charter screen exists
    page.goto(CHARTERS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "row4-01-charters.png"), full_page=False)
    text = page.inner_text("body")
    check("a charter screen is reachable by deep link", "Charters" in text, page.title())
    check(
        "it lists the seeded starters by name",
        "Tech Lead" in text and "Code Reviewer" in text,
        text[:200].replace("\n", " / "),
    )
    check(
        "the screen fetched the charter list", any("/charters" in u for u in urls), str(len(urls))
    )

    # agent-charter:88-95 — collapsed by default, so the list of names is readable without
    # scrolling past full documents.
    longest = max((c["content"] for c in api("GET", f"{A}/charters")[1]), key=len, default="")
    check(
        "every charter is collapsed on first open — no full document is on screen",
        longest[:120] not in text,
        f"longest starter is {len(longest)} chars",
    )

    # ------------------------------------------------------------ 2. read without an editor
    expanders = page.locator("button[aria-expanded]")
    check("each charter has a disclosure control", expanders.count() >= 9, str(expanders.count()))
    if expanders.count() >= 2:
        expanders.nth(0).click()
        page.wait_for_timeout(500)
        after_one = page.inner_text("body")
        page.screenshot(path=str(OUT / "row4-02-one-expanded.png"), full_page=False)
        check(
            "expanding one shows its full content",
            len(after_one) > len(text) + 500,
            f"{len(text)} -> {len(after_one)} chars of visible text",
        )
        # agent-charter:79-81 — reading must not open a surface that can modify.
        n_dialog = page.locator('[role="dialog"]').count()
        n_textarea = page.locator("textarea:visible").count()
        check(
            "reading opens no editor — no dialog, no textarea, no save action",
            n_dialog == 0 and n_textarea == 0,
            f"{n_dialog} dialog(s), {n_textarea} textarea(s)",
        )
        # agent-charter:83-84 — two open at once.
        expanders.nth(1).click()
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "row4-03-two-expanded.png"), full_page=False)
        open_now = page.locator('button[aria-expanded="true"]').count()
        check(
            "opening a second charter does not close the first",
            open_now >= 2,
            f"{open_now} expanded",
        )
        expanders.nth(0).click()
        expanders.nth(1).click()
        page.wait_for_timeout(400)

    # ------------------------------------------------------------ 3. the delete refusal
    #
    # `charters.py:99-103` refuses a bound charter with a 409 naming the agent and the repair.
    # This is the one charter refusal the page has an error path for (`ChartersPage.tsx:77-87`),
    # so it should reach the operator — which makes it the control for section 4 below.
    code, bound_ch = api("GET", f"{A}/agents/agent-context?agent={AGENT}")
    bound_name = bound_ch.get("charter_name") if code == 200 else None
    check(f"the fixture agent {AGENT} has a charter bound", bool(bound_name), str(bound_name))
    if bound_name:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        btn = page.locator(f'button[aria-label="Delete {bound_name}"]')
        check("the bound charter offers a delete control", btn.count() == 1, str(btn.count()))
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(OUT / "row4-04-delete-refused.png"), full_page=False)
            after = page.inner_text("body")
            check(
                "the delete refusal reaches the operator on screen",
                "bound to agent" in after or "Unbind" in after,
                after[:300].replace("\n", " / "),
            )
            check(
                "and it names the agent holding it and the repair",
                AGENT in after and "nbind" in after,
                [ln for ln in after.split("\n") if "harter" in ln and "bound" in ln][:2],
            )

    # ------------------------------------------------------------ 4. an UNBOUND delete
    #
    # Destructive, immediate, and not asked about. The API has no soft delete and no undo, and a
    # charter is the authored text an operator wrote — the one charter record that cannot be
    # re-seeded. This asserts the confirmation the screen should ask for.
    code, victim = api(
        "POST", f"{A}/charters", {"name": "row4-ui-victim", "content": "Authored by hand. " * 40}
    )
    victim_id = victim.get("id") if code == 201 else None
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    vbtn = page.locator('button[aria-label="Delete row4-ui-victim"]')
    check("the authored charter is on the screen", vbtn.count() == 1, str(vbtn.count()))
    if vbtn.count():
        vbtn.first.click()
        page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT / "row4-05-deleted-no-confirm.png"), full_page=False)
        confirmed = page.locator('[role="dialog"], [role="alertdialog"]').count() > 0
        code, still = api("GET", f"{A}/charters/{victim_id}")
        check(
            "deleting an authored charter asks before destroying it",
            confirmed or still == 200,
            f"no dialog appeared and GET returned {still} — gone in one click, no undo",
        )
        if still == 200:
            api("DELETE", f"{A}/charters/{victim_id}")

    # ------------------------------------------------------------ 5. a refused EDIT
    #
    # F173's shape, asked of this screen. `ChartersPage.tsx:196-204` passes only `onSuccess` to
    # both the create and the update mutation — there is no `onError` on either, and the form
    # holds no error state. The API refuses a name past 256 characters with a 422. What does the
    # operator see?
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    new_btn = page.get_by_role("button", name="New Charter")
    check("the screen offers a way to author a charter", new_btn.count() > 0, str(new_btn.count()))
    if new_btn.count():
        new_btn.first.click()
        page.wait_for_timeout(800)
        dialog = page.locator('[role="dialog"]')
        check("it opens the charter form", dialog.count() > 0, str(dialog.count()))
        before_count = len(api("GET", f"{A}/charters")[1])
        dialog.locator('input[aria-label="Charter name"]').fill("N" * 300)
        dialog.locator('textarea[aria-label="Charter content"]').fill("content")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "row4-06-overlong-typed.png"), full_page=False)
        save = dialog.locator('button:has-text("Save")')
        check(
            "Save is reachable with a name the API will refuse", save.count() > 0, str(save.count())
        )
        if save.count():
            save.first.click()
            page.wait_for_timeout(2500)
            page.screenshot(path=str(OUT / "row4-07-refusal-swallowed.png"), full_page=False)
            after = page.inner_text("body")
            after_count = len(api("GET", f"{A}/charters")[1])
            check(
                "the charter was not created (the API refused it)",
                after_count == before_count,
                f"{before_count} -> {after_count}",
            )
            check(
                "the operator is TOLD the charter was refused, and why",
                "256" in after or "refus" in after.lower() or "could not" in after.lower(),
                (
                    "form still open, nothing said"
                    if page.locator('[role="dialog"]').count()
                    else "dialog gone, nothing said, charter not created"
                ),
            )
            n_after = page.locator('[role="dialog"]').count()
            check(
                "the form stays open so the typed content is not lost",
                n_after > 0,
                f"{n_after} dialog(s) after the refusal",
            )

    # ------------------------------------------------------------ 6. duplicate names on screen
    #
    # The API half proved the surface has no uniqueness rule. This asks what that looks like at
    # the only place a charter is CHOSEN: the picker in agent settings, which renders the name
    # and nothing else (`AgentSettingsControls.tsx:280-284`).
    code, dup = api(
        "POST", f"{A}/charters", {"name": "Code Reviewer", "content": "A second one, by hand."}
    )
    dup_id = dup.get("id") if code == 201 else None
    page.goto(
        f"{HUB}/?project={PROJECT}&agent={AGENT}&settings=charter", wait_until="domcontentloaded"
    )
    page.wait_for_timeout(3500)
    page.screenshot(path=str(OUT / "row4-08-picker.png"), full_page=False)
    picker = page.locator(f'select[aria-label="Charter for {AGENT}"]')
    check("the agent's charter picker is on screen", picker.count() == 1, str(picker.count()))
    if picker.count():
        labels = picker.first.locator("option").all_text_contents()
        cr = [x for x in labels if x.strip() == "Code Reviewer"]
        check(
            "the picker distinguishes two charters that share a name",
            len(cr) <= 1,
            f"{len(cr)} options read exactly 'Code Reviewer': {labels}",
        )
    if dup_id:
        api("DELETE", f"{A}/charters/{dup_id}")

    # This harness deliberately provokes a 409 and a 422, and the browser logs each as a
    # "Failed to load resource" console error. Those are the product working. What this asserts
    # is that nothing ELSE went wrong on the way.
    unexpected = [e for e in console_errors if "Failed to load resource" not in e]
    check(
        "no console error beyond the 4xx this harness deliberately provoked",
        not unexpected,
        f"{len(console_errors)} total, {len(unexpected)} unexpected: {unexpected[:3]}",
    )
    browser.close()

print()
print("=" * 78)
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} PASS   screenshots in {OUT}")
for label, ok, det in results:
    if not ok:
        print(f"  FAIL  {label}" + (f" — {str(det)[:200]}" if det else ""))
print("=" * 78)
sys.exit(0 if passed == len(results) else 1)
