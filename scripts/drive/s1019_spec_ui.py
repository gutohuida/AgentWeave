"""Sweep 2026-10-19, spec UI: the amendments panel's report answers (answered, unanswered, on an
archived change), decided proposals, and the roadmap page's slice state, in a real browser.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1019_spec_ui.py <project-id> <hub-url> <archived DOC> <REJ DOC> <PD> <RM>
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/e2e-loop"))
import e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P, HUB, DOC, REJ, PD, RM = sys.argv[1:7]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def open_doc(j, path):
    page = j.page(P, mode="light", query=f"tab=spec&document={path}")
    page.wait_for_timeout(5000)
    return page


with Judge("s1019-spec", hub=HUB, key=e2e.key()) as j:
    page = open_doc(j, REJ)
    panel = page.get_by_test_id("spec-amendments")
    print("REJ amendments panel:", txt(panel)[:600])
    j.shot(page, "01_rejected_report", locator=panel.first if panel.count() else None, full_page=not panel.count())

    page = open_doc(j, DOC)
    panel = page.get_by_test_id("spec-amendments")
    print("archived DOC phase bar:", txt(page.get_by_test_id("spec-phase-bar"))[:200])
    print("archived DOC amendments panel:", txt(panel)[:1500])
    answers = page.locator("[data-testid^='report-answer-']")
    print("answer forms offered on the archived change:", answers.count())
    j.shot(page, "02_archived_change_amendments", locator=panel.first if panel.count() else None,
           full_page=not panel.count())
    if answers.count():
        form = answers.first
        form.get_by_role("button", name="Amend criterion…").click()
        form.get_by_label("Criterion then").fill("alpha finishes under 3ms")
        form.get_by_role("button", name="Amend and unblock").click()
        page.wait_for_timeout(2500)
        print("amend on archived change ->", txt(form.get_by_role("alert")))
        j.shot(page, "03_amend_on_archived", locator=form)

    page = open_doc(j, PD)
    toggle = page.get_by_test_id("spec-proposals-resolved-toggle")
    print("resolved toggle:", txt(toggle))
    if toggle.count():
        toggle.first.click()
        page.wait_for_timeout(1500)
    resolved = page.get_by_test_id("spec-proposals-resolved")
    print("resolved proposals:", txt(resolved)[:1200])
    j.shot(page, "04_resolved_proposals", locator=resolved.first if resolved.count() else None,
           full_page=not resolved.count())

    page = open_doc(j, RM)
    chips = page.locator(".aw-chip")
    print("roadmap chips:", [" ".join((chips.nth(i).text_content() or "").split()) for i in range(min(chips.count(), 12))])
    body = page.locator("body")
    t = txt(body)
    i = t.find("First")
    print("roadmap around slice 'First':", t[max(0, i - 80):i + 300])
    print("roadmap offers a way to link a change to a slice:",
          page.get_by_role("button", name="Link").count() + page.get_by_text("Link a change").count())
    j.shot(page, "05_roadmap", full_page=True)
