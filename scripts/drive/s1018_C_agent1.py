"""Sweep C: agent-side task work + refusals at the actor boundary."""
import json
import pathlib
import sys

from s1018_C_lib import B, api, git, outputs, say, transitions, trigger, wait_run

SF = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\86873fe7-5c51-403e-b5ff-b44583b4da1f\scratchpad\sweepC\state.json")
S = json.loads(SF.read_text()) if SF.exists() else {}


def save():
    SF.write_text(json.dumps(S, indent=2))


def run(agent, msg, task=None, fresh=False, secs=600):
    code, res = trigger(agent, msg, task=task, fresh=fresh)
    say(f"trigger {agent}", (code, res))
    if code >= 300:
        return None
    rid = res.get("run_id")
    st = wait_run(rid, secs)
    say(f"run {rid}", st)
    outputs(rid, 400)
    return rid


def a1():
    code, t = api("POST", f"{B}/tasks", {
        "title": "Fix median for even-length input", "assignee": "alpha",
        "description": "mathkit/stats.py median() returns the upper middle value for even-length input; "
                       "it must average the two middle values. tests/test_stats.py::test_median_even must pass."})
    S["A"] = t["id"]
    say("A", t["id"])
    say("B dep A", api("POST", f"{B}/tasks/{S['B']}/dependencies", {"depends_on": S["A"]}))
    save()
    rid = run("alpha", "Work your task: fix the median bug described in it, run `py -3.11 -m pytest -q` to confirm, "
                       "commit the change with git, then move the task to completed with the AgentWeave task tool. "
                       "Do not ask me anything.", task=S["A"], fresh=True)
    S["run_a1"] = rid
    save()
    say("A after", {k: api("GET", f"{B}/tasks/{S['A']}")[1].get(k) for k in ("status", "assignee", "latest_integration")})
    say("A transitions", transitions(S["A"]))
    say("checks A", api("GET", f"{B}/tasks/{S['A']}/checks"))
    say("worktrees", api("GET", f"{B}/worktrees"))


def a2():
    """Refusals at the actor boundary, all from alpha's own run."""
    msg = (
        "Do exactly these AgentWeave task-tool calls one after another, and report the exact answer "
        "(status and message) of each, verbatim. Do not ask me anything; a refusal is an expected result, "
        "just record it and go on.\n"
        f"1. Move task {S['A']} (yours) to approved.\n"
        f"2. Move task {S['A']} to under_review.\n"
        f"3. Move task {S['B']} (beta's) to completed.\n"
        f"4. Update task {S['B']}: set assignee to alpha.\n"
        f"5. Update task {S['B']}: set priority to critical.\n"
        f"6. Update task {S['B']}: set description to 'hijacked'.\n"
        f"7. Update task {S['A']}: set title to 'renamed by alpha'.\n"
        f"8. Delete task {S['C']} if any tool lets you; otherwise say there is none."
    )
    rid = run("alpha", msg)
    S["run_a2"] = rid
    save()
    for k in ("A", "B", "C"):
        say(f"{k} after", {kk: api("GET", f"{B}/tasks/{S[k]}")[1].get(kk) for kk in ("title", "status", "assignee", "priority", "description")})




def r1():
    say("A -> under_review, assignee rev", api("PATCH", f"{B}/tasks/{S['A']}", {"status": "under_review", "assignee": "rev"}))
    rid = run("rev", "Review your task: inspect the commit on the task's branch (git log / git show in your checkout), "
                     "run `py -3.11 -m pytest -q`, and if the fix is correct move the task to approved with the AgentWeave "
                     "task tool, with a one-line verdict in notes; otherwise move it to revision_needed with the reason. "
                     "Do not ask me anything.", task=S["A"], fresh=True)
    S["run_r1"] = rid
    save()
    say("A after", {k: api("GET", f"{B}/tasks/{S['A']}")[1].get(k) for k in ("status", "assignee", "latest_integration", "notes")})
    say("A transitions", transitions(S["A"]))
    say("integrations A", api("GET", f"{B}/tasks/{S['A']}/integrations"))
    say("master log", git("log", "--oneline", "-5", "master"))


