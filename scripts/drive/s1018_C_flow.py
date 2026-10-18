"""Sweep C: a flow on an approved document (parallel firing, reviewer, verdict withdrawal)."""
import json
import pathlib
import sys
import time
import urllib.parse

from s1018_C_lib import B, api, ro, say, texts

SF = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepC\state.json")
S = json.loads(SF.read_text()) if SF.exists() else {}
D = f"{B}/project"


def save():
    SF.write_text(json.dumps(S, indent=2))


PAYLOAD = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "mathkit gains spread and truncation helpers",
    "summary": "Add coefficient_of_variation() and truncate(), then list every public helper in the README.",
    "problem": "Users need relative spread and safe truncation; the README does not list the public helpers.",
    "scope": {"in_scope": ["mathkit/stats.py", "mathkit/text.py", "mathkit/registry.py", "README.md"],
              "non_goals": ["Changing existing functions"]},
    "requirements": [
        {"key": "cv", "modal": "MUST", "statement": "mathkit.stats MUST provide coefficient_of_variation(values) = population stdev / mean, raising ValueError for an empty sequence or a zero mean.", "rationale": "Relative spread."},
        {"key": "trunc", "modal": "MUST", "statement": "mathkit.text MUST provide truncate(text, n) returning text unchanged when len(text) <= n, else the first n-1 characters followed by a single ellipsis character.", "rationale": "Safe display."},
        {"key": "readme", "modal": "MUST", "statement": "README.md MUST list every name in mathkit.registry.PUBLIC under a 'Public helpers' heading.", "rationale": "Discoverability."},
    ],
    "acceptance_criteria": [
        {"key": "a-cv", "requirement": "cv", "given": "[2, 4, 4, 4, 5, 5, 7, 9]", "when": "coefficient_of_variation is called", "then": "it returns 0.4", "checked_by": "agent"},
        {"key": "a-tr", "requirement": "trunc", "given": "'abcdef' and n=4", "when": "truncate is called", "then": "it returns 'abc\u2026'", "checked_by": "agent"},
        {"key": "a-rd", "requirement": "readme", "given": "the merged library", "when": "README.md is read", "then": "every PUBLIC name appears under 'Public helpers'", "checked_by": "agent"},
    ],
    "tasks": [
        {"key": "t-cv", "title": "Add coefficient_of_variation()", "description": "Add coefficient_of_variation(values) to the END of mathkit/stats.py, append \"coefficient_of_variation\" as the LAST entry of mathkit/registry.py PUBLIC, add tests in tests/test_stats.py.", "requirements": ["cv"], "files": ["mathkit/stats.py", "mathkit/registry.py"]},
        {"key": "t-trunc", "title": "Add truncate()", "description": "Add truncate(text, n) to the END of mathkit/text.py, append \"truncate\" as the LAST entry of mathkit/registry.py PUBLIC, add tests in tests/test_text.py.", "requirements": ["trunc"], "files": ["mathkit/text.py", "mathkit/registry.py"]},
        {"key": "t-readme", "title": "List public helpers in README", "description": "Add a 'Public helpers' section to README.md listing every name in mathkit/registry.py PUBLIC.", "requirements": ["readme"], "depends_on": ["t-cv", "t-trunc"], "files": ["README.md"]},
    ],
    "algorithms": [],
    "design": "Two independent helpers, then the README. Kept small on purpose.",
    "evidence": {"checked": ["mathkit has registry.py listing PUBLIC"], "limits": []},
    "lifecycle": "one-off",
    "open_questions": [],
    "delivery": {"mode": "flow", "agent": "alpha", "reviewer": "rev", "tester": False,
                 "stop_when_queue_empties": True, "cron": "0 0 1 1 *"},
}


def q(path):
    return urllib.parse.quote(path)


def f1():
    code, doc = api("POST", f"{D}/documents", {"title": PAYLOAD["title"], "kind": "change-spec"})
    say("create", (code, doc))
    path = doc["path"]
    S["doc"] = path
    S["doc_id"] = doc.get("id")
    save()
    code, res = api("PUT", f"{D}/documents/{q(path)}/content", {"document": PAYLOAD})
    say("write", (code, res))
    say("close", api("POST", f"{D}/documents/close-exploration?path={q(path)}"))
    say("propose", api("POST", f"{D}/documents/propose?path={q(path)}"))
    code, res = api("POST", f"{D}/documents/phase?path={q(path)}&to=approved", {"reason": "sweep C flow"})
    say("approve (no anyway)", (code, res))
    if code >= 300:
        code, res = api("POST", f"{D}/documents/phase?path={q(path)}&to=approved",
                        {"reason": "sweep C flow", "approve_anyway": True})
        say("approve anyway", (code, res))
    time.sleep(3)
    say("jobs", api("GET", f"{B}/jobs"))
    say("tasks", [(t["id"], t["title"], t["status"], t.get("assignee")) for t in api("GET", f"{B}/tasks?limit=50")[1]["tasks"] if t.get("spec_document_id")])
    say("runs", ro("select id, agent, status, task_id, started_at from runs where project_id=? order by started_at desc limit 4", (S.get("P", "proj-d056068c19fb"),)))


def watch(secs=60):
    end = time.time() + secs
    while time.time() < end:
        time.sleep(10)
    status()


def status():
    say("runs", ro("select id, agent, status, task_id, substr(started_at,12,8) t from runs order by started_at desc limit 6"))
    for t in api("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        if t.get("spec_document_id"):
            print("  task", t["id"], t["title"][:30], t["status"], t.get("assignee"), t.get("dependency_state"))
    for j in api("GET", f"{B}/jobs")[1]:
        print("  job", j["id"], j["name"][:40], j.get("enabled"), j.get("run_count"), (j.get("loop") or {}).get("state"))
    for a in ("alpha", "beta", "rev"):
        qs = [e for e in api("GET", f"{B}/queue/{a}")[1] if e["state"] in ("queued",)]
        if qs:
            print("  queued", a, [(e["id"], e.get("abandoned_reason")) for e in qs])




def drive(n="6", job="job-c30a440cc6d6", loop="loop-5f953c243a85"):
    for i in range(int(n)):
        before = {r["id"] for r in ro("select id from runs")}
        code, res = api("POST", f"{B}/jobs/{job}/run")
        say(f"fire {i}", (code, res))
        time.sleep(6)
        new = [r for r in ro("select id, agent, status, task_id from runs order by started_at desc limit 4") if r["id"] not in before]
        say("new runs", new)
        for r in new:
            say(r["id"], (r["agent"], r["task_id"], __import__("s1018_C_lib").wait_run(r["id"])))
            tx = texts(r["id"])
            if tx:
                print("   LAST:", tx[-1][:400])
        status()
        lp = api("GET", f"{B}/loops/{loop}")[1]
        say("loop", {k: lp.get(k) for k in ("queue", "stop_reason", "stopped_at", "ending_state", "stall_reason", "control")})
        if lp.get("stopped_at") or (code >= 300 and not new):
            break


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
