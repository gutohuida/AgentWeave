"""2026-10-23 Runs drive, UI: do turn-end labels (a stopped turn, a completed turn) survive
navigating away and back, and a reload?

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_rn_ui.py <agent> <conversation-id> [label]
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rn_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

LABELS = re.compile(r"(Turn stopped|Turn failed|Turn interrupted|Worked for \d+\s*[a-z]*|Stopped|Completed)")


def norm(s):
    return " ".join((s or "").split())


def labels(page):
    text = norm(page.locator("main").first.text_content())
    return LABELS.findall(text), text


agent, conv = sys.argv[1], sys.argv[2]
label = sys.argv[3] if len(sys.argv) > 3 else "turnend"
with Judge("s1023-rn", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query=f"agent={agent}&conversation={conv}")
    page.wait_for_timeout(6000)
    first, text = labels(page)
    print("1 direct load  :", first)
    print("   'awaiting result' on screen:", "awaiting result" in text, "| 'interrupted':", "nterrupted" in text)
    print("   tail:", text[-700:])
    j.shot(page, f"{label}_1_direct")
    page.locator("[data-testid=project-tab-tasks]").click()
    page.wait_for_timeout(2500)
    print("   on tasks, url:", page.url)
    row = page.locator(f"[data-testid=rail-conversation-{conv}]")
    print("   rail row present:", row.count())
    if row.count():
        row.first.click()
    page.wait_for_timeout(4000)
    second, _ = labels(page)
    print("2 away and back:", second, page.url)
    j.shot(page, f"{label}_2_back")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    third, _ = labels(page)
    print("3 after reload :", third)
    j.shot(page, f"{label}_3_reload")
    print("SAME:", first == second == third)