def d1():
    rid = run("beta", "Work your task: add variance(values) (population variance) to mathkit/stats.py, add it to "
                      "mathkit/registry.py PUBLIC, add a test in tests/test_stats.py, run the tests, and commit. "
                      "Do NOT mark the task completed yet; leave it in progress. Do not ask me anything.",
              task=S["B"], fresh=True)
    S["run_d1"] = rid
    save()
    say("B after", {k: api("GET", f"{B}/tasks/{S['B']}")[1].get(k) for k in ("status", "assignee")})
    say("B transitions", transitions(S["B"]))
    say("worktrees", api("GET", f"{B}/worktrees"))


def d2():
    say("reopen A (approved->revision_needed)", api("PATCH", f"{B}/tasks/{S['A']}", {"status": "revision_needed", "assignee": "alpha"}))
    say("B after reopen", {k: api("GET", f"{B}/tasks/{S['B']}")[1].get(k) for k in ("status", "dependency_state", "prerequisites")})
    say("trigger beta on B while A reopened", trigger("beta", "Continue your task.", task=S["B"]))


def d3():
    rid = run("alpha", "Your task was reopened. Rework: add a function median_low(values) to the END of mathkit/stats.py "
                       "(returns the lower of the two middle values for even-length input, the middle value otherwise), "
                       "and list \"median_low\" in mathkit/registry.py PUBLIC directly after \"median\". Run the tests, "
                       "commit, then move the task to completed. Do not ask me anything.", task=S["A"])
    S["run_d3"] = rid
    save()
    say("A", {k: api("GET", f"{B}/tasks/{S['A']}")[1].get(k) for k in ("status", "assignee")})
    say("A tr", transitions(S["A"])[-3:])


def d4():
    say("A -> under_review (operator, clear assignee)", api("PATCH", f"{B}/tasks/{S['A']}", {"status": "under_review", "assignee": None})[0])
    say("preview A", api("GET", f"{B}/tasks/{S['A']}/integration-preview"))
    code, res = api("PATCH", f"{B}/tasks/{S['A']}", {"status": "approved"})
    say("A -> approved (operator)", (code, res if code >= 300 else res.get("latest_integration")))
    say("master log", git("log", "--oneline", "-6", "master"))
    say("B preview", api("GET", f"{B}/tasks/{S['B']}/integration-preview"))
    say("B state", {k: api("GET", f"{B}/tasks/{S['B']}")[1].get(k) for k in ("status", "dependency_state", "prerequisites")})


def w1():
    code, d = api("POST", f"{B}/tasks", {"title": "Add mode()", "assignee": "alpha",
        "description": "Add mode(values) (most common value; ties -> smallest) at the END of mathkit/stats.py, and add \"mode\" to mathkit/registry.py PUBLIC as the LAST entry (after \"slugify\"). Add a test. Commit."})
    code, e = api("POST", f"{B}/tasks", {"title": "Add title_case()", "assignee": "beta",
        "description": "Add title_case(text) to mathkit/text.py, and add \"title_case\" to mathkit/registry.py PUBLIC as the LAST entry (after \"slugify\"). Add a test. Commit."})
    S["D"], S["E"] = d["id"], e["id"]
    save()
    msg = "Work your task now: implement it exactly as described, run the tests, commit, then move it to completed. Do not ask me anything."
    r1 = trigger("alpha", msg, task=S["D"], fresh=True)
    r2 = trigger("beta", msg, task=S["E"], fresh=True)
    say("triggers", (r1, r2))
    for r in (r1, r2):
        if r[0] < 300 and r[1].get("run_id"):
            say("run", (r[1]["run_id"], wait_run(r[1]["run_id"])))
    for k in ("D", "E"):
        say(k, {kk: api("GET", f"{B}/tasks/{S[k]}")[1].get(kk) for kk in ("status", "assignee")})
        say(k + " preview", api("GET", f"{B}/tasks/{S[k]}/integration-preview"))
    say("conflicts route", api("GET", f"{B}/worktrees/conflicts"))
    say("worktrees", api("GET", f"{B}/worktrees"))


if __name__ == "__main__":
    globals()[sys.argv[1]]()
