"""2026-10-23 Questions row drive, scratch Hub (hub-up qa1023 8116).

  setup     project under testbed/drive1023qa; alpha, beta, gamma (haiku); waiting-setting refusals
  t1        beta asks (10 s wait) and ends its turn unanswered -- F909's state
  t2        beta asks (10 s wait), then sleeps 75 s; we answer after the wait, before the run ends
  ta        alpha: a cheap turn opening conversation X (older)
  t4        alpha, fresh conversation A: a three-question batch, blocking (600 s)
  probes    question refusals (unknown id, decline/answer state machine) -- read-only where possible
  t4end     wait alpha's batch run out, dump it, then the delivery turn from X
  t7        gamma: non-blocking ask, sleeps, get_answer; we answer with a label that is not an option
  state     questions, runs, conversations

  py -3.11 scripts/drive/s1023_qa_drive.py <phase>
"""

import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ.setdefault("AW_E2E_STATE", str(ROOT / "testbed" / "e2e-state-qa1023.json"))
os.environ.setdefault("AW_E2E_ROOT", str(ROOT / "testbed" / "drive1023qa"))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1023_qa_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
LIVE = ("running", "queued", "starting", "pending")
HAIKU = "claude-haiku-4-5-20251001"


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None):
    if path.startswith("~"):
        path = f"/projects/{S['P']}" + path[1:]
    return e2e.request(method, path, body)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:3000]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def trigger(agent, message, conversation=None, perm="workspace"):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if conversation:
        body["conversation_id"] = conversation
    st, res = api("POST", "~/agent/trigger", body)
    say(f"trigger {agent} -> {st}", {k: res.get(k) for k in ("run_id", "status", "conversation_id", "detail")})
    return res.get("run_id")


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        rows = ro("select status from runs where id=?", (run_id,))
        if rows and rows[0]["status"] not in LIVE:
            return rows[0]["status"]
        time.sleep(3)
    return "still-running"


def conv_of(run_id):
    return ro("select conversation_id from runs where id=?", (run_id,))[0]["conversation_id"]


def questions(answered=None):
    q = "" if answered is None else f"?answered={'true' if answered else 'false'}"
    st, rows = api("GET", "~/questions" + q)
    return rows if isinstance(rows, list) else []


QKEYS = ("id", "from_agent", "question", "blocking", "asker_waiting", "answered", "answer", "answer_labels",
         "declined", "conversation_id", "created_by_run_id")


def qshow(label, agent=None):
    rows = [q for q in questions() if agent is None or q.get("from_agent") == agent]
    say(label, [{k: q.get(k) for k in QKEYS} for q in rows])
    return rows


def qrow(qid):
    return ro("select id, answered, declined, wait_ended_at, wait_expires_at, created_at from questions where id=?", (qid,))


def attention(agent):
    st, res = api("GET", f"~/agent/{agent}/conversations")
    items = res.get("conversations", res) if isinstance(res, dict) else res
    return [{k: c.get(k) for k in ("id", "attention", "updated_at", "title")} for c in items] if isinstance(items, list) else res


def phase_setup():
    S["P"] = e2e.cmd_setup("aw-qa1023")
    save()
    for a in ("alpha", "beta", "gamma"):
        e2e.cmd_agent(S["P"], a, "-", "claude", HAIKU)
    for v in (5, 9, 0, -1, "10", True, 601, 10):
        st, res = api("PATCH", "~/agents/beta", {"question_timeout_seconds": v})
        say(f"PATCH beta question_timeout_seconds={v!r} -> {st}", res.get("detail") if st >= 300 else res.get("question_timeout_seconds"))
    say("beta row", ro("select name, question_timeout_seconds from agents where name='beta'"))
    st, res = api("PATCH", "~/agents/alpha", {"question_timeout_seconds": 600})
    say("alpha 600 ->", st)
    st, res = api("PATCH", "~/agents/gamma", {"question_timeout_seconds": 10})
    say("gamma 10 ->", st)


def phase_t1():
    run = trigger(
        "beta",
        "Call your ask_user tool now with one question: 'Ship the release on Friday?' (header 'Release'), "
        "options yes and no. If no answer comes back, reply with the single word NOANSWER and stop. Do nothing else.",
    )
    S["RUN_T1"] = run
    save()
    say("t1 run", wait_run(run, 300))
    e2e.dump_turn(run)
    rows = [q for q in qshow("beta questions after t1", "beta")]
    if rows:
        S["Q_T1"] = rows[-1]["id"]
        say("Q_T1 row", qrow(S["Q_T1"]))
    S["CONV_T1"] = conv_of(run)
    save()
    say("beta conversations attention", attention("beta"))


