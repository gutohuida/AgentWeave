"""2026-10-22 day sweep: Questions x Conversations & composer, scratch Hub (hub-up qs1022 8113).

  setup    project under testbed/drive1022q with calc.py, a binary and a 2 MB file; alpha + beta (haiku)
  convs    alpha: conversation A ("OK"), then a fresh conversation B ("BEE") -- B is the newer one
  refuse   alpha in B calls send_message to the operator (a Hub refusal, for F860's tool row)
  ask      alpha in A asks a blocking question (600 s) and is left waiting
  timeout  beta asks with a 10 s timeout and ends its turn -- an "is asking" row nobody waits on
  probes   workspace paths/file (outside, binary, huge), question refusals, rename/archive refusals
  state    questions as the route returns them, runs, conversations

  py -3.11 scripts/drive/s1022_qs_drive.py <phase>
"""

import json
import os
import pathlib
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-qs1022.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ.setdefault("AW_E2E_ROOT", str(ROOT / "testbed" / "drive1022q"))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1022_qs_state.json"
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
    print(f"--- {label}: {text[:2500]}", flush=True)


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


def phase_setup():
    d = pathlib.Path(os.environ["AW_E2E_ROOT"]) / "aw-qs1022"
    d.mkdir(parents=True, exist_ok=True)
    (d / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (d / "logo.bin").write_bytes(bytes(range(256)) * 8)
    (d / "big.txt").write_text("x" * 2_000_000, encoding="utf-8")
    (d / "notes ü.md").write_text("# Notizen\nÜber alles.\n", encoding="utf-8")
    S["P"] = e2e.cmd_setup("aw-qs1022")
    S["DIR"] = str(d)
    save()
    e2e.cmd_agent(S["P"], "alpha", "-", "claude", HAIKU)
    e2e.cmd_agent(S["P"], "beta", "-", "claude", HAIKU)


def phase_convs():
    run = trigger("alpha", "Reply with the single word OK.")
    say("A run", wait_run(run))
    S["A"] = conv_of(run)
    # No conversation_id: the trigger opens a fresh conversation (as the 10-22 traces sweep saw).
    run = trigger("alpha", "Reply with the single word BEE.")
    say("B run", wait_run(run))
    S["B"] = conv_of(run)
    say("A != B", S["A"] != S["B"])
    save()


def phase_refuse():
    run = trigger(
        "alpha",
        "Use the AgentWeave send_message tool to send the text 'hello' to the agent named operator. "
        "Then reply with exactly what the tool returned, word for word.",
        conversation=S["B"],
    )
    S["RUN_REFUSE"] = run
    save()
    say("refuse run", wait_run(run))
    e2e.dump_turn(run)


def phase_ask():
    run = trigger(
        "alpha",
        "Call the ask_user tool now to ask me exactly 'Which colour for the border?' with the options red and "
        "blue, waiting up to 600 seconds for the answer. Then reply with the colour I chose.",
        conversation=S["A"],
    )
    S["RUN_ASK"] = run
    save()
    end = time.time() + 240
    while time.time() < end:
        live = [q for q in questions(False) if q.get("from_agent") == "alpha"]
        if live:
            say("open question", {k: live[0].get(k) for k in ("id", "question", "conversation_id", "blocking", "asker_waiting")})
            S.setdefault("Q_A", live[0]["id"])
            S["Q_A2"] = live[0]["id"]
            save()
            return
        time.sleep(4)
    say("NO QUESTION", ro("select status from runs where id=?", (run,)))


def phase_timeout():
    run = trigger(
        "beta",
        "Call the ask_user tool now to ask me exactly 'Ship the release on Friday?' with the options yes and no, "
        "with a timeout of 10 seconds. If no answer comes, reply with the single word NOANSWER and stop.",
    )
    S["RUN_TO"] = run
    save()
    say("timeout run", wait_run(run, 300))
    e2e.dump_turn(run)
    for q in questions(False):
        if q.get("from_agent") == "beta":
            S["Q_B"] = q["id"]
            say("beta question after its turn", {k: q.get(k) for k in ("id", "blocking", "asker_waiting", "answered", "conversation_id")})
    save()


def phase_probes():
    for p in ("calc.py", "logo.bin", "big.txt", "notes ü.md", "../outside.txt", "C:/Windows/win.ini", "nope.py"):
        st, res = api("GET", "~/workspace/file?path=" + e2e.urllib.parse.quote(p))
        short = {k: (v if k != "content" else (v or "")[:40]) for k, v in res.items()} if isinstance(res, dict) else res
        say(f"workspace/file {p!r} -> {st}", short)
    st, paths = api("GET", "~/workspace/paths")
    say(f"workspace/paths -> {st}", paths)
    # Conversation refusals: empty title, overlong title, archive while a question is open.
    say("rename empty", api("PATCH", f"~/agent/alpha/conversations/{S['B']}", {"title": "   "}))
    say("rename 300", api("PATCH", f"~/agent/alpha/conversations/{S['B']}", {"title": "t" * 300}))
    say("rename ok", api("PATCH", f"~/agent/alpha/conversations/{S['B']}", {"title": "Refusal probe"})[0])
    say("archive A (question open)", api("POST", f"~/agent/alpha/conversations/{S['A']}/archive"))
    say("rename wrong agent", api("PATCH", f"~/agent/beta/conversations/{S['B']}", {"title": "x"}))
    # Question refusals: answer an unknown id, empty answer, a label that is not an option.
    say("answer unknown", api("PATCH", "~/questions/q-nope", {"answer": "x"}))
    if S.get("Q_A"):
        say("answer empty", api("PATCH", f"~/questions/{S['Q_A']}", {"answer": ""}))
        say("answer bad label", api("PATCH", f"~/questions/{S['Q_A']}", {"answer": "green", "labels": ["green"]}))


def phase_state():
    say("questions", [{k: q.get(k) for k in ("id", "from_agent", "question", "blocking", "asker_waiting", "answered", "declined", "conversation_id", "created_at")} for q in questions()])
    say("runs", ro("select id, agent, status, conversation_id from runs order by started_at"))
    st, convs = api("GET", "~/conversations")
    items = convs.get("conversations", convs) if isinstance(convs, dict) else convs
    say("conversations", [{k: c.get(k) for k in ("id", "agent", "title", "attention", "lifecycle", "updated_at")} for c in items] if isinstance(items, list) else items)


if __name__ == "__main__":
    {
        "setup": phase_setup, "convs": phase_convs, "refuse": phase_refuse, "ask": phase_ask,
        "timeout": phase_timeout, "probes": phase_probes, "state": phase_state,
    }[sys.argv[1]]()
