"""Reach sweep 2026-10-23, UI: beta (no tool server) with its own default "Ask me"; send a write
request from beta's composer as the operator would, with the pill untouched, and read what the run
got: was the operator asked (a card, a pending permission request), and was the file written?

  AW_P=proj-... py -3.11 scripts/drive/s1023_rc_ui_send.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rc_lib import B, P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def norm(s):
    return " ".join((s or "").split())


req("PATCH", f"{B}/agents/beta", {"default_permission_mode": "manual"})
before = {r["id"] for r in q("select id from runs where project_id=? and agent='beta'", P)}
try:
    with Judge("s1023-reach-send", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="agent=beta")
        page.wait_for_timeout(5000)
        dock = page.locator("[data-slot=composer], form").last
        print("PILL before send:", "Ask me" in norm(dock.text_content()), "|", norm(dock.text_content())[:200])
        box = page.locator("textarea").last
        box.fill("Use your Write tool to create the file pill-check.txt containing the word hi, then reply "
                 "with one line saying whether it was written or refused, quoting any refusal.")
        box.press("Enter")
        rid = None
        for _ in range(30):
            new = [r["id"] for r in q("select id from runs where project_id=? and agent='beta'", P) if r["id"] not in before]
            if new:
                rid = new[0]
                break
            time.sleep(1)
        print("RUN", rid)
        e2e.wait_for(rid, 5)
        print("STATUS", q("select status, workspace_dir from runs where id=?", rid))
        ws = pathlib.Path(q("select workspace_dir w from runs where id=?", rid)[0]["w"])
        print("FILE written:", (ws / "pill-check.txt").exists())
        st, perms = req("GET", f"{B}/permission-requests")
        print("PERMISSION REQUESTS for run:", [p for p in perms if p.get("run_id") == rid])
        out = q("select content from agent_outputs where run_id=? and kind='text' order by sequence desc limit 1", rid)
        print("REPLY", (out[0]["content"] if out else "")[:400])
        page.wait_for_timeout(2000)
        print("PILL after:", "Ask me" in norm(page.locator("[data-slot=composer], form").last.text_content()))
        j.shot(page, "01_after_send")
        print("console errors:", j.errors[:5])
finally:
    req("PATCH", f"{B}/agents/beta", {"default_permission_mode": None})