def phase_t1s():
    """gamma asks (blocking, 600 s) and the operator stops the run mid-wait: the wait is never reported ended."""
    say("gamma 600", api("PATCH", "~/agents/gamma", {"question_timeout_seconds": 600})[0])
    run = trigger(
        "gamma",
        "Call your ask_user tool now with one question: 'Rename the module to utils?' (header 'Rename'), "
        "options yes and no, and wait for the answer. Then reply with the answer.",
    )
    S["RUN_T1S"] = run
    save()
    qid = None
    end = time.time() + 240
    while time.time() < end and not qid:
        for q in questions(False):
            if q.get("from_agent") == "gamma":
                qid = q["id"]
        time.sleep(2)
    S["Q_T1S"] = qid
    save()
    time.sleep(5)
    say("before stop: attention", attention("gamma"))
    st, res = api("POST", "~/agent/gamma/stop", {})
    say(f"stop -> {st}", res)
    say("run after stop", wait_run(run, 120))
    time.sleep(5)
    say("Q_T1S row", qrow(qid))
    say("Q_T1S route", [{k: q.get(k) for k in QKEYS} for q in questions() if q["id"] == qid])
    say("gamma attention after stop", attention("gamma"))
    S["CONV_T1S"] = conv_of(run)
    save()


def phase_t2():
    run = trigger(
        "beta",
        "Call your ask_user tool now with one question: 'Deploy to staging today?' (header 'Deploy'), options yes "
        "and no. If no answer comes back, run this exact shell command: py -3.11 -c \"import time; time.sleep(75)\" "
        "and after it finishes reply with the single word FINISHED. Do nothing else.",
        conversation=S.get("CONV_T1"),
    )
    S["RUN_T2"] = run
    save()
    qid = None
    end = time.time() + 240
    while time.time() < end and not qid:
        for q in questions(False):
            if q.get("from_agent") == "beta" and q["id"] != S.get("Q_T1"):
                qid = q["id"]
        time.sleep(2)
    S["Q_T2"] = qid
    save()
    say("Q_T2 open", qrow(qid))
    # Wait for the wait to end (tool returned), the run still going.
    end = time.time() + 120
    while time.time() < end:
        row = qrow(qid)[0]
        st = ro("select status from runs where id=?", (run,))[0]["status"]
        if row["wait_ended_at"] or st not in LIVE:
            break
        time.sleep(2)
    say("before answer: question", qrow(qid))
    say("before answer: run", ro("select status from runs where id=?", (run,)))
    say("before answer: asker_waiting", [q.get("asker_waiting") for q in questions() if q["id"] == qid])
    time.sleep(8)
    st, res = api("PATCH", f"~/questions/{qid}", {"answer": "yes", "labels": ["yes"]})
    say(f"answer after timeout -> {st}", {k: res.get(k) for k in ("answered", "answer", "answer_labels", "asker_waiting", "detail", "delivery", "delivered_as")} if isinstance(res, dict) else res)
    say("full answer response", res)
    say("run at answer", ro("select status from runs where id=?", (run,)))
    say("queue entries beta", ro("select id, state, conversation_id, substr(content,1,200) c, delivered_in_run_id from inbound_queue_entries where agent='beta' order by sequence"))
    say("t2 run end", wait_run(run, 300))
    e2e.dump_turn(run)
    # The delivery turn.
    end = time.time() + 120
    nxt = None
    while time.time() < end and not nxt:
        rows = ro("select id, status, conversation_id from runs where agent='beta' and id not in (?, ?) order by started_at", (S["RUN_T1"], run))
        nxt = rows[-1]["id"] if rows else None
        time.sleep(3)
    say("delivery run", nxt)
    if nxt:
        S["RUN_T3"] = nxt
        save()
        say("t3 end", wait_run(nxt, 300))
        e2e.dump_turn(nxt)
        say("t3 conversation", ro("select conversation_id from runs where id=?", (nxt,)))
    say("queue entries beta after", ro("select id, state, conversation_id, substr(content,1,300) c, delivered_in_run_id from inbound_queue_entries where agent='beta' order by sequence"))


def phase_ta():
    run = trigger("alpha", "Reply with the single word OK.")
    say("ta", wait_run(run))
    S["X"] = conv_of(run)
    S["RUN_TA"] = run
    save()


