"""Driving sweep 4 (jobs-loops), 2026-10-13: plain jobs, a documentless loop with seeded tasks,
firing, disable, archive, the inbound queue (withdraw, release a hop-held entry), on a scratch Hub.

Every real turn binds Haiku. Jobs are created on a far-future cron ("0 0 1 1 *") and fired only by
hand through `POST /jobs/{id}/run`; `teardown` disables every job it finds, so none is left enabled.

Start a scratch Hub by hand (see sweep_client.py), then run one phase at a time:

    SWEEP_PORT=8110 SWEEP_KEY=... SWEEP_DB=... py -3.11 scripts/drive/s1013_jobs_loops_sweep.py <phase>

State between phases is kept in testbed/sweep1013-jobs/state.json.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from sweep_client import HAIKU, api, git, poll, ro, turn  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
TMP = REPO / "testbed" / "sweep1013-jobs"
STATE = TMP / "state.json"
ROOT = TMP / "proj"
FAR = "0 0 1 1 *"
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
            say(f"  {kind}", (content or "")[:400])


def settle(agent, secs=300):
    """Wait until the agent has no live run."""
    return poll(lambda: ro("select count(*) from runs where agent=? and status in "
                           "('running','queued','starting','pending')", (agent,))[0][0] == 0,
                secs, every=2)


def runs_of(agent):
    return ro("select id, status, error, started_at from runs where agent=? order by started_at",
              (agent,))


def setup():
    ROOT.mkdir(parents=True, exist_ok=True)
    git(ROOT, "init", "-q", "-b", "main")
    (ROOT / "README.md").write_text("scratch\n", encoding="utf-8")
    git(ROOT, "add", "README.md")
    git(ROOT, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(ROOT), "name": "jobsweep"})
    say("open", (code, project.get("id") if isinstance(project, dict) else project))
    base = f"/projects/{project['id']}"
    s = {"pid": project["id"], "base": base}
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    say("runner", (code, haiku.get("id")))
    s["haiku"] = haiku["id"]
    for name in ("worker", "peer", "idle"):
        say(f"agent {name}", api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]}))
    save(s)


def plain():
    """A plain job: refusals at create, disabled run, run now, history, edit, delete."""
    s = load()
    b = s["base"]
    say("bad cron", api("POST", f"{b}/jobs", {"name": "bad", "agent": "worker",
                                              "message": "x", "cron": "not a cron"}))
    say("6-field cron", api("POST", f"{b}/jobs", {"name": "six", "agent": "worker",
                                                  "message": "x", "cron": "0 0 0 1 1 *"}))
    say("unknown agent", api("POST", f"{b}/jobs", {"name": "ghost", "agent": "ghost",
                                                   "message": "x", "cron": FAR,
                                                   "enabled": False}))
    say("reserved agent", api("POST", f"{b}/jobs", {"name": "op", "agent": "operator",
                                                    "message": "x", "cron": FAR,
                                                    "enabled": False}))
    code, job = api("POST", f"{b}/jobs", {"name": "hello", "agent": "worker", "cron": FAR,
                                          "enabled": False,
                                          "message": "Reply with the single word PONG."})
    say("create disabled", (code, job))
    s["job"] = job["id"]
    save(s)
    say("run disabled", api("POST", f"{b}/jobs/{job['id']}/run"))
    say("enable", api("PATCH", f"{b}/jobs/{job['id']}", {"enabled": True}))
    say("patch bad cron", api("PATCH", f"{b}/jobs/{job['id']}", {"cron": "61 * * * *"}))
    say("patch loop field on plain", api("PATCH", f"{b}/jobs/{job['id']}",
                                         {"stop_reason": "x"}))
    code, fired = api("POST", f"{b}/jobs/{job['id']}/run")
    say("run now", (code, fired))
    say("run now again (while running)", api("POST", f"{b}/jobs/{job['id']}/run"))
    plain2()


def plain2():
    s = load()
    b = s["base"]
    job = {"id": s["job"]}
    say("job_runs", ro("select id, status, trigger, session_id, conversation_id, error_summary "
                       "from job_runs where job_id=?", (job["id"],)))
    settle("worker")
    for rid, st, err, _ in runs_of("worker"):
        say("worker run", (rid, st, err))
        outputs(rid, ("assistant", "text", "result", "error"))
    say("job after", api("GET", f"{b}/jobs/{job['id']}"))
    say("history", api("GET", f"{b}/jobs/{job['id']}/history"))
    say("queue worker", api("GET", f"{b}/queue/worker"))
    say("disable", api("PATCH", f"{b}/jobs/{job['id']}", {"enabled": False}))
    # A job whose agent loses its runner: what does run-now answer, and what does history say?
    code, j2 = api("POST", f"{b}/jobs", {"name": "norunner", "agent": "idle", "cron": FAR,
                                         "enabled": True, "message": "Reply OK."})
    s["job_norunner"] = j2["id"]
    save(s)
    say("unbind idle", api("PATCH", f"{b}/agents/idle", {"runner_id": None}))
    say("run job of runnerless agent", api("POST", f"{b}/jobs/{j2['id']}/run"))
    say("history norunner", api("GET", f"{b}/jobs/{j2['id']}/history"))
    say("queue idle", api("GET", f"{b}/queue/idle"))
    say("queue idle status", api("GET", f"{b}/queue/idle/status"))
    say("disable norunner", api("PATCH", f"{b}/jobs/{j2['id']}", {"enabled": False}))
    say("archive agent with job", api("POST", f"{b}/agents/idle/archive"))
    say("jobs", [(j["name"], j["agent"], j["enabled"], j["run_count"])
                 for j in api("GET", f"{b}/jobs")[1]])


def loop():
    """A documentless loop seeded with two tasks: fire it, watch the queue drain, stop."""
    s = load()
    b = s["base"]
    tasks = [
        {"title": "Write alpha.txt", "assignee": "worker",
         "description": "Create a file alpha.txt at the repository root containing the single "
                        "line ALPHA, commit it, then mark this task completed."},
        {"title": "Write beta.txt", "assignee": "worker",
         "description": "Create a file beta.txt at the repository root containing the single "
                        "line BETA, commit it, then mark this task completed."},
    ]
    say("loop no stop condition (operator)", api("POST", f"{b}/jobs", {
        "name": "nostop", "agent": "worker", "cron": FAR, "enabled": False,
        "message": "work", "purpose": "p"}))
    say("loop resume mode", api("POST", f"{b}/jobs", {
        "name": "resume", "agent": "worker", "cron": FAR, "enabled": False,
        "message": "work", "purpose": "p", "session_mode": "resume"}))
    say("bad initial task", api("POST", f"{b}/jobs", {
        "name": "badtask", "agent": "worker", "cron": FAR, "enabled": False, "message": "w",
        "purpose": "p", "stop_when_queue_empties": True, "initial_tasks": [{"nope": 1}]}))
    code, job = api("POST", f"{b}/jobs", {
        "name": "letters", "agent": "worker", "cron": FAR, "enabled": True,
        "message": "Work the next task on your loop's queue.",
        "purpose": "Write two letter files.", "stop_when_queue_empties": True,
        "initial_tasks": tasks})
    say("create loop", (code, job))
    s["loop_job"] = job["id"]
    s["loop_id"] = job["loop"]["id"]
    save(s)
    say("loops", api("GET", f"{b}/loops"))
    code, fired = api("POST", f"{b}/jobs/{job['id']}/run")
    say("fire 1", (code, fired))
    say("fire again while busy", api("POST", f"{b}/jobs/{job['id']}/run"))
    say("staged edit while firing", api("PATCH", f"{b}/jobs/{job['id']}",
                                        {"purpose": "Write two letter files, carefully."}))
    say("loop mid", api("GET", f"{b}/loops/{s['loop_id']}"))
    settle("worker", 400)
    for rid, st, err, _ in runs_of("worker")[-2:]:
        say("worker run", (rid, st, err))
        outputs(rid, ("tool_use", "assistant", "text", "result", "error"))
    say("loop after 1", api("GET", f"{b}/loops/{s['loop_id']}"))
    say("tasks", [(t["id"], t["title"], t["status"], t.get("assignee"))
                  for t in api("GET", f"{b}/tasks?loop_id={s['loop_id']}")[1]]
        if isinstance(api("GET", f"{b}/tasks?loop_id={s['loop_id']}")[1], list) else
        api("GET", f"{b}/tasks?loop_id={s['loop_id']}"))


def loop2():
    """Second firing, then whatever the queue then says."""
    s = load()
    b = s["base"]
    code, fired = api("POST", f"{b}/jobs/{s['loop_job']}/run")
    say("fire 2", (code, fired))
    settle("worker", 400)
    for rid, st, err, _ in runs_of("worker")[-1:]:
        say("worker run", (rid, st, err))
        outputs(rid, ("tool_use", "assistant", "text", "result", "error"))
    say("loop after 2", api("GET", f"{b}/loops/{s['loop_id']}"))
    say("tasks", api("GET", f"{b}/tasks?loop_id={s['loop_id']}"))
    say("fire 3", api("POST", f"{b}/jobs/{s['loop_job']}/run"))
    say("loop after 3", api("GET", f"{b}/loops/{s['loop_id']}"))
    say("job", api("GET", f"{b}/jobs/{s['loop_job']}"))


def queue():
    """The inbound queue: a second trigger queues, withdraw, release refusals, hop-held release."""
    s = load()
    b = s["base"]
    say("queue settings", api("GET", f"{b}/queue/settings"))
    code, r1 = api("POST", f"{b}/agent/trigger", {"agent": "worker", "message": (
        "Run the shell command `python -c \"import time; time.sleep(40)\"`, then reply DONE1.")})
    say("trigger 1", (code, r1))
    poll(lambda: ro("select count(*) from runs where agent='worker' and status='running'")[0][0],
         30)
    code, r2 = api("POST", f"{b}/agent/trigger", {"agent": "worker", "message": "Reply DONE2."})
    say("trigger 2 while running", (code, r2))
    code, r3 = api("POST", f"{b}/agent/trigger", {"agent": "worker", "message": "Reply DONE3."})
    say("trigger 3 while running", (code, r3))
    code, entries = api("GET", f"{b}/queue/worker")
    say("queue worker", (code, [(e["id"], e["state"], e["content"][:30]) for e in entries]
                         if isinstance(entries, list) else entries))
    say("queue status", api("GET", f"{b}/queue/worker/status"))
    queued = [e for e in entries if e["state"] == "queued"] if isinstance(entries, list) else []
    if queued:
        say("withdraw last", api("DELETE", f"{b}/queue/entries/{queued[-1]['id']}"))
        say("withdraw again", api("DELETE", f"{b}/queue/entries/{queued[-1]['id']}"))
        say("release a non-held entry", api("POST",
                                            f"{b}/queue/entries/{queued[0]['id']}/release"))
    say("release unknown", api("POST", f"{b}/queue/entries/nope/release"))
    settle("worker", 300)
    for rid, st, err, _ in runs_of("worker")[-3:]:
        say("worker run", (rid, st, err))
        outputs(rid, ("assistant", "text", "result"))
    code, entries = api("GET", f"{b}/queue/worker")
    say("queue after", [(e["id"], e["state"], e["delivered_in_run_id"], e["content"][:30])
                        for e in entries] if isinstance(entries, list) else entries)
    if queued:
        say("withdraw delivered", api("DELETE", f"{b}/queue/entries/{queued[0]['id']}"))


def hops():
    """hop_budget=1: worker messages peer; peer's reply to worker is held; release it."""
    s = load()
    b = s["base"]
    say("set hop_budget=1", api("PUT", f"/projects/{s['pid']}/settings", {"hop_budget": 1}))
    rid, status, _ = turn(b, "worker", (
        "Use your AgentWeave send_message tool to send the agent 'peer' the message 'Please "
        "reply to worker with the word ACK using send_message.' Then stop."))
    say("worker turn", (rid, status))
    outputs(rid, ("tool_use", "tool_result", "assistant"))
    settle("peer", 240)
    settle("worker", 240)
    say("peer runs", runs_of("peer"))
    for prid, _, _, _ in runs_of("peer"):
        outputs(prid, ("tool_use", "tool_result", "assistant"))
    code, entries = api("GET", f"{b}/queue/worker")
    say("worker queue", [(e["id"], e["state"], e["hop_depth"], e["origin_agent"],
                          e["content"][:40]) for e in entries] if isinstance(entries, list)
        else entries)
    say("worker status", api("GET", f"{b}/queue/worker/status"))
    held = [e for e in entries if e["state"] == "queued"] if isinstance(entries, list) else []
    if held:
        code, rel = api("POST", f"{b}/queue/entries/{held[0]['id']}/release")
        say("release held", (code, rel))
        settle("worker", 240)
        say("worker runs", runs_of("worker")[-1:])
        outputs(runs_of("worker")[-1][0], ("tool_use", "assistant"))
        say("release again", api("POST", f"{b}/queue/entries/{held[0]['id']}/release"))
    say("restore hop_budget", api("PUT", f"/projects/{s['pid']}/settings", {"hop_budget": 6}))


