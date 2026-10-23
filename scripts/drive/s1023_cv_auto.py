"""Conversations & composer, 2026-10-23: with no operator click, watch the live work block's own
open/close as a fresh turn streams (thinking, a slow command, more thinking, text); with the
conversation-titles job on, read the generated title; then show how beta's conversation renders the
message alpha wrote with an at-sign. Turns conversation-titles off again in `finally`.

    py -3.11 scripts/drive/s1023_cv_auto.py
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import B, P, e2e, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402

MSG = (
    "Think step by step about whether 221 is prime before doing anything. Then run this exact shell "
    "command: py -3.11 -c \"import time\nfor i in range(4): print('tock', i, flush=True); time.sleep(3)\" "
    "Then think again about whether 223 is prime. Then reply in two short lines with both answers."
)
STATE_JS = """() => [...document.querySelectorAll('details.work-disclosure')].map((d, i) => ({
  i, open: d.open, summary: (d.querySelector('summary')?.textContent || '').trim().slice(0, 50),
  expandedRows: d.querySelectorAll('button[aria-expanded=true]').length}))"""


def norm(s):
    return " ".join((s or "").split())


st, res = req("PUT", f"{B}/manager/jobs/conversation-titles", {"enabled": True})
if st >= 300:
    st, res = req("PATCH", f"{B}/manager/jobs/conversation-titles", {"enabled": True})
print("titles job on ->", st, str(res)[:200])
try:
    before = {r["id"] for r in q("select id from runs where project_id=? and agent='alpha'", P)}
    with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query="agent=alpha&conversation=__new__")
        page.wait_for_timeout(5000)
        b = page.locator("[data-slot=composer] textarea").last
        b.fill(MSG)
        b.press("Enter")
        rid = None
        for _ in range(30):
            new = [r["id"] for r in q("select id from runs where project_id=? and agent='alpha'", P) if r["id"] not in before]
            if new:
                rid = new[0]
                break
            time.sleep(1)
        print("RUN", rid)
        prev = None
        t0 = time.time()
        while time.time() - t0 < 200:
            status = q("select status from runs where id=?", rid)[0]["status"]
            blocks = page.evaluate(STATE_JS)
            hidden = page.get_by_test_id("hidden-reasoning").count()
            kinds = [r["kind"] for r in q("select kind from agent_outputs where run_id=? order by timestamp, sequence", rid)]
            snap = (json.dumps(blocks), hidden)
            if snap != prev:
                print(f"t={time.time() - t0:5.1f} run={status} hidden_lines={hidden} blocks={json.dumps(blocks)} last_kinds={kinds[-4:]}")
                prev = snap
            if status not in ("running", "queued", "starting", "pending"):
                break
            page.wait_for_timeout(700)
        j.shot(page, "auto_end")
        conv = q("select conversation_id c from runs where id=?", rid)[0]["c"]
        for _ in range(20):
            r = q("select title, title_set_by_operator from conversations where id=?", conv)[0]
            if r["title"] and not r["title"].startswith("Think step by step"):
                break
            time.sleep(3)
        print("TITLE:", q("select title, title_set_by_operator from conversations where id=?", conv))
        print("FIRINGS:", q("select event_type, substr(data,1,300) d from event_logs where project_id=? and event_type like 'manager%' order by timestamp", P))
        page.wait_for_timeout(2000)
        print("header:", norm(page.locator("[data-slot=convbar-title]").text_content()))

        page2 = j.page(P, mode="light", query="agent=beta&conversation=conv-d4ed4da7ee13")
        page2.wait_for_timeout(5000)
        main = norm(page2.locator("main").first.text_content())
        i = main.find("Hello beta")
        print("BETA CONVERSATION shows:", main[max(0, i - 80): i + 260])
        j.shot(page2, "beta_escaped_message")
        print("console errors:", j.errors[:5])
finally:
    st, res = req("PUT", f"{B}/manager/jobs/conversation-titles", {"enabled": False})
    if st >= 300:
        st, res = req("PATCH", f"{B}/manager/jobs/conversation-titles", {"enabled": False})
    print("titles job off ->", st, str(res)[:200])