def phase_t4():
    run = trigger(
        "alpha",
        "Call your ask_user tool ONCE with these three questions in one batch, blocking: "
        "1) 'Which colour for the border?' header 'Colour', options red and blue; "
        "2) 'Ship it on Friday?' header 'Ship', options yes and no; "
        "3) 'Name for the helper?' header 'Name', options double and twice. "
        "Then reply with one line per question saying exactly what came back for it (answer, declined, or nothing).",
    )
    S["RUN_T4"] = run
    save()
    end = time.time() + 240
    while time.time() < end:
        live = [q for q in questions(False) if q.get("from_agent") == "alpha"]
        if len(live) >= 3 or (live and time.time() > end - 200):
            break
        time.sleep(3)
    rows = qshow("alpha open questions", "alpha")
    S["A"] = conv_of(run)
    S["Q_A"] = [q["id"] for q in rows]
    save()
    say("A, X", [S["A"], S["X"]])
    say("alpha attention", attention("alpha"))


def phase_probes():
    say("answer unknown", api("PATCH", "~/questions/q-nope", {"answer": "x"}))
    say("decline unknown", api("POST", "~/questions/q-nope/decline"))
    say("get unknown", api("GET", "~/questions/q-nope"))
    say("answer missing body", api("PATCH", f"~/questions/{S['Q_A'][0]}", {}))
    say("answer wrong type", api("PATCH", f"~/questions/{S['Q_A'][0]}", {"answer": 5}))
    say("timeout via question create (operator POST /questions)", api("POST", "~/questions", {"from_agent": "alpha", "question": "x?", "blocking": True}))


def phase_f912():
    q3 = S["Q_A"][-1]
    st, res = api("PATCH", f"~/questions/{q3}", {"answer": "   "})
    say(f"F912 whitespace answer on {q3} -> {st}", res)
    if st >= 300:
        st, res = api("PATCH", f"~/questions/{q3}", {"answer": ""})
        say(f"F912 empty answer on {q3} -> {st}", res)
    say("Q3 row", qrow(q3))


def phase_t4end():
    say("t4 end", wait_run(S["RUN_T4"], 700))
    e2e.dump_turn(S["RUN_T4"])
    qshow("alpha questions after", "alpha")
    end = time.time() + 120
    nxt = None
    while time.time() < end and not nxt:
        rows = ro("select id, conversation_id from runs where agent='alpha' and id not in (?, ?) order by started_at", (S["RUN_TA"], S["RUN_T4"]))
        nxt = rows[-1]["id"] if rows else None
        time.sleep(3)
    say("alpha next run", nxt)
    if nxt:
        say("t5 end", wait_run(nxt, 300))
        e2e.dump_turn(nxt)
        say("t5 conv (X?)", [ro("select conversation_id from runs where id=?", (nxt,)), S["X"]])
    say("alpha queue", ro("select id, state, conversation_id, substr(content,1,300) c from inbound_queue_entries where agent='alpha' order by sequence"))


def phase_t7():
    run = trigger(
        "gamma",
        "Step 1: call your ask_user tool with blocking set to false and one question: 'Which port should the "
        "server use?' header 'Port', options 8080 and 9090. Step 2: run this exact shell command: "
        "py -3.11 -c \"import time; time.sleep(45)\" . Step 3: call your get_answer tool with the question id "
        "from step 1. Reply with exactly what get_answer returned, verbatim JSON.",
    )
    S["RUN_T7"] = run
    save()
    qid = None
    end = time.time() + 240
    while time.time() < end and not qid:
        for q in questions(False):
            if q.get("from_agent") == "gamma":
                qid = q["id"]
        time.sleep(2)
    S["Q_T7"] = qid
    save()
    say("Q_T7", [{k: q.get(k) for k in QKEYS} for q in questions() if q["id"] == qid])
    st, res = api("PATCH", f"~/questions/{qid}", {"answer": "maybe next week", "labels": ["maybe"]})
    say(f"F912 label not an option -> {st}", res)
    if st >= 300:
        st, res = api("PATCH", f"~/questions/{qid}", {"answer": "8080", "labels": ["8080"]})
        say(f"real answer -> {st}", res)
    say("t7 end", wait_run(run, 300))
    e2e.dump_turn(run)
    say("gamma runs", ro("select id, status from runs where agent='gamma' order by started_at"))


def phase_state():
    qshow("questions")
    say("question rows", ro("select id, from_agent, answered, declined, wait_ended_at, wait_expires_at, created_by_run_id from questions"))
    say("runs", ro("select id, agent, status, conversation_id, started_at, ended_at from runs order by started_at"))
    for a in ("alpha", "beta", "gamma"):
        say(f"{a} attention", attention(a))


if __name__ == "__main__":
    globals()["phase_" + sys.argv[1]]()
