"""F21 probe (operator decision B11, 2026-09-24), on `:8010`: does a Haiku turn reach `record_evidence`?

Six Haiku turns, two per arm, each its own agent on its own task in one fresh project. Each turn is the
shape F21 was observed in: implement a small requirement, test it, commit, then record evidence.

- arm1: today's argv (a runner with no flags);
- arm2: `--strict-mcp-config` (runner flag);
- arm3: `ENABLE_TOOL_SEARCH=false`, through a runner flag `--settings {"env": {...}}`. A direct
  `claude -p` read-out showed this has the same effect as the environment variable (`ToolSearch` gone
  from `system/init`).

Per turn it reports: the run's status, whether an evidence row exists for its requirement, how many
times it called `ToolSearch`, and whether it called `record_evidence` at all. Every turn runs under
`bypassPermissions`, the same in every arm, so an approval can never stall one.

Usage: py -3.11 scripts/drive/d1008_f21_probe.py
"""

import json
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HUB = "http://127.0.0.1:8010/api/v1"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
REPO = pathlib.Path(__file__).resolve().parents[2]
HAIKU = "claude-haiku-4-5-20251001"
ARMS = {
    "arm1": [],
    "arm2": ["--strict-mcp-config"],
    "arm3": ["--settings", json.dumps({"env": {"ENABLE_TOOL_SEARCH": "false"}})],
}
AGENTS = [(f"{arm}{s}", arm) for arm in ARMS for s in ("x", "y")]


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + path, data, {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]


def ro(sql, args=()):
    connection = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return connection.execute(sql, args).fetchall()
    finally:
        connection.close()


def git(root, *args):
    out = subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                         cwd=root, capture_output=True, text=True)
    assert out.returncode == 0, (args, out.stderr)
    return out.stdout.strip()


