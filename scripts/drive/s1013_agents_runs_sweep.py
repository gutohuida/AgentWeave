"""Driving sweep 3 (agents-runs), 2026-10-13: runners, request_agent and the budget, ask_user,
stop, checkpoint and cut-over, archived agents, on a scratch Hub.

Every real turn binds Haiku; a Sonnet 5.5 runner is created and bound but never run. Watches the
seams: what the operator would see (the run's status, the question, the agent list) after each
step, and what each route answers when the step before it did not happen.

Start a scratch Hub by hand (see sweep_client.py), then run one phase at a time:

    SWEEP_PORT=8110 SWEEP_KEY=... SWEEP_DB=... py -3.11 scripts/drive/s1013_agents_runs_sweep.py <phase>

State between phases is kept in testbed/sweep1013-agents/state.json.
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from sweep_client import HAIKU, api, git, poll, ro, turn  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
TMP = REPO / "testbed" / "sweep1013-agents"
STATE = TMP / "state.json"
ROOT = TMP / "proj"
SONNET = "claude-sonnet-5-5"
LIVE = ("running", "queued", "starting", "pending")


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def say(label, obj=""):
    print(f"--- {label}: {obj if isinstance(obj, str) else json.dumps(obj, default=str)[:1800]}",
          flush=True)


def outputs(run_id, kinds=("tool_use", "tool_result", "assistant", "text", "error", "result")):
    for kind, content, _ in ro("select kind, content, payload from agent_outputs where run_id=? "
                               "order by sequence, timestamp", (run_id,)):
        if kind in kinds:
            say(f"  {kind}", (content or "")[:500])


def agents(s):
    code, rows = api("GET", f"{s['base']}/agents")
    return code, [{k: a.get(k) for k in ("name", "lifecycle", "runner_id", "model", "status")}
                  for a in rows] if isinstance(rows, list) else rows


def setup():
    ROOT.mkdir(parents=True, exist_ok=True)
    git(ROOT, "init", "-q", "-b", "main")
    (ROOT / "README.md").write_text("scratch\n", encoding="utf-8")
    git(ROOT, "add", "README.md")
    git(ROOT, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(ROOT), "name": "agentsweep"})
    say("open", (code, project.get("id") if isinstance(project, dict) else project))
    base = f"/projects/{project['id']}"
    s = {"pid": project["id"], "base": base}
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    say("runner haiku", (code, haiku))
    code, sonnet = api("POST", f"{base}/runners",
                       {"name": "Sonnet", "cli": "claude", "model": SONNET})
    say("runner sonnet", (code, sonnet))
    s["haiku"], s["sonnet"] = haiku["id"], sonnet["id"]
    say("agent lead (runner_id)", api("POST", f"{base}/agents",
                                      {"name": "lead", "runner_id": haiku["id"]}))
    # find-or-create: the Sonnet runner already exists; does provider+model reuse it?
    say("agent son (provider+model)", api("POST", f"{base}/agents",
                                          {"name": "son", "provider": "claude", "model": SONNET}))
    say("runners after", api("GET", f"{base}/runners"))
    say("launchability", api("GET", f"{base}/agents/launchability"))
    say("runner launchability", api("GET", f"{base}/runners/launchability"))
    say("agents", agents(s))
    save(s)


def runners():
    """Rebinding and refusals around runners."""
    s = load()
    b = s["base"]
    say("bind son to unknown runner", api("PATCH", f"{b}/agents/son", {"runner_id": "runner-nope"}))
    say("bind son to null runner", api("PATCH", f"{b}/agents/son", {"runner_id": None}))
    say("agents", agents(s))
    say("trigger son (no runner)", api("POST", f"{b}/agent/trigger",
                                       {"agent": "son", "message": "hi"}))
    say("rebind son to sonnet", api("PATCH", f"{b}/agents/son", {"runner_id": s["sonnet"]}))
    say("delete sonnet runner while bound", api("DELETE", f"{b}/runners/{s['sonnet']}"))
    say("agents after delete attempt", agents(s))
    say("bad override model", api("POST", f"{b}/agent/trigger", {
        "agent": "lead", "message": "hi", "overrides": {"model": "claude-nope-1"}}))
    say("runner patch model to unknown", api("PATCH", f"{b}/runners/{s['sonnet']}",
                                             {"model": "claude-nope-1"}))
    say("unknown cli runner", api("POST", f"{b}/runners", {"name": "X", "cli": "nope", "model": "m"}))
    say("duplicate runner name", api("POST", f"{b}/runners",
                                     {"name": "Haiku", "cli": "claude", "model": HAIKU}))


def budget():
    """request_agent: one succeeds, the budget refuses the next, archiving frees a slot."""
    s = load()
    b = s["base"]
    say("settings before", api("GET", f"/projects/{s['pid']}/settings"))
    say("set agent_budget=3", api("PUT", f"/projects/{s['pid']}/settings", {"agent_budget": 3}))
    rid, status, outs = turn(b, "lead", (
        "Use your AgentWeave tools. First call request_agent to create a new agent named "
        "'helper1' modelled on the template 'lead', with the task 'Reply with the single word "
        "READY and nothing else.'. Then call request_agent again for 'helper2' with the same "
        "template and task. Report exactly what each call returned, then stop."))
    s["budget_run"] = rid
    save(s)
    say("budget run", (rid, status))
    outputs(rid)
    say("agents", agents(s))
    poll(lambda: ro("select count(*) from runs where agent='helper1' and status not in "
                    "('running','queued','starting','pending')")[0][0] > 0, 240, every=3)
    say("helper1 runs", ro("select id, status, error, turn_depth from runs where agent='helper1'"))
    for (hid,) in ro("select id from runs where agent='helper1'"):
        outputs(hid, ("assistant", "text", "result", "error"))
    say("queue", ro("select agent, state, origin_type, hop_depth from inbound_queue_entries "
                    "where agent like 'helper%'"))


def ask():
    """ask_user answered: the run waits, the operator answers, the run reports it."""
    s = load()
    b = s["base"]
    code, run = api("POST", f"{b}/agent/trigger", {"agent": "lead", "message": (
        "Call the ask_user tool once, asking the operator 'Pick a colour' with the options "
        "red and blue. When you get the answer, reply with just the colour they picked.")})
    say("trigger", (code, run))
    rid = run["run_id"]
    got = poll(lambda: ro("select count(*) from questions where project_id=? and answer is null",
                          (s["pid"],))[0][0] > 0, 180, every=2)
    code, qs = api("GET", f"{b}/questions")
    say("questions", (got, code, qs))
    open_q = [q for q in qs if not q.get("answer")] if isinstance(qs, list) else []
    say("run while waiting", ro("select status from runs where id=?", (rid,)))
    if open_q:
        q = open_q[0]
        say("answer", api("PATCH", f"{b}/questions/{q['id']}",
                          {"answer": "blue", "labels": ["blue"]}))
        say("answer again", api("PATCH", f"{b}/questions/{q['id']}", {"answer": "red"}))
        say("decline answered", api("POST", f"{b}/questions/{q['id']}/decline"))
    poll(lambda: ro("select status from runs where id=?", (rid,))[0][0] not in LIVE, 240, every=2)
    say("run after", ro("select status, error from runs where id=?", (rid,)))
    outputs(rid)
    say("runs for lead", ro("select id, status, started_at from runs where agent='lead' "
                            "order by started_at"))


def timeout():
    """ask_user timed out: 10 s wait, nobody answers; then a late answer."""
    s = load()
    b = s["base"]
    say("set question timeout 10", api("PATCH", f"{b}/agents/lead", {"question_timeout_seconds": 10}))
    say("set question timeout 5 (below min)",
        api("PATCH", f"{b}/agents/lead", {"question_timeout_seconds": 5}))
    before = {r[0] for r in ro("select id from questions")}
    code, run = api("POST", f"{b}/agent/trigger", {"agent": "lead", "message": (
        "Call the ask_user tool once, asking 'Ship it?' with options yes and no. If no answer "
        "comes back, reply with exactly NO-ANSWER and what the tool told you.")})
    say("trigger", (code, run))
    rid = run["run_id"]
    poll(lambda: ro("select status from runs where id=?", (rid,))[0][0] not in LIVE, 300, every=2)
    say("run after", ro("select status, error from runs where id=?", (rid,)))
    outputs(rid)
    new = [r for r in ro("select id, answer, declined, wait_expires_at, wait_ended_at from questions")
           if r[0] not in before]
    say("question rows", new)
    code, qs = api("GET", f"{b}/questions")
    say("questions API", [q for q in qs if q["id"] in {n[0] for n in new}]
        if isinstance(qs, list) else qs)
    if new:
        qid = new[0][0]
        runs_before = ro("select count(*) from runs where agent='lead'")[0][0]
        say("late answer", api("PATCH", f"{b}/questions/{qid}", {"answer": "yes"}))
        time.sleep(8)
        say("runs after late answer", (runs_before,
                                       ro("select id, status from runs where agent='lead' "
                                          "order by started_at desc limit 2")))
        poll(lambda: ro("select count(*) from runs where agent='lead' and status in "
                        "('running','queued','starting','pending')")[0][0] == 0, 240, every=2)
        last = ro("select id, status from runs where agent='lead' order by started_at desc limit 1")
        say("last lead run", last)
        outputs(last[0][0], ("assistant", "text", "result", "error"))
    say("queue lead", ro("select state, origin_type, arrived_at from inbound_queue_entries "
                         "where agent='lead' order by sequence"))


def stop():
    """Stop a running turn; then the agent is usable again."""
    s = load()
    b = s["base"]
    code, run = api("POST", f"{b}/agent/trigger", {"agent": "lead", "message": (
        "Run this shell command and wait for it: python -c \"import time; time.sleep(150)\". "
        "Then reply DONE.")})
    say("trigger", (code, run))
    rid = run["run_id"]
    poll(lambda: ro("select count(*) from agent_outputs where run_id=? and kind='tool_use'",
                    (rid,))[0][0] > 0, 120, every=2)
    say("before stop", ro("select status from runs where id=?", (rid,)))
    t0 = time.time()
    say("stop", api("POST", f"{b}/agent/lead/stop"))
    poll(lambda: ro("select status from runs where id=?", (rid,))[0][0] not in LIVE, 60, every=1)
    say("after stop", (round(time.time() - t0, 1),
                       ro("select status, error, ended_at from runs where id=?", (rid,))))
    say("stop again", api("POST", f"{b}/agent/lead/stop"))
    say("events", ro("select event_type, data from event_logs where project_id=? and (event_type like '%stop%' "
                     "or event_type like 'run_%') order by timestamp desc limit 6", (s["pid"],)))
    rid2, status, _ = turn(b, "lead", "Reply with the single word AGAIN.")
    say("next turn", (rid2, status))
    outputs(rid2, ("assistant", "text", "result"))


def checkpoint():
    """Take a checkpoint on lead's conversation, cut over to a successor, continue it."""
    s = load()
    b = s["base"]
    code, convs = api("GET", f"{b}/agent/lead/conversations")
    say("conversations", (code, [{k: c.get(k) for k in ("id", "title", "status")} for c in convs]
                          if isinstance(convs, list) else convs))
    conv = convs[0]["id"]
    say("checkpoint without runner", api("POST", f"{b}/conversations/{conv}/checkpoint",
                                         timeout=180))
    say("set checkpoint runner", api("PUT", f"/projects/{s['pid']}/settings", {
        "checkpoint_runner_id": s["haiku"], "checkpoint_model": HAIKU}))
    code, cp = api("POST", f"{b}/conversations/{conv}/checkpoint", timeout=300)
    say("checkpoint", (code, cp))
    if code != 201:
        return
    s["checkpoint"] = cp["id"]
    save(s)
    say("list", api("GET", f"{b}/conversations/{conv}/checkpoints"))
    code, rendered = api("GET", f"{b}/checkpoints/{cp['id']}/rendered")
    say("rendered", (code, str(rendered)[:1200]))
    code, cut = api("POST", f"{b}/checkpoints/{cp['id']}/cutover", timeout=120)
    say("cutover", (code, cut))
    say("cutover again", api("POST", f"{b}/checkpoints/{cp['id']}/cutover", timeout=120))
    say("agents", agents(s))
    s["cut"] = cut
    save(s)


