"""Jobs & loops x Flows & review x Resilience sweep 2026-10-22, API phases (scratch Hub :8117, lp1022).

setup   -- a mathkit fixture, the haiku runner, agents alpha and beta
flow    -- F864 live: a flow whose own agent is also its named reviewer (alpha/alpha), two independent
           tasks on different files; the first press must staff beta only, alpha kept for review
fire / status / watch [secs] / story <task>   -- drive and read the flow back
jobs    -- job route refusals: unknown agent, bad cron, both day fields, loop with no stop condition,
           PATCH bad cron, Run on a disabled job, Run while the agent is busy (two presses)
resil   -- two concurrent triggers for one agent (F349), unknown route 404, a job whose runner is gone

py -3.11 scripts/drive/s1022_lp_drive.py <phase> [args]
"""

import ast
import copy
import json
import pathlib
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1022_lp_lib import HAIKU, P, q, req, show  # noqa: E402

B = f"projects/{P}"
D = f"{B}/project"
LIVE = ("running", "queued", "starting", "pending")
_src = (pathlib.Path(__file__).parent / "s1018_C_flow.py").read_text(encoding="utf-8")
PAYLOAD = copy.deepcopy(next(ast.literal_eval(n.value) for n in ast.parse(_src).body
                             if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PAYLOAD"))
PAYLOAD["requirements"] = PAYLOAD["requirements"][:2]
PAYLOAD["acceptance_criteria"] = PAYLOAD["acceptance_criteria"][:2]
PAYLOAD["tasks"] = PAYLOAD["tasks"][:2]
# Different files, so the two builds never collide (yesterday's registry conflict was F865's).
PAYLOAD["tasks"][0]["description"] = "Add coefficient_of_variation(values) to the END of mathkit/stats.py and a test in tests/test_stats.py."
PAYLOAD["tasks"][0]["files"] = ["mathkit/stats.py"]
PAYLOAD["tasks"][1]["description"] = "Add truncate(text, n) to the END of mathkit/text.py and a test in tests/test_text.py."
PAYLOAD["tasks"][1]["files"] = ["mathkit/text.py"]
PAYLOAD["scope"]["in_scope"] = ["mathkit/stats.py", "mathkit/text.py"]
PAYLOAD["delivery"]["reviewer"] = "alpha"
STATE = pathlib.Path.home() / ".agentweave" / "e2e-lp1022-flow.json"
S = json.loads(STATE.read_text()) if STATE.exists() else {}


def save():
    STATE.write_text(json.dumps(S, indent=1))


def qp(p):
    return urllib.parse.quote(p)


def runner_id():
    return next(r["id"] for r in req("GET", f"{B}/runners")[1] if r.get("model") == HAIKU)


def setup():
    d = pathlib.Path(q("select working_directory w from projects where id=?", P)[0]["w"])
    (d / "mathkit").mkdir(exist_ok=True)
    (d / "mathkit" / "__init__.py").write_text("", encoding="utf-8")
    (d / "mathkit" / "stats.py").write_text("def mean(values):\n    return sum(values) / len(values)\n", encoding="utf-8")
    (d / "mathkit" / "text.py").write_text("def shout(text):\n    return text.upper()\n", encoding="utf-8")
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "test_stats.py").write_text(
        "from mathkit.stats import mean\n\n\ndef test_mean():\n    assert mean([1, 2, 3]) == 2\n", encoding="utf-8")
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "mathkit"]):
        subprocess.run(["git", "-C", str(d), *args])
    st, runner = req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    print("runner", st, runner.get("id"))
    for name in ("alpha", "beta"):
        show("POST", f"{B}/agents", {"name": name, "runner_id": runner["id"]}, limit=200)


def status():
    for r in q("select id, agent, status, task_id, substr(started_at,12,8) t from runs where project_id=? order by started_at desc limit 8", P):
        print("  RUN", r)
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        print("  TASK", t["id"], t["title"][:34], t["status"], t.get("assignee"), t.get("loop_id"))
    for a in ("alpha", "beta"):
        qs = [e for e in req("GET", f"{B}/queue/{a}")[1] if e["state"] == "queued"]
        if qs:
            print("  QUEUED", a, [(e["id"], e["origin_type"], e.get("waiting_reason")) for e in qs])
    if S.get("loop"):
        lp = req("GET", f"{B}/loops/{S['loop']}")[1]
        print("  LOOP", json.dumps({k: lp.get(k) for k in ("queue", "stop_reason", "ending_state", "stall_reason", "firing_active")}, ensure_ascii=False)[:1200])
    for e in q("select event_type, substr(timestamp,12,8) t, data from event_logs where project_id=? and event_type in ('review_unstaffed','loop_stalled','review_staged') order by timestamp", P):
        print("  EVENT", e["event_type"], e["t"], e["data"][:400])


