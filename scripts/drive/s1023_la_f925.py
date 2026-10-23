"""Jobs & loops drive 2026-10-23 (scratch Hub :8111, la1023): F925 re-drive.

setup  -- haiku runner; agents alpha, gone1, arch1; per gone agent: a disabled job, an enabled job
          (far cron) and an enabled documentless loop. Then a sync that drops gone1, and arch1 archived.
probe  -- enable (want 400 with the create's sentence), Run now (want 409), rows/events/queue/convs
recreate -- POST /agents gone1 again: does it find anything queued
sweep  -- archive every job left (never leave one enabled)

py -3.11 scripts/drive/s1023_la_f925.py <phase>
"""

import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1023_la_lib import HAIKU, P, q, req, show  # noqa: E402

B = f"projects/{P}"
FAR = "0 0 1 1 *"


def runner_id():
    rs = [r for r in req("GET", f"{B}/runners")[1] if r.get("model") == HAIKU]
    if rs:
        return rs[0]["id"]
    return req("POST", f"{B}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})[1]["id"]


def jobs_by_name():
    return {j["name"]: j for j in req("GET", f"{B}/jobs?include_archived=true")[1]}


def setup():
    rid = runner_id()
    for n in ("alpha", "gone1", "arch1"):
        show("POST", f"{B}/agents", {"name": n, "runner_id": rid}, 200)
    for a in ("gone1", "arch1"):
        show("POST", f"{B}/jobs", {"name": f"{a} off", "agent": a, "message": "Say hi.", "cron": FAR, "enabled": False}, 300)
        show("POST", f"{B}/jobs", {"name": f"{a} on", "agent": a, "message": "Say hi.", "cron": FAR, "enabled": True}, 300)
        show("POST", f"{B}/jobs", {"name": f"{a} loop", "agent": a, "message": "Work the next task.", "cron": FAR,
                                   "enabled": True, "purpose": "f925", "stop_when_queue_empties": True,
                                   "initial_tasks": [{"title": f"{a} task", "description": "Write X.txt."}]}, 300)
    show("POST", f"{B}/session/sync", {"data": {"agents": {"alpha": {}, "arch1": {}}}}, 1500)
    show("POST", f"{B}/agents/arch1/archive", None, 1500)
    print("AGENTS", q("select name, lifecycle from agents where project_id=?", P))


def snapshot(tag):
    print(f"--- {tag}")
    print("JOB_RUNS", q("select j.name, r.status, r.trigger, substr(r.error_summary,1,160) e, r.tick_count from job_runs r join ai_jobs j on j.id=r.job_id where j.project_id=? order by r.fired_at", P))
    print("EVENTS", [(e["event_type"], e["data"][:220]) for e in q("select event_type, data from event_logs where project_id=? and event_type like 'job_%' order by timestamp", P)])
    print("QUEUE", q("select agent, state, substr(content,1,60) b, job_id from inbound_queue_entries where project_id=? and agent in ('gone1','arch1')", P))
    print("CONVS", q("select agent, lifecycle, title from conversations where project_id=? and agent in ('gone1','arch1')", P))
    print("RUNS", q("select agent, status from runs where project_id=? and agent in ('gone1','arch1')", P))
    print("TASKS", q("select title, status, assignee from tasks where project_id=?", P))


def probe():
    js = jobs_by_name()
    for a in ("gone1", "arch1"):
        show("PATCH", f"{B}/jobs/{js[a + ' off']['id']}", {"enabled": True}, 800)
        show("PATCH", f"{B}/jobs/{js[a + ' off']['id']}", {"enabled": True, "agent": a}, 800)
        show("POST", f"{B}/jobs/{js[a + ' on']['id']}/run", None, 800)
        show("POST", f"{B}/jobs/{js[a + ' loop']['id']}/run", None, 800)
        show("POST", f"{B}/jobs/{js[a + ' loop']['id']}/run", None, 800)
    snapshot("after probe")


def recreate():
    show("POST", f"{B}/agents", {"name": "gone1", "runner_id": runner_id()}, 400)
    show("GET", f"{B}/queue/gone1", None, 1200)
    snapshot("after recreate")


def sweep():
    for j in req("GET", f"{B}/jobs?include_archived=true")[1]:
        if not j.get("archived_at"):
            print("archive", j["name"], req("POST", f"{B}/jobs/{j['id']}/archive")[0])
    print("ENABLED LEFT", q("select name from ai_jobs where project_id=? and enabled=1 and archived_at is null", P))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
