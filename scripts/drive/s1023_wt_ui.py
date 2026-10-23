"""2026-10-23 worktrees sweep, UI (real Chromium against the served bundle, scratch Hub hub-up wt1023 8160).

  board        every card: status line text and Retry buttons
  drawer KEY   a task's drawer: Story and Details text, the integration note, Try again count, checks row
  tryagain KEY press the drawer's Try again; what the note, the card and the drawer then say
  approve KEY  press Approve in the drawer (or move it to approved); what refusal reaches the screen

  py -3.11 scripts/drive/s1023_wt_ui.py <what> [key]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "board"
ARG = sys.argv[2] if len(sys.argv) > 2 else None
from s1023_wt_drive import S, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]
NAMES = {v: k for k, v in S.items() if isinstance(v, str) and v.startswith("task-")}


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def cards(page):
    for card in page.locator("article.aw-task-card").all():
        tid = card.get_attribute("data-task-id")
        st = card.locator(f"[data-testid='task-card-status-{tid}']")
        print(f"CARD {NAMES.get(tid, tid)} | status={txt(st)} | retry={card.get_by_role('button', name='Retry').count()}")


def tasks_tab(j):
    page = j.page(P, mode="light", query="tab=tasks")
    page.wait_for_timeout(4000)
    return page


def drawer(page, key):
    tid = S[key]
    page.get_by_test_id(f"task-open-{tid}").click()
    page.wait_for_timeout(2500)
    d = page.get_by_test_id(f"task-drawer-{tid}")
    print(f"[{key}] STORY:", txt(d)[:2500])
    print(f"[{key}] note:", txt(page.get_by_test_id(f"task-integrations-{tid}")))
    print(f"[{key}] try again:", page.get_by_test_id(f"task-integration-retry-{tid}").count())
    view = page.get_by_test_id(f"task-view-details-{tid}")
    if view.count():
        view.click()
        page.wait_for_timeout(1500)
        print(f"[{key}] DETAILS:", txt(d)[:3000])
        print(f"[{key}] note (details):", txt(page.get_by_test_id(f"task-integrations-{tid}")))
    return d


with Judge("s1023-wt", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "board":
        page = tasks_tab(j)
        cards(page)
        j.shot(page, "board")
    elif WHAT == "drawer":
        page = tasks_tab(j)
        drawer(page, ARG)
        j.shot(page, f"drawer_{ARG}")
    elif WHAT == "tryagain":
        page = tasks_tab(j)
        tid = S[ARG]
        drawer(page, ARG)
        btn = page.get_by_test_id(f"task-integration-retry-{tid}")
        print("try again buttons:", btn.count(), txt(btn))
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(5000)
            print("after note:", txt(page.get_by_test_id(f"task-integrations-{tid}")))
            print("after try again:", page.get_by_test_id(f"task-integration-retry-{tid}").count())
            print("after drawer:", txt(page.get_by_test_id(f"task-drawer-{tid}"))[:2500])
        j.shot(page, f"tryagain_{ARG}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        cards(page)
    elif WHAT == "status":
        page = tasks_tab(j)
        tid = S[ARG]
        d = drawer(page, ARG)
        page.get_by_test_id(f"task-status-menu-{tid}").first.click()
        page.wait_for_timeout(1000)
        opts = [" ".join((o.text_content() or "").split()) for o in page.get_by_role("menuitem").all()]
        opts += [" ".join((o.text_content() or "").split()) for o in page.get_by_role("option").all()]
        print("status options:", opts)
        target = page.get_by_role("menuitem", name="Move to Approved")
        if not target.count():
            target = page.get_by_role("option", name="Approved")
        if target.count():
            target.first.click()
            page.wait_for_timeout(4000)
            print("after approve:", txt(d)[:1500])
            print("refusal:", txt(page.get_by_test_id(f"task-status-refusal-{tid}")))
        j.shot(page, f"status_{ARG}")
    elif WHAT == "approve":
        page = tasks_tab(j)
        tid = S[ARG]
        drawer(page, ARG)
        for name in ("Approve", "Approve anyway"):
            b = page.get_by_test_id(f"task-drawer-{tid}").get_by_role("button", name=name, exact=True)
            print(f"button {name}:", b.count())
        b = page.get_by_test_id(f"task-drawer-{tid}").get_by_role("button", name="Approve", exact=True)
        if b.count():
            b.first.click()
            page.wait_for_timeout(4000)
            print("after approve drawer:", txt(page.get_by_test_id(f"task-drawer-{tid}"))[:3000])
            print("refusal:", txt(page.get_by_test_id(f"task-status-refusal-{tid}")))
        j.shot(page, f"approve_{ARG}")
    elif WHAT == "delete":
        page = tasks_tab(j)
        tid = S[ARG]
        page.get_by_test_id(f"task-open-{tid}").click()
        page.wait_for_timeout(1500)
        page.get_by_test_id(f"task-view-details-{tid}").click()
        page.wait_for_timeout(800)
        page.get_by_test_id(f"task-delete-{tid}").click()
        page.wait_for_timeout(800)
        print("confirm text:", txt(page.get_by_test_id(f"task-delete-confirm-{tid}")))
        j.shot(page, f"delete_confirm_{ARG}")
        page.get_by_test_id("delete-confirm").click()
        page.wait_for_timeout(3000)
        print("drawer still open:", page.get_by_test_id(f"task-drawer-{tid}").count())
        body = page.locator("body").text_content() or ""
        print("page mentions kept/branch/unmerged:", [w for w in ("kept", "Kept", "branch", "unmerged") if w in body])
        page.goto(page.url.split("?")[0] + f"?project={P}&tab=activity")
        page.wait_for_timeout(4000)
        for label in ("Activity", "Ledger"):
            r = page.get_by_role("radio", name=label)
            if r.count():
                r.first.click()
                page.wait_for_timeout(2000)
            b = page.locator("main").text_content() or ""
            for needle in ("Kept", "kept", "task_checkout_kept", "deleted"):
                i = b.find(needle)
                if i >= 0:
                    print(f"[{label}] {needle}:", " ".join(b[max(0, i - 120):i + 220].split()))
            j.shot(page, f"delete_activity_{label}")
        page.goto(page.url.split("?")[0] + f"?project={P}&tab=environment&section=worktrees")
        page.wait_for_timeout(4000)
        b = page.locator("main").text_content() or ""
        i = b.find("Task deleted")
        print("worktrees 'Task deleted':", " ".join(b[max(0, i - 300):i + 200].split()) if i >= 0 else "<absent>")
        j.shot(page, "delete_worktrees", full_page=True)
