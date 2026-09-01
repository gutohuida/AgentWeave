"""Row 8's screen half — what the operator sees of a project with more than 100 tasks.

The API half (`t_sweep_row8_tasks.py`) measured that `GET /projects/{id}/tasks` defaults to
`limit=100` (`hub/hub/api/v1/tasks.py:850`), orders by `created_at` ascending, and returns a bare
JSON array with no `total`, no `has_more` and no `next` — so a client past 100 tasks is given the
OLDEST hundred and told nothing. Two questions only a browser can answer:

  1. `useTasks` (`hub/ui/src/api/tasks.ts:210-225`) sends no `limit` and no `offset`, and
     `OverviewPage.tsx:86` does `const taskCount = tasks.length`. Does the Overview page therefore
     state a task count that is simply wrong?
  2. `TasksBoard` reads the same hook. Does the board render fewer cards than the project has
     tasks, and does anything on the screen say so?

And the contrast that makes the finding precise rather than sweeping: the DEPENDENCY board reads
`GET /tasks/board`, which has no limit at all, so the two boards in the same tab should disagree.

Also driven here, because they are the screen half of the API sweep's other two findings:

  3. the hand-set block control collects the reason *before* it sends — so the UI cannot produce
     the 422 the API half found (`TaskDetailDrawer.tsx:397-400`: "Required by the Hub, so the
     control collects it rather than sending a status that would be refused");
  4. the drawer's status control offers only edges the published map allows (design D13), which is
     why an operator working in the product never meets an illegal transition at all.

Run: AW_HUB=... AW_KEY=... AW_PROJECT=... AW_SHOTS=<dir> py -3.11 scripts/drive/t_sweep_row8_ui.py
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
OUT = pathlib.Path(os.environ.get("AW_SHOTS", "."))
OUT.mkdir(parents=True, exist_ok=True)

A = f"/projects/{PROJECT}"
FAILURES = []

SEED = f"""
sessionStorage.setItem('agentweave-session', {json.dumps(json.dumps({"apiKey": KEY, "hubUrl": HUB}))});
localStorage.setItem('agentweave-selected-project', {json.dumps(PROJECT)});
"""


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail[:300]}" if detail else ""))
    if not ok:
        FAILURES.append((label, str(detail)))


# What is actually there, measured on the API before the browser is opened.
paged = []
for page in range(0, 20):
    _, chunk = api("GET", f"{A}/tasks?limit=1000&offset={page * 1000}")
    chunk = chunk if isinstance(chunk, list) else []
    paged.extend(chunk)
    if len(chunk) < 1000:
        break
TOTAL = len(paged)
_, default_page = api("GET", f"{A}/tasks")
DEFAULT = len(default_page) if isinstance(default_page, list) else 0
_, board = api("GET", f"{A}/tasks/board")
BOARD = len(board.get("tasks") or []) if isinstance(board, dict) else 0
print(
    f"project {PROJECT}: {TOTAL} tasks by paging, {DEFAULT} on the default page, {BOARD} on /board"
)
if TOTAL <= 100:
    print("REFUSING TO RUN: this leg needs more than 100 tasks in the project to mean anything.")
    sys.exit(1)

# A card the drawer legs can act on, at a status with a small, checkable set of legal moves.
_, made = api("POST", f"{A}/tasks", {"title": "row8 ui subject"})
SUBJECT = made["id"]
api("PATCH", f"{A}/tasks/{SUBJECT}", {"status": "in_progress"})

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.goto(HUB, wait_until="domcontentloaded")
        page.evaluate(SEED)

        # ---------------------------------------------------------------- OVERVIEW
        page.goto(f"{HUB}/?project={PROJECT}&tab=overview", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        page.screenshot(path=str(OUT / "row8-01-overview.png"), full_page=True)
        overview = page.inner_text("body")
        # Scoped as tightly as this page allows: the count is rendered as a bare number beside its
        # own label, so the assertion is on the two numbers, not on a substring of the whole page.
        check(
            "the Overview page does not state a task count capped at 100",
            f"{DEFAULT}" not in overview.split("Tasks")[0][-40:] or str(TOTAL) in overview,
            f"project has {TOTAL} tasks; the page was screenshotted for the number it shows",
        )
        shown = [line.strip() for line in overview.splitlines() if line.strip().isdigit()]
        print(f"  numbers on the overview page: {shown[:20]}")
        check(
            "some number on the Overview page equals the real task count",
            str(TOTAL) in shown,
            f"real total {TOTAL}, default page {DEFAULT}, numbers shown {shown[:20]}",
        )

        # ---------------------------------------------------------------- TASKS TAB
        page.goto(f"{HUB}/?project={PROJECT}&tab=tasks", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "row8-02-tasks.png"), full_page=True)
        cards = page.locator('[data-testid^="task-open-"]').count()
        print(f"  task cards rendered: {cards}")
        check(
            "the Tasks board renders every task the project has",
            cards >= TOTAL,
            f"{cards} cards for {TOTAL} tasks (the default page carries {DEFAULT})",
        )
        body = page.inner_text("body")
        check(
            "or else the screen says the list was truncated",
            cards >= TOTAL
            or any(
                w in body.lower() for w in ("showing", "of 1", "more task", "truncat", "load more")
            ),
            "no 'showing N of M', no 'load more', nothing",
        )

        # ---------------------------------------------------------- THE DRAWER, D13
        page.goto(f"{HUB}/?project={PROJECT}&tab=tasks", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        opener = page.locator(f'[data-testid="task-open-{SUBJECT}"]')
        if opener.count() == 0:
            check(
                "the subject card is reachable on the board",
                False,
                "created moments ago and not rendered — the same cut as the count leg",
            )
        else:
            opener.first.click()
            page.wait_for_timeout(1500)
            drawer = page.locator(f'[data-testid="task-drawer-{SUBJECT}"]')
            check("the task drawer opens", drawer.count() > 0)
            if drawer.count():
                text = drawer.first.inner_text()
                page.screenshot(path=str(OUT / "row8-03-drawer.png"), full_page=True)
                # From `in_progress` the operator's legal moves are exactly these four.
                legal = {"assigned", "blocked", "completed", "rejected"}
                illegal = {"pending", "under_review", "approved", "revision_needed"}
                offered = {w for w in legal | illegal if w.replace("_", " ") in text.lower()}
                print(f"  words the drawer shows: {sorted(offered)}")
                check(
                    "the drawer offers no move the machine would refuse (design D13)",
                    not (offered & illegal),
                    f"offered {sorted(offered & illegal)} from in_progress",
                )
                # The block control: does it collect the reason before sending?
                blocker = drawer.first.locator("text=Blocked").or_(
                    drawer.first.locator("text=blocked")
                )
                if blocker.count():
                    blocker.first.click()
                    page.wait_for_timeout(1200)
                    check(
                        "asking for 'blocked' opens a field for the reason rather than sending",
                        page.locator(f'[data-testid="task-block-reason-{SUBJECT}"]').count() > 0,
                        "no reason field appeared",
                    )
                    confirm = page.locator(f'[data-testid="task-block-confirm-{SUBJECT}"]')
                    if confirm.count():
                        check(
                            "  and the confirm control is disabled until a reason is typed",
                            confirm.first.is_disabled(),
                            "enabled with an empty reason",
                        )
                    page.screenshot(path=str(OUT / "row8-04-block-reason.png"), full_page=True)
                else:
                    check(
                        "a control for the waiting status exists in the drawer", False, "none found"
                    )

        # 4xx/5xx this drive deliberately provoked are none — nothing here provokes one.
        real = [e for e in console_errors if "favicon" not in e.lower()]
        check("no console errors", not real, str(real[:3])[:300])
        browser.close()

finally:
    print()
    print("=" * 78)
    print(f"SUMMARY — {len(FAILURES)} failure(s)")
    print("=" * 78)
    for label, detail in FAILURES:
        print(f"  FAIL {label}  {detail[:180]}")
    print(f"screenshots in {OUT}")
