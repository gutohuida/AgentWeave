"""2026-10-23 resilience drive (scratch Hub :8113): kill the Hub with a plain conversation turn in
flight (task-bound, workspace posture), then read the reconciliation back.

    py -3.11 scripts/drive/s1023_lc_kill.py hold <task-id>
    py -3.11 scripts/drive/s1023_lc_kill.py after <run-id> <task-id>
"""

import json
import sys
import time

from s1023_lc_lib import B, P, q, req, show

SLEEP = 'py -3.11 -c "import time\nfor i in range(150): time.sleep(1)"'


def hold(tid, agent="alpha"):
    body = {
        "agent": agent,
        "message": f"Run exactly this shell command and wait for it to finish: {SLEEP} . Then reply DONE.",
        "task_id": tid,
        "overrides": {"permission_mode": "workspace"},
    }
    st, r = show("POST", f"{B}/agent/trigger", body, limit=800)
    run = r.get("run_id")
    for _ in range(50):
        time.sleep(3)
        row = q("select status from runs where id=?", run)
        outs = q("select substr(content,1,160) c from agent_outputs where run_id=? order by sequence", run)
        if row and row[0]["status"] == "running" and any(
            "time.sleep" in (o["c"] or "") or "PowerShell" in (o["c"] or "") or "Bash" in (o["c"] or "")
            for o in outs
        ):
            print("RUNNING WITH TOOL CALL", run)
            for o in outs:
                print("  OUT", o["c"])
            break
    else:
        print("never reached running+tool", q("select status, error from runs where id=?", run))
    print(json.dumps({"run": run, "conversation": r.get("conversation_id")}))


def after(run, tid, agent="alpha"):
    print("RUN", q("select id, status, exit_code, substr(error,1,400) e, started_at, ended_at, conversation_id from runs where id=?", run))
    print("RUNS(all)", q("select id, status, started_at from runs where project_id=? order by started_at", P))
    show("GET", f"{B}/tasks/{tid}", limit=900)
    show("GET", f"{B}/tasks/{tid}/transitions", limit=1500)
    st, qu = req("GET", f"{B}/queue/{agent}")
    for e in (qu if isinstance(qu, list) else [qu])[-4:]:
        print("ENTRY", json.dumps(e, ensure_ascii=False)[:500])
    for e in q("select sequence, state, origin_type, delivered_in_run_id, delivery_attempts, abandoned_reason, waiting_reason, substr(content,1,80) c from inbound_queue_entries where project_id=? and agent=? order by sequence", P, agent):
        print("QROW", e)
    for e in q("select event_type, agent, substr(data,1,300) d, severity, timestamp from event_logs where project_id=? order by timestamp desc limit 15", P):
        print("EVENT", e)
    show("GET", f"{B}/agent/sessions/{agent}", limit=1500)



def hold_free(agent="alpha"):
    """The same 150 s hold on a fresh conversation, bound to no task."""
    body = {"agent": agent, "overrides": {"permission_mode": "workspace"},
            "message": f"Run exactly this shell command and wait for it to finish: {SLEEP} . Then reply DONE."}
    st, r = show("POST", f"{B}/agent/trigger", body, limit=600)
    run = r.get("run_id")
    for _ in range(50):
        time.sleep(3)
        outs = q("select substr(content,1,160) c from agent_outputs where run_id=? order by sequence", run)
        if any("PowerShell" in (o["c"] or "") or "Bash" in (o["c"] or "") for o in outs):
            print("RUNNING WITH TOOL CALL", run, q("select status, pid from runs where id=?", run))
            break
    print(json.dumps({"run": run, "conversation": r.get("conversation_id")}))


def kill_parent_only():
    """Kill the Hub's own process and nothing under it: the agent's process survives (Windows)."""
    import pathlib, subprocess
    from s1023_lc_lib import e2e
    st = json.loads(pathlib.Path(e2e.STATE).read_text())
    print(subprocess.run(["taskkill", "/PID", str(st["pid"]), "/F"], capture_output=True, text=True).stdout)


def orphan(run, agent="alpha"):
    """After restart with the agent's process still alive: Stop, two concurrent triggers, state."""
    import concurrent.futures
    print("RUN", q("select id, status, pid, substr(error,1,200) e from runs where id=?", run))
    show("POST", f"{B}/agent/{agent}/stop", {}, limit=800)
    conv = q("select conversation_id from runs where id=?", run)[0]["conversation_id"]
    bodies = [{"agent": agent, "message": f"Concurrent probe {i}: reply ok, no tools.", "conversation_id": conv,
               "overrides": {"permission_mode": "workspace"}} for i in (1, 2)]
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        for st, r in ex.map(lambda b: req("POST", f"{B}/agent/trigger", b), bodies):
            print("TRIGGER ->", st, json.dumps(r, ensure_ascii=False)[:500])
    show("GET", f"{B}/queue/{agent}/status", limit=600)
    st, ags = req("GET", f"{B}/agents")
    print("ROSTER", [(a["name"], a["status"]) for a in ags])



def race(agent="alpha", conv=None):
    """F349 re-check: two triggers at the same moment for one idle agent; withdraw the queued one."""
    import concurrent.futures
    bodies = [{"agent": agent, "message": f"Race probe {i}: reply with the single word ok, no tools.",
               "overrides": {"permission_mode": "workspace"}, **({"conversation_id": conv} if conv else {})} for i in (1, 2)]
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        results = list(ex.map(lambda b: req("POST", f"{B}/agent/trigger", b), bodies))
    for st, r in results:
        print("TRIGGER ->", st, json.dumps(r, ensure_ascii=False)[:400])
        if st == 200 and r.get("status") == "queued" and r.get("queue_entry_id"):
            print("  withdraw", req("DELETE", f"{B}/queue/entries/{r['queue_entry_id']}")[0])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
