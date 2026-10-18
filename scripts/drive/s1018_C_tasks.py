"""Sweep C: Tasks + Dependencies, operator side (no agent spend)."""
import json
import sys

from s1018_C_lib import B, api, say, transitions

state_file = __import__("pathlib").Path(__file__).with_name("s1018_C_state.json")
S = json.loads(state_file.read_text()) if state_file.exists() else {}


def save():
    state_file.write_text(json.dumps(S, indent=2))


def mk(title, **kw):
    code, t = api("POST", f"{B}/tasks", {"title": title, **kw})
    say(f"create {title}", (code, t if code >= 300 else {k: t.get(k) for k in ("id", "status", "assignee", "depends_on")}))
    return t.get("id") if isinstance(t, dict) else None


def phase1():
    say("allowed", api("GET", f"{B}/tasks/transitions/allowed"))
    a = mk("Fix median for even-length input", assignee="alpha",
           description="mathkit/stats.py median() returns the upper middle for even-length input; it must average the two middle values. tests/test_stats.py::test_median_even must pass.")
    b = mk("Add variance()", assignee="beta", depends_on=[a],
           description="Add variance(values) (population variance) to mathkit/stats.py, list it in mathkit/registry.py PUBLIC, add a test.")
    c = mk("Add stdev()", assignee="beta", depends_on=[b],
           description="Add stdev(values) = sqrt(variance) to mathkit/stats.py, list it in registry PUBLIC, add a test.")
    S.update(A=a, B=b, C=c)
    save()
    # refusals at creation
    mk("dep on ghost", depends_on=["task-nope"])
    mk("dep on self id", id="selfdep", depends_on=["selfdep"])
    mk("", assignee="alpha")
    mk("assign to operator", assignee="operator")
    mk("assign to ghost agent", assignee="ghostagent")
    mk("bad status", status="flying")
    mk("bad priority", priority="urgent!!")
    # cycle: A depends on C
    say("cycle A->C", api("POST", f"{B}/tasks/{a}/dependencies", {"depends_on": c}))
    say("self A->A", api("POST", f"{B}/tasks/{a}/dependencies", {"depends_on": a}))
    say("dup B->A", api("POST", f"{B}/tasks/{b}/dependencies", {"depends_on": a}))
    say("dep on ghost via route", api("POST", f"{B}/tasks/{b}/dependencies", {"depends_on": "task-ghost"}))
    say("remove non-dep", api("DELETE", f"{B}/tasks/{a}/dependencies/{c}"))
    # rename
    say("rename empty", api("PATCH", f"{B}/tasks/{c}", {"title": "   "}))
    say("rename ok", api("PATCH", f"{B}/tasks/{c}", {"title": "Add stdev() — population standard deviation"}))
    say("priority only keeps assignee", api("PATCH", f"{B}/tasks/{c}", {"priority": "high"}))
    say("C after", {k: api("GET", f"{B}/tasks/{c}")[1].get(k) for k in ("title", "priority", "assignee", "depends_on")})
    # Start B while A is unapproved (operator move)
    say("B pending->in_progress (A open)", api("PATCH", f"{B}/tasks/{b}", {"status": "in_progress"}))
    say("B pending->assigned (A open)", api("PATCH", f"{B}/tasks/{b}", {"status": "assigned"}))
    # transition machine walk on a scratch task
    w = mk("walk the machine", assignee="rev")
    S["W"] = w
    save()
    for st in ("approved", "completed", "assigned", "in_progress", "completed", "under_review",
               "revision_needed", "in_progress", "completed", "under_review", "approved", "pending"):
        code, res = api("PATCH", f"{B}/tasks/{w}", {"status": st})
        say(f"walk -> {st}", (code, res.get("status") if code < 300 and isinstance(res, dict) else res))
    say("walk transitions", transitions(w))
    say("walk story", api("GET", f"{B}/tasks/{w}/story"))
    say("walk transitions route", api("GET", f"{B}/tasks/{w}/transitions"))
    # delete with dependents
    say("delete A (B depends)", api("DELETE", f"{B}/tasks/{a}"))
    # list total
    say("list limit=2", {k: v for k, v in api("GET", f"{B}/tasks?limit=2")[1].items() if k != "tasks"}
        if isinstance(api("GET", f"{B}/tasks?limit=2")[1], dict) else api("GET", f"{B}/tasks?limit=2")[1])
    say("list limit=1000", api("GET", f"{B}/tasks?limit=1000")[0])
    say("board", api("GET", f"{B}/tasks/board"))
    say("ghost task get", api("GET", f"{B}/tasks/task-ghost"))
    say("ghost task story", api("GET", f"{B}/tasks/task-ghost/story"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
