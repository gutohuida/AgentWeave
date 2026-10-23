"""2026-10-23 Flows & review drive, UI (Chromium, served bundle on scratch Hub :8112): what the
operator reads after a verdict withdrew waiting review turns -- the operator's own withdrawn review
conversations, the flow's withdrawn review conversation, tester's rail, the task drawer story, the
Jobs tab for the flow, and Activity.

  AW_P=proj-... py -3.11 scripts/drive/s1023_lb_ui.py conv=<id>[,<id>] [task=<id>]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lb_lib import P, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


args = dict(a.split("=", 1) for a in sys.argv[1:])
with Judge("s1023-lb", hub=e2e.hub(), key=e2e.key()) as j:
    for conv in [c for c in args.get("conv", "").split(",") if c]:
        agent = args.get("agent", "tester")
        page = j.page(P, mode="light", query=f"agent={agent}&conversation={conv}")
        page.wait_for_timeout(5000)
        main = page.locator("main").first
        print(f"\n=== CONV {conv} URL {page.url}\n", norm(main.text_content())[:2500])
        j.shot(page, f"conv_{conv}")
        page.context.close()
    for tab in [t for t in args.get("tabs", "").split(",") if t]:
        page = j.page(P, mode="light", query=f"tab={tab}")
        page.wait_for_timeout(5000)
        print(f"\n=== TAB {tab}\n", norm(page.locator("main").first.text_content())[:3500])
        j.shot(page, f"tab_{tab}", full_page=True)
        page.context.close()
    print("console errors:", j.errors[:5])
