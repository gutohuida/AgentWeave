"""Acceptance drive for `a-name-a-caller-chooses-reaches-its-own-resource` (F248), 2026-10-10.

The change's `drive` criterion (spdoc-4e1fa307cd4e on :8010, task drive-first). Starts its own Hub on
:8107 with a fresh database (never :8000 or :8010). No agent turn is spent: every step is a route
call the app makes. One project with a Claude runner. Steps, in the order the criterion's `when` gives:

  1. the operator creates an agent named `settings` (POST /agents): refused 400 and the detail names
     /queue/settings; one named `Sessions` (case-insensitive): refused 400 and the detail names
     /agent/sessions/{agent}; neither leaves an agent row behind;
  2. a task with id `board` (POST /tasks) is refused 422 naming `id`, and leaves no task;
  3. the near misses are not refused: an agent `conflict` is created, a task
     `boardroom` is created, GET /queue/conflict answers 200 for the agent and GET /tasks/boardroom
     answers 200 for the task.

Fails on today's Hub at check 1 (`settings` is created, 201). Stops at the first failure.

    py -3.11 scripts/drive/d1021_route_shadow_names.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8107
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1021-route-shadow-names" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def agent_names(base):
    code, out = d.api("GET", f"{base}/agents")
    assert code == 200, (code, out)
    rows = out if isinstance(out, list) else out.get("agents", out)
    return sorted(a["name"] for a in rows)


def task_ids(base):
    code, out = d.api("GET", f"{base}/tasks")
    assert code == 200, (code, out)
    rows = out if isinstance(out, list) else out["tasks"]
    return sorted(t["id"] for t in rows)


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# shadow\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "shadow"})
    assert code in (200, 201), (code, project)
    base = f"/projects/{project['id']}"
    d.api("PATCH", base, {"main_branch": "main"})
    _, runner = d.api(
        "POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU}
    )

    def create_agent(name):
        return d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})

    # 1: an agent named for a route registered before the agent's own routes is refused.
    agents_before = agent_names(base)
    code_s, out_s = create_agent("settings")
    code_c, out_c = create_agent("Sessions")
    d.check(
        "1 an agent named settings is refused 400 naming /queue/settings, Sessions 400 naming "
        "/agent/sessions/{agent}, and neither leaves a row",
        code_s == 400
        and "/queue/settings" in str(out_s)
        and code_c == 400
        and "/agent/sessions/{agent}" in str(out_c)
        and agent_names(base) == agents_before,
        f"settings={code_s} {out_s} / Sessions={code_c} {out_c}",
    )

    # 2: a task id the task routes would answer for is refused 422 naming id.
    ids_before = task_ids(base)
    code, out = d.api(
        "POST",
        f"{base}/tasks",
        {"title": "A board", "description": "x", "assignee": "alice", "id": "board"},
    )
    d.check(
        "2 a task with id board is refused 422 naming id, and leaves no task",
        code == 422 and "id" in str(out) and task_ids(base) == ids_before,
        f"{code} {out}",
    )

    # 3: near misses are created and answer on their own routes.
    code_a, out_a = create_agent("conflict")
    code_t, out_t = d.api(
        "POST",
        f"{base}/tasks",
        {"title": "A boardroom", "description": "x", "assignee": "conflict", "id": "boardroom"},
    )
    code_q, out_q = d.api("GET", f"{base}/queue/conflict")
    code_g, out_g = d.api("GET", f"{base}/tasks/boardroom")
    d.check(
        "3 conflict and boardroom are created; GET /queue/conflict and GET /tasks/boardroom answer",
        code_a in (200, 201)
        and code_t in (200, 201)
        and code_q == 200
        and code_g == 200
        and out_g.get("id") == "boardroom",
        f"agent={code_a} task={code_t} {out_t} queue={code_q} {out_q} get={code_g}",
    )


d.drive = drive

if __name__ == "__main__":
    d.main()
