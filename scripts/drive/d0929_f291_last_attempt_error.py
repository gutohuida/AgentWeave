"""Task 3.1 drive for an-undelivered-message-says-how-its-last-attempt-ended.

Opens the f291drive/conv-e06538d7fa11 conversation on screen (already carrying two abandoned
entries from the API-level drive), sends a THIRD message through the API while the page sits
open and untouched, and watches whether "Last attempt failed: %1 is not a valid Win32
application." appears beneath the NOT DELIVERED block live, with no reload.

    AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
        py -3.11 scripts/drive/f291_live_drive.py <agent> <conversation-id>
"""

import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import require_key  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8010")
KEY = require_key()
PROJ = os.environ["AW_PROJECT"]
AGENT, CONV = sys.argv[1], sys.argv[2]

SEED = f"""
sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {KEY!r}, hubUrl: {HUB!r}}}));
localStorage.setItem('agentweave-selected-project', {PROJ!r});
"""


def send_third_message():
    time.sleep(4)
    data = json.dumps({"to": AGENT, "content": "third live message, watch the screen"}).encode()
    req = urllib.request.Request(
        HUB + f"/api/v1/projects/{PROJ}/messages", data=data, method="POST"
    )
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"--- sent third message, status {r.status}")


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1500, "height": 1100})
    page.add_init_script(SEED)
    page.goto(HUB, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.locator(f"text={AGENT}").first.click()
    page.wait_for_timeout(1500)
    exp = page.locator(f"[data-testid='agent-expander-{PROJ}-{AGENT}']")
    print(f"--- agent expander: count={exp.count()}")
    if exp.count():
        exp.first.click()
        page.wait_for_timeout(2000)
    target = page.locator(f"[data-testid='rail-conversation-{CONV}']")
    print(f"--- rail-conversation-{CONV}: count={target.count()}")
    if not target.count():
        print("--- ABORT: the rail does not carry that conversation")
        print(page.inner_text("body")[:1500])
        b.close()
        sys.exit(2)
    target.first.click()
    page.wait_for_timeout(2500)

    before = page.inner_text("body")
    print("--- BEFORE third message ---")
    print(f"NOT DELIVERED count: {before.count('NOT DELIVERED')}")
    print(f"'Last attempt failed' count: {before.count('Last attempt failed')}")
    print(f"Win32 text present: {'Win32 application' in before}")

    t = threading.Thread(target=send_third_message)
    t.start()

    # Watch for up to 20s, no reload, for the third block to appear live.
    seen_at = None
    for i in range(20):
        page.wait_for_timeout(1000)
        body = page.inner_text("body")
        if body.count("NOT DELIVERED") >= 3 and "third live message" in body:
            seen_at = i + 1
            break
    t.join()

    after = page.inner_text("body")
    print(f"--- live update observed after ~{seen_at}s (None = never)")
    print(f"NOT DELIVERED count: {after.count('NOT DELIVERED')}")
    print(f"'Last attempt failed' count: {after.count('Last attempt failed')}")
    print(f"Win32 text present: {'Win32 application' in after}")
    print("--- tail of conversation pane ---")
    print(after[-2000:])
    page.screenshot(path=os.path.join(os.path.dirname(__file__), "f291_live_drive.png"), full_page=True)
    b.close()
