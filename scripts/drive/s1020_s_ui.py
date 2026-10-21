"""2026-10-20 sweep, Spec documents x Corpus & folding in a real browser: Approve -> the gaps ->
Approve anyway; the journey nav on a document a real exploring turn walked (custom step); the
answered cannot-satisfy report; the corpus strip (Rebuild index, Adopt an untracked file); a
retired capability; the delete dialog's focus and Escape.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1020_s_ui.py <project-id> <hub-url> <project-dir> <walked-doc> <retired-cap>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from s1019_spec_lib import payload, request  # noqa: E402
from uiharness import Judge  # noqa: E402

P, HUB, DIR, WALKED, RETIRED = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3]), sys.argv[4], sys.argv[5]
SFX = time.strftime("%H%M%S")
BASE = f"/projects/{P}/project"


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def open_doc(j, path):
    page = j.page(P, mode="light", query=f"tab=spec&document={path}")
    page.wait_for_timeout(5000)
    return page


# fixtures: a proposed change to approve on screen, an exploring one to delete, an untracked file
PROP = f"spec/changes/ui-approve-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": PROP, "title": "UI approve " + SFX})
request("PUT", f"{BASE}/documents/{PROP}/content", {"document": payload("UI approve " + SFX, SFX, keys=("one",))})
print("propose:", request("POST", f"{BASE}/documents/propose?path={PROP}")[1].get("phase"))
DEL = f"spec/changes/ui-delete-{SFX}/spec.json"
request("POST", f"{BASE}/documents", {"path": DEL, "title": "UI delete " + SFX})
UNTR = DIR / f"spec/changes/ui-untracked-{SFX}/spec.json"
UNTR.parent.mkdir(parents=True, exist_ok=True)
UNTR.write_text(json.dumps(payload("UI untracked " + SFX, SFX + "u", keys=("one",))), encoding="utf-8")

with Judge("s1020-spec", hub=HUB, key=e2e.key()) as j:
    # --- Approve -> gaps -> Approve anyway ---
    page = open_doc(j, PROP)
    bar = page.get_by_test_id("spec-phase")
    print("phase bar (proposed):", txt(bar)[:300])
    page.get_by_role("button", name="Approve", exact=True).first.click()
    page.wait_for_timeout(2500)
    warn = page.get_by_test_id("approval-warnings")
    print("approval warnings on screen:", txt(warn)[:700])
    j.shot(page, "01_approval_warnings", locator=warn.first if warn.count() else None, full_page=not warn.count())
    if warn.count():
        warn.get_by_role("button", name="Approve anyway").click()
        page.wait_for_timeout(3000)
    print("after Approve anyway, phase bar:", txt(page.get_by_test_id("spec-phase"))[:300])
    over = page.get_by_test_id("approval-overridden")
    print("approval-overridden:", txt(over)[:500])
    report = page.get_by_test_id("spec-approval-report")
    print("spec-approval-report:", txt(report)[:500])
    j.shot(page, "02_after_approve_anyway", full_page=True)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    print("after reload, approval-overridden:", txt(page.get_by_test_id("approval-overridden"))[:300],
          "| report:", txt(page.get_by_test_id("spec-approval-report"))[:300])

    # --- journey nav on the document a real exploring turn walked ---
    page = open_doc(j, WALKED)
    nav = page.get_by_test_id("spec-journey")
    print("journey nav:", txt(nav)[:400])
    steps = page.locator("[data-testid^='spec-journey-step-']")
    print("journey steps:", [(steps.nth(i).get_attribute("data-testid"), steps.nth(i).get_attribute("aria-current"))
                              for i in range(steps.count())])
    print("journey size:", txt(page.get_by_test_id("spec-journey-size")))
    j.shot(page, "03_journey", locator=nav.first if nav.count() else None, full_page=not nav.count())

    # --- the answered cannot-satisfy report ---
    page = open_doc(j, "spec/changes/slug-speed/spec.json")
    panel = page.get_by_test_id("spec-amendments")
    print("slug-speed amendments panel:", txt(panel)[:900])
    j.shot(page, "04_answered_report", locator=panel.first if panel.count() else None, full_page=not panel.count())

    # --- corpus strip: untracked file, Adopt, Rebuild index ---
    strip = page.get_by_test_id("spec-corpus-strip")
    print("corpus strip:", txt(strip)[:700])
    adopt = page.get_by_test_id("spec-corpus-adopt-all")
    if adopt.count():
        adopt.first.click()
        page.wait_for_timeout(3000)
        print("adopt result:", txt(page.get_by_test_id("spec-corpus-adopt-result"))[:700])
    rebuild = page.get_by_test_id("spec-corpus-rebuild")
    if rebuild.count():
        rebuild.first.click()
        page.wait_for_timeout(3000)
        print("rebuild summary:", txt(page.get_by_test_id("spec-corpus-summary"))[:500],
              "| diagnostics:", txt(page.get_by_test_id("spec-corpus-diagnostics"))[:500],
              "| home question:", txt(page.get_by_test_id("spec-corpus-home-question"))[:300])
    j.shot(page, "05_corpus_strip", locator=strip.first if strip.count() else None, full_page=not strip.count())

    # --- the retired capability ---
    page = open_doc(j, RETIRED)
    print("retired capability phase bar:", txt(page.get_by_test_id("spec-phase"))[:300])
    body = txt(page.locator("main"))
    i = body.find("etire")
    print("retired page around 'retire':", body[max(0, i - 120):i + 300] if i >= 0 else "<no 'retire' on the page>")
    print("absorber named on screen:", "tool-" in body or "Tool " in body)
    j.shot(page, "06_retired", full_page=True)

    # --- delete dialog: focus, Escape, then delete ---
    page = open_doc(j, DEL)
    page.get_by_test_id("spec-delete").first.click()
    page.wait_for_timeout(800)
    focused = page.evaluate("() => { const a = document.activeElement; return a ? (a.textContent || a.getAttribute('aria-label') || a.tagName).trim().slice(0, 60) : null }")
    dialog = page.get_by_role("dialog")
    print("delete dialog:", txt(dialog)[:400] if dialog.count() else "<no role=dialog>", "| focused:", focused)
    j.shot(page, "07_delete_dialog", full_page=True)
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    print("after Escape, dialog open:", page.get_by_role("dialog").count(), "| doc still listed:",
          any(d["path"] == DEL for d in request("GET", f"{BASE}/documents")[1]["documents"]))
    print("console errors:", j.errors[:5] if hasattr(j, "errors") else "n/a")
print("PROP", PROP, "DEL", DEL, "UNTR", UNTR)