def successor():
    s = load()
    b = s["base"]
    cut = s.get("cut") or {}
    say("cut", cut)
    succ_conv = cut.get("successor_conversation_id")
    succ_agent = cut.get("agent") or cut.get("successor_agent") or "lead"
    say("queue for successor", ro("select agent, state, origin_type, conversation_id "
                                  "from inbound_queue_entries order by sequence desc limit 3"))
    if succ_conv:
        code, res = api("POST", f"{b}/conversations/{succ_conv}/continue")
        say("continue", (code, res))
        say("continue again", api("POST", f"{b}/conversations/{succ_conv}/continue"))
        poll(lambda: ro("select count(*) from runs where conversation_id=? and status not in "
                        "('running','queued','starting','pending')", (succ_conv,))[0][0] > 0,
             240, every=2)
        for rid, st in ro("select id, status from runs where conversation_id=?", (succ_conv,)):
            say("successor run", (rid, st))
            outputs(rid, ("assistant", "text", "result", "error"))
    say("agents", agents(s))
    say("old conversation", api("GET", f"{b}/agent/{succ_agent}/conversations"))


def archived():
    """Archived agents: trigger, message, template, unarchive, name reuse."""
    s = load()
    b = s["base"]
    say("archive son", api("POST", f"{b}/agents/son/archive"))
    say("trigger archived", api("POST", f"{b}/agent/trigger", {"agent": "son", "message": "hi"}))
    say("message archived", api("POST", f"{b}/messages", {
        "sender": "user", "recipient": "son", "subject": "x", "content": "hello archived"}))
    say("create same name", api("POST", f"{b}/agents", {"name": "son", "runner_id": s["haiku"]}))
    say("patch archived", api("PATCH", f"{b}/agents/son", {"description": "edited while archived"}))
    say("agents", agents(s))
    say("unarchive", api("POST", f"{b}/agents/son/unarchive"))
    say("archive with queued msg: queue",
        ro("select agent, state from inbound_queue_entries where agent='son'"))
    say("archive helper1", api("POST", f"{b}/agents/helper1/archive"))
    say("settings", api("GET", f"/projects/{s['pid']}/settings"))


def teardown():
    s = load()
    say("jobs", api("GET", f"{s['base']}/jobs"))
    say("live runs", ro("select id, agent, status from runs where status in "
                        "('running','queued','starting','pending')"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
