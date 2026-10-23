"""2026-10-23 Flows & review drive (scratch Hub :8112): an idle holder is free for a flow.

beta holds an in-progress operator task nothing will move (no loop, no queued turn); alpha has no
runner, so if the flow withheld beta it could staff nobody. A one-task flow whose job agent is beta
fires: beta starting the work shows the holding released it (a-task-nothing-will-move-holds-nobody).

    AW_P=proj-... py -3.11 scripts/drive/s1023_lb_hold.py setup|fire|stop|clean
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lb_lib import B, DOCS, q, req, show  # noqa: E402

PATH = "spec/changes/lb-hold/spec.json"
HELD = "task-29eb33c003d0"
DOC = {
    "schema_version": 1, "kind": "change-spec", "title": "Add mode()",
    "scope": {"in_scope": ["numkit.stats"], "non_goals": ["multimodal ties"]},
    "requirements": [{"key": "mode", "statement": "numkit.stats MUST offer mode(values) returning the most common value.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c-mode", "requirement": "mode", "given": "numkit", "when": "mode([1,2,2]) runs", "then": "it returns 2", "how_to_check": "py -3.11 -c \"from numkit.stats import mode; print(mode([1,2,2]))\""}],
    "tasks": [{"key": "t-mode", "title": "Add mode()", "description": "Add mode to numkit/stats.py with a test.", "requirements": ["mode"], "files": ["numkit/stats.py"]}],
    "delivery": {"mode": "flow", "agent": "beta", "reviewer": "tester", "tester": False,
                 "stop_when_queue_empties": True, "cron": "0 0 1 1 *"},
}
STATE = pathlib.Path(__file__).with_suffix(".state.json")


def setup():
    show("PATCH", f"{B}/tasks/{HELD}", {"assignee": "beta", "status": "assigned"}, limit=300)
    show("PATCH", f"{B}/tasks/{HELD}", {"status": "in_progress"}, limit=300)
    show("PATCH", f"{B}/agents/alpha", {"runner_id": None}, limit=300)
    show("GET", f"{B}/agents", limit=100)
    for a in req("GET", f"{B}/agents")[1]:
        print("  AGENT", a["name"], a.get("runner_id"), {k: a.get(k) for k in a if "task" in k})
    show("POST", DOCS, {"path": PATH, "title": DOC["title"]}, limit=200)
    show("PUT", DOCS + f"/{PATH}/content", {"document": DOC}, limit=300)
    req("POST", f"{DOCS}/close-exploration?path={PATH}")
    req("POST", f"{DOCS}/propose?path={PATH}")
    st, out = req("POST", f"{DOCS}/phase?path={PATH}&to=approved", {"reason": "drive", "approve_anyway": True})
    flow = (out.get("approval_outcome") or {}).get("flow")
    print("approve", st, json.dumps(flow, ensure_ascii=False))
    STATE.write_text(json.dumps({"job": flow and flow.get("job_id")}))


def fire():
    job = json.loads(STATE.read_text())["job"]
    show("POST", f"{B}/jobs/{job}/run", limit=1500)
    time.sleep(6)
    for r in q("select id, agent, status, task_id from runs where status in ('running','starting')"):
        print("  LIVE", r)
    st, jobs = req("GET", f"{B}/jobs")
    for j in jobs:
        lp = j.get("loop") or {}
        print("  JOB", j["id"], lp.get("stall_reason"), lp.get("current_tasks"))


def stop():
    for r in q("select agent from runs where status in ('running','starting')"):
        show("POST", f"{B}/agent/{r['agent']}/stop", {}, limit=400)


def clean():
    job = json.loads(STATE.read_text())["job"]
    show("POST", f"{B}/jobs/{job}/archive", limit=200)


if __name__ == "__main__":
    globals()[sys.argv[1]]()
