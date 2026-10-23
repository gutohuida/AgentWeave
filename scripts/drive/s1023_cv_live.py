"""Conversations & composer, 2026-10-23: send from alpha's composer a turn that is refused once by the
Hub (send_message to the operator), thinks, and runs two slow commands. While it runs, watch every
work block: does one the operator opened stay open as more output streams, is it remounted, does
an expanded thinking row stay expanded? After it ends, expand the refused call's row (F860).

    py -3.11 scripts/drive/s1023_cv_live.py
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_cv_lib import P, e2e, q  # noqa: E402
from uiharness import Judge  # noqa: E402

MSG = (
    "Do these steps in order. 1) Call the AgentWeave send_message tool with to_agent set to operator "
    "and the message hi (it may be refused; keep its answer). 2) Run this exact shell command: "
    "py -3.11 -c \"import time\nfor i in range(5): print('tick', i, flush=True); time.sleep(3)\" "
    "3) Think carefully about which of 91, 97 and 99 are prime. 4) Run the same shell command again. "
    "5) Reply quoting exactly the answer step 1 got, and naming the primes."
)

STATE_JS = """() => [...document.querySelectorAll('details.work-disclosure')].map((d, i) => {
  if (d.__mark === undefined) { d.__mark = 'm' + Math.random().toString(36).slice(2, 7); }
  return {i, mark: d.__mark, open: d.open,
          summary: (d.querySelector('summary')?.textContent || '').trim().slice(0, 60),
          expandedRows: d.querySelectorAll('button[aria-expanded=true]').length,
          rows: d.querySelectorAll('button[aria-expanded]').length};
})"""


def norm(s):
    return " ".join((s or "").split())


before = {r["id"] for r in q("select id from runs where project_id=? and agent='alpha'", P)}
with Judge("s1023-conversations", hub=e2e.hub(), key=e2e.key()) as j:
    page = j.page(P, mode="light", query="agent=alpha")
    page.wait_for_timeout(5000)
    dock = page.locator("[data-slot=composer]").last
    print("COMPOSER:", norm(dock.text_content())[:300])
    box = page.locator("[data-slot=composer] textarea").last
    box.fill(MSG)
    box.press("Enter")
    rid = None
    for _ in range(30):
        new = [r["id"] for r in q("select id from runs where project_id=? and agent='alpha'", P) if r["id"] not in before]
        if new:
            rid = new[0]
            break
        time.sleep(1)
    print("RUN", rid)
    clicked = {}
    marks_seen = {}
    row_clicked = False
    t0 = time.time()
    shot_n = 0
    while time.time() - t0 < 240:
        status = q("select status from runs where id=?", rid)[0]["status"]
        blocks = page.evaluate(STATE_JS)
        for b in blocks:
            key = b["i"]
            if key in marks_seen and marks_seen[key] != b["mark"]:
                print(f"  !! block {key} REMOUNTED ({marks_seen[key]} -> {b['mark']})")
            marks_seen[key] = b["mark"]
        print(f"t={time.time()-t0:5.1f} run={status} blocks={json.dumps(blocks)}")
        # The operator opens every closed block once, and opens one thinking row by hand.
        for b in blocks:
            if b["i"] not in clicked:
                clicked[b["i"]] = b["open"]
                if not b["open"]:
                    page.locator("details.work-disclosure").nth(b["i"]).locator("summary").click()
                    print(f"  operator opened block {b['i']}")
        if not row_clicked:
            think = page.locator("details.work-disclosure button[aria-expanded=false]", has_text="Thinking")
            if think.count():
                think.first.click()
                row_clicked = True
                print("  operator expanded a Thinking row")
        if blocks and shot_n < 4 and int(time.time() - t0) % 12 < 2:
            j.shot(page, f"live_{shot_n:02d}")
            shot_n += 1
        if status not in ("running", "queued", "starting", "pending"):
            break
        page.wait_for_timeout(1500)
    page.wait_for_timeout(3000)
    print("FINAL blocks:", json.dumps(page.evaluate(STATE_JS)))
    j.shot(page, "live_end")
    # F860: expand each tool row whose header mentions aw-tool / send_message, read its body.
    rows = page.locator("details.work-disclosure button[aria-expanded]")
    print("ROWS:", [norm(rows.nth(i).text_content())[:90] for i in range(rows.count())])
    for i in range(rows.count()):
        r = rows.nth(i)
        if "send_message" in (r.text_content() or "") or "aw-tool" in (r.text_content() or ""):
            if r.get_attribute("aria-expanded") == "false":
                r.click()
            page.wait_for_timeout(500)
            body = r.locator("xpath=..").text_content()
            print("EXPANDED ROW BODY:", norm(body)[:1500])
            j.shot(page, f"f860_row_{i}", locator=r.locator("xpath=.."))
    out = q("select kind, content, payload from agent_outputs where run_id=? order by timestamp, sequence", rid)
    for o in out:
        if o["kind"] in ("tool_result",):
            print("DB tool_result:", (o["content"] or "")[:80], "| payload.output:", (json.loads(o["payload"] or "{}").get("output") or "")[:400])
        if o["kind"] == "text":
            print("DB text:", (o["content"] or "")[:600])
    print("console errors:", j.errors[:5])
