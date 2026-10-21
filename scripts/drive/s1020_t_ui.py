"""Tasks x Dependencies x Worktrees sweep 2026-10-20, UI (real Chromium, served bundle, :8170).

    AW_P=proj-... py -3.11 scripts/drive/s1020_t_ui.py <phase>
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_t_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

S = json.loads((pathlib.Path.home() / ".agentweave" / "e2e-t1020-tasks.json").read_text())


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def around(text, word, before=150, after=350):
    hits = [m.start() for m in re.finditer(re.escape(word), text, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(text[max(0, i - before): i + after] for i in hits[:3])


def open_drawer(j, tid):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    try:
        page.get_by_test_id(f"task-open-{tid}").first.click(timeout=5000)
    except Exception as exc:
        print("card click intercepted:", type(exc).__name__, "| page:", body(page)[:400])
        j.shot(page, "intercepted", full_page=True)
        page.get_by_test_id(f"task-open-{tid}").first.dispatch_event("click")
    page.wait_for_timeout(2500)
    return page


def retry(j):
    a = S["A"]
    page = open_drawer(j, a)
    drawer = page.get_by_test_id(f"task-drawer-{a}")
    print("in drawer (story) retry:", drawer.get_by_test_id(f"task-integration-retry-{a}").count())
    page.get_by_test_id(f"task-view-details-{a}").click()
    page.wait_for_timeout(1500)
    btn = drawer.get_by_test_id(f"task-integration-retry-{a}")
    print("in drawer (details) retry:", btn.count())
    note = drawer.get_by_test_id(f"task-integrations-{a}")
    print("drawer NOTE:", " ".join((note.text_content() or "").split()) if note.count() else "<no note>")
    j.shot(page, f"retry-details-{sys.argv[1]}", full_page=True)
    if not btn.count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        btn = page.get_by_test_id(f"task-integration-retry-{a}")
        print("card retry:", btn.count())
    btn.first.click()
    page.wait_for_timeout(4000)
    note = page.get_by_test_id(f"task-integrations-{a}").first
    print("NOTE after:", " ".join((note.text_content() or "").split()) if note.count() else "<no note>")
    print("retry buttons after:", page.get_by_test_id(f"task-integration-retry-{a}").count())
    print("error line:", around(body(page), "Could not retry", 50, 200))
    j.shot(page, f"retry-after-{sys.argv[1]}", full_page=True)


def rename(j):
    c = S["C"]
    page = open_drawer(j, c)
    page.get_by_test_id(f"task-drawer-title-{c}").click()
    inp = page.get_by_test_id(f"task-drawer-title-input-{c}")
    inp.fill("C: README (escaped)")
    inp.press("Escape")
    page.wait_for_timeout(1000)
    print("after Esc:", page.get_by_test_id(f"task-drawer-title-{c}").text_content(),
          "| drawer open:", page.get_by_test_id(f"task-drawer-{c}").count())
    page.get_by_test_id(f"task-drawer-title-{c}").click()
    inp = page.get_by_test_id(f"task-drawer-title-input-{c}")
    inp.fill("C: README for discounts — résumé")
    inp.press("Enter")
    page.wait_for_timeout(1500)
    print("after Enter:", page.get_by_test_id(f"task-drawer-title-{c}").text_content())
    t = body(page)
    print("DEPENDS:", around(t, "Depends on", 50, 300))
    j.shot(page, "rename", full_page=True)


def deps(j):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    tabs = page.get_by_role("tab")
    print("tabs:", [tabs.nth(i).text_content() for i in range(tabs.count())])
    dep = page.get_by_role("tab", name=re.compile("Dependenc", re.I))
    if not dep.count():
        dep = page.get_by_role("button", name=re.compile("Dependenc", re.I))
    print("dependencies control:", dep.count())
    if dep.count():
        dep.first.click()
        page.wait_for_timeout(2500)
        t = body(page)
        print("DEP VIEW:", t[:1500])
        j.shot(page, "deps", full_page=True)


def story(j):
    tid = S[sys.argv[2]]
    page = open_drawer(j, tid)
    v = page.get_by_test_id(f"task-view-story-{tid}")
    print("story view control:", v.count())
    if v.count():
        v.first.click()
        page.wait_for_timeout(2500)
    t = " ".join((page.get_by_test_id(f"task-drawer-body-{tid}").text_content() or "").split())
    print("STORY:", t[:3000])
    j.shot(page, f"story-{sys.argv[2]}", full_page=True)


def delete(j):
    tid = S[sys.argv[2]]
    page = open_drawer(j, tid)
    page.get_by_test_id(f"task-view-details-{tid}").click()
    page.wait_for_timeout(1000)
    page.get_by_test_id(f"task-delete-{tid}").click()
    page.wait_for_timeout(800)
    t = body(page)
    print("DELETE DIALOG:", around(t, "Delete", 100, 400))
    focused = page.evaluate("document.activeElement && (document.activeElement.textContent || document.activeElement.getAttribute('data-testid'))")
    print("focused:", focused)
    j.shot(page, "delete-dialog", full_page=True)
    box = page.get_by_test_id(f"task-delete-confirm-{tid}")
    print("CONFIRM BOX:", " ".join((box.text_content() or "").split()))
    box.get_by_role("button", name=re.compile("^Delete", re.I)).click()
    page.wait_for_timeout(2500)
    print("drawer still open:", page.get_by_test_id(f"task-drawer-{tid}").count(),
          "| card:", page.get_by_test_id(f"task-open-{tid}").count())
    print("after:", around(body(page), "delete", 100, 300))


def delete404(j):
    """Delete a task from its drawer and record every 404 the page then requests, for 20 s."""
    from s1020_t_lib import req
    ts = {t["title"][:8]: t["id"] for t in req("GET", f"projects/{P}/tasks?limit=500")[1]["tasks"]}
    tid = ts["bulk 004"]
    page = open_drawer(j, tid)
    hits = []
    page.on("response", lambda r: hits.append((round(page.evaluate("performance.now()")), r.status, r.url.split("/api/v1/")[-1])) if r.status == 404 else None)
    page.get_by_test_id(f"task-view-details-{tid}").click()
    page.wait_for_timeout(800)
    page.get_by_test_id(f"task-delete-{tid}").click()
    page.wait_for_timeout(500)
    page.get_by_test_id(f"task-delete-confirm-{tid}").get_by_role("button", name=re.compile("^Delete", re.I)).click()
    for sec in (2, 5, 10, 20):
        page.wait_for_timeout(sec * 1000 - (0 if sec == 2 else {5: 2, 10: 5, 20: 10}[sec] * 1000))
        print(f"t+{sec}s card={page.get_by_test_id(f'task-open-{tid}').count()} 404s={len(hits)}")
    from collections import Counter
    print(Counter(u for _, _, u in hits).most_common(8))
    j.shot(page, "after-delete", full_page=True)


if __name__ == "__main__":
    with Judge("s1020-t", hub=e2e.hub(), key=e2e.key()) as j:
        globals()[sys.argv[1].split("-")[0]](j)
