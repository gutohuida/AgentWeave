"""Tasks x Dependencies x Worktrees sweep 2026-10-21, UI (real Chromium, served bundle, :8150).

    AW_P=proj-... py -3.11 scripts/drive/s1021_t_ui.py <phase> [key]
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1021_t_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

S = json.loads((pathlib.Path.home() / ".agentweave" / "e2e-t1021-tasks.json").read_text())


def body(page):
    return " ".join((page.locator("body").text_content() or "").split())


def text(loc):
    return " ".join((loc.text_content() or "").split()) if loc.count() else "<absent>"


def around(t, word, before=150, after=350):
    hits = [m.start() for m in re.finditer(re.escape(word), t, re.I)]
    if not hits:
        return f"<no '{word}'>"
    return " | ".join(t[max(0, i - before): i + after] for i in hits[:3])


def open_drawer(j, tid):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    try:
        page.get_by_test_id(f"task-open-{tid}").first.click(timeout=5000)
    except Exception as exc:
        print("card click intercepted:", type(exc).__name__)
        page.get_by_test_id(f"task-open-{tid}").first.dispatch_event("click")
    page.wait_for_timeout(2500)
    return page


def focused(page):
    return page.evaluate(
        "document.activeElement && ((document.activeElement.getAttribute('data-testid') || '') + ' | ' + (document.activeElement.textContent || '').trim().slice(0, 60))"
    )


def delete(j):
    """Delete S[key] from its drawer; print the confirm, focus, and what the page says afterwards."""
    key = sys.argv[2]
    tid = S[key]
    page = open_drawer(j, tid)
    page.get_by_test_id(f"task-view-details-{tid}").click()
    page.wait_for_timeout(1000)
    page.get_by_test_id(f"task-delete-{tid}").click()
    page.wait_for_timeout(800)
    box = page.get_by_test_id(f"task-delete-confirm-{tid}")
    print("CONFIRM:", text(box))
    print("focus on open:", focused(page))
    j.shot(page, f"confirm-{key}", full_page=True)
    box.get_by_role("button", name=re.compile("^Delete", re.I)).click()
    page.wait_for_timeout(3000)
    print("drawer still open:", page.get_by_test_id(f"task-drawer-{tid}").count(),
          "| card:", page.get_by_test_id(f"task-open-{tid}").count())
    t = body(page)
    for w in ("kept", "checkout", "branch", "unmerged", "deleted", "released", "free to start"):
        print(f"  '{w}':", around(t, w, 80, 200)[:300])
    j.shot(page, f"after-{key}", full_page=True)


def activity(j):
    page = j.page(P, mode="light", query="tab=activity")
    page.wait_for_timeout(3000)
    sub = page.locator("button, [role=tab]").filter(has_text=re.compile("^\s*activity\s*$", re.I))
    print("activity controls:", sub.count())
    sub.last.click()
    page.wait_for_timeout(3000)
    print("ACTIVITY:", body(page)[:2500])
    t = body(page)
    for w in ("checkout", "kept", "task_deleted", "Deleted", "K1", "released"):
        print(f"  '{w}':", around(t, w, 120, 260)[:500])
    j.shot(page, "activity", full_page=True)


def worktrees(j):
    page = j.page(P, mode="light", query="tab=environment&section=worktrees")
    page.wait_for_timeout(4000)
    print("WORKTREES:", body(page)[:2500])
    j.shot(page, "worktrees", full_page=True)


def retry(j):
    """F823: the drawer offers Try again on a failed merge and names the attempt time."""
    key = sys.argv[2]
    tid = S[key]
    page = open_drawer(j, tid)
    drawer = page.get_by_test_id(f"task-drawer-{tid}")
    print("story view retry in drawer:", drawer.get_by_test_id(f"task-integration-retry-{tid}").count())
    print("story NOTE:", text(drawer.get_by_test_id(f"task-integrations-{tid}")))
    times = drawer.locator(f"[data-testid='task-integrations-{tid}'] time")
    print("time elements:", [(times.nth(i).text_content(), times.nth(i).get_attribute("datetime")) for i in range(times.count())])
    page.get_by_test_id(f"task-view-details-{tid}").click()
    page.wait_for_timeout(1500)
    btn = drawer.get_by_test_id(f"task-integration-retry-{tid}")
    print("details view retry in drawer:", btn.count())
    print("details NOTE:", text(drawer.get_by_test_id(f"task-integrations-{tid}")))
    j.shot(page, f"retry-before-{sys.argv[3] if len(sys.argv) > 3 else 'x'}", full_page=True)
    if btn.count():
        btn.first.click()
        page.wait_for_timeout(5000)
        print("NOTE after press:", text(drawer.get_by_test_id(f"task-integrations-{tid}")))
        times = drawer.locator(f"[data-testid='task-integrations-{tid}'] time")
        print("time elements after:", [(times.nth(i).text_content(), times.nth(i).get_attribute("datetime")) for i in range(times.count())])
        print("retry buttons after:", drawer.get_by_test_id(f"task-integration-retry-{tid}").count())
        print("error line:", around(body(page), "Could not", 50, 200))
        j.shot(page, f"retry-after-{sys.argv[3] if len(sys.argv) > 3 else 'x'}", full_page=True)


def conv(j):
    agent, cid = sys.argv[2], sys.argv[3]
    page = j.page(P, mode="light", query=f"agent={agent}&conversation={cid}")
    page.wait_for_timeout(5000)
    t = body(page)
    for w in ("queued", "Could not prepare", "Continue", "Withdraw", "frozen", "waiting"):
        print(f"  '{w}':", around(t, w, 120, 300)[:450])
    j.shot(page, f"conv-{agent}", full_page=True)
    if len(sys.argv) > 4 and sys.argv[4] == "continue":
        page.get_by_role("button", name=re.compile("^Continue$")).first.click()
        page.wait_for_timeout(4000)
        print("after Continue:", around(body(page), "waiting", 120, 300)[:450])


def story(j):
    tid = S[sys.argv[2]]
    page = open_drawer(j, tid)
    v = page.get_by_test_id(f"task-view-story-{tid}")
    if v.count():
        v.first.click()
        page.wait_for_timeout(2500)
    print("STORY:", text(page.get_by_test_id(f"task-drawer-body-{tid}"))[:3000])
    j.shot(page, f"story-{sys.argv[2]}", full_page=True)


if __name__ == "__main__":
    with Judge("s1021-t", hub=e2e.hub(), key=e2e.key()) as j:
        globals()[sys.argv[1]](j)