def archive():
    """Archive and delete around jobs and loops."""
    s = load()
    b = s["base"]
    say("archive loop", api("POST", f"{b}/loops/{s['loop_id']}/archive"))
    say("run archived loop job", api("POST", f"{b}/jobs/{s['loop_job']}/run"))
    say("archive job", api("POST", f"{b}/jobs/{s['job']}/archive"))
    say("run archived job", api("POST", f"{b}/jobs/{s['job']}/run"))
    say("patch archived job", api("PATCH", f"{b}/jobs/{s['job']}", {"enabled": True}))
    say("delete job", api("DELETE", f"{b}/jobs/{s['job_norunner']}"))
    say("delete again", api("DELETE", f"{b}/jobs/{s['job_norunner']}"))
    say("loops (default)", [(lp["id"], lp["label"], lp["ending_state"], lp["archived_at"])
                            for lp in api("GET", f"{b}/loops")[1]])
    say("jobs", [(j["name"], j["enabled"], j["archived_at"]) for j in api("GET", f"{b}/jobs")[1]])


def teardown():
    s = load()
    b = s["base"]
    code, jobs = api("GET", f"{b}/jobs?include_archived=true")
    for j in jobs if isinstance(jobs, list) else []:
        if j["enabled"]:
            say(f"disable {j['name']}", api("PATCH", f"{b}/jobs/{j['id']}", {"enabled": False})[0])
    say("enabled jobs", ro("select id, name from ai_jobs where enabled=1"))
    say("live runs", ro("select id, agent, status from runs where status in "
                        "('running','queued','starting','pending')"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
