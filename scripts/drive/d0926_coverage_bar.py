"""Setup for driving the-coverage-bar-takes-the-evidence-decision-it-asks-for (F215).

Creates a git project, one Haiku builder, an approved one-requirement document, then triggers the
builder to record evidence and hold its turn open ~90s (so the bar's row is greyed while the run
lives). Prints PID/PATH/task; the browser half is d0926_coverage_bar_browser.py. Needs AW_HUB, AW_KEY.
"""
import os, pathlib, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"covbar-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("coverage bar drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)
c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"covbar-{TAG}"})
PID = proj["id"]; A = f"/projects/{PID}"; S = f"{A}/project"
c, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
api("POST", f"{A}/agents", {"name": "builder", "runner_id": runner["id"]})
c, doc = api("POST", f"{S}/documents", {"title": "coverage bar"}); path = doc["path"]
payload = {
    "schema_version": 1, "kind": doc["kind"], "title": "coverage bar", "summary": "One requirement.",
    "problem": "Drive fixture.", "scope": {"in_scope": ["README"], "non_goals": ["Anything else"]},
    "requirements": [{"key": "r1", "statement": "The README MUST mention item 1.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "the README", "when": "read", "then": "it mentions item 1"}],
    "tasks": [{"key": "t1", "title": "Check item 1", "description": "Record evidence.", "requirements": ["r1"]}],
    "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
}
show("write", *api("PUT", f"{S}/documents/{path}/content", {"document": payload}))
api("POST", f"{S}/documents/close-exploration?path={path}")
api("POST", f"{S}/documents/propose?path={path}")
c, res = api("POST", f"{S}/documents/phase?path={path}&to=approved", {"reason": "drive"})
task = res["tasks_created"][0]
api("PATCH", f"{A}/tasks/{task}", {"assignee": "builder", "status": "in_progress"})
print("PID", PID, "PATH", path, "TASK", task)
msg = (f"Use the record_evidence tool once with identifier FR-1, task_id {task}, summary 'README checked', "
       "kind manual_observation. Then run the shell command: for i in 1 2 3 4 5 6 7 8 9; do sleep 10; done, as ONE Bash call with timeout 150000 ms. Do not shorten it. Then say done.")
show("trigger", *api("POST", f"{A}/agent/trigger", {"agent": "builder", "message": msg}, timeout=90))
