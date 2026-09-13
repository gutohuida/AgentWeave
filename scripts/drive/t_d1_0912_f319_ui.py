"""D-1 2026-09-12, priority 3: what the operator SEES for a task F319 stranded.

Opens the served bundle as an operator, goes to the task board, and reads what it says about the
tasks `t_d1_0912_f319_reach.py` left behind for the same `AW_RUN_TAG`: B1/B2 (pre-fix:
`under_review`, held, no run), A (pre-fix: `completed`, held by the agent that became its author)
and C (restaffed, entry never delivered -- F320).

AW_EXPECT selects what is asserted (a-refused-review-leaves-nothing-behind 5.4):
  prefix (default)  report only, as the original D-1 script did.
  fixed             the B1 and B2 cards are not in the Under Review column, and A's card does not
                    name `auth<TAG>` -- the refused dispatch left the board as it was.

The column is read from the board's own markup (`.task-board-column[data-status=...]`), the card
from its `Open <title>` label, so a card is placed by the column that renders it, not by text order.

    AW_HUB=http://127.0.0.1:8016 AW_KEY=... AW_PROJECT=proj-... AW_RUN_TAG=r8f AW_EXPECT=fixed \
        SHOTDIR=... py -3.11 scripts/drive/t_d1_0912_f319_ui.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ["AW_HUB"]
KEY = require_key()
PROJ = os.environ["AW_PROJECT"]
SHOTDIR = os.environ.get("SHOTDIR", ".")
TAG = os.environ["AW_RUN_TAG"]
EXPECT = os.environ.get("AW_EXPECT", "prefix")
if EXPECT not in ("prefix", "fixed"):
    raise SystemExit(f"AW_EXPECT must be prefix or fixed, not {EXPECT!r}")
AUTH = f"auth{TAG}"
TITLES = {"B1": f"B1 {TAG}", "B2": f"B2 {TAG}", "A": f"A {TAG}", "C": f"C {TAG}"}

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail else ""))


SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 1100})
    page.add_init_script(SEED)
    console = []
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"[:300]))
    requests = []
    page.on(
        "request", lambda r: requests.append(f"{r.method} {r.url}") if r.method != "GET" else None
    )
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(SHOTDIR, f"f319-{TAG}-home.png"))
    for name in ("Tasks", "Board"):
        loc = page.get_by_role("button", name=name)
        if not loc.count():
            loc = page.get_by_text(name, exact=True)
        if loc.count():
            loc.first.click()
            print(f"clicked {name!r}")
            break
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(SHOTDIR, f"f319-{TAG}-board.png"), full_page=True)
    columns = page.locator(".task-board-column")
    print(f"--- {columns.count()} board columns")
    placed = {}
    card_text = {}
    for leg_key, title in TITLES.items():
        label = f"Open {title}"
        where = []
        for i in range(columns.count()):
            col = columns.nth(i)
            if col.locator(f'[aria-label="{label}"]').count():
                where.append(col.get_attribute("data-status"))
        placed[leg_key] = where
        card = page.locator(f'[aria-label="{label}"]')
        # The first match is the card's `task-card-body`; its parent is the card, which also holds
        # the `@assignee` chip.
        text = card.first.locator("xpath=..").inner_text() if card.count() else ""
        card_text[leg_key] = text
        print(f"--- {title!r}: columns {where or 'ABSENT'}")
        if text:
            print("    " + text[:300].replace("\n", " | "))
    if EXPECT == "fixed":
        for leg_key in ("B1", "B2", "A"):
            ok(f"{TITLES[leg_key]!r} is on the board", placed[leg_key], placed[leg_key])
        for leg_key in ("B1", "B2"):
            ok(
                f"{TITLES[leg_key]!r} is not in Under Review",
                placed[leg_key] and "under_review" not in placed[leg_key],
                placed[leg_key],
            )
        ok(
            f"{TITLES['A']!r}'s card does not name {AUTH}",
            card_text["A"] and f"@{AUTH}" not in card_text["A"],
            card_text["A"][:200].replace("\n", " | "),
        )
    loc = page.get_by_label(f"Open {TITLES['B1']}")
    if loc.count():
        loc.first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=os.path.join(SHOTDIR, f"f319-{TAG}-b1-detail.png"), full_page=True)
        print("--- B1 detail body (head):")
        print(page.inner_text("body")[:2500])
    print("--- non-GET requests the page made:")
    for r in requests:
        print("   ", r)
    for line in console:
        print("   ", line)
    b.close()

if EXPECT == "fixed":
    print(f"\n{len(PASS)} ok, {len(FAIL)} fail")
    sys.exit(1 if FAIL else 0)
