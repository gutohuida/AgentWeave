"""Sweep A (2026-10-18): Questions on a live Hub. Agent turns (Haiku 4.5):

Q1: ask_user with options; the operator answers in Chromium with the number key 2 (+ Enter).
Q2: timeout 30 s, left unanswered; after the timeout the agent sleeps 60 s in Python, and the
    operator answers during it (answer after timeout, before the run ends).
Q3: the operator declines through the card's dismiss control.
Also: question timeout under 10 s refused.

    py -3.11 scripts/drive/s1018_A_questions.py <agent>
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from playwright.sync_api import sync_playwright  # noqa: E402
from s1018_A_lib import P, e2e, q, req  # noqa: E402

agent = sys.argv[1]
OUT = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepA\shots")
errors = []
print("timeout 5:", req("PATCH", f"/projects/{P}/agents/{agent}", {"question_timeout_seconds": 5}))
print("timeout 9:", req("PATCH", f"/projects/{P}/agents/{agent}", {"question_timeout_seconds": 9}))
print("timeout 0:", req("PATCH", f"/projects/{P}/agents/{agent}", {"question_timeout_seconds": 0}))


def open_page(b):
    ctx = b.new_context(viewport={"width": 1440, "height": 1000})
    ctx.add_init_script(
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s);"
        % (json.dumps(e2e.key()), json.dumps(e2e.hub()), json.dumps(P)))
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{e2e.hub()}/?project={P}", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.get_by_text(agent, exact=True).first.click()
    page.wait_for_timeout(2500)
    return page


def open_questions(run_id=None):
    s, rows = req("GET", f"/projects/{P}/questions?answered=false")
    return [r for r in rows if r["from_agent"] == agent and not r.get("declined")]


def wait_question(timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = open_questions()
        if rows:
            return rows
        time.sleep(2)
    return []


def task_status(tid):
    return q("select status from tasks where id=?", tid)[0]["status"] if tid else None


ASK = ("Call the AgentWeave tool ask_user once with one question: question 'Which colour should the "
       "release banner be?', header 'Banner', options [{label: 'Red', description: 'Loud'}, {label: "
       "'Blue', description: 'Calm'}, {label: 'Green', description: 'Fresh'}]. ")
with sync_playwright() as pw:
    b = pw.chromium.launch()
    # a task bound to the turn, to see it parked while the question is open
    s, task = req("POST", f"/projects/{P}/tasks", {"title": "Pick the banner colour", "description": "Ask the operator.", "assignee": agent})
    tid = task.get("id") if isinstance(task, dict) else None
    print("task:", s, tid)
    print("timeout 30:", req("PATCH", f"/projects/{P}/agents/{agent}", {"question_timeout_seconds": 600}))
    r1 = e2e.cmd_turn(P, agent, ASK + "Then reply with exactly the label you got back.", perm="workspace", fresh=True, task=tid)
    rows = wait_question()
    print("Q1 open:", [(r["id"], r["question"], r.get("timeout_at") or r.get("expires_at")) for r in rows])
    print("task while asking:", task_status(tid), q("select status from runs where id=?", r1))
    page = open_page(b)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "q1_card.png"))
    page.keyboard.press("2")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "q1_after_key.png"))
    sel = page.locator("[data-selected='true']").all()
    print("selected after key 2:", [x.text_content() for x in sel])
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    print("Q1 after Enter, still open:", [r["id"] for r in open_questions()])
    if open_questions():
        # fall back: click the send button
        page.locator("button[aria-label*='Send'], button:has-text('Send')").first.click()
        page.wait_for_timeout(2000)
        print("after send click, open:", [r["id"] for r in open_questions()])
    print("r1", e2e.wait_for(r1, 4))
    print("Q1 row:", q("select * from questions where id=?", rows[0]["id"]) if rows else None)
    print("task after:", task_status(tid))
    e2e.dump_turn(r1, tools=False)
    page.context.close()

    # Q2: time out, then answer during the run's tail
    print("timeout 30:", req("PATCH", f"/projects/{P}/agents/{agent}", {"question_timeout_seconds": 30}))
    r2 = e2e.cmd_turn(P, agent, ASK + "If the answer says it timed out, run exactly this with the Bash "
                      "tool: py -3.11 -c \"import time; time.sleep(60)\" and then call get_answer for that "
                      "question and reply with what it returned. Otherwise reply with the label.", perm="workspace")
    rows = wait_question()
    qid = rows[0]["id"] if rows else None
    print("Q2:", qid)
    t0 = time.time()
    while time.time() - t0 < 120:
        rr = q("select answered_at, declined, timed_out_at from questions where id=?", qid) if q("select 1 from pragma_table_info('questions') where name='timed_out_at'") else q("select * from questions where id=?", qid)
        tools = q("select content from agent_outputs where run_id=? and kind='tool_use'", r2)
        if len(tools) >= 2:
            break
        time.sleep(3)
    print("Q2 row after timeout:", q("select * from questions where id=?", qid))
    print("r2 tool calls:", tools)
    s, res = req("PATCH", f"/projects/{P}/questions/{qid}", {"answer": "Green", "labels": ["Green"]})
    print("late answer:", s, json.dumps(res)[:500])
    print("r2", e2e.wait_for(r2, 4))
    e2e.dump_turn(r2, tools=True)
    time.sleep(8)
    later = q("select id, status from runs where agent=? and project_id=? order by started_at desc limit 2", agent, P)
    print("runs after late answer:", later)
    if later and later[0]["id"] != r2:
        print("late answer started", later[0]["id"], e2e.wait_for(later[0]["id"], 4))
        e2e.dump_turn(later[0]["id"], tools=False)

    # Q3: decline from the card
    req("PATCH", f"/projects/{P}/agents/{agent}", {"question_timeout_seconds": 300})
    r3 = e2e.cmd_turn(P, agent, ASK + "Then reply with what came back, quoting it.", perm="workspace")
    rows = wait_question()
    page = open_page(b)
    page.wait_for_timeout(1500)
    if rows:
        page.locator(f"[data-testid='agent-question-decline-{rows[0]['id']}']").click()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "q3_declined.png"))
    print("r3", e2e.wait_for(r3, 4))
    print("Q3 row:", q("select * from questions where id=?", rows[0]["id"]) if rows else None)
    e2e.dump_turn(r3, tools=False)
    page.context.close()
    b.close()
print("errors:", errors[:10])
