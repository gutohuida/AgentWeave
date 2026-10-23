"""Requirements, evidence & coverage x Drift sweep 2026-10-23, UI (Chromium, served bundle on the
scratch Hub :8115, profile ev1023):

  health <tag>        the Spec header's requirements fact (text, tone, popover) beside the coverage
                      bar's counts, read on the same page (F945)
  evidence [focus]    the Spec tab's Evidence view (view=evidence), optionally focused
  story <FR-n>        one requirement's story (view=requirement)
  drift <tag>         the drift detail: its strip, rows and answers

    AW_P=proj-... py -3.11 scripts/drive/s1023_ev_ui.py <phase> [arg]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ev_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

DOCP = "spec/changes/ev-main/spec.json"


def norm(s):
    return " ".join((s or "").split())


def open_doc(j, mode="light"):
    page = j.page(P, mode=mode, query=f"tab=spec&document={DOCP}")
    page.wait_for_timeout(4500)
    return page


def health(tag):
    with Judge("s1023-evidence", hub=e2e.hub(), key=e2e.key()) as j:
        page = open_doc(j)
        fact = page.locator("[data-testid=spec-health-requirements]")
        print("FACT:", norm(fact.text_content()) if fact.count() else None,
              "| tone:", fact.get_attribute("data-tone") if fact.count() else None)
        for name in ("drift", "vault", "tasks"):
            f = page.locator(f"[data-testid=spec-health-{name}]")
            if f.count():
                print(f"  {name}:", norm(f.text_content()), "| tone:", f.get_attribute("data-tone"))
        if fact.count():
            fact.click()
            page.wait_for_timeout(600)
            pop = page.locator(".aw-health-pop")
            print("POPOVER:", norm(pop.first.text_content()) if pop.count() else None)
            j.shot(page, f"{tag}_health_popover")
            item = page.get_by_role("menuitem", name="Show details")
            if item.count():
                item.first.click()
                page.wait_for_timeout(1200)
            else:
                page.keyboard.press("Escape")
        cov = page.locator("[data-testid=spec-coverage]")
        print("COVERAGE BAR:", norm(cov.first.text_content())[:900] if cov.count() else None)
        j.shot(page, f"{tag}_coverage")
        print("errors:", j.errors[:5])


def evidence(focus=None):
    with Judge("s1023-evidence", hub=e2e.hub(), key=e2e.key()) as j:
        q = "tab=spec&view=evidence" + (f"&focus={focus}" if focus else "")
        page = j.page(P, mode="light", query=q)
        page.wait_for_timeout(4500)
        print("URL", page.url)
        b = page.locator("[data-testid=evidence-browser]")
        print("BROWSER:", norm(b.first.text_content())[:2500] if b.count() else None)
        rows = page.locator("[data-testid^=evidence-row-toggle-]")
        print("rows:", rows.count())
        if rows.count():
            rows.first.click()
            page.wait_for_timeout(2000)
            print("OPENED ROW:", norm(page.locator("[data-testid^=evidence-row-ev-]").first.text_content())[:1500])
        j.shot(page, f"evidence_{focus or 'all'}", full_page=True)
        print("errors:", j.errors[:5])


def story(identifier):
    with Judge("s1023-evidence", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query=f"tab=spec&view=requirement&document={DOCP}&focus={identifier}")
        page.wait_for_timeout(4500)
        s = page.locator("[data-testid=requirement-story]")
        print("STORY:", norm(s.first.text_content())[:3000] if s.count() else None)
        j.shot(page, f"story_{identifier}", full_page=True)
        print("errors:", j.errors[:5])


def drift(tag):
    with Judge("s1023-evidence", hub=e2e.hub(), key=e2e.key()) as j:
        page = open_doc(j)
        fact = page.locator("[data-testid=spec-health-drift]")
        print("DRIFT FACT:", norm(fact.text_content()) if fact.count() else None,
              "| tone:", fact.get_attribute("data-tone") if fact.count() else None)
        if fact.count():
            fact.click()
            page.wait_for_timeout(600)
            pop = page.locator(".aw-health-pop")
            print("POPOVER:", norm(pop.first.text_content()) if pop.count() else None)
            item = page.get_by_role("menuitem", name="Show details")
            if item.count():
                item.first.click()
                page.wait_for_timeout(1500)
        panel = page.locator("[data-testid=spec-drift-panel]")
        print("PANEL:", norm(panel.first.text_content())[:2000] if panel.count() else None)
        j.shot(page, f"{tag}_drift")
        print("errors:", j.errors[:5])


if __name__ == "__main__":
    if sys.argv[1] != "answer":
        {"health": health, "evidence": evidence, "story": story, "drift": drift}[sys.argv[1]](*sys.argv[2:])


def answer(drift_id, button):
    """Open the drift detail and press one answer on one candidate's row, then read the panel."""
    with Judge("s1023-evidence", hub=e2e.hub(), key=e2e.key()) as j:
        page = open_doc(j)
        page.locator("[data-testid=spec-health-drift]").click()
        page.wait_for_timeout(600)
        page.get_by_role("menuitem", name="Show details").first.click()
        page.wait_for_timeout(1500)
        row = page.locator(f"[data-testid=spec-drift-row-{drift_id}]")
        print("ROW before:", norm(row.text_content()) if row.count() else None)
        row.get_by_role("button", name=button).click()
        page.wait_for_timeout(2500)
        print("ROW after:", norm(row.text_content()) if row.count() else "(gone)")
        panel = page.locator("[data-testid=spec-drift-panel]")
        print("PANEL after:", norm(panel.first.text_content())[:1500] if panel.count() else None)
        fact = page.locator("[data-testid=spec-health-requirements]")
        print("FACT after:", norm(fact.text_content()), "| tone:", fact.get_attribute("data-tone"))
        j.shot(page, f"answer_{drift_id}")
        print("errors:", j.errors[:5])


if __name__ == "__main__" and sys.argv[1] == "answer":
    answer(sys.argv[2], sys.argv[3])