def flow():
    code, doc = req("POST", f"{D}/documents", {"title": PAYLOAD["title"], "kind": "change-spec"})
    path = doc["path"]
    S.update(doc=path, doc_id=doc.get("id")); save()
    print("write", req("PUT", f"{D}/documents/{qp(path)}/content", {"document": PAYLOAD})[0])
    print("close", req("POST", f"{D}/documents/close-exploration?path={qp(path)}")[0])
    st, res = req("POST", f"{D}/documents/propose?path={qp(path)}")
    print("propose", st, (res or {}).get("blocking"))
    st, res = req("POST", f"{D}/documents/phase?path={qp(path)}&to=approved", {"reason": "sweep lp flow", "approve_anyway": True})
    print("approve", st, json.dumps((res or {}).get("approval_outcome"), ensure_ascii=False)[:1500])
    time.sleep(4)
    jobs = req("GET", f"{B}/jobs")[1]
    fl = [j for j in jobs if (j.get("loop") or {}).get("spec_document_id") == S["doc_id"]]
    if fl:
        S.update(job=fl[0]["id"], loop=fl[0]["loop"]["id"]); save()
        print("FLOW", fl[0]["id"], fl[0]["loop"]["id"], fl[0]["enabled"], fl[0]["agent"])
    status()


def fire():
    show("POST", f"{B}/jobs/{S['job']}/run", limit=1500)
    time.sleep(6)
    status()


def watch(secs="300"):
    end = time.time() + int(secs)
    while time.time() < end:
        if not q("select count(*) n from runs where project_id=? and status in ('running','starting')", P)[0]["n"]:
            break
        time.sleep(8)
    status()


def story(tid):
    st, res = req("GET", f"{B}/tasks/{tid}/story")
    for e in res.get("events", res if isinstance(res, list) else []):
        print("  STORY", json.dumps(e, ensure_ascii=False)[:400])
    if st >= 300:
        print(st, res)


def jobs():
    base = {"name": "probe", "agent": "alpha", "message": "Reply OK.", "cron": "0 4 1 1 *", "enabled": False}
    for label, patch in (("unknown agent", {"agent": "nobody"}), ("bad cron", {"cron": "61 * * * *"}),
                         ("both day fields", {"cron": "0 4 13 * 5"}), ("blank name", {"name": "  "}),
                         ("loop no stop", {"purpose": "Work the queue"}),
                         ("loop stop_at past", {"purpose": "Work", "stop_at": "2020-01-01T00:00:00Z"})):
        st, res = req("POST", f"{B}/jobs", {**base, **patch})
        print(f"CREATE {label}: {st} {json.dumps(res, ensure_ascii=False)[:400]}")
        if st < 300:
            req("POST", f"{B}/jobs/{res['id']}/archive")
    st, job = req("POST", f"{B}/jobs", base)
    print("CREATE ok:", st, job.get("id"), job.get("enabled"))
    S["probe_job"] = job["id"]; save()
    for patch in ({"cron": "nonsense"}, {"agent": "nobody"}, {"cron": "0 4 13 * 5"}, {"name": ""}, {"bogus": 1}):
        st, res = req("PATCH", f"{B}/jobs/{job['id']}", patch)
        print(f"PATCH {patch}: {st} {json.dumps(res, ensure_ascii=False)[:300]}")
    st, res = req("POST", f"{B}/jobs/{job['id']}/run")
    print("RUN disabled:", st, json.dumps(res, ensure_ascii=False)[:400])
    for path in (f"{B}/jobs/job-nope/run", f"{B}/jobs/job-nope", f"{B}/jobs/job-nope/history"):
        st, res = req("POST" if path.endswith("run") else "GET", path)
        print("UNKNOWN", path.rsplit("/", 2)[-2:], st, json.dumps(res)[:200])


def busy_run():
    """Run an enabled one-off job twice back to back: the second press while the first turn runs."""
    jid = S["probe_job"]
    show("PATCH", f"{B}/jobs/{jid}", {"enabled": True, "message": "Reply with the single word OK."}, limit=300)
    try:
        a = req("POST", f"{B}/jobs/{jid}/run")
        b = req("POST", f"{B}/jobs/{jid}/run")
        print("RUN 1:", a[0], json.dumps(a[1], ensure_ascii=False)[:500])
        print("RUN 2:", b[0], json.dumps(b[1], ensure_ascii=False)[:500])
    finally:
        print("disable:", req("PATCH", f"{B}/jobs/{jid}", {"enabled": False})[0])
    time.sleep(3)
    print(q("select id, status, run_id, substr(error_summary,1,200) e, waiting_reason from job_runs where job_id=? order by started_at", jid))


def resil():
    # F349: two concurrent triggers for one agent.
    out = {}

    def fire_one(i):
        out[i] = req("POST", f"{B}/agent/trigger", {"agent": "beta", "message": "Reply with the single word PING."})

    th = [threading.Thread(target=fire_one, args=(i,)) for i in range(2)]
    [t.start() for t in th]
    [t.join() for t in th]
    for i, (st, res) in out.items():
        print(f"TRIGGER {i}: {st} {json.dumps(res, ensure_ascii=False)[:400]}")
    for path in ("projects/nope/jobs", f"{B}/nonexistent", f"{B}/jobs/x/y/z", "no/such/route"):
        st, res = req("GET", path)
        print("ROUTE", path, st, json.dumps(res)[:160])
    st, res = req("DELETE", f"{B}/jobs")
    print("DELETE /jobs", st, json.dumps(res)[:160])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
