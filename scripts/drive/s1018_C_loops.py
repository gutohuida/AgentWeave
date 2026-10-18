"""Sweep C: loops without spend — stop with reason, archive, adopt leftovers, control, runnerless wait."""
import json
import sys
import urllib.parse

from s1018_C_flow import PAYLOAD
from s1018_C_lib import B, api, ro, say

D = f"{B}/project"
FAR = "0 0 1 1 *"


def q(p):
    return urllib.parse.quote(p)


def adopt():
    doc = json.loads(json.dumps(PAYLOAD))
    doc["title"] = "mathkit gains median_high"
    doc["requirements"] = [{"key": "mh", "modal": "MUST", "statement": "mathkit.stats MUST provide median_high(values).", "rationale": "symmetry"},
                           {"key": "mh2", "modal": "MUST", "statement": "median_high MUST be listed in registry PUBLIC.", "rationale": "registry"}]
    doc["acceptance_criteria"] = [{"key": "a1", "requirement": "mh", "given": "[1,2,3,4]", "when": "median_high", "then": "3", "checked_by": "agent"},
                                  {"key": "a2", "requirement": "mh2", "given": "registry", "when": "read", "then": "listed", "checked_by": "agent"}]
    doc["tasks"] = [{"key": "x1", "title": "Add median_high()", "description": "Add median_high to stats.py.", "requirements": ["mh"], "files": ["mathkit/stats.py"]},
                    {"key": "x2", "title": "Register median_high", "description": "List it in registry.", "requirements": ["mh2"], "depends_on": ["x1"], "files": ["mathkit/registry.py"]}]
    doc["delivery"] = {"mode": "none"}
    code, d = api("POST", f"{D}/documents", {"title": doc["title"], "kind": "change-spec"})
    path = d["path"]
    say("write", api("PUT", f"{D}/documents/{q(path)}/content", {"document": doc})[0])
    api("POST", f"{D}/documents/close-exploration?path={q(path)}")
    api("POST", f"{D}/documents/propose?path={q(path)}")
    code, res = api("POST", f"{D}/documents/phase?path={q(path)}&to=approved", {"reason": "x", "approve_anyway": True})
    say("approve", (code, res.get("tasks_created"), (res.get("approval_outcome") or {}).get("flow")))
    did = d["id"]
    code, j1 = api("POST", f"{B}/jobs", {"name": "flow one", "agent": "beta", "message": "work", "cron": FAR,
                                         "enabled": False, "spec_document_id": did, "stop_when_queue_empties": True})
    say("flow one", (code, j1 if code >= 300 else (j1["id"], j1["loop"]["id"], j1["loop"]["queue"])))
    lid = j1["loop"]["id"]
    say("archive running loop", api("POST", f"{B}/loops/{lid}/archive"))
    say("delegate", api("POST", f"{B}/loops/{lid}/control", {"control": "creator"})[1].get("control"))
    say("take back", api("POST", f"{B}/loops/{lid}/control", {"control": "operator"})[1].get("control"))
    say("settings: clear stop condition", api("PATCH", f"{B}/jobs/{j1['id']}", {"stop_when_queue_empties": False}))
    say("settings: purpose", api("PATCH", f"{B}/jobs/{j1['id']}", {"purpose": "median_high work"})[0])
    say("stop blank reason", api("PATCH", f"{B}/jobs/{j1['id']}", {"stop_reason": "  "}))
    say("stop with reason", api("PATCH", f"{B}/jobs/{j1['id']}", {"stop_reason": "operator is re-planning"})[0])
    lp = api("GET", f"{B}/loops/{lid}")[1]
    say("loop after stop", {k: lp.get(k) for k in ("stop_reason", "ending_state", "queue")})
    say("second flow while first stopped-not-archived", api("POST", f"{B}/jobs", {"name": "flow two", "agent": "beta", "message": "work", "cron": FAR, "enabled": False, "spec_document_id": did, "stop_when_queue_empties": True}))
    say("archive job", api("POST", f"{B}/jobs/{j1['id']}/archive")[0])
    code, j2 = api("POST", f"{B}/jobs", {"name": "flow three", "agent": "beta", "message": "work", "cron": FAR,
                                         "enabled": False, "spec_document_id": did, "stop_when_queue_empties": True})
    say("flow three (adopt)", (code, j2 if code >= 300 else (j2["loop"]["id"], j2["loop"]["queue"], j2["loop"].get("current_tasks"))))
    if code < 300:
        lp = api("GET", f"{B}/loops/{j2['loop']['id']}")[1]
        say("adopt events", [(e["event_type"], e["data"]) for e in lp.get("events", [])])
        say("archive flow three", api("PATCH", f"{B}/jobs/{j2['id']}", {"stop_reason": "sweep done"})[0])
        say("archive", api("POST", f"{B}/jobs/{j2['id']}/archive")[0])


def runnerless():
    say("agent gamma", api("POST", f"{B}/agents", {"name": "gamma", "runner_id": api("GET", f"{B}/runners")[1][0]["id"]})[0])
    say("unbind", api("PATCH", f"{B}/agents/gamma", {"runner_id": None})[0])
    code, j = api("POST", f"{B}/jobs", {"name": "gamma loop", "agent": "gamma", "message": "Work the next task.", "cron": FAR, "enabled": True,
                                        "purpose": "say hi", "stop_when_queue_empties": True,
                                        "initial_tasks": [{"title": "Write HELLO.txt", "assignee": "gamma", "description": "Create HELLO.txt containing HI, commit it, complete the task."}]})
    say("gamma loop", (code, j if code >= 300 else j["id"]))
    say("run (no runner)", api("POST", f"{B}/jobs/{j['id']}/run"))
    say("job_runs", ro("select id, status, error_summary from job_runs where job_id=?", (j["id"],)))
    say("queue gamma", [(e["id"], e["state"]) for e in api("GET", f"{B}/queue/gamma")[1]])
    say("status gamma", api("GET", f"{B}/queue/gamma/status"))
    say("operator message to runnerless", api("POST", f"{B}/agent/trigger", {"agent": "gamma", "message": "Also: reply with the word READY."}))
    print(json.dumps({"gamma_job": j["id"]}))


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
