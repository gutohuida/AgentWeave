"""Drive a-footprint-names-the-line-of-work-its-commit-is-on (F165, F166) against a live Hub.

F155's shape without agent turns (operator routes only): a task whose branch has commit C, then D on
top (the conflict resolved). Operator records evidence naming C, then -- the branch having moved on --
evidence naming D, while the checkout is DETACHED at C (the old code read that as branch `HEAD`).
Reads footprints, the preview, approves, and reads the repository. Needs AW_HUB, AW_KEY.
"""
import json, os, pathlib, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api  # noqa: E402

TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"fpline-{TAG}"
root.mkdir(parents=True, exist_ok=True)


def git(*a):
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout.strip()


(root / "README.md").write_text("fp line\n", encoding="utf-8")
subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True)
git("config", "user.email", "a@example.invalid"); git("config", "user.name", "a")
git("add", "README.md"); git("commit", "-m", "base")
git("checkout", "-q", "-b", "agentweave/builder")
(root / "c.txt").write_text("c\n"); git("add", "c.txt"); git("commit", "-m", "C")
C = git("rev-parse", "HEAD")
(root / "d.txt").write_text("d\n"); git("add", "d.txt"); git("commit", "-m", "D")
D = git("rev-parse", "HEAD")
git("checkout", "-q", "--detach", C)          # the released checkout: detached at the OLDER commit
print("C", C[:12], "D", D[:12], "HEAD detached at C:", git("status", "--short", "-b"))

c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"fpline-{TAG}"})
PID = proj["id"]; A = f"/projects/{PID}"; S = f"{A}/project"
print("project", PID)
print("settings", api("PATCH", f"{A}/settings", {"main_branch": "main"})[0])
c, runner = api("POST", f"{A}/runners", {"name": f"h{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
print("agent", api("POST", f"{A}/agents", {"name": "builder", "runner_id": runner["id"]})[0])
c, doc = api("POST", f"{S}/documents", {"title": "fp line"}); path = doc["path"]
payload = {
    "schema_version": 1, "kind": doc["kind"], "title": "fp line", "summary": "One requirement.",
    "problem": "Drive fixture.", "scope": {"in_scope": ["README"], "non_goals": ["Anything else"]},
    "requirements": [{"key": "r1", "statement": "The repo MUST hold c and d.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c1", "requirement": "r1", "given": "the repo", "when": "read", "then": "c and d exist"}],
    "tasks": [{"key": "t1", "title": "Add c and d", "description": "Add them.", "requirements": ["r1"]}],
    "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
}
api("PUT", f"{S}/documents/{path}/content", {"document": payload})
api("POST", f"{S}/documents/close-exploration?path={path}")
api("POST", f"{S}/documents/propose?path={path}")
c, res = api("POST", f"{S}/documents/phase?path={path}&to=approved", {"reason": "drive"})
TASK = res["tasks_created"][0]; print("task", TASK)
print("in_progress", api("PATCH", f"{A}/tasks/{TASK}", {"assignee": "builder", "status": "in_progress"})[0])


def record(loc, summ):
    c, b = api("POST", f"{S}/spec/evidence", {"identifier": "FR-1", "document": path, "kind": "manual_observation",
                                              "locator": loc, "summary": summ, "task_id": TASK})
    fp = (b or {}).get("footprint") if isinstance(b, dict) else None
    print(f"record {loc[:12]} -> {c}; footprint={json.dumps(fp)}; latest_review={((b or {}).get('latest_review') or {}).get('decision') if isinstance(b, dict) else b}")
    return c, b


record(C, "first pass at C")
git("checkout", "-q", "--detach", C)
c2, b2 = record(D, "branch moved on; resolved at D")
print("completed", api("PATCH", f"{A}/tasks/{TASK}", {"status": "completed"}))
c, pv = api("GET", f"{A}/tasks/{TASK}/integration-preview")
print("PREVIEW", c, json.dumps(pv, indent=1)[:1600])
print("under_review", api("PATCH", f"{A}/tasks/{TASK}", {"status": "under_review"})[0])
before = git("rev-parse", "main")
c, b = api("PATCH", f"{A}/tasks/{TASK}", {"status": "approved"})
print("APPROVE", c, json.dumps(b)[:600])
time.sleep(4)
c, ints = api("GET", f"{A}/tasks/{TASK}/integrations")
print("INTEGRATIONS", json.dumps(ints, indent=1)[:1600])
print("main", before[:12], "->", git("rev-parse", "main")[:12], "| files on main:", git("ls-tree", "--name-only", "main").split())
for name, sha in (("C", C), ("D", D)):
    anc = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "main"]).returncode == 0
    print(f"{name} ancestor of main: {anc}")
