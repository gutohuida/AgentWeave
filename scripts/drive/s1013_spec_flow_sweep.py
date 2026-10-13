"""Driving sweep 2 (spec-flow), 2026-10-13: one change from creation to its capability, on a scratch Hub.

create (Hub-minted name) -> write while exploring -> close exploration -> propose -> approve (the
409 gap list) -> approve anyway -> tasks -> a Haiku agent builds one -> evidence -> land -> fold
into a capability; then amend an approved document. Watches the seams between the steps: what the
board, coverage and the document say after each, and what each route answers when the step before
it did not happen.

Start a scratch Hub by hand (see sweep_client.py), then run one phase at a time:

    SWEEP_PORT=8110 SWEEP_KEY=... SWEEP_DB=... py -3.11 scripts/drive/s1013_spec_flow_sweep.py <phase>

State between phases is kept in testbed/sweep1013-spec/state.json.
"""

import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from sweep_client import HAIKU, api, git, ro  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
TMP = REPO / "testbed" / "sweep1013-spec"
STATE = TMP / "state.json"
ROOT = TMP / "proj"
CAPABILITY = "spec/capabilities/calculator/spec.json"

CALC = '''import sys


def add(a, b):
    return a + b


def land():
    """Land the built task; the gated second task should then be startable."""
    s = load()
    P = s["base"] + "/project"
    first, second = s["tasks"]
    say("land second (gated, not started)", api("POST", f"{s['base']}/tasks/{second}/land"))
    say("land first", api("POST", f"{s['base']}/tasks/{first}/land"))
    say("second after", api("GET", f"{s['base']}/tasks/{second}"))
    say("coverage after land", api("GET", f"{P}/spec/coverage"))
    say("document", api("GET", f"{P}/documents?path={q(s['doc'])}"))


def fold():
    """A capability, then fold the change into it."""
    s = load()
    P = s["base"] + "/project"
    say("create capability", api("POST", f"{P}/documents",
                                 {"title": "Calculator", "kind": "capability", "path": CAPABILITY}))
    cap = payload("capability", "Calculator", [
        {"key": "add", "statement": "`python calc.py A B` MUST print A plus B.", "modal": "MUST"},
    ], [], [])
    say("capability direct write", api("PUT", f"{P}/documents/{CAPABILITY}/content",
                                       {"document": cap}))
    say("capability merge", api("POST", f"{P}/documents/{CAPABILITY}/merge",
                                {"payload": cap, "from_changes": []}))
    say("fold draft", api("GET", f"{P}/documents/{s['doc']}/fold-draft?into={q(CAPABILITY)}"))
    say("fold", api("POST", f"{P}/documents/{s['doc']}/fold", {"into": CAPABILITY}))
    say("coverage after fold", api("GET", f"{P}/spec/coverage"))
    say("requirements after fold", api("GET", f"{P}/spec/requirements"))


if __name__ == "__main__":
    print(add(int(sys.argv[1]), int(sys.argv[2])))
'''


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def say(label, obj=""):
    print(f"--- {label}: {obj if isinstance(obj, str) else json.dumps(obj, default=str)[:1800]}",
          flush=True)


def q(path):
    return urllib.parse.quote(path, safe="")


def payload(kind, title, requirements, criteria, tasks):
    body = {
        "schema_version": 1, "kind": kind, "title": title,
        "summary": "A subtract command for the calculator.",
        "problem": "calc.py can only add.",
        "scope": {"in_scope": ["calc.py"], "non_goals": ["Floats"]},
        "requirements": requirements, "acceptance_criteria": criteria, "tasks": tasks,
        "algorithms": [], "design": "", "evidence": {"checked": ["calc.py only adds"], "limits": []},
        "lifecycle": "one-off", "open_questions": [],
    }
    if kind == "change-spec":
        body["delivery"] = {"mode": "none"}
    return body


CHANGE_REQS = [
    {"key": "subtract", "statement": "`python calc.py sub A B` MUST print A minus B.",
     "modal": "MUST"},
    {"key": "help", "statement": "`python calc.py` with no arguments SHOULD print a usage line.",
     "modal": "SHOULD"},
]
CHANGE_CRITERIA = [
    {"key": "subtract-c", "requirement": "subtract", "given": "calc.py",
     "when": "`python calc.py sub 5 3` runs", "then": "it prints 2"},
]
CHANGE_TASKS = [
    {"key": "sub", "title": "Add the sub command", "description": "Add `sub A B` to calc.py.",
     "requirements": ["subtract"], "files": ["calc.py"]},
    {"key": "usage", "title": "Print usage with no arguments", "description": "Usage line.",
     "requirements": ["help"], "files": ["calc.py"], "depends_on": ["sub"]},
]


def setup():
    ROOT.mkdir(parents=True, exist_ok=True)
    git(ROOT, "init", "-q", "-b", "main")
    (ROOT / "calc.py").write_text(CALC, encoding="utf-8")
    git(ROOT, "add", "calc.py")
    git(ROOT, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(ROOT), "name": "specsweep"})
    say("open", (code, project.get("id") if isinstance(project, dict) else project))
    base = f"/projects/{project['id']}"
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    say("runner", (code, runner.get("id")))
    code, agent = api("POST", f"{base}/agents", {"name": "builder", "runner_id": runner["id"]})
    say("agent", (code, str(agent)[:200]))
    save({"pid": project["id"], "base": base, "runner": runner["id"]})