def main():
    if len(sys.argv) > 1:
        # Round 2: the same six agents. Each one's first run reported `connected`, so this run is
        # told MCP (`launchability.described_access_path`), which is the path F21 is about.
        pid, prefix = sys.argv[1], "biggest"
        P = f"/projects/{pid}"
    else:
        prefix = "total"
        root = REPO / "testbed/drive1008-f21" / time.strftime("proj-%H%M%S")
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("A tiny ledger library.\n", encoding="utf-8")
        (root / "ledger").mkdir()
        (root / "ledger/__init__.py").write_text("", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "seed")

        _, project = api("POST", "/projects/open", {"path": str(root), "name": root.name})
        pid = project["id"]
        P = f"/projects/{pid}"
        print("project", pid, root)
        api("PATCH", P, {"main_branch": "main"})
        runners = {}
        for arm, flags in ARMS.items():
            code, runner = api("POST", f"{P}/runners", {"name": f"Haiku {arm}", "cli": "claude", "model": HAIKU,
                                                        "flags": flags})
            assert code in (200, 201), (arm, code, runner)
            runners[arm] = runner["id"]
        for name, arm in AGENTS:
            code, body = api("POST", f"{P}/agents", {"name": name, "runner_id": runners[arm]})
            assert code in (200, 201), (name, code, body)

    funcs = {name: f"{prefix}_{name}" for name, _ in AGENTS}
    _, doc = api("POST", f"{P}/project/documents", {"title": f"ledger {prefix}"})
    path = doc["path"]
    payload = {
        "schema_version": 1, "kind": doc["kind"], "title": f"ledger {prefix}", "summary": "s",
        "problem": "The ledger has no totals.", "scope": {"in_scope": ["ledger"], "non_goals": ["n"]},
        "requirements": [
            {"key": name, "modal": "MUST",
             "statement": f"`ledger.{funcs[name]}(amounts)` MUST return " + ("the sum" if prefix == "total" else "the largest") + " of a list of integers."}
            for name, _ in AGENTS
        ],
        "acceptance_criteria": [
            {"key": f"c{name}", "requirement": name, "given": "[1, 2, 3]", "when": f"{funcs[name]} is called",
             "then": "it returns 6" if prefix == "total" else "it returns 3"} for name, _ in AGENTS
        ],
        "tasks": [
            {"key": f"t{name}", "title": f"{funcs[name]}", "description": f"Implement ledger.{funcs[name]}.",
             "requirements": [name]} for name, _ in AGENTS
        ],
        "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []},
        "lifecycle": "one-off", "open_questions": [], "delivery": {"mode": "none"},
    }
    code, res = api("PUT", f"{P}/project/documents/{path}/content", {"document": payload})
    assert code == 200, (code, res)
    identifiers = res["identifiers"]
    api("POST", f"{P}/project/documents/close-exploration?path={path}")
    code, res = api("POST", f"{P}/project/documents/propose?path={path}")
    assert isinstance(res, dict) and res.get("phase") == "proposed", res
    code, res = api("POST", f"{P}/project/documents/phase?path={path}&to=approved", {"reason": "F21 probe"})
    assert code == 200, (code, res)
    _, tasks = api("GET", f"{P}/tasks")
    rows = tasks if isinstance(tasks, list) else tasks.get("tasks", tasks.get("items", []))
    task_of = {}
    for name, _ in AGENTS:
        (task,) = [t for t in rows if t["title"] == funcs[name]]
        task_of[name] = task["id"]
        code, moved = api("PATCH", f"{P}/tasks/{task['id']}", {"assignee": name})
        assert code == 200, (name, code, moved)

    runs = {}
    for name, _ in AGENTS:
        message = (
            f"Work task {task_of[name]}. Implement `{funcs[name]}(amounts)` in `ledger/__init__.py`: it "
            f"returns {'the sum' if prefix == 'total' else 'the largest'} of a list of integers. Add `tests/test_{prefix}_{name}.py` with a pytest test that "
            f"checks `{funcs[name]}([1, 2, 3]) == {6 if prefix == 'total' else 3}`, run it, and commit both files. Then record evidence "
            f"for requirement {identifiers[name]} with the passing test as its locator, and stop."
        )
        code, body = api("POST", f"{P}/agent/trigger", {
            "agent": name, "session_mode": "new", "message": message, "task_id": task_of[name],
            "overrides": {"permission_mode": "bypassPermissions"},
        })
        print("trigger", name, code, body.get("run_id") if isinstance(body, dict) else body)
        runs[name] = body.get("run_id") if isinstance(body, dict) else None
        time.sleep(2)

    deadline = time.time() + 900
    while time.time() < deadline:
        states = [ro("select status from runs where id=?", (r,)) for r in runs.values() if r]
        if all(s and s[0][0] not in ("running", "queued", "pending", "starting") for s in states):
            break
        time.sleep(10)

    print()
    print(f"{'agent':7} {'arm':5} {'status':10} {'evidence':8} {'ToolSearch':10} reached-by")
    for name, arm in AGENTS:
        run_id = runs[name]
        status = (ro("select status from runs where id=?", (run_id,)) or [("?",)])[0][0]
        evidence = ro(
            "select count(*) from requirement_evidence e join spec_requirements r on r.id = e.requirement_id "
            "where e.project_id=? and r.identifier=?", (pid, identifiers[name]))[0][0]
        outputs = ro("select coalesce(content,''), coalesce(json(payload),'') from agent_outputs "
                     "where run_id=? order by sequence", (run_id,))
        blob = "\n".join(c + "\n" + p for c, p in outputs)
        tool_search = blob.count('"tool":"ToolSearch"')
        via_mcp = '"tool":"mcp__agentweave__record_evidence"' in blob
        via_shim = "aw-tool record_evidence" in blob
        told = ro("select plane_surface, harness_mcp_status from runs where id=?", (run_id,))[0]
        print(f"{name:7} {arm:5} {status:10} {evidence:<8} {tool_search:<10} "
              f"mcp={via_mcp!s:5} shim={via_shim!s:5} told={told[0]} harness={told[1]} run={run_id}")
    print("project", pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
