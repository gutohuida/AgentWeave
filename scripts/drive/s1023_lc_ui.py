"""2026-10-23 resilience drive, UI: what alpha's conversation shows after the Hub was killed with a
turn in flight (turn-end label, composer, busy state), and the task's card.

    py -3.11 scripts/drive/s1023_lc_ui.py <label> [agent] [conversation-id]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lc_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


label = sys.argv[1]
agent = sys.argv[2] if len(sys.argv) > 2 else "alpha"
conv = sys.argv[3] if len(sys.argv) > 3 else None
with Judge("s1023-lc", hub=e2e.hub(), key=e2e.key()) as j:
    query = f"agent={agent}" + (f"&conversation={conv}" if conv else "")
    page = j.page(P, mode="light", query=query)
    page.wait_for_timeout(7000)
    print("URL", page.url)
    main = page.locator("main").first
    print("MAIN:", norm(main.text_content())[-2500:])
    for sel in ("[data-slot=composer]", "form"):
        loc = page.locator(sel)
        if loc.count():
            print(f"COMPOSER({sel}):", norm(loc.last.text_content())[:400])
            break
    btns = page.get_by_role("button")
    names = [norm(btns.nth(i).get_attribute("aria-label") or btns.nth(i).text_content())[:40] for i in range(min(btns.count(), 120))]
    print("BUTTONS:", [n for n in names if any(w in n.lower() for w in ("stop", "send", "queue", "retry", "interrupt", "continue", "cancel"))])
    j.shot(page, f"{label}_conv", full_page=False)
    print("console errors:", j.errors[:5])