def create():
    """A Hub-minted document, written while exploring, closed, proposed."""
    s = load()
    P = s["base"] + "/project"
    code, doc = api("POST", f"{P}/documents", {"title": "Calculator subtract", "kind": "change-spec"})
    say("create (minted)", (code, doc))
    path = doc["path"]
    s["doc"] = path
    save(s)
    body = payload("change-spec", "Calculator subtract", CHANGE_REQS, CHANGE_CRITERIA, CHANGE_TASKS)
    say("write while exploring", api("PUT", f"{P}/documents/{path}/content", {"document": body}))
    say("propose before closing", api("POST", f"{P}/documents/propose?path={q(path)}"))
    say("close exploration", api("POST", f"{P}/documents/close-exploration?path={q(path)}"))
    say("propose", api("POST", f"{P}/documents/propose?path={q(path)}"))
    say("tasks before approval", api("GET", f"{s['base']}/tasks"))
    say("coverage proposed", api("GET", f"{P}/spec/coverage"))


def approve():
    s = load()
    P = s["base"] + "/project"
    path = s["doc"]
    say("approve (expect gaps)", api("POST", f"{P}/documents/phase?path={q(path)}&to=approved", {}))
    code, res = api("POST", f"{P}/documents/phase?path={q(path)}&to=approved",
                    {"approve_anyway": True, "reason": "sweep"})
    say("approve anyway", (code, res))
    s["tasks"] = res.get("tasks_created") if isinstance(res, dict) else None
    save(s)
    say("approve again", api("POST", f"{P}/documents/phase?path={q(path)}&to=approved",
                             {"approve_anyway": True}))
    code, tasks = api("GET", f"{s['base']}/tasks")
    say("tasks", (code, [{k: t.get(k) for k in ("id", "title", "status", "assignee", "depends_on",
                                                  "spec_document")}
                         for t in (tasks.get("tasks") if isinstance(tasks, dict) else tasks) or []]))
    say("board", api("GET", f"{s['base']}/tasks/board"))
    say("coverage approved", api("GET", f"{P}/spec/coverage"))
    say("requirements", api("GET", f"{P}/spec/requirements"))


def build():
    """The Haiku agent builds the first task through the real tool surface."""
    s = load()
    task = s["tasks"][0]
    code, run = api("POST", f"{s['base']}/agent/trigger", {
        "agent": "builder", "task_id": task,
        "overrides": {"permission_mode": "workspace"},
        "message": "Build your task: add a `sub A B` command to calc.py so `python calc.py sub 5 3`"
                   " prints 2. Commit it on your branch, record evidence for the requirement with"
                   " the spec evidence tool naming the commit, and mark the task completed.",
    })
    say("trigger", (code, run))
    s["run"] = run.get("run_id") if isinstance(run, dict) else None
    save(s)


def after():
    s = load()
    P = s["base"] + "/project"
    rid = s.get("run")
    if rid:
        say("run", ro("select status, error from runs where id=?", (rid,)))
        for kind, content, _ in ro("select kind, content, payload from agent_outputs where run_id=? "
                                   "order by sequence, timestamp", (rid,)):
            if kind in ("tool_use", "tool_result", "assistant", "text", "error", "result"):
                say(kind, (content or "")[:600])
    for t in s.get("tasks") or []:
        say(f"task {t}", api("GET", f"{s['base']}/tasks/{t}"))
        say(f"transitions {t}", api("GET", f"{s['base']}/tasks/{t}/transitions"))
    say("evidence", api("GET", f"{P}/spec/evidence?document={q(s['doc'])}"))
    say("coverage", api("GET", f"{P}/spec/coverage"))


def land():
    """Land the built task; the gated second task should then be startable."""
    s = load()
    P = s["base"] + "/project"
    first, second = s["tasks"]
    say("land second (gated, not started)", api("POST", f"{s['base']}/tasks/{second}/land"))
    say("land first", api("POST", f"{s['base']}/tasks/{first}/land"))
    say("second after", api("GET", f"{s['base']}/tasks/{second}"))
    say("coverage after land", api("GET", f"{P}/spec/coverage"))
    say("document", api("GET", f"{P}/documents?path={q(s['doc'])}"))


def fold():
    """A capability, then fold the change into it."""
    s = load()
    P = s["base"] + "/project"
    say("create capability", api("POST", f"{P}/documents",
                                 {"title": "Calculator", "kind": "capability", "path": CAPABILITY}))
    cap = payload("capability", "Calculator", [
        {"key": "add", "statement": "`python calc.py A B` MUST print A plus B.", "modal": "MUST"},
    ], [], [])
    say("capability direct write", api("PUT", f"{P}/documents/{CAPABILITY}/content",
                                       {"document": cap}))
    say("capability merge", api("POST", f"{P}/documents/{CAPABILITY}/merge",
                                {"payload": cap, "from_changes": []}))
    say("fold draft", api("GET", f"{P}/documents/{s['doc']}/fold-draft?into={q(CAPABILITY)}"))
    say("fold", api("POST", f"{P}/documents/{s['doc']}/fold", {"into": CAPABILITY}))
    say("coverage after fold", api("GET", f"{P}/spec/coverage"))
    say("requirements after fold", api("GET", f"{P}/spec/requirements"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
